from __future__ import annotations

import numpy as np
import pandas as pd

from src.options.selection import select_option
from src.utils.dates import month_end_roll_dates


def _valid_bid_ask(df: pd.DataFrame) -> pd.Series:
    if not {"bid", "ask"}.issubset(df.columns):
        return pd.Series(False, index=df.index)
    mid = (df["bid"] + df["ask"]) / 2
    return (df["bid"] > 0) & (df["ask"] > df["bid"]) & (mid > 0)


def _nanmedian_or_nan(values: list[float]) -> float:
    cleaned = pd.Series(values, dtype="float64").dropna()
    return float(np.nanmedian(cleaned)) if len(cleaned) else np.nan


def compute_option_metrics(etf_prices: pd.DataFrame, options: pd.DataFrame, config: dict) -> pd.DataFrame:
    rows = []
    for etf_code, price_g in etf_prices.groupby("etf_code"):
        price_g = price_g.sort_values("date")
        opt = options[options["underlying_etf"] == etf_code].copy()
        overlapping_dates = price_g[
            (price_g["date"] >= opt["trade_date"].min()) & (price_g["date"] <= opt["trade_date"].max())
        ]["date"] if not opt.empty else pd.Series(dtype="datetime64[ns]")
        roll_dates = month_end_roll_dates(price_g["date"])
        eligible_rolls = 0
        atm_premium_yields = []
        delta_premium_yields = []
        selected_30delta_ivs = []
        atm_ivs = []
        for roll_date in roll_dates:
            spot_row = price_g[price_g["date"] == roll_date]
            if spot_row.empty:
                continue
            spot = float(spot_row.iloc[0]["adj_close"])
            atm = select_option(
                opt,
                roll_date,
                etf_code,
                spot,
                "atm",
                config["backtest"]["target_dte"],
                config["backtest"]["min_days_to_expiry"],
                config["backtest"]["max_days_to_expiry"],
                config["liquidity_filters"],
            )
            if atm.selected:
                eligible_rolls += 1
                atm_premium_yields.append(atm.option["selected_premium"] / spot)
                if pd.notna(atm.option.get("implied_vol", np.nan)):
                    atm_ivs.append(atm.option["implied_vol"])
            d30 = select_option(
                opt,
                roll_date,
                etf_code,
                spot,
                "delta30",
                config["backtest"]["target_dte"],
                config["backtest"]["min_days_to_expiry"],
                config["backtest"]["max_days_to_expiry"],
                config["liquidity_filters"],
            )
            if d30.selected:
                delta_premium_yields.append(d30.option["selected_premium"] / spot)
                if pd.notna(d30.option.get("implied_vol", np.nan)):
                    selected_30delta_ivs.append(d30.option["implied_vol"])

        valid_ba = _valid_bid_ask(opt)
        spread = pd.Series(np.nan, index=opt.index)
        if valid_ba.any():
            mid = (opt.loc[valid_ba, "bid"] + opt.loc[valid_ba, "ask"]) / 2
            spread.loc[valid_ba] = (opt.loc[valid_ba, "ask"] - opt.loc[valid_ba, "bid"]) / mid
        median_spread = float(spread.dropna().median()) if spread.notna().any() else np.nan
        rows.append(
            {
                "etf_code": etf_code,
                "has_options": not opt.empty,
                "number_of_option_trade_dates": opt["trade_date"].nunique() if not opt.empty else 0,
                "option_date_coverage_ratio": opt["trade_date"].nunique() / len(overlapping_dates)
                if len(overlapping_dates)
                else 0.0,
                "number_of_call_contracts": len(opt),
                "number_of_monthly_roll_dates_with_eligible_calls": eligible_rolls,
                "eligible_roll_date_ratio": eligible_rolls / len(roll_dates) if len(roll_dates) else 0.0,
                "median_call_volume": opt["volume"].median() if "volume" in opt else np.nan,
                "median_call_open_interest": opt["open_interest"].median() if "open_interest" in opt else np.nan,
                "median_call_amount": opt["amount"].median() if "amount" in opt else np.nan,
                "median_bid_ask_spread_pct": median_spread,
                "pct_contracts_with_valid_bid_ask": valid_ba.mean() if len(opt) else 0.0,
                "pct_contracts_with_valid_delta": opt["delta"].notna().mean() if "delta" in opt and len(opt) else 0.0,
                "pct_contracts_with_valid_iv": opt["implied_vol"].notna().mean()
                if "implied_vol" in opt and len(opt)
                else 0.0,
                "median_atm_call_iv": _nanmedian_or_nan(atm_ivs),
                "median_selected_30delta_call_iv": _nanmedian_or_nan(selected_30delta_ivs),
                "median_atm_premium_yield": _nanmedian_or_nan(atm_premium_yields),
                "median_30delta_premium_yield": _nanmedian_or_nan(delta_premium_yields),
            }
        )
    return pd.DataFrame(rows)
