from __future__ import annotations

import math

import numpy as np
import pandas as pd

from src.options.greeks import black_scholes_delta
from src.options.pricing import implied_volatility
from src.options.selection import option_mid_price

CALENDAR_DAYS_PER_YEAR = 365


def _finite_positive(value: object) -> bool:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(x) and x > 0


def _spot_lookup(etf_prices: pd.DataFrame) -> pd.Series:
    prices = etf_prices.copy()
    prices["date"] = pd.to_datetime(prices["date"])
    prices["etf_code"] = prices["etf_code"].astype(str)
    return prices.set_index(["etf_code", "date"])["adj_close"]


def _row_price(row: pd.Series) -> tuple[float, str, float]:
    try:
        return option_mid_price(row)
    except Exception:
        close = row.get("close", np.nan)
        return float(close) if pd.notna(close) else np.nan, "close", np.nan


def _standardize_one(row: pd.Series, rate: float) -> dict[str, object]:
    spot = row.get("spot", np.nan)
    strike = row.get("strike", np.nan)
    price = row.get("model_price_input", np.nan)
    years = row.get("years_to_expiry", np.nan)
    option_type = str(row.get("option_type", "")).upper()
    raw_iv = row.get("implied_vol", np.nan)
    raw_delta = row.get("delta", np.nan)

    if option_type not in {"C", "P"}:
        return {"model_iv": np.nan, "model_delta": np.nan, "delta_quality_flag": "invalid_option_type"}
    if not _finite_positive(spot):
        return {"model_iv": np.nan, "model_delta": np.nan, "delta_quality_flag": "invalid_spot"}
    if not _finite_positive(strike):
        return {"model_iv": np.nan, "model_delta": np.nan, "delta_quality_flag": "invalid_strike"}
    if not _finite_positive(years):
        return {"model_iv": np.nan, "model_delta": np.nan, "delta_quality_flag": "invalid_dte"}
    if not _finite_positive(price):
        return {"model_iv": np.nan, "model_delta": np.nan, "delta_quality_flag": "invalid_price"}

    model_iv = implied_volatility(float(price), float(spot), float(strike), float(years), rate, option_type)
    iv_source = "model_iv"
    quality = "valid_model_iv"
    if not _finite_positive(model_iv):
        if _finite_positive(raw_iv):
            model_iv = float(raw_iv)
            iv_source = "raw_implied_vol_fallback"
            quality = "raw_iv_fallback"
        else:
            return {"model_iv": np.nan, "model_delta": np.nan, "delta_quality_flag": "iv_failed"}

    try:
        model_delta = black_scholes_delta(float(spot), float(strike), float(years), rate, float(model_iv), option_type)
    except (ValueError, OverflowError):
        return {"model_iv": model_iv, "model_delta": np.nan, "delta_quality_flag": "delta_failed"}

    return {
        "model_iv": float(model_iv),
        "model_delta": float(model_delta),
        "model_abs_delta": abs(float(model_delta)),
        "raw_delta": float(raw_delta) if pd.notna(raw_delta) else np.nan,
        "raw_implied_vol": float(raw_iv) if pd.notna(raw_iv) else np.nan,
        "iv_source_for_delta": iv_source,
        "delta_quality_flag": quality,
    }


def build_delta_enriched_options(
    etf_prices: pd.DataFrame,
    options: pd.DataFrame,
    config: dict,
) -> pd.DataFrame:
    """Add model IV and Black-Scholes delta to an option chain.

    The output preserves all input option rows and appends standardized columns.
    Failed calculations are kept with explicit quality flags so later experiments
    can filter deliberately instead of inheriting silent data loss.
    """
    if options.empty:
        return options.copy()

    rate = float(
        config.get("delta_standardization", {}).get(
            "risk_free_rate",
            config.get("iv_timing", {}).get("risk_free_rate", 0.02),
        )
    )
    out = options.copy()
    out["trade_date"] = pd.to_datetime(out["trade_date"])
    out["expiry"] = pd.to_datetime(out["expiry"])
    out["underlying_etf"] = out["underlying_etf"].astype(str)
    out["option_type"] = out["option_type"].astype(str).str.upper()

    spot_by_key = _spot_lookup(etf_prices)
    keys = list(zip(out["underlying_etf"], out["trade_date"]))
    out["spot"] = [spot_by_key.get(key, np.nan) for key in keys]
    out["days_to_expiry"] = (out["expiry"] - out["trade_date"]).dt.days
    out["years_to_expiry"] = out["days_to_expiry"] / CALENDAR_DAYS_PER_YEAR

    price_info = out.apply(_row_price, axis=1, result_type="expand")
    price_info.columns = ["model_price_input", "model_price_source", "bid_ask_spread_pct"]
    out = pd.concat([out.reset_index(drop=True), price_info.reset_index(drop=True)], axis=1)

    calc = out.apply(lambda row: _standardize_one(row, rate), axis=1, result_type="expand")
    out = pd.concat([out.reset_index(drop=True), calc.reset_index(drop=True)], axis=1)
    out["moneyness"] = out["strike"] / out["spot"] - 1
    out["log_moneyness"] = np.log(out["strike"] / out["spot"])
    out["delta_standardization_rate"] = rate
    out["delta_valid"] = out["model_delta"].notna().astype(int)
    return out.sort_values(["underlying_etf", "trade_date", "expiry", "strike", "option_type"]).reset_index(drop=True)
