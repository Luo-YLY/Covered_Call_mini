from __future__ import annotations

from pathlib import Path

import pandas as pd


def write_markdown_report(
    path: Path,
    *,
    config_summary: dict[str, object],
    sample_window: pd.DataFrame,
    frontier_default: pd.DataFrame,
    frontier_relaxed: pd.DataFrame,
    best_weights: pd.DataFrame,
    baseline_comparison: pd.DataFrame,
    universe_comparison: pd.DataFrame,
    option_attribution: pd.DataFrame,
    risk_contribution: pd.DataFrame,
    validation: pd.DataFrame,
) -> None:
    """Write a reader-facing Step B+ report in Chinese."""

    best = _best_frontier_row(pd.concat([frontier_default, frontier_relaxed], ignore_index=True, sort=False))
    report = f"""# ver3.0 Step B+：最大回撤约束 Sharpe 前沿

## 工程结构说明

Step B+ 的入口脚本放在 `ver3/scripts/python`，模块化源码放在 `ver3/src/covered_call_mini_ver3/stepB_plus`。真实实验输出写入仓库根目录的 `outputs/{config_summary["experiment_id"]}`；`ver3/outputs` 只保留轻量索引，方便人工导航，不存放大 CSV、PNG 或 daily 明细。

## 输入与样本

{_md_table(sample_window)}

## 组合池定义

- Universe A：510300 使用 D40 Q70 Hold，510500 使用 ETF BuyHold，159915 使用 OTM5up Q50 Hold。
- Universe B：510300 使用 D40 Q70 Hold，510050 使用 D40 Q70 Hold，159915 使用 OTM5up Q50 Hold。
- 588000 不进入主前沿。它目前是短样本 extension，混入主线会拉短共同样本，影响 A/B 比较的可读性。

## 方法口径

Step B+ 对每个 universe 和约束组枚举静态 long-only 权重网格。每个权重向量的组合日收益为：

`R_p,t = sum_i w_i * r_i,t`

随后用组合日收益累乘生成 NAV。目标是在 `max_drawdown <= D_star` 的约束下最大化 `sharpe_daily_mean`。指标口径沿用当前冻结的 daily-NAV 标准口径。

这一步是样本内研究前沿，不是样本外结论，也不是实盘交易承诺。

## 约束设置

- 回撤目标：`{config_summary["d_star_list"]}`
- default 权重边界：`0.05 <= w_i <= 0.70`
- relaxed 权重边界：`0.00 <= w_i <= 0.80`
- 网格步长：`{config_summary["grid_step"]}`

## 前沿汇总

default 约束：

{_md_table(frontier_default, pct_cols=["D_star", "max_drawdown", "annualized_return_cagr", "annualized_volatility"], num_cols=["sharpe_daily_mean", "calmar_ratio", "sortino_ratio", "final_nav"])}

relaxed 约束：

{_md_table(frontier_relaxed, pct_cols=["D_star", "max_drawdown", "annualized_return_cagr", "annualized_volatility"], num_cols=["sharpe_daily_mean", "calmar_ratio", "sortino_ratio", "final_nav"])}

## Universe A 与 Universe B 对比

{_md_table(universe_comparison, pct_cols=["D_star", "delta_cagr_B_minus_A", "delta_mdd_B_minus_A"], num_cols=["delta_sharpe_B_minus_A"])}

## 与固定权重基准对比

固定权重基准来自已完成的 Step B selected portfolios：50/30/20、70/20/10、40/40/20。`delta_mdd_vs_fixed_baseline < 0` 表示前沿点的最大回撤低于匹配的固定权重基准。

{_md_table(baseline_comparison, pct_cols=["D_star", "max_drawdown", "annualized_return_cagr", "delta_cagr_vs_fixed_baseline", "delta_mdd_vs_fixed_baseline"], num_cols=["sharpe_daily_mean", "delta_sharpe_vs_fixed_baseline"])}

## 期权腿归因

{_md_table(option_attribution[option_attribution["sleeve_key"].eq("PORTFOLIO_TOTAL")], pct_cols=["D_star", "weight", "option_leg_annualized_pnl_contribution"])}

## 风险诊断

风险贡献表只用于解释已选前沿点的波动来源，不作为动态调仓规则。

{_md_table(risk_contribution, pct_cols=["D_star", "weight", "portfolio_volatility", "risk_contribution_pct"], num_cols=["risk_contribution_to_variance"])}

## 结果解读

- 本轮网格中 Sharpe 最高的可行点是 `{best.get("portfolio_name", "")}`，Sharpe 为 {_fmt_num(best.get("sharpe_daily_mean"))}，MDD 为 {_fmt_pct(best.get("max_drawdown"))}，CAGR 为 {_fmt_pct(best.get("annualized_return_cagr"))}。
- 当目标更偏低回撤时，Universe B 更值得优先观察；当可以接受更多中盘成长暴露时，Universe A 仍是重要的成长分散化对照线。
- relaxed 约束用于观察结果是否依赖集中权重。如果 relaxed 与 default 的前沿点高度接近，说明结论对最小权重边界不太敏感。

## 588000 说明

588000 继续排除在主 Step B+ 前沿之外。后续可以单独做短样本 extension，但不应混入当前长样本 A/B 主线，否则样本定义会被改变。

## 结论

Step B+ 把 Step B 的固定权重比较推进为“回撤约束下的静态权重前沿”。它适合用来挑选下一步稳健性检验的候选权重族，而不是直接给出最终配置。

Step C 建议围绕候选前沿点做事件窗口剔除、滚动窗口和成本敏感性检验，再判断它是否足够稳健。

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
    sample_text: str,
    conclusion_text: str,
) -> None:
    """Write a lightweight Chinese index inside ver3/outputs."""

    lines = [
        "# ver3.0 Step B+ 输出索引",
        "",
        f"- 真实输出目录：`{output_root}`",
        f"- 中文报告：`{report_path}`",
        f"- 样本：{sample_text}",
        f"- 快速结论：{conclusion_text}",
        "",
        "## 关键文件",
    ]
    for label, path_item in summary_paths.items():
        lines.append(f"- {label}: `{path_item}`")
    lines.append("")
    lines.append("本文件只做轻量导航；CSV、PNG 和正式报告仍保留在根目录 `outputs/`。")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def _best_frontier_row(df: pd.DataFrame) -> dict[str, object]:
    feasible = df[df.get("feasible", False).astype(bool)].copy() if "feasible" in df else pd.DataFrame()
    if feasible.empty:
        return {}
    return feasible.sort_values(["sharpe_daily_mean", "max_drawdown"], ascending=[False, True]).iloc[0].to_dict()


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
    out = validation.copy()
    out = out.rename(columns={"check_name": "检查项", "passed": "是否通过", "note": "说明"})
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
