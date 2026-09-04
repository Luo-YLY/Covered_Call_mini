from __future__ import annotations

from pathlib import Path

import pandas as pd


def write_markdown_report(
    path: Path,
    *,
    sample_summary: pd.DataFrame,
    candidate_weights: pd.DataFrame,
    full_summary: pd.DataFrame,
    baseline_comparison: pd.DataFrame,
    event_exclusion: pd.DataFrame,
    rolling_stability: pd.DataFrame,
    cost_summary: pd.DataFrame,
    weight_bound: pd.DataFrame,
    barbell: pd.DataFrame,
    scorecard: pd.DataFrame,
    recommended: pd.DataFrame,
    validation: pd.DataFrame,
) -> None:
    """Write the Step C Chinese markdown report."""

    primary = recommended.iloc[0] if not recommended.empty else {}
    report = f"""# ver3.0 Step C：稳健性与稳定性诊断

## 研究目的

Step C 不新增期权参数，也不做动态权重。它只围绕 Step B+ 选出的代表性前沿点，检查这些候选权重是否依赖少数事件窗口、是否对滚动子样本稳定、是否对更保守成本假设敏感，以及 default / relaxed 权重边界是否改变研究解释。

本报告是样本内稳健性诊断，不是样本外最优声明，也不是实盘承诺。

## 工程结构说明

- 当前 `ver3/` 是主项目入口。
- Step C 代码位于 `ver3/scripts/python/` 与 `ver3/src/covered_call_mini_ver3/stepC_robustness/`。
- 真实实验输出位于根目录 `outputs/ver3_0_stepC_robustness_stability_diagnostics/`。
- `ver3/outputs/` 只保留轻量索引。
- 旧 engine 和旧证据保留在 `ver2_downside_protection/`，本实验不修改。
- 指标口径依赖冻结的 `src/metrics/`，本实验只读调用。

## 候选组合定义

{_md_table(candidate_weights, pct_cols=["weight"])}

## 全样本表现

{_md_table(full_summary[[
        "portfolio_name",
        "role",
        "annualized_return_cagr",
        "sharpe_daily_mean",
        "annualized_volatility",
        "max_drawdown",
        "calmar_ratio",
        "sortino_ratio",
        "option_leg_annualized_pnl_contribution",
        "final_nav",
    ]], pct_cols=[
        "annualized_return_cagr",
        "annualized_volatility",
        "max_drawdown",
        "option_leg_annualized_pnl_contribution",
    ], num_cols=["sharpe_daily_mean", "calmar_ratio", "sortino_ratio", "final_nav"])}

样本窗口：

{_md_table(sample_summary)}

## 事件窗口剔除诊断

`exclude_all_extreme_event_metrics` 是同时剔除自动识别的极端上涨、极端下跌与手动事件窗口后的结果。重点观察 `delta_sharpe_vs_full_sample`、`delta_mdd_vs_full_sample` 和 `delta_cagr_vs_full_sample`。

{_md_table(event_exclusion[[
        "portfolio_name",
        "diagnostic_case",
        "removed_trading_days",
        "annualized_return_cagr",
        "sharpe_daily_mean",
        "max_drawdown",
        "delta_sharpe_vs_full_sample",
        "delta_mdd_vs_full_sample",
        "delta_cagr_vs_full_sample",
    ]], pct_cols=["annualized_return_cagr", "max_drawdown", "delta_mdd_vs_full_sample", "delta_cagr_vs_full_sample"], num_cols=["sharpe_daily_mean", "delta_sharpe_vs_full_sample"])}

## 滚动稳定性

滚动稳定性用于观察候选组合是否只在个别时间段表现突出。`ranking_stability_score` 表示在同一滚动窗口结束日中，候选组合 Sharpe 排名前二的比例。

{_md_table(rolling_stability, pct_cols=[
        "rolling_mdd_mean",
        "rolling_mdd_p75",
        "worst_rolling_mdd",
        "positive_rolling_cagr_rate",
        "positive_rolling_sharpe_rate",
        "ranking_stability_score",
    ], num_cols=["rolling_sharpe_mean", "rolling_sharpe_median", "rolling_sharpe_p25", "rolling_sharpe_p75"])}

## 成本敏感性

成本敏感性使用组合日度净期权腿收益施加年化 bps 成本拖累。该方法是透明近似，不伪造不存在的交易明细。

{_md_table(cost_summary[[
        "portfolio_name",
        "cost_scenario",
        "extra_cost_bps",
        "annualized_return_cagr",
        "sharpe_daily_mean",
        "max_drawdown",
        "option_leg_annualized_pnl_contribution",
        "delta_sharpe_vs_base",
        "delta_mdd_vs_base",
        "option_leg_still_positive",
        "interpretation_hint",
    ]], pct_cols=["annualized_return_cagr", "max_drawdown", "option_leg_annualized_pnl_contribution", "delta_mdd_vs_base"], num_cols=["sharpe_daily_mean", "delta_sharpe_vs_base"])}

## 权重边界敏感性

该诊断解释 Step B+ 中 default 与 relaxed 约束差异，重点看中间资产 510500 / 510050 是否被压到 0，以及前沿是否退化为 510300 + 159915 杠铃。

{_md_table(weight_bound, pct_cols=["D_star", "middle_asset_weight", "weight_510300", "weight_159915", "max_drawdown"], num_cols=["sharpe_daily_mean"])}

杠铃诊断：

{_md_table(barbell, pct_cols=[
        "D_star",
        "default_middle_asset_weight",
        "relaxed_middle_asset_weight",
        "middle_asset_weight_delta_relaxed_minus_default",
        "delta_mdd_relaxed_minus_default",
    ], num_cols=["delta_sharpe_relaxed_minus_default"])}

## 稳定性评分

稳定性评分是研究辅助，不是严格统计显著性检验。

{_md_table(scorecard, pct_cols=[
        "full_sample_mdd",
        "event_exclusion_sharpe_stability",
        "event_exclusion_mdd_stability",
        "rolling_sharpe_stability",
        "rolling_mdd_stability",
        "cost_sensitivity_score",
        "option_leg_robustness_score",
        "weight_interpretability_score",
        "overall_stability_score",
    ], num_cols=["full_sample_sharpe"])}

## 研究解释

- `B_default_D20` 是主线 defensive-income candidate 的优先观察对象：它比 D18 少牺牲一些收益弹性，又比 D22 更贴近 20% 回撤预算。
- `B_default_D18` 更适合作为 strict defensive candidate，而不是收益主线。
- `B_default_D22` 是更平衡的防御成长候选，如果滚动稳定性不弱，可以作为 D20 的平衡对照。
- `A_default_D25` 是 growth comparison candidate，用于保留 Universe A 的成长分散化解释，不应直接替代防御收益主线。
- 如果候选点相对固定权重基准提升有限，报告主线应保留固定权重基准作为高可解释对照。

固定权重基准对比：

{_md_table(baseline_comparison, pct_cols=["candidate_mdd", "baseline_mdd", "delta_mdd_vs_baseline", "candidate_cagr", "baseline_cagr", "delta_cagr_vs_baseline"], num_cols=["candidate_sharpe", "baseline_sharpe", "delta_sharpe_vs_baseline"])}

## 588000 说明

588000 仍然只属于 short-sample tech-growth extension，不纳入主线 Step C。这样可以保持 2022-09-30 至 2026-05-27 的共同长样本可比性。

## 结论

- 推荐主候选：`{primary.get("portfolio_name", "")}`，定位为 `{primary.get("recommendation_role", "")}`。
- 推荐对照候选：保留 `B_default_D22` 作为平衡对照，保留 `A_default_D25` 作为成长弹性对照。
- 当前结果支持形成研究看板中的候选组合族，但不应写成最终实盘答案。
- 如继续 Step D，应定位为可选的 dynamic weighting / covariance-learning layer；不应重新打开 DTE、delta、moneyness、TP 或 Touch-K 参数网格。

## 推荐表

{_md_table(recommended, pct_cols=["overall_stability_score", "full_sample_mdd"], num_cols=["full_sample_sharpe", "delta_sharpe_vs_context_baseline"])}

## 校验结果

{_md_table(_validation_for_report(validation))}
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report, encoding="utf-8")


def write_ver3_output_index(
    path: Path,
    *,
    output_root: Path,
    report_path: Path,
    summary_paths: dict[str, Path],
    run_timestamp: str,
    sample_text: str,
    recommended_candidate: str,
    stability_conclusion: str,
    next_stage: str,
) -> None:
    """Write a lightweight Step C output index under ver3/outputs."""

    lines = [
        "# ver3.0 Step C 输出索引",
        "",
        f"- 真实输出目录：`{output_root}`",
        f"- 中文报告：`{report_path}`",
        f"- 运行时间：{run_timestamp}",
        f"- 样本：{sample_text}",
        f"- 推荐主候选：`{recommended_candidate}`",
        f"- 稳健性结论：{stability_conclusion}",
        f"- 是否建议进入下一阶段：{next_stage}",
        "",
        "## 关键 summary 文件",
    ]
    for label, value in summary_paths.items():
        lines.append(f"- {label}: `{value}`")
    lines.append("")
    lines.append("本索引只做轻量导航；大型 CSV、PNG 和正式报告保留在根目录 `outputs/`。")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def _md_table(df: pd.DataFrame, pct_cols: list[str] | None = None, num_cols: list[str] | None = None) -> str:
    if df.empty:
        return "_empty_"
    out = df.copy()
    pct = set(pct_cols or [])
    num = set(num_cols or [])
    for col in out.columns:
        if col in pct:
            out[col] = out[col].map(_fmt_pct)
        elif col in num:
            out[col] = out[col].map(_fmt_num)
        else:
            out[col] = out[col].map(lambda x: "" if pd.isna(x) else str(x))
    return out.to_markdown(index=False)


def _validation_for_report(validation: pd.DataFrame) -> pd.DataFrame:
    if validation.empty:
        return validation
    out = validation.copy().rename(columns={"check_name": "检查项", "passed": "是否通过", "note": "说明"})
    if "是否通过" in out.columns:
        out["是否通过"] = out["是否通过"].map(lambda value: "通过" if bool(value) else "未通过")
    return out


def _fmt_pct(value: object) -> str:
    try:
        if pd.isna(value):
            return ""
        return f"{float(value):.2%}"
    except (TypeError, ValueError):
        return ""


def _fmt_num(value: object) -> str:
    try:
        if pd.isna(value):
            return ""
        return f"{float(value):.3f}"
    except (TypeError, ValueError):
        return ""
