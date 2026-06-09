from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import matplotlib.pyplot as plt
import pandas as pd

from src.reports.labels import label_strategy
from scripts.build_from_raw_data import build_source_from_raw


plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial Unicode MS", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

EXECUTABLE_STRATEGIES = [
    "S0_BuyHold",
    "S1_ATM_100_Monthly",
    "S4_OTM5_100_Monthly",
    "S5_IVTiming_ATM_Monthly",
    "S6_IVTiming_OTM5_Monthly",
    "S7_IVStyleRule_v1",
    "S8_IVStyleRule_Close_v1",
]
STRATEGY_ORDER_CN = [label_strategy(s) for s in EXECUTABLE_STRATEGIES]


def save(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(path, dpi=170)
    plt.close()


def write_csv_safe(df: pd.DataFrame, path: Path) -> Path:
    try:
        df.to_csv(path, index=False, encoding="utf-8-sig")
        return path
    except PermissionError:
        stamp = pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")
        fallback = path.with_name(f"{path.stem}_{stamp}{path.suffix}")
        df.to_csv(fallback, index=False, encoding="utf-8-sig")
        print(f"{path} is locked; wrote {fallback} instead.")
        return fallback


def pct(x: float) -> str:
    return "" if pd.isna(x) else f"{x:.2%}"


def strategy_cn(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["strategy_cn"] = out["strategy"].map(label_strategy)
    return out


def load_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    source = ROOT / "data" / "source"
    return (
        pd.read_csv(source / "etf_suitability_scores.csv"),
        pd.read_csv(source / "fixed_cc_strategy_summary.csv"),
        pd.read_csv(source / "pnl_decomposition_by_roll.csv"),
        pd.read_csv(source / "nav_by_strategy.csv"),
    )


def load_iv_rule_experiment() -> pd.DataFrame:
    path = ROOT / "data" / "source" / "iv_rule_experiment_summary.csv"
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def load_optional_source(name: str) -> pd.DataFrame:
    path = ROOT / "data" / "source" / name
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def write_tables(scores: pd.DataFrame, perf: pd.DataFrame, periods: pd.DataFrame, top5: list[str]) -> None:
    table_dir = ROOT / "tables"
    table_dir.mkdir(parents=True, exist_ok=True)
    score_cols = [
        "etf_code",
        "suitability_score",
        "etf_liquidity_score",
        "option_availability_score",
        "option_liquidity_score",
        "premium_adequacy_score",
        "upside_truncation_risk_score",
        "data_quality_score",
    ]
    scores_table = scores.head(5)[score_cols].copy()
    scores_table.columns = ["ETF代码", "备兑适用性总分", "ETF流动性分数", "期权可得性分数", "期权流动性分数", "权利金充足性分数", "低上涨截断风险分数", "数据质量分数"]
    scores_table.to_csv(table_dir / "top5_suitability_scores_cn.csv", index=False, encoding="utf-8-sig")

    audit_cols = [
        "etf_code",
        "soft_suitability_score",
        "hard_gate_has_options",
        "hard_gate_eligible_rolls",
        "hard_gate_data_completeness",
        "hard_gate_trading_days",
        "hard_gate_all",
        "suitability_score",
        "eligible_roll_date_ratio",
        "data_completeness_ratio",
        "number_of_trading_days",
        "etf_liquidity_score",
        "option_availability_score",
        "option_liquidity_score",
        "premium_adequacy_score",
        "upside_truncation_risk_score",
        "data_quality_score",
    ]
    audit_table = scores[[col for col in audit_cols if col in scores.columns]].copy()
    audit_table.columns = [
        "ETF代码",
        "软评分",
        "硬门槛_有期权",
        "硬门槛_有可选Roll",
        "硬门槛_数据完整度",
        "硬门槛_交易天数",
        "硬门槛_全部通过",
        "最终评分",
        "可选Roll比例",
        "数据完整度",
        "交易天数",
        "ETF流动性分数",
        "期权可得性分数",
        "期权流动性分数",
        "权利金充足性分数",
        "低上涨截断风险分数",
        "数据质量分数",
    ][: len(audit_table.columns)]
    audit_table.to_csv(table_dir / "universe_suitability_audit_cn.csv", index=False, encoding="utf-8-sig")

    perf_table = perf[[
        "etf_code",
        "strategy_cn",
        "annualized_return",
        "sharpe_ratio",
        "max_drawdown",
        "excess_return_annualized",
        "average_premium_yield",
        "total_premium_contribution",
        "total_upside_truncation_cost",
        "net_option_contribution",
        "assignment_frequency",
        "option_sale_success_rate",
    ]].copy()
    perf_table.columns = ["ETF代码", "策略", "年化收益", "夏普比率", "最大回撤", "年化超额收益", "平均权利金收益率", "累计权利金贡献", "累计上涨截断成本", "净期权贡献", "被行权频率", "期权卖出成功率"]
    perf_table.to_csv(table_dir / "top5_executable_strategy_summary_cn.csv", index=False, encoding="utf-8-sig")

    roll = periods[
        periods["strategy"].isin(
            [
                "S1_ATM_100_Monthly",
                "S4_OTM5_100_Monthly",
                "S5_IVTiming_ATM_Monthly",
                "S6_IVTiming_OTM5_Monthly",
                "S7_IVStyleRule_v1",
                "S8_IVStyleRule_Close_v1",
            ]
        )
    ].copy()
    roll["策略"] = roll["strategy"].map(label_strategy)
    roll = roll[["etf_code", "策略", "roll_date", "end_date", "option_selected_flag", "selection_reason", "premium_yield", "upside_cost", "cost", "net_option_contribution", "assignment_flag"]]
    roll.columns = ["ETF代码", "策略", "建仓日", "结束日", "是否卖出期权", "选券状态", "权利金收益率", "上涨截断成本", "交易成本", "净期权贡献", "是否被行权"]
    roll.to_csv(table_dir / "top5_roll_decomposition_cn.csv", index=False, encoding="utf-8-sig")

    iv_rules = load_iv_rule_experiment()
    if not iv_rules.empty:
        iv_rules = iv_rules[iv_rules["etf_code"].astype(str).isin(top5)].copy()
        iv_rules["etf_code"] = iv_rules["etf_code"].astype(str).str.zfill(6)
        rule_table = iv_rules[
            [
                "experiment_stage_name",
                "rule_name",
                "etf_code",
                "annualized_return",
                "excess_return_annualized",
                "average_coverage_ratio",
                "option_sale_success_rate",
                "net_option_contribution",
                "assignment_frequency",
            ]
        ].copy()
        rule_table.columns = [
            "实验阶段",
            "规则",
            "ETF代码",
            "年化收益",
            "年化期权贡献",
            "平均覆盖比例",
            "期权卖出成功率",
            "净期权贡献",
            "被行权频率",
        ]
        write_csv_safe(rule_table, table_dir / "iv_rule_experiment_summary_cn.csv")

    by_style = load_optional_source("iv_rule_experiment_by_style.csv")
    if not by_style.empty:
        style_table = by_style[
            [
                "style_group",
                "experiment_stage_name",
                "rule_name",
                "avg_excess_return_annualized",
                "avg_net_option_contribution",
                "avg_max_drawdown",
                "avg_coverage_ratio",
                "avg_assignment_frequency",
                "avg_option_sale_success_rate",
            ]
        ].copy()
        style_table.columns = [
            "风格组",
            "实验阶段",
            "规则",
            "平均年化期权贡献",
            "平均净期权贡献",
            "平均最大回撤",
            "平均覆盖比例",
            "平均被行权频率",
            "平均卖出成功率",
        ]
        write_csv_safe(style_table, table_dir / "iv_rule_experiment_by_style_cn.csv")

    rec = load_optional_source("iv_rule_recommendation.csv")
    if not rec.empty:
        rec_table = rec[
            [
                "etf_code",
                "style_group",
                "recommended_rule",
                "recommended_moneyness",
                "annualized_return",
                "excess_return_annualized",
                "net_option_contribution",
                "average_coverage_ratio",
                "option_sale_success_rate",
                "reason",
            ]
        ].copy()
        rec_table.columns = [
            "ETF代码",
            "风格组",
            "推荐规则",
            "推荐虚实值",
            "年化收益",
            "年化期权贡献",
            "净期权贡献",
            "平均覆盖比例",
            "期权卖出成功率",
            "推荐理由",
        ]
        write_csv_safe(rec_table, table_dir / "iv_rule_recommendation_cn.csv")


def make_figures(perf: pd.DataFrame, nav: pd.DataFrame, top5: list[str]) -> None:
    fig_dir = ROOT / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    nav = nav[(nav["etf_code"].isin(top5)) & (nav["strategy"].isin(EXECUTABLE_STRATEGIES))].copy()

    fig, axes = plt.subplots(len(top5), 1, figsize=(11, 3.1 * len(top5)))
    for ax, etf in zip(axes, top5):
        g = nav[nav["etf_code"] == etf]
        for strategy, s in g.groupby("strategy"):
            ax.plot(pd.to_datetime(s["date"]), s["nav"], label=label_strategy(strategy), color="black" if strategy == "S0_BuyHold" else None, linewidth=2.6 if strategy == "S0_BuyHold" else 1.5)
        ax.set_title(f"{etf}：净值曲线 (NAV), 黑线为买入持有基准")
        ax.grid(alpha=0.25)
        ax.legend(fontsize=8, ncol=3)
    save(fig_dir / "top5_nav_curves_executable.png")

    rows = []
    for etf, g in nav.groupby("etf_code"):
        benchmark = g[g["strategy"] == "S0_BuyHold"][["date", "nav"]].rename(columns={"nav": "bh_nav"})
        for strategy, s in g[g["strategy"] != "S0_BuyHold"].groupby("strategy"):
            merged = s.merge(benchmark, on="date", how="inner")
            merged["relative_nav"] = merged["nav"] / merged["bh_nav"]
            merged["strategy"] = strategy
            rows.append(merged[["date", "etf_code", "strategy", "relative_nav"]])
    rel = pd.concat(rows, ignore_index=True)
    fig, axes = plt.subplots(len(top5), 1, figsize=(11, 3.1 * len(top5)))
    for ax, etf in zip(axes, top5):
        g = rel[rel["etf_code"] == etf]
        for strategy, s in g.groupby("strategy"):
            ax.plot(pd.to_datetime(s["date"]), s["relative_nav"], label=label_strategy(strategy))
        ax.axhline(1, color="black", linestyle="--")
        ax.set_title(f"{etf}：相对买入持有净值 (Strategy NAV / BuyHold NAV)")
        ax.grid(alpha=0.25)
        ax.legend(fontsize=8, ncol=3)
    save(fig_dir / "top5_relative_nav_vs_buyhold.png")

    for metric, title, filename, center in [
        ("annualized_return", "前五ETF年化收益率 (Annualized Return)", "top5_annualized_return_heatmap.png", False),
        ("excess_return_annualized", "前五ETF相对买入持有年化超额收益 (Excess Return vs BuyHold)", "top5_excess_return_heatmap.png", True),
        ("sharpe_ratio", "前五ETF夏普比率 (Sharpe Ratio)", "top5_sharpe_heatmap.png", False),
    ]:
        matrix = perf.pivot(index="etf_code", columns="strategy_cn", values=metric).reindex(index=top5, columns=STRATEGY_ORDER_CN)
        plt.figure(figsize=(11, 4.8))
        if center:
            vmax = max(abs(pd.Series(matrix.to_numpy().ravel()).dropna()).max(), 1e-9)
            im = plt.imshow(matrix.fillna(0), aspect="auto", cmap="RdYlGn", vmin=-vmax, vmax=vmax)
        else:
            im = plt.imshow(matrix.fillna(0), aspect="auto", cmap="RdYlGn")
        plt.colorbar(im, label=title)
        plt.xticks(range(len(matrix.columns)), matrix.columns, rotation=25, ha="right")
        plt.yticks(range(len(matrix.index)), matrix.index)
        plt.title(title)
        save(fig_dir / filename)

    cc = perf[
        perf["strategy"].isin(
            [
                "S1_ATM_100_Monthly",
                "S4_OTM5_100_Monthly",
                "S5_IVTiming_ATM_Monthly",
                "S6_IVTiming_OTM5_Monthly",
            ]
        )
    ].copy()
    cc["label"] = cc["etf_code"] + "\n" + cc["strategy_cn"]
    x = range(len(cc))
    plt.figure(figsize=(14, 6))
    plt.bar(x, cc["total_premium_contribution"], label="累计权利金贡献 (Premium)")
    plt.bar(x, -cc["total_upside_truncation_cost"], label="累计上涨截断成本 (Upside Cost)")
    plt.bar(x, -cc["total_transaction_cost_drag"], label="累计交易成本拖累 (Cost)")
    plt.plot(x, cc["net_option_contribution"], color="black", marker="o", label="净期权贡献 (Net Option)")
    plt.axhline(0, color="black", linewidth=1)
    plt.xticks(list(x), cc["label"], rotation=35, ha="right", fontsize=8)
    plt.title("前五ETF可执行备兑策略收益拆解")
    plt.legend(fontsize=8, ncol=4)
    save(fig_dir / "top5_option_contribution_decomposition.png")

    fig, axes = plt.subplots(1, 2, figsize=(13, 4.8), sharey=True)
    for ax, metric, title in [
        (axes[0], "option_sale_success_rate", "期权卖出成功率 (Option Sale Success Rate)"),
        (axes[1], "assignment_frequency", "被行权频率 (Assignment Frequency)"),
    ]:
        matrix = cc.pivot(index="etf_code", columns="strategy_cn", values=metric).reindex(index=top5)
        ax.imshow(matrix.fillna(0), aspect="auto", cmap="YlGnBu", vmin=0, vmax=1)
        ax.set_xticks(range(len(matrix.columns)))
        ax.set_xticklabels(matrix.columns, rotation=25, ha="right")
        ax.set_yticks(range(len(matrix.index)))
        ax.set_yticklabels(matrix.index)
        ax.set_title(title)
        for i, etf in enumerate(matrix.index):
            for j, col in enumerate(matrix.columns):
                ax.text(j, i, pct(matrix.loc[etf, col]), ha="center", va="center", fontsize=8)
    save(fig_dir / "top5_option_success_and_assignment.png")


def write_report(scores: pd.DataFrame, perf: pd.DataFrame, top5: list[str]) -> None:
    scores_table = pd.read_csv(ROOT / "tables" / "top5_suitability_scores_cn.csv")
    lines = []
    for etf in top5:
        g = perf[perf["etf_code"] == etf]
        best = g.sort_values("annualized_return", ascending=False).iloc[0]
        best_cc = g[
            g["strategy"].isin(
                [
                    "S1_ATM_100_Monthly",
                    "S4_OTM5_100_Monthly",
                    "S5_IVTiming_ATM_Monthly",
                    "S6_IVTiming_OTM5_Monthly",
                ]
            )
        ].sort_values("excess_return_annualized", ascending=False).iloc[0]
        result = "跑赢" if best_cc["excess_return_annualized"] > 0 else "跑输"
        lines.append(f"- {etf}：绝对年化收益最高的是 **{best['strategy_cn']}**（年化收益 {pct(best['annualized_return'])}）。备兑策略中相对 BuyHold 最好的是 **{best_cc['strategy_cn']}**，年化超额收益 {pct(best_cc['excess_return_annualized'])}，结论为{result} BuyHold。")
    text = f"""# 前五ETF备兑策略聚焦报告

本报告选取备兑适用性评分前五 ETF：{', '.join(top5)}。

数据流程：本报告以本项目 `data/raw/` 中自带的 Tushare raw/converted data 为起点，18 只 ETF 只参与第一步备兑适用性评分；评分前五 ETF 才进入后续备兑增强策略回测。

评分规则：先计算流动性、期权可得性、期权流动性、权利金充足性、低上涨截断风险和数据质量等软评分；再把“有期权”“有可选月度 roll”“数据完整度达标”“交易天数达标”等硬性条件作为示性函数乘到软评分上。硬性门槛未通过的 ETF 不进入后续策略对比。

只展示当前可执行策略：买入持有、ATM全覆盖月度备兑、OTM5全覆盖月度备兑。Delta30 和 IV 相关内容因缺少 delta/implied_vol 暂不展示。

## 前五ETF适用性评分

```text
{scores_table.to_string(index=False)}
```

## 策略比较结论

{chr(10).join(lines)}

## 图表清单

- `figures/top5_nav_curves_executable.png`
- `figures/top5_relative_nav_vs_buyhold.png`
- `figures/top5_annualized_return_heatmap.png`
- `figures/top5_excess_return_heatmap.png`
- `figures/top5_sharpe_heatmap.png`
- `figures/top5_option_contribution_decomposition.png`
- `figures/top5_option_success_and_assignment.png`

全量评分审计表：`tables/universe_suitability_audit_cn.csv`
"""
    (ROOT / "report").mkdir(parents=True, exist_ok=True)
    (ROOT / "report" / "focused_top5_executable_strategy_report.md").write_text(text, encoding="utf-8-sig")


def main() -> None:
    build_source_from_raw()
    scores, perf, periods, nav = load_inputs()
    style_summary = load_optional_source("iv_style_rule_v1_summary.csv")
    style_periods = load_optional_source("iv_style_rule_v1_periods.csv")
    close_summary = load_optional_source("iv_style_rule_close_v1_summary.csv")
    close_periods = load_optional_source("iv_style_rule_close_v1_periods.csv")
    if not style_summary.empty:
        perf = pd.concat([perf, style_summary], ignore_index=True, sort=False)
    if not close_summary.empty:
        perf = pd.concat([perf, close_summary], ignore_index=True, sort=False)
    style_period_sets = [df for df in [style_periods, close_periods] if not df.empty]
    if style_period_sets:
        extra_periods = pd.concat(style_period_sets, ignore_index=True, sort=False)
        periods = pd.concat([periods, extra_periods], ignore_index=True, sort=False)
        style_nav_rows = []
        for (etf_code, strategy), g in extra_periods.groupby(["etf_code", "strategy"]):
            g = g.sort_values("roll_date")
            nav_value = 1.0
            if not g.empty:
                style_nav_rows.append({"date": g.iloc[0]["roll_date"], "etf_code": etf_code, "strategy": strategy, "nav": nav_value})
            for _, row in g.iterrows():
                nav_value *= 1 + row["R_cc"]
                style_nav_rows.append({"date": row["end_date"], "etf_code": etf_code, "strategy": strategy, "nav": nav_value})
        if style_nav_rows:
            nav = pd.concat([nav, pd.DataFrame(style_nav_rows)], ignore_index=True, sort=False)
    scores = scores.sort_values("suitability_score", ascending=False)
    top5 = scores.head(5)["etf_code"].astype(str).tolist()
    for df in [perf, periods, nav]:
        df["etf_code"] = df["etf_code"].astype(str).str.zfill(6)
    perf = perf[(perf["etf_code"].isin(top5)) & (perf["strategy"].isin(EXECUTABLE_STRATEGIES))].copy()
    perf = strategy_cn(perf)
    strategy_rank = {s: i for i, s in enumerate(EXECUTABLE_STRATEGIES)}
    perf["etf_rank"] = perf["etf_code"].map({etf: i for i, etf in enumerate(top5)})
    perf["strategy_rank"] = perf["strategy"].map(strategy_rank)
    perf = perf.sort_values(["etf_rank", "strategy_rank"])
    periods = periods[(periods["etf_code"].isin(top5)) & (periods["strategy"].isin(EXECUTABLE_STRATEGIES))].copy()

    write_tables(scores, perf, periods, top5)
    make_figures(perf, nav, top5)
    write_report(scores, perf, top5)
    print("covered_call_mini_demo completed.")


if __name__ == "__main__":
    main()
