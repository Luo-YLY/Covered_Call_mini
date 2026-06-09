from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class OptionSelectionResult:
    selected: bool
    reason: str
    option: dict[str, Any] | None = None
    fallback_flag: str | None = None


def option_mid_price(row: pd.Series) -> tuple[float, str, float]:
    bid = row.get("bid", np.nan)
    ask = row.get("ask", np.nan)
    if pd.notna(bid) and pd.notna(ask) and bid > 0 and ask > bid:
        mid = (float(bid) + float(ask)) / 2
        spread_pct = (float(ask) - float(bid)) / mid if mid > 0 else np.nan
        return mid, "mid", spread_pct
    return float(row["close"]), "close", np.nan


def _apply_liquidity_filters(options: pd.DataFrame, filters: dict[str, Any]) -> pd.DataFrame:
    out = options.copy()
    if "volume" in out.columns:
        out = out[out["volume"].fillna(0) >= filters.get("min_option_volume", 0)]
    if "open_interest" in out.columns:
        out = out[out["open_interest"].fillna(0) >= filters.get("min_open_interest", 0)]
    if {"bid", "ask"}.issubset(out.columns):
        mid = (out["bid"] + out["ask"]) / 2
        spread_pct = (out["ask"] - out["bid"]) / mid.replace(0, np.nan)
        valid_or_missing = spread_pct.isna() | (spread_pct <= filters.get("max_bid_ask_spread_pct", 1.0))
        out = out[valid_or_missing]
    return out


def select_option(
    options: pd.DataFrame,
    trade_date: pd.Timestamp,
    underlying_etf: str,
    spot: float,
    strategy_kind: str,
    target_dte: int = 30,
    min_days_to_expiry: int = 20,
    max_days_to_expiry: int = 45,
    liquidity_filters: dict[str, Any] | None = None,
) -> OptionSelectionResult:
    liquidity_filters = liquidity_filters or {}
    t = pd.Timestamp(trade_date)
    chain = options[
        (options["trade_date"] == t)
        & (options["underlying_etf"].astype(str) == str(underlying_etf))
        & (options["option_type"].astype(str).str.upper() == "C")
    ].copy()
    if chain.empty:
        return OptionSelectionResult(False, "no_chain_on_trade_date")

    chain["days_to_expiry"] = (pd.to_datetime(chain["expiry"]) - t).dt.days
    chain = chain[
        (chain["days_to_expiry"] >= min_days_to_expiry)
        & (chain["days_to_expiry"] <= max_days_to_expiry)
    ]
    if chain.empty:
        return OptionSelectionResult(False, "no_contract_in_dte_window")

    chain = _apply_liquidity_filters(chain, liquidity_filters)
    if chain.empty:
        return OptionSelectionResult(False, "no_contract_after_liquidity_filters")

    chain["_expiry_distance"] = (chain["days_to_expiry"] - target_dte).abs()
    best_expiry = chain.sort_values("_expiry_distance").iloc[0]["expiry"]
    chain = chain[chain["expiry"] == best_expiry].copy()

    fallback_flag = None
    if strategy_kind == "atm":
        chain["_selection_distance"] = (chain["strike"] - spot).abs()
    elif strategy_kind == "otm5":
        chain["_selection_distance"] = (chain["strike"] - spot * 1.05).abs()
    elif strategy_kind == "delta30":
        delta_col = "model_delta" if "model_delta" in chain.columns and not chain["model_delta"].dropna().empty else "delta"
        if delta_col not in chain.columns or chain[delta_col].dropna().empty:
            return OptionSelectionResult(False, "delta_unavailable_for_delta30", fallback_flag="delta_missing")
        chain["_selection_distance"] = (chain[delta_col] - 0.30).abs()
    else:
        raise ValueError(f"Unknown strategy_kind: {strategy_kind}")

    row = chain.sort_values(["_selection_distance", "strike"]).iloc[0].copy()
    premium, price_source, spread_pct = option_mid_price(row)
    row["selected_premium"] = premium
    row["price_source"] = price_source
    row["bid_ask_spread_pct"] = spread_pct
    return OptionSelectionResult(True, "selected", option=row.to_dict(), fallback_flag=fallback_flag)
