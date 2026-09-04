from __future__ import annotations

from pathlib import Path

import pandas as pd


def write_markdown_report(
    path: Path,
    *,
    sleeve_robustness: pd.DataFrame,
    portfolio_robustness: pd.DataFrame,
    sleeve_metrics: pd.DataFrame,
    portfolio_metrics: pd.DataFrame,
    cycle_concentration: pd.DataFrame,
    leave_one_summary: pd.DataFrame,
    sleeve_ensemble: pd.DataFrame,
    portfolio_ensemble: pd.DataFrame,
    ensemble_compare: pd.DataFrame,
    validation: pd.DataFrame,
    figure_paths: list[Path],
) -> None:
    """Write the independent phase-sensitivity diagnostic report."""

    b20 = _row(portfolio_robustness, "portfolio_name", "B_default_D20")
    most_robust = portfolio_robustness.iloc[0] if not portfolio_robustness.empty else {}
    fragile = sleeve_robustness.sort_values("phase_fragility_score", ascending=False).iloc[0] if not sleeve_robustness.empty else {}
    report = f"""# Independent Diagnostic: Phase Sensitivity Diagnostics for Covered-Call Sleeves

## 1. Research Goal / 研究目的

本实验是独立于 ver3 主实验线的旁路诊断，用于检验已经进入主线研究的 selected sleeves 与 candidate portfolios 是否对 inception-date / roll-calendar phase 高度敏感。

本实验不新增 DTE、delta、moneyness、TP、Touch-K 或动态权重，不纳入 588000，也不替换 `B_default_D20`。它只提供 phase robustness evidence，可作为后续 final appendix / robustness diagnostic 使用。

## 2. Project Structure Note / 工程结构说明

- 当前 `ver3/` 仍是主项目入口。
- phase sensitivity 代码位于 `ver3/scripts/python/` 与 `ver3/src/covered_call_mini_ver3/diagnostics/phase_sensitivity/`。
- 真实实验输出位于根目录 `outputs/ver3_0_independent_phase_sensitivity_diagnostics/`。
- `ver3/outputs/` 只保留轻量索引。
- 本实验不修改 Step A / Step B / Step B+ / Step C / Step D 的已有输出。

## 3. Methodology / 方法

- Phase grid: `h = 0..20` 个交易日，从 2022-09-30 起按共同 ETF 交易日向后平移。
- ETF BuyHold 使用 shifted window 直接计算。
- covered-call sleeves 不截取 h=0 return panel；每个 phase 都以 shifted inception date 作为第一笔 rebalance date，重新选第一张 call，并由到期结算日驱动后续 roll schedule。
- 指标分为 natural shifted window 与 common evaluation window；主表优先解读 common window。
- phase ensemble 使用共同窗口中各 phase 的日收益等权平均，用于诊断 staggered calendar 是否能降低 phase risk。

## 4. Target Sleeves / 目标 sleeves

{_md_table(_select_cols(sleeve_robustness, ["sleeve_name", "phase_count", "sharpe_median", "sharpe_std", "mdd_p75", "option_leg_median", "phase_fragility_score", "phase_robustness_label"]), pct_cols=["mdd_p75", "option_leg_median"], num_cols=["sharpe_median", "sharpe_std", "phase_fragility_score"])}

## 5. Target Portfolios / 目标组合

{_md_table(_select_cols(portfolio_robustness, ["portfolio_name", "phase_count", "sharpe_median", "sharpe_std", "mdd_p75", "option_leg_median", "phase_fragility_score", "phase_robust_score", "phase_robustness_label"]), pct_cols=["mdd_p75", "option_leg_median"], num_cols=["sharpe_median", "sharpe_std", "phase_fragility_score", "phase_robust_score"])}

## 6. Phase Metrics / 相位指标分布

Common evaluation window 是主读数。Natural shifted window 已保留在 CSV，用于观察真实不同入场日的自然样本差异；但因为样本长度略有不同，不作为主排名依据。

关键图表：

{_figure_list(figure_paths)}

## 7. Phase Robustness Summary / 相位稳健性总结

- 最高 phase fragility sleeve: `{fragile.get("sleeve_name", "")}`，fragility score = {_fmt_num(fragile.get("phase_fragility_score", float("nan")))}。
- phase robust score 最高的 candidate: `{most_robust.get("portfolio_name", "")}`，label = `{most_robust.get("phase_robustness_label", "")}`。
- `B_default_D20` label = `{b20.get("phase_robustness_label", "")}`，Sharpe median = {_fmt_num(b20.get("sharpe_median", float("nan")))}，MDD p75 = {_fmt_pct(b20.get("mdd_p75", float("nan")))}。

`B_default_D20` 的 phase 结果应理解为主线候选可信度的压力测试，而不是选择最佳入场 phase 的优化器。如果其 median / p25 / ensemble 读数仍然可接受，才增强主线候选可信度；如果 dispersion 过大，则应在 final appendix 中加入 phase risk caveat。

## 8. Cycle Attribution / 周期归因

{_cycle_section(cycle_concentration, leave_one_summary)}

## 9. Staggered Ensemble / 相位分散组合

Sleeve ensemble summary:

{_md_table(_select_cols(sleeve_ensemble, ["sleeve_name", "phase_count", "annualized_return_cagr", "sharpe_daily_mean", "max_drawdown", "option_leg_annualized_pnl_contribution", "final_nav"]), pct_cols=["annualized_return_cagr", "max_drawdown", "option_leg_annualized_pnl_contribution"], num_cols=["sharpe_daily_mean", "final_nav"])}

Portfolio ensemble summary:

{_md_table(_select_cols(portfolio_ensemble, ["portfolio_name", "phase_count", "annualized_return_cagr", "sharpe_daily_mean", "max_drawdown", "option_leg_annualized_pnl_contribution", "final_nav"]), pct_cols=["annualized_return_cagr", "max_drawdown", "option_leg_annualized_pnl_contribution"], num_cols=["sharpe_daily_mean", "final_nav"])}

Ensemble comparison:

{_md_table(_select_cols(ensemble_compare, ["portfolio_name", "ensemble_sharpe", "phase0_sharpe", "phase_median_sharpe", "delta_sharpe_vs_phase0", "ensemble_mdd", "phase0_mdd", "delta_mdd_vs_phase0", "ensemble_improves_sharpe_dispersion_proxy"]), pct_cols=["ensemble_mdd", "phase0_mdd", "delta_mdd_vs_phase0"], num_cols=["ensemble_sharpe", "phase0_sharpe", "phase_median_sharpe", "delta_sharpe_vs_phase0"])}

## 10. Interpretation / 研究解释

phase sensitivity 是 covered-call 策略的真实风险来源之一，因为起始日会改变第一张 option、后续 roll calendar、strike selection、premium、payoff burden 与 option-leg path。本实验不把 best phase 当成推荐，也不把 premium 当成立即利润；option leg contribution 一律按净 P&L contribution 解读。

如果某个 sleeve 的 option-leg 由少数 cycles 主导，应降低其 classification confidence。若 ensemble 明显降低 MDD 或 Sharpe dispersion，可以把 staggered calendar ensemble 作为执行层面的 risk mitigation 方案，但不自动替换主线 single-phase 结果。

## 11. Conclusion / 结论

- 建议将 phase diagnostics 纳入 final appendix：是。
- 是否把主线候选从 single-phase `B_default_D20` 改为 phase-ensemble `B_default_D20`：本报告只给 evidence，不自动替换；若 ensemble 在 common window 中同时改善 Sharpe/MDD 稳定性，可在执行层作为 risk mitigation 讨论。
- 是否需要对 sleeve 增加 phase risk caveat：对 label 为 `Phase Fragile` 或 cycle concentration 偏高的 sleeve 应增加。
- 后续建议：保留 phase-aware entry diagnostic，避免未来把单一起始日表现误读为稳定结构优势。

## Validation / 校验结果

{_md_table(validation)}
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report, encoding="utf-8-sig")


def _cycle_section(cycle: pd.DataFrame, leave_one: pd.DataFrame) -> str:
    if cycle.empty or "cycle_attribution_available" not in cycle or not bool(cycle["cycle_attribution_available"].iloc[0]):
        return "Cycle attribution unavailable; no synthetic cycle results were generated."
    table = cycle.groupby("sleeve_name", as_index=False).agg(
        option_cycle_count=("option_cycle_count", "median"),
        top_1_abs_cycle_pnl_share=("top_1_abs_cycle_pnl_share", "mean"),
        top_3_abs_cycle_pnl_share=("top_3_abs_cycle_pnl_share", "mean"),
        option_cycle_hhi=("option_cycle_hhi", "mean"),
        positive_cycle_rate=("positive_cycle_rate", "mean"),
    )
    loo = (
        leave_one.groupby("sleeve_name", as_index=False)
        .agg(
            leave_one_cycle_out_sharpe_min=("leave_one_cycle_out_sharpe_min", "min"),
            leave_one_cycle_out_option_leg_sign_flip_flag=("leave_one_cycle_out_option_leg_sign_flip_flag", "max"),
        )
        if not leave_one.empty and "leave_one_cycle_out_sharpe_min" in leave_one
        else pd.DataFrame()
    )
    if not loo.empty:
        table = table.merge(loo, on="sleeve_name", how="left")
    return _md_table(
        table,
        pct_cols=["top_1_abs_cycle_pnl_share", "top_3_abs_cycle_pnl_share", "positive_cycle_rate"],
        num_cols=["option_cycle_count", "option_cycle_hhi", "leave_one_cycle_out_sharpe_min"],
    )


def _select_cols(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    return df[[c for c in cols if c in df.columns]].copy() if not df.empty else pd.DataFrame(columns=cols)


def _figure_list(paths: list[Path]) -> str:
    if not paths:
        return "- No figures generated."
    return "\n".join(f"- `{p}`" for p in paths)


def _md_table(df: pd.DataFrame, pct_cols: list[str] | None = None, num_cols: list[str] | None = None) -> str:
    pct_cols = pct_cols or []
    num_cols = num_cols or []
    if df.empty:
        return "_No rows._"
    out = df.copy()
    for col in pct_cols:
        if col in out:
            out[col] = out[col].map(_fmt_pct)
    for col in num_cols:
        if col in out:
            out[col] = out[col].map(_fmt_num)
    return out.to_markdown(index=False)


def _fmt_pct(value: object) -> str:
    try:
        if pd.isna(value):
            return ""
        return f"{float(value):.2%}"
    except Exception:  # noqa: BLE001
        return str(value)


def _fmt_num(value: object) -> str:
    try:
        if pd.isna(value):
            return ""
        return f"{float(value):.3f}"
    except Exception:  # noqa: BLE001
        return str(value)


def _row(df: pd.DataFrame, col: str, value: str) -> pd.Series:
    if df.empty or col not in df:
        return pd.Series(dtype="object")
    row = df[df[col].eq(value)]
    return row.iloc[0] if not row.empty else pd.Series(dtype="object")
