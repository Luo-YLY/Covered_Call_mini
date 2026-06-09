from __future__ import annotations

import numpy as np
import pandas as pd

from src.features.etf_features import compute_etf_tradability_metrics
from src.features.option_features import compute_option_metrics


def _score_high_good(series: pd.Series) -> pd.Series:
    s = pd.to_numeric(series, errors="coerce")
    if s.notna().sum() == 0:
        return pd.Series(0.0, index=series.index)
    lo, hi = s.min(), s.max()
    if np.isclose(lo, hi):
        return pd.Series(50.0, index=series.index)
    return ((s - lo) / (hi - lo) * 100).fillna(0)


def _score_low_good(series: pd.Series) -> pd.Series:
    return 100 - _score_high_good(series)


def build_suitability_screen(
    etf_prices: pd.DataFrame,
    options: pd.DataFrame,
    metadata: pd.DataFrame,
    config: dict,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    etf_metrics = compute_etf_tradability_metrics(etf_prices)
    option_metrics = compute_option_metrics(etf_prices, options, config)
    screen = etf_metrics.merge(option_metrics, on="etf_code", how="left").merge(metadata, on="etf_code", how="left")
    screen["upside_truncation_risk_proxy"] = screen["strong_up_month_frequency"]

    scores = screen[["etf_code"]].copy()
    scores["etf_liquidity_score"] = (
        _score_high_good(np.log1p(screen["avg_daily_amount_252d"]))
        + _score_high_good(np.log1p(screen["median_daily_amount_252d"]))
    ) / 2
    scores["option_availability_score"] = (
        _score_high_good(screen["eligible_roll_date_ratio"])
        + _score_high_good(np.log1p(screen["number_of_call_contracts"].fillna(0)))
    ) / 2
    spread_score = _score_low_good(screen["median_bid_ask_spread_pct"].fillna(screen["median_bid_ask_spread_pct"].max()))
    scores["option_liquidity_score"] = (
        _score_high_good(np.log1p(screen["median_call_volume"].fillna(0)))
        + _score_high_good(np.log1p(screen["median_call_open_interest"].fillna(0)))
        + _score_high_good(np.log1p(screen["median_call_amount"].fillna(0)))
        + spread_score
    ) / 4
    premium_cols = screen[["median_atm_premium_yield", "median_30delta_premium_yield"]]
    premium_base = premium_cols.apply(lambda row: row.dropna().mean() if row.notna().any() else 0.0, axis=1)
    scores["premium_adequacy_score"] = _score_high_good(premium_base.fillna(0))
    scores["data_quality_score"] = (
        _score_high_good(screen["data_completeness_ratio"].fillna(0))
        + _score_high_good(screen["option_date_coverage_ratio"].fillna(0))
    ) / 2
    scores["upside_truncation_risk_score"] = _score_low_good(screen["upside_truncation_risk_proxy"].fillna(0))

    weights = config["suitability_weights"]
    scores["suitability_score"] = sum(scores[col] * weight for col, weight in weights.items())
    scores = scores.sort_values("suitability_score", ascending=False).reset_index(drop=True)
    return screen.sort_values("etf_code").reset_index(drop=True), scores
