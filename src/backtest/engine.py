from __future__ import annotations

import numpy as np
import pandas as pd

from src.backtest.accounting import assert_accounting_identity, covered_call_period_return
from src.backtest.transaction_costs import proportional_cost
from src.options.selection import select_option
from src.strategies.base import STRATEGY_SPECS
from src.utils.dates import month_end_roll_dates, nearest_trading_date_on_or_after


def _price_on(price_g: pd.DataFrame, date: pd.Timestamp) -> float:
    row = price_g[price_g["date"] == date]
    if row.empty:
        raise ValueError(f"No price for {date}")
    return float(row.iloc[0]["adj_close"])


def _iv_signal_on(iv_signals: pd.DataFrame | None, etf_code: str, date: pd.Timestamp) -> dict:
    if iv_signals is None or iv_signals.empty:
        return {}
    row = iv_signals[
        (iv_signals["etf_code"].astype(str) == str(etf_code))
        & (pd.to_datetime(iv_signals["trade_date"]) == pd.Timestamp(date))
    ]
    return row.iloc[0].to_dict() if not row.empty else {}


def _coverage_from_iv_signal(spec, iv_signal: dict, config: dict) -> tuple[float, str]:
    if not spec.use_iv_timing:
        return spec.coverage_ratio, "not_used"

    iv_config = config.get("iv_timing", {})
    regime = str(iv_signal.get("iv_regime", "data_invalid"))
    if regime == "high_iv":
        high_coverage = float(iv_config.get("high_iv_coverage_ratio", spec.coverage_ratio))
        return (high_coverage, "high_iv_sell") if high_coverage > 0 else (0.0, "high_iv_skip")
    if regime == "normal_iv":
        normal_coverage = float(iv_config.get("normal_iv_coverage_ratio", 0.5 * spec.coverage_ratio))
        return (normal_coverage, "normal_iv_sell") if normal_coverage > 0 else (0.0, "normal_iv_skip")
    if regime == "low_iv":
        low_coverage = float(iv_config.get("low_iv_coverage_ratio", 0.0))
        return (low_coverage, "low_iv_sell") if low_coverage > 0 else (0.0, "low_iv_skip")
    if regime == "warmup_invalid":
        warmup_coverage = float(iv_config.get("warmup_invalid_coverage_ratio", 0.0))
        return (
            (warmup_coverage, "warmup_invalid_sell")
            if warmup_coverage > 0
            else (0.0, "warmup_invalid_skip")
        )
    data_invalid_coverage = float(iv_config.get("data_invalid_coverage_ratio", 0.0))
    return (
        (data_invalid_coverage, "data_invalid_sell")
        if data_invalid_coverage > 0
        else (0.0, "data_invalid_skip")
    )


def run_fixed_covered_call_backtest(
    etf_prices: pd.DataFrame,
    options: pd.DataFrame,
    metadata: pd.DataFrame,
    config: dict,
    iv_signals: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    period_rows = []
    nav_rows = []
    meta = metadata.set_index("etf_code").to_dict(orient="index") if not metadata.empty else {}

    for etf_code, price_g in etf_prices.groupby("etf_code"):
        price_g = price_g.sort_values("date").copy()
        if config["backtest"].get("start_date"):
            price_g = price_g[price_g["date"] >= pd.Timestamp(config["backtest"]["start_date"])]
        if config["backtest"].get("end_date"):
            price_g = price_g[price_g["date"] <= pd.Timestamp(config["backtest"]["end_date"])]
        roll_dates = month_end_roll_dates(price_g["date"])
        if len(roll_dates) < 2:
            continue
        for strategy_name in config["strategies"]:
            spec = STRATEGY_SPECS[strategy_name]
            nav = float(config["backtest"]["initial_nav"])
            nav_rows.append({"date": roll_dates[0], "etf_code": etf_code, "strategy": strategy_name, "nav": nav})
            for roll_idx, roll_date in enumerate(roll_dates[:-1]):
                spot_start = _price_on(price_g, roll_date)
                period_end = roll_dates[roll_idx + 1]
                option_settlement_date = pd.NaT
                option_settlement_spot = None
                strike = None
                premium = 0.0
                selected = False
                no_option = 0
                reason = "buy_hold"
                option = {}
                fallback_flag = None
                price_source = "none"
                iv_signal = _iv_signal_on(iv_signals, etf_code, roll_date)
                coverage_ratio, iv_timing_action = _coverage_from_iv_signal(spec, iv_signal, config)
                if spec.kind != "buy_hold":
                    if coverage_ratio <= 0:
                        reason = iv_timing_action
                    else:
                        result = select_option(
                            options,
                            roll_date,
                            etf_code,
                            spot_start,
                            spec.kind,
                            config["backtest"]["target_dte"],
                            config["backtest"]["min_days_to_expiry"],
                            config["backtest"]["max_days_to_expiry"],
                            config["liquidity_filters"],
                        )
                        reason = result.reason
                        fallback_flag = result.fallback_flag
                        if result.selected:
                            selected = True
                            option = result.option or {}
                            strike = float(option["strike"])
                            premium = float(option["selected_premium"])
                            expiry = pd.Timestamp(option["expiry"])
                            hold_end = nearest_trading_date_on_or_after(price_g["date"], expiry)
                            option_settlement_date = hold_end if hold_end is not None else expiry
                            option_settlement_spot = (
                                _price_on(price_g, option_settlement_date)
                                if hold_end is not None
                                else _price_on(price_g, period_end)
                            )
                            price_source = str(option.get("price_source", "close"))
                        else:
                            no_option = 1
                spot_end = _price_on(price_g, period_end)
                cost = proportional_cost(
                    premium,
                    spot_start,
                    coverage_ratio if selected else 0.0,
                    config["transaction_costs"],
                    option.get("bid_ask_spread_pct"),
                )
                accounting = covered_call_period_return(
                    spot_start,
                    spot_end,
                    strike,
                    premium,
                    coverage_ratio if selected else 0.0,
                    cost,
                    option_settlement_spot,
                )
                assert_accounting_identity(accounting)
                period = {
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
                    "coverage_ratio": coverage_ratio if selected else 0.0,
                    "option_selected_flag": int(selected),
                    "no_option_available_flag": int(no_option),
                    "selection_reason": reason,
                    "iv_timing_action": iv_timing_action,
                    "iv_30d_atm": iv_signal.get("iv_30d_atm", np.nan),
                    "iv_percentile_252": iv_signal.get("iv_percentile_252", np.nan),
                    "iv_regime": iv_signal.get("iv_regime", "not_used" if not spec.use_iv_timing else "data_invalid"),
                    "iv_invalid_reason": iv_signal.get("iv_invalid_reason", np.nan),
                    "iv_observation_count": iv_signal.get("iv_observation_count", np.nan),
                    "rv_20d": iv_signal.get("rv_20d", np.nan),
                    "iv_rv_spread": iv_signal.get("iv_rv_spread", np.nan),
                    "iv_signal_valid": iv_signal.get("signal_valid", 0 if spec.use_iv_timing else np.nan),
                    "fallback_flag": fallback_flag,
                    "price_source": price_source,
                    "option_code": option.get("option_code", np.nan),
                    "selected_delta": option.get("model_delta", option.get("delta", np.nan)),
                    "selected_iv": option.get("model_iv", option.get("implied_vol", np.nan)),
                    "days_to_expiry": option.get("days_to_expiry", np.nan),
                    "moneyness": strike / spot_start - 1 if strike else np.nan,
                    **accounting,
                }
                period_rows.append(period)
                nav *= 1 + accounting["R_cc"]
                nav_rows.append({"date": period_end, "etf_code": etf_code, "strategy": strategy_name, "nav": nav})
    periods = pd.DataFrame(period_rows)
    nav = pd.DataFrame(nav_rows).drop_duplicates(["date", "etf_code", "strategy"], keep="last")
    nav = nav.sort_values(["etf_code", "strategy", "date"]).reset_index(drop=True)
    return periods, nav
