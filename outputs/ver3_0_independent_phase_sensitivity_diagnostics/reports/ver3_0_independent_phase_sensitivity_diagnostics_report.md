# Independent Diagnostic: Phase Sensitivity Diagnostics for Covered-Call Sleeves

## 1. Research Goal / 研究目的

本实验是独立于 ver3 主实验线的旁路诊断，用于检验已经进入主线研究的 selected sleeves 与 candidate portfolios 是否对 inception-date / roll-calendar phase 高度敏感。

本实验不新增 DTE、delta、moneyness、TP、Touch-K 或动态权重，不纳入 588000，也不替换 `B_default_D20`。它只提供 phase robustness evidence，可作为后续 final appendix / robustness diagnostic 使用。

## 2. Project Structure Note / 工程结构说明

- 当前 `ver3/` 仍是主项目入口。
- phase sensitivity 代码位于 `ver3/scripts/python/` 与 `ver3/src/covered_call_mini_ver3/diagnostics/phase_sensitivity/`。
- 真实实验输出位于根目录 `outputs/ver3_0_independent_phase_sensitivity_diagnostics/`。
- `ver3/outputs/` 只保留轻量索引。
- 本实验不修改 Step A / Step B / Step B+ / Step C / Step D 的已有输出。

## 3. Methodology / 方法

- Phase grid: `h = 0..20` 个交易日，从 2022-09-19 起按共同 ETF 交易日向后平移。
- ETF BuyHold 使用 shifted window 直接计算。
- covered-call sleeves 不截取 h=0 return panel；每个 phase 都以 shifted inception date 作为第一笔 rebalance date，重新选第一张 call，并由到期结算日驱动后续 roll schedule。
- 指标分为 natural shifted window 与 common evaluation window；主表优先解读 common window。
- phase ensemble 使用共同窗口中各 phase 的日收益等权平均，用于诊断 staggered calendar 是否能降低 phase risk。

## 4. Target Sleeves / 目标 sleeves

| sleeve_name                  |   phase_count |   sharpe_median |   sharpe_std | mdd_p75   | option_leg_median   |   phase_fragility_score | phase_robustness_label   |
|:-----------------------------|--------------:|----------------:|-------------:|:----------|:--------------------|------------------------:|:-------------------------|
| 510300_DTE30_D40_Q70_Hold    |            21 |           0.798 |        0.004 | 16.45%    | -0.02%              |                   0.005 | High Phase Robustness    |
| 510050_DTE30_D40_Q70_Hold    |            21 |           0.709 |        0.013 | 14.71%    | 0.84%               |                   0.019 | High Phase Robustness    |
| 510300_ETF_BuyHold           |            21 |           0.563 |        0     | 24.19%    | 0.00%               |                   0     | Low Phase Robustness     |
| 510500_ETF_BuyHold           |            21 |           0.607 |        0     | 30.16%    | 0.00%               |                   0     | Low Phase Robustness     |
| 159915_ETF_BuyHold           |            21 |           0.689 |        0     | 40.88%    | 0.00%               |                   0     | Low Phase Robustness     |
| 159915_DTE30_OTM5up_Q50_Hold |            21 |           0.644 |        0.004 | 37.69%    | -5.69%              |                   0.006 | Low Phase Robustness     |
| 510050_ETF_BuyHold           |            21 |           0.455 |        0     | 21.59%    | 0.00%               |                   0     | Medium Phase Robustness  |

## 5. Target Portfolios / 目标组合

| portfolio_name      |   phase_count |   sharpe_median |   sharpe_std | mdd_p75   | option_leg_median   |   phase_fragility_score |   phase_robust_score | phase_robustness_label   |
|:--------------------|--------------:|----------------:|-------------:|:----------|:--------------------|------------------------:|---------------------:|:-------------------------|
| B_default_D18       |            21 |           0.79  |        0.003 | 17.34%    | -0.29%              |                   0.004 |                0.788 | High Phase Robustness    |
| B_default_D20       |            21 |           0.784 |        0.003 | 19.21%    | -0.74%              |                   0.004 |                0.782 | High Phase Robustness    |
| B_default_D22       |            21 |           0.773 |        0.003 | 21.24%    | -1.24%              |                   0.004 |                0.771 | High Phase Robustness    |
| A_default_D25       |            21 |           0.749 |        0.003 | 24.03%    | -1.83%              |                   0.004 |                0.747 | High Phase Robustness    |
| A_Selected_50_30_20 |            21 |           0.725 |        0.002 | 24.14%    | -1.15%              |                   0.003 |                0.724 | High Phase Robustness    |

## 6. Phase Metrics / 相位指标分布

Common evaluation window 是主读数。Natural shifted window 已保留在 CSV，用于观察真实不同入场日的自然样本差异；但因为样本长度略有不同，不作为主排名依据。

关键图表：

- `C:\Users\WIN11\Desktop\CCFund\ETF备兑策略设计\covered_call_mini\outputs\ver3_0_independent_phase_sensitivity_diagnostics\figures\ver3_0_phase_sharpe_distribution.png`
- `C:\Users\WIN11\Desktop\CCFund\ETF备兑策略设计\covered_call_mini\outputs\ver3_0_independent_phase_sensitivity_diagnostics\figures\ver3_0_phase_mdd_distribution.png`
- `C:\Users\WIN11\Desktop\CCFund\ETF备兑策略设计\covered_call_mini\outputs\ver3_0_independent_phase_sensitivity_diagnostics\figures\ver3_0_phase_option_leg_distribution.png`
- `C:\Users\WIN11\Desktop\CCFund\ETF备兑策略设计\covered_call_mini\outputs\ver3_0_independent_phase_sensitivity_diagnostics\figures\ver3_0_phase_heatmap_candidate_metrics.png`
- `C:\Users\WIN11\Desktop\CCFund\ETF备兑策略设计\covered_call_mini\outputs\ver3_0_independent_phase_sensitivity_diagnostics\figures\ver3_0_phase_ensemble_vs_single_nav.png`
- `C:\Users\WIN11\Desktop\CCFund\ETF备兑策略设计\covered_call_mini\outputs\ver3_0_independent_phase_sensitivity_diagnostics\figures\ver3_0_phase_cycle_concentration.png`

## 7. Phase Robustness Summary / 相位稳健性总结

- 最高 phase fragility sleeve: `510050_DTE30_D40_Q70_Hold`，fragility score = 0.019。
- phase robust score 最高的 candidate: `B_default_D18`，label = `High Phase Robustness`。
- `B_default_D20` label = `High Phase Robustness`，Sharpe median = 0.784，MDD p75 = 19.21%。

`B_default_D20` 的 phase 结果应理解为主线候选可信度的压力测试，而不是选择最佳入场 phase 的优化器。如果其 median / p25 / ensemble 读数仍然可接受，才增强主线候选可信度；如果 dispersion 过大，则应在 final appendix 中加入 phase risk caveat。

## 8. Cycle Attribution / 周期归因

| sleeve_name                  |   option_cycle_count | top_1_abs_cycle_pnl_share   | top_3_abs_cycle_pnl_share   |   option_cycle_hhi | positive_cycle_rate   |   leave_one_cycle_out_sharpe_min | leave_one_cycle_out_option_leg_sign_flip_flag   |
|:-----------------------------|---------------------:|:----------------------------|:----------------------------|-------------------:|:----------------------|---------------------------------:|:------------------------------------------------|
| 159915_DTE30_OTM5up_Q50_Hold |                   43 | 26.17%                      | 45.92%                      |              0.102 | 74.70%                |                            0.372 | False                                           |
| 510050_DTE30_D40_Q70_Hold    |                   43 | 18.05%                      | 28.37%                      |              0.053 | 71.20%                |                            0.315 | False                                           |
| 510300_DTE30_D40_Q70_Hold    |                   43 | 20.20%                      | 32.97%                      |              0.063 | 74.70%                |                            0.484 | True                                            |

## 9. Staggered Ensemble / 相位分散组合

Sleeve ensemble summary:

| sleeve_name                  |   phase_count | annualized_return_cagr   |   sharpe_daily_mean | max_drawdown   | option_leg_annualized_pnl_contribution   |   final_nav |
|:-----------------------------|--------------:|:-------------------------|--------------------:|:---------------|:-----------------------------------------|------------:|
| 159915_DTE30_OTM5up_Q50_Hold |            21 | 13.81%                   |               0.643 | 37.69%         | -5.68%                                   |       1.53  |
| 159915_ETF_BuyHold           |            21 | 18.39%                   |               0.689 | 40.88%         | 0.00%                                    |       1.75  |
| 510050_DTE30_D40_Q70_Hold    |            21 | 8.00%                    |               0.716 | 14.71%         | 1.03%                                    |       1.263 |
| 510050_ETF_BuyHold           |            21 | 6.27%                    |               0.455 | 21.59%         | 0.00%                                    |       1.192 |
| 510300_DTE30_D40_Q70_Hold    |            21 | 9.45%                    |               0.796 | 16.45%         | 0.02%                                    |       1.334 |
| 510300_ETF_BuyHold           |            21 | 8.66%                    |               0.563 | 24.19%         | 0.00%                                    |       1.299 |
| 510500_ETF_BuyHold           |            21 | 11.53%                   |               0.607 | 30.16%         | 0.00%                                    |       1.445 |

Portfolio ensemble summary:

| portfolio_name      |   phase_count | annualized_return_cagr   |   sharpe_daily_mean | max_drawdown   | option_leg_annualized_pnl_contribution   |   final_nav |
|:--------------------|--------------:|:-------------------------|--------------------:|:---------------|:-----------------------------------------|------------:|
| A_Selected_50_30_20 |            21 | 11.29%                   |               0.725 | 24.14%         | -1.13%                                   |       1.42  |
| A_default_D25       |            21 | 11.28%                   |               0.748 | 24.03%         | -1.81%                                   |       1.415 |
| B_default_D18       |            21 | 9.62%                    |               0.791 | 17.34%         | -0.22%                                   |       1.339 |
| B_default_D20       |            21 | 10.09%                   |               0.785 | 19.21%         | -0.69%                                   |       1.36  |
| B_default_D22       |            21 | 10.59%                   |               0.773 | 21.24%         | -1.20%                                   |       1.382 |

Ensemble comparison:

| portfolio_name      |   ensemble_sharpe |   phase0_sharpe |   phase_median_sharpe |   delta_sharpe_vs_phase0 | ensemble_mdd   | phase0_mdd   | delta_mdd_vs_phase0   | ensemble_improves_sharpe_dispersion_proxy   |
|:--------------------|------------------:|----------------:|----------------------:|-------------------------:|:---------------|:-------------|:----------------------|:--------------------------------------------|
| A_Selected_50_30_20 |             0.725 |           0.725 |                 0.725 |                   -0     | 24.14%         | 24.14%       | 0.00%                 | False                                       |
| A_default_D25       |             0.748 |           0.749 |                 0.749 |                   -0.001 | 24.03%         | 24.03%       | 0.00%                 | False                                       |
| B_default_D18       |             0.791 |           0.789 |                 0.79  |                    0.002 | 17.34%         | 17.34%       | -0.00%                | True                                        |
| B_default_D20       |             0.785 |           0.784 |                 0.784 |                    0.001 | 19.21%         | 19.21%       | 0.00%                 | False                                       |
| B_default_D22       |             0.773 |           0.772 |                 0.773 |                    0     | 21.24%         | 21.24%       | 0.00%                 | False                                       |

## 10. Interpretation / 研究解释

phase sensitivity 是 covered-call 策略的真实风险来源之一，因为起始日会改变第一张 option、后续 roll calendar、strike selection、premium、payoff burden 与 option-leg path。本实验不把 best phase 当成推荐，也不把 premium 当成立即利润；option leg contribution 一律按净 P&L contribution 解读。

如果某个 sleeve 的 option-leg 由少数 cycles 主导，应降低其 classification confidence。若 ensemble 明显降低 MDD 或 Sharpe dispersion，可以把 staggered calendar ensemble 作为执行层面的 risk mitigation 方案，但不自动替换主线 single-phase 结果。

## 11. Conclusion / 结论

- 建议将 phase diagnostics 纳入 final appendix：是。
- 是否把主线候选从 single-phase `B_default_D20` 改为 phase-ensemble `B_default_D20`：本报告只给 evidence，不自动替换；若 ensemble 在 common window 中同时改善 Sharpe/MDD 稳定性，可在执行层作为 risk mitigation 讨论。
- 是否需要对 sleeve 增加 phase risk caveat：对 label 为 `Phase Fragile` 或 cycle concentration 偏高的 sleeve 应增加。
- 后续建议：保留 phase-aware entry diagnostic，避免未来把单一起始日表现误读为稳定结构优势。

## Validation / 校验结果

| check_name                                        | passed   | detail                                                                                                                                                                                      |
|:--------------------------------------------------|:---------|:--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| phase_rebuild_supported_for_covered_call_sleeves  | True     | covered-call phases ran                                                                                                                                                                     |
| phase_shift_grid_non_empty                        | True     | 21 rows                                                                                                                                                                                     |
| phase_inception_dates_valid                       | True     | inception dates populated                                                                                                                                                                   |
| covered_call_paths_rebuilt_not_sliced             | True     | engine wrapper rebuild flag                                                                                                                                                                 |
| natural_window_metrics_non_empty                  | True     | natural metrics                                                                                                                                                                             |
| common_window_metrics_non_empty                   | True     | common metrics                                                                                                                                                                              |
| candidate_portfolios_built                        | True     | portfolio metrics                                                                                                                                                                           |
| ensemble_outputs_non_empty_or_marked_skipped      | True     | ensemble summary                                                                                                                                                                            |
| cycle_attribution_available_or_marked_unavailable | True     | cycle artifact                                                                                                                                                                              |
| nav_positive                                      | True     | sleeve NAV                                                                                                                                                                                  |
| max_drawdown_positive_magnitude                   | True     | MDD uses positive magnitude                                                                                                                                                                 |
| output_csv_rows_nonzero                           | True     | nonzero rows                                                                                                                                                                                |
| report_generated                                  | True     | C:\Users\WIN11\Desktop\CCFund\ETF备兑策略设计\covered_call_mini\outputs\ver3_0_independent_phase_sensitivity_diagnostics\reports\ver3_0_independent_phase_sensitivity_diagnostics_report.md |
| real_outputs_written_to_root_outputs              | True     | C:\Users\WIN11\Desktop\CCFund\ETF备兑策略设计\covered_call_mini\outputs\ver3_0_independent_phase_sensitivity_diagnostics                                                                    |
| no_large_outputs_written_to_ver3_outputs          | True     | only index intended                                                                                                                                                                         |
| no_outputs_written_outside_allowed_dirs           | True     | output scope                                                                                                                                                                                |
| no_stepA_to_D_outputs_modified                    | True     | phase diagnostic writes only its own output tree                                                                                                                                            |
| no_ver2_files_modified                            | True     | ver2 files are read-only inputs                                                                                                                                                             |
| frozen_metrics_not_modified                       | True     | src/metrics is read-only input                                                                                                                                                              |
| ver3_output_index_generated                       | True     | C:\Users\WIN11\Desktop\CCFund\ETF备兑策略设计\covered_call_mini\ver3\outputs\ver3_0_phase_sensitivity_output_index.md                                                                       |
