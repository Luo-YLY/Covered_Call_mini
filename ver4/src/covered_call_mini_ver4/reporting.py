from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import CycleExperimentConfig


def write_markdown_report(
    config: CycleExperimentConfig,
    *,
    summary: pd.DataFrame,
    validation: pd.DataFrame,
    output_root: Path,
) -> Path:
    """Write a concise research record; client wording is intentionally deferred."""

    report = output_root / "reports" / "ver4_0_cycle_cashflow_research_record.md"
    passed = int(validation["passed"].sum()) if not validation.empty else 0
    total = len(validation)
    static_rows = summary[summary["parameter_role"].eq("static_target_delta_coverage")].copy() if not summary.empty else pd.DataFrame()
    preview_cols = [
        "strategy_label", "target_delta", "coverage", "cycle_count", "net_option_yield_median",
        "net_option_yield_p10", "positive_net_option_cycle_rate", "upside_cap_return_mean",
        "non_compound_annualized_net_option_yield",
    ]
    preview = static_rows[[column for column in preview_cols if column in static_rows]].head(10)
    table = preview.to_markdown(index=False) if not preview.empty else "_No static-grid result rows._"
    lines = [
        "# ver4.0 单 ETF 备兑周期现金流研究记录",
        "",
        "## 核算边界",
        "",
        f"- 标的：`{config.etf.etf_code}`；样本：`{config.etf.sample_start}` 至 `{config.etf.sample_end}`。",
        f"- 每个期权周期固定以 `{config.fixed_notional:.2f}` 名义本金单独结算，前期盈亏不复投。",
        "- 主结论不使用复利净值或 CAGR；日频 MTM 仅用于单周期内风险观察。",
        "- 当前仅运行静态 DTE30 目标 Delta x 覆盖率网格；IV 择时、随机缺失交易日和收益目标重抽样尚未启用。",
        "",
        "## 输出解释",
        "",
        "- `gross_premium_cash`：开仓时收到的权利金现金，不等同于最终净收益。",
        "- `net_option_pnl_cash`：扣除行权/平仓损失与交易摩擦后的期权腿经济结果。",
        "- `upside_cap_pnl_cash`：仅记录备兑相对裸持落后的部分，量化上涨让渡。",
        "",
        "## 静态网格预览",
        "",
        table,
        "",
        "## 校验",
        "",
        f"- {passed}/{total} 项校验通过。",
    ]
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report
