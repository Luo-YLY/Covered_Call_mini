from __future__ import annotations

from pathlib import Path

import pandas as pd


def write_markdown_report(
    path: Path,
    summary: pd.DataFrame,
    selected_vs_pure: pd.DataFrame,
    universe_comparison: pd.DataFrame,
    option_contribution: pd.DataFrame,
    risk_contribution: pd.DataFrame,
    sample_window: pd.DataFrame,
    validation: pd.DataFrame,
    extension_588000_available: bool,
) -> None:
    """Write the Step B reader-facing report in Chinese."""

    selected = summary[summary["portfolio_type"].eq("Selected")].copy()
    best_sharpe = summary.sort_values("sharpe_daily_mean", ascending=False).iloc[0]
    lowest_mdd = summary.sort_values("max_drawdown", ascending=True).iloc[0]
    selected_option = option_contribution[
        option_contribution["sleeve_key"].ne("PORTFOLIO_TOTAL")
        & option_contribution["portfolio_type"].eq("Selected")
    ].copy()
    report = f"""# ver3.0 Step B：固定权重 Universe 组合比较

## 研究目标

本实验从 Step A 的单 ETF sleeve 诊断推进到固定权重组合层比较。它只使用已选定的 Step A sleeves，不重新跑期权参数网格，不做权重优化，也不把 588000 纳入长样本 Step B 主组合。

## 方法口径

对组合 p：

`R_p,t = sum_i w_i * r_i,t`

组合 NAV 从初始净值 1.0 开始，由每日组合收益累乘得到。这是研究层面的固定权重 sleeve 组合，不是账户级实盘交易模拟。期权腿归因沿用 Step A 的日度核算口径，使用加权后的净期权腿收益。

## 样本窗口

{_md_table(sample_window)}

## 组合汇总

{_md_table(summary[[
        "portfolio_name",
        "universe_short",
        "portfolio_type",
        "weight_scheme",
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

## Selected 与 Pure ETF 基准对比

`delta_mdd_vs_baseline < 0` 表示 selected 组合相对 pure ETF 基准降低了最大回撤。

{_md_table(selected_vs_pure, pct_cols=[
        "excess_cagr_vs_baseline",
        "delta_volatility_vs_baseline",
        "delta_mdd_vs_baseline",
        "delta_final_nav_vs_baseline",
        "option_leg_annualized_pnl_contribution",
    ], num_cols=["delta_sharpe_vs_baseline", "delta_calmar_vs_baseline", "delta_sortino_vs_baseline"])}

## Universe A 与 Universe B 对比

{_md_table(universe_comparison, pct_cols=[
        "delta_cagr",
        "delta_volatility",
        "delta_mdd",
    ], num_cols=["delta_sharpe", "delta_calmar", "delta_sortino"])}

## 期权腿归因

{_md_table(selected_option[[
        "portfolio_name",
        "etf_code",
        "sleeve_key",
        "weight",
        "option_leg_annualized_pnl_contribution",
        "attribution_method",
    ]], pct_cols=["weight", "option_leg_annualized_pnl_contribution"])}

## 风险诊断

风险贡献表只用于静态解释，不作为动态调仓规则。

{_md_table(risk_contribution[risk_contribution["portfolio_type"].eq("Selected")][[
        "portfolio_name",
        "etf_code",
        "sleeve_key",
        "weight",
        "portfolio_volatility",
        "risk_contribution_pct",
    ]], pct_cols=["weight", "portfolio_volatility", "risk_contribution_pct"])}

## 588000 说明

588000 被视为短样本科技成长 extension。当前是否有 588000 数据：`{extension_588000_available}`。它被有意排除在本次长样本固定权重 Step B 比较之外；如需包含 588000，应单独做 Step B-Extension。

## 结论

- Sharpe 最高组合：`{best_sharpe["portfolio_name"]}`，Sharpe 为 {float(best_sharpe["sharpe_daily_mean"]):.3f}。
- 最大回撤最低组合：`{lowest_mdd["portfolio_name"]}`，MDD 为 {_fmt_pct(lowest_mdd["max_drawdown"])}。
- 当 510500 的中盘成长分散化有价值时，Universe A 仍是成长分散化基准线。
- 当更重视低回撤和双大盘备兑核心时，Universe B 是防御收益候选线。
- Step B+ 应在 Universe A 与 Universe B 内分别比较 MDD 约束 Sharpe 前沿，而不是把本次样本内固定权重结果直接视为样本外最优。

## 校验结果

{_md_table(_validation_for_report(validation))}
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report, encoding="utf-8")


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
