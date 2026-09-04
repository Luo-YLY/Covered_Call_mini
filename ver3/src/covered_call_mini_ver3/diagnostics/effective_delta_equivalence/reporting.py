from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from .config import DiagnosticConfig
from .io import rel_path


def write_markdown_report(
    *,
    config: DiagnosticConfig,
    implementation_grid: pd.DataFrame,
    summary: pd.DataFrame,
    tracking: pd.DataFrame,
    quality: pd.DataFrame,
    stress: pd.DataFrame,
    pairwise: pd.DataFrame,
    phase_summary: pd.DataFrame,
    recommendation: pd.DataFrame,
    validation: pd.DataFrame,
    figure_paths: dict[str, Path],
) -> Path:
    report_path = config.paths.output_root / "reports" / "ver3_0_independent_effective_delta_equivalence_diagnostic_report.md"
    lines = [
        "# Independent Diagnostic | Effective-Delta Equivalent Covered-Call Implementation Test",
        "",
        f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## 1. Research Goal / 研究目的",
        "",
        "本实验是独立旁路诊断，用于检验在相同 entry effective delta 附近，不同 target-delta x coverage 实现方式是否会产生不同的 payoff shape、期权腿质量、回撤与相位稳健性。它不是参数网格优化，也不修改 Step A-D 或当前主候选 `B_default_D20`。",
        "",
        "## 2. Project Structure Note / 工程结构说明",
        "",
        f"- 代码入口：`{rel_path(config, config.paths.ver3_root / 'scripts/python/run_effective_delta_equivalence_diagnostic.py')}`",
        "- 模块目录：`ver3/src/covered_call_mini_ver3/diagnostics/effective_delta_equivalence/`",
        f"- 真实输出：`{rel_path(config, config.paths.output_root)}`",
        f"- ver3 轻量索引：`{rel_path(config, config.paths.ver3_output_index)}`",
        "- 本实验不改写 Step A / B / B+ / C / D 既有输出。",
        "",
        "## 3. Methodology / 方法",
        "",
        f"目标 entry effective delta = `{config.target_effective_delta:.2f}`，对应 short call overlay delta = `1 - {config.target_effective_delta:.2f} = {1 - config.target_effective_delta:.2f}`。每个实现方式满足 `coverage x target_call_delta = 0.28`。D28_Q100 在这里不是 Q100 stress 主线，而是等 effective delta 对照。",
        "",
        md_table(implementation_grid, pct_cols=["target_effective_delta", "target_call_delta", "coverage", "expected_overlay_delta", "expected_effective_delta", "effective_delta_error_vs_target"]),
        "",
        "## 4. Target ETFs / 目标 ETF",
        "",
        f"本轮默认只覆盖 `{', '.join(config.active_etfs)}`。510300 与 510050 是主线大盘 covered-call core，因此优先用于检验同一 effective delta 下 implementation 是否等价。",
        "",
        "## 5. Effective Delta Tracking / 有效 delta 跟踪",
        "",
        md_table(
            tracking,
            pct_cols=[
                "target_effective_delta",
                "target_call_delta",
                "coverage",
                "expected_overlay_delta",
                "expected_effective_delta",
                "actual_entry_delta_mean",
                "actual_entry_delta_median",
                "actual_effective_delta_mean",
                "actual_effective_delta_median",
                "effective_delta_tracking_error",
            ],
        ),
        "",
        "## 6. Performance Comparison / 绩效比较",
        "",
        md_table(
            summary[
                [
                    "etf_code",
                    "implementation_name",
                    "sample_start",
                    "sample_end",
                    "n_trading_days",
                    "annualized_return_cagr",
                    "sharpe_daily_mean",
                    "annualized_volatility",
                    "max_drawdown",
                    "calmar_ratio",
                    "sortino_ratio",
                    "final_nav",
                ]
            ],
            pct_cols=["annualized_return_cagr", "annualized_volatility", "max_drawdown"],
            num_cols=["sharpe_daily_mean", "calmar_ratio", "sortino_ratio", "final_nav"],
        ),
        "",
        "## 7. Option-Leg Quality / 期权腿质量",
        "",
        md_table(
            quality,
            pct_cols=[
                "premium_sum",
                "payoff_sum",
                "transaction_cost_sum",
                "net_option_leg_sum",
                "option_leg_annualized_pnl_contribution",
                "premium_capture_ratio_agg",
                "payoff_burden_agg",
                "positive_option_leg_period_rate",
                "assignment_rate",
                "avg_active_coverage",
                "avg_realized_moneyness",
                "avg_actual_entry_delta",
            ],
        ),
        "",
        "MTM stress：",
        "",
        md_table(stress, pct_cols=["p95_short_call_mtm_loss", "p99_short_call_mtm_loss", "max_short_call_mtm_loss", "mean_short_call_mtm_loss"]),
        "",
        "## 8. Pairwise Implementation Comparison / 两两对照",
        "",
        md_table(
            pairwise,
            pct_cols=[
                "delta_cagr_left_minus_right",
                "delta_vol_left_minus_right",
                "delta_mdd_left_minus_right",
                "delta_option_leg_left_minus_right",
                "delta_premium_capture_left_minus_right",
                "delta_payoff_burden_left_minus_right",
                "delta_p99_mtm_stress_left_minus_right",
                "delta_tracking_error_abs_left_minus_right",
            ],
            num_cols=["delta_sharpe_left_minus_right"],
        ),
        "",
        "## 9. Phase-lite Diagnostics / 轻量相位检验",
        "",
        md_table(
            phase_summary,
            pct_cols=["phase_lite_mdd_p75", "phase_lite_option_leg_median", "phase_lite_tracking_error_abs_median"],
            num_cols=["phase_lite_sharpe_median", "phase_lite_sharpe_std"],
        ),
        "",
        "## 10. Interpretation / 研究解释",
        "",
        "本实验不按最高 Sharpe 选择新策略，而是观察同一 entry effective delta 下，strike 距离与覆盖率如何改变收益截断、权利金缓冲、MTM 压力和相位稳定性。如果 implementation 之间差异显著，说明 entry effective delta 不是 covered-call sleeve 的充分统计量，target delta 与 coverage 需要分别解释。",
        "",
        md_table(recommendation),
        "",
        "## 11. Conclusion / 结论",
        "",
        conclusion_text(recommendation),
        "",
        "## 12. Figures / 图表索引",
        "",
        "\n".join(f"- `{rel_path(config, path)}`" for path in figure_paths.values()) if figure_paths else "_Plots skipped._",
        "",
        "## 13. Validation / 校验",
        "",
        md_table(validation),
    ]
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def write_ver3_output_index(
    *,
    config: DiagnosticConfig,
    report_path: Path,
    summary_path: Path,
    validation: pd.DataFrame,
    recommendation: pd.DataFrame,
) -> Path:
    path = config.paths.ver3_output_index
    d40_support = "mixed"
    appendix = "mixed"
    if not recommendation.empty:
        d40_support = "; ".join(recommendation["d40_q70_support_state"].astype(str).unique())
        appendix = "yes" if bool(recommendation["final_appendix_recommended"].any()) else "no"
    text = "\n".join(
        [
            "# ver3.0 Effective-Delta Equivalence Output Index",
            "",
            f"- Real output root: `{rel_path(config, config.paths.output_root)}`",
            f"- Core report: `{rel_path(config, report_path)}`",
            f"- Core summary: `{rel_path(config, summary_path)}`",
            f"- Run time: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`",
            f"- Target effective delta: `{config.target_effective_delta:.2f}`",
            f"- Target ETFs: `{', '.join(config.active_etfs)}`",
            f"- Candidate implementations: `{', '.join(item.name for item in config.implementations)}`",
            f"- D40_Q70 support state: `{d40_support}`",
            f"- Recommend final appendix: `{appendix}`",
            f"- Validation: `{int(validation['passed'].sum())}/{len(validation)} passed`",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def conclusion_text(recommendation: pd.DataFrame) -> str:
    if recommendation.empty:
        return "Phase-lite 或 recommendation 诊断未生成，本实验只作为 implementation evidence 保留。"
    if recommendation["d40_q70_support_state"].astype(str).str.contains("supports_current_mainline").all():
        d40 = "D40_Q70 在同一 effective delta 对照中仍能支持当前主线解释。"
    else:
        d40 = "D40_Q70 的主线解释需要在 appendix 中补充 implementation 差异说明。"
    appendix = "D28_Q100 / D35_Q80 值得纳入 appendix。" if recommendation["final_appendix_recommended"].any() else "暂不需要把替代实现作为重点 appendix。"
    return f"{d40} {appendix} 本实验不建议自动替换主线，仅提供 implementation robustness evidence。"


def md_table(
    df: pd.DataFrame,
    pct_cols: list[str] | None = None,
    num_cols: list[str] | None = None,
) -> str:
    if df.empty:
        return "_No rows._"
    out = df.copy()
    for col in pct_cols or []:
        if col in out.columns:
            out[col] = out[col].map(_fmt_pct)
    for col in num_cols or []:
        if col in out.columns:
            out[col] = out[col].map(_fmt_num)
    return out.fillna("").to_markdown(index=False)


def _fmt_pct(value: object) -> str:
    if pd.isna(value):
        return ""
    return f"{float(value):.2%}"


def _fmt_num(value: object) -> str:
    if pd.isna(value):
        return ""
    return f"{float(value):.3f}"
