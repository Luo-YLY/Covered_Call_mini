from __future__ import annotations

import pandas as pd

from src.metrics.ver2_metric_standard import compute_portfolio_option_contribution, summarize_daily_nav


def compute_performance_metrics(portfolio_returns: pd.DataFrame, portfolio_nav: pd.DataFrame) -> dict[str, object]:
    """Compute ver2-standard metrics for one portfolio path."""

    metrics = summarize_daily_nav(portfolio_nav[["date", "nav"]], date_col="date", nav_col="nav", rf=0.0)
    option_contribution = compute_portfolio_option_contribution(
        portfolio_returns["portfolio_option_leg_return"],
        n_days=len(portfolio_returns),
    )
    return {
        **metrics,
        "n_obs": int(len(portfolio_nav)),
        "final_nav": float(portfolio_nav["nav"].iloc[-1]),
        "option_leg_annualized_pnl_contribution": option_contribution,
    }
