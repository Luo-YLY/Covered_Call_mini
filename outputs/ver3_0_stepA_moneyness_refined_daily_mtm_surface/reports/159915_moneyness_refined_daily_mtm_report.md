## 159915

成长弹性资产；重点观察保留上行后的备兑曲面是否仍被期权腿拖累。

- 样本: 2022-09-30 至 2026-05-27；范围: main_stepA_common_sample。
- BuyHold: Sharpe 0.700，CAGR 18.82%，MDD 40.88%。
- Sharpe 最高点: OTM7 Q20，Sharpe 0.702，CAGR 17.50%，MDD 39.86%，期权腿 -1.91%。
- 读取: risk-adjusted defensive tradeoff, not a return upgrade；期权腿判断: negative option leg。

### Sharpe 前五

| moneyness_label   | coverage_label   |   sharpe_daily_mean | annualized_return_cagr   | max_drawdown   | option_leg_annualized_pnl_contribution   | avg_realized_moneyness   | recommendation_read                                    |
|:------------------|:-----------------|--------------------:|:-------------------------|:---------------|:-----------------------------------------|:-------------------------|:-------------------------------------------------------|
| OTM7              | Q20              |               0.702 | 17.50%                   | 39.86%         | -1.91%                                   | 7.01%                    | risk-adjusted defensive tradeoff, not a return upgrade |
| OTM7              | Q10              |               0.702 | 18.18%                   | 40.27%         | -0.96%                                   | 7.01%                    | risk-adjusted defensive tradeoff, not a return upgrade |
| OTM7              | Q30              |               0.7   | 16.79%                   | 39.51%         | -2.87%                                   | 7.01%                    | drawdown cushion with visible return cost              |
| OTM5              | Q10              |               0.7   | 18.05%                   | 40.13%         | -1.11%                                   | 5.21%                    | drawdown cushion with visible return cost              |
| OTM4              | Q10              |               0.699 | 17.98%                   | 39.69%         | -1.20%                                   | 3.78%                    | drawdown cushion with visible return cost              |

### 各 moneyness 的最优覆盖率

| moneyness_label   | coverage_label   |   sharpe_daily_mean | annualized_return_cagr   | max_drawdown   | option_leg_annualized_pnl_contribution   | avg_realized_moneyness   |
|:------------------|:-----------------|--------------------:|:-------------------------|:---------------|:-----------------------------------------|:-------------------------|
| ATM               | Q10              |               0.697 | 17.67%                   | 39.16%         | -1.59%                                   | -0.16%                   |
| OTM1              | Q10              |               0.698 | 17.81%                   | 39.25%         | -1.42%                                   | 1.13%                    |
| OTM2              | Q10              |               0.699 | 17.90%                   | 39.54%         | -1.31%                                   | 2.16%                    |
| OTM3              | Q10              |               0.696 | 17.84%                   | 39.73%         | -1.34%                                   | 2.90%                    |
| OTM4              | Q10              |               0.699 | 17.98%                   | 39.69%         | -1.20%                                   | 3.78%                    |
| OTM5              | Q10              |               0.7   | 18.05%                   | 40.13%         | -1.11%                                   | 5.21%                    |
| OTM7              | Q20              |               0.702 | 17.50%                   | 39.86%         | -1.91%                                   | 7.01%                    |

### 期权腿前五

| moneyness_label   | coverage_label   | option_leg_annualized_pnl_contribution   | premium_capture_ratio_agg   | payoff_burden_agg   | positive_option_leg_period_rate   | assignment_rate   |   sharpe_daily_mean |
|:------------------|:-----------------|:-----------------------------------------|:----------------------------|:--------------------|:----------------------------------|:------------------|--------------------:|
| OTM7              | Q10              | -0.96%                                   | -90.92%                     | 188.37%             | 79.55%                            | 25.00%            |               0.702 |
| OTM5              | Q10              | -1.11%                                   | -77.51%                     | 174.96%             | 75.00%                            | 27.27%            |               0.7   |
| OTM4              | Q10              | -1.20%                                   | -64.87%                     | 162.32%             | 72.73%                            | 34.09%            |               0.699 |
| OTM2              | Q10              | -1.31%                                   | -53.42%                     | 150.87%             | 68.18%                            | 38.64%            |               0.699 |
| OTM3              | Q10              | -1.34%                                   | -63.03%                     | 160.48%             | 70.45%                            | 36.36%            |               0.696 |

### 选券审计

| check_name     | value                                                      | passed   | note                                                                    |
|:---------------|:-----------------------------------------------------------|:---------|:------------------------------------------------------------------------|
| sample_window  | 2022-09-30 to 2026-05-27                                   | True     | main_stepA_common_sample                                                |
| source_engine  | ver2_downside_protection.strategy_engine.run_ver2_backtest | True     | continuous_30d daily MTM, not src.backtest.custom monthly segmented NAV |
| option_source  | data/raw/options_daily.csv                                 | True     | daily option chain                                                      |
| ATM_selection  | selected=44; skipped=0; avg_realized_moneyness=-0.0016     | True     | target_moneyness=0.00%                                                  |
| OTM1_selection | selected=44; skipped=0; avg_realized_moneyness=0.0113      | True     | target_moneyness=1.00%                                                  |
| OTM2_selection | selected=44; skipped=0; avg_realized_moneyness=0.0216      | True     | target_moneyness=2.00%                                                  |
| OTM3_selection | selected=44; skipped=0; avg_realized_moneyness=0.0290      | True     | target_moneyness=3.00%                                                  |
| OTM4_selection | selected=44; skipped=0; avg_realized_moneyness=0.0378      | True     | target_moneyness=4.00%                                                  |
| OTM5_selection | selected=44; skipped=0; avg_realized_moneyness=0.0521      | True     | target_moneyness=5.00%                                                  |
| OTM7_selection | selected=44; skipped=0; avg_realized_moneyness=0.0701      | True     | target_moneyness=7.00%                                                  |
| daily_rows     | 62551                                                      | True     | 71 sleeves including BuyHold                                            |
| period_rows    | 3080                                                       | True     | surface period attribution rows                                         |

### 图表

- sharpe_daily_mean: `outputs/ver3_0_stepA_moneyness_refined_daily_mtm_surface/figures/159915_sharpe_daily_mean_surface.png`
- sharpe_daily_mean_3d_surface: `outputs/ver3_0_stepA_moneyness_refined_daily_mtm_surface/figures/159915_sharpe_daily_mean_3d_surface.png`
- annualized_return_cagr: `outputs/ver3_0_stepA_moneyness_refined_daily_mtm_surface/figures/159915_annualized_return_cagr_surface.png`
- annualized_return_cagr_3d_surface: `outputs/ver3_0_stepA_moneyness_refined_daily_mtm_surface/figures/159915_annualized_return_cagr_3d_surface.png`
- max_drawdown: `outputs/ver3_0_stepA_moneyness_refined_daily_mtm_surface/figures/159915_max_drawdown_surface.png`
- max_drawdown_3d_surface: `outputs/ver3_0_stepA_moneyness_refined_daily_mtm_surface/figures/159915_max_drawdown_3d_surface.png`
- option_leg_annualized_pnl_contribution: `outputs/ver3_0_stepA_moneyness_refined_daily_mtm_surface/figures/159915_option_leg_annualized_pnl_contribution_surface.png`
- option_leg_annualized_pnl_contribution_3d_surface: `outputs/ver3_0_stepA_moneyness_refined_daily_mtm_surface/figures/159915_option_leg_annualized_pnl_contribution_3d_surface.png`
- selected_nav_paths: `outputs/ver3_0_stepA_moneyness_refined_daily_mtm_surface/figures/159915_selected_nav_paths.png`
