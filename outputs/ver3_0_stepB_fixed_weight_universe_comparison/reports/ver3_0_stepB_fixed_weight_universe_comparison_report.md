# ver3.0 Step B：固定权重 Universe 组合比较

## 研究目标

本实验从 Step A 的单 ETF sleeve 诊断推进到固定权重组合层比较。它只使用已选定的 Step A sleeves，不重新跑期权参数网格，不做权重优化，也不把 588000 纳入长样本 Step B 主组合。

## 方法口径

对组合 p：

`R_p,t = sum_i w_i * r_i,t`

组合 NAV 从初始净值 1.0 开始，由每日组合收益累乘得到。这是研究层面的固定权重 sleeve 组合，不是账户级实盘交易模拟。期权腿归因沿用 Step A 的日度核算口径，使用加权后的净期权腿收益。

## 样本窗口

| window_name                 | sample_start   | sample_end   | n_obs   | note                                                      |
|:----------------------------|:---------------|:-------------|:--------|:----------------------------------------------------------|
| stepB_common_long_sample    | 2022-09-30     | 2026-05-27   | 881.0   | Universe A/B 必需 sleeves 对齐后的共同非缺失样本。        |
| requested_main_stepB_sample | 2022-09-30     | 2026-05-27   |         | 任务指定的长样本窗口；实际样本由可用面板对齐后确认。      |
| 588000_extension_status     |                |              |         | 588000 仅作为短样本 extension，可用但不进入 Step B 主线。 |
| portfolio_metric_sample     | 2022-09-30     | 2026-05-27   | 881.0   | 组合 NAV 构建后的指标样本。                               |

## 组合汇总

| portfolio_name      | universe_short   | portfolio_type   |   weight_scheme | annualized_return_cagr   |   sharpe_daily_mean | annualized_volatility   | max_drawdown   |   calmar_ratio |   sortino_ratio | option_leg_annualized_pnl_contribution   |   final_nav |
|:--------------------|:-----------------|:-----------------|----------------:|:-------------------------|--------------------:|:------------------------|:---------------|---------------:|----------------:|:-----------------------------------------|------------:|
| A_Pure_ETF_40_40_20 | A                | Pure_ETF         |        40_40_20 | 11.97%                   |               0.644 | 20.93%                  | 29.03%         |          0.412 |           1.152 | 0.00%                                    |       1.484 |
| A_Pure_ETF_50_30_20 | A                | Pure_ETF         |        50_30_20 | 11.43%                   |               0.629 | 20.53%                  | 28.51%         |          0.401 |           1.126 | 0.00%                                    |       1.459 |
| A_Pure_ETF_70_20_10 | A                | Pure_ETF         |        70_20_10 | 9.63%                    |               0.579 | 18.97%                  | 26.36%         |          0.365 |           1.027 | 0.00%                                    |       1.379 |
| A_Selected_40_40_20 | A                | Selected         |        40_40_20 | 11.56%                   |               0.711 | 17.56%                  | 25.44%         |          0.454 |           1.218 | -1.00%                                   |       1.465 |
| A_Selected_50_30_20 | A                | Selected         |        50_30_20 | 11.14%                   |               0.719 | 16.60%                  | 24.13%         |          0.462 |           1.225 | -0.98%                                   |       1.446 |
| A_Selected_70_20_10 | A                | Selected         |        70_20_10 | 10.01%                   |               0.727 | 14.60%                  | 20.59%         |          0.486 |           1.213 | -0.37%                                   |       1.395 |
| B_Pure_ETF_40_40_20 | B                | Pure_ETF         |        40_40_20 | 8.41%                    |               0.525 | 18.71%                  | 26.23%         |          0.321 |           0.934 | 0.00%                                    |       1.326 |
| B_Pure_ETF_50_30_20 | B                | Pure_ETF         |        50_30_20 | 8.75%                    |               0.537 | 18.93%                  | 26.59%         |          0.329 |           0.957 | 0.00%                                    |       1.34  |
| B_Pure_ETF_70_20_10 | B                | Pure_ETF         |        70_20_10 | 7.82%                    |               0.507 | 18.07%                  | 25.21%         |          0.31  |           0.896 | 0.00%                                    |       1.301 |
| B_Selected_40_40_20 | B                | Selected         |        40_40_20 | 8.66%                    |               0.684 | 13.49%                  | 19.65%         |          0.441 |           1.138 | -0.60%                                   |       1.337 |
| B_Selected_50_30_20 | B                | Selected         |        50_30_20 | 8.94%                    |               0.697 | 13.62%                  | 19.93%         |          0.449 |           1.159 | -0.67%                                   |       1.349 |
| B_Selected_70_20_10 | B                | Selected         |        70_20_10 | 8.50%                    |               0.701 | 12.82%                  | 17.87%         |          0.476 |           1.149 | -0.17%                                   |       1.33  |

## Selected 与 Pure ETF 基准对比

`delta_mdd_vs_baseline < 0` 表示 selected 组合相对 pure ETF 基准降低了最大回撤。

| selected_portfolio   | matched_baseline    | universe_name                         |   weight_scheme | excess_cagr_vs_baseline   |   delta_sharpe_vs_baseline | delta_volatility_vs_baseline   | delta_mdd_vs_baseline   |   delta_calmar_vs_baseline |   delta_sortino_vs_baseline | delta_final_nav_vs_baseline   | option_leg_annualized_pnl_contribution   | interpretation_hint                                        |
|:---------------------|:--------------------|:--------------------------------------|----------------:|:--------------------------|---------------------------:|:-------------------------------|:------------------------|---------------------------:|----------------------------:|:------------------------------|:-----------------------------------------|:-----------------------------------------------------------|
| A_Selected_40_40_20  | A_Pure_ETF_40_40_20 | Main Growth-Diversified Universe      |        40_40_20 | -0.41%                    |                      0.066 | -3.37%                         | -3.60%                  |                      0.042 |                       0.066 | -1.90%                        | -1.00%                                   | selected 改善风险调整路径，但收益取舍仍需复核              |
| A_Selected_50_30_20  | A_Pure_ETF_50_30_20 | Main Growth-Diversified Universe      |        50_30_20 | -0.29%                    |                      0.09  | -3.93%                         | -4.38%                  |                      0.061 |                       0.099 | -1.33%                        | -0.98%                                   | selected 改善风险调整路径，但收益取舍仍需复核              |
| A_Selected_70_20_10  | A_Pure_ETF_70_20_10 | Main Growth-Diversified Universe      |        70_20_10 | 0.38%                     |                      0.147 | -4.36%                         | -5.76%                  |                      0.121 |                       0.186 | 1.68%                         | -0.37%                                   | selected 相对匹配 pure ETF 基准同时改善收益、Sharpe 和回撤 |
| B_Selected_40_40_20  | B_Pure_ETF_40_40_20 | Alternative Defensive-Income Universe |        40_40_20 | 0.25%                     |                      0.159 | -5.22%                         | -6.58%                  |                      0.12  |                       0.204 | 1.09%                         | -0.60%                                   | selected 相对匹配 pure ETF 基准同时改善收益、Sharpe 和回撤 |
| B_Selected_50_30_20  | B_Pure_ETF_50_30_20 | Alternative Defensive-Income Universe |        50_30_20 | 0.20%                     |                      0.16  | -5.31%                         | -6.66%                  |                      0.12  |                       0.202 | 0.84%                         | -0.67%                                   | selected 相对匹配 pure ETF 基准同时改善收益、Sharpe 和回撤 |
| B_Selected_70_20_10  | B_Pure_ETF_70_20_10 | Alternative Defensive-Income Universe |        70_20_10 | 0.68%                     |                      0.194 | -5.25%                         | -7.34%                  |                      0.166 |                       0.253 | 2.90%                         | -0.17%                                   | selected 相对匹配 pure ETF 基准同时改善收益、Sharpe 和回撤 |

## Universe A 与 Universe B 对比

| left_portfolio      | right_portfolio     | portfolio_type   |   weight_scheme | delta_cagr   |   delta_sharpe | delta_volatility   | delta_mdd   |   delta_calmar |   delta_sortino | interpretation_hint                         |
|:--------------------|:--------------------|:-----------------|----------------:|:-------------|---------------:|:-------------------|:------------|---------------:|----------------:|:--------------------------------------------|
| B_Pure_ETF_40_40_20 | A_Pure_ETF_40_40_20 | Pure_ETF         |        40_40_20 | -3.56%       |         -0.119 | -2.22%             | -2.80%      |         -0.092 |          -0.218 | Universe B 降低回撤，但成长分散化收益较有限 |
| B_Pure_ETF_50_30_20 | A_Pure_ETF_50_30_20 | Pure_ETF         |        50_30_20 | -2.68%       |         -0.092 | -1.60%             | -1.92%      |         -0.072 |          -0.168 | Universe B 降低回撤，但成长分散化收益较有限 |
| B_Pure_ETF_70_20_10 | A_Pure_ETF_70_20_10 | Pure_ETF         |        70_20_10 | -1.81%       |         -0.073 | -0.90%             | -1.15%      |         -0.055 |          -0.132 | Universe B 降低回撤，但成长分散化收益较有限 |
| B_Selected_40_40_20 | A_Selected_40_40_20 | Selected         |        40_40_20 | -2.89%       |         -0.027 | -4.08%             | -5.79%      |         -0.013 |          -0.08  | Universe B 降低回撤，但成长分散化收益较有限 |
| B_Selected_50_30_20 | A_Selected_50_30_20 | Selected         |        50_30_20 | -2.19%       |         -0.022 | -2.98%             | -4.20%      |         -0.013 |          -0.065 | Universe B 降低回撤，但成长分散化收益较有限 |
| B_Selected_70_20_10 | A_Selected_70_20_10 | Selected         |        70_20_10 | -1.51%       |         -0.026 | -1.79%             | -2.73%      |         -0.01  |          -0.065 | Universe B 降低回撤，但成长分散化收益较有限 |

## 期权腿归因

| portfolio_name      |   etf_code | sleeve_key                           | weight   | option_leg_annualized_pnl_contribution   | attribution_method               |
|:--------------------|-----------:|:-------------------------------------|:---------|:-----------------------------------------|:---------------------------------|
| A_Selected_50_30_20 |     510300 | 510300__510300_DTE30_D40_Q70_Hold    | 50.00%   | 0.13%                                    | daily_weighted_option_leg_return |
| A_Selected_50_30_20 |     510500 | 510500__510500_ETF_BuyHold           | 30.00%   | 0.00%                                    | daily_weighted_option_leg_return |
| A_Selected_50_30_20 |     159915 | 159915__159915_DTE30_OTM5up_Q50_Hold | 20.00%   | -1.11%                                   | daily_weighted_option_leg_return |
| A_Selected_70_20_10 |     510300 | 510300__510300_DTE30_D40_Q70_Hold    | 70.00%   | 0.18%                                    | daily_weighted_option_leg_return |
| A_Selected_70_20_10 |     510500 | 510500__510500_ETF_BuyHold           | 20.00%   | 0.00%                                    | daily_weighted_option_leg_return |
| A_Selected_70_20_10 |     159915 | 159915__159915_DTE30_OTM5up_Q50_Hold | 10.00%   | -0.55%                                   | daily_weighted_option_leg_return |
| A_Selected_40_40_20 |     510300 | 510300__510300_DTE30_D40_Q70_Hold    | 40.00%   | 0.10%                                    | daily_weighted_option_leg_return |
| A_Selected_40_40_20 |     510500 | 510500__510500_ETF_BuyHold           | 40.00%   | 0.00%                                    | daily_weighted_option_leg_return |
| A_Selected_40_40_20 |     159915 | 159915__159915_DTE30_OTM5up_Q50_Hold | 20.00%   | -1.11%                                   | daily_weighted_option_leg_return |
| B_Selected_50_30_20 |     510300 | 510300__510300_DTE30_D40_Q70_Hold    | 50.00%   | 0.13%                                    | daily_weighted_option_leg_return |
| B_Selected_50_30_20 |     510050 | 510050__510050_DTE30_D40_Q70_Hold    | 30.00%   | 0.31%                                    | daily_weighted_option_leg_return |
| B_Selected_50_30_20 |     159915 | 159915__159915_DTE30_OTM5up_Q50_Hold | 20.00%   | -1.11%                                   | daily_weighted_option_leg_return |
| B_Selected_70_20_10 |     510300 | 510300__510300_DTE30_D40_Q70_Hold    | 70.00%   | 0.18%                                    | daily_weighted_option_leg_return |
| B_Selected_70_20_10 |     510050 | 510050__510050_DTE30_D40_Q70_Hold    | 20.00%   | 0.20%                                    | daily_weighted_option_leg_return |
| B_Selected_70_20_10 |     159915 | 159915__159915_DTE30_OTM5up_Q50_Hold | 10.00%   | -0.55%                                   | daily_weighted_option_leg_return |
| B_Selected_40_40_20 |     510300 | 510300__510300_DTE30_D40_Q70_Hold    | 40.00%   | 0.10%                                    | daily_weighted_option_leg_return |
| B_Selected_40_40_20 |     510050 | 510050__510050_DTE30_D40_Q70_Hold    | 40.00%   | 0.41%                                    | daily_weighted_option_leg_return |
| B_Selected_40_40_20 |     159915 | 159915__159915_DTE30_OTM5up_Q50_Hold | 20.00%   | -1.11%                                   | daily_weighted_option_leg_return |

## 风险诊断

风险贡献表只用于静态解释，不作为动态调仓规则。

| portfolio_name      |   etf_code | sleeve_key                           | weight   | portfolio_volatility   | risk_contribution_pct   |
|:--------------------|-----------:|:-------------------------------------|:---------|:-----------------------|:------------------------|
| A_Selected_50_30_20 |     510300 | 510300__510300_DTE30_D40_Q70_Hold    | 50.00%   | 16.59%                 | 34.54%                  |
| A_Selected_50_30_20 |     510500 | 510500__510500_ETF_BuyHold           | 30.00%   | 16.59%                 | 37.56%                  |
| A_Selected_50_30_20 |     159915 | 159915__159915_DTE30_OTM5up_Q50_Hold | 20.00%   | 16.59%                 | 27.90%                  |
| A_Selected_70_20_10 |     510300 | 510300__510300_DTE30_D40_Q70_Hold    | 70.00%   | 14.60%                 | 57.08%                  |
| A_Selected_70_20_10 |     510500 | 510500__510500_ETF_BuyHold           | 20.00%   | 14.60%                 | 27.57%                  |
| A_Selected_70_20_10 |     159915 | 159915__159915_DTE30_OTM5up_Q50_Hold | 10.00%   | 14.60%                 | 15.35%                  |
| A_Selected_40_40_20 |     510300 | 510300__510300_DTE30_D40_Q70_Hold    | 40.00%   | 17.55%                 | 25.54%                  |
| A_Selected_40_40_20 |     510500 | 510500__510500_ETF_BuyHold           | 40.00%   | 17.55%                 | 48.14%                  |
| A_Selected_40_40_20 |     159915 | 159915__159915_DTE30_OTM5up_Q50_Hold | 20.00%   | 17.55%                 | 26.32%                  |
| B_Selected_50_30_20 |     510300 | 510300__510300_DTE30_D40_Q70_Hold    | 50.00%   | 13.61%                 | 44.25%                  |
| B_Selected_50_30_20 |     510050 | 510050__510050_DTE30_D40_Q70_Hold    | 30.00%   | 13.61%                 | 23.33%                  |
| B_Selected_50_30_20 |     159915 | 159915__159915_DTE30_OTM5up_Q50_Hold | 20.00%   | 13.61%                 | 32.42%                  |
| B_Selected_70_20_10 |     510300 | 510300__510300_DTE30_D40_Q70_Hold    | 70.00%   | 12.81%                 | 66.70%                  |
| B_Selected_70_20_10 |     510050 | 510050__510050_DTE30_D40_Q70_Hold    | 20.00%   | 12.81%                 | 16.76%                  |
| B_Selected_70_20_10 |     159915 | 159915__159915_DTE30_OTM5up_Q50_Hold | 10.00%   | 12.81%                 | 16.54%                  |
| B_Selected_40_40_20 |     510300 | 510300__510300_DTE30_D40_Q70_Hold    | 40.00%   | 13.48%                 | 35.65%                  |
| B_Selected_40_40_20 |     510050 | 510050__510050_DTE30_D40_Q70_Hold    | 40.00%   | 13.48%                 | 31.97%                  |
| B_Selected_40_40_20 |     159915 | 159915__159915_DTE30_OTM5up_Q50_Hold | 20.00%   | 13.48%                 | 32.38%                  |

## 588000 说明

588000 被视为短样本科技成长 extension。当前是否有 588000 数据：`True`。它被有意排除在本次长样本固定权重 Step B 比较之外；如需包含 588000，应单独做 Step B-Extension。

## 结论

- Sharpe 最高组合：`A_Selected_70_20_10`，Sharpe 为 0.727。
- 最大回撤最低组合：`B_Selected_70_20_10`，MDD 为 17.87%。
- 当 510500 的中盘成长分散化有价值时，Universe A 仍是成长分散化基准线。
- 当更重视低回撤和双大盘备兑核心时，Universe B 是防御收益候选线。
- Step B+ 应在 Universe A 与 Universe B 内分别比较 MDD 约束 Sharpe 前沿，而不是把本次样本内固定权重结果直接视为样本外最优。

## 校验结果

| 检查项                                | 是否通过   | 说明                                     |
|:--------------------------------------|:-----------|:-----------------------------------------|
| required_sleeves_exist                | 通过       | 组合构建前已验证必需 sleeves 存在        |
| weights_sum_to_one                    | 通过       | 所有组合权重和为 1                       |
| portfolio_returns_non_empty           | 通过       | 组合日收益存在有效行                     |
| initial_nav_reference_is_one          | 通过       | NAV 路径使用 initial_nav=1.0 作为参考    |
| nav_positive                          | 通过       | 所有 NAV 值均为正                        |
| max_drawdown_positive_magnitude       | 通过       | max_drawdown 使用正数幅度口径            |
| selected_has_matched_pure_baseline    | 通过       | 每个 selected 组合均有匹配 pure ETF 基准 |
| universe_a_b_same_sample              | 通过       | Universe A 与 B 使用同一共同样本         |
| no_588000_in_main_portfolios          | 通过       | 588000 已排除在长样本 Step B 主线之外    |
| no_q100_atm_tp80_touchk_main_selected | 通过       | 默认 selected 组合排除诊断型 sleeves     |
| output_csv_rows_nonzero               | 通过       | CSV 输出存在非空行                       |
| report_generated                      | 通过       | Markdown 报告已生成                      |
