from __future__ import annotations

import pandas as pd


def evaluate_weight_bound_sensitivity(default_frontier: pd.DataFrame, relaxed_frontier: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Evaluate default-vs-relaxed frontier sensitivity."""

    combined = pd.concat([default_frontier, relaxed_frontier], ignore_index=True, sort=False)
    rows = []
    for _, row in combined[combined["frontier_status"].eq("feasible")].iterrows():
        universe = str(row["universe_short"])
        middle_asset = "510500" if universe == "A" else "510050"
        middle_weight = float(row.get(f"weight_{middle_asset}", 0.0) or 0.0)
        w510300 = float(row.get("weight_510300", 0.0) or 0.0)
        w159915 = float(row.get("weight_159915", 0.0) or 0.0)
        barbell = middle_weight <= 1e-10 and w510300 > 0 and w159915 > 0
        rows.append(
            {
                "constraint_set": row["constraint_set"],
                "D_star": row["D_star"],
                "universe_short": universe,
                "portfolio_name": row["portfolio_name"],
                "middle_asset": middle_asset,
                "middle_asset_weight": middle_weight,
                "middle_asset_weight_is_zero": bool(middle_weight <= 1e-10),
                "barbell_flag": bool(barbell),
                "weight_510300": w510300,
                "weight_159915": w159915,
                "sharpe_daily_mean": row["sharpe_daily_mean"],
                "max_drawdown": row["max_drawdown"],
                "interpretation_hint": _middle_asset_hint(row["constraint_set"], middle_asset, middle_weight, barbell),
            }
        )
    detail = pd.DataFrame(rows)

    pair_rows = []
    for (universe, d_star), group in detail.groupby(["universe_short", "D_star"], sort=True):
        default = group[group["constraint_set"].eq("default")]
        relaxed = group[group["constraint_set"].eq("relaxed")]
        if default.empty or relaxed.empty:
            continue
        drow = default.iloc[0]
        rrow = relaxed.iloc[0]
        pair_rows.append(
            {
                "universe_short": universe,
                "D_star": d_star,
                "default_portfolio": drow["portfolio_name"],
                "relaxed_portfolio": rrow["portfolio_name"],
                "middle_asset": drow["middle_asset"],
                "default_middle_asset_weight": drow["middle_asset_weight"],
                "relaxed_middle_asset_weight": rrow["middle_asset_weight"],
                "middle_asset_weight_delta_relaxed_minus_default": rrow["middle_asset_weight"] - drow["middle_asset_weight"],
                "default_barbell_flag": drow["barbell_flag"],
                "relaxed_barbell_flag": rrow["barbell_flag"],
                "delta_sharpe_relaxed_minus_default": rrow["sharpe_daily_mean"] - drow["sharpe_daily_mean"],
                "delta_mdd_relaxed_minus_default": rrow["max_drawdown"] - drow["max_drawdown"],
                "interpretation_hint": _pair_hint(drow, rrow),
            }
        )
    return detail, pd.DataFrame(pair_rows)


def _middle_asset_hint(constraint_set: str, middle_asset: str, middle_weight: float, barbell: bool) -> str:
    if barbell:
        return f"{constraint_set} 下 {middle_asset} 被压到 0，组合退化为 510300 + 159915 杠铃。"
    if middle_weight <= 0.02:
        return f"{constraint_set} 下 {middle_asset} 权重接近 0，经济解释需要谨慎。"
    return f"{constraint_set} 下 {middle_asset} 保留正权重，最小权重约束仍有解释价值。"


def _pair_hint(default: pd.Series, relaxed: pd.Series) -> str:
    if bool(relaxed["barbell_flag"]) and not bool(default["barbell_flag"]):
        return "relaxed 放开最小权重后，中间资产被压到 0，说明 default 最小权重有解释约束作用。"
    if abs(float(relaxed["middle_asset_weight"]) - float(default["middle_asset_weight"])) < 0.03:
        return "default 与 relaxed 的中间资产权重接近，边界敏感性较低。"
    return "default 与 relaxed 权重差异较明显，应在报告中单独解释。"
