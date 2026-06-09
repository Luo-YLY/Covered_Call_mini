from __future__ import annotations

import numpy as np
import pandas as pd

from src.options.pricing import implied_volatility
from src.options.selection import option_mid_price

TRADING_DAYS_PER_YEAR = 252
CALENDAR_DAYS_PER_YEAR = 365


def _rolling_percentile(series: pd.Series, window: int, min_periods: int) -> pd.Series:
    def pct_rank(values: np.ndarray) -> float:
        current = values[-1]
        if np.isnan(current):
            return np.nan
        valid = values[~np.isnan(values)]
        if len(valid) < min_periods:
            return np.nan
        return float((valid <= current).mean())

    valid_series = series.dropna()
    ranks = valid_series.rolling(window=window, min_periods=min_periods).apply(pct_rank, raw=True)
    return ranks.reindex(series.index)


def _apply_liquidity_filters(options: pd.DataFrame, filters: dict) -> pd.DataFrame:
    out = options.copy()
    if "volume" in out.columns:
        out = out[out["volume"].fillna(0) >= filters.get("min_option_volume", 0)]
    if "open_interest" in out.columns:
        out = out[out["open_interest"].fillna(0) >= filters.get("min_open_interest", 0)]
    if {"bid", "ask"}.issubset(out.columns):
        mid = (out["bid"] + out["ask"]) / 2
        spread_pct = (out["ask"] - out["bid"]) / mid.replace(0, np.nan)
        out = out[spread_pct.isna() | (spread_pct <= filters.get("max_bid_ask_spread_pct", 1.0))]
    return out


def _best_atm_leg(
    chain: pd.DataFrame,
    option_type: str,
    spot: float,
    trade_date: pd.Timestamp,
    rate: float,
) -> dict[str, float | str] | None:
    leg = chain[chain["option_type"].astype(str).str.upper() == option_type].copy()
    if leg.empty:
        return None
    leg["_atm_distance"] = (leg["strike"] - spot).abs()
    row = leg.sort_values(["_atm_distance", "strike"]).iloc[0]
    price, price_source, spread_pct = option_mid_price(row)
    years = max((pd.Timestamp(row["expiry"]) - trade_date).days, 0) / CALENDAR_DAYS_PER_YEAR
    iv = implied_volatility(price, spot, float(row["strike"]), years, rate, option_type)
    return {
        "iv": iv,
        "strike": float(row["strike"]),
        "price": float(price),
        "price_source": price_source,
        "bid_ask_spread_pct": float(spread_pct) if pd.notna(spread_pct) else np.nan,
    }


def _expiry_atm_iv(
    chain: pd.DataFrame,
    spot: float,
    trade_date: pd.Timestamp,
    rate: float,
) -> dict[str, float | str]:
    call = _best_atm_leg(chain, "C", spot, trade_date, rate)
    put = _best_atm_leg(chain, "P", spot, trade_date, rate)
    call_iv = call["iv"] if call else np.nan
    put_iv = put["iv"] if put else np.nan
    iv_values = pd.Series([call_iv, put_iv], dtype="float64").dropna()
    expiry = pd.Timestamp(chain.iloc[0]["expiry"])
    return {
        "expiry": expiry,
        "days_to_expiry": int((expiry - trade_date).days),
        "atm_iv": float(iv_values.mean()) if len(iv_values) else np.nan,
        "call_iv": float(call_iv) if pd.notna(call_iv) else np.nan,
        "put_iv": float(put_iv) if pd.notna(put_iv) else np.nan,
        "call_strike": call["strike"] if call else np.nan,
        "put_strike": put["strike"] if put else np.nan,
        "price_source": "mid" if any((call or {}).get("price_source") == "mid" for call in [call, put]) else "close",
    }


def _constant_maturity_iv(expiry_rows: list[dict], target_dte: int) -> dict[str, float | str]:
    valid = [row for row in expiry_rows if pd.notna(row["atm_iv"])]
    if not valid:
        return {"iv_30d_atm": np.nan, "near_expiry": pd.NaT, "next_expiry": pd.NaT, "iv_quality_flag": "no_valid_iv"}

    target_years = target_dte / CALENDAR_DAYS_PER_YEAR
    below = [row for row in valid if row["days_to_expiry"] <= target_dte]
    above = [row for row in valid if row["days_to_expiry"] >= target_dte]
    near = max(below, key=lambda row: row["days_to_expiry"]) if below else None
    nxt = min(above, key=lambda row: row["days_to_expiry"]) if above else None

    if near and nxt and near["expiry"] != nxt["expiry"]:
        t1 = near["days_to_expiry"] / CALENDAR_DAYS_PER_YEAR
        t2 = nxt["days_to_expiry"] / CALENDAR_DAYS_PER_YEAR
        total_var_1 = near["atm_iv"] ** 2 * t1
        total_var_2 = nxt["atm_iv"] ** 2 * t2
        total_var_30 = total_var_1 + (total_var_2 - total_var_1) * (target_years - t1) / (t2 - t1)
        return {
            "iv_30d_atm": float(np.sqrt(max(total_var_30 / target_years, 0.0))),
            "near_expiry": near["expiry"],
            "next_expiry": nxt["expiry"],
            "near_dte": near["days_to_expiry"],
            "next_dte": nxt["days_to_expiry"],
            "near_atm_iv": near["atm_iv"],
            "next_atm_iv": nxt["atm_iv"],
            "call_iv_30d_atm": np.nanmean([near["call_iv"], nxt["call_iv"]]),
            "put_iv_30d_atm": np.nanmean([near["put_iv"], nxt["put_iv"]]),
            "atm_strike": np.nanmean([near["call_strike"], near["put_strike"], nxt["call_strike"], nxt["put_strike"]]),
            "iv_quality_flag": "interpolated",
        }

    closest = min(valid, key=lambda row: abs(row["days_to_expiry"] - target_dte))
    return {
        "iv_30d_atm": closest["atm_iv"],
        "near_expiry": closest["expiry"],
        "next_expiry": closest["expiry"],
        "near_dte": closest["days_to_expiry"],
        "next_dte": closest["days_to_expiry"],
        "near_atm_iv": closest["atm_iv"],
        "next_atm_iv": closest["atm_iv"],
        "call_iv_30d_atm": closest["call_iv"],
        "put_iv_30d_atm": closest["put_iv"],
        "atm_strike": np.nanmean([closest["call_strike"], closest["put_strike"]]),
        "iv_quality_flag": "single_expiry",
    }


def build_30d_atm_iv_signals(
    etf_prices: pd.DataFrame,
    options: pd.DataFrame,
    config: dict,
) -> pd.DataFrame:
    iv_config = config.get("iv_timing", {})
    target_dte = iv_config.get("target_dte", config["backtest"].get("target_dte", 30))
    min_dte = iv_config.get("min_days_to_expiry", config["backtest"].get("min_days_to_expiry", 20))
    max_dte = iv_config.get("max_days_to_expiry", config["backtest"].get("max_days_to_expiry", 45))
    rate = iv_config.get("risk_free_rate", 0.02)
    percentile_window = iv_config.get("percentile_window", 252)
    min_percentile_obs = iv_config.get("min_percentile_observations", 60)
    liquidity_filters = config.get("liquidity_filters", {})

    rows = []
    prices = etf_prices.sort_values(["etf_code", "date"]).copy()
    options = options.sort_values(["underlying_etf", "trade_date", "expiry", "strike"]).copy()

    for etf_code, price_g in prices.groupby("etf_code"):
        opt_g = options[options["underlying_etf"].astype(str) == str(etf_code)]
        if opt_g.empty:
            continue
        spot_by_date = price_g.set_index("date")["adj_close"]
        for trade_date, chain in opt_g.groupby("trade_date"):
            trade_date = pd.Timestamp(trade_date)
            if trade_date not in spot_by_date.index:
                continue
            spot = float(spot_by_date.loc[trade_date])
            chain = chain.copy()
            chain["days_to_expiry"] = (pd.to_datetime(chain["expiry"]) - trade_date).dt.days
            chain = chain[(chain["days_to_expiry"] >= min_dte) & (chain["days_to_expiry"] <= max_dte)]
            chain = _apply_liquidity_filters(chain, liquidity_filters)
            if chain.empty:
                rows.append(
                    {
                        "trade_date": trade_date,
                        "etf_code": etf_code,
                        "spot": spot,
                        "iv_30d_atm": np.nan,
                        "iv_quality_flag": "no_contract_after_filters",
                    }
                )
                continue
            expiry_rows = [
                _expiry_atm_iv(expiry_chain, spot, trade_date, rate)
                for _, expiry_chain in chain.groupby("expiry")
            ]
            row = {
                "trade_date": trade_date,
                "etf_code": etf_code,
                "spot": spot,
                **_constant_maturity_iv(expiry_rows, target_dte),
            }
            rows.append(row)

    signals = pd.DataFrame(rows)
    if signals.empty:
        return signals

    signals = signals.sort_values(["etf_code", "trade_date"]).reset_index(drop=True)
    out = []
    for etf_code, g in signals.groupby("etf_code"):
        g = g.copy()
        g["iv_observation_count"] = g["iv_30d_atm"].notna().cumsum()
        g["iv_percentile_252"] = _rolling_percentile(g["iv_30d_atm"], percentile_window, min_percentile_obs)
        valid_iv = g["iv_30d_atm"].dropna()
        rolling_mean = valid_iv.rolling(percentile_window, min_periods=min_percentile_obs).mean()
        rolling_std = valid_iv.rolling(percentile_window, min_periods=min_percentile_obs).std()
        g["iv_zscore_252"] = ((valid_iv - rolling_mean) / rolling_std).reindex(g.index)

        price_g = prices[prices["etf_code"] == etf_code].set_index("date").sort_index()
        daily_ret = price_g["adj_close"].pct_change()
        rv20 = daily_ret.rolling(20, min_periods=15).std() * np.sqrt(TRADING_DAYS_PER_YEAR)
        rv30 = daily_ret.rolling(30, min_periods=20).std() * np.sqrt(TRADING_DAYS_PER_YEAR)
        g["rv_20d"] = g["trade_date"].map(rv20)
        g["rv_30d"] = g["trade_date"].map(rv30)
        g["iv_rv_spread"] = g["iv_30d_atm"] - g["rv_20d"]
        g["iv_rv_ratio"] = g["iv_30d_atm"] / g["rv_20d"].replace(0, np.nan)
        g["iv_regime"] = np.select(
            [
                g["iv_percentile_252"] >= iv_config.get("high_iv_percentile", 0.70),
                g["iv_percentile_252"] <= iv_config.get("low_iv_percentile", 0.30),
            ],
            ["high_iv", "low_iv"],
            default="normal_iv",
        )
        g["iv_invalid_reason"] = "valid"
        warmup_invalid = (
            g["iv_30d_atm"].notna()
            & g["iv_percentile_252"].isna()
            & (g["iv_observation_count"] < min_percentile_obs)
        )
        data_invalid = g["iv_30d_atm"].isna() | (g["iv_percentile_252"].isna() & ~warmup_invalid)
        g.loc[warmup_invalid, "iv_regime"] = "warmup_invalid"
        g.loc[warmup_invalid, "iv_invalid_reason"] = "warmup"
        g.loc[data_invalid, "iv_regime"] = "data_invalid"
        g.loc[data_invalid, "iv_invalid_reason"] = "data_quality"
        g["signal_valid"] = g["iv_regime"].isin(["high_iv", "normal_iv", "low_iv"]).astype(int)
        out.append(g)

    return pd.concat(out, ignore_index=True)
