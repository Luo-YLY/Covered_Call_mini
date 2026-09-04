from __future__ import annotations

import pandas as pd

from .config import CostScenario
from .metrics import compute_metrics_from_returns


TRADING_DAYS = 252.0


def evaluate_cost_sensitivity(candidate_returns: pd.DataFrame, scenarios: list[CostScenario]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Apply transparent option-leg cost stress to candidate returns."""

    frames = []
    for scenario in scenarios:
        data = candidate_returns.copy()
        daily_drag = scenario.extra_cost_bps / 10000.0 / TRADING_DAYS
        data["portfolio_daily_return"] = data["portfolio_daily_return"].astype(float) - daily_drag
        data["portfolio_option_leg_return"] = data["portfolio_option_leg_return"].astype(float) - daily_drag
        data["cost_scenario"] = scenario.cost_scenario
        data["extra_cost_bps"] = scenario.extra_cost_bps
        data["cost_model"] = "组合日度净期权腿收益施加年化 bps 成本拖累"
        data["approximation_note"] = "已有组合日度 option-leg return；未伪造更细交易明细。"
        frames.append(data)

    stressed = pd.concat(frames, ignore_index=True, sort=False)
    summary = compute_metrics_from_returns(stressed, group_cols=["portfolio_name", "cost_scenario", "extra_cost_bps", "cost_model", "approximation_note"])
    base = summary[summary["cost_scenario"].eq("base")].set_index("portfolio_name")
    rows = []
    for _, row in summary.iterrows():
        base_row = base.loc[row["portfolio_name"]]
        rows.append(
            {
                **row.to_dict(),
                "delta_cagr_vs_base": float(row["annualized_return_cagr"]) - float(base_row["annualized_return_cagr"]),
                "delta_sharpe_vs_base": float(row["sharpe_daily_mean"]) - float(base_row["sharpe_daily_mean"]),
                "delta_mdd_vs_base": float(row["max_drawdown"]) - float(base_row["max_drawdown"]),
                "option_leg_still_positive": bool(float(row["option_leg_annualized_pnl_contribution"]) > 0),
                "interpretation_hint": _cost_hint(row, base_row),
            }
        )
    out = pd.DataFrame(rows)
    robustness = (
        out.groupby("portfolio_name", as_index=False)
        .agg(
            min_option_leg_contribution=("option_leg_annualized_pnl_contribution", "min"),
            option_leg_positive_rate=("option_leg_still_positive", "mean"),
            worst_delta_sharpe_vs_base=("delta_sharpe_vs_base", "min"),
            worst_delta_cagr_vs_base=("delta_cagr_vs_base", "min"),
            worst_delta_mdd_vs_base=("delta_mdd_vs_base", "max"),
        )
    )
    robustness["cost_robustness_label"] = robustness.apply(_robustness_label, axis=1)
    return out, robustness


def _cost_hint(row: pd.Series, base_row: pd.Series) -> str:
    if row["cost_scenario"] == "base":
        return "基础成本口径。"
    if row["option_leg_annualized_pnl_contribution"] > 0 and row["sharpe_daily_mean"] >= base_row["sharpe_daily_mean"] - 0.05:
        return "额外成本下期权腿仍为正，Sharpe 变化较小。"
    if row["option_leg_annualized_pnl_contribution"] > 0:
        return "额外成本下期权腿仍为正，但 Sharpe 有一定回落。"
    return "额外成本下期权腿转弱，需要谨慎解释。"


def _robustness_label(row: pd.Series) -> str:
    if row["option_leg_positive_rate"] >= 1.0 and row["worst_delta_sharpe_vs_base"] > -0.08:
        return "成本稳健性较高"
    if row["option_leg_positive_rate"] >= 0.8:
        return "成本稳健性中等"
    return "成本稳健性偏弱"
