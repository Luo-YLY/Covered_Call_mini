from __future__ import annotations

import pandas as pd

from src.metrics.ver2_metric_standard import compute_portfolio_option_contribution, summarize_daily_nav


def compute_performance_metrics(portfolio_returns: pd.DataFrame, portfolio_nav: pd.DataFrame) -> pd.DataFrame:
    """Compute ver2-standard portfolio metrics plus option-leg contribution."""

    rows: list[dict[str, object]] = []
    returns_lookup = {name: g.sort_values("date") for name, g in portfolio_returns.groupby("portfolio_name")}
    for portfolio_name, nav_g in portfolio_nav.groupby("portfolio_name", sort=False):
        nav_g = nav_g.sort_values("date").copy()
        ret_g = returns_lookup[portfolio_name]
        metrics = summarize_daily_nav(nav_g[["date", "nav"]], date_col="date", nav_col="nav", rf=0.0)
        option_contribution = compute_portfolio_option_contribution(
            ret_g["portfolio_option_leg_return"],
            n_days=len(ret_g),
        )
        rows.append(
            {
                "portfolio_name": portfolio_name,
                "universe_name": nav_g["universe_name"].iloc[0],
                "universe_short": nav_g["universe_short"].iloc[0],
                "portfolio_type": nav_g["portfolio_type"].iloc[0],
                "weight_scheme": nav_g["weight_scheme"].iloc[0],
                **metrics,
                "option_leg_annualized_pnl_contribution": option_contribution,
                "final_nav": float(nav_g["nav"].iloc[-1]),
                "initial_nav": float(nav_g["initial_nav"].iloc[0]),
            }
        )
    out = pd.DataFrame(rows)
    order = [
        "portfolio_name",
        "universe_name",
        "universe_short",
        "portfolio_type",
        "weight_scheme",
        "sample_start",
        "sample_end",
        "n_trading_days",
        "annualized_return_cagr",
        "sharpe_daily_mean",
        "annualized_volatility",
        "max_drawdown",
        "calmar_ratio",
        "sortino_ratio",
        "option_leg_annualized_pnl_contribution",
        "final_nav",
        "initial_nav",
    ]
    ordered = [col for col in order if col in out.columns]
    ordered += [col for col in out.columns if col not in ordered]
    return out[ordered].sort_values(["universe_short", "portfolio_type", "weight_scheme"]).reset_index(drop=True)
