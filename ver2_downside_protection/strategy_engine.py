from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

import numpy as np
import pandas as pd

from src.backtest.accounting import assert_accounting_identity, covered_call_period_return
from src.utils.dates import nearest_trading_date_on_or_after

from ver2_downside_protection.config import ExperimentConfig, StrategyConfig, with_transaction_cost_overrides
from ver2_downside_protection.cost_model import TransactionCostBreakdown, calculate_transaction_cost
from ver2_downside_protection.data_adapter import Ver2DataBundle, load_ver2_data, price_on, roll_dates_for_prices
from ver2_downside_protection.downside_analysis import build_downside_bucket_table
from ver2_downside_protection.metrics import add_period_diagnostics, summarize_ver2_performance
from ver2_downside_protection.option_selector import select_ver2_option

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class Ver2BacktestResult:
    periods: pd.DataFrame
    nav: pd.DataFrame
    daily_mtm: pd.DataFrame
    summary: pd.DataFrame
    downside_buckets: pd.DataFrame
    skipped_periods: pd.DataFrame
    metadata: dict[str, Any]


def _metadata_lookup(metadata: pd.DataFrame) -> dict[str, dict[str, Any]]:
    if metadata.empty or "etf_code" not in metadata.columns:
        return {}
    meta = metadata.copy()
    meta["etf_code"] = meta["etf_code"].astype(str).str.zfill(6)
    return meta.set_index("etf_code").to_dict(orient="index")


def _empty_option_fields(strategy: StrategyConfig) -> dict[str, Any]:
    return {
        "expiry_date": pd.NaT,
        "actual_dte": np.nan,
        "option_code": np.nan,
        "option_type": np.nan,
        "strike": np.nan,
        "option_price_at_entry": 0.0,
        "target_moneyness": strategy.target_moneyness,
        "realized_moneyness": np.nan,
        "underlying_price_at_expiry": np.nan,
        "option_payoff_at_expiry": 0.0,
        "option_payoff_return_at_expiry": 0.0,
        "option_intrinsic_value_at_expiry": 0.0,
        "price_source": "none",
        "selection_fallback_flag": np.nan,
        "selected_delta": np.nan,
        "selected_iv": np.nan,
        "bid_ask_spread_pct": np.nan,
        "raw_bid_ask_spread_pct": np.nan,
        "effective_bid_ask_spread_pct": np.nan,
        "bid_ask_spread_source": "none",
        "option_slippage_cost_return": 0.0,
        "bid_ask_spread_cost_return": 0.0,
        "etf_slippage_cost_return": 0.0,
        "option_commission_cost_return": 0.0,
    }


def _apply_cost_fields(option_fields: dict[str, Any], cost: TransactionCostBreakdown) -> None:
    option_fields.update(
        {
            "effective_bid_ask_spread_pct": cost.effective_bid_ask_spread_pct,
            "bid_ask_spread_source": cost.bid_ask_spread_source,
            "option_slippage_cost_return": cost.option_slippage_cost_return,
            "bid_ask_spread_cost_return": cost.bid_ask_spread_cost_return,
            "etf_slippage_cost_return": cost.etf_slippage_cost_return,
            "option_commission_cost_return": cost.option_commission_cost_return,
        }
    )


def _period_row(
    *,
    etf_code: str,
    style_bucket: object,
    strategy: StrategyConfig,
    period_index: int,
    roll_date: pd.Timestamp,
    period_end: pd.Timestamp,
    spot_start: float,
    spot_end: float,
    selected: bool,
    selection_reason: str,
    no_option_available: bool,
    option_fields: dict[str, Any],
    accounting: dict[str, Any],
) -> dict[str, Any]:
    row = {
        "etf_code": etf_code,
        "style_bucket": style_bucket,
        "strategy_name": strategy.name,
        "strategy_kind": strategy.kind,
        "period_index": period_index,
        "rebalance_date": roll_date,
        "period_end_date": period_end,
        "underlying_price_at_entry": spot_start,
        "underlying_price_at_period_end": spot_end,
        "coverage_ratio": strategy.coverage_ratio if selected else 0.0,
        "base_coverage_ratio": strategy.coverage_ratio,
        "option_selected_flag": int(selected),
        "no_option_available_flag": int(no_option_available),
        "selection_reason": selection_reason,
        "premium_return": accounting["premium_yield"],
        "upside_payoff_return": accounting["upside_cost"],
        "transaction_cost_return": accounting["cost"],
        "etf_period_return": accounting["R_etf"],
        "strategy_period_return": accounting["R_cc"],
        "excess_return_vs_etf": accounting["excess_return"],
        "assignment_flag": accounting["assignment_flag"],
        "premium_contribution": accounting["premium_contribution"],
        "upside_cost_contribution": accounting["upside_cost_contribution"],
        "transaction_cost_contribution": accounting["transaction_cost_contribution"],
        "net_option_contribution": accounting["net_option_contribution"],
    }
    row.update(option_fields)
    return row


def _buyhold_row(
    etf_code: str,
    style_bucket: object,
    period_index: int,
    roll_date: pd.Timestamp,
    period_end: pd.Timestamp,
    spot_start: float,
    spot_end: float,
) -> dict[str, Any]:
    strategy = StrategyConfig("BuyHold", "buy_hold", 0.0)
    accounting = covered_call_period_return(spot_start, spot_end, None, 0.0, 0.0, 0.0, None)
    return _period_row(
        etf_code=etf_code,
        style_bucket=style_bucket,
        strategy=strategy,
        period_index=period_index,
        roll_date=roll_date,
        period_end=period_end,
        spot_start=spot_start,
        spot_end=spot_end,
        selected=False,
        selection_reason="buy_hold",
        no_option_available=False,
        option_fields=_empty_option_fields(strategy),
        accounting=accounting,
    )


def _covered_call_row(
    *,
    data: Ver2DataBundle,
    config: ExperimentConfig,
    etf_code: str,
    style_bucket: object,
    strategy: StrategyConfig,
    period_index: int,
    roll_date: pd.Timestamp,
    period_end: pd.Timestamp,
    price_g: pd.DataFrame,
    spot_start: float,
    spot_end: float,
) -> dict[str, Any]:
    result = select_ver2_option(
        options=data.options,
        trade_date=roll_date,
        etf_code=etf_code,
        spot=spot_start,
        period_end=period_end,
        strategy=strategy,
        backtest=config.backtest,
        liquidity_filters=config.liquidity_filters,
    )
    selected = bool(result.selected)
    option = result.option or {}
    selection_reason = result.reason
    option_fields = _empty_option_fields(strategy)
    strike = None
    premium = 0.0
    settlement_spot = None

    if selected:
        strike = float(option["strike"])
        premium = float(option["selected_premium"])
        expiry = pd.Timestamp(option["expiry"])
        settlement_date = nearest_trading_date_on_or_after(price_g["date"], expiry)
        if settlement_date is None or settlement_date > period_end:
            LOGGER.warning(
                "Skipping %s %s on %s because settlement date is outside current period.",
                etf_code,
                strategy.name,
                roll_date.date(),
            )
            selected = False
            selection_reason = "contract_settlement_after_period_end"
            strike = None
            premium = 0.0
            option = {}
        else:
            settlement_spot = price_on(price_g, settlement_date)
            actual_dte = int((expiry - pd.Timestamp(roll_date)).days)
            intrinsic = max(settlement_spot - strike, 0.0)
            option_fields.update(
                {
                    "expiry_date": expiry,
                    "actual_dte": actual_dte,
                    "option_code": option.get("option_code", np.nan),
                    "option_type": option.get("option_type", "C"),
                    "strike": strike,
                    "option_price_at_entry": premium,
                    "target_moneyness": strategy.target_moneyness,
                    "realized_moneyness": strike / spot_start - 1.0,
                    "underlying_price_at_expiry": settlement_spot,
                    "option_intrinsic_value_at_expiry": intrinsic,
                    "price_source": option.get("price_source", "close"),
                    "selection_fallback_flag": result.fallback_flag,
                    "selected_delta": option.get("model_delta", option.get("delta", np.nan)),
                    "selected_iv": option.get("model_iv", option.get("implied_vol", np.nan)),
                    "bid_ask_spread_pct": option.get("bid_ask_spread_pct", np.nan),
                    "raw_bid_ask_spread_pct": option.get("bid_ask_spread_pct", np.nan),
                }
            )

    coverage_ratio = strategy.coverage_ratio if selected else 0.0
    cost_breakdown = calculate_transaction_cost(
        premium,
        spot_start,
        coverage_ratio,
        config.transaction_costs,
        option.get("bid_ask_spread_pct"),
    )
    _apply_cost_fields(option_fields, cost_breakdown)
    accounting = covered_call_period_return(
        spot_start=spot_start,
        spot_end=spot_end,
        strike=strike,
        premium=premium,
        coverage_ratio=coverage_ratio,
        transaction_cost=cost_breakdown.total_cost_return,
        option_settlement_spot=settlement_spot,
    )
    assert_accounting_identity(accounting)
    option_fields["option_payoff_at_expiry"] = coverage_ratio * option_fields["option_intrinsic_value_at_expiry"]
    option_fields["option_payoff_return_at_expiry"] = accounting["upside_cost"]

    return _period_row(
        etf_code=etf_code,
        style_bucket=style_bucket,
        strategy=strategy,
        period_index=period_index,
        roll_date=roll_date,
        period_end=period_end,
        spot_start=spot_start,
        spot_end=spot_end,
        selected=selected,
        selection_reason=selection_reason,
        no_option_available=not selected,
        option_fields=option_fields,
        accounting=accounting,
    )


def _next_trading_date(price_g: pd.DataFrame, date: pd.Timestamp) -> pd.Timestamp | None:
    dates = pd.DatetimeIndex(pd.to_datetime(price_g["date"]).sort_values().unique())
    later = dates[dates > pd.Timestamp(date)]
    return pd.Timestamp(later[0]) if len(later) else None


def _first_roll_date(price_g: pd.DataFrame, config: ExperimentConfig) -> pd.Timestamp:
    roll_dates = roll_dates_for_prices(price_g["date"], config.backtest.roll_frequency)
    if len(roll_dates) == 0:
        raise ValueError("No initial roll date is available.")
    return pd.Timestamp(roll_dates[0])


def _continuous_covered_call_rows(
    *,
    data: Ver2DataBundle,
    config: ExperimentConfig,
    etf_code: str,
    style_bucket: object,
    strategy: StrategyConfig,
    price_g: pd.DataFrame,
    first_rebalance_date: pd.Timestamp,
    last_date: pd.Timestamp,
) -> list[dict[str, Any]]:
    """Build event-driven DTE30 periods: expiry settlement immediately becomes the next rebalance."""

    rows: list[dict[str, Any]] = []
    rebalance_date = pd.Timestamp(first_rebalance_date)
    period_index = 1
    while rebalance_date < last_date:
        if (last_date - rebalance_date).days < config.backtest.min_days_to_expiry:
            LOGGER.info(
                "Ending %s %s continuous roll on %s because remaining sample days are below DTE window lower bound %s.",
                etf_code,
                strategy.name,
                rebalance_date.date(),
                config.backtest.min_days_to_expiry,
            )
            break
        spot_start = price_on(price_g, rebalance_date)
        result = select_ver2_option(
            options=data.options,
            trade_date=rebalance_date,
            etf_code=etf_code,
            spot=spot_start,
            period_end=last_date,
            strategy=strategy,
            backtest=config.backtest,
            liquidity_filters=config.liquidity_filters,
        )

        selected = bool(result.selected)
        option = result.option or {}
        selection_reason = result.reason
        option_fields = _empty_option_fields(strategy)
        strike = None
        premium = 0.0
        settlement_date: pd.Timestamp | None = None
        settlement_spot = None

        if selected:
            strike = float(option["strike"])
            premium = float(option["selected_premium"])
            expiry = pd.Timestamp(option["expiry"])
            settlement_date = nearest_trading_date_on_or_after(price_g["date"], expiry)
            if settlement_date is None or settlement_date > last_date:
                selected = False
                selection_reason = "contract_settlement_after_backtest_end"
                strike = None
                premium = 0.0
                option = {}
                settlement_date = None
            elif settlement_date <= rebalance_date:
                selected = False
                selection_reason = "invalid_non_forward_settlement"
                strike = None
                premium = 0.0
                option = {}
                settlement_date = None
            else:
                settlement_spot = price_on(price_g, settlement_date)
                intrinsic = max(settlement_spot - strike, 0.0)
                option_fields.update(
                    {
                        "expiry_date": expiry,
                        "actual_dte": int((expiry - rebalance_date).days),
                        "option_code": option.get("option_code", np.nan),
                        "option_type": option.get("option_type", "C"),
                        "strike": strike,
                        "option_price_at_entry": premium,
                        "target_moneyness": strategy.target_moneyness,
                        "realized_moneyness": strike / spot_start - 1.0,
                        "underlying_price_at_expiry": settlement_spot,
                        "option_intrinsic_value_at_expiry": intrinsic,
                        "price_source": option.get("price_source", "close"),
                        "selection_fallback_flag": result.fallback_flag,
                        "selected_delta": option.get("model_delta", option.get("delta", np.nan)),
                        "selected_iv": option.get("model_iv", option.get("implied_vol", np.nan)),
                        "bid_ask_spread_pct": option.get("bid_ask_spread_pct", np.nan),
                        "raw_bid_ask_spread_pct": option.get("bid_ask_spread_pct", np.nan),
                    }
                )

        if selected and settlement_date is not None and settlement_spot is not None:
            period_end = settlement_date
            spot_end = settlement_spot
            coverage_ratio = strategy.coverage_ratio
        else:
            next_date = _next_trading_date(price_g, rebalance_date)
            if next_date is None:
                break
            period_end = next_date
            spot_end = price_on(price_g, period_end)
            coverage_ratio = 0.0
            strike = None
            premium = 0.0
            settlement_spot = None
            option = {}

        cost_breakdown = calculate_transaction_cost(
            premium,
            spot_start,
            coverage_ratio,
            config.transaction_costs,
            option.get("bid_ask_spread_pct"),
        )
        _apply_cost_fields(option_fields, cost_breakdown)
        accounting = covered_call_period_return(
            spot_start=spot_start,
            spot_end=spot_end,
            strike=strike,
            premium=premium,
            coverage_ratio=coverage_ratio,
            transaction_cost=cost_breakdown.total_cost_return,
            option_settlement_spot=settlement_spot,
        )
        assert_accounting_identity(accounting)
        option_fields["option_payoff_at_expiry"] = coverage_ratio * option_fields["option_intrinsic_value_at_expiry"]
        option_fields["option_payoff_return_at_expiry"] = accounting["upside_cost"]
        rows.append(
            _period_row(
                etf_code=etf_code,
                style_bucket=style_bucket,
                strategy=strategy,
                period_index=period_index,
                roll_date=rebalance_date,
                period_end=period_end,
                spot_start=spot_start,
                spot_end=spot_end,
                selected=selected,
                selection_reason=selection_reason,
                no_option_available=not selected,
                option_fields=option_fields,
                accounting=accounting,
            )
        )
        rebalance_date = period_end
        period_index += 1

    return rows


def _buyhold_rows_from_calendar(
    etf_code: str,
    style_bucket: object,
    price_g: pd.DataFrame,
    calendar_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for idx, row in enumerate(calendar_rows, start=1):
        start = pd.Timestamp(row["rebalance_date"])
        end = pd.Timestamp(row["period_end_date"])
        rows.append(
            _buyhold_row(
                etf_code,
                style_bucket,
                idx,
                start,
                end,
                price_on(price_g, start),
                price_on(price_g, end),
            )
        )
    return rows


def _option_price_lookup(options: pd.DataFrame) -> dict[str, pd.DataFrame]:
    lookup: dict[str, pd.DataFrame] = {}
    if options.empty or "option_code" not in options.columns:
        return lookup
    cols = ["trade_date", "close"]
    for code, g in options.dropna(subset=["option_code"]).sort_values(["option_code", "trade_date"]).groupby("option_code"):
        lookup[str(code)] = g[cols].dropna(subset=["trade_date"]).copy()
    return lookup


def _option_price_on(
    lookup: dict[str, pd.DataFrame],
    option_code: object,
    date: pd.Timestamp,
    fallback: float,
) -> tuple[float, str]:
    if pd.isna(option_code):
        return 0.0, "none"
    g = lookup.get(str(option_code))
    if g is None or g.empty:
        return float(fallback), "fallback_initial"
    date = pd.Timestamp(date)
    exact = g[g["trade_date"] == date]
    if not exact.empty:
        return float(exact.iloc[-1]["close"]), "close"
    previous = g[g["trade_date"] <= date]
    if not previous.empty:
        return float(previous.iloc[-1]["close"]), "fallback_previous_close"
    return float(fallback), "fallback_initial"


def _build_daily_mtm(periods: pd.DataFrame, prices: pd.DataFrame, options: pd.DataFrame, initial_nav: float) -> pd.DataFrame:
    """Build daily mark-to-market rows for ETF plus short-call liability.

    Daily rows are diagnostic account marks. At expiry, the option mark is forced
    to settlement intrinsic value so the period-end MTM NAV matches period accounting.
    """

    option_codes = periods["option_code"].dropna().astype(str)
    option_codes = option_codes[option_codes.str.lower() != "nan"].unique()
    if len(option_codes):
        lookup_options = options[options["option_code"].astype(str).isin(option_codes)].copy()
    else:
        lookup_options = options.iloc[0:0].copy()
    lookup = _option_price_lookup(lookup_options)
    rows: list[dict[str, Any]] = []
    for (etf_code, strategy_name), g in periods.groupby(["etf_code", "strategy_name"]):
        price_g = prices[prices["etf_code"] == etf_code].sort_values("date")
        if price_g.empty:
            continue
        nav_start = float(initial_nav)
        for _, period in g.sort_values("rebalance_date").iterrows():
            start = pd.Timestamp(period["rebalance_date"])
            end = pd.Timestamp(period["period_end_date"])
            period_dates = pd.DatetimeIndex(
                price_g[(price_g["date"] >= start) & (price_g["date"] <= end)]["date"]
            )
            if period_dates.empty:
                continue
            entry_spot = float(period["underlying_price_at_entry"])
            entry_option_price = float(period.get("option_price_at_entry", 0.0) or 0.0)
            coverage = float(period.get("coverage_ratio", 0.0) or 0.0)
            option_code = period.get("option_code", np.nan)
            selected = bool(int(period.get("option_selected_flag", 0)))
            cost_return = float(period.get("transaction_cost_return", 0.0) or 0.0)
            premium_return = float(period.get("premium_return", 0.0) or 0.0)
            intrinsic_at_expiry = float(period.get("option_intrinsic_value_at_expiry", 0.0) or 0.0)
            for date in period_dates:
                date = pd.Timestamp(date)
                spot = price_on(price_g, date)
                if selected:
                    if date == start:
                        option_mark = entry_option_price
                        option_price_source = str(period.get("price_source", "entry"))
                        event = "open_call"
                    elif date == end:
                        option_mark = intrinsic_at_expiry
                        option_price_source = "settlement_intrinsic"
                        event = "expire_settle"
                    else:
                        option_mark, option_price_source = _option_price_on(
                            lookup,
                            option_code,
                            date,
                            entry_option_price,
                        )
                        event = "mark_to_market"
                    position_state = "short_call"
                else:
                    option_mark = 0.0
                    option_price_source = "none"
                    event = "no_option"
                    position_state = "no_option"

                etf_return_since_entry = spot / entry_spot - 1.0 if entry_spot else np.nan
                option_liability_return = coverage * option_mark / entry_spot if entry_spot else 0.0
                short_call_unrealized_pnl_return = premium_return - option_liability_return
                short_call_mtm_loss_return = max(option_liability_return - premium_return, 0.0)
                period_mtm_return = (
                    etf_return_since_entry
                    + premium_return
                    - option_liability_return
                    - cost_return
                )
                rows.append(
                    {
                        "date": date,
                        "etf_code": etf_code,
                        "strategy_name": strategy_name,
                        "execution_mode": period.get("execution_mode", np.nan),
                        "period_index": int(period["period_index"]),
                        "rebalance_date": start,
                        "period_end_date": end,
                        "position_state": position_state,
                        "event": event,
                        "underlying_price": spot,
                        "underlying_price_at_entry": entry_spot,
                        "underlying_return_since_entry": etf_return_since_entry,
                        "option_code": option_code,
                        "strike": period.get("strike", np.nan),
                        "expiry_date": period.get("expiry_date", pd.NaT),
                        "coverage_ratio": coverage,
                        "option_price_at_entry": entry_option_price,
                        "option_mark_price": option_mark,
                        "option_price_source": option_price_source,
                        "option_mark_change": option_mark - entry_option_price if selected else 0.0,
                        "option_liability_return": option_liability_return,
                        "short_call_unrealized_pnl_return": short_call_unrealized_pnl_return if selected else 0.0,
                        "short_call_mtm_loss_return": short_call_mtm_loss_return if selected else 0.0,
                        "premium_return": premium_return,
                        "transaction_cost_return": cost_return,
                        "option_slippage_cost_return": period.get("option_slippage_cost_return", 0.0),
                        "bid_ask_spread_cost_return": period.get("bid_ask_spread_cost_return", 0.0),
                        "etf_slippage_cost_return": period.get("etf_slippage_cost_return", 0.0),
                        "option_commission_cost_return": period.get("option_commission_cost_return", 0.0),
                        "effective_bid_ask_spread_pct": period.get("effective_bid_ask_spread_pct", np.nan),
                        "bid_ask_spread_source": period.get("bid_ask_spread_source", "none"),
                        "period_mtm_return": period_mtm_return,
                        "period_start_nav": nav_start,
                        "daily_mtm_nav": nav_start * (1.0 + period_mtm_return),
                    }
                )
            nav_start *= 1.0 + float(period["strategy_period_return"])
    return pd.DataFrame(rows).sort_values(["etf_code", "strategy_name", "date", "period_index"]).reset_index(drop=True)


def _build_nav(periods: pd.DataFrame, initial_nav: float) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for (etf_code, strategy_name), g in periods.groupby(["etf_code", "strategy_name"]):
        g = g.sort_values("rebalance_date")
        if g.empty:
            continue
        nav = float(initial_nav)
        rows.append(
            {
                "date": g.iloc[0]["rebalance_date"],
                "etf_code": etf_code,
                "strategy_name": strategy_name,
                "nav": nav,
            }
        )
        for _, row in g.iterrows():
            nav *= 1.0 + float(row["strategy_period_return"])
            rows.append(
                {
                    "date": row["period_end_date"],
                    "etf_code": etf_code,
                    "strategy_name": strategy_name,
                    "nav": nav,
                }
            )
    return (
        pd.DataFrame(rows)
        .drop_duplicates(["date", "etf_code", "strategy_name"], keep="last")
        .sort_values(["etf_code", "strategy_name", "date"])
        .reset_index(drop=True)
    )


def run_ver2_backtest(config: ExperimentConfig, data: Ver2DataBundle | None = None) -> Ver2BacktestResult:
    """Run the downside-protection experiment without modifying ver1 outputs."""

    data = data or load_ver2_data(config)
    meta_lookup = _metadata_lookup(data.metadata)
    strategies = config.enabled_strategies
    if not strategies:
        raise ValueError("No enabled strategies found in the ver2 config.")

    period_rows: list[dict[str, Any]] = []
    for etf_code in config.etf_codes:
        price_g = data.prices[data.prices["etf_code"] == etf_code].sort_values("date").copy()
        if config.backtest.start_date:
            price_g = price_g[price_g["date"] >= pd.Timestamp(config.backtest.start_date)]
        if config.backtest.end_date:
            price_g = price_g[price_g["date"] <= pd.Timestamp(config.backtest.end_date)]
        if price_g.empty:
            raise ValueError(f"No ETF prices found for {etf_code} after date filtering.")

        roll_dates = list(roll_dates_for_prices(price_g["date"], config.backtest.roll_frequency))
        available_monthly_periods = max(len(roll_dates) - 1, 0)
        if available_monthly_periods < config.backtest.min_periods:
            raise ValueError(
                f"{etf_code} only has {available_monthly_periods} initial monthly roll periods; "
                f"min_periods is {config.backtest.min_periods}."
            )

        style_bucket = meta_lookup.get(etf_code, {}).get("style_bucket", np.nan)
        LOGGER.info(
            "Running ver2 for %s in %s mode.",
            etf_code,
            config.backtest.execution_mode,
        )
        if config.backtest.execution_mode == "continuous_30d":
            first_rebalance_date = _first_roll_date(price_g, config)
            last_date = pd.Timestamp(price_g["date"].max())
            covered_by_strategy: dict[str, list[dict[str, Any]]] = {}
            for strategy in strategies:
                if strategy.kind == "buy_hold":
                    continue
                rows = _continuous_covered_call_rows(
                    data=data,
                    config=config,
                    etf_code=etf_code,
                    style_bucket=style_bucket,
                    strategy=strategy,
                    price_g=price_g,
                    first_rebalance_date=first_rebalance_date,
                    last_date=last_date,
                )
                covered_by_strategy[strategy.name] = rows
                period_rows.extend(rows)

            anchor_rows = next((rows for rows in covered_by_strategy.values() if rows), [])
            if anchor_rows:
                period_rows.extend(_buyhold_rows_from_calendar(etf_code, style_bucket, price_g, anchor_rows))
        else:
            for period_index, roll_date in enumerate(roll_dates[:-1], start=1):
                period_end = pd.Timestamp(roll_dates[period_index])
                roll_date = pd.Timestamp(roll_date)
                spot_start = price_on(price_g, roll_date)
                spot_end = price_on(price_g, period_end)
                period_rows.append(
                    _buyhold_row(etf_code, style_bucket, period_index, roll_date, period_end, spot_start, spot_end)
                )
                for strategy in strategies:
                    if strategy.kind == "buy_hold":
                        continue
                    period_rows.append(
                        _covered_call_row(
                            data=data,
                            config=config,
                            etf_code=etf_code,
                            style_bucket=style_bucket,
                            strategy=strategy,
                            period_index=period_index,
                            roll_date=roll_date,
                            period_end=period_end,
                            price_g=price_g,
                            spot_start=spot_start,
                            spot_end=spot_end,
                        )
                    )

    periods = add_period_diagnostics(pd.DataFrame(period_rows))
    if periods.empty:
        raise ValueError("No ver2 periods were generated.")
    periods["execution_mode"] = config.backtest.execution_mode
    nav = _build_nav(periods, config.backtest.initial_nav)
    daily_mtm = _build_daily_mtm(periods, data.prices, data.options, config.backtest.initial_nav)
    summary = summarize_ver2_performance(periods, nav)
    downside_buckets = build_downside_bucket_table(periods)
    skipped = periods[
        (periods["strategy_name"] != "BuyHold") & (periods["option_selected_flag"] == 0)
    ].copy()

    metadata = {
        "experiment_name": config.experiment_name,
        "etf_codes": list(config.etf_codes),
        "strategies": [strategy.name for strategy in strategies],
        "input_etf_prices": str(config.paths.etf_prices),
        "input_options": str(config.paths.options),
        "output_dir": str(config.paths.output_dir),
        "execution_mode": config.backtest.execution_mode,
    }
    return Ver2BacktestResult(
        periods=periods,
        nav=nav,
        daily_mtm=daily_mtm,
        summary=summary,
        downside_buckets=downside_buckets,
        skipped_periods=skipped,
        metadata=metadata,
    )


def run_ver2_backtest_with_transaction_costs(
    config: ExperimentConfig,
    data: Ver2DataBundle | None = None,
    *,
    assumed_bid_ask_spread_pct: float | None = None,
    use_assumed_bid_ask_spread_when_missing: bool | None = None,
    option_slippage_bps: float | None = None,
    etf_slippage_bps: float | None = None,
    charge_etf_slippage_on_roll: bool | None = None,
) -> Ver2BacktestResult:
    """Run ver2 with user-adjustable transaction-cost assumptions.

    This is the dashboard-friendly entry point: callers can keep the same base
    config and rerun with a different assumed bid/ask spread or slippage model.
    """

    overrides = {
        "assumed_bid_ask_spread_pct": assumed_bid_ask_spread_pct,
        "use_assumed_bid_ask_spread_when_missing": use_assumed_bid_ask_spread_when_missing,
        "option_slippage_bps": option_slippage_bps,
        "etf_slippage_bps": etf_slippage_bps,
        "charge_etf_slippage_on_roll": charge_etf_slippage_on_roll,
    }
    return run_ver2_backtest(with_transaction_cost_overrides(config, **overrides), data=data)
