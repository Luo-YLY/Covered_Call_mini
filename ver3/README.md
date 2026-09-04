# covered_call_mini ver3 工作区

## Step D 已新增

Step D 是波动率控制的动态 sleeve 权重研究层，入口为：

```text
ver3/scripts/python/run_stepD_volatility_controlled_dynamic_weighting.py
```

源码目录：

```text
ver3/src/covered_call_mini_ver3/stepD_dynamic_weighting/
```

真实输出目录：

```text
outputs/ver3_0_stepD_volatility_controlled_dynamic_weighting/
```

轻量索引：

```text
ver3/outputs/ver3_0_stepD_output_index.md
```

这个目录是 ver3 的独立项目入口，不是旧工程的整仓副本。

它的目标是让 VSCode 里只看到当前研究主线：ver3 源码地图、ver3 入口脚本、ver3 输出索引、少量冻结依赖说明和文档。ver1/ver2 仍保留在原工程里作为历史证据，但不再混入日常阅读视图。

## 打开方式

最简方式：在 VSCode 里直接打开这个文件夹：

```text
C:\Users\WIN11\Desktop\CCFund\ETF备兑策略设计\covered_call_mini\ver3
```

如果你想同时看根目录兼容入口、ver3 源码和真实输出目录，也可以打开仓库根目录下的：

```text
covered_call_mini_ver3.code-workspace
```

这个 workspace 会把视图收敛到：

- `ver3-control`: 当前目录，放 ver3 导航、运行手册和迁移约束。
- `ver3-source`: `ver3/src/covered_call_mini_ver3/`，目前主要是 Step B 模块化源码。
- `ver3-entry-scripts`: 根目录 `scripts/`，但隐藏 ver1/ver2/layer 旧脚本。
- `metric-standard-dependency`: `src/metrics/`，保留 ver2 标准化指标口径。
- `StepA-*` / `StepB-*`: 已完成的 ver3 输出目录。
- `ver3-docs`: 工程规划和实验说明文档。

## 当前 ver3 主线

| Step | 状态 | 入口 | 输出 |
| --- | --- | --- | --- |
| Step A main | 已完成 | `ver3/scripts/python/run_ver3_0_stepA_single_etf_sleeves.py` | `outputs/ver3_0_stepA_single_etf_sleeves/` |
| Step A 510050 extension | 已完成 | `ver3/scripts/python/run_ver3_0_stepA_extension_510050_sleeve_clarification.py` | `outputs/ver3_0_stepA_extension_510050_sleeve_clarification/` |
| Step A 588000 extension | 已完成 | `ver3/scripts/python/run_ver3_0_stepA_extension_588000_sleeve_clarification.py` | `outputs/ver3_0_stepA_extension_588000_sleeve_clarification/` |
| Step A refined daily-MTM surface | 已完成 | `ver3/scripts/python/run_ver3_0_stepA_moneyness_refined_daily_mtm_surface.py` | `outputs/ver3_0_stepA_moneyness_refined_daily_mtm_surface/` |
| Step B fixed-weight universe | 已完成 | `ver3/scripts/python/ver3_0_stepB_fixed_weight_universe_comparison.py` | `outputs/ver3_0_stepB_fixed_weight_universe_comparison/` |
| Step B+ MDD-constrained Sharpe frontier | 已完成 | `ver3/scripts/python/run_stepB_plus_mdd_constrained_sharpe_frontier.py` | `outputs/ver3_0_stepB_plus_mdd_constrained_sharpe_frontier/` |
| Step C robustness diagnostics | 已完成 | `ver3/scripts/python/run_stepC_robustness_stability_diagnostics.py` | `outputs/ver3_0_stepC_robustness_stability_diagnostics/` |
| ver3.1 effective-zone target-delta sidecar | 已完成 | `ver3/scripts/python/run_ver3_1_effective_zone_target_delta.py` | `outputs/ver3_1_effective_zone_target_delta/` |
| independent effective-delta equivalence diagnostic | 已完成 | `ver3/scripts/python/run_effective_delta_equivalence_diagnostic.py` | `outputs/ver3_0_independent_effective_delta_equivalence_diagnostic/` |

## 阅读顺序

如果你要人工跟源码，建议按这个顺序读：

1. `PROJECT_LAYOUT.md`: 看这个文件夹和旧仓库根目录怎么分工。
2. `SOURCE_MAP.md`: 看清每个入口脚本、模块和输出的关系。
3. `RUNBOOK.md`: 看怎么重跑，哪些输出会被刷新。
4. `MIGRATION_PLAN.md`: 看后续代码如何继续收拢，哪些旧依赖先冻结。
5. `scripts/python/ver3_0_stepB_fixed_weight_universe_comparison.py`: Step B 固定权重组合层主流程。
6. `src/covered_call_mini_ver3/stepB/config.py`: Step B universe、sleeve、权重和路径契约。
7. `scripts/python/run_stepB_plus_mdd_constrained_sharpe_frontier.py`: Step B+ MDD 约束 Sharpe frontier 主流程。
8. `src/covered_call_mini_ver3/stepB_plus/optimizer.py`: Step B+ 静态权重网格、MDD 约束和最优点筛选。
9. `scripts/python/run_stepC_robustness_stability_diagnostics.py`: Step C 稳健性诊断主流程。
10. `src/covered_call_mini_ver3/stepC_robustness/stability.py`: Step C 稳定性评分和候选推荐。
11. `src/covered_call_mini_ver3/stepC_robustness/reporting.py`: Step C 中文报告和 `ver3/outputs` 轻量索引。

## 重要边界

- ver3 不再新建 `covered_call_mini_ver*` 整仓副本。
- 新实验优先写进 `ver3/src/covered_call_mini_ver3/<step>/` 和 `ver3/scripts/`。
- 每个实验输出独立落在 `outputs/ver3_*`。
- 本项目后续所有面向阅读的报告默认使用中文；CSV 字段名、程序参数和指标名可保留稳定英文标识，方便下游复用。
- 可再生的大 CSV、PNG、daily 明细默认只本地保留，不作为核心人工审阅对象。
- 588000 目前仍是 short-sample extension，不拉短 Step B 主样本。
