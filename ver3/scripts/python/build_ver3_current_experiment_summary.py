from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys
from typing import Iterable, Optional

import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
OUTPUT_ROOT = ROOT / "outputs" / "ver3_0_current_experiment_summary"
REPORT_PATH = OUTPUT_ROOT / "reports" / "ver3_0_current_experiment_summary_report.md"
INDEX_PATH = ROOT / "ver3" / "outputs" / "ver3_0_current_experiment_summary_output_index.md"


def main() -> None:
    data = load_data()
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(build_report(data), encoding="utf-8")
    INDEX_PATH.write_text(build_index(data), encoding="utf-8")
    print(f"wrote report: {REPORT_PATH}")
    print(f"wrote index: {INDEX_PATH}")


def load_data() -> dict[str, pd.DataFrame]:
    stepA_main_class = read_csv("outputs/ver3_0_stepA_single_etf_sleeves/summary/ver3_0_stepA_sleeve_classification_table.csv")
    stepA_510050_class = read_csv("outputs/ver3_0_stepA_extension_510050_sleeve_clarification/summary/ver3_0_stepA_extension_510050_classification_table.csv")
    stepA_588000_class = read_csv("outputs/ver3_0_stepA_extension_588000_sleeve_clarification/summary/ver3_0_stepA_extension_588000_classification_table.csv")
    sleeve_surface_grid = read_csv("outputs/ver3_0_stepA_moneyness_refined_daily_mtm_surface/summary/ver3_0_stepA_moneyness_refined_daily_mtm_surface_grid.csv")
    return {
        "stepA_main_summary": read_csv("outputs/ver3_0_stepA_single_etf_sleeves/summary/ver3_0_stepA_single_etf_sleeve_summary.csv"),
        "stepA_main_class": stepA_main_class,
        "stepA_510050_summary": read_csv("outputs/ver3_0_stepA_extension_510050_sleeve_clarification/summary/ver3_0_stepA_extension_510050_sleeve_summary.csv"),
        "stepA_510050_class": stepA_510050_class,
        "stepA_588000_summary": read_csv("outputs/ver3_0_stepA_extension_588000_sleeve_clarification/summary/ver3_0_stepA_extension_588000_sleeve_summary.csv"),
        "stepA_588000_class": stepA_588000_class,
        "sleeve_diag_primary": build_current_primary_recommendations(
            stepA_main_class,
            stepA_510050_class,
            stepA_588000_class,
        ),
        "sleeve_surface_grid": sleeve_surface_grid,
        "sleeve_surface_metadata": build_refined_surface_metadata(sleeve_surface_grid),
        "sleeve_surface_figures": read_csv("outputs/ver3_0_stepA_moneyness_refined_daily_mtm_surface/summary/ver3_0_stepA_moneyness_refined_daily_mtm_figures.csv"),
        "stepB_summary": read_csv("outputs/ver3_0_stepB_fixed_weight_universe_comparison/summary/ver3_0_stepB_portfolio_summary.csv"),
        "stepB_weights": read_csv("outputs/ver3_0_stepB_fixed_weight_universe_comparison/config/ver3_0_stepB_portfolio_weight_map.csv"),
        "stepB_selected_vs_pure": read_csv("outputs/ver3_0_stepB_fixed_weight_universe_comparison/summary/ver3_0_stepB_selected_vs_pure_baseline.csv"),
        "stepB_plus_default": read_csv("outputs/ver3_0_stepB_plus_mdd_constrained_sharpe_frontier/summary/ver3_0_stepB_plus_frontier_summary_default.csv"),
        "stepB_plus_weights": read_csv("outputs/ver3_0_stepB_plus_mdd_constrained_sharpe_frontier/summary/ver3_0_stepB_plus_best_weights_by_drawdown_target.csv"),
        "stepB_plus_vs_fixed": read_csv("outputs/ver3_0_stepB_plus_mdd_constrained_sharpe_frontier/summary/ver3_0_stepB_plus_comparison_vs_fixed_weight_baselines.csv"),
        "stepC_summary": read_csv("outputs/ver3_0_stepC_robustness_stability_diagnostics/summary/ver3_0_stepC_candidate_full_sample_summary.csv"),
        "stepC_scorecard": read_csv("outputs/ver3_0_stepC_robustness_stability_diagnostics/summary/ver3_0_stepC_stability_scorecard.csv"),
        "stepC_recommended": read_csv("outputs/ver3_0_stepC_robustness_stability_diagnostics/summary/ver3_0_stepC_recommended_candidate_table.csv"),
        "stepC_validation": read_csv("outputs/ver3_0_stepC_robustness_stability_diagnostics/summary/ver3_0_stepC_validation_summary.csv"),
        "stepD_universe": read_csv("outputs/ver3_0_stepD_volatility_controlled_dynamic_weighting/config/ver3_0_stepD_universe_config.csv"),
        "stepD_methods": read_csv("outputs/ver3_0_stepD_volatility_controlled_dynamic_weighting/config/ver3_0_stepD_method_config.csv"),
        "stepD_summary": read_csv("outputs/ver3_0_stepD_volatility_controlled_dynamic_weighting/summary/ver3_0_stepD_dynamic_strategy_summary.csv"),
        "stepD_recommended": read_csv("outputs/ver3_0_stepD_volatility_controlled_dynamic_weighting/summary/ver3_0_stepD_recommendation_table.csv"),
        "stepD_vs_static": read_csv("outputs/ver3_0_stepD_volatility_controlled_dynamic_weighting/summary/ver3_0_stepD_comparison_vs_static_baselines.csv"),
        "stepD_turnover": read_csv("outputs/ver3_0_stepD_volatility_controlled_dynamic_weighting/turnover/ver3_0_stepD_turnover_summary.csv"),
        "stepD_bound_hits": read_csv("outputs/ver3_0_stepD_volatility_controlled_dynamic_weighting/weights/ver3_0_stepD_weight_bound_hits.csv"),
        "stepD_cost": read_csv("outputs/ver3_0_stepD_volatility_controlled_dynamic_weighting/cost/ver3_0_stepD_rebalance_cost_sensitivity.csv"),
        "stepD_validation": read_csv("outputs/ver3_0_stepD_volatility_controlled_dynamic_weighting/summary/ver3_0_stepD_validation_summary.csv"),
    }


def build_report(data: dict[str, pd.DataFrame]) -> str:
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    primary = data["stepC_recommended"].iloc[0]
    stepc_validation = validation_text(data["stepC_validation"])
    stepd_validation = validation_text(data["stepD_validation"])
    primary_metrics = data["stepC_summary"][data["stepC_summary"]["portfolio_name"].eq(primary["portfolio_name"])].iloc[0]

    return f"""# covered_call_mini ver3 当前实验汇总报告

生成时间：{generated_at}
项目入口：`ver3/`
报告范围：ver3.0 已完成的 Step A、Step A Extension、Sleeve Diagnostics Pack、Step B、Step B+、Step C、Step D。
报告定位：这是当前研究总报告，目的是把每个定义、样本口径、实验步骤、输出位置、结果解释和当前结论放在同一份 Markdown 中，方便人工审查和后续写作。

## 0. 结论先行

当前主线仍建议以 Step C 的 `{primary["portfolio_name"]}` 作为核心展示候选，而不是直接用 Step D 动态权重替代。

```text
{primary["portfolio_name"]}
= 510300 DTE30_D40_Q70_Hold 70%
+ 510050 DTE30_D40_Q70_Hold 15%
+ 159915 DTE30_OTM5up_Q50_Hold 15%
```

选择它的原因是：它不是单项收益最高，而是在共同长样本中保留了较好的 Sharpe、较可控的 MDD、清晰的大盘备兑收入逻辑和较高的稳定性评分。

{md_table(pd.DataFrame([{
        "主候选": primary["portfolio_name"],
        "样本开始": primary_metrics["sample_start"],
        "样本结束": primary_metrics["sample_end"],
        "交易日数": primary_metrics["n_trading_days"],
        "CAGR": primary_metrics["annualized_return_cagr"],
        "Sharpe": primary_metrics["sharpe_daily_mean"],
        "MDD": primary_metrics["max_drawdown"],
        "期权腿年化贡献": primary_metrics["option_leg_annualized_pnl_contribution"],
        "稳定性评分": primary["overall_stability_score"],
        "稳定性标签": primary["overall_stability_label"],
    }]), pct_cols=["CAGR", "MDD", "期权腿年化贡献", "稳定性评分"], num_cols=["Sharpe"])}

Step D 已经完成第一轮实验建设，但在本版完整报告中暂不展示动态策略指标、权重路径、触边统计或换手数据。它的定位仍是“动态权重研究层”：在 Step A/B/C 已固定的 sleeve 之上，观察月度资金权重调整是否有研究价值，而不是直接替代 Step C 的静态主线结论。

校验状态：Step C `{stepc_validation}`；Step D `{stepd_validation}`。

## 1. 定义词典

### 1.1 标的与 ETF 代码

| 代码 | 本项目中的含义 | 当前主线角色 |
| --- | --- | --- |
| `510300` | 沪深 300 ETF，用作大盘核心资产之一。 | Step A/B/C/D 主线资产。 |
| `510050` | 上证 50 ETF，用作大盘偏防御/偏蓝筹补充。 | Step A extension 后进入 Universe B。 |
| `510500` | 中证 500 ETF，用作中盘/成长分散化资产。 | Universe A 中保留纯 ETF sleeve。 |
| `159915` | 创业板 ETF，用作成长弹性资产。 | 采用较轻覆盖的备兑 sleeve，偏防御成长 overlay。 |
| `588000` | 科创 50 ETF。 | 仅 short-sample extension，不进入主线长样本组合。 |

### 1.2 Sleeve 与期权参数命名

`sleeve` 是本项目的最小策略单元。一个 sleeve 通常等于“一个 ETF 标的 + 一套期权覆盖规则 + 一条日收益/NAV 曲线”。组合层不直接重新选择期权，而是读取这些 sleeve 的 `daily_return` 后加权。

| 名称片段 | 定义 |
| --- | --- |
| `ETF_BuyHold` | 裸持 ETF，不卖出 call，期权腿收益为 0。 |
| `DTE30` | 开仓时目标剩余期限约 30 个自然日或交易日附近，具体由 Step A engine 可得合约决定。 |
| `D40` | 按 Delta 约 0.40 的 call 作为备兑卖出目标。 |
| `ATM` | 平值附近 call。当前主线不提升 ATM Q100，只保留诊断。 |
| `OTM5up` | 虚值约 5% 以上的 call，用于减轻上涨损失。 |
| `Q50` / `Q70` / `Q100` | 覆盖比例，分别约代表 50%、70%、100% 的标的名义覆盖。Q100 多数只作为压力测试。 |
| `Hold` | 卖出后持有到到期或规则结束，不使用 TP/Touch-K 提前平仓逻辑。 |
| `TP80` | 获利 80% 附近提前止盈的路径管理诊断。当前不进入主线。 |
| `TouchK` | 标的触及行权价附近触发处理的诊断。当前不进入主线。 |

### 1.3 组合层定义

| 概念 | 定义 |
| --- | --- |
| `Universe A` | `510300 covered-call + 510500 ETF BuyHold + 159915 covered-call`，偏成长分散化。 |
| `Universe B` | `510300 covered-call + 510050 covered-call + 159915 covered-call`，偏防御收入。 |
| `Pure_ETF` | 三个标的均使用 ETF BuyHold，作为裸持基准。 |
| `Selected` | 使用 Step A 筛出的推荐 sleeve 构成组合。 |
| `weight_scheme` | 固定权重方案，例如 `50_30_20` 表示三个 sleeve 权重分别为 50%、30%、20%。 |
| `portfolio_daily_return` | 组合当日收益，计算为 `sum(weight_i * sleeve_daily_return_i,t)`。 |
| `portfolio_nav` | 从 `initial_nav=1.0` 开始，对 `1 + portfolio_daily_return` 连乘得到的净值。 |
| `portfolio_option_leg_return` | 各 sleeve 期权腿日收益按组合权重加总。ETF BuyHold 的期权腿为 0。 |

### 1.4 指标定义

| 指标 | 定义与解释 |
| --- | --- |
| `annualized_return_cagr` | 年化复合收益率，来自日频 NAV 起点和终点。 |
| `arithmetic_annualized_return` | 日收益均值乘以年化交易日数的算术年化收益。 |
| `annualized_volatility` | 日收益标准差年化。 |
| `sharpe_daily_mean` | 以日均收益和日波动计算的 Sharpe，再年化；当前所有 Step B/C/D 汇总沿用冻结指标口径。 |
| `max_drawdown` / `MDD` | 净值从历史高点到低点的最大回撤幅度，报告中以正数表示回撤大小。 |
| `calmar_ratio` | CAGR / MDD，描述单位回撤对应的年化收益。 |
| `sortino_ratio` | 只惩罚下行波动的风险调整收益指标。 |
| `monthly_win_rate` | 月度收益为正的月份比例。 |
| `option_leg_annualized_pnl_contribution` | 期权腿日收益序列年化后的 PnL 贡献。正值表示卖 call 净贡献为正，负值表示期权腿拖累。 |
| `premium_capture_ratio_agg` | 聚合口径下，最终保留的权利金相对收取权利金的比例。 |
| `payoff_burden_agg` | 聚合口径下，期权赔付/回补损失相对权利金收入的负担。 |
| `p99_short_call_mtm_loss` | 空头 call 按市值计价损失的 99 分位，用于衡量尾部挤压。 |
| `assignment_rate` | 到期或路径中接近被行权/实质赔付的周期比例。 |

### 1.5 Step B+ 与 Step C 诊断定义

| 概念 | 定义 |
| --- | --- |
| `D_star` | 目标 MDD 预算，例如 `D20` 表示最大回撤约束目标为 20%。 |
| `default constraint` | Step B+ 主约束组，通常为单资产权重下限 5%、上限 70%。 |
| `relaxed constraint` | 更宽松的权重边界，用于检查最优解是否变成杠铃式或过度集中。 |
| `frontier_status` | 某个 `D_star` 下是否找到满足回撤约束的候选。 |
| `event exclusion` | 剔除极端事件窗口后重算指标，检查候选是否依赖少数事件。 |
| `rolling stability` | 在滚动窗口中重复计算 Sharpe/MDD，检查候选跨时间是否稳定。 |
| `cost sensitivity` | 对期权腿或再平衡换手施加成本压力，检查结论是否脆弱。 |
| `weight interpretability` | 权重是否仍有经济解释，而不是机械压到边界。 |

### 1.6 Step D 动态权重定义

| 概念 | 定义 |
| --- | --- |
| `dynamic sleeve weighting` | 只调整固定 sleeve 之间的资金权重 `w_i,t`，不改变期权参数。 |
| `lookback` | 计算波动率/协方差使用的历史窗口，本次只允许 `126` 和 `252`。 |
| `signal_date` | 月末信号日，用截至该日的数据计算下一期权重。 |
| `effective_date` | 下一交易日，动态权重从这一天开始生效。 |
| `anchored_inverse_vol` | `anchor_weight / trailing_volatility` 后归一化，保留原静态研究主线。 |
| `pure_inverse_vol` | `1 / trailing_volatility` 后归一化，不保留 anchor 倾向。 |
| `rolling_min_variance` | 仅用滚动协方差最小化组合方差，不使用预期收益。 |
| `turnover` | 本次使用 `0.5 * sum(abs(w_new - w_previous_target))` 的目标权重变化近似。 |
| `rebalance_cost_bps` | 再平衡换手成本压力，0、5、10、20 bps，只在再平衡生效日扣减。 |

## 2. 工程与输出边界

ver3 的工程定位已经独立出来：源码入口在 `ver3/`，真实输出在根目录 `outputs/`，`ver3/outputs/` 只放轻量索引。这样做的原因是：实验 CSV、PNG、报告都可再生成，不适合塞进源码阅读目录；而人工审查需要清楚知道入口脚本、源码模块和输出证据在哪里。

{md_table(pd.DataFrame([
        {"位置": "ver3/", "用途": "当前主项目入口，放 README、SOURCE_MAP、RUNBOOK、源码和轻量索引"},
        {"位置": "ver3/src/covered_call_mini_ver3/", "用途": "ver3 模块化源码，Step B/B+/C/D 均在这里"},
        {"位置": "ver3/scripts/python/", "用途": "ver3 主 runner"},
        {"位置": "outputs/ver3_0_*", "用途": "真实实验输出、CSV、图表和报告"},
        {"位置": "ver3/outputs/", "用途": "轻量索引，不放大型 CSV/PNG"},
        {"位置": "src/metrics/", "用途": "冻结指标依赖，供 ver3 只读复用"},
        {"位置": "ver2_downside_protection/", "用途": "历史 engine 和证据，不作为 ver3 主线修改对象"},
    ]))}

当前已完成输出目录：

{md_table(output_inventory())}

## 3. 全流程工作流

1. Step A main：对 `510300`、`510500`、`159915` 做单 ETF sleeve 画像，产出可供组合层读取的 return panel。
2. Step A Extension：补充 `510050` 和 `588000`。其中 `510050` 进入 Universe B；`588000` 只作为 short-sample extension，不进入主线长样本。
3. Sleeve Diagnostics Pack：把单 ETF 报告集中到阅读包，方便人工审查 sleeve 是否合理。
4. Step B：用固定权重组合比较 Universe A/B，并与 pure ETF 基准比较。
5. Step B+：在 selected sleeve 上做静态权重网格，按 MDD 预算 `D_star` 选择 Sharpe 较优组合。
6. Step C：围绕代表性候选做稳健性诊断，不新增期权参数，不再打开大网格。
7. Step D：在固定 sleeve 上加一层月度动态权重研究，只动态调整资金权重，不改变期权 sleeve。

组合层共同公式：

```text
portfolio_daily_return_t = sum_i(weight_i,t * sleeve_daily_return_i,t)
portfolio_nav_t = portfolio_nav_{{t-1}} * (1 + portfolio_daily_return_t)
```

Step B 和 Step B+ 的 `weight_i` 是固定权重或静态网格权重；Step D 的 `weight_i,t` 是月度更新、日度持有的动态权重。

## 4. 样本与主线约束

主线长样本：

{md_table(pd.DataFrame([{"开始日期": "2022-09-30", "结束日期": "2026-05-27", "交易日数": 881, "初始 NAV": 1.0}]))}

主线约束：

- 不让 `588000` 拉短主线长样本；它只作为 short-sample extension。
- 不把 `Q100`、`ATM_Q100`、`TP80`、`TouchK` 升为主线组合 sleeve。
- Step C 之后不重新打开期权参数网格。
- Step D 不做收益预测，不做 full Markowitz expected-return optimization，不用波动率决定是否卖 call。
- 所有面向阅读的新增报告默认中文；CSV 字段名保留英文稳定标识。

## 5. Step A：单 ETF sleeve 画像

Step A 的职责是回答：每个 ETF 自己适合哪一种 sleeve？哪些 sleeve 可以进入组合层？哪些只能当压力测试或附录诊断？

本节按 ETF 分开写，每个 ETF 都放入 Sharpe 参数曲面图，并只保留 `BuyHold` 与 Sharpe 表现最好的 4 条参数格点。曲面图来自 Sleeve Diagnostics Pack；插值只用于读图，表格只使用真实回测格点。

{etf_diagnostic_sections(data)}

## 6. Step B：固定权重 Universe 组合比较

Step B 的问题是：如果把 Step A 选出来的 sleeve 组成固定权重组合，相对裸持 ETF 组合有没有改善？

Universe 定义：

{md_table(pd.DataFrame([
        {"Universe": "A", "组合含义": "510300 covered-call + 510500 ETF BuyHold + 159915 covered-call", "定位": "成长分散化"},
        {"Universe": "B", "组合含义": "510300 covered-call + 510050 covered-call + 159915 covered-call", "定位": "防御收入"},
    ]))}

固定权重组合结果：

{md_table(select_cols(data["stepB_summary"], [
        "portfolio_name", "universe_short", "portfolio_type", "weight_scheme", "annualized_return_cagr",
        "sharpe_daily_mean", "annualized_volatility", "max_drawdown", "option_leg_annualized_pnl_contribution", "final_nav"
    ]), pct_cols=["annualized_return_cagr", "annualized_volatility", "max_drawdown", "option_leg_annualized_pnl_contribution"], num_cols=["sharpe_daily_mean", "final_nav"])}

Selected 相对 pure ETF 的改善：

{md_table(select_cols(data["stepB_selected_vs_pure"], [
        "selected_portfolio", "matched_baseline", "weight_scheme", "excess_cagr_vs_baseline",
        "delta_sharpe_vs_baseline", "delta_volatility_vs_baseline", "delta_mdd_vs_baseline",
        "option_leg_annualized_pnl_contribution", "interpretation_hint"
    ]), pct_cols=["excess_cagr_vs_baseline", "delta_volatility_vs_baseline", "delta_mdd_vs_baseline", "option_leg_annualized_pnl_contribution"], num_cols=["delta_sharpe_vs_baseline"])}

Step B 的结论是：Selected 组合相对 pure ETF 组合普遍改善 Sharpe 和 MDD，说明 covered-call sleeve 在组合层有风险控制价值。Universe B 的防御收入特征更清楚。

## 7. Step B+：MDD 约束 Sharpe 前沿

Step B+ 的问题是：在 selected sleeve 固定以后，如果给一个最大回撤预算 `D_star`，静态权重应该怎么配？

默认约束下的 frontier：

{md_table(select_cols(data["stepB_plus_default"], [
        "portfolio_name", "universe_short", "constraint_set", "D_star", "frontier_status", "feasible",
        "sharpe_daily_mean", "annualized_return_cagr", "annualized_volatility", "max_drawdown",
        "weight_510300", "weight_510500", "weight_510050", "weight_159915"
    ]), pct_cols=["D_star", "annualized_return_cagr", "annualized_volatility", "max_drawdown", "weight_510300", "weight_510500", "weight_510050", "weight_159915"], num_cols=["sharpe_daily_mean"])}

与固定权重基准比较：

{md_table(select_cols(data["stepB_plus_vs_fixed"], [
        "portfolio_name", "universe_short", "constraint_set", "D_star", "matched_fixed_weight_baseline",
        "annualized_return_cagr", "sharpe_daily_mean", "max_drawdown", "delta_cagr_vs_fixed_baseline",
        "delta_sharpe_vs_fixed_baseline", "delta_mdd_vs_fixed_baseline"
    ]), pct_cols=["D_star", "annualized_return_cagr", "max_drawdown", "delta_cagr_vs_fixed_baseline", "delta_mdd_vs_fixed_baseline"], num_cols=["sharpe_daily_mean", "delta_sharpe_vs_fixed_baseline"])}

Step B+ 的关键观察：随着 `D_star` 放宽，收益和 Sharpe 通常上升，但 MDD 也上升；`B_default_D20` 是一个较好的中间点，既贴近 20% MDD 预算，又保持了 Universe B 的大盘备兑收入解释。

## 8. Step C：稳健性与稳定性诊断

Step C 不是新优化器，而是围绕 Step B+ 的代表性候选做诊断。候选包括 `B_default_D18`、`B_default_D20`、`B_default_D22` 和 `A_default_D25`。

全样本结果：

{md_table(select_cols(data["stepC_summary"], [
        "portfolio_name", "role", "sample_start", "sample_end", "n_trading_days", "annualized_return_cagr",
        "sharpe_daily_mean", "annualized_volatility", "max_drawdown", "option_leg_annualized_pnl_contribution", "final_nav"
    ]), pct_cols=["annualized_return_cagr", "annualized_volatility", "max_drawdown", "option_leg_annualized_pnl_contribution"], num_cols=["sharpe_daily_mean", "final_nav"])}

稳定性评分：

{md_table(select_cols(data["stepC_scorecard"], [
        "portfolio_name", "role", "full_sample_sharpe", "full_sample_mdd", "event_exclusion_sharpe_stability",
        "rolling_sharpe_stability", "cost_sensitivity_score", "option_leg_robustness_score",
        "weight_interpretability_score", "overall_stability_score", "overall_stability_label"
    ]), pct_cols=["full_sample_mdd", "event_exclusion_sharpe_stability", "rolling_sharpe_stability", "cost_sensitivity_score", "option_leg_robustness_score", "weight_interpretability_score", "overall_stability_score"], num_cols=["full_sample_sharpe"])}

推荐表：

{md_table(select_cols(data["stepC_recommended"], [
        "portfolio_name", "recommendation_role", "overall_stability_label", "overall_stability_score",
        "full_sample_sharpe", "full_sample_mdd", "matched_baseline_for_context",
        "delta_sharpe_vs_context_baseline", "reason", "next_stage_suggestion"
    ]), pct_cols=["overall_stability_score", "full_sample_mdd"], num_cols=["full_sample_sharpe", "delta_sharpe_vs_context_baseline"])}

Step C 结论：`B_default_D20` 是主线候选；`B_default_D18` 是更严格防御候选；`B_default_D22` 是接受更高 MDD 换取收益弹性的对照；`A_default_D25` 是成长弹性对照。

## 9. Step D：波动率控制的动态 sleeve 权重

Step D 的问题是：在 Step A/B/C 固定出来的 sleeve 上，只动态调整 sleeve 之间的资金权重，能否改善风险收益？

本版报告暂时略去 Step D 的数据展示，不列出动态策略指标表、静态基准比较表、权重路径图、触边统计、换手统计和推荐观察表；这里只保留实验进展、方法论和解释边界。

### 9.1 实验进展

Step D 已完成第一轮动态权重实验框架：输入端读取 Step A/Step B/Step C 已经冻结的 sleeve 与组合候选，组合端只改变不同 sleeve 之间的资金分配，输出端生成动态权重路径、动态组合日收益/NAV、换手、成本敏感性、静态基准对照和校验表。该层已经具备可复算的工程闭环，也已经接入 ver3 的输出索引和 dashboard 数据准备流程。

但从研究叙事上，Step D 仍处于“可选动态资金管理层”，而不是正式主线替代层。当前报告主线仍以 Step C 选出的 `B_default_D20` 为核心展示候选；Step D 只回答一个后续问题：在不重新选择期权、不改变 sleeve 语义的前提下，月度动态分配是否能提供额外的风险控制或组合解释价值。

### 9.2 方法论

Step D 的基本单位仍是固定 sleeve，而不是重新生成期权交易。所有 ETF、DTE、delta、moneyness、覆盖率、TP/Touch-K 等期权参数都沿用 Step A 至 Step C 中已经确定的候选，不在 Step D 中重新搜索。动态权重只作用于组合层的资金权重，即把静态组合中的固定权重扩展为按月更新、按日持有的权重路径。

权重信号采用滞后机制：月末作为 signal date，用截至该日的历史收益窗口计算下一期目标权重；下一交易日作为 effective date，新的目标权重开始生效。这样可以避免使用未来信息，也让 Step D 的路径能够与真实组合再平衡节奏对应。

本轮只使用三类不含收益预测的权重规则。第一类是 anchored inverse volatility，即在静态基准权重的基础上按历史波动率倒数调整，保留原组合的研究主线倾向；第二类是 pure inverse volatility，即完全按历史波动率倒数分配，不保留静态 anchor；第三类是 rolling minimum variance，即只使用滚动协方差最小化组合方差，不引入预期收益。三类方法的共同边界是：不预测收益、不做 full Markowitz expected-return optimization，也不用波动率信号决定是否卖出 call。

历史窗口只采用 126 日和 252 日两个 lookback，用来分别观察半年与一年尺度下的风险估计差异。权重约束仍保留上下界，避免动态策略机械地把单一资产压到极端；再平衡成本以 bps 形式作为敏感性压力，而不是声称精确模拟真实交易明细。

### 9.3 解释边界

Step D 的有效样本会受到 lookback 窗口约束，因此不能直接把动态策略短样本指标与 Step C 全样本指标硬比。合理的读法是：在同一有效样本中比较动态策略和匹配静态基准，再观察收益、Sharpe、MDD、换手和成本敏感性之间是否形成稳定改进。

当前阶段，Step D 可以作为 dashboard 和附录中的动态权重观察层，用来展示“如果只做资金权重调整，组合路径会如何变化”。但正式主线仍应保持克制：除非后续稳健性检验能够证明动态层在不同窗口、不同成本和不同市场阶段下都能稳定改善风险收益，否则不应把 Step D 直接写成对 Step C 静态主线的替代。

Step D 结论边界：已经完成实验框架和初步研究证据，但本版完整报告暂不展示数据结果；研究叙事只把它定义为可选动态权重层和后续观察层，不改变当前以 `B_default_D20` 为核心的 Step C 主线。

## 10. 输出文件导航

| 类别 | 路径 |
| --- | --- |
| 本汇总报告 | `outputs/ver3_0_current_experiment_summary/reports/ver3_0_current_experiment_summary_report.md` |
| 汇总报告索引 | `ver3/outputs/ver3_0_current_experiment_summary_output_index.md` |
| Step C 报告 | `outputs/ver3_0_stepC_robustness_stability_diagnostics/reports/ver3_0_stepC_robustness_stability_diagnostics_report.md` |
| Step D 报告 | `outputs/ver3_0_stepD_volatility_controlled_dynamic_weighting/reports/ver3_0_stepD_volatility_controlled_dynamic_weighting_report.md` |
| Step D 权重路径 CSV | `outputs/ver3_0_stepD_volatility_controlled_dynamic_weighting/weights/ver3_0_stepD_dynamic_weight_paths.csv` |
| Step D 动态策略汇总 | `outputs/ver3_0_stepD_volatility_controlled_dynamic_weighting/summary/ver3_0_stepD_dynamic_strategy_summary.csv` |
| Step D 静态基准比较 | `outputs/ver3_0_stepD_volatility_controlled_dynamic_weighting/summary/ver3_0_stepD_comparison_vs_static_baselines.csv` |
| Step D 权重路径图 A | `outputs/ver3_0_stepD_volatility_controlled_dynamic_weighting/figures/ver3_0_stepD_dynamic_weight_paths_universeA.png` |
| Step D 权重路径图 B | `outputs/ver3_0_stepD_volatility_controlled_dynamic_weighting/figures/ver3_0_stepD_dynamic_weight_paths_universeB.png` |

## 11. 当前研究判断

1. 单 ETF 层面，`510300_DTE30_D40_Q70_Hold` 和 `510050_DTE30_D40_Q70_Hold` 是更像“正 carry + 降回撤”的大盘备兑 sleeve。
2. `159915_DTE30_OTM5up_Q50_Hold` 的期权腿不一定正，但它能在组合中提供成长资产的防御 overlay。
3. `510500` 当前更适合保留 pure ETF，而不是强行备兑。
4. `588000` 成长弹性强，但样本短，且备兑会显著牺牲上涨，因此只做 extension。
5. Step B 证明 selected sleeve 组合相对 pure ETF 基准普遍改善 Sharpe 和 MDD。
6. Step B+ 把主线推到 MDD 约束下的 `B_default_D20` 附近。
7. Step C 证明 `B_default_D20` 有较好的综合稳定性，适合作为当前主报告候选。
8. Step D 已经提供动态权重研究证据，但没有足够理由替代 `B_default_D20` 静态主线。
9. dashboard 可以展示 Step D 动态权重路径，但研究叙事仍应把动态层写成“可选改进/观察层”。

## 12. 后续建议

- 把 Step D 的权重路径图和动态策略比较接入 ver3 dashboard，而不是单独散落在 PNG。
- 如果继续做 Step E，应优先做样本外/滚动训练验证，而不是重新扩大期权参数网格。
- 对外部展示时，主线写 `B_default_D20`，附录展示 `B_default_D18`、`B_default_D22`、`A_default_D25` 和 Step D 动态层。
- 所有新增报告继续中文输出；CSV 字段名继续保留英文稳定标识。
"""


def build_index(data: dict[str, pd.DataFrame]) -> str:
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    primary = data["stepC_recommended"].iloc[0]
    stepd_top = data["stepD_recommended"].iloc[0]
    return f"""# ver3.0 当前实验汇总报告索引

生成时间：{generated_at}

真实报告位置：

```text
{REPORT_PATH}
```

本索引只用于 ver3 工作区导航。真实 Markdown 报告保存在根目录 `outputs/` 下，符合 ver3 工程约束。

核心结论：

- 当前主候选：`{primary["portfolio_name"]}`
- 主候选定位：`{primary["recommendation_role"]}`
- 稳健性标签：`{primary["overall_stability_label"]}`
- Step D 已纳入总报告：是
- Step D 当前研究排序第一：`{stepd_top["strategy_name"]}`
- Step D 解释：动态权重研究层，暂不替代 Step C 静态主线

关键文件：

- Step C 推荐表：`outputs/ver3_0_stepC_robustness_stability_diagnostics/summary/ver3_0_stepC_recommended_candidate_table.csv`
- Step D 推荐表：`outputs/ver3_0_stepD_volatility_controlled_dynamic_weighting/summary/ver3_0_stepD_recommendation_table.csv`
- Step D 权重路径：`outputs/ver3_0_stepD_volatility_controlled_dynamic_weighting/weights/ver3_0_stepD_dynamic_weight_paths.csv`
- Step D 权重路径图：`outputs/ver3_0_stepD_volatility_controlled_dynamic_weighting/figures/`
"""


def read_csv(rel_path: str) -> pd.DataFrame:
    path = ROOT / rel_path
    if not path.exists():
        raise FileNotFoundError(path)
    return pd.read_csv(path)


def build_current_primary_recommendations(*frames: pd.DataFrame) -> pd.DataFrame:
    combined = pd.concat(frames, ignore_index=True, sort=False)
    if combined.empty:
        return combined
    status_rank = {
        "primary_for_portfolio_layer": 0,
        "primary_for_short_sample_extension": 0,
        "backup_for_portfolio_layer": 1,
        "backup_defensive_overlay": 1,
        "diagnostic_only": 2,
        "rejected": 3,
    }
    out = combined.copy()
    out["_status_rank"] = out["recommendation_status"].map(status_rank).fillna(9)
    out["_sharpe_rank"] = pd.to_numeric(out.get("sharpe_daily_mean"), errors="coerce").fillna(-999.0)
    out = (
        out.sort_values(["etf_code", "_status_rank", "_sharpe_rank"], ascending=[True, True, False])
        .drop_duplicates(subset=["etf_code"], keep="first")
        .drop(columns=["_status_rank", "_sharpe_rank"])
        .reset_index(drop=True)
    )
    return out


def build_refined_surface_metadata(surface_grid: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "etf_code",
        "available_moneyness_rules",
        "coverage_grid",
        "n_surface_points",
        "sample_start",
        "sample_end",
    ]
    if surface_grid.empty:
        return pd.DataFrame(columns=cols)
    surface = surface_grid.copy()
    if "parameter_grid_role" in surface.columns:
        surface = surface[surface["parameter_grid_role"].astype(str).eq("surface")].copy()
    rows: list[dict[str, object]] = []
    for etf_code, group in surface.groupby("etf_code", sort=True):
        moneyness = (
            group[["moneyness_label", "target_moneyness"]]
            .drop_duplicates()
            .sort_values("target_moneyness", na_position="first")
        )
        coverage = (
            group[["coverage_label", "coverage"]]
            .drop_duplicates()
            .sort_values("coverage", na_position="first")
        )
        rows.append({
            "etf_code": str(etf_code),
            "available_moneyness_rules": ", ".join(moneyness["moneyness_label"].astype(str).tolist()),
            "coverage_grid": ", ".join(coverage["coverage_label"].astype(str).tolist()),
            "n_surface_points": int(len(group)),
            "sample_start": group["sample_start"].min(),
            "sample_end": group["sample_end"].max(),
        })
    return pd.DataFrame(rows, columns=cols)


def output_inventory() -> pd.DataFrame:
    rows = [
        ("Step A main", "outputs/ver3_0_stepA_single_etf_sleeves/"),
        ("Step A 510050 extension", "outputs/ver3_0_stepA_extension_510050_sleeve_clarification/"),
        ("Step A 588000 extension", "outputs/ver3_0_stepA_extension_588000_sleeve_clarification/"),
        ("Step A refined moneyness surface", "outputs/ver3_0_stepA_moneyness_refined_daily_mtm_surface/"),
        ("Step B fixed-weight universe", "outputs/ver3_0_stepB_fixed_weight_universe_comparison/"),
        ("Step B+ MDD-constrained Sharpe frontier", "outputs/ver3_0_stepB_plus_mdd_constrained_sharpe_frontier/"),
        ("Step C robustness diagnostics", "outputs/ver3_0_stepC_robustness_stability_diagnostics/"),
        ("Step D dynamic sleeve weighting", "outputs/ver3_0_stepD_volatility_controlled_dynamic_weighting/"),
        ("Dashboard data", "outputs/ver3_0_dashboard_data/"),
        ("Current experiment summary", "outputs/ver3_0_current_experiment_summary/"),
    ]
    return pd.DataFrame(rows, columns=["Step", "输出目录"])


def etf_diagnostic_sections(data: dict[str, pd.DataFrame]) -> str:
    etf_order = ["510300", "510050", "510500", "159915", "588000"]
    sections: list[str] = []
    for idx, etf_code in enumerate(etf_order, start=1):
        sections.append(etf_diagnostic_section(data, etf_code, idx))
    return "\n\n".join(sections)


def etf_diagnostic_section(data: dict[str, pd.DataFrame], etf_code: str, idx: int) -> str:
    meta = lookup_etf_row(data["sleeve_surface_metadata"], etf_code)
    primary = lookup_etf_row(data["sleeve_diag_primary"], etf_code)
    figure = surface_figure_markdown(data["sleeve_surface_figures"], etf_code)
    table_df = best_parameter_rows(data, etf_code)
    note = etf_diagnosis_note(etf_code)
    primary_text = "暂无集中推荐记录。"
    if primary is not None:
        primary_text = (
            f"当前推荐/定位：`{primary['sleeve_name']}`，分类为“{label_classification(primary['classification'])}”，"
            f"状态为“{label_recommendation_status(primary['recommendation_status'])}”。"
            f"理由：{translate_diagnostic_text(primary['reason'])}"
        )
        caveat = translate_diagnostic_text(primary.get("caveat", ""))
        if caveat:
            primary_text += f" 注意事项：{caveat}"

    meta_text = "暂无参数曲面元数据。"
    if meta is not None:
        meta_text = (
            f"参数曲面覆盖 `{meta['available_moneyness_rules']}`，覆盖率网格为 `{meta['coverage_grid']}`，"
            f"真实格点数 `{int(meta['n_surface_points'])}`，样本 `{meta['sample_start']}` 至 `{meta['sample_end']}`。"
        )

    return f"""### 5.{idx} {etf_code} 单 ETF 诊断

{note}

{primary_text}

{meta_text}

{figure}

表格口径：第一行保留 `BuyHold`；其余只保留 `sharpe_daily_mean` 最高的 4 条真实参数格点。排名不等于自动纳入主线，尤其是 Q100/ATM 行仍需结合主线约束和样本解释。

{md_table(table_df, pct_cols=["CAGR", "MDD", "年化波动", "期权腿年化贡献"], num_cols=["Sharpe"])}
"""


def lookup_etf_row(df: pd.DataFrame, etf_code: str) -> Optional[pd.Series]:
    subset = df[df["etf_code"].astype(str).eq(str(etf_code))]
    if subset.empty:
        return None
    return subset.iloc[0]


def surface_figure_markdown(figures: pd.DataFrame, etf_code: str) -> str:
    subset = figures[
        figures["etf_code"].astype(str).eq(str(etf_code))
        & figures["metric_name"].astype(str).eq("sharpe_daily_mean")
    ]
    if subset.empty:
        return "_未找到 Sharpe 参数曲面图。_"
    if "figure_kind" in subset.columns:
        preferred = subset[subset["figure_kind"].astype(str).eq("surface_3d")]
        if not preferred.empty:
            subset = preferred
    path_col = "path" if "path" in subset.columns else "figure_path"
    figure_path = str(subset.iloc[0][path_col]).replace("\\", "/")
    if figure_path.startswith("outputs/"):
        rel_path = f"../../{figure_path[len('outputs/'):]}"
    else:
        rel_path = f"../../ver3_0_stepA_moneyness_refined_daily_mtm_surface/{figure_path}"
    return f"![{etf_code} Sharpe 参数曲面]({rel_path})"


def best_parameter_rows(data: dict[str, pd.DataFrame], etf_code: str) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    buyhold = buyhold_summary_row(data, etf_code)
    if buyhold is not None:
        rows.append({
            "行类型": "BuyHold",
            "策略": buyhold["sleeve_name"],
            "规则": "BuyHold",
            "覆盖率": "0%",
            "样本": sample_label(buyhold),
            "CAGR": buyhold.get("annualized_return_cagr"),
            "Sharpe": buyhold.get("sharpe_daily_mean"),
            "MDD": buyhold.get("max_drawdown"),
            "年化波动": buyhold.get("annualized_volatility"),
            "期权腿年化贡献": buyhold.get("option_leg_annualized_pnl_contribution"),
        })

    grid = data["sleeve_surface_grid"]
    grid = grid[grid["etf_code"].astype(str).eq(str(etf_code))].copy()
    if "parameter_grid_role" in grid.columns:
        grid = grid[grid["parameter_grid_role"].astype(str).eq("surface")].copy()
    top = (
        grid.dropna(subset=["sharpe_daily_mean"])
        .sort_values("sharpe_daily_mean", ascending=False)
        .head(4)
    )
    for _, row in top.iterrows():
        rows.append({
            "行类型": "Sharpe前四",
            "策略": row["sleeve_name"],
            "规则": row["moneyness_label"],
            "覆盖率": row["coverage_label"],
            "样本": sample_label(row),
            "CAGR": row.get("annualized_return_cagr"),
            "Sharpe": row.get("sharpe_daily_mean"),
            "MDD": row.get("max_drawdown"),
            "年化波动": row.get("annualized_volatility"),
            "期权腿年化贡献": row.get("option_leg_annualized_pnl_contribution"),
        })
    return pd.DataFrame(rows)


def label_classification(value: object) -> str:
    labels = {
        "Positive Carry Overlay": "正 carry 备兑覆盖",
        "Defensive Overlay": "防御覆盖",
        "Pure ETF Preferred": "优先裸持 ETF",
        "Growth Extension Sleeve": "成长扩展样本",
        "Stress Test Only": "仅压力测试",
    }
    return labels.get(str(value), fmt_cell(value))


def label_recommendation_status(value: object) -> str:
    labels = {
        "primary_for_portfolio_layer": "组合层主候选",
        "backup_for_portfolio_layer": "组合层备选",
        "diagnostic_only": "仅诊断",
        "primary_for_short_sample_extension": "短样本扩展主候选",
    }
    return labels.get(str(value), fmt_cell(value))


def translate_diagnostic_text(value: object) -> str:
    text = fmt_cell(value)
    translations = {
        "ETF-only baseline for comparison.": "ETF 裸持基准，用于与备兑路径比较。",
        "No option leg.": "无期权腿。",
        "Net option leg is positive while Sharpe and drawdown are at least as good as BuyHold.": "期权腿为正，且 Sharpe 与回撤至少不弱于 BuyHold。",
        "Still sample-limited and not an arbitrage claim.": "样本仍有限，不应解释为套利机会。",
        "Net option leg is positive while Sharpe improves and max drawdown is lower than BuyHold.": "期权腿为正，同时 Sharpe 改善，最大回撤低于 BuyHold。",
        "This is structural risk compensation with path and sample risk.": "这是结构性风险补偿，但仍有路径风险和样本风险。",
        "Net option leg is not positive, but drawdown improves enough with similar Sharpe.": "期权腿不是正贡献，但在 Sharpe 接近的同时回撤改善较明显。",
        "Use as risk-control sleeve, not income enhancement.": "作为风险控制型 sleeve 使用，不作为收入增强型 sleeve。",
        "Pure ETF path best preserves 588000's tech-growth upside and has the strongest Sharpe in this sample.": "纯 ETF 路径最能保留 588000 的科创成长上行，且在当前样本中 Sharpe 最高。",
        "Use only in short-sample extension universes.": "仅用于短样本扩展 universe。",
    }
    return translations.get(text, text)


def buyhold_summary_row(data: dict[str, pd.DataFrame], etf_code: str) -> Optional[pd.Series]:
    surface = data.get("sleeve_surface_grid")
    if surface is not None and not surface.empty and "parameter_grid_role" in surface.columns:
        subset = surface[
            surface["etf_code"].astype(str).eq(str(etf_code))
            & surface["parameter_grid_role"].astype(str).eq("buyhold")
        ].copy()
        if not subset.empty:
            return subset.iloc[0]

    summary = pd.concat([
        data["stepA_main_summary"],
        data["stepA_510050_summary"],
        data["stepA_588000_summary"],
    ], ignore_index=True, sort=False)
    subset = summary[
        summary["etf_code"].astype(str).eq(str(etf_code))
        & summary["sleeve_name"].astype(str).str.endswith("ETF_BuyHold", na=False)
    ].copy()
    if subset.empty:
        return None
    if "sample_scope" in subset.columns:
        preferred = subset[subset["sample_scope"].astype(str).isin(["common_portfolio_sample", "short_sample_extension"])]
        if not preferred.empty:
            subset = preferred
    return subset.iloc[0]


def sample_label(row: pd.Series) -> str:
    start = fmt_cell(row.get("sample_start", ""))
    end = fmt_cell(row.get("sample_end", ""))
    if start and end:
        return f"{start} 至 {end}"
    return ""


def etf_diagnosis_note(etf_code: str) -> str:
    notes = {
        "510300": "定位：主线大盘核心资产。它是 Step B/C/D 中最重要的底层 sleeve 之一，诊断重点是大盘备兑是否能在不明显牺牲收益的情况下降低回撤。",
        "510050": "定位：大盘偏蓝筹/偏防御补充。它通过 Step A extension 进入 Universe B，诊断重点是能否提供更稳定的正 carry 与更低 MDD。",
        "510500": "定位：中盘分散化资产。当前更偏向保留 ETF BuyHold，诊断重点是 covered call 是否真的改善风险收益，而不是机械降低波动。",
        "159915": "定位：成长弹性资产。当前主线使用轻覆盖 defensive overlay，诊断重点是用较低覆盖率降低回撤，同时尽量保留成长上行。",
        "588000": "定位：科创成长扩展样本。样本从 2023-06-30 开始，短于主线长样本，因此只做 extension 诊断，不进入 Step B/C/D 主线。",
    }
    return notes.get(etf_code, "")


def matched_stepd_comparison(df: pd.DataFrame) -> pd.DataFrame:
    is_a = df["universe_short"].eq("A") & df["baseline_portfolio_name"].eq("A_Selected_50_30_20")
    is_b = df["universe_short"].eq("B") & df["baseline_portfolio_name"].eq("B_default_D20")
    return df[is_a | is_b].sort_values(["universe_short", "method", "lookback"]).reset_index(drop=True)


def validation_text(df: pd.DataFrame) -> str:
    passed = int(df["passed"].astype(bool).sum())
    total = int(len(df))
    return f"{passed}/{total} passed"


def select_cols(df: pd.DataFrame, cols: Iterable[str]) -> pd.DataFrame:
    return df[[col for col in cols if col in df.columns]].copy()


def md_table(df: pd.DataFrame, pct_cols: list[str] | None = None, num_cols: list[str] | None = None) -> str:
    if df.empty:
        return "_empty_"
    out = df.copy()
    pct = set(pct_cols or [])
    num = set(num_cols or [])
    for col in out.columns:
        if col in pct:
            out[col] = out[col].map(fmt_pct)
        elif col in num:
            out[col] = out[col].map(fmt_num)
        else:
            out[col] = out[col].map(fmt_cell)
    return out.to_markdown(index=False)


def fmt_cell(value: object) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def fmt_pct(value: object) -> str:
    try:
        if pd.isna(value):
            return ""
        return f"{float(value):.2%}"
    except (TypeError, ValueError):
        return ""


def fmt_num(value: object) -> str:
    try:
        if pd.isna(value):
            return ""
        return f"{float(value):.3f}"
    except (TypeError, ValueError):
        return ""


if __name__ == "__main__":
    sys.exit(main())
