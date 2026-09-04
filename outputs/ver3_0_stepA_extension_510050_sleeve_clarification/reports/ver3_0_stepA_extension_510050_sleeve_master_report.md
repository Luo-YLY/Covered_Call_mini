# ver3.0 Step A-Extension | 510050 单 ETF 备兑 Sleeve 画像

## 1. 研究目的

此前 Step A 显示 510500 更适合作为 pure ETF BuyHold，而不是强行做 covered call。本扩展补充考察 510050：它是否能像 510300 一样，成为较稳定的 covered-call income / risk-control sleeve，并服务于备选 universe `510300 + 510050 + 159915`。

本报告只做单 ETF sleeve clarification，不做 fixed-weight portfolio、不做动态权重、不做均值方差优化。

## 2. 样本区间与数据说明

- 510050 DTE30 源数据可用区间：2021-01-29 至 2026-05-27
- 本次正式指标区间：2022-09-30 至 2026-05-27
- 期权路径来源：`outputs/ver2_downside_protection/ver2_1_dte_regime/`
- 510300 相关性参照：优先读取既有 Step A return panel，不修改其输出文件。

510050 可以覆盖 Step A 共同样本，因此没有强行填补期权交易数据。

## 3. 候选 sleeve 列表

- `510050_ETF_BuyHold`：纯 ETF baseline。
- `510050_DTE30_D40_Q50_Hold`：DTE30、目标 Delta 约 40、50% 覆盖率。
- `510050_DTE30_D40_Q70_Hold`：DTE30、目标 Delta 约 40、70% 覆盖率，主候选。
- `510050_DTE30_D40_Q100_Hold`：D40 全覆盖 stress / diagnostic。
- `510050_DTE30_ATM_Q100_Hold`：ATM 全覆盖 stress / diagnostic。

## 4. 主指标表

| sleeve_name                | classification           | recommendation_status       | annualized_return_cagr   |   sharpe_daily_mean | max_drawdown   |   calmar_ratio |   sortino_ratio | annualized_volatility   | option_leg_annualized_pnl_contribution   |
|:---------------------------|:-------------------------|:----------------------------|:-------------------------|--------------------:|:---------------|---------------:|----------------:|:------------------------|:-----------------------------------------|
| 510050_ETF_BuyHold         | Pure ETF Preferred       | rejected                    | 3.70%                    |               0.303 | 21.59%         |          0.171 |           0.53  | 16.45%                  | 0.00%                                    |
| 510050_DTE30_D40_Q50_Hold  | Positive Carry Overlay   | backup_for_portfolio_layer  | 4.98%                    |               0.439 | 16.71%         |          0.298 |           0.736 | 12.98%                  | 0.73%                                    |
| 510050_DTE30_D40_Q70_Hold  | Positive Carry Overlay   | primary_for_portfolio_layer | 5.44%                    |               0.506 | 14.70%         |          0.37  |           0.825 | 11.85%                  | 1.02%                                    |
| 510050_DTE30_D40_Q100_Hold | Stress / Diagnostic Only | diagnostic_only             | 6.05%                    |               0.608 | 11.61%         |          0.521 |           0.947 | 10.59%                  | 1.45%                                    |
| 510050_DTE30_ATM_Q100_Hold | Stress / Diagnostic Only | diagnostic_only             | 6.70%                    |               0.752 | 9.41%          |          0.712 |           1.141 | 9.18%                   | 1.93%                                    |

## 5. Option-leg 归因

`510050_DTE30_D40_Q70_Hold` 的净 option leg 年化贡献为 1.02%，是否为正：是。

| sleeve_name                | premium_capture_ratio_agg   | payoff_burden_agg   | positive_option_leg_period_rate   | assignment_rate   | p95_short_call_mtm_loss   | p99_short_call_mtm_loss   |
|:---------------------------|:----------------------------|:--------------------|:----------------------------------|:------------------|:--------------------------|:--------------------------|
| 510050_ETF_BuyHold         |                             |                     |                                   |                   | 0.00%                     | 0.00%                     |
| 510050_DTE30_D40_Q50_Hold  | 8.81%                       | 88.64%              | 69.77%                            | 46.51%            | 1.08%                     | 4.61%                     |
| 510050_DTE30_D40_Q70_Hold  | 8.81%                       | 88.64%              | 69.77%                            | 46.51%            | 1.51%                     | 6.45%                     |
| 510050_DTE30_D40_Q100_Hold | 8.81%                       | 88.64%              | 69.77%                            | 46.51%            | 2.16%                     | 9.21%                     |
| 510050_DTE30_ATM_Q100_Hold | 6.86%                       | 90.59%              | 67.44%                            | 58.14%            | 2.73%                     | 9.21%                     |

读数：D40 Q70 相对 BuyHold 的 Sharpe 从 0.303 提升到 0.506，最大回撤从 21.59% 降到 14.70%。这支持把 510050 视为 positive carry / risk-control 候选，而不是单纯的 premium illusion。

## 6. 与 510300 的相关性

| comparison_name   | left_sleeve                       | right_sleeve                      | sample_start   | sample_end   |   n_obs |   daily_return_correlation |   rolling_window_days |   rolling_corr_mean |   rolling_corr_median |   rolling_corr_p05 |   rolling_corr_p95 |   rolling_corr_min |   rolling_corr_max | interpretation                                                  |
|:------------------|:----------------------------------|:----------------------------------|:---------------|:-------------|--------:|---------------------------:|----------------------:|--------------------:|----------------------:|-------------------:|-------------------:|-------------------:|-------------------:|:----------------------------------------------------------------|
| ETF_BuyHold_pair  | 510050__510050_ETF_BuyHold        | 510300__510300_ETF_BuyHold        | 2022-09-30     | 2026-05-27   |     881 |                      0.921 |                    63 |               0.91  |                 0.921 |              0.792 |              0.967 |              0.724 |              0.978 | very high overlap; mainly repeated large-cap exposure           |
| D40_Q70_pair      | 510050__510050_DTE30_D40_Q70_Hold | 510300__510300_DTE30_D40_Q70_Hold | 2022-09-30     | 2026-05-27   |     881 |                      0.892 |                    63 |               0.888 |                 0.908 |              0.72  |              0.963 |              0.642 |              0.974 | high overlap; limited diversification but usable as second core |

解释：510050 与 510300 的 Q70 sleeve 相关性为 0.892，属于 `high overlap; limited diversification but usable as second core`。它提供的是相似的大盘低波动 / 金融权重暴露，分散化价值有限；但如果 option carry 更稳定，可以作为第二个大盘备兑核心，组合层需要控制风格重叠。

## 7. Sleeve 分类结论

推荐 sleeve：`510050_DTE30_D40_Q70_Hold`。

分类：`Positive Carry Overlay`。

理由：Net option leg is positive while Sharpe improves and max drawdown is lower than BuyHold.

约束：Q100 和 ATM Q100 只保留为 stress / diagnostic，不作为默认组合层主候选。本报告中的收益捕捉指结构性风险补偿，不表示确定性收益。

## 8. 后续组合层建议

510050 建议进入 后续 Step B / Step B+ 的 alternative universe：`510300 + 510050 + 159915`。

推荐定位：defensive-income universe。510300 仍是第一大盘备兑核心；510050 可以作为第二个大盘备兑核心，但与 510300 高相关，组合层应把它看成同类风格增强，而不是独立分散化资产。

## 9. Sanity Checks

| check_name                                | passed   | note                                                     |
|:------------------------------------------|:---------|:---------------------------------------------------------|
| required_sleeves_created                  | True     | all requested 510050 sleeves exist                       |
| common_sample_matches_stepA               | True     | metrics use Step A common sample                         |
| uses_standardized_metric_names            | True     | summary follows ver2 field names                         |
| option_leg_net_pnl_formula                | True     | period option leg equals premium minus payoff minus cost |
| q100_diagnostic_only                      | True     | Q100 sleeves are not default recommendations             |
| primary_not_q100                          | True     | primary sleeve excludes Q100                             |
| correlation_diagnostics_created           | True     | 510050 vs 510300 correlations are populated              |
| no_portfolio_weighting_in_stepA_extension | True     | single-ETF extension only                                |
| panel_created                             | True     | long and wide return panels are populated                |
| reports_avoid_forbidden_profit_claims     | True     | reports avoid guaranteed-profit wording                  |
