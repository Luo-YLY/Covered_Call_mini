from __future__ import annotations

import numpy as np
import pandas as pd

from src.metrics.ver2_metric_standard import compute_portfolio_option_contribution, summarize_daily_nav

from .config import INITIAL_NAV


METRIC_COLUMNS = [
    "sample_start",
    "sample_end",
    "n_trading_days",
    "annualized_return_cagr",
    "sharpe_daily_mean",
    "annualized_volatility",
    "max_drawdown",
    "calmar_ratio",
    "sortino_ratio",
    "final_nav",
    "option_leg_annualized_pnl_contribution",
]


def compute_metrics_from_returns(
    returns: pd.DataFrame,
    *,
    group_cols: list[str],
    return_col: str = "portfolio_daily_return",
    option_col: str = "portfolio_option_leg_return",
) -> pd.DataFrame:
    """Compute frozen daily-NAV metrics for grouped daily returns."""

    rows: list[dict[str, object]] = []
    for keys, group in returns.groupby(group_cols, dropna=False, sort=True):
        key_values = keys if isinstance(keys, tuple) else (keys,)
        meta = dict(zip(group_cols, key_values))
        metrics = compute_single_path_metrics(group, return_col=return_col, option_col=option_col)
        rows.append({**meta, **metrics})
    return pd.DataFrame(rows)


def compute_single_path_metrics(
    group: pd.DataFrame,
    *,
    return_col: str = "portfolio_daily_return",
    option_col: str = "portfolio_option_leg_return",
) -> dict[str, object]:
    """Compute metrics for one daily return path."""

    g = group.sort_values("date").copy()
    g["date"] = pd.to_datetime(g["date"])
    nav = (1.0 + g[return_col].astype(float)).cumprod() * INITIAL_NAV
    daily_nav = pd.DataFrame({"date": g["date"].values, "nav": nav.values})
    metrics = summarize_daily_nav(daily_nav, date_col="date", nav_col="nav", rf=0.0)
    option = (
        compute_portfolio_option_contribution(g[option_col].astype(float), n_days=len(g))
        if option_col in g.columns
        else np.nan
    )
    return {
        **metrics,
        "n_obs": int(len(g)),
        "final_nav": float(nav.iloc[-1]) if len(nav) else np.nan,
        "option_leg_annualized_pnl_contribution": option,
    }


def compare_candidates_to_baselines(candidate_summary: pd.DataFrame, baseline_summary: pd.DataFrame) -> pd.DataFrame:
    """Compare each candidate with same-universe Step B fixed baselines."""

    baselines = baseline_summary[baseline_summary["portfolio_type"].eq("Selected")].copy()
    rows: list[dict[str, object]] = []
    for _, candidate in candidate_summary.iterrows():
        same_universe = baselines[baselines["universe_short"].eq(candidate["universe_short"])]
        for _, baseline in same_universe.iterrows():
            rows.append(
                {
                    "portfolio_name": candidate["portfolio_name"],
                    "candidate_role": candidate.get("role", ""),
                    "universe_short": candidate["universe_short"],
                    "baseline_portfolio_name": baseline["portfolio_name"],
                    "baseline_weight_scheme": baseline["weight_scheme"],
                    "candidate_sharpe": candidate["sharpe_daily_mean"],
                    "baseline_sharpe": baseline["sharpe_daily_mean"],
                    "delta_sharpe_vs_baseline": float(candidate["sharpe_daily_mean"]) - float(baseline["sharpe_daily_mean"]),
                    "candidate_mdd": candidate["max_drawdown"],
                    "baseline_mdd": baseline["max_drawdown"],
                    "delta_mdd_vs_baseline": float(candidate["max_drawdown"]) - float(baseline["max_drawdown"]),
                    "candidate_cagr": candidate["annualized_return_cagr"],
                    "baseline_cagr": baseline["annualized_return_cagr"],
                    "delta_cagr_vs_baseline": float(candidate["annualized_return_cagr"]) - float(baseline["annualized_return_cagr"]),
                    "interpretation_hint": _baseline_hint(candidate, baseline),
                }
            )
    return pd.DataFrame(rows)


def _baseline_hint(candidate: pd.Series, baseline: pd.Series) -> str:
    sharpe_delta = float(candidate["sharpe_daily_mean"]) - float(baseline["sharpe_daily_mean"])
    mdd_delta = float(candidate["max_drawdown"]) - float(baseline["max_drawdown"])
    cagr_delta = float(candidate["annualized_return_cagr"]) - float(baseline["annualized_return_cagr"])
    if sharpe_delta > 0 and mdd_delta <= 0:
        return "候选组合相对固定权重基准提高 Sharpe 且未增加回撤。"
    if sharpe_delta > 0:
        return "候选组合提高 Sharpe，但回撤成本需要复核。"
    if mdd_delta < 0:
        return "候选组合降低回撤，但收益或 Sharpe 优势有限。"
    if cagr_delta > 0:
        return "候选组合提高 CAGR，但风险调整表现需要复核。"
    return "候选组合相对固定权重基准优势不明显。"
