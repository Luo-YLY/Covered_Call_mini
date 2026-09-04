from __future__ import annotations

import pandas as pd

from covered_call_mini_ver3.stepC_robustness.metrics import compute_metrics_from_returns, compute_single_path_metrics


def compute_dynamic_summary(daily_returns: pd.DataFrame) -> pd.DataFrame:
    """Compute frozen daily-NAV metrics for Step D dynamic strategies."""

    return compute_metrics_from_returns(
        daily_returns,
        group_cols=["strategy_name", "portfolio_name", "universe_short", "method", "lookback", "rebalance_frequency"],
    )


def compare_dynamic_to_static_baselines(
    dynamic_daily: pd.DataFrame,
    dynamic_summary: pd.DataFrame,
    static_daily: pd.DataFrame,
    baseline_config: pd.DataFrame,
) -> pd.DataFrame:
    """Compare every dynamic path with same-universe static baselines on the same effective sample."""

    rows: list[dict[str, object]] = []
    for _, dyn in dynamic_summary.iterrows():
        strategy = dyn["strategy_name"]
        dgroup = dynamic_daily[dynamic_daily["strategy_name"].eq(strategy)].sort_values("date")
        dates = pd.to_datetime(dgroup["date"])
        same_universe = baseline_config[baseline_config["universe_short"].eq(dyn["universe_short"])]
        for _, baseline in same_universe.iterrows():
            bgroup = static_daily[static_daily["portfolio_name"].eq(baseline["portfolio_name"])].copy()
            bgroup["date"] = pd.to_datetime(bgroup["date"])
            bgroup = bgroup[bgroup["date"].isin(set(dates))]
            if len(bgroup) != len(dgroup):
                continue
            bmetrics = compute_single_path_metrics(bgroup)
            rows.append(
                {
                    "strategy_name": strategy,
                    "universe_short": dyn["universe_short"],
                    "method": dyn["method"],
                    "lookback": int(dyn["lookback"]),
                    "rebalance_frequency": dyn["rebalance_frequency"],
                    "baseline_portfolio_name": baseline["portfolio_name"],
                    "baseline_source": baseline["baseline_source"],
                    "baseline_role": baseline["role"],
                    "sample_start": dates.min().date().isoformat(),
                    "sample_end": dates.max().date().isoformat(),
                    "n_trading_days": int(len(dgroup)),
                    "dynamic_sharpe": dyn["sharpe_daily_mean"],
                    "baseline_sharpe": bmetrics["sharpe_daily_mean"],
                    "delta_sharpe_vs_baseline": float(dyn["sharpe_daily_mean"]) - float(bmetrics["sharpe_daily_mean"]),
                    "dynamic_cagr": dyn["annualized_return_cagr"],
                    "baseline_cagr": bmetrics["annualized_return_cagr"],
                    "delta_cagr_vs_baseline": float(dyn["annualized_return_cagr"]) - float(bmetrics["annualized_return_cagr"]),
                    "dynamic_mdd": dyn["max_drawdown"],
                    "baseline_mdd": bmetrics["max_drawdown"],
                    "delta_mdd_vs_baseline": float(dyn["max_drawdown"]) - float(bmetrics["max_drawdown"]),
                    "dynamic_final_nav": dyn["final_nav"],
                    "baseline_final_nav": bmetrics["final_nav"],
                    "delta_final_nav_vs_baseline": float(dyn["final_nav"]) - float(bmetrics["final_nav"]),
                    "interpretation_hint": _comparison_hint(dyn, bmetrics),
                }
            )
    return pd.DataFrame(rows)


def compare_universe_A_vs_B(dynamic_summary: pd.DataFrame) -> pd.DataFrame:
    """Compare Universe A and B dynamic strategies method by method."""

    rows = []
    for (method, lookback), group in dynamic_summary.groupby(["method", "lookback"], sort=True):
        by_universe = {row["universe_short"]: row for _, row in group.iterrows()}
        if "A" not in by_universe or "B" not in by_universe:
            continue
        a = by_universe["A"]
        b = by_universe["B"]
        rows.append(
            {
                "method": method,
                "lookback": int(lookback),
                "A_strategy_name": a["strategy_name"],
                "B_strategy_name": b["strategy_name"],
                "A_sharpe": a["sharpe_daily_mean"],
                "B_sharpe": b["sharpe_daily_mean"],
                "delta_B_minus_A_sharpe": float(b["sharpe_daily_mean"]) - float(a["sharpe_daily_mean"]),
                "A_cagr": a["annualized_return_cagr"],
                "B_cagr": b["annualized_return_cagr"],
                "delta_B_minus_A_cagr": float(b["annualized_return_cagr"]) - float(a["annualized_return_cagr"]),
                "A_mdd": a["max_drawdown"],
                "B_mdd": b["max_drawdown"],
                "delta_B_minus_A_mdd": float(b["max_drawdown"]) - float(a["max_drawdown"]),
                "A_final_nav": a["final_nav"],
                "B_final_nav": b["final_nav"],
                "delta_B_minus_A_final_nav": float(b["final_nav"]) - float(a["final_nav"]),
            }
        )
    return pd.DataFrame(rows)


def build_static_baseline_config_table(baseline_specs: list[object]) -> pd.DataFrame:
    """Convert baseline dataclasses to a DataFrame."""

    return pd.DataFrame([item.__dict__ for item in baseline_specs])


def _comparison_hint(dynamic: pd.Series, baseline: dict[str, object]) -> str:
    sharpe_delta = float(dynamic["sharpe_daily_mean"]) - float(baseline["sharpe_daily_mean"])
    mdd_delta = float(dynamic["max_drawdown"]) - float(baseline["max_drawdown"])
    cagr_delta = float(dynamic["annualized_return_cagr"]) - float(baseline["annualized_return_cagr"])
    if sharpe_delta > 0 and mdd_delta <= 0:
        return "dynamic_improves_sharpe_without_higher_mdd"
    if sharpe_delta > 0 and cagr_delta > 0:
        return "dynamic_improves_sharpe_and_cagr_but_mdd_must_be_checked"
    if mdd_delta < 0:
        return "dynamic_reduces_mdd_but_return_tradeoff_must_be_checked"
    return "dynamic_not_clearly_better_than_static_baseline"
