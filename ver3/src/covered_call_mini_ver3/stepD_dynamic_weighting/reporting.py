from __future__ import annotations

from pathlib import Path

import pandas as pd


def write_markdown_report(
    path: Path,
    *,
    sample_summary: pd.DataFrame,
    universe_config: pd.DataFrame,
    method_config: pd.DataFrame,
    dynamic_summary: pd.DataFrame,
    static_comparison: pd.DataFrame,
    universe_comparison: pd.DataFrame,
    turnover_summary: pd.DataFrame,
    cost_summary: pd.DataFrame,
    recommendation: pd.DataFrame,
    option_attribution: pd.DataFrame,
    risk_contribution: pd.DataFrame,
    validation: pd.DataFrame,
) -> None:
    """Write the Step D Chinese markdown report."""

    top = recommendation.iloc[0] if not recommendation.empty else {}
    report = f"""# ver3.0 Step D：波动率控制的动态 sleeve 权重

## 研究定位

Step D 只研究组合层面的动态资金权重 `w_i,t`。底层 sleeve 已经由 Step A / Step B / Step C 固定，本步骤不新增 DTE、delta、moneyness、TP、Touch-K 参数，不动态调整 q，不用波动率决定是否卖出 call，也不做收益预测或带预期收益的 Markowitz 优化。

本步骤的核心问题是：在固定 sleeve 之上，如果只根据历史波动率或协方差对 sleeve 之间的资金权重做月度调整，是否能在回撤、Sharpe、收益弹性和换手成本之间提供有解释力的改善。

## 样本与 universe

动态权重的原始长样本仍从 2022-09-30 到 2026-05-27，但有效样本会从 lookback 之后的下一次月度再平衡开始，因此 126 日与 252 日曲线的起点不同。所有指标均按每条净值曲线自己的有效样本计算；静态基准比较也按同一有效日期重新截样本。

{_md_table(sample_summary)}

{_md_table(universe_config, pct_cols=["anchor_weight"])}

## 方法设置

{_md_table(method_config)}

三种方法的共同约束是：月度再平衡、信号日只使用当日及以前数据、下一交易日生效、权重区间 5% 到 70%、long-only、权重和为 1。

## 动态策略全样本结果

{_md_table(dynamic_summary[[
        "strategy_name",
        "universe_short",
        "method",
        "lookback",
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
    ]], pct_cols=[
        "annualized_return_cagr",
        "annualized_volatility",
        "max_drawdown",
        "option_leg_annualized_pnl_contribution",
    ], num_cols=["sharpe_daily_mean", "calmar_ratio", "sortino_ratio", "final_nav"])}

## 与静态基准比较

下表中的静态基准均按对应动态策略的有效日期重新截样本，因此它回答的是“在同一段动态可用样本内，动态权重相对静态权重是否改善”。

{_md_table(static_comparison[[
        "strategy_name",
        "baseline_portfolio_name",
        "sample_start",
        "sample_end",
        "dynamic_sharpe",
        "baseline_sharpe",
        "delta_sharpe_vs_baseline",
        "dynamic_cagr",
        "baseline_cagr",
        "delta_cagr_vs_baseline",
        "dynamic_mdd",
        "baseline_mdd",
        "delta_mdd_vs_baseline",
        "interpretation_hint",
    ]], pct_cols=["dynamic_cagr", "baseline_cagr", "delta_cagr_vs_baseline", "dynamic_mdd", "baseline_mdd", "delta_mdd_vs_baseline"], num_cols=["dynamic_sharpe", "baseline_sharpe", "delta_sharpe_vs_baseline"])}

## Universe A/B 动态比较

{_md_table(universe_comparison, pct_cols=["A_cagr", "B_cagr", "delta_B_minus_A_cagr", "A_mdd", "B_mdd", "delta_B_minus_A_mdd"], num_cols=["A_sharpe", "B_sharpe", "delta_B_minus_A_sharpe", "A_final_nav", "B_final_nav"])}

## 换手与再平衡成本

换手使用 `0.5 * sum(abs(w_new - w_previous_target))` 的目标权重变化近似。第一次再平衡以前一阶段 anchor weight 作为 previous target。成本情景为 0、5、10、20 bps，并只在再平衡生效日按 `turnover * cost_rate` 扣减。

{_md_table(turnover_summary, pct_cols=["total_turnover", "avg_rebalance_turnover", "max_rebalance_turnover", "annualized_turnover_approx"])}

{_md_table(cost_summary[[
        "strategy_name",
        "cost_scenario",
        "rebalance_cost_bps",
        "annualized_return_cagr",
        "sharpe_daily_mean",
        "max_drawdown",
        "delta_sharpe_vs_no_cost",
        "delta_cagr_vs_no_cost",
        "delta_mdd_vs_no_cost",
        "final_nav",
    ]], pct_cols=["annualized_return_cagr", "max_drawdown", "delta_cagr_vs_no_cost", "delta_mdd_vs_no_cost"], num_cols=["sharpe_daily_mean", "delta_sharpe_vs_no_cost", "final_nav"])}

## Attribution

期权腿贡献来自 Step A daily_nav 中的 `daily_return_option_leg_component`，再按动态权重加总；风险贡献是使用有效样本内平均动态权重和资产协方差矩阵做的 ex-post 方差贡献近似。

{_md_table(option_attribution, pct_cols=["option_leg_cumulative_simple_return", "portfolio_cumulative_simple_return", "option_leg_annualized_pnl_contribution", "avg_daily_option_leg_return", "option_leg_positive_day_rate"])}

{_md_table(risk_contribution, pct_cols=["avg_target_weight", "asset_vol_annualized", "risk_contribution_to_variance"])}

## 推荐观察表

当前推荐表只用于研究排序，不代表动态权重一定优于静态基准。若动态结果相对静态基准没有稳定提升，应保留静态基准作为主解释线。

当前排序第一：`{top.get("strategy_name", "")}`。

{_md_table(recommendation, pct_cols=["annualized_return_cagr", "max_drawdown", "avg_rebalance_turnover", "delta_cagr_vs_matched_baseline", "delta_mdd_vs_matched_baseline"], num_cols=["sharpe_daily_mean", "delta_sharpe_vs_matched_baseline", "recommendation_score"])}

## 研究结论

- Step D 提供的是可选的 covariance-learning / volatility-control layer，而不是重新打开期权参数网格。
- anchored inverse volatility 更接近原有研究主线，因为它保留了 Step B/C 的 anchor 解释。
- pure inverse volatility 和 rolling minimum variance 更像压力测试：如果它们显著偏离 anchor 且换手较高，需要更谨慎解释。
- 若扣除再平衡成本后 Sharpe 或回撤优势消失，应优先保留 Step C 静态候选。

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
    run_timestamp: str,
    recommendation: pd.DataFrame,
    validation: pd.DataFrame,
    key_paths: dict[str, Path],
) -> None:
    """Write a lightweight Step D output index under ver3/outputs."""

    top = recommendation.iloc[0]["strategy_name"] if not recommendation.empty else ""
    lines = [
        "# ver3.0 Step D 输出索引",
        "",
        f"- 真实输出目录：`{output_root}`",
        f"- 中文报告：`{report_path}`",
        f"- 运行时间：{run_timestamp}",
        f"- 当前研究排序第一：`{top}`",
        f"- validation：{int(validation['passed'].sum())}/{len(validation)} passed",
        "",
        "## 关键文件",
    ]
    for label, value in key_paths.items():
        lines.append(f"- {label}: `{value}`")
    lines.extend(
        [
            "",
            "说明：`ver3/outputs/` 只保留轻量索引；大型 CSV、PNG 和正式报告均保留在根目录 `outputs/`。",
        ]
    )
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
