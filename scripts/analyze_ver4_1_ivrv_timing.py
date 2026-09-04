"""Ver4.1: entry IV-RV timing diagnostics on the fixed-notional cycle ledger.

This is a descriptive diagnostic only.  It does not alter the Ver4.0 ledger or
claim that the current daily-close IV can be traded at the same day's close.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import mannwhitneyu, pearsonr, spearmanr


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "outputs" / "ver4_0_single_etf_cycle_cashflow"
OUTPUT_ROOT = PROJECT_ROOT / "outputs" / "ver4_1_ivrv_timing_diagnostics"
ETFS = ("510050", "510300", "510500", "159915", "588000")
STRATEGY_ORDER = ("ATM_Q100", "D50_Q100", "D40_Q100", "D30_Q100", "D20_Q100", "D10_Q100")
OUTCOMES = {
    "premium_net_income": "premium_net_income_yield",
    "final_net_option": "net_option_yield",
    "covered_call_strategy": "strategy_net_return",
}


def load_ledger(etf: str) -> pd.DataFrame:
    path = SOURCE_ROOT / etf / "period" / "ver4_0_cycle_ledger.csv"
    frame = pd.read_csv(path)
    frame = frame.loc[frame["strategy_name"].isin(STRATEGY_ORDER)].copy()
    frame["etf_code"] = etf
    frame["premium_net_income_yield"] = (
        pd.to_numeric(frame["gross_premium_yield"], errors="coerce")
        - pd.to_numeric(frame["transaction_cost_yield"], errors="coerce")
    )
    frame["iv_rv_spread"] = pd.to_numeric(frame["entry_iv_rv20_spread"], errors="coerce")
    return frame


def correlation_row(frame: pd.DataFrame, etf: str, strategy: str, outcome_name: str, outcome_column: str) -> dict:
    valid = frame[["iv_rv_spread", outcome_column]].dropna()
    observations = len(valid)
    if observations < 4 or valid["iv_rv_spread"].nunique() < 2 or valid[outcome_column].nunique() < 2:
        pearson = pearson_p = spearman = spearman_p = np.nan
    else:
        pearson, pearson_p = pearsonr(valid["iv_rv_spread"], valid[outcome_column])
        spearman, spearman_p = spearmanr(valid["iv_rv_spread"], valid[outcome_column])
    return {
        "etf_code": etf,
        "strategy_name": strategy,
        "outcome": outcome_name,
        "observations": observations,
        "pearson_r": pearson,
        "pearson_p_value": pearson_p,
        "spearman_rho": spearman,
        "spearman_p_value": spearman_p,
        "mean_iv_rv_spread": valid["iv_rv_spread"].mean(),
        "mean_outcome": valid[outcome_column].mean(),
    }


def tercile_rows(frame: pd.DataFrame, etf: str, strategy: str) -> list[dict]:
    valid = frame[["iv_rv_spread", *OUTCOMES.values()]].dropna().copy()
    if len(valid) < 9 or valid["iv_rv_spread"].nunique() < 3:
        return []
    valid["iv_rv_tercile"] = pd.qcut(valid["iv_rv_spread"], q=3, labels=("Low", "Mid", "High"), duplicates="drop")
    rows = []
    for bucket, group in valid.groupby("iv_rv_tercile", observed=True):
        result = {
            "etf_code": etf,
            "strategy_name": strategy,
            "iv_rv_tercile": str(bucket),
            "observations": len(group),
            "iv_rv_spread_mean": group["iv_rv_spread"].mean(),
        }
        for outcome_name, outcome_column in OUTCOMES.items():
            result[f"{outcome_name}_mean"] = group[outcome_column].mean()
            result[f"{outcome_name}_median"] = group[outcome_column].median()
        rows.append(result)
    return rows


def high_low_tercile_contrast(frame: pd.DataFrame, etf: str, strategy: str) -> dict | None:
    """Test whether the high-IV-RV third has higher final option yield than the low third.

    This is deliberately labelled exploratory: terciles are sample-derived and
    the test is repeated over multiple ETF/strategy combinations.
    """
    valid = frame[["iv_rv_spread", "net_option_yield"]].dropna().copy()
    if len(valid) < 9 or valid["iv_rv_spread"].nunique() < 3:
        return None
    valid["iv_rv_tercile"] = pd.qcut(valid["iv_rv_spread"], q=3, labels=("Low", "Mid", "High"), duplicates="drop")
    low = valid.loc[valid["iv_rv_tercile"] == "Low", "net_option_yield"]
    high = valid.loc[valid["iv_rv_tercile"] == "High", "net_option_yield"]
    if low.empty or high.empty:
        return None
    _, p_value = mannwhitneyu(high, low, alternative="greater")
    return {
        "etf_code": etf,
        "strategy_name": strategy,
        "low_observations": len(low),
        "high_observations": len(high),
        "low_final_net_option_mean": low.mean(),
        "high_final_net_option_mean": high.mean(),
        "high_minus_low_mean": high.mean() - low.mean(),
        "one_sided_mann_whitney_p_value": p_value,
    }


def pct(value: float) -> str:
    return "-" if pd.isna(value) else f"{value:.2%}"


def num(value: float) -> str:
    return "-" if pd.isna(value) else f"{value:.3f}"


def p_value(value: float) -> str:
    return "-" if pd.isna(value) else f"{value:.3f}"


def markdown_table(frame: pd.DataFrame, columns: list[str]) -> str:
    table = frame.loc[:, columns].copy()
    for column in ("pearson_r", "spearman_rho"):
        if column in table:
            table[column] = table[column].map(num)
    for column in ("pearson_p_value", "spearman_p_value", "one_sided_mann_whitney_p_value"):
        if column in table:
            table[column] = table[column].map(p_value)
    for column in (
        "mean_iv_rv_spread",
        "mean_outcome",
        "low_final_net_option_mean",
        "high_final_net_option_mean",
        "high_minus_low_mean",
    ):
        if column in table:
            table[column] = table[column].map(pct)
    return table.to_markdown(index=False)


def main() -> None:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    ledgers = {etf: load_ledger(etf) for etf in ETFS}
    correlation_rows: list[dict] = []
    tercile_result_rows: list[dict] = []
    tercile_contrast_rows: list[dict] = []

    for etf, ledger in ledgers.items():
        for strategy in STRATEGY_ORDER:
            subset = ledger.loc[ledger["strategy_name"] == strategy]
            for outcome_name, outcome_column in OUTCOMES.items():
                correlation_rows.append(correlation_row(subset, etf, strategy, outcome_name, outcome_column))
            tercile_result_rows.extend(tercile_rows(subset, etf, strategy))
            contrast = high_low_tercile_contrast(subset, etf, strategy)
            if contrast is not None:
                tercile_contrast_rows.append(contrast)

        # The pooled ETF view is descriptive across moneyness; strategy-level
        # correlations remain the primary evidence because their payoff shapes differ.
        for outcome_name, outcome_column in OUTCOMES.items():
            correlation_rows.append(correlation_row(ledger, etf, "ALL_STATIC_STRATEGIES", outcome_name, outcome_column))

    correlations = pd.DataFrame(correlation_rows)
    correlations.to_csv(OUTPUT_ROOT / "ver4_1_ivrv_correlations.csv", index=False, encoding="utf-8-sig")
    terciles = pd.DataFrame(tercile_result_rows)
    terciles.to_csv(OUTPUT_ROOT / "ver4_1_ivrv_tercile_outcomes.csv", index=False, encoding="utf-8-sig")
    tercile_contrasts = pd.DataFrame(tercile_contrast_rows)
    tercile_contrasts.to_csv(OUTPUT_ROOT / "ver4_1_ivrv_tercile_high_low_contrast.csv", index=False, encoding="utf-8-sig")

    primary = correlations.loc[
        (correlations["strategy_name"].isin(STRATEGY_ORDER))
        & (correlations["outcome"] == "final_net_option")
    ].copy()
    primary["same_direction"] = (primary["pearson_r"] > 0) & (primary["spearman_rho"] > 0)
    primary["both_p_under_10pct"] = (
        (primary["pearson_p_value"] < 0.10) & (primary["spearman_p_value"] < 0.10)
    )
    primary.to_csv(OUTPUT_ROOT / "ver4_1_ivrv_primary_net_option_screen.csv", index=False, encoding="utf-8-sig")

    report_lines = [
        "# Ver4.1 IV-RV 与备兑收益相关性诊断",
        "",
        "## 研究口径",
        "- 样本：Ver4.0 固定名义本金、逐期独立结算账本；五只 ETF，ATM/D50/D40/D30/D20/D10，满覆盖率。",
        "- 信号：`entry_iv_rv20_spread = entry_iv - entry_rv20`。RV 使用开仓日前 20 日收益；当前 IV 为开仓日的日频收盘隐含波动率。",
        "- 结果变量：扣摩擦权利金净收入、最终净期权收益、完整备兑策略当期收益。",
        "- 统计：Pearson 检验线性关系，Spearman 检验单调关系；p 值只作探索性参考，不进行多重检验调整。",
        "- 时间边界：当前开仓日收盘 IV 不能支持同日收盘成交的择时主张；若形成规则，日频可执行版本须以 T 日信号、T+1 日执行重跑。",
        "",
        "## 初筛：IV-RV 与最终净期权收益",
        markdown_table(
            primary,
            ["etf_code", "strategy_name", "observations", "pearson_r", "pearson_p_value", "spearman_rho", "spearman_p_value", "same_direction", "both_p_under_10pct"],
        ),
        "",
        "## 解读边界",
        "- 只有 Pearson 与 Spearman 同向、且三分位结果存在一致单调性时，才进入候选择时规则筛选。",
        "- 即使相关性为正，也可能只说明高 IV-RV 带来更高报价端权利金；必须进一步确认行权/截断后仍能留下更高的最终净期权收益。",
        "- 跨 Delta 汇总会混合不同的收益-让渡结构，因此只能作辅助描述，不应用于直接定阈值。",
        "",
        "## 高低 IV-RV 三分位对照（最终净期权收益）",
        "下表的 p 值为单侧 Mann-Whitney 检验（高 IV-RV 组是否高于低 IV-RV 组），未进行多重检验调整，仅用于提出候选规则。",
        markdown_table(
            tercile_contrasts,
            ["etf_code", "strategy_name", "low_observations", "high_observations", "low_final_net_option_mean", "high_final_net_option_mean", "high_minus_low_mean", "one_sided_mann_whitney_p_value"],
        ),
    ]
    (OUTPUT_ROOT / "ver4_1_ivrv_timing_research_record.md").write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    screen = primary.loc[primary["both_p_under_10pct"]]
    print(f"Wrote {OUTPUT_ROOT}")
    print(f"Strategy-level tests: {len(primary)}; exploratory same-direction candidates: {len(screen)}")
    if not screen.empty:
        print(screen[["etf_code", "strategy_name", "pearson_r", "spearman_rho"]].to_string(index=False))


if __name__ == "__main__":
    main()
