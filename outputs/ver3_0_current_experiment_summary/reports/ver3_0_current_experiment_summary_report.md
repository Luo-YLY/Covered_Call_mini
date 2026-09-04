# covered_call_mini ver3 当前实验汇总报告

生成时间：2026-07-08 10:27:24
项目入口：`ver3/`
报告范围：ver3.0 已完成的 Step A、Step A Extension、Sleeve Diagnostics Pack、Step B、Step B+、Step C、Step D。
报告定位：这是当前研究总报告，目的是把每个定义、样本口径、实验步骤、输出位置、结果解释和当前结论放在同一份 Markdown 中，方便人工审查和后续写作。

## 0. 结论先行

当前主线仍建议以 Step C 的 `B_default_D20` 作为核心展示候选，而不是直接用 Step D 动态权重替代。

```text
B_default_D20
= 510300 DTE30_D40_Q70_Hold 70%
+ 510050 DTE30_D40_Q70_Hold 15%
+ 159915 DTE30_OTM5up_Q50_Hold 15%
```

选择它的原因是：它不是单项收益最高，而是在共同长样本中保留了较好的 Sharpe、较可控的 MDD、清晰的大盘备兑收入逻辑和较高的稳定性评分。

| 主候选        | 样本开始   | 样本结束   |   交易日数 | CAGR   |   Sharpe | MDD    | 期权腿年化贡献   | 稳定性评分   | 稳定性标签       |
|:--------------|:-----------|:-----------|-----------:|:-------|---------:|:-------|:-----------------|:-------------|:-----------------|
| B_default_D20 | 2022-09-30 | 2026-05-27 |        881 | 9.30%  |    0.717 | 19.99% | -0.70%           | 56.60%       | Medium Stability |

Step D 已经完成第一轮实验建设，但在本版完整报告中暂不展示动态策略指标、权重路径、触边统计或换手数据。它的定位仍是“动态权重研究层”：在 Step A/B/C 已固定的 sleeve 之上，观察月度资金权重调整是否有研究价值，而不是直接替代 Step C 的静态主线结论。

校验状态：Step C `23/23 passed`；Step D `37/37 passed`。

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

| 位置                             | 用途                                                           |
|:---------------------------------|:---------------------------------------------------------------|
| ver3/                            | 当前主项目入口，放 README、SOURCE_MAP、RUNBOOK、源码和轻量索引 |
| ver3/src/covered_call_mini_ver3/ | ver3 模块化源码，Step B/B+/C/D 均在这里                        |
| ver3/scripts/python/             | ver3 主 runner                                                 |
| outputs/ver3_0_*                 | 真实实验输出、CSV、图表和报告                                  |
| ver3/outputs/                    | 轻量索引，不放大型 CSV/PNG                                     |
| src/metrics/                     | 冻结指标依赖，供 ver3 只读复用                                 |
| ver2_downside_protection/        | 历史 engine 和证据，不作为 ver3 主线修改对象                   |

当前已完成输出目录：

| Step                                    | 输出目录                                                      |
|:----------------------------------------|:--------------------------------------------------------------|
| Step A main                             | outputs/ver3_0_stepA_single_etf_sleeves/                      |
| Step A 510050 extension                 | outputs/ver3_0_stepA_extension_510050_sleeve_clarification/   |
| Step A 588000 extension                 | outputs/ver3_0_stepA_extension_588000_sleeve_clarification/   |
| Step A refined moneyness surface        | outputs/ver3_0_stepA_moneyness_refined_daily_mtm_surface/     |
| Step B fixed-weight universe            | outputs/ver3_0_stepB_fixed_weight_universe_comparison/        |
| Step B+ MDD-constrained Sharpe frontier | outputs/ver3_0_stepB_plus_mdd_constrained_sharpe_frontier/    |
| Step C robustness diagnostics           | outputs/ver3_0_stepC_robustness_stability_diagnostics/        |
| Step D dynamic sleeve weighting         | outputs/ver3_0_stepD_volatility_controlled_dynamic_weighting/ |
| Dashboard data                          | outputs/ver3_0_dashboard_data/                                |
| Current experiment summary              | outputs/ver3_0_current_experiment_summary/                    |

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
portfolio_nav_t = portfolio_nav_{t-1} * (1 + portfolio_daily_return_t)
```

Step B 和 Step B+ 的 `weight_i` 是固定权重或静态网格权重；Step D 的 `weight_i,t` 是月度更新、日度持有的动态权重。

## 4. 样本与主线约束

主线长样本：

| 开始日期   | 结束日期   |   交易日数 |   初始 NAV |
|:-----------|:-----------|-----------:|-----------:|
| 2022-09-30 | 2026-05-27 |        881 |          1 |

主线约束：

- 不让 `588000` 拉短主线长样本；它只作为 short-sample extension。
- 不把 `Q100`、`ATM_Q100`、`TP80`、`TouchK` 升为主线组合 sleeve。
- Step C 之后不重新打开期权参数网格。
- Step D 不做收益预测，不做 full Markowitz expected-return optimization，不用波动率决定是否卖 call。
- 所有面向阅读的新增报告默认中文；CSV 字段名保留英文稳定标识。

## 5. Step A：单 ETF sleeve 画像

Step A 的职责是回答：每个 ETF 自己适合哪一种 sleeve？哪些 sleeve 可以进入组合层？哪些只能当压力测试或附录诊断？

本节按 ETF 分开写，每个 ETF 都放入 Sharpe 参数曲面图，并只保留 `BuyHold` 与 Sharpe 表现最好的 4 条参数格点。曲面图来自 Sleeve Diagnostics Pack；插值只用于读图，表格只使用真实回测格点。

### 5.1 510300 单 ETF 诊断

定位：主线大盘核心资产。它是 Step B/C/D 中最重要的底层 sleeve 之一，诊断重点是大盘备兑是否能在不明显牺牲收益的情况下降低回撤。

当前推荐/定位：`510300_DTE30_D40_Q70_Hold`，分类为“正 carry 备兑覆盖”，状态为“组合层主候选”。理由：期权腿为正，且 Sharpe 与回撤至少不弱于 BuyHold。 注意事项：样本仍有限，不应解释为套利机会。

参数曲面覆盖 `ATM, OTM1, OTM2, OTM3, OTM4, OTM5, OTM7`，覆盖率网格为 `Q10, Q20, Q30, Q40, Q50, Q60, Q70, Q80, Q90, Q100`，真实格点数 `70`，样本 `2022-09-30` 至 `2026-05-27`。

![510300 Sharpe 参数曲面](../../ver3_0_stepA_moneyness_refined_daily_mtm_surface/figures/510300_sharpe_daily_mean_3d_surface.png)

表格口径：第一行保留 `BuyHold`；其余只保留 `sharpe_daily_mean` 最高的 4 条真实参数格点。排名不等于自动纳入主线，尤其是 Q100/ATM 行仍需结合主线约束和样本解释。

| 行类型     | 策略                        | 规则    | 覆盖率   | 样本                     | CAGR   |   Sharpe | MDD    | 年化波动   | 期权腿年化贡献   |
|:-----------|:----------------------------|:--------|:---------|:-------------------------|:-------|---------:|:-------|:-----------|:-----------------|
| BuyHold    | 510300_ETF_BuyHold          | BuyHold | 0%       | 2022-09-30 至 2026-05-27 | 7.21%  |    0.484 | 24.19% | 17.53%     | 0.00%            |
| Sharpe前四 | 510300_DTE30_OTM4_Q100_Hold | OTM4    | Q100     | 2022-09-30 至 2026-05-27 | 9.31%  |    0.753 | 18.53% | 12.93%     | 1.25%            |
| Sharpe前四 | 510300_DTE30_OTM4_Q90_Hold  | OTM4    | Q90      | 2022-09-30 至 2026-05-27 | 9.13%  |    0.728 | 19.11% | 13.20%     | 1.12%            |
| Sharpe前四 | 510300_DTE30_OTM1_Q100_Hold | OTM1    | Q100     | 2022-09-30 至 2026-05-27 | 6.99%  |    0.709 | 12.87% | 10.29%     | -1.20%           |
| Sharpe前四 | 510300_DTE30_OTM4_Q80_Hold  | OTM4    | Q80      | 2022-09-30 至 2026-05-27 | 8.95%  |    0.701 | 19.69% | 13.53%     | 1.00%            |


### 5.2 510050 单 ETF 诊断

定位：大盘偏蓝筹/偏防御补充。它通过 Step A extension 进入 Universe B，诊断重点是能否提供更稳定的正 carry 与更低 MDD。

当前推荐/定位：`510050_DTE30_D40_Q70_Hold`，分类为“正 carry 备兑覆盖”，状态为“组合层主候选”。理由：期权腿为正，同时 Sharpe 改善，最大回撤低于 BuyHold。 注意事项：这是结构性风险补偿，但仍有路径风险和样本风险。

参数曲面覆盖 `ATM, OTM1, OTM2, OTM3, OTM4, OTM5, OTM7`，覆盖率网格为 `Q10, Q20, Q30, Q40, Q50, Q60, Q70, Q80, Q90, Q100`，真实格点数 `70`，样本 `2022-09-30` 至 `2026-05-27`。

![510050 Sharpe 参数曲面](../../ver3_0_stepA_moneyness_refined_daily_mtm_surface/figures/510050_sharpe_daily_mean_3d_surface.png)

表格口径：第一行保留 `BuyHold`；其余只保留 `sharpe_daily_mean` 最高的 4 条真实参数格点。排名不等于自动纳入主线，尤其是 Q100/ATM 行仍需结合主线约束和样本解释。

| 行类型     | 策略                        | 规则    | 覆盖率   | 样本                     | CAGR   |   Sharpe | MDD    | 年化波动   | 期权腿年化贡献   |
|:-----------|:----------------------------|:--------|:---------|:-------------------------|:-------|---------:|:-------|:-----------|:-----------------|
| BuyHold    | 510050_ETF_BuyHold          | BuyHold | 0%       | 2022-09-30 至 2026-05-27 | 3.70%  |    0.303 | 21.59% | 16.45%     | 0.00%            |
| Sharpe前四 | 510050_DTE30_ATM_Q100_Hold  | ATM     | Q100     | 2022-09-30 至 2026-05-27 | 6.69%  |    0.752 | 9.41%  | 9.18%      | 1.92%            |
| Sharpe前四 | 510050_DTE30_ATM_Q90_Hold   | ATM     | Q90      | 2022-09-30 至 2026-05-27 | 6.44%  |    0.698 | 10.29% | 9.61%      | 1.73%            |
| Sharpe前四 | 510050_DTE30_OTM2_Q100_Hold | OTM2    | Q100     | 2022-09-30 至 2026-05-27 | 7.09%  |    0.669 | 12.08% | 11.17%     | 2.49%            |
| Sharpe前四 | 510050_DTE30_ATM_Q80_Hold   | ATM     | Q80      | 2022-09-30 至 2026-05-27 | 6.19%  |    0.643 | 11.17% | 10.14%     | 1.54%            |


### 5.3 510500 单 ETF 诊断

定位：中盘分散化资产。当前更偏向保留 ETF BuyHold，诊断重点是 covered call 是否真的改善风险收益，而不是机械降低波动。

当前推荐/定位：`510500_DTE30_OTM5up_Q50_Hold`，分类为“防御覆盖”，状态为“组合层主候选”。理由：期权腿不是正贡献，但在 Sharpe 接近的同时回撤改善较明显。 注意事项：作为风险控制型 sleeve 使用，不作为收入增强型 sleeve。

参数曲面覆盖 `ATM, OTM1, OTM2, OTM3, OTM4, OTM5, OTM7`，覆盖率网格为 `Q10, Q20, Q30, Q40, Q50, Q60, Q70, Q80, Q90, Q100`，真实格点数 `70`，样本 `2022-09-30` 至 `2026-05-27`。

![510500 Sharpe 参数曲面](../../ver3_0_stepA_moneyness_refined_daily_mtm_surface/figures/510500_sharpe_daily_mean_3d_surface.png)

表格口径：第一行保留 `BuyHold`；其余只保留 `sharpe_daily_mean` 最高的 4 条真实参数格点。排名不等于自动纳入主线，尤其是 Q100/ATM 行仍需结合主线约束和样本解释。

| 行类型     | 策略                       | 规则    | 覆盖率   | 样本                     | CAGR   |   Sharpe | MDD    | 年化波动   | 期权腿年化贡献   |
|:-----------|:---------------------------|:--------|:---------|:-------------------------|:-------|---------:|:-------|:-----------|:-----------------|
| BuyHold    | 510500_ETF_BuyHold         | BuyHold | 0%       | 2022-09-30 至 2026-05-27 | 12.48% |    0.646 | 30.16% | 21.88%     | 0.00%            |
| Sharpe前四 | 510500_DTE30_OTM7_Q10_Hold | OTM7    | Q10      | 2022-09-30 至 2026-05-27 | 12.19% |    0.645 | 29.82% | 21.37%     | -0.37%           |
| Sharpe前四 | 510500_DTE30_OTM5_Q10_Hold | OTM5    | Q10      | 2022-09-30 至 2026-05-27 | 12.07% |    0.642 | 29.63% | 21.24%     | -0.50%           |
| Sharpe前四 | 510500_DTE30_OTM7_Q20_Hold | OTM7    | Q20      | 2022-09-30 至 2026-05-27 | 11.88% |    0.642 | 29.64% | 20.88%     | -0.74%           |
| Sharpe前四 | 510500_DTE30_OTM4_Q10_Hold | OTM4    | Q10      | 2022-09-30 至 2026-05-27 | 11.96% |    0.64  | 29.54% | 21.15%     | -0.61%           |


### 5.4 159915 单 ETF 诊断

定位：成长弹性资产。当前主线使用轻覆盖 defensive overlay，诊断重点是用较低覆盖率降低回撤，同时尽量保留成长上行。

当前推荐/定位：`159915_DTE30_OTM5up_Q50_Hold`，分类为“防御覆盖”，状态为“组合层主候选”。理由：期权腿不是正贡献，但在 Sharpe 接近的同时回撤改善较明显。 注意事项：作为风险控制型 sleeve 使用，不作为收入增强型 sleeve。

参数曲面覆盖 `ATM, OTM1, OTM2, OTM3, OTM4, OTM5, OTM7`，覆盖率网格为 `Q10, Q20, Q30, Q40, Q50, Q60, Q70, Q80, Q90, Q100`，真实格点数 `70`，样本 `2022-09-30` 至 `2026-05-27`。

![159915 Sharpe 参数曲面](../../ver3_0_stepA_moneyness_refined_daily_mtm_surface/figures/159915_sharpe_daily_mean_3d_surface.png)

表格口径：第一行保留 `BuyHold`；其余只保留 `sharpe_daily_mean` 最高的 4 条真实参数格点。排名不等于自动纳入主线，尤其是 Q100/ATM 行仍需结合主线约束和样本解释。

| 行类型     | 策略                       | 规则    | 覆盖率   | 样本                     | CAGR   |   Sharpe | MDD    | 年化波动   | 期权腿年化贡献   |
|:-----------|:---------------------------|:--------|:---------|:-------------------------|:-------|---------:|:-------|:-----------|:-----------------|
| BuyHold    | 159915_ETF_BuyHold         | BuyHold | 0%       | 2022-09-30 至 2026-05-27 | 18.82% |    0.7   | 40.88% | 31.63%     | 0.00%            |
| Sharpe前四 | 159915_DTE30_OTM7_Q20_Hold | OTM7    | Q20      | 2022-09-30 至 2026-05-27 | 17.50% |    0.702 | 39.86% | 28.84%     | -1.91%           |
| Sharpe前四 | 159915_DTE30_OTM7_Q10_Hold | OTM7    | Q10      | 2022-09-30 至 2026-05-27 | 18.18% |    0.702 | 40.27% | 30.21%     | -0.96%           |
| Sharpe前四 | 159915_DTE30_OTM7_Q30_Hold | OTM7    | Q30      | 2022-09-30 至 2026-05-27 | 16.79% |    0.7   | 39.51% | 27.54%     | -2.87%           |
| Sharpe前四 | 159915_DTE30_OTM5_Q10_Hold | OTM5    | Q10      | 2022-09-30 至 2026-05-27 | 18.05% |    0.7   | 40.13% | 30.08%     | -1.11%           |


### 5.5 588000 单 ETF 诊断

定位：科创成长扩展样本。样本从 2023-06-30 开始，短于主线长样本，因此只做 extension 诊断，不进入 Step B/C/D 主线。

当前推荐/定位：`588000_ETF_BuyHold`，分类为“成长扩展样本”，状态为“短样本扩展主候选”。理由：纯 ETF 路径最能保留 588000 的科创成长上行，且在当前样本中 Sharpe 最高。 注意事项：仅用于短样本扩展 universe。

参数曲面覆盖 `ATM, OTM1, OTM2, OTM3, OTM4, OTM5, OTM7`，覆盖率网格为 `Q10, Q20, Q30, Q40, Q50, Q60, Q70, Q80, Q90, Q100`，真实格点数 `70`，样本 `2023-06-30` 至 `2026-05-27`。

![588000 Sharpe 参数曲面](../../ver3_0_stepA_moneyness_refined_daily_mtm_surface/figures/588000_sharpe_daily_mean_3d_surface.png)

表格口径：第一行保留 `BuyHold`；其余只保留 `sharpe_daily_mean` 最高的 4 条真实参数格点。排名不等于自动纳入主线，尤其是 Q100/ATM 行仍需结合主线约束和样本解释。

| 行类型     | 策略                       | 规则    | 覆盖率   | 样本                     | CAGR   |   Sharpe | MDD    | 年化波动   | 期权腿年化贡献   |
|:-----------|:---------------------------|:--------|:---------|:-------------------------|:-------|---------:|:-------|:-----------|:-----------------|
| BuyHold    | 588000_ETF_BuyHold         | BuyHold | 0%       | 2023-06-30 至 2026-05-27 | 23.90% |    0.785 | 36.48% | 34.74%     | 0.00%            |
| Sharpe前四 | 588000_DTE30_OTM1_Q10_Hold | OTM1    | Q10      | 2023-06-30 至 2026-05-27 | 22.48% |    0.782 | 34.26% | 32.49%     | -1.85%           |
| Sharpe前四 | 588000_DTE30_ATM_Q10_Hold  | ATM     | Q10      | 2023-06-30 至 2026-05-27 | 22.27% |    0.778 | 34.21% | 32.41%     | -2.05%           |
| Sharpe前四 | 588000_DTE30_OTM1_Q20_Hold | OTM1    | Q20      | 2023-06-30 至 2026-05-27 | 20.99% |    0.777 | 31.97% | 30.32%     | -3.71%           |
| Sharpe前四 | 588000_DTE30_OTM4_Q10_Hold | OTM4    | Q10      | 2023-06-30 至 2026-05-27 | 22.27% |    0.773 | 35.17% | 32.79%     | -1.93%           |


## 6. Step B：固定权重 Universe 组合比较

Step B 的问题是：如果把 Step A 选出来的 sleeve 组成固定权重组合，相对裸持 ETF 组合有没有改善？

Universe 定义：

| Universe   | 组合含义                                                        | 定位       |
|:-----------|:----------------------------------------------------------------|:-----------|
| A          | 510300 covered-call + 510500 ETF BuyHold + 159915 covered-call  | 成长分散化 |
| B          | 510300 covered-call + 510050 covered-call + 159915 covered-call | 防御收入   |

固定权重组合结果：

| portfolio_name      | universe_short   | portfolio_type   |   weight_scheme | annualized_return_cagr   |   sharpe_daily_mean | annualized_volatility   | max_drawdown   | option_leg_annualized_pnl_contribution   |   final_nav |
|:--------------------|:-----------------|:-----------------|----------------:|:-------------------------|--------------------:|:------------------------|:---------------|:-----------------------------------------|------------:|
| A_Pure_ETF_40_40_20 | A                | Pure_ETF         |        40_40_20 | 11.97%                   |               0.644 | 20.93%                  | 29.03%         | 0.00%                                    |       1.484 |
| A_Pure_ETF_50_30_20 | A                | Pure_ETF         |        50_30_20 | 11.43%                   |               0.629 | 20.53%                  | 28.51%         | 0.00%                                    |       1.459 |
| A_Pure_ETF_70_20_10 | A                | Pure_ETF         |        70_20_10 | 9.63%                    |               0.579 | 18.97%                  | 26.36%         | 0.00%                                    |       1.379 |
| A_Selected_40_40_20 | A                | Selected         |        40_40_20 | 11.56%                   |               0.711 | 17.56%                  | 25.44%         | -1.00%                                   |       1.465 |
| A_Selected_50_30_20 | A                | Selected         |        50_30_20 | 11.14%                   |               0.719 | 16.60%                  | 24.13%         | -0.98%                                   |       1.446 |
| A_Selected_70_20_10 | A                | Selected         |        70_20_10 | 10.01%                   |               0.727 | 14.60%                  | 20.59%         | -0.37%                                   |       1.395 |
| B_Pure_ETF_40_40_20 | B                | Pure_ETF         |        40_40_20 | 8.41%                    |               0.525 | 18.71%                  | 26.23%         | 0.00%                                    |       1.326 |
| B_Pure_ETF_50_30_20 | B                | Pure_ETF         |        50_30_20 | 8.75%                    |               0.537 | 18.93%                  | 26.59%         | 0.00%                                    |       1.34  |
| B_Pure_ETF_70_20_10 | B                | Pure_ETF         |        70_20_10 | 7.82%                    |               0.507 | 18.07%                  | 25.21%         | 0.00%                                    |       1.301 |
| B_Selected_40_40_20 | B                | Selected         |        40_40_20 | 8.66%                    |               0.684 | 13.49%                  | 19.65%         | -0.60%                                   |       1.337 |
| B_Selected_50_30_20 | B                | Selected         |        50_30_20 | 8.94%                    |               0.697 | 13.62%                  | 19.93%         | -0.67%                                   |       1.349 |
| B_Selected_70_20_10 | B                | Selected         |        70_20_10 | 8.50%                    |               0.701 | 12.82%                  | 17.87%         | -0.17%                                   |       1.33  |

Selected 相对 pure ETF 的改善：

| selected_portfolio   | matched_baseline    |   weight_scheme | excess_cagr_vs_baseline   |   delta_sharpe_vs_baseline | delta_volatility_vs_baseline   | delta_mdd_vs_baseline   | option_leg_annualized_pnl_contribution   | interpretation_hint                                        |
|:---------------------|:--------------------|----------------:|:--------------------------|---------------------------:|:-------------------------------|:------------------------|:-----------------------------------------|:-----------------------------------------------------------|
| A_Selected_40_40_20  | A_Pure_ETF_40_40_20 |        40_40_20 | -0.41%                    |                      0.066 | -3.37%                         | -3.60%                  | -1.00%                                   | selected 改善风险调整路径，但收益取舍仍需复核              |
| A_Selected_50_30_20  | A_Pure_ETF_50_30_20 |        50_30_20 | -0.29%                    |                      0.09  | -3.93%                         | -4.38%                  | -0.98%                                   | selected 改善风险调整路径，但收益取舍仍需复核              |
| A_Selected_70_20_10  | A_Pure_ETF_70_20_10 |        70_20_10 | 0.38%                     |                      0.147 | -4.36%                         | -5.76%                  | -0.37%                                   | selected 相对匹配 pure ETF 基准同时改善收益、Sharpe 和回撤 |
| B_Selected_40_40_20  | B_Pure_ETF_40_40_20 |        40_40_20 | 0.25%                     |                      0.159 | -5.22%                         | -6.58%                  | -0.60%                                   | selected 相对匹配 pure ETF 基准同时改善收益、Sharpe 和回撤 |
| B_Selected_50_30_20  | B_Pure_ETF_50_30_20 |        50_30_20 | 0.20%                     |                      0.16  | -5.31%                         | -6.66%                  | -0.67%                                   | selected 相对匹配 pure ETF 基准同时改善收益、Sharpe 和回撤 |
| B_Selected_70_20_10  | B_Pure_ETF_70_20_10 |        70_20_10 | 0.68%                     |                      0.194 | -5.25%                         | -7.34%                  | -0.17%                                   | selected 相对匹配 pure ETF 基准同时改善收益、Sharpe 和回撤 |

Step B 的结论是：Selected 组合相对 pure ETF 组合普遍改善 Sharpe 和 MDD，说明 covered-call sleeve 在组合层有风险控制价值。Universe B 的防御收入特征更清楚。

## 7. Step B+：MDD 约束 Sharpe 前沿

Step B+ 的问题是：在 selected sleeve 固定以后，如果给一个最大回撤预算 `D_star`，静态权重应该怎么配？

默认约束下的 frontier：

| portfolio_name                           | universe_short   | constraint_set   | D_star   | frontier_status   | feasible   | sharpe_daily_mean   | annualized_return_cagr   | annualized_volatility   | max_drawdown   | weight_510300   | weight_510500   | weight_510050   | weight_159915   |
|:-----------------------------------------|:-----------------|:-----------------|:---------|:------------------|:-----------|:--------------------|:-------------------------|:------------------------|:---------------|:----------------|:----------------|:----------------|:----------------|
| A_default_D18_NA                         | A                | default          | 18.00%   | infeasible        | False      |                     |                          |                         |                |                 |                 |                 |                 |
| A_default_D20_NA                         | A                | default          | 20.00%   | infeasible        | False      |                     |                          |                         |                |                 |                 |                 |                 |
| A_default_D22_51030070_51050009_15991521 | A                | default          | 22.00%   | feasible          | True       | 0.730               | 10.26%                   | 14.92%                  | 21.94%         | 70.00%          | 9.00%           |                 | 21.00%          |
| A_default_D25_51030070_51050009_15991521 | A                | default          | 25.00%   | feasible          | True       | 0.730               | 10.26%                   | 14.92%                  | 21.94%         | 70.00%          | 9.00%           |                 | 21.00%          |
| A_default_D30_51030070_51050009_15991521 | A                | default          | 30.00%   | feasible          | True       | 0.730               | 10.26%                   | 14.92%                  | 21.94%         | 70.00%          | 9.00%           |                 | 21.00%          |
| B_default_D18_51030070_51005020_15991510 | B                | default          | 18.00%   | feasible          | True       | 0.701               | 8.50%                    | 12.82%                  | 17.87%         | 70.00%          |                 | 20.00%          | 10.00%          |
| B_default_D20_51030070_51005012_15991518 | B                | default          | 20.00%   | feasible          | True       | 0.717               | 9.30%                    | 13.71%                  | 19.99%         | 70.00%          |                 | 12.00%          | 18.00%          |
| B_default_D22_51030070_51005005_15991525 | B                | default          | 22.00%   | feasible          | True       | 0.725               | 9.98%                    | 14.59%                  | 21.80%         | 70.00%          |                 | 5.00%           | 25.00%          |
| B_default_D25_51030070_51005005_15991525 | B                | default          | 25.00%   | feasible          | True       | 0.725               | 9.98%                    | 14.59%                  | 21.80%         | 70.00%          |                 | 5.00%           | 25.00%          |
| B_default_D30_51030070_51005005_15991525 | B                | default          | 30.00%   | feasible          | True       | 0.725               | 9.98%                    | 14.59%                  | 21.80%         | 70.00%          |                 | 5.00%           | 25.00%          |

与固定权重基准比较：

| portfolio_name                           | universe_short   | constraint_set   | D_star   | matched_fixed_weight_baseline   | annualized_return_cagr   |   sharpe_daily_mean | max_drawdown   | delta_cagr_vs_fixed_baseline   |   delta_sharpe_vs_fixed_baseline | delta_mdd_vs_fixed_baseline   |
|:-----------------------------------------|:-----------------|:-----------------|:---------|:--------------------------------|:-------------------------|--------------------:|:---------------|:-------------------------------|---------------------------------:|:------------------------------|
| A_default_D22_51030070_51050009_15991521 | A                | default          | 22.00%   | A_Selected_70_20_10             | 10.26%                   |               0.73  | 21.94%         | 0.25%                          |                            0.003 | 1.34%                         |
| A_default_D25_51030070_51050009_15991521 | A                | default          | 25.00%   | A_Selected_70_20_10             | 10.26%                   |               0.73  | 21.94%         | 0.25%                          |                            0.003 | 1.34%                         |
| A_default_D30_51030070_51050009_15991521 | A                | default          | 30.00%   | A_Selected_70_20_10             | 10.26%                   |               0.73  | 21.94%         | 0.25%                          |                            0.003 | 1.34%                         |
| B_default_D18_51030070_51005020_15991510 | B                | default          | 18.00%   | B_Selected_70_20_10             | 8.50%                    |               0.701 | 17.87%         | 0.00%                          |                            0     | 0.00%                         |
| B_default_D20_51030070_51005012_15991518 | B                | default          | 20.00%   | B_Selected_70_20_10             | 9.30%                    |               0.717 | 19.99%         | 0.80%                          |                            0.016 | 2.12%                         |
| B_default_D22_51030070_51005005_15991525 | B                | default          | 22.00%   | B_Selected_70_20_10             | 9.98%                    |               0.725 | 21.80%         | 1.47%                          |                            0.024 | 3.94%                         |
| B_default_D25_51030070_51005005_15991525 | B                | default          | 25.00%   | B_Selected_70_20_10             | 9.98%                    |               0.725 | 21.80%         | 1.47%                          |                            0.024 | 3.94%                         |
| B_default_D30_51030070_51005005_15991525 | B                | default          | 30.00%   | B_Selected_70_20_10             | 9.98%                    |               0.725 | 21.80%         | 1.47%                          |                            0.024 | 3.94%                         |
| A_relaxed_D20_51030079_51050008_15991513 | A                | relaxed          | 20.00%   | A_Selected_70_20_10             | 9.66%                    |               0.729 | 19.99%         | -0.36%                         |                            0.003 | -0.60%                        |
| A_relaxed_D22_51030074_51050007_15991519 | A                | relaxed          | 22.00%   | A_Selected_70_20_10             | 10.03%                   |               0.73  | 21.28%         | 0.02%                          |                            0.003 | 0.68%                         |
| A_relaxed_D25_51030074_51050007_15991519 | A                | relaxed          | 25.00%   | A_Selected_70_20_10             | 10.03%                   |               0.73  | 21.28%         | 0.02%                          |                            0.003 | 0.68%                         |
| A_relaxed_D30_51030074_51050007_15991519 | A                | relaxed          | 30.00%   | A_Selected_70_20_10             | 10.03%                   |               0.73  | 21.28%         | 0.02%                          |                            0.003 | 0.68%                         |
| B_relaxed_D18_51030080_51005011_15991509 | B                | relaxed          | 18.00%   | B_Selected_70_20_10             | 8.68%                    |               0.711 | 17.93%         | 0.18%                          |                            0.01  | 0.06%                         |
| B_relaxed_D20_51030079_51005004_15991517 | B                | relaxed          | 20.00%   | B_Selected_70_20_10             | 9.44%                    |               0.725 | 19.99%         | 0.94%                          |                            0.024 | 2.12%                         |
| B_relaxed_D22_51030077_51005000_15991523 | B                | relaxed          | 22.00%   | B_Selected_70_20_10             | 9.97%                    |               0.729 | 21.49%         | 1.47%                          |                            0.028 | 3.62%                         |
| B_relaxed_D25_51030077_51005000_15991523 | B                | relaxed          | 25.00%   | B_Selected_70_20_10             | 9.97%                    |               0.729 | 21.49%         | 1.47%                          |                            0.028 | 3.62%                         |
| B_relaxed_D30_51030077_51005000_15991523 | B                | relaxed          | 30.00%   | B_Selected_70_20_10             | 9.97%                    |               0.729 | 21.49%         | 1.47%                          |                            0.028 | 3.62%                         |

Step B+ 的关键观察：随着 `D_star` 放宽，收益和 Sharpe 通常上升，但 MDD 也上升；`B_default_D20` 是一个较好的中间点，既贴近 20% MDD 预算，又保持了 Universe B 的大盘备兑收入解释。

## 8. Step C：稳健性与稳定性诊断

Step C 不是新优化器，而是围绕 Step B+ 的代表性候选做诊断。候选包括 `B_default_D18`、`B_default_D20`、`B_default_D22` 和 `A_default_D25`。

全样本结果：

| portfolio_name   | role             | sample_start   | sample_end   |   n_trading_days | annualized_return_cagr   |   sharpe_daily_mean | annualized_volatility   | max_drawdown   | option_leg_annualized_pnl_contribution   |   final_nav |
|:-----------------|:-----------------|:---------------|:-------------|-----------------:|:-------------------------|--------------------:|:------------------------|:---------------|:-----------------------------------------|------------:|
| A_default_D25    | 成长弹性对照候选 | 2022-09-30     | 2026-05-27   |              881 | 10.26%                   |               0.73  | 14.92%                  | 21.94%         | -0.98%                                   |       1.407 |
| B_default_D18    | 严格防御候选     | 2022-09-30     | 2026-05-27   |              881 | 8.50%                    |               0.701 | 12.82%                  | 17.87%         | -0.17%                                   |       1.33  |
| B_default_D20    | 稳健防御主线候选 | 2022-09-30     | 2026-05-27   |              881 | 9.30%                    |               0.717 | 13.71%                  | 19.99%         | -0.70%                                   |       1.364 |
| B_default_D22    | 平衡防御成长候选 | 2022-09-30     | 2026-05-27   |              881 | 9.98%                    |               0.725 | 14.59%                  | 21.80%         | -1.15%                                   |       1.394 |

稳定性评分：

| portfolio_name   | role             |   full_sample_sharpe | full_sample_mdd   | event_exclusion_sharpe_stability   | rolling_sharpe_stability   | cost_sensitivity_score   | option_leg_robustness_score   | weight_interpretability_score   | overall_stability_score   | overall_stability_label   |
|:-----------------|:-----------------|---------------------:|:------------------|:-----------------------------------|:---------------------------|:-------------------------|:------------------------------|:--------------------------------|:--------------------------|:--------------------------|
| A_default_D25    | 成长弹性对照候选 |                0.73  | 21.94%            | 31.76%                             | 63.81%                     | 97.24%                   | 0.00%                         | 50.00%                          | 56.88%                    | Medium Stability          |
| B_default_D22    | 平衡防御成长候选 |                0.725 | 21.80%            | 34.12%                             | 63.81%                     | 97.16%                   | 0.00%                         | 50.00%                          | 56.81%                    | Medium Stability          |
| B_default_D20    | 稳健防御主线候选 |                0.717 | 19.99%            | 31.86%                             | 64.60%                     | 96.95%                   | 0.00%                         | 50.00%                          | 56.60%                    | Medium Stability          |
| B_default_D18    | 严格防御候选     |                0.701 | 17.87%            | 29.18%                             | 65.24%                     | 96.66%                   | 0.00%                         | 50.00%                          | 56.53%                    | Medium Stability          |

推荐表：

| portfolio_name   | recommendation_role             | overall_stability_label   | overall_stability_score   |   full_sample_sharpe | full_sample_mdd   | matched_baseline_for_context   |   delta_sharpe_vs_context_baseline | reason                                               | next_stage_suggestion          |
|:-----------------|:--------------------------------|:--------------------------|:--------------------------|---------------------:|:------------------|:-------------------------------|-----------------------------------:|:-----------------------------------------------------|:-------------------------------|
| B_default_D20    | 主线 defensive-income candidate | Medium Stability          | 56.60%                    |                0.717 | 19.99%            | B_Selected_40_40_20            |                              0.033 | 优先作为报告主线候选，后续只做稳健性解释和看板展示。 | 可进入 Step D 可选动态权重研究 |
| B_default_D22    | 平衡候选                        | Medium Stability          | 56.81%                    |                0.725 | 21.80%            | B_Selected_40_40_20            |                              0.041 | 用于检验是否值得接受更高回撤换取更好收益弹性。       | 可进入 Step D 可选动态权重研究 |
| B_default_D18    | 严格防御候选                    | Medium Stability          | 56.53%                    |                0.701 | 17.87%            | B_Selected_40_40_20            |                              0.017 | 用于低回撤约束场景，不直接追求收益最大化。           | 可进入 Step D 可选动态权重研究 |
| A_default_D25    | 成长弹性对照                    | Medium Stability          | 56.88%                    |                0.73  | 21.94%            | A_Selected_40_40_20            |                              0.019 | 用于保留 Universe A 的成长分散化对照线。             | 可进入 Step D 可选动态权重研究 |

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
