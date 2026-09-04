from __future__ import annotations

import numpy as np
import pandas as pd


def build_stability_scorecard(
    full_summary: pd.DataFrame,
    event_exclusion: pd.DataFrame,
    rolling_stability: pd.DataFrame,
    cost_robustness: pd.DataFrame,
    weight_bound: pd.DataFrame,
) -> pd.DataFrame:
    """Build a research-assist stability scorecard."""

    event_all = event_exclusion[event_exclusion["diagnostic_case"].eq("exclude_all_extreme_event_metrics")].set_index("portfolio_name")
    rolling_252 = rolling_stability[rolling_stability["window_days"].eq(252)].set_index("portfolio_name")
    cost = cost_robustness.set_index("portfolio_name")
    rows = []
    for _, row in full_summary.iterrows():
        name = row["portfolio_name"]
        event_row = event_all.loc[name] if name in event_all.index else pd.Series(dtype=float)
        rolling_row = rolling_252.loc[name] if name in rolling_252.index else pd.Series(dtype=float)
        cost_row = cost.loc[name] if name in cost.index else pd.Series(dtype=float)
        event_sharpe_score = _bounded(1.0 - abs(float(event_row.get("delta_sharpe_vs_full_sample", 0.0))) / max(abs(float(row["sharpe_daily_mean"])), 0.2))
        event_mdd_score = _bounded(1.0 - abs(float(event_row.get("delta_mdd_vs_full_sample", 0.0))) / max(float(row["max_drawdown"]), 0.05))
        rolling_sharpe_score = _bounded(float(rolling_row.get("positive_rolling_sharpe_rate", 0.0)))
        full_mdd = max(float(row["max_drawdown"]), 0.05)
        worst_rolling_mdd = float(rolling_row.get("worst_rolling_mdd", full_mdd * 1.5))
        rolling_mdd_score = _bounded(1.0 - max(0.0, worst_rolling_mdd / full_mdd - 1.0) / 0.75)
        cost_score = _bounded(1.0 + float(cost_row.get("worst_delta_sharpe_vs_base", -0.5)) / max(abs(float(row["sharpe_daily_mean"])), 0.2))
        option_score = _bounded(float(cost_row.get("option_leg_positive_rate", 0.0)))
        weight_score = _weight_interpretability_score(name, weight_bound)
        overall = float(np.nanmean([event_sharpe_score, event_mdd_score, rolling_sharpe_score, rolling_mdd_score, cost_score, option_score, weight_score]))
        rows.append(
            {
                "portfolio_name": name,
                "role": row.get("role", ""),
                "full_sample_sharpe": row["sharpe_daily_mean"],
                "full_sample_mdd": row["max_drawdown"],
                "event_exclusion_sharpe_stability": event_sharpe_score,
                "event_exclusion_mdd_stability": event_mdd_score,
                "rolling_sharpe_stability": rolling_sharpe_score,
                "rolling_mdd_stability": rolling_mdd_score,
                "cost_sensitivity_score": cost_score,
                "option_leg_robustness_score": option_score,
                "weight_interpretability_score": weight_score,
                "overall_stability_score": overall,
                "overall_stability_label": _label(overall),
            }
        )
    return pd.DataFrame(rows).sort_values(["overall_stability_score", "full_sample_sharpe"], ascending=[False, False]).reset_index(drop=True)


def build_recommended_candidate_table(scorecard: pd.DataFrame, baseline_comparison: pd.DataFrame) -> pd.DataFrame:
    """Build recommended candidate and comparison table."""

    rows = []
    lookup = scorecard.set_index("portfolio_name")
    primary_name = "B_default_D20" if "B_default_D20" in lookup.index else scorecard.iloc[0]["portfolio_name"]
    balanced_name = "B_default_D22" if "B_default_D22" in lookup.index else scorecard.iloc[0]["portfolio_name"]
    comparison_name = "A_default_D25" if "A_default_D25" in lookup.index else scorecard.iloc[-1]["portfolio_name"]
    strict_name = "B_default_D18" if "B_default_D18" in lookup.index else scorecard.iloc[-1]["portfolio_name"]
    recommendations = [
        (primary_name, "主线 defensive-income candidate", "优先作为报告主线候选，后续只做稳健性解释和看板展示。"),
        (balanced_name, "平衡候选", "用于检验是否值得接受更高回撤换取更好收益弹性。"),
        (strict_name, "严格防御候选", "用于低回撤约束场景，不直接追求收益最大化。"),
        (comparison_name, "成长弹性对照", "用于保留 Universe A 的成长分散化对照线。"),
    ]
    seen: set[str] = set()
    for name, rec_role, reason in recommendations:
        if name not in lookup.index or name in seen:
            continue
        seen.add(name)
        row = lookup.loc[name]
        same = baseline_comparison[baseline_comparison["portfolio_name"].eq(name)]
        best_delta = same.sort_values("delta_sharpe_vs_baseline", ascending=False).iloc[0] if not same.empty else None
        rows.append(
            {
                "portfolio_name": name,
                "recommendation_role": rec_role,
                "overall_stability_label": row["overall_stability_label"],
                "overall_stability_score": row["overall_stability_score"],
                "full_sample_sharpe": row["full_sample_sharpe"],
                "full_sample_mdd": row["full_sample_mdd"],
                "matched_baseline_for_context": best_delta["baseline_portfolio_name"] if best_delta is not None else "",
                "delta_sharpe_vs_context_baseline": best_delta["delta_sharpe_vs_baseline"] if best_delta is not None else np.nan,
                "reason": reason,
                "next_stage_suggestion": "可进入 Step D 可选动态权重研究" if row["overall_stability_label"] in {"High Stability", "Medium Stability"} else "先完善风险解释，不建议急于动态化",
            }
        )
    return pd.DataFrame(rows)


def _weight_interpretability_score(portfolio_name: str, weight_bound: pd.DataFrame) -> float:
    if "_v31_" in str(portfolio_name):
        return 1.0
    source = {
        "B_default_D18": "B_default_D18_51030070_51005022_15991508",
        "B_default_D20": "B_default_D20_51030070_51005015_15991515",
        "B_default_D22": "B_default_D22_51030068_51005009_15991523",
        "A_default_D25": "A_default_D25_51030063_51050005_15991532",
    }.get(portfolio_name)
    if source is None:
        return 0.5
    row = weight_bound[weight_bound["portfolio_name"].eq(source)]
    if row.empty:
        return 0.5
    middle_weight = float(row.iloc[0]["middle_asset_weight"])
    if middle_weight >= 0.05:
        return 1.0
    if middle_weight > 0:
        return 0.7
    return 0.35


def _bounded(value: float) -> float:
    if pd.isna(value):
        return 0.0
    return float(min(max(value, 0.0), 1.0))


def _label(score: float) -> str:
    if score >= 0.75:
        return "High Stability"
    if score >= 0.55:
        return "Medium Stability"
    if score >= 0.35:
        return "Low Stability"
    return "Diagnostic Only"
