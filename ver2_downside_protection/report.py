from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from ver2_downside_protection.config import ExperimentConfig
from ver2_downside_protection.plotting import write_figures
from ver2_downside_protection.premium_income_defensive import (
    add_premium_decomposition,
    build_premium_income_outputs,
)
from ver2_downside_protection.strategy_engine import Ver2BacktestResult
from ver2_downside_protection.metrics import STRATEGY_ORDER


SELECTION_LOG_COLUMNS = [
    "etf_code",
    "strategy_name",
    "execution_mode",
    "rebalance_date",
    "period_end_date",
    "expiry_date",
    "actual_dte",
    "option_code",
    "option_type",
    "strike",
    "underlying_price_at_entry",
    "option_price_at_entry",
    "target_moneyness",
    "realized_moneyness",
    "coverage_ratio",
    "underlying_price_at_expiry",
    "option_payoff_at_expiry",
    "option_payoff_return_at_expiry",
    "total_premium",
    "intrinsic_value_at_entry",
    "extrinsic_value_at_entry",
    "total_premium_yield",
    "intrinsic_premium_yield",
    "extrinsic_premium_yield",
    "premium_return",
    "etf_period_return",
    "strategy_period_return",
    "excess_return_vs_etf",
    "option_selected_flag",
    "no_option_available_flag",
    "selection_reason",
    "price_source",
    "raw_bid_ask_spread_pct",
    "effective_bid_ask_spread_pct",
    "bid_ask_spread_source",
    "transaction_cost_return",
    "option_slippage_cost_return",
    "bid_ask_spread_cost_return",
    "etf_slippage_cost_return",
    "option_commission_cost_return",
]


SUMMARY_COLUMNS = [
    "etf_code",
    "strategy_name",
    "start_date",
    "end_date",
    "num_periods",
    "cumulative_return",
    "annualized_return",
    "annualized_volatility",
    "sharpe_ratio",
    "max_drawdown",
    "calmar_ratio",
    "assignment_rate",
    "excess_return_mean",
    "excess_win_rate",
    "downside_excess_mean",
    "downside_win_rate",
    "downside_cushion_ratio_mean",
    "downside_cushion_ratio_median",
    "average_downside_benefit",
    "upside_cost_mean",
    "upside_underperformance_rate",
    "protection_cost_ratio",
    "max_drawdown_improvement",
]


MARKDOWN_COLUMN_LABELS = {
    "etf_code": "ETF代码",
    "strategy_name": "策略名称",
    "start_date": "开始日期",
    "end_date": "结束日期",
    "num_periods": "周期数",
    "cumulative_return": "累计收益",
    "annualized_return": "年化收益",
    "annualized_volatility": "年化波动率",
    "sharpe_ratio": "夏普比率",
    "max_drawdown": "最大回撤",
    "calmar_ratio": "Calmar比率",
    "assignment_rate": "被行权频率",
    "excess_return_mean": "平均超额收益",
    "excess_win_rate": "超额收益胜率",
    "downside_excess_mean": "下跌期超额收益均值",
    "downside_win_rate": "下跌期跑赢频率",
    "downside_cushion_ratio_mean": "下跌缓冲比例均值",
    "downside_cushion_ratio_median": "下跌缓冲比例中位数",
    "average_downside_benefit": "平均下跌保护收益",
    "upside_cost_mean": "上涨成本均值",
    "upside_underperformance_rate": "上涨期跑输频率",
    "protection_cost_ratio": "保护成本比",
    "max_drawdown_improvement": "最大回撤改善",
    "annualized_extrinsic_premium_yield": "年化时间价值权利金收益",
    "average_total_premium_yield": "平均总权利金收益",
    "premium_capture_ratio": "权利金留存率",
    "primary_score": "主评分",
    "selection_reason": "跳过原因",
    "count": "次数",
}


def _safe_name(value: object) -> str:
    return str(value).replace("/", "_").replace("\\", "_").replace(" ", "_")


def _write_csv(df: pd.DataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    return path


def _format_percent(value: Any) -> str:
    if pd.isna(value):
        return ""
    return f"{float(value):.2%}"


def _format_float(value: Any) -> str:
    if pd.isna(value):
        return ""
    return f"{float(value):.3f}"


def _markdown_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_No rows._"
    display_columns = [MARKDOWN_COLUMN_LABELS.get(str(col), str(col)) for col in df.columns]
    header = "| " + " | ".join(display_columns) + " |"
    divider = "| " + " | ".join(["---"] * len(df.columns)) + " |"
    rows = ["| " + " | ".join(str(v) for v in row) + " |" for row in df.astype(str).values]
    return "\n".join([header, divider, *rows])


def _sort_by_strategy_order(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "strategy_name" not in df.columns:
        return df.copy()
    out = df.copy()
    out["_strategy_order"] = out["strategy_name"].map(STRATEGY_ORDER).fillna(999)
    sort_cols = [col for col in ["etf_code", "_strategy_order", "strategy_name"] if col in out.columns]
    return out.sort_values(sort_cols).drop(columns=["_strategy_order"]).reset_index(drop=True)


def _markdown_table_with_etf_gap(df: pd.DataFrame) -> str:
    if df.empty:
        return "_No rows._"
    display_columns = [MARKDOWN_COLUMN_LABELS.get(str(col), str(col)) for col in df.columns]
    header = "| " + " | ".join(display_columns) + " |"
    divider = "| " + " | ".join(["---"] * len(df.columns)) + " |"
    rows: list[str] = []
    previous_etf = None
    for _, row in df.astype(str).iterrows():
        current_etf = row["etf_code"] if "etf_code" in df.columns else None
        if previous_etf is not None and current_etf != previous_etf:
            rows.append("| " + " | ".join([""] * len(df.columns)) + " |")
        rows.append("| " + " | ".join(str(v) for v in row.values) + " |")
        previous_etf = current_etf
    return "\n".join([header, divider, *rows])


def _summary_for_markdown(summary: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "etf_code",
        "strategy_name",
        "num_periods",
        "cumulative_return",
        "annualized_return",
        "annualized_volatility",
        "sharpe_ratio",
        "max_drawdown",
        "assignment_rate",
        "downside_excess_mean",
        "downside_win_rate",
        "average_downside_benefit",
        "upside_cost_mean",
        "protection_cost_ratio",
        "max_drawdown_improvement",
    ]
    out = _sort_by_strategy_order(summary)[[col for col in cols if col in summary.columns]].copy()
    percent_cols = [
        "cumulative_return",
        "annualized_return",
        "annualized_volatility",
        "max_drawdown",
        "assignment_rate",
        "downside_excess_mean",
        "downside_win_rate",
        "average_downside_benefit",
        "upside_cost_mean",
        "max_drawdown_improvement",
    ]
    for col in percent_cols:
        if col in out.columns:
            out[col] = out[col].map(_format_percent)
    for col in ["sharpe_ratio", "protection_cost_ratio"]:
        if col in out.columns:
            out[col] = out[col].map(_format_float)
    return out


def _skipped_section(skipped: pd.DataFrame) -> str:
    if skipped.empty:
        return "本次没有 covered-call 策略的选券失败或跳过周期。"
    counts = (
        skipped.groupby(["etf_code", "strategy_name", "selection_reason"])
        .size()
        .reset_index(name="count")
        .sort_values(["etf_code", "strategy_name", "selection_reason"])
    )
    return _markdown_table(counts)


def _premium_income_for_markdown(premium_summary: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "etf_code",
        "strategy_name",
        "annualized_extrinsic_premium_yield",
        "average_total_premium_yield",
        "premium_capture_ratio",
        "assignment_rate",
        "downside_cushion_ratio_mean",
        "max_drawdown",
        "max_drawdown_improvement",
    ]
    out = _sort_by_strategy_order(premium_summary)[[col for col in cols if col in premium_summary.columns]].copy()
    for col in out.columns:
        if col not in {"etf_code", "strategy_name"}:
            out[col] = out[col].map(_format_percent)
    return out


def _ranking_for_markdown(ranking: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "etf_code",
        "strategy_name",
        "primary_score",
        "annualized_extrinsic_premium_yield",
        "downside_cushion_ratio_mean",
        "max_drawdown_improvement",
        "premium_capture_ratio",
    ]
    out = ranking[[col for col in cols if col in ranking.columns]].copy()
    if "primary_score" in out.columns:
        out["primary_score"] = out["primary_score"].map(_format_float)
    for col in [
        "annualized_extrinsic_premium_yield",
        "downside_cushion_ratio_mean",
        "max_drawdown_improvement",
        "premium_capture_ratio",
    ]:
        if col in out.columns:
            out[col] = out[col].map(_format_percent)
    return out


def build_markdown_report(config: ExperimentConfig, result: Ver2BacktestResult) -> str:
    summary_md = _markdown_table_with_etf_gap(_summary_for_markdown(result.summary))
    skipped_md = _skipped_section(result.skipped_periods)
    premium_outputs = build_premium_income_outputs(result.periods, result.nav, result.summary)
    premium_md = _markdown_table(_premium_income_for_markdown(premium_outputs["premium_summary"]))
    ranking_md = _markdown_table(_ranking_for_markdown(premium_outputs["defensive_ranking"]))
    strategies = ", ".join(strategy.name for strategy in config.enabled_strategies)
    assumptions = config.assumptions
    option_price_note = assumptions.get(
        "option_price",
        "Use bid/ask mid when both are available and valid; otherwise use option close.",
    )
    transaction_cost_note = assumptions.get("transaction_costs", "Use the configured proportional cost model.")

    return f"""# ver2 downside protection summary report

## 实验目标

ver2 将研究重点从收益增强转向下跌保护：观察 covered call 在 ETF 下跌周期中能否提供稳定缓冲，以及这种缓冲需要牺牲多少上涨收益。

## 实验标的

当前仅包含：{", ".join(config.etf_codes)}。

## 策略设定

启用策略：{strategies}。

BuyHold 为 ETF 买入持有基准；ITM5_100、ITM2_100、ATM_100、OTM2_100、OTM5_100 均为 100% 覆盖率的 DTE30 卖出 call 策略。ITM5/ITM2 的目标行权价分别为 `S * 0.95` 和 `S * 0.98`；OTM2/OTM5 的目标行权价分别为 `S * 1.02` 和 `S * 1.05`。OTM5_50 已在配置中预留，可打开 enabled 后运行。

## DTE30 与到期后再平衡

本框架当前执行口径为 `{config.backtest.execution_mode}`。初始建仓日使用首个月末 ETF 交易日；之后不再等待下一个月末，而是在上一张 call 的到期结算日立即尝试开下一张 DTE30 call。若结算日当天没有合适合约，则记录一段无期权的 ETF 持有期，并在下一交易日继续尝试。

选券复用 ver1 的 DTE 窗口逻辑：在 rebalance_date 当天的 call 链中，先筛选 {config.backtest.min_days_to_expiry}-{config.backtest.max_days_to_expiry} 天到期合约，再选择最接近 {config.backtest.target_dte} 天的到期日。ATM/ITM/OTM 选券只在该到期日内按目标行权价距离选择。continuous_30d 不使用“必须在下个月末前到期”的月度上限，只要求合约能在当前数据样本内完成结算。

## 日频盯市输出

本版已加入日频 MTM 账户诊断表：`daily_mtm/ver2_daily_mtm.csv`。该表逐日记录 ETF 价格、short call 标记价格、期权负债、开仓后 short call 浮动盈亏、`short_call_mtm_loss_return` 以及 `daily_mtm_nav`。其中 `short_call_mtm_loss_return = max(当前期权负债收益率 - 开仓权利金收益率, 0)`，用于后续专门考察卖出 call 后的日频盯市浮亏。

到期日当天，期权标记价格强制使用结算内在价值，使日频 MTM 路径在 period_end 与到期结算收益口径一致。非到期日只使用当日或此前可见的期权收盘价，不使用未来价格。

## 核心结果表

{summary_md}

## Premium-income defensive covered call optimization

本节新增一个更偏防御的优化口径：当用户不关心上涨截断时，策略优先提高权利金厚度、ETF 下跌时的缓冲、最大回撤改善和收益曲线平滑性。`upside_cost_mean` 与 `protection_cost_ratio` 不进入主评分，只保留为辅助诊断。

OTM5 不再是核心策略，而是偏保守的对照组；ATM 与轻度 ITM call 更重要，因为它们通常提供更厚的权利金和更直接的下跌缓冲。ITM call 的高权利金必须拆分为 intrinsic value 与 extrinsic value：真正可视为期权时间价值收入的部分，应重点观察 `extrinsic_premium_yield` 和 `premium_capture_ratio`。

主评分定义为：

`primary_score = 0.35 * annualized_extrinsic_premium_yield_rank + 0.25 * downside_cushion_ratio_rank + 0.25 * max_drawdown_improvement_rank + 0.15 * premium_capture_ratio_rank`

Premium-income summary：

{premium_md}

Defensive ranking：

{ranking_md}

## 下跌保护指标解释

`downside_excess_mean` 是 ETF 下跌周期内 covered call 相对 ETF 的平均超额收益，代表平均少亏幅度。

`downside_win_rate` 是 ETF 下跌周期内 covered call 跑赢 ETF 的频率。

`downside_cushion_ratio_mean` 是 `(R_CC - R_ETF) / abs(R_ETF)` 在 ETF 下跌周期内的均值，用于衡量下跌损失被权利金缓冲的比例。

`upside_cost_mean` 是 ETF 上涨周期内 covered call 平均牺牲的上涨收益；在 premium-income defensive 优化口径中它只作为辅助诊断，不进入主评分。

`protection_cost_ratio` 是平均上涨成本除以平均下跌保护收益；分母为 0 时返回 NaN。它同样只作为辅助输出。

`max_drawdown` 在 ver2 中统一为正数回撤幅度，`max_drawdown_improvement = BuyHold MDD - Strategy MDD`，正数表示最大回撤改善。

## 数据缺失或异常说明

{skipped_md}

字段映射与默认假设：

- ETF 价格使用 `adj_close`。
- 期权权利金：{option_price_note}
- 到期 payoff 使用期权到期日或其后最近 ETF 交易日的标的价格计算；`option_payoff_at_expiry` 为覆盖率调整后的每份 ETF 对应金额，`option_payoff_return_at_expiry` 为回测收益率口径。
- 交易成本：{transaction_cost_note}
- 选券只使用 rebalance_date 当天可见的期权链，不使用未来收益、未来波动率或未来价格。
- continuous_30d 使用日频期权链；如果期权源退回月末快照，会显著退化为低频开仓。

## 后续可扩展方向

- 打开 OTM5_50，比较 50% 覆盖率是否改善保护成本比。
- 在 ver2 稳定后，再单独引入 IV percentile timing 或 trend filter，不和本轮基础框架混在一起。
- 将 severe_down 样本单独做事件复盘，检查保护是否来自权利金本身还是极端上涨截断较少。
"""


def write_ver2_outputs(config: ExperimentConfig, result: Ver2BacktestResult) -> dict[str, Path | dict[str, dict[str, Path]]]:
    output_dir = config.paths.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path | dict[str, dict[str, Path]]] = {}

    periods = add_premium_decomposition(result.periods.copy())
    summary = _sort_by_strategy_order(result.summary.copy())
    summary = summary[[col for col in SUMMARY_COLUMNS if col in summary.columns]]
    premium_outputs = build_premium_income_outputs(periods, result.nav, result.summary)

    paths["periods"] = _write_csv(periods, output_dir / "summary_tables" / "ver2_periods.csv")
    paths["summary"] = _write_csv(summary, output_dir / "summary_tables" / "ver2_summary.csv")
    paths["nav"] = _write_csv(result.nav, output_dir / "nav" / "ver2_nav.csv")
    paths["daily_mtm"] = _write_csv(result.daily_mtm, output_dir / "daily_mtm" / "ver2_daily_mtm.csv")
    paths["downside_buckets"] = _write_csv(
        result.downside_buckets,
        output_dir / "downside_tables" / "ver2_downside_bucket_all.csv",
    )
    paths["skipped_periods"] = _write_csv(
        result.skipped_periods,
        output_dir / "selection_logs" / "ver2_skipped_periods.csv",
    )
    paths["premium_income_summary"] = _write_csv(
        premium_outputs["premium_summary"],
        output_dir / "premium_income" / "ver2_premium_income_summary.csv",
    )
    paths["premium_decomposition"] = _write_csv(
        premium_outputs["premium_decomposition"],
        output_dir / "premium_income" / "ver2_premium_decomposition_by_period.csv",
    )
    paths["defensive_strategy_ranking"] = _write_csv(
        premium_outputs["defensive_ranking"],
        output_dir / "premium_income" / "ver2_defensive_strategy_ranking.csv",
    )

    selection_cols = [col for col in SELECTION_LOG_COLUMNS if col in periods.columns]
    for (etf_code, strategy_name), g in periods.groupby(["etf_code", "strategy_name"]):
        path = output_dir / "selection_logs" / f"ver2_selection_log_{etf_code}_{_safe_name(strategy_name)}.csv"
        _write_csv(g[selection_cols].sort_values("rebalance_date"), path)

    if not result.daily_mtm.empty:
        for (etf_code, strategy_name), g in result.daily_mtm.groupby(["etf_code", "strategy_name"]):
            path = output_dir / "daily_mtm" / f"ver2_daily_mtm_{etf_code}_{_safe_name(strategy_name)}.csv"
            _write_csv(g.sort_values(["date", "period_index"]), path)

    if not result.downside_buckets.empty:
        for (etf_code, strategy_name), g in result.downside_buckets.groupby(["etf_code", "strategy_name"]):
            path = output_dir / "downside_tables" / f"ver2_downside_bucket_{etf_code}_{_safe_name(strategy_name)}.csv"
            _write_csv(g.sort_values("downside_bucket"), path)

    paths["figures"] = write_figures(
        result.periods,
        result.nav,
        result.downside_buckets,
        output_dir,
        result.daily_mtm,
    )
    report_text = build_markdown_report(config, result)
    report_path = output_dir / "reports" / "ver2_summary_report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report_text, encoding="utf-8")
    paths["report"] = report_path
    return paths
