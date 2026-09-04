# ver3 Source Map

## Step D Dynamic Weighting Quick Map

| File | Responsibility |
| --- | --- |
| `ver3/scripts/python/run_stepD_volatility_controlled_dynamic_weighting.py` | Step D end-to-end runner: dynamic weights, daily returns, cost sensitivity, report, validation. |
| `ver3/scripts/run_stepD_dynamic_weighting.ps1` | PowerShell wrapper that returns to project root and calls the real Step D runner. |
| `ver3/src/covered_call_mini_ver3/stepD_dynamic_weighting/config.py` | Universe A/B, anchor weights, lookbacks, methods, bounds, paths. |
| `ver3/src/covered_call_mini_ver3/stepD_dynamic_weighting/universe.py` | Align fixed sleeve return panels and option-leg panels. |
| `ver3/src/covered_call_mini_ver3/stepD_dynamic_weighting/signals.py` | Month-end rolling volatility/covariance signals, next-trading-day application. |
| `ver3/src/covered_call_mini_ver3/stepD_dynamic_weighting/weights.py` | Anchored inverse vol, pure inverse vol, rolling minimum variance weights. |
| `ver3/src/covered_call_mini_ver3/stepD_dynamic_weighting/rebalance.py` | Expand monthly target weights into daily weight paths. |
| `ver3/src/covered_call_mini_ver3/stepD_dynamic_weighting/portfolio.py` | Build dynamic daily returns, NAV, drawdown. |
| `ver3/src/covered_call_mini_ver3/stepD_dynamic_weighting/metrics.py` | Frozen metrics and same-effective-sample static baseline comparison. |
| `ver3/src/covered_call_mini_ver3/stepD_dynamic_weighting/turnover.py` | Turnover approximation and rebalance-cost sensitivity. |
| `ver3/src/covered_call_mini_ver3/stepD_dynamic_weighting/attribution.py` | Option-leg and ex-post risk contribution. |
| `ver3/src/covered_call_mini_ver3/stepD_dynamic_weighting/reporting.py` | Chinese markdown report and lightweight ver3 output index. |
| `ver3/src/covered_call_mini_ver3/stepD_dynamic_weighting/validation.py` | Validation checks for inputs, lagging, bounds, paths, and report output. |

Step D real output root: `outputs/ver3_0_stepD_volatility_controlled_dynamic_weighting/`

Step D lightweight index: `ver3/outputs/ver3_0_stepD_output_index.md`

这份文件只回答一个问题：人工跟源码时，从哪里进、读哪些文件、哪些只是冻结依赖。

如果你直接打开 `ver3/` 文件夹，下面以 `../` 开头的路径都指向仓库根目录中的真实源码或真实输出。

报告语言约定：后续新增的面向阅读报告默认中文输出；只有机器字段、指标名和脚本参数保留英文标识。

## 1. Entry Scripts

这些是 ver3 当前真实入口：

| Entry | Purpose |
| --- | --- |
| `ver3/scripts/python/run_effective_delta_equivalence_diagnostic.py` | 独立旁路诊断：比较同一 entry effective delta 下 D28_Q100、D35_Q80、D40_Q70、D50_Q56 的 payoff 实现差异；不改写 Step A-D。 |
| `ver3/scripts/python/run_ver3_1_effective_zone_target_delta.py` | ver3.1 sidecar：先从固定虚值 x 覆盖率参数曲面识别有效区间，再映射到 target-delta 选券，并复算固定权重、MDD frontier 与动态权重。 |
| `ver3/scripts/python/run_ver3_0_stepA_single_etf_sleeves.py` | 构建 510300、510500、159915 单 ETF sleeve 画像。 |
| `ver3/scripts/python/run_ver3_0_stepA_extension_510050_sleeve_clarification.py` | 构建 510050 单 ETF extension 画像。 |
| `ver3/scripts/python/run_ver3_0_stepA_extension_588000_sleeve_clarification.py` | 构建 588000 short-sample extension 画像。 |
| `ver3/scripts/python/run_ver3_0_stepA_moneyness_refined_daily_mtm_surface.py` | 构建 5 ETF 的虚值程度 × 覆盖率细网格单 ETF 参数曲面诊断；当前入口为 continuous DTE30 daily MTM 口径。 |
| `ver3/scripts/python/ver3_0_stepB_fixed_weight_universe_comparison.py` | 构建 Step B 固定权重 universe 组合比较。 |
| `ver3/scripts/python/run_stepB_plus_mdd_constrained_sharpe_frontier.py` | 构建 Step B+ MDD 约束 Sharpe frontier。 |
| `ver3/scripts/python/run_stepC_robustness_stability_diagnostics.py` | 构建 Step C 稳健性与稳定性诊断。 |

`ver3/scripts/*.ps1` 是薄运行包装器，只是为了从 ver3 项目文件夹里方便运行，不承载策略逻辑。

仓库根目录 `scripts/run_ver3_0_stepA_*.py` 现在是兼容入口，会转发到 `ver3/scripts/python/` 下的真实脚本。

## 2. Reusable ver3 Source

目前真正模块化并且已经验证的 ver3 源码集中在 Step B：

| File | Responsibility |
| --- | --- |
| `ver3/src/covered_call_mini_ver3/stepB/config.py` | 样本日期、输入输出路径、Universe A/B、固定权重、禁止混入的 sleeve token。 |
| `ver3/src/covered_call_mini_ver3/stepB/io.py` | 读取 Step A 面板、510050 extension、588000 reference，并对齐主样本。 |
| `ver3/src/covered_call_mini_ver3/stepB/portfolio.py` | 按日收益加权，生成组合 daily return、NAV 和 drawdown。 |
| `ver3/src/covered_call_mini_ver3/stepB/metrics.py` | 调用 ver2 标准指标口径，生成组合 summary。 |
| `ver3/src/covered_call_mini_ver3/stepB/attribution.py` | selected-vs-pure、A-vs-B、option leg、相关性、协方差和风险贡献。 |
| `ver3/src/covered_call_mini_ver3/stepB/plotting.py` | Step B 图表输出。 |
| `ver3/src/covered_call_mini_ver3/stepB/reporting.py` | Step B Markdown 报告。 |
| `ver3/src/covered_call_mini_ver3/stepB/validation.py` | Step B sanity checks。 |

Step B+ 的模块化源码在同一条 ver3 主线下：

| File | Responsibility |
| --- | --- |
| `ver3/src/covered_call_mini_ver3/stepB_plus/config.py` | Step B+ 样本、universe A/B、约束组、D-star、输入输出路径契约。 |
| `ver3/src/covered_call_mini_ver3/stepB_plus/io.py` | 读取 Step A/510050 extension 面板和 Step B 固定权重 baseline。 |
| `ver3/src/covered_call_mini_ver3/stepB_plus/optimizer.py` | 生成静态权重网格，计算 frontier 指标，按 MDD 目标筛选最大 Sharpe。 |
| `ver3/src/covered_call_mini_ver3/stepB_plus/portfolio.py` | 根据 best weights 重建 daily return、NAV 和 drawdown。 |
| `ver3/src/covered_call_mini_ver3/stepB_plus/attribution.py` | option-leg contribution、相关性、协方差和风险贡献。 |
| `ver3/src/covered_call_mini_ver3/stepB_plus/plotting.py` | frontier、NAV、drawdown、权重和风险贡献图。 |
| `ver3/src/covered_call_mini_ver3/stepB_plus/reporting.py` | Step B+ Markdown 报告和轻量输出索引。 |
| `ver3/src/covered_call_mini_ver3/stepB_plus/validation.py` | Step B+ 输出边界和实验口径校验。 |

Step C 的模块化源码在：

| File | Responsibility |
| --- | --- |
| `ver3/src/covered_call_mini_ver3/stepC_robustness/config.py` | Step C 候选点、事件窗口、成本情景和路径契约。 |
| `ver3/src/covered_call_mini_ver3/stepC_robustness/io.py` | 读取 Step B+、Step B、Step A 面板和 option-leg 数据。 |
| `ver3/src/covered_call_mini_ver3/stepC_robustness/portfolio.py` | 构建候选组合 daily return、NAV 和 drawdown。 |
| `ver3/src/covered_call_mini_ver3/stepC_robustness/event_windows.py` | 自动/手动事件窗口和事件剔除诊断。 |
| `ver3/src/covered_call_mini_ver3/stepC_robustness/rolling.py` | 年度、半年度、rolling 252d/504d 稳定性指标。 |
| `ver3/src/covered_call_mini_ver3/stepC_robustness/cost_sensitivity.py` | option-leg 成本敏感性。 |
| `ver3/src/covered_call_mini_ver3/stepC_robustness/weight_bound_sensitivity.py` | default / relaxed 权重边界敏感性。 |
| `ver3/src/covered_call_mini_ver3/stepC_robustness/stability.py` | 综合稳定性评分和候选推荐。 |
| `ver3/src/covered_call_mini_ver3/stepC_robustness/reporting.py` | Step C 中文报告和轻量输出索引。 |

后续新增代码的项目内落点是：

```text
ver3/src/covered_call_mini_ver3/
```

Step B 已经在这里，不再保留 `src/covered_call_mini/ver3/stepB` 影子目录。

## 3. Frozen Dependencies

这些文件不是 ver3 主线源码，但当前 ver3 还会复用它们：

| Dependency | Why it remains |
| --- | --- |
| `../src/metrics/ver2_metric_standard.py` | 统一 `sharpe_daily_mean`、CAGR、MDD、Sortino、option-leg contribution 等指标口径。 |
| `../ver2_downside_protection/config.py` | 588000 extension 暂时复用旧 engine 配置对象。 |
| `../ver2_downside_protection/strategy_engine.py` | 588000 extension 暂时复用旧 backtest engine。 |

这三个属于冻结依赖。后续如果要进一步清洁工程，可以把必要口径迁入 `ver3/src/covered_call_mini_ver3/common/`，但不要在没有测试对照时直接改动旧 engine。

## 4. Output Map

| Output Root | Current Role |
| --- | --- |
| `outputs/ver3_0_stepA_single_etf_sleeves/` | Step A main sleeves: 510300、510500、159915。 |
| `outputs/ver3_0_stepA_extension_510050_sleeve_clarification/` | 510050 single ETF extension。 |
| `outputs/ver3_0_stepA_extension_588000_sleeve_clarification/` | 588000 short-sample extension。 |
| `outputs/ver3_0_stepA_moneyness_refined_daily_mtm_surface/` | Step A 单 ETF 细虚值参数曲面诊断；current daily-MTM output。 |
| `outputs/ver3_0_stepB_fixed_weight_universe_comparison/` | Step B 固定权重组合层结果。 |
| `outputs/ver3_0_stepB_plus_mdd_constrained_sharpe_frontier/` | Step B+ MDD 约束 Sharpe frontier 结果。 |
| `outputs/ver3_0_stepC_robustness_stability_diagnostics/` | Step C 稳健性与稳定性诊断结果。 |

Step B 当前口径是：读取每个 sleeve 的 daily return，按固定权重逐日加总，再累乘生成组合 NAV。它不是把每条完整净值曲线终值或净值路径简单线性相加。

Step B+ 当前口径是：在同一组 selected sleeves 上枚举静态权重网格，逐日加权 returns 后生成 NAV，并在每个 `D_star` 下选择满足 MDD 约束的最高 `sharpe_daily_mean` 组合。它不是动态择时、滚动优化、波动率目标、风险平价或均值方差优化。

Step C 当前口径是：只围绕四个代表性 Step B+ 候选权重做稳健性诊断，包括事件窗口剔除、滚动窗口、成本敏感性、权重边界敏感性和稳定性评分。它不是新的优化层，也不重新打开期权参数网格。
