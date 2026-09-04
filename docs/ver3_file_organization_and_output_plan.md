# ver3 文件整理与实验输出规划

本文档用于约束 ver3 之后的工程结构和实验产物命名。目标不是回头清理或移动 ver1/ver2，而是在 ver3 开始把代码、配置、输入、输出、报告和审计记录分开，避免新的实验继续扩大脏文件面。

## 一、目录分区

ver3 推荐按功能分区，而不是按整仓复制：

| 区域 | 用途 | 规则 |
| --- | --- | --- |
| `src/` | 稳定、可复用的策略和分析模块 | 放公共逻辑，不直接写实验产物 |
| `scripts/run_ver3_*` | 单次实验入口 | 尽量薄，只负责装配输入、调用模块、落盘 |
| `configs/ver3/` | 实验配置快照或模板 | 参数变化优先写配置，不复制脚本 |
| `docs/` | 稳定规划、实验说明、输出契约 | 记录为什么这样组织，而不是存大结果 |
| `data/raw/` | 原始输入数据 | 不写回测中间结果 |
| `data/source/` | 标准化后的基础输入 | 不放单次实验输出 |
| `outputs/ver3_*` | 可再生成的实验输出根目录 | 每个实验一个根目录，必须有 README 和 manifest |

原则：不再新增 `covered_call_mini_ver*` 这类整仓副本；不把实验输出写进 `data/`；不把可再生成的大 CSV、PNG、临时文件纳入版本管理。

## 二、ver3 输出根目录契约

每个 ver3 实验统一使用：

```text
outputs/ver3_<step>_<short_slug>/
  README.md
  manifest.json
  config_snapshot.yaml
  input_manifest.csv
  daily/
  period/
  summary/
  panel/
  figures/
  reports/
  audit/
  logs/
  tmp/
```

目录含义：

| 子目录 | 内容 |
| --- | --- |
| `daily/` | 日频净值、日收益、日度状态、日度归因 |
| `period/` | 持仓期、调仓期、到期周期等分段归因 |
| `summary/` | 策略级汇总指标、候选排序、分类表 |
| `panel/` | 给下一步组合实验读取的统一面板 |
| `figures/` | 可再生成图片 |
| `reports/` | 面向阅读的 Markdown 报告 |
| `audit/` | sanity check、样本覆盖、输入一致性检查 |
| `logs/` | 运行日志 |
| `tmp/` | 临时文件，原则上不保留 |

`README.md` 说明这个实验是什么、怎么重跑、哪些文件给下一步使用。`manifest.json` 记录输入、输出、样本区间、状态、主结论和审计结果。

## 三、版本管理规则

默认追踪：

- 源码：`src/`、`scripts/`
- 配置：`configs/ver3/`
- 文档：`docs/`
- 每个 ver3 输出根目录的 `README.md`
- 每个 ver3 输出根目录的 `manifest.json`
- 面向阅读的 Markdown 报告和轻量审计表

默认不追踪：

- `outputs/**` 下的大 CSV、PNG、日志、临时文件
- 可由脚本再生成的中间结果
- 原始行情和期权大文件

这不是删除本地结果，而是让 git status 只显示真正需要评审的东西。

## 四、当前已完成部分

### ver3.0 Universe Strategy Direction

ver3.0 后续研究分为三个 universe 层次：

| Universe | ETF 组合 | 定位 |
| --- | --- | --- |
| Main Growth-Diversified Universe | `510300 + 510500 + 159915` | 主线成长分散组合；510500 不做备兑主力，但保留中盘成长分散价值 |
| Alternative Defensive-Income Universe | `510300 + 510050 + 159915` | 用 510050 替代 510500，检验第二个大盘备兑核心，但需注意与 510300 高相关 |
| Tech-Growth Short-Sample Extension Universe | `510300 + 510050 + 159915 + 588000` 或 `510300 + 510500 + 159915 + 588000` | 科创成长 / 硬科技短样本扩展；不拖短主线 Step B / Step B+ |

正式 strategy 文件：

- `outputs/ver3_0_stepA_extension_588000_sleeve_clarification/strategy/ver3_0_universe_strategy_direction.md`
- `outputs/ver3_0_stepA_extension_588000_sleeve_clarification/strategy/ver3_0_universe_strategy_map.csv`

### Step A：Single-ETF Covered-Call Sleeve Clarification

| 项目 | 内容 |
| --- | --- |
| 状态 | 已完成 |
| 输出根目录 | `outputs/ver3_0_stepA_single_etf_sleeves/` |
| 运行脚本 | `scripts/run_ver3_0_stepA_single_etf_sleeves.py` |
| 样本区间 | 2022-09-19 到 2026-05-27 |
| ETF 范围 | `510300`、`510500`、`159915` |
| sanity check | 18/18 通过 |

Step A 的职责是把单 ETF 备兑 sleeve 先讲清楚，只回答“每个 ETF 自己适合哪类备兑表达”。它不做组合权重优化，也不承担组合层收益解释。

当前主结论：

| ETF | 推荐 sleeve | 分类 |
| --- | --- | --- |
| `510300` | `510300_DTE30_D40_Q70_Hold` | Positive Carry Overlay |
| `510500` | `510500_ETF_BuyHold` | Pure ETF Preferred |
| `159915` | `159915_DTE30_OTM5up_Q50_Hold` | Defensive Overlay |

Step A 生成的下一步输入：

- `outputs/ver3_0_stepA_single_etf_sleeves/panel/ver3_0_stepA_sleeve_return_panel_wide.csv`
- `outputs/ver3_0_stepA_single_etf_sleeves/panel/ver3_0_stepA_sleeve_return_panel_long.csv`

### Step A-Extension：510050 Single-ETF Sleeve Clarification

| 项目 | 内容 |
| --- | --- |
| 状态 | 已完成 |
| 输出根目录 | `outputs/ver3_0_stepA_extension_510050_sleeve_clarification/` |
| 运行脚本 | `scripts/run_ver3_0_stepA_extension_510050_sleeve_clarification.py` |
| 正式样本区间 | 2022-09-19 到 2026-05-27 |
| 源数据可用区间 | 2021-01-29 到 2026-05-27 |
| ETF 范围 | `510050` |
| sanity check | 10/10 通过 |

Step A-Extension 的职责是补做 510050 的单 ETF 备兑画像，判断其是否可以替代 510500，进入 alternative defensive-income universe。它仍然不计算组合权重。

当前主结论：

| ETF | 推荐 sleeve | 分类 | 与 510300 Q70 相关性判断 |
| --- | --- | --- | --- |
| `510050` | `510050_DTE30_D40_Q70_Hold` | Positive Carry Overlay | 高重叠，日收益相关系数约 0.885 |

Step A-Extension 生成的下一步输入：

- `outputs/ver3_0_stepA_extension_510050_sleeve_clarification/panel/ver3_0_stepA_extension_510050_sleeve_return_panel_wide.csv`
- `outputs/ver3_0_stepA_extension_510050_sleeve_clarification/panel/ver3_0_stepA_extension_510050_sleeve_return_panel_long.csv`

### Step A-Extension：588000 Single-ETF Sleeve Clarification

| 项目 | 内容 |
| --- | --- |
| 状态 | 已完成 |
| 输出根目录 | `outputs/ver3_0_stepA_extension_588000_sleeve_clarification/` |
| 运行脚本 | `scripts/run_ver3_0_stepA_extension_588000_sleeve_clarification.py` |
| 主线 Step A 样本 | 2022-09-19 到 2026-05-27 |
| 588000 ETF 数据可用区间 | 2021-01-04 到 2026-06-03 |
| 588000 期权数据可用区间 | 2023-06-05 到 2026-06-03 |
| 实际 sleeve 回测区间 | 2023-06-30 到 2026-05-27 |
| ETF 范围 | `588000` |
| sanity check | 12/12 通过 |

Step A-Extension 的职责是补做 588000 的短样本科创成长画像，判断它是否应作为 short-sample tech-growth extension 进入后续组合层扩展实验。它仍然不计算组合权重，也不拖短主线 Step B 样本。

当前主结论：

| ETF | 推荐 sleeve | 分类 | 与 159915 相关性判断 |
| --- | --- | --- | --- |
| `588000` | `588000_ETF_BuyHold` | Growth Extension Sleeve | 高重叠，日收益相关系数约 0.856 |

Step A-Extension 生成的下一步输入：

- `outputs/ver3_0_stepA_extension_588000_sleeve_clarification/panel/ver3_0_stepA_extension_588000_sleeve_return_panel_wide.csv`
- `outputs/ver3_0_stepA_extension_588000_sleeve_clarification/panel/ver3_0_stepA_extension_588000_sleeve_return_panel_long.csv`

### Step B：Fixed-Weight Portfolio Layer

| 项目 | 内容 |
| --- | --- |
| 状态 | 已完成 |
| 输出根目录 | `outputs/ver3_0_stepB_fixed_weight_universe_comparison/` |
| 运行脚本 | `scripts/ver3_0_stepB_fixed_weight_universe_comparison.py` |
| 主要输入 | Step A 的 wide/long return panel、510050 extension panel、Step A daily option-leg return |
| 核心问题 | 在不做动态优化的前提下，Universe A 与 Universe B 的固定权重组合是否改善收益、回撤和稳定性 |
| sanity check | 12/12 通过 |

Step B 应保持简单：固定权重、固定 sleeve 集合、清晰归因。它是组合层基准，不应提前引入滚动协方差、动态风险预算或均值方差优化。本轮没有纳入 588000，因此没有缩短主线长样本。

当前主结论：

- 样本区间：2022-09-19 到 2026-05-27，890 个观测日。
- Universe A selected 组合保留更强增长分散特征；最佳 Sharpe 当前为 `A_Selected_50_30_20`。
- Universe B selected 组合降低最大回撤；最低 MDD 当前为 `B_Selected_70_20_10`。
- 588000 保留为 short-sample tech-growth extension，不进入本轮长样本 Step B。
- 后续 Step B+ 应在 Universe A 与 Universe B 内分别做 MDD-constrained Sharpe frontier，而不是把本轮固定权重样本内结果直接视为最终最优。

主要输出：

- `config/ver3_0_stepB_portfolio_weight_map.csv`
- `daily/ver3_0_stepB_portfolio_daily_returns.csv`
- `daily/ver3_0_stepB_portfolio_daily_nav.csv`
- `summary/ver3_0_stepB_portfolio_summary.csv`
- `summary/ver3_0_stepB_selected_vs_pure_baseline.csv`
- `summary/ver3_0_stepB_universeA_vs_universeB_comparison.csv`
- `attribution/ver3_0_stepB_option_leg_contribution.csv`
- `attribution/ver3_0_stepB_risk_contribution.csv`
- `reports/ver3_0_stepB_fixed_weight_universe_comparison_report.md`
- `audit/ver3_0_stepB_sanity_checks.csv`

### Step C：Dynamic Weighting / Risk Budget Layer

| 项目 | 内容 |
| --- | --- |
| 状态 | 规划中 |
| 建议输出根目录 | `outputs/ver3_0_stepC_dynamic_weighting/` |
| 主要输入 | Step A sleeve panel、Step B 固定权重基准 |
| 核心问题 | 动态权重是否真实改善风险调整收益，而不是只在样本内过拟合 |

Step C 才引入动态规则，例如波动率目标、回撤预算、滚动协方差或 sleeve 风险预算。所有动态规则都需要和 Step B 基准对照。

建议输出：

- `daily/dynamic_portfolio_daily_nav.csv`
- `summary/dynamic_strategy_summary.csv`
- `summary/dynamic_vs_fixed_comparison.csv`
- `period/dynamic_period_attribution.csv`
- `figures/dynamic_vs_fixed_nav.png`
- `reports/ver3_0_stepC_dynamic_weighting.md`
- `audit/ver3_0_stepC_sanity_checks.csv`

### Step D：Robustness and Boundary Checks

| 项目 | 内容 |
| --- | --- |
| 状态 | 可选但建议做 |
| 建议输出根目录 | `outputs/ver3_0_stepD_robustness_checks/` |
| 主要输入 | Step A/B/C 的候选策略 |
| 核心问题 | 当前结论是否依赖特定窗口、成本、事件行情或参数点 |

优先检查：

- 交易成本敏感性
- 滚动窗口稳定性
- 极端行情窗口剔除
- 不同起止日期的排序稳定性
- 单 ETF sleeve 选择是否对参数微调过敏

### ver3.0 Sleeve Diagnostics Report Pack

| 项目 | 内容 |
| --- | --- |
| 状态 | 已完成 |
| 输出根目录 | `outputs/ver3_0_sleeve_diagnostics_report_pack/` |
| 运行脚本 | 已于 2026-09-04 主线收口时归档；当前不再重建早期集中报告包 |
| 职责 | 把已完成的 single-ETF sleeve 诊断报告集中到一个阅读入口 |
| 边界 | 只做报告汇总，不运行组合权重，不移动原始实验输出，不新增策略结论 |

集中包当前收录：

- strategy direction：ver3 universe map
- Step A main：510300、510500、159915 master report 和 sleeve cards
- Step A extension：510050 master report 和 sleeve card
- Step A extension：588000 master report 和 sleeve card
- 汇总表：report manifest、combined classification、primary recommendations、correlation references

以后新增 sleeve 诊断实验时，保持原实验目录、README 与 manifest 完整，并通过 ver3.1 汇总报告和看板刷新集中阅读入口，不再依赖早期 multi-asset 报告构建器。

## 五、执行规则

每新增一个 ver3 实验前，先在本文档登记 Step 名称、职责边界和输出根目录。

每个实验完成时，必须同步更新：

- 输出根目录下的 `README.md`
- 输出根目录下的 `manifest.json`
- `audit/` 下的 sanity check
- 如有主结论变化，更新本文档的“当前已完成部分”

每个实验脚本必须能在仓库根目录直接运行。可再生成的大结果不进 git；需要人工阅读或协作评审的轻量文件才进 git。
