# 510050 Sleeve Card

## 1. 标的定位

510050 是大盘蓝筹 / 金融权重风格 ETF。本扩展只判断它能否作为 510500 的备选，进入 `510300 + 510050 + 159915` defensive-income universe。

## 2. 候选 sleeve 列表

| sleeve_name                | classification           | recommendation_status       |
|:---------------------------|:-------------------------|:----------------------------|
| 510050_ETF_BuyHold         | Pure ETF Preferred       | rejected                    |
| 510050_DTE30_D40_Q50_Hold  | Positive Carry Overlay   | backup_for_portfolio_layer  |
| 510050_DTE30_D40_Q70_Hold  | Positive Carry Overlay   | primary_for_portfolio_layer |
| 510050_DTE30_D40_Q100_Hold | Stress / Diagnostic Only | diagnostic_only             |
| 510050_DTE30_ATM_Q100_Hold | Stress / Diagnostic Only | diagnostic_only             |

## 3. 核心绩效对比

| sleeve_name                | annualized_return_cagr   |   sharpe_daily_mean | max_drawdown   | annualized_volatility   | option_leg_annualized_pnl_contribution   |
|:---------------------------|:-------------------------|--------------------:|:---------------|:------------------------|:-----------------------------------------|
| 510050_ETF_BuyHold         | 2.90%                    |               0.256 | 21.59%         | 16.40%                  | 0.00%                                    |
| 510050_DTE30_D40_Q50_Hold  | 4.25%                    |               0.386 | 16.71%         | 12.96%                  | 0.79%                                    |
| 510050_DTE30_D40_Q70_Hold  | 4.72%                    |               0.449 | 14.70%         | 11.84%                  | 1.11%                                    |
| 510050_DTE30_D40_Q100_Hold | 5.37%                    |               0.547 | 11.95%         | 10.59%                  | 1.59%                                    |
| 510050_DTE30_ATM_Q100_Hold | 6.15%                    |               0.695 | 10.32%         | 9.19%                   | 2.18%                                    |

## 4. Option-leg 质量

| sleeve_name                | premium_capture_ratio_agg   | payoff_burden_agg   | positive_option_leg_period_rate   | assignment_rate   | p99_short_call_mtm_loss   |
|:---------------------------|:----------------------------|:--------------------|:----------------------------------|:------------------|:--------------------------|
| 510050_ETF_BuyHold         |                             |                     |                                   |                   | 0.00%                     |
| 510050_DTE30_D40_Q50_Hold  | 10.88%                      | 86.57%              | 70.45%                            | 45.45%            | 4.58%                     |
| 510050_DTE30_D40_Q70_Hold  | 10.88%                      | 86.57%              | 70.45%                            | 45.45%            | 6.41%                     |
| 510050_DTE30_D40_Q100_Hold | 10.88%                      | 86.57%              | 70.45%                            | 45.45%            | 9.16%                     |
| 510050_DTE30_ATM_Q100_Hold | 9.21%                       | 88.24%              | 68.18%                            | 56.82%            | 9.16%                     |

## 5. 与 510300 的相关性

| comparison_name   | left_sleeve                       | right_sleeve                      | sample_start   | sample_end   |   n_obs |   daily_return_correlation |   rolling_window_days |   rolling_corr_mean |   rolling_corr_median |   rolling_corr_p05 |   rolling_corr_p95 |   rolling_corr_min |   rolling_corr_max | interpretation                                                  |
|:------------------|:----------------------------------|:----------------------------------|:---------------|:-------------|--------:|---------------------------:|----------------------:|--------------------:|----------------------:|-------------------:|-------------------:|-------------------:|-------------------:|:----------------------------------------------------------------|
| ETF_BuyHold_pair  | 510050__510050_ETF_BuyHold        | 510300__510300_ETF_BuyHold        | 2022-09-19     | 2026-05-27   |     890 |                      0.921 |                    63 |               0.91  |              0.921211 |              0.792 |              0.967 |           0.72371  |           0.977796 | very high overlap; mainly repeated large-cap exposure           |
| D40_Q70_pair      | 510050__510050_DTE30_D40_Q70_Hold | 510300__510300_DTE30_D40_Q70_Hold | 2022-09-19     | 2026-05-27   |     890 |                      0.885 |                    63 |               0.882 |              0.893854 |              0.728 |              0.96  |           0.641198 |           0.971903 | high overlap; limited diversification but usable as second core |

## 6. 推荐进入组合层的 sleeve

- primary_sleeve_for_portfolio_layer: 510050_DTE30_D40_Q70_Hold
- classification: Positive Carry Overlay
- correlation_judgment: high overlap; limited diversification but usable as second core
- caveat: This is structural risk compensation with path and sample risk.
