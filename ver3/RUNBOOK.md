# ver3 Runbook

## Step D: Volatility-Controlled Dynamic Sleeve Weighting

```powershell
python ver3\scripts\python\run_stepD_volatility_controlled_dynamic_weighting.py --strict
```

常用轻量调试：

```powershell
python ver3\scripts\python\run_stepD_volatility_controlled_dynamic_weighting.py --strict --skip-plots
```

输出：

```text
outputs/ver3_0_stepD_volatility_controlled_dynamic_weighting/
```

核心文件：

```text
summary/ver3_0_stepD_dynamic_strategy_summary.csv
summary/ver3_0_stepD_comparison_vs_static_baselines.csv
summary/ver3_0_stepD_recommendation_table.csv
weights/ver3_0_stepD_dynamic_weight_paths.csv
weights/ver3_0_stepD_rebalance_weights.csv
turnover/ver3_0_stepD_turnover_summary.csv
cost/ver3_0_stepD_rebalance_cost_sensitivity.csv
reports/ver3_0_stepD_volatility_controlled_dynamic_weighting_report.md
```

`ver3/outputs/ver3_0_stepD_output_index.md` 只是轻量索引，不放大 CSV、PNG 或正式报告。

所有命令默认从仓库根目录运行：

```powershell
cd "C:\Users\WIN11\Desktop\CCFund\ETF备兑策略设计\covered_call_mini"
```

也可以从 `ver3/scripts/*.ps1` 包装器运行，它们会自动切回仓库根目录。

报告语言约定：本项目后续所有面向阅读的 Markdown/DOCX/PDF 报告默认使用中文；CSV 字段名、程序参数和指标名可以保留稳定英文标识。

## Step A: Main Single ETF Sleeves

```powershell
python ver3\scripts\python\run_ver3_0_stepA_single_etf_sleeves.py
```

输出：

```text
outputs/ver3_0_stepA_single_etf_sleeves/
```

主要下游输入：

```text
outputs/ver3_0_stepA_single_etf_sleeves/panel/ver3_0_stepA_sleeve_return_panel_wide.csv
outputs/ver3_0_stepA_single_etf_sleeves/daily/ver3_0_stepA_single_etf_sleeve_daily_nav.csv
```

## Step A Extension: 510050

```powershell
python ver3\scripts\python\run_ver3_0_stepA_extension_510050_sleeve_clarification.py
```

输出：

```text
outputs/ver3_0_stepA_extension_510050_sleeve_clarification/
```

## Step A Extension: 588000

```powershell
python ver3\scripts\python\run_ver3_0_stepA_extension_588000_sleeve_clarification.py
```

输出：

```text
outputs/ver3_0_stepA_extension_588000_sleeve_clarification/
```

注意：588000 目前只作为 short-sample extension，不进入 Step B 主长样本组合。

## Step A Diagnostics: Moneyness Refined Surface

```powershell
python ver3\scripts\python\run_ver3_0_stepA_moneyness_refined_daily_mtm_surface.py
```

输出：

```text
outputs/ver3_0_stepA_moneyness_refined_daily_mtm_surface/
```

这一步使用 `data/raw/options_daily.csv` 重新按 `ATM / OTM1 / OTM2 / OTM3 / OTM4 / OTM5 / OTM7` 目标虚值选券，并在 `Q10` 到 `Q100` 覆盖率上构造细网格。口径为 continuous DTE30 daily MTM，不再使用旧 Monthly custom 回测；它只完善单 ETF 参数曲面诊断，不自动改写 Step B/C/D 主线候选。

## ver3.1 Sidecar: Effective Zone to Target Delta

```powershell
python ver3\scripts\python\run_ver3_1_effective_zone_target_delta.py
```

也可以通过工程化入口运行：

```powershell
.\ver3\scripts\ver3.ps1 run effective-delta
```

输出：

```text
outputs/ver3_1_effective_zone_target_delta/
```

这一层不覆盖 ver3.0 主线输出。它使用 Step A refined daily-MTM surface 的固定虚值 x 覆盖率网格来识别有效区间，再使用 `data/source/delta_enriched_options.csv` 做 target-delta 单 ETF 网格，并在同一侧车实验中复算固定权重、MDD 约束 Sharpe frontier 和动态权重。

## Independent Diagnostic: Effective-Delta Equivalence

```powershell
python ver3\scripts\python\run_effective_delta_equivalence_diagnostic.py --strict
```

也可以通过工程化入口运行：

```powershell
.\ver3\scripts\ver3.ps1 run effective-delta-equivalence --strict
```

输出：

```text
outputs/ver3_0_independent_effective_delta_equivalence_diagnostic/
```

这一层只比较 `D28_Q100 / D35_Q80 / D40_Q70 / D50_Q56` 在 target effective delta 0.72 附近的实现差异，不是自由参数网格优化，不纳入 588000，不改写 Step A-D 或当前主线结论。

## Step B: Fixed-Weight Universe Comparison

```powershell
python ver3\scripts\python\ver3_0_stepB_fixed_weight_universe_comparison.py --strict
```

常用轻量调试：

```powershell
python ver3\scripts\python\ver3_0_stepB_fixed_weight_universe_comparison.py --strict --skip-plots --no-write-report
```

输出：

```text
outputs/ver3_0_stepB_fixed_weight_universe_comparison/
```

核心文件：

```text
summary/ver3_0_stepB_portfolio_summary.csv
summary/ver3_0_stepB_selected_vs_pure_baseline.csv
summary/ver3_0_stepB_universeA_vs_universeB_comparison.csv
attribution/ver3_0_stepB_option_leg_contribution.csv
attribution/ver3_0_stepB_risk_contribution.csv
reports/ver3_0_stepB_fixed_weight_universe_comparison_report.md
audit/ver3_0_stepB_sanity_checks.csv
```

## Step B+: MDD-Constrained Sharpe Frontier

```powershell
python ver3\scripts\python\run_stepB_plus_mdd_constrained_sharpe_frontier.py --strict
```

常用轻量调试：

```powershell
python ver3\scripts\python\run_stepB_plus_mdd_constrained_sharpe_frontier.py --strict --skip-plots --no-write-report --grid-step 0.05
```

输出：

```text
outputs/ver3_0_stepB_plus_mdd_constrained_sharpe_frontier/
```

核心文件：

```text
summary/ver3_0_stepB_plus_frontier_summary_default.csv
summary/ver3_0_stepB_plus_frontier_summary_relaxed.csv
summary/ver3_0_stepB_plus_best_weights_by_drawdown_target.csv
summary/ver3_0_stepB_plus_comparison_vs_fixed_weight_baselines.csv
summary/ver3_0_stepB_plus_universeA_vs_universeB_frontier_comparison.csv
summary/ver3_0_stepB_plus_validation_summary.csv
reports/ver3_0_stepB_plus_mdd_constrained_sharpe_frontier_report.md
```

`ver3/outputs/ver3_0_stepB_plus_output_index.md` 只是轻量索引，不放大 CSV 或 PNG。

## Step C: Robustness and Stability Diagnostics

```powershell
python ver3\scripts\python\run_stepC_robustness_stability_diagnostics.py --strict
```

常用轻量调试：

```powershell
python ver3\scripts\python\run_stepC_robustness_stability_diagnostics.py --strict --skip-plots
```

输出：

```text
outputs/ver3_0_stepC_robustness_stability_diagnostics/
```

核心文件：

```text
summary/ver3_0_stepC_candidate_full_sample_summary.csv
summary/ver3_0_stepC_stability_scorecard.csv
summary/ver3_0_stepC_recommended_candidate_table.csv
events/ver3_0_stepC_event_exclusion_summary.csv
rolling/ver3_0_stepC_rolling_stability_summary.csv
cost/ver3_0_stepC_cost_sensitivity_summary.csv
reports/ver3_0_stepC_robustness_stability_diagnostics_report.md
```

`ver3/outputs/ver3_0_stepC_output_index.md` 只是轻量索引，不放大 CSV、PNG 或正式报告。

## Wrapper Usage

从任意位置运行：

```powershell
powershell -ExecutionPolicy Bypass -File ver3\scripts\run_stepB_fixed_weight_universe.ps1 --strict
powershell -ExecutionPolicy Bypass -File ver3\scripts\run_stepB_plus.ps1 --strict
powershell -ExecutionPolicy Bypass -File ver3\scripts\run_stepC_robustness.ps1 --strict
```

包装器只负责定位仓库根目录并调用真实脚本。Step A、Step B、Step B+ 和 Step C 的真实 runner 在 `ver3/scripts/python/`；组合层模块化逻辑分别在 `ver3/src/covered_call_mini_ver3/stepB/`、`ver3/src/covered_call_mini_ver3/stepB_plus/` 和 `ver3/src/covered_call_mini_ver3/stepC_robustness/`。

根目录 `scripts/run_ver3_0_stepA_*.py` 仍可使用，但现在只是兼容入口。
