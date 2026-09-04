from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from src.backtest.accounting import assert_accounting_identity, covered_call_period_return
from src.backtest.metrics import summarize_performance
from src.backtest.transaction_costs import proportional_cost
from src.options.selection import select_option
from src.utils.dates import nearest_trading_date_on_or_after


@dataclass(frozen=True)
class CustomBacktestRequest:
    etf_code: str
    target_delta: float = 0.30
    coverage_ratio: float = 1.0
    start_date: str | None = None
    end_date: str | None = None
    roll_frequency: str = "monthly"
    target_dte: int = 30
    min_days_to_expiry: int = 20
    max_days_to_expiry: int = 45
    selection_mode: str = "target_delta"
    otm_pct: float = 0.05
    initial_nav: float = 1.0
    min_periods: int = 6
    use_iv_timing: bool = False
    high_iv_coverage: float = 1.0
    normal_iv_coverage: float = 0.5
    low_iv_coverage: float = 0.0
    warmup_invalid_coverage: float = 0.0
    data_invalid_coverage: float = 0.0


DEFAULT_LIQUIDITY_FILTERS = {
    "min_option_volume": 0,
    "min_open_interest": 0,
    "max_bid_ask_spread_pct": 0.20,
}

DEFAULT_TRANSACTION_COSTS = {
    "option_slippage_bps": 5,
    "etf_slippage_bps": 2,
    "option_commission_per_contract": 0,
    "use_bid_ask_spread_cost": True,
}


def _validate_request(request: CustomBacktestRequest) -> list[str]:
    warnings = []
    if not 0 <= request.coverage_ratio <= 1:
        raise ValueError("coverage_ratio must be between 0 and 1.")
    if not 0.01 <= request.target_delta <= 0.95:
        raise ValueError("target_delta must be between 0.01 and 0.95.")
    if request.selection_mode not in {"target_delta", "atm", "otm_pct"}:
        raise ValueError("selection_mode must be one of: target_delta, atm, otm_pct.")
    if request.roll_frequency not in {"monthly", "weekly"}:
        raise ValueError("roll_frequency must be monthly or weekly.")
    if request.min_days_to_expiry <= 0 or request.max_days_to_expiry <= 0 or request.target_dte <= 0:
        raise ValueError("DTE inputs must be positive.")
    if request.min_days_to_expiry > request.target_dte or request.target_dte > request.max_days_to_expiry:
        raise ValueError("Require min_days_to_expiry <= target_dte <= max_days_to_expiry.")
    for name in [
        "high_iv_coverage",
        "normal_iv_coverage",
        "low_iv_coverage",
        "warmup_invalid_coverage",
        "data_invalid_coverage",
    ]:
        value = getattr(request, name)
        if not 0 <= value <= 1:
            raise ValueError(f"{name} must be between 0 and 1.")
    if request.roll_frequency == "weekly" and request.target_dte > 14:
        warnings.append("Weekly roll with target_dte above 14 may find few closed periods.")
    if request.roll_frequency == "monthly" and request.target_dte < 15:
        warnings.append("Monthly roll with target_dte below 15 may behave more like short weekly income.")
    return warnings


def _roll_dates(price_dates: pd.Series, frequency: str) -> pd.DatetimeIndex:
    dates = pd.DatetimeIndex(pd.to_datetime(price_dates).sort_values().unique())
    if len(dates) == 0:
        return pd.DatetimeIndex([])
    if frequency == "monthly":
        grouped = pd.Series(dates, index=dates).groupby(dates.to_period("M")).last()
    elif frequency == "weekly":
        grouped = pd.Series(dates, index=dates).groupby(dates.to_period("W-FRI")).last()
    else:
        raise ValueError(f"Unsupported roll_frequency: {frequency}")
    return pd.DatetimeIndex(grouped.values)


def _price_on(price_g: pd.DataFrame, date: pd.Timestamp) -> float:
    row = price_g[price_g["date"] == date]
    if row.empty:
        raise ValueError(f"No price for {date}")
    return float(row.iloc[0]["adj_close"])


def _mode_to_strategy_kind(selection_mode: str) -> str:
    if selection_mode == "target_delta":
        return "target_delta"
    if selection_mode == "otm_pct":
        return "otm_pct"
    return "atm"


def _iv_signal_on(iv_signals: pd.DataFrame | None, etf_code: str, date: pd.Timestamp) -> dict:
    if iv_signals is None or iv_signals.empty:
        return {}
    row = iv_signals[
        (iv_signals["etf_code"].astype(str).str.zfill(6) == str(etf_code).zfill(6))
        & (pd.to_datetime(iv_signals["trade_date"]) == pd.Timestamp(date))
    ]
    return row.iloc[0].to_dict() if not row.empty else {}


def _iv_multiplier(request: CustomBacktestRequest, iv_signal: dict) -> tuple[float, str]:
    if not request.use_iv_timing:
        return 1.0, "not_used"
    regime = str(iv_signal.get("iv_regime", "data_invalid"))
    mapping = {
        "high_iv": request.high_iv_coverage,
        "normal_iv": request.normal_iv_coverage,
        "low_iv": request.low_iv_coverage,
        "warmup_invalid": request.warmup_invalid_coverage,
        "data_invalid": request.data_invalid_coverage,
    }
    multiplier = float(mapping.get(regime, request.data_invalid_coverage))
    action = f"{regime}_{'sell' if multiplier > 0 else 'skip'}"
    return multiplier, action


def run_custom_covered_call_backtest(
    etf_prices: pd.DataFrame,
    options: pd.DataFrame,
    request: CustomBacktestRequest,
    metadata: pd.DataFrame | None = None,
    iv_signals: pd.DataFrame | None = None,
    liquidity_filters: dict | None = None,
    transaction_costs: dict | None = None,
) -> dict[str, pd.DataFrame | dict | list[str]]:
    warnings = _validate_request(request)
    liquidity_filters = liquidity_filters or DEFAULT_LIQUIDITY_FILTERS
    transaction_costs = transaction_costs or DEFAULT_TRANSACTION_COSTS

    etf_code = str(request.etf_code).zfill(6)
    prices = etf_prices.copy()
    opts = options.copy()
    prices["date"] = pd.to_datetime(prices["date"])
    prices["etf_code"] = prices["etf_code"].astype(str).str.zfill(6)
    opts["trade_date"] = pd.to_datetime(opts["trade_date"])
    opts["expiry"] = pd.to_datetime(opts["expiry"])
    opts["underlying_etf"] = opts["underlying_etf"].astype(str).str.zfill(6)
    ivs = iv_signals.copy() if iv_signals is not None else None
    if ivs is not None and not ivs.empty:
        ivs["trade_date"] = pd.to_datetime(ivs["trade_date"])
        ivs["etf_code"] = ivs["etf_code"].astype(str).str.zfill(6)

    price_g = prices[prices["etf_code"] == etf_code].sort_values("date").copy()
    if request.start_date:
        price_g = price_g[price_g["date"] >= pd.Timestamp(request.start_date)]
    if request.end_date:
        price_g = price_g[price_g["date"] <= pd.Timestamp(request.end_date)]
    if price_g.empty:
        raise ValueError(f"No ETF prices found for {etf_code} in the requested date window.")

    roll_dates = _roll_dates(price_g["date"], request.roll_frequency)
    if len(roll_dates) < request.min_periods + 1:
        raise ValueError(
            f"Only {max(len(roll_dates) - 1, 0)} roll periods are available; "
            f"min_periods is {request.min_periods}."
        )

    meta = {}
    if metadata is not None and not metadata.empty:
        meta_df = metadata.copy()
        meta_df["etf_code"] = meta_df["etf_code"].astype(str).str.zfill(6)
        meta = meta_df.set_index("etf_code").to_dict(orient="index")

    period_rows = []
    nav_rows = []
    strategy_name = (
        f"Custom_{request.selection_mode}_delta{request.target_delta:.2f}_"
        f"cov{request.coverage_ratio:.0%}_{request.roll_frequency}"
    )

    nav = float(request.initial_nav)
    nav_rows.append({"date": roll_dates[0], "etf_code": etf_code, "strategy": "S0_BuyHold", "nav": nav})
    nav_rows.append({"date": roll_dates[0], "etf_code": etf_code, "strategy": strategy_name, "nav": nav})

    for roll_idx, roll_date in enumerate(roll_dates[:-1]):
        period_end = pd.Timestamp(roll_dates[roll_idx + 1])
        spot_start = _price_on(price_g, pd.Timestamp(roll_date))
        spot_end = _price_on(price_g, period_end)

        bh_accounting = covered_call_period_return(spot_start, spot_end, None, 0.0, 0.0, 0.0)
        period_rows.append(
            {
                "etf_code": etf_code,
                "style_bucket": meta.get(etf_code, {}).get("style_bucket", np.nan),
                "strategy": "S0_BuyHold",
                "roll_date": roll_date,
                "end_date": period_end,
                "option_settlement_date": pd.NaT,
                "S0": spot_start,
                "ST": spot_end,
                "K": np.nan,
                "C0": 0.0,
                "coverage_ratio": 0.0,
                "option_selected_flag": 0,
                "no_option_available_flag": 0,
                "selection_reason": "buy_hold",
                "iv_timing_action": "not_used",
                "iv_regime": "not_used",
                "iv_multiplier": 0.0,
                "base_coverage_ratio": 0.0,
                "iv_30d_atm": np.nan,
                "iv_percentile_252": np.nan,
                "iv_signal_valid": np.nan,
                "price_source": "none",
                "option_code": np.nan,
                "selected_delta": np.nan,
                "selected_iv": np.nan,
                "days_to_expiry": np.nan,
                "moneyness": np.nan,
                **bh_accounting,
            }
        )

        iv_signal = _iv_signal_on(ivs, etf_code, pd.Timestamp(roll_date))
        iv_multiplier, iv_timing_action = _iv_multiplier(request, iv_signal)
        effective_coverage = request.coverage_ratio * iv_multiplier
        if effective_coverage <= 0:
            result = None
            option = {}
            selected = False
            strike = None
            premium = 0.0
            selection_reason = iv_timing_action
        else:
            result = select_option(
                opts,
                pd.Timestamp(roll_date),
                etf_code,
                spot_start,
                _mode_to_strategy_kind(request.selection_mode),
                request.target_dte,
                request.min_days_to_expiry,
                request.max_days_to_expiry,
                liquidity_filters,
                target_delta=request.target_delta,
                otm_pct=request.otm_pct,
                max_expiry_date=period_end,
            )
            option = result.option or {}
            selected = result.selected
            strike = float(option["strike"]) if selected else None
            premium = float(option["selected_premium"]) if selected else 0.0
            selection_reason = result.reason

        option_settlement_date = pd.NaT
        option_settlement_spot = None
        if selected:
            expiry = pd.Timestamp(option["expiry"])
            hold_end = nearest_trading_date_on_or_after(price_g["date"], expiry)
            if hold_end is not None and hold_end <= period_end:
                option_settlement_date = hold_end
                option_settlement_spot = _price_on(price_g, option_settlement_date)
            else:
                selected = False
                strike = None
                premium = 0.0
                option = {}
                selection_reason = "contract_expires_after_period_end"

        cost = proportional_cost(
            premium,
            spot_start,
            effective_coverage if selected else 0.0,
            transaction_costs,
            option.get("bid_ask_spread_pct"),
        )
        accounting = covered_call_period_return(
            spot_start,
            spot_end,
            strike,
            premium,
            effective_coverage if selected else 0.0,
            cost,
            option_settlement_spot,
        )
        assert_accounting_identity(accounting)
        period_rows.append(
            {
                "etf_code": etf_code,
                "style_bucket": meta.get(etf_code, {}).get("style_bucket", np.nan),
                "strategy": strategy_name,
                "roll_date": roll_date,
                "end_date": period_end,
                "option_settlement_date": option_settlement_date,
                "S0": spot_start,
                "ST": spot_end,
                "K": strike,
                "C0": premium,
                "coverage_ratio": effective_coverage if selected else 0.0,
                "base_coverage_ratio": request.coverage_ratio,
                "iv_multiplier": iv_multiplier,
                "option_selected_flag": int(selected),
                "no_option_available_flag": int(not selected),
                "selection_reason": selection_reason,
                "iv_timing_action": iv_timing_action,
                "iv_30d_atm": iv_signal.get("iv_30d_atm", np.nan),
                "iv_percentile_252": iv_signal.get("iv_percentile_252", np.nan),
                "iv_regime": iv_signal.get("iv_regime", "not_used" if not request.use_iv_timing else "data_invalid"),
                "iv_signal_valid": iv_signal.get("signal_valid", 0 if request.use_iv_timing else np.nan),
                "price_source": option.get("price_source", "none"),
                "option_code": option.get("option_code", np.nan),
                "selected_delta": option.get("model_delta", option.get("delta", np.nan)),
                "selected_iv": option.get("model_iv", option.get("implied_vol", np.nan)),
                "days_to_expiry": option.get("days_to_expiry", np.nan),
                "moneyness": strike / spot_start - 1 if strike else np.nan,
                **accounting,
            }
        )
        nav *= 1 + accounting["R_cc"]
        nav_rows.append({"date": period_end, "etf_code": etf_code, "strategy": strategy_name, "nav": nav})
        bh_nav = float(
            pd.DataFrame([r for r in nav_rows if r["strategy"] == "S0_BuyHold"])["nav"].iloc[-1]
        )
        nav_rows.append(
            {
                "date": period_end,
                "etf_code": etf_code,
                "strategy": "S0_BuyHold",
                "nav": bh_nav * (1 + bh_accounting["R_cc"]),
            }
        )

    periods = pd.DataFrame(period_rows)
    nav_df = pd.DataFrame(nav_rows).drop_duplicates(["date", "etf_code", "strategy"], keep="last")
    nav_df = nav_df.sort_values(["etf_code", "strategy", "date"]).reset_index(drop=True)
    summary, _ = summarize_performance(periods)
    diagnostics = {
        "request": asdict(request),
        "strategy_name": strategy_name,
        "available_periods": int(len(roll_dates) - 1),
        "selected_periods": int(periods[periods["strategy"] == strategy_name]["option_selected_flag"].sum()),
        "warnings": warnings,
    }
    return {"summary": summary, "periods": periods, "nav": nav_df, "diagnostics": diagnostics, "warnings": warnings}
