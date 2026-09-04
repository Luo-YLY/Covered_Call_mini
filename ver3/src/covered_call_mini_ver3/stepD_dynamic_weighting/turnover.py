from __future__ import annotations

import pandas as pd

from .config import TURNOVER_METHOD, UniverseSpec
from .metrics import compute_metrics_from_returns


def compute_rebalance_turnover(rebalance_weights: pd.DataFrame, universes: dict[str, UniverseSpec]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Compute target-weight-change turnover on rebalance dates."""

    rows: list[dict[str, object]] = []
    for strategy, group in rebalance_weights.groupby("strategy_name", sort=False):
        meta = group.iloc[0]
        universe = universes[str(meta["universe_short"])]
        wide = (
            group.pivot_table(index="effective_date", columns="etf_code", values="target_weight", aggfunc="last")
            .sort_index()
            .reindex(columns=list(universe.etf_codes))
        )
        previous = pd.Series(universe.anchor_weights, dtype=float).reindex(universe.etf_codes)
        signal_dates = group.drop_duplicates("effective_date").set_index("effective_date")["signal_date"].sort_index()
        for effective_date, new in wide.iterrows():
            turnover = 0.5 * (new.astype(float) - previous.astype(float)).abs().sum()
            row = {
                "strategy_name": strategy,
                "universe_short": meta["universe_short"],
                "method": meta["method"],
                "lookback": int(meta["lookback"]),
                "rebalance_frequency": "monthly",
                "signal_date": pd.Timestamp(signal_dates.loc[effective_date]),
                "effective_date": pd.Timestamp(effective_date),
                "turnover": float(turnover),
                "turnover_method": TURNOVER_METHOD,
            }
            for etf in universe.etf_codes:
                row[f"previous_target_weight_{etf}"] = float(previous.loc[etf])
                row[f"new_target_weight_{etf}"] = float(new.loc[etf])
            rows.append(row)
            previous = new.astype(float)

    detail = pd.DataFrame(rows)
    summary = (
        detail.groupby(["strategy_name", "universe_short", "method", "lookback"], as_index=False)
        .agg(
            rebalance_count=("effective_date", "count"),
            total_turnover=("turnover", "sum"),
            avg_rebalance_turnover=("turnover", "mean"),
            max_rebalance_turnover=("turnover", "max"),
            first_rebalance_date=("effective_date", "min"),
            last_rebalance_date=("effective_date", "max"),
        )
        .sort_values(["universe_short", "method", "lookback"])
    )
    years = (
        (pd.to_datetime(summary["last_rebalance_date"]) - pd.to_datetime(summary["first_rebalance_date"])).dt.days.clip(lower=1)
        / 365.25
    )
    summary["annualized_turnover_approx"] = summary["total_turnover"].astype(float) / years
    summary["turnover_method"] = TURNOVER_METHOD
    return detail, summary


def evaluate_rebalance_cost_sensitivity(
    daily_returns: pd.DataFrame,
    turnover_detail: pd.DataFrame,
    cost_bps_values: list[float],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Apply rebalance costs to turnover dates and compute metrics."""

    frames = []
    turnover_map = turnover_detail[["strategy_name", "effective_date", "turnover"]].copy()
    turnover_map["effective_date"] = pd.to_datetime(turnover_map["effective_date"])
    for cost_bps in cost_bps_values:
        cost_rate = float(cost_bps) / 10000.0
        for strategy, group in daily_returns.groupby("strategy_name", sort=False):
            g = group.sort_values("date").copy()
            g["date"] = pd.to_datetime(g["date"])
            turns = turnover_map[turnover_map["strategy_name"].eq(strategy)].rename(columns={"effective_date": "date"})
            g = g.merge(turns[["date", "turnover"]], on="date", how="left")
            g["turnover"] = g["turnover"].fillna(0.0)
            g["rebalance_cost_bps"] = float(cost_bps)
            g["rebalance_cost_rate"] = cost_rate
            g["rebalance_cost_return_drag"] = g["turnover"].astype(float) * cost_rate
            g["portfolio_daily_return_gross"] = g["portfolio_daily_return"].astype(float)
            g["portfolio_daily_return"] = g["portfolio_daily_return_gross"] - g["rebalance_cost_return_drag"]
            g["cost_scenario"] = "no_rebalance_cost" if abs(cost_bps) < 1e-12 else f"rebalance_cost_{int(cost_bps)}bps"
            frames.append(g)
    cost_daily = pd.concat(frames, ignore_index=True, sort=False)
    cost_summary = compute_metrics_from_returns(
        cost_daily,
        group_cols=[
            "strategy_name",
            "portfolio_name",
            "universe_short",
            "method",
            "lookback",
            "rebalance_frequency",
            "cost_scenario",
            "rebalance_cost_bps",
        ],
    )
    base = cost_summary[cost_summary["rebalance_cost_bps"].astype(float).eq(0.0)][
        ["strategy_name", "sharpe_daily_mean", "annualized_return_cagr", "max_drawdown", "final_nav"]
    ].rename(
        columns={
            "sharpe_daily_mean": "base_sharpe",
            "annualized_return_cagr": "base_cagr",
            "max_drawdown": "base_mdd",
            "final_nav": "base_final_nav",
        }
    )
    cost_summary = cost_summary.merge(base, on="strategy_name", how="left")
    cost_summary["delta_sharpe_vs_no_cost"] = cost_summary["sharpe_daily_mean"].astype(float) - cost_summary["base_sharpe"].astype(float)
    cost_summary["delta_cagr_vs_no_cost"] = cost_summary["annualized_return_cagr"].astype(float) - cost_summary["base_cagr"].astype(float)
    cost_summary["delta_mdd_vs_no_cost"] = cost_summary["max_drawdown"].astype(float) - cost_summary["base_mdd"].astype(float)
    cost_summary["delta_final_nav_vs_no_cost"] = cost_summary["final_nav"].astype(float) - cost_summary["base_final_nav"].astype(float)
    cost_summary["turnover_method"] = TURNOVER_METHOD
    return cost_daily, cost_summary
