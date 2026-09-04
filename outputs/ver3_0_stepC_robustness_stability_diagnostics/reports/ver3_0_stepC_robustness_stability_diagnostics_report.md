# ver3.0 Step C：稳健性与稳定性诊断

## 研究目的

Step C 不新增期权参数，也不做动态权重。它只围绕 Step B+ 选出的代表性前沿点，检查这些候选权重是否依赖少数事件窗口、是否对滚动子样本稳定、是否对更保守成本假设敏感，以及 default / relaxed 权重边界是否改变研究解释。

本报告是样本内稳健性诊断，不是样本外最优声明，也不是实盘承诺。

## 工程结构说明

- 当前 `ver3/` 是主项目入口。
- Step C 代码位于 `ver3/scripts/python/` 与 `ver3/src/covered_call_mini_ver3/stepC_robustness/`。
- 真实实验输出位于根目录 `outputs/ver3_0_stepC_robustness_stability_diagnostics/`。
- `ver3/outputs/` 只保留轻量索引。
- 旧 engine 和旧证据保留在 `ver2_downside_protection/`，本实验不修改。
- 指标口径依赖冻结的 `src/metrics/`，本实验只读调用。

## 候选组合定义

| portfolio_name                       | source_portfolio_name                | universe_short   | role                         |   etf_code | sleeve_key                        | sleeve_name               | weight   |
|:-------------------------------------|:-------------------------------------|:-----------------|:-----------------------------|-----------:|:----------------------------------|:--------------------------|:---------|
| B_v31_D20_51030070_51005014_15991516 | B_v31_D20_51030070_51005014_15991516 | B                | 3.1 主线组合（D20 回撤预算） |     510300 | 510300__510300_DTE30_D40_Q70_Hold | 510300_DTE30_D40_Q70_Hold | 70.00%   |
| B_v31_D20_51030070_51005014_15991516 | B_v31_D20_51030070_51005014_15991516 | B                | 3.1 主线组合（D20 回撤预算） |     510050 | 510050__510050_DTE30_D40_Q70_Hold | 510050_DTE30_D40_Q70_Hold | 14.00%   |
| B_v31_D20_51030070_51005014_15991516 | B_v31_D20_51030070_51005014_15991516 | B                | 3.1 主线组合（D20 回撤预算） |     159915 | 159915__159915_DTE30_D20_Q10_Hold | 159915_DTE30_D20_Q10_Hold | 16.00%   |

## 全样本表现

| portfolio_name                       | role                         | annualized_return_cagr   |   sharpe_daily_mean | annualized_volatility   | max_drawdown   |   calmar_ratio |   sortino_ratio | option_leg_annualized_pnl_contribution   |   final_nav |
|:-------------------------------------|:-----------------------------|:-------------------------|--------------------:|:------------------------|:---------------|---------------:|----------------:|:-----------------------------------------|------------:|
| B_v31_D20_51030070_51005014_15991516 | 3.1 主线组合（D20 回撤预算） | 9.80%                    |               0.731 | 14.15%                  | 19.96%         |          0.491 |           1.228 | 0.17%                                    |       1.386 |

样本窗口：

| window_name                | sample_start   | sample_end   | n_obs   | note                                                           |
|:---------------------------|:---------------|:-------------|:--------|:---------------------------------------------------------------|
| stepC_common_long_sample   | 2022-09-30     | 2026-05-27   | 881     | 四个候选组合对齐后的共同非缺失样本。                           |
| requested_stepC_sample     | 2022-09-30     | 2026-05-27   |         | 任务指定的长样本窗口；若与实际不同，报告应以实际共同样本解释。 |
| candidate_nav_sample_check | 2022-09-30     | 2026-05-27   | 881     | 每个候选组合 NAV 的最小观察数。                                |
| input_file_count           |                |              | 22      | 本次 Step C 读取的上游输入文件数量。                           |

## 事件窗口剔除诊断

`exclude_all_extreme_event_metrics` 是同时剔除自动识别的极端上涨、极端下跌与手动事件窗口后的结果。重点观察 `delta_sharpe_vs_full_sample`、`delta_mdd_vs_full_sample` 和 `delta_cagr_vs_full_sample`。

| portfolio_name                       | diagnostic_case                   |   removed_trading_days | annualized_return_cagr   |   sharpe_daily_mean | max_drawdown   |   delta_sharpe_vs_full_sample | delta_mdd_vs_full_sample   | delta_cagr_vs_full_sample   |
|:-------------------------------------|:----------------------------------|-----------------------:|:-------------------------|--------------------:|:---------------|------------------------------:|:---------------------------|:----------------------------|
| B_v31_D20_51030070_51005014_15991516 | full_sample_metrics               |                      0 | 9.80%                    |               0.731 | 19.96%         |                         0     | 0.00%                      | 0.00%                       |
| B_v31_D20_51030070_51005014_15991516 | exclude_downside_event_metrics    |                     11 | 11.42%                   |               0.862 | 19.96%         |                         0.131 | 0.00%                      | 1.62%                       |
| B_v31_D20_51030070_51005014_15991516 | exclude_upside_event_metrics      |                     11 | 5.37%                    |               0.467 | 21.85%         |                        -0.264 | 1.89%                      | -4.43%                      |
| B_v31_D20_51030070_51005014_15991516 | exclude_all_extreme_event_metrics |                     22 | 6.89%                    |               0.599 | 19.96%         |                        -0.132 | 0.00%                      | -2.91%                      |

## 滚动稳定性

滚动稳定性用于观察候选组合是否只在个别时间段表现突出。`ranking_stability_score` 表示在同一滚动窗口结束日中，候选组合 Sharpe 排名前二的比例。

| portfolio_name                       |   window_days |   n_windows |   rolling_sharpe_mean |   rolling_sharpe_median |   rolling_sharpe_p25 |   rolling_sharpe_p75 | rolling_mdd_mean   | rolling_mdd_p75   | worst_rolling_mdd   | positive_rolling_cagr_rate   | positive_rolling_sharpe_rate   | ranking_stability_score   |
|:-------------------------------------|--------------:|------------:|----------------------:|------------------------:|---------------------:|---------------------:|:-------------------|:------------------|:--------------------|:-----------------------------|:-------------------------------|:--------------------------|
| B_v31_D20_51030070_51005014_15991516 |           252 |         630 |                 0.496 |                   0.62  |               -0.495 |                1.418 | 13.04%             | 15.47%            | 19.96%              | 64.44%                       | 64.76%                         | 100.00%                   |
| B_v31_D20_51030070_51005014_15991516 |           504 |         378 |                 0.618 |                   0.455 |                0.153 |                1.076 | 16.11%             | 18.95%            | 19.96%              | 88.36%                       | 98.15%                         | 100.00%                   |

## 成本敏感性

成本敏感性使用组合日度净期权腿收益施加年化 bps 成本拖累。该方法是透明近似，不伪造不存在的交易明细。

| portfolio_name                       | cost_scenario          |   extra_cost_bps | annualized_return_cagr   |   sharpe_daily_mean | max_drawdown   | option_leg_annualized_pnl_contribution   |   delta_sharpe_vs_base | delta_mdd_vs_base   | option_leg_still_positive   | interpretation_hint                       |
|:-------------------------------------|:-----------------------|-----------------:|:-------------------------|--------------------:|:---------------|:-----------------------------------------|-----------------------:|:--------------------|:----------------------------|:------------------------------------------|
| B_v31_D20_51030070_51005014_15991516 | base                   |                0 | 9.80%                    |               0.731 | 19.96%         | 0.17%                                    |                  0     | 0.00%               | True                        | 基础成本口径。                            |
| B_v31_D20_51030070_51005014_15991516 | option_cost_plus_10bps |               10 | 9.69%                    |               0.724 | 20.03%         | 0.07%                                    |                 -0.007 | 0.08%               | True                        | 额外成本下期权腿仍为正，Sharpe 变化较小。 |
| B_v31_D20_51030070_51005014_15991516 | option_cost_plus_20bps |               20 | 9.58%                    |               0.717 | 20.11%         | -0.03%                                   |                 -0.014 | 0.16%               | False                       | 额外成本下期权腿转弱，需要谨慎解释。      |
| B_v31_D20_51030070_51005014_15991516 | option_cost_plus_30bps |               30 | 9.47%                    |               0.71  | 20.19%         | -0.13%                                   |                 -0.021 | 0.24%               | False                       | 额外成本下期权腿转弱，需要谨慎解释。      |
| B_v31_D20_51030070_51005014_15991516 | option_cost_plus_5bps  |                5 | 9.74%                    |               0.728 | 19.99%         | 0.12%                                    |                 -0.004 | 0.04%               | True                        | 额外成本下期权腿仍为正，Sharpe 变化较小。 |

## 权重边界敏感性

该诊断解释 Step B+ 中 default 与 relaxed 约束差异，重点看中间资产 510500 / 510050 是否被压到 0，以及前沿是否退化为 510300 + 159915 杠铃。

| constraint_set   | D_star   | universe_short   | portfolio_name                           |   middle_asset | middle_asset_weight   | middle_asset_weight_is_zero   | barbell_flag   | weight_510300   | weight_159915   |   sharpe_daily_mean | max_drawdown   | interpretation_hint                                           |
|:-----------------|:---------|:-----------------|:-----------------------------------------|---------------:|:----------------------|:------------------------------|:---------------|:----------------|:----------------|--------------------:|:---------------|:--------------------------------------------------------------|
| default          | 22.00%   | A                | A_default_D22_51030070_51050009_15991521 |         510500 | 9.00%                 | False                         | False          | 70.00%          | 21.00%          |               0.73  | 21.94%         | default 下 510500 保留正权重，最小权重约束仍有解释价值。      |
| default          | 25.00%   | A                | A_default_D25_51030070_51050009_15991521 |         510500 | 9.00%                 | False                         | False          | 70.00%          | 21.00%          |               0.73  | 21.94%         | default 下 510500 保留正权重，最小权重约束仍有解释价值。      |
| default          | 30.00%   | A                | A_default_D30_51030070_51050009_15991521 |         510500 | 9.00%                 | False                         | False          | 70.00%          | 21.00%          |               0.73  | 21.94%         | default 下 510500 保留正权重，最小权重约束仍有解释价值。      |
| default          | 18.00%   | B                | B_default_D18_51030070_51005020_15991510 |         510050 | 20.00%                | False                         | False          | 70.00%          | 10.00%          |               0.701 | 17.87%         | default 下 510050 保留正权重，最小权重约束仍有解释价值。      |
| default          | 20.00%   | B                | B_default_D20_51030070_51005012_15991518 |         510050 | 12.00%                | False                         | False          | 70.00%          | 18.00%          |               0.717 | 19.99%         | default 下 510050 保留正权重，最小权重约束仍有解释价值。      |
| default          | 22.00%   | B                | B_default_D22_51030070_51005005_15991525 |         510050 | 5.00%                 | False                         | False          | 70.00%          | 25.00%          |               0.725 | 21.80%         | default 下 510050 保留正权重，最小权重约束仍有解释价值。      |
| default          | 25.00%   | B                | B_default_D25_51030070_51005005_15991525 |         510050 | 5.00%                 | False                         | False          | 70.00%          | 25.00%          |               0.725 | 21.80%         | default 下 510050 保留正权重，最小权重约束仍有解释价值。      |
| default          | 30.00%   | B                | B_default_D30_51030070_51005005_15991525 |         510050 | 5.00%                 | False                         | False          | 70.00%          | 25.00%          |               0.725 | 21.80%         | default 下 510050 保留正权重，最小权重约束仍有解释价值。      |
| relaxed          | 20.00%   | A                | A_relaxed_D20_51030079_51050008_15991513 |         510500 | 8.00%                 | False                         | False          | 79.00%          | 13.00%          |               0.729 | 19.99%         | relaxed 下 510500 保留正权重，最小权重约束仍有解释价值。      |
| relaxed          | 22.00%   | A                | A_relaxed_D22_51030074_51050007_15991519 |         510500 | 7.00%                 | False                         | False          | 74.00%          | 19.00%          |               0.73  | 21.28%         | relaxed 下 510500 保留正权重，最小权重约束仍有解释价值。      |
| relaxed          | 25.00%   | A                | A_relaxed_D25_51030074_51050007_15991519 |         510500 | 7.00%                 | False                         | False          | 74.00%          | 19.00%          |               0.73  | 21.28%         | relaxed 下 510500 保留正权重，最小权重约束仍有解释价值。      |
| relaxed          | 30.00%   | A                | A_relaxed_D30_51030074_51050007_15991519 |         510500 | 7.00%                 | False                         | False          | 74.00%          | 19.00%          |               0.73  | 21.28%         | relaxed 下 510500 保留正权重，最小权重约束仍有解释价值。      |
| relaxed          | 18.00%   | B                | B_relaxed_D18_51030080_51005011_15991509 |         510050 | 11.00%                | False                         | False          | 80.00%          | 9.00%           |               0.711 | 17.93%         | relaxed 下 510050 保留正权重，最小权重约束仍有解释价值。      |
| relaxed          | 20.00%   | B                | B_relaxed_D20_51030079_51005004_15991517 |         510050 | 4.00%                 | False                         | False          | 79.00%          | 17.00%          |               0.725 | 19.99%         | relaxed 下 510050 保留正权重，最小权重约束仍有解释价值。      |
| relaxed          | 22.00%   | B                | B_relaxed_D22_51030077_51005000_15991523 |         510050 | 0.00%                 | True                          | True           | 77.00%          | 23.00%          |               0.729 | 21.49%         | relaxed 下 510050 被压到 0，组合退化为 510300 + 159915 杠铃。 |
| relaxed          | 25.00%   | B                | B_relaxed_D25_51030077_51005000_15991523 |         510050 | 0.00%                 | True                          | True           | 77.00%          | 23.00%          |               0.729 | 21.49%         | relaxed 下 510050 被压到 0，组合退化为 510300 + 159915 杠铃。 |
| relaxed          | 30.00%   | B                | B_relaxed_D30_51030077_51005000_15991523 |         510050 | 0.00%                 | True                          | True           | 77.00%          | 23.00%          |               0.729 | 21.49%         | relaxed 下 510050 被压到 0，组合退化为 510300 + 159915 杠铃。 |

杠铃诊断：

| universe_short   | D_star   | default_portfolio                        | relaxed_portfolio                        |   middle_asset | default_middle_asset_weight   | relaxed_middle_asset_weight   | middle_asset_weight_delta_relaxed_minus_default   | default_barbell_flag   | relaxed_barbell_flag   |   delta_sharpe_relaxed_minus_default | delta_mdd_relaxed_minus_default   | interpretation_hint                                                             |
|:-----------------|:---------|:-----------------------------------------|:-----------------------------------------|---------------:|:------------------------------|:------------------------------|:--------------------------------------------------|:-----------------------|:-----------------------|-------------------------------------:|:----------------------------------|:--------------------------------------------------------------------------------|
| A                | 22.00%   | A_default_D22_51030070_51050009_15991521 | A_relaxed_D22_51030074_51050007_15991519 |         510500 | 9.00%                         | 7.00%                         | -2.00%                                            | False                  | False                  |                                0     | -0.66%                            | default 与 relaxed 的中间资产权重接近，边界敏感性较低。                         |
| A                | 25.00%   | A_default_D25_51030070_51050009_15991521 | A_relaxed_D25_51030074_51050007_15991519 |         510500 | 9.00%                         | 7.00%                         | -2.00%                                            | False                  | False                  |                                0     | -0.66%                            | default 与 relaxed 的中间资产权重接近，边界敏感性较低。                         |
| A                | 30.00%   | A_default_D30_51030070_51050009_15991521 | A_relaxed_D30_51030074_51050007_15991519 |         510500 | 9.00%                         | 7.00%                         | -2.00%                                            | False                  | False                  |                                0     | -0.66%                            | default 与 relaxed 的中间资产权重接近，边界敏感性较低。                         |
| B                | 18.00%   | B_default_D18_51030070_51005020_15991510 | B_relaxed_D18_51030080_51005011_15991509 |         510050 | 20.00%                        | 11.00%                        | -9.00%                                            | False                  | False                  |                                0.01  | 0.06%                             | default 与 relaxed 权重差异较明显，应在报告中单独解释。                         |
| B                | 20.00%   | B_default_D20_51030070_51005012_15991518 | B_relaxed_D20_51030079_51005004_15991517 |         510050 | 12.00%                        | 4.00%                         | -8.00%                                            | False                  | False                  |                                0.008 | -0.00%                            | default 与 relaxed 权重差异较明显，应在报告中单独解释。                         |
| B                | 22.00%   | B_default_D22_51030070_51005005_15991525 | B_relaxed_D22_51030077_51005000_15991523 |         510050 | 5.00%                         | 0.00%                         | -5.00%                                            | False                  | True                   |                                0.004 | -0.31%                            | relaxed 放开最小权重后，中间资产被压到 0，说明 default 最小权重有解释约束作用。 |
| B                | 25.00%   | B_default_D25_51030070_51005005_15991525 | B_relaxed_D25_51030077_51005000_15991523 |         510050 | 5.00%                         | 0.00%                         | -5.00%                                            | False                  | True                   |                                0.004 | -0.31%                            | relaxed 放开最小权重后，中间资产被压到 0，说明 default 最小权重有解释约束作用。 |
| B                | 30.00%   | B_default_D30_51030070_51005005_15991525 | B_relaxed_D30_51030077_51005000_15991523 |         510050 | 5.00%                         | 0.00%                         | -5.00%                                            | False                  | True                   |                                0.004 | -0.31%                            | relaxed 放开最小权重后，中间资产被压到 0，说明 default 最小权重有解释约束作用。 |

## 稳定性评分

稳定性评分是研究辅助，不是严格统计显著性检验。

| portfolio_name                       | role                         |   full_sample_sharpe | full_sample_mdd   | event_exclusion_sharpe_stability   | event_exclusion_mdd_stability   | rolling_sharpe_stability   | rolling_mdd_stability   | cost_sensitivity_score   | option_leg_robustness_score   | weight_interpretability_score   | overall_stability_score   | overall_stability_label   |
|:-------------------------------------|:-----------------------------|---------------------:|:------------------|:-----------------------------------|:--------------------------------|:---------------------------|:------------------------|:-------------------------|:------------------------------|:--------------------------------|:--------------------------|:--------------------------|
| B_v31_D20_51030070_51005014_15991516 | 3.1 主线组合（D20 回撤预算） |                0.731 | 19.96%            | 81.88%                             | 100.00%                         | 64.76%                     | 100.00%                 | 97.10%                   | 60.00%                        | 100.00%                         | 86.25%                    | High Stability            |

## 研究解释

- `B_default_D20` 是主线 defensive-income candidate 的优先观察对象：它比 D18 少牺牲一些收益弹性，又比 D22 更贴近 20% 回撤预算。
- `B_default_D18` 更适合作为 strict defensive candidate，而不是收益主线。
- `B_default_D22` 是更平衡的防御成长候选，如果滚动稳定性不弱，可以作为 D20 的平衡对照。
- `A_default_D25` 是 growth comparison candidate，用于保留 Universe A 的成长分散化解释，不应直接替代防御收益主线。
- 如果候选点相对固定权重基准提升有限，报告主线应保留固定权重基准作为高可解释对照。

固定权重基准对比：

| portfolio_name                       | candidate_role               | universe_short   | baseline_portfolio_name   |   baseline_weight_scheme |   candidate_sharpe |   baseline_sharpe |   delta_sharpe_vs_baseline | candidate_mdd   | baseline_mdd   | delta_mdd_vs_baseline   | candidate_cagr   | baseline_cagr   | delta_cagr_vs_baseline   | interpretation_hint                       |
|:-------------------------------------|:-----------------------------|:-----------------|:--------------------------|-------------------------:|-------------------:|------------------:|---------------------------:|:----------------|:---------------|:------------------------|:-----------------|:----------------|:-------------------------|:------------------------------------------|
| B_v31_D20_51030070_51005014_15991516 | 3.1 主线组合（D20 回撤预算） | B                | B_Selected_40_40_20       |                 40_40_20 |              0.731 |             0.684 |                      0.048 | 19.96%          | 19.65%         | 0.31%                   | 9.80%            | 8.66%           | 1.13%                    | 候选组合提高 Sharpe，但回撤成本需要复核。 |
| B_v31_D20_51030070_51005014_15991516 | 3.1 主线组合（D20 回撤预算） | B                | B_Selected_50_30_20       |                 50_30_20 |              0.731 |             0.697 |                      0.034 | 19.96%          | 19.93%         | 0.02%                   | 9.80%            | 8.94%           | 0.86%                    | 候选组合提高 Sharpe，但回撤成本需要复核。 |
| B_v31_D20_51030070_51005014_15991516 | 3.1 主线组合（D20 回撤预算） | B                | B_Selected_70_20_10       |                 70_20_10 |              0.731 |             0.701 |                      0.03  | 19.96%          | 17.87%         | 2.09%                   | 9.80%            | 8.50%           | 1.30%                    | 候选组合提高 Sharpe，但回撤成本需要复核。 |

## 588000 说明

588000 仍然只属于 short-sample tech-growth extension，不纳入主线 Step C。这样可以保持 2022-09-30 至 2026-05-27 的共同长样本可比性。

## 结论

- 推荐主候选：`B_v31_D20_51030070_51005014_15991516`，定位为 `主线 defensive-income candidate`。
- 推荐对照候选：保留 `B_default_D22` 作为平衡对照，保留 `A_default_D25` 作为成长弹性对照。
- 当前结果支持形成研究看板中的候选组合族，但不应写成最终实盘答案。
- 如继续 Step D，应定位为可选的 dynamic weighting / covariance-learning layer；不应重新打开 DTE、delta、moneyness、TP 或 Touch-K 参数网格。

## 推荐表

| portfolio_name                       | recommendation_role             | overall_stability_label   | overall_stability_score   |   full_sample_sharpe | full_sample_mdd   | matched_baseline_for_context   |   delta_sharpe_vs_context_baseline | reason                                               | next_stage_suggestion          |
|:-------------------------------------|:--------------------------------|:--------------------------|:--------------------------|---------------------:|:------------------|:-------------------------------|-----------------------------------:|:-----------------------------------------------------|:-------------------------------|
| B_v31_D20_51030070_51005014_15991516 | 主线 defensive-income candidate | High Stability            | 86.25%                    |                0.731 | 19.96%            | B_Selected_40_40_20            |                              0.048 | 优先作为报告主线候选，后续只做稳健性解释和看板展示。 | 可进入 Step D 可选动态权重研究 |

## 校验结果

| 检查项                                       | 是否通过   | 说明                                                                 |
|:---------------------------------------------|:-----------|:---------------------------------------------------------------------|
| project_root_exists                          | 通过       | C:\Users\WIN11\Desktop\CCFund\ETF备兑策略设计\covered_call_mini      |
| ver3_root_exists                             | 通过       | C:\Users\WIN11\Desktop\CCFund\ETF备兑策略设计\covered_call_mini\ver3 |
| input_files_exist                            | 通过       | 所有 Step C 必需输入文件均存在                                       |
| required_candidate_portfolios_exist          | 通过       | 当前 Step C 候选组合已定义                                           |
| required_sleeves_exist                       | 通过       | 候选组合需要的 sleeve return 均存在                                  |
| candidates_same_sample                       | 通过       | 四个候选组合使用同一共同样本                                         |
| no_588000_in_main_stepC                      | 通过       | 588000 未进入 Step C 主线                                            |
| no_new_option_parameter_sleeves              | 通过       | 未引入 Q100/ATM/TP80/TouchK 等新参数 sleeve                          |
| weights_sum_to_one                           | 通过       | 候选组合权重和均为 1                                                 |
| nav_initial_reference_is_one                 | 通过       | NAV 使用 initial_nav=1.0                                             |
| nav_positive                                 | 通过       | 所有候选 NAV 均为正                                                  |
| max_drawdown_positive_magnitude              | 通过       | 回撤幅度使用正数口径                                                 |
| rolling_outputs_non_empty                    | 通过       | 滚动与分段指标输出非空                                               |
| event_outputs_non_empty                      | 通过       | 事件窗口输出非空                                                     |
| cost_outputs_non_empty_or_marked_unavailable | 通过       | 成本敏感性输出非空                                                   |
| output_csv_rows_nonzero                      | 通过       | 所有 CSV 输出均包含有效行                                            |
| report_generated                             | 通过       | 中文 Markdown 报告已生成                                             |
| real_outputs_written_to_root_outputs         | 通过       | 真实输出写入根目录 outputs                                           |
| no_large_outputs_written_to_ver3_outputs     | 通过       | ver3/outputs 只保留轻量索引                                          |
| no_outputs_written_outside_allowed_dirs      | 通过       | 输出路径均在允许目录内                                               |
| no_ver2_files_modified                       | 通过       | 未写入冻结 ver2 目录                                                 |
| frozen_metrics_not_modified                  | 通过       | 未写入冻结指标目录                                                   |
| ver3_output_index_generated                  | 通过       | ver3 轻量索引已生成                                                  |
