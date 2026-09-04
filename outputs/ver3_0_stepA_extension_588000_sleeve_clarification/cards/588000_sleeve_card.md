# 588000 Sleeve Card

## 1. 标的定位

588000 是科创50 / 硬科技成长暴露。本扩展只判断它是否有资格作为 short-sample tech-growth extension sleeve，不进入主线 Step B 样本。

## 2. 候选 sleeve 列表

| sleeve_name                   | classification           | recommendation_status              |
|:------------------------------|:-------------------------|:-----------------------------------|
| 588000_ETF_BuyHold            | Growth Extension Sleeve  | primary_for_short_sample_extension |
| 588000_DTE30_OTM5up_Q50_Hold  | Defensive Overlay        | backup_defensive_overlay           |
| 588000_DTE30_OTM5up_Q100_Hold | Stress / Diagnostic Only | diagnostic_only                    |
| 588000_DTE30_D40_Q50_Hold     | Defensive Overlay        | rejected                           |
| 588000_DTE30_D40_Q100_Hold    | Stress / Diagnostic Only | diagnostic_only                    |
| 588000_DTE30_ATM_Q100_Hold    | Stress / Diagnostic Only | diagnostic_only                    |

## 3. 核心绩效对比

| sleeve_name                   | annualized_return_cagr   |   sharpe_daily_mean | max_drawdown   | annualized_volatility   | option_leg_annualized_pnl_contribution   |
|:------------------------------|:-------------------------|--------------------:|:---------------|:------------------------|:-----------------------------------------|
| 588000_ETF_BuyHold            | 23.90%                   |               0.785 | 36.48%         | 34.74%                  | 0.00%                                    |
| 588000_DTE30_OTM5up_Q50_Hold  | 15.29%                   |               0.668 | 30.88%         | 26.50%                  | -9.54%                                   |
| 588000_DTE30_OTM5up_Q100_Hold | 5.94%                    |               0.373 | 26.54%         | 21.90%                  | -19.07%                                  |
| 588000_DTE30_D40_Q50_Hold     | 13.69%                   |               0.634 | 28.96%         | 25.26%                  | -11.24%                                  |
| 588000_DTE30_D40_Q100_Hold    | 2.76%                    |               0.236 | 24.32%         | 20.11%                  | -22.49%                                  |
| 588000_DTE30_ATM_Q100_Hold    | 5.30%                    |               0.379 | 19.21%         | 17.79%                  | -20.49%                                  |

## 4. Option-leg 质量

| sleeve_name                   | premium_capture_ratio_agg   | payoff_burden_agg   | positive_option_leg_period_rate   | assignment_rate   | p99_short_call_mtm_loss   |
|:------------------------------|:----------------------------|:--------------------|:----------------------------------|:------------------|:--------------------------|
| 588000_ETF_BuyHold            |                             |                     |                                   |                   | 0.00%                     |
| 588000_DTE30_OTM5up_Q50_Hold  | -113.17%                    | 210.62%             | 80.00%                            | 20.00%            | 14.76%                    |
| 588000_DTE30_OTM5up_Q100_Hold | -113.17%                    | 210.62%             | 80.00%                            | 20.00%            | 29.52%                    |
| 588000_DTE30_D40_Q50_Hold     | -90.65%                     | 188.10%             | 80.00%                            | 31.43%            | 17.42%                    |
| 588000_DTE30_D40_Q100_Hold    | -90.65%                     | 188.10%             | 80.00%                            | 31.43%            | 34.84%                    |
| 588000_DTE30_ATM_Q100_Hold    | -58.10%                     | 155.55%             | 74.29%                            | 42.86%            | 34.84%                    |

## 5. 相关性诊断

| comparison_name                   | left_sleeve                          | right_sleeve                         | sample_start   | sample_end   |   n_obs |   daily_return_correlation |   rolling_window_days |   rolling_corr_mean |   rolling_corr_p05 |   rolling_corr_p95 | interpretation                |
|:----------------------------------|:-------------------------------------|:-------------------------------------|:---------------|:-------------|--------:|---------------------------:|----------------------:|--------------------:|-------------------:|-------------------:|:------------------------------|
| 588000_buyhold_vs_510300_buyhold  | 588000__588000_ETF_BuyHold           | 510300__510300_ETF_BuyHold           | 2023-06-30     | 2026-05-27   |     703 |                      0.759 |                    63 |               0.747 |              0.569 |              0.852 | moderate growth-style overlap |
| 588000_buyhold_vs_510500_buyhold  | 588000__588000_ETF_BuyHold           | 510500__510500_ETF_BuyHold           | 2023-06-30     | 2026-05-27   |     703 |                      0.813 |                    63 |               0.837 |              0.755 |              0.911 | moderate growth-style overlap |
| 588000_buyhold_vs_159915_buyhold  | 588000__588000_ETF_BuyHold           | 159915__159915_ETF_BuyHold           | 2023-06-30     | 2026-05-27   |     703 |                      0.856 |                    63 |               0.846 |              0.712 |              0.928 | high overlap                  |
| 588000_OTM5_Q50_vs_159915_primary | 588000__588000_DTE30_OTM5up_Q50_Hold | 159915__159915_DTE30_OTM5up_Q50_Hold | 2023-06-30     | 2026-05-27   |     703 |                      0.832 |                    63 |               0.843 |              0.734 |              0.933 | moderate growth-style overlap |
| 588000_OTM5_Q50_vs_510300_primary | 588000__588000_DTE30_OTM5up_Q50_Hold | 510300__510300_DTE30_D40_Q70_Hold    | 2023-06-30     | 2026-05-27   |     703 |                      0.726 |                    63 |               0.723 |              0.514 |              0.85  | moderate growth-style overlap |
| 588000_buyhold_vs_510050_buyhold  | 588000__588000_ETF_BuyHold           | 510050__510050_ETF_BuyHold           | 2023-06-30     | 2026-05-27   |     703 |                      0.626 |                    63 |               0.607 |              0.392 |              0.771 | partial diversification value |
| 588000_OTM5_Q50_vs_510050_primary | 588000__588000_DTE30_OTM5up_Q50_Hold | 510050__510050_DTE30_D40_Q70_Hold    | 2023-06-30     | 2026-05-27   |     703 |                      0.584 |                    63 |               0.581 |              0.367 |              0.791 | partial diversification value |

## 6. 推荐

- primary_sleeve_for_short_sample_extension: 588000_ETF_BuyHold
- classification: Growth Extension Sleeve
- role: pure ETF growth sleeve
- caveat: Use only in short-sample extension universes.
