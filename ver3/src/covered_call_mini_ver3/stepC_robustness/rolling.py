from __future__ import annotations

import numpy as np
import pandas as pd

from .metrics import compute_metrics_from_returns, compute_single_path_metrics


def compute_calendar_year_metrics(candidate_returns: pd.DataFrame) -> pd.DataFrame:
    """Compute calendar-year metrics."""

    data = candidate_returns.copy()
    data["calendar_year"] = pd.to_datetime(data["date"]).dt.year.astype(str)
    return compute_metrics_from_returns(data, group_cols=["portfolio_name", "calendar_year"])


def compute_half_year_metrics(candidate_returns: pd.DataFrame) -> pd.DataFrame:
    """Compute half-year metrics."""

    data = candidate_returns.copy()
    dt = pd.to_datetime(data["date"])
    half = np.where(dt.dt.month <= 6, "H1", "H2")
    data["half_year"] = dt.dt.year.astype(str) + "_" + half
    return compute_metrics_from_returns(data, group_cols=["portfolio_name", "half_year"])


def compute_rolling_metrics(candidate_returns: pd.DataFrame, window_days: int) -> pd.DataFrame:
    """Compute rolling-window metrics for each candidate."""

    rows: list[dict[str, object]] = []
    for portfolio_name, group in candidate_returns.groupby("portfolio_name", sort=True):
        g = group.sort_values("date").reset_index(drop=True)
        if len(g) < window_days:
            continue
        for end_idx in range(window_days - 1, len(g)):
            window = g.iloc[end_idx - window_days + 1 : end_idx + 1].copy()
            metrics = compute_single_path_metrics(window)
            rows.append(
                {
                    "portfolio_name": portfolio_name,
                    "window_days": int(window_days),
                    "window_start": pd.Timestamp(window["date"].iloc[0]).date().isoformat(),
                    "window_end": pd.Timestamp(window["date"].iloc[-1]).date().isoformat(),
                    "n_obs": int(len(window)),
                    "rolling_cagr": metrics["annualized_return_cagr"],
                    "rolling_sharpe": metrics["sharpe_daily_mean"],
                    "rolling_volatility": metrics["annualized_volatility"],
                    "rolling_mdd": metrics["max_drawdown"],
                    "rolling_calmar": metrics["calmar_ratio"],
                    "rolling_sortino": metrics["sortino_ratio"],
                    "rolling_final_nav_over_window": metrics["final_nav"],
                    "rolling_option_leg_contribution": metrics["option_leg_annualized_pnl_contribution"],
                }
            )
    return pd.DataFrame(rows)


def compute_rolling_stability_summary(rolling_252: pd.DataFrame, rolling_504: pd.DataFrame) -> pd.DataFrame:
    """Summarize rolling stability statistics."""

    rows = []
    for window_days, data in [(252, rolling_252), (504, rolling_504)]:
        if data.empty:
            continue
        rank_data = data.copy()
        rank_data["rank_by_sharpe"] = rank_data.groupby("window_end")["rolling_sharpe"].rank(ascending=False, method="min")
        for portfolio_name, group in rank_data.groupby("portfolio_name", sort=True):
            rows.append(
                {
                    "portfolio_name": portfolio_name,
                    "window_days": window_days,
                    "n_windows": int(len(group)),
                    "rolling_sharpe_mean": float(group["rolling_sharpe"].mean()),
                    "rolling_sharpe_median": float(group["rolling_sharpe"].median()),
                    "rolling_sharpe_p25": float(group["rolling_sharpe"].quantile(0.25)),
                    "rolling_sharpe_p75": float(group["rolling_sharpe"].quantile(0.75)),
                    "rolling_mdd_mean": float(group["rolling_mdd"].mean()),
                    "rolling_mdd_p75": float(group["rolling_mdd"].quantile(0.75)),
                    "worst_rolling_mdd": float(group["rolling_mdd"].max()),
                    "positive_rolling_cagr_rate": float((group["rolling_cagr"] > 0).mean()),
                    "positive_rolling_sharpe_rate": float((group["rolling_sharpe"] > 0).mean()),
                    "ranking_stability_score": float((group["rank_by_sharpe"] <= 2).mean()),
                }
            )
    return pd.DataFrame(rows)
