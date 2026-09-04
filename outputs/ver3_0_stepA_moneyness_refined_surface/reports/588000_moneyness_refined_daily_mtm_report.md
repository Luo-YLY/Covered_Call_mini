## 588000

科创成长扩展样本；期权数据从 2023-06-05 起，只作 extension 诊断。

- 样本: 2023-06-30 至 2026-05-27；范围: short_sample_extension。
- BuyHold: Sharpe 0.785，CAGR 23.90%，MDD 36.48%。
- Sharpe 最高点: OTM1 Q10，Sharpe 0.782，CAGR 22.48%，MDD 34.26%，期权腿 -1.85%。
- 读取: drawdown cushion with visible return cost；期权腿判断: negative option leg。

### Sharpe 前五

| moneyness_label   | coverage_label   |   sharpe_daily_mean | annualized_return_cagr   | max_drawdown   | option_leg_annualized_pnl_contribution   | avg_realized_moneyness   | recommendation_read                       |
|:------------------|:-----------------|--------------------:|:-------------------------|:---------------|:-----------------------------------------|:-------------------------|:------------------------------------------|
| OTM1              | Q10              |               0.782 | 22.48%                   | 34.26%         | -1.85%                                   | 1.07%                    | drawdown cushion with visible return cost |
| ATM               | Q10              |               0.778 | 22.27%                   | 34.21%         | -2.05%                                   | 0.06%                    | drawdown cushion with visible return cost |
| OTM1              | Q20              |               0.777 | 20.99%                   | 31.97%         | -3.71%                                   | 1.07%                    | drawdown cushion with visible return cost |
| OTM4              | Q10              |               0.773 | 22.27%                   | 35.17%         | -1.93%                                   | 4.03%                    | drawdown cushion with visible return cost |
| OTM2              | Q10              |               0.771 | 22.06%                   | 34.68%         | -2.17%                                   | 1.78%                    | drawdown cushion with visible return cost |

### 各 moneyness 的最优覆盖率

| moneyness_label   | coverage_label   |   sharpe_daily_mean | annualized_return_cagr   | max_drawdown   | option_leg_annualized_pnl_contribution   | avg_realized_moneyness   |
|:------------------|:-----------------|--------------------:|:-------------------------|:---------------|:-----------------------------------------|:-------------------------|
| ATM               | Q10              |               0.778 | 22.27%                   | 34.21%         | -2.05%                                   | 0.06%                    |
| OTM1              | Q10              |               0.782 | 22.48%                   | 34.26%         | -1.85%                                   | 1.07%                    |
| OTM2              | Q10              |               0.771 | 22.06%                   | 34.68%         | -2.17%                                   | 1.78%                    |
| OTM3              | Q10              |               0.767 | 21.98%                   | 35.07%         | -2.21%                                   | 2.82%                    |
| OTM4              | Q10              |               0.773 | 22.27%                   | 35.17%         | -1.93%                                   | 4.03%                    |
| OTM5              | Q10              |               0.77  | 22.24%                   | 35.39%         | -1.91%                                   | 5.34%                    |
| OTM7              | Q10              |               0.766 | 22.13%                   | 35.78%         | -1.97%                                   | 7.39%                    |

### 期权腿前五

| moneyness_label   | coverage_label   | option_leg_annualized_pnl_contribution   | premium_capture_ratio_agg   | payoff_burden_agg   | positive_option_leg_period_rate   | assignment_rate   |   sharpe_daily_mean |
|:------------------|:-----------------|:-----------------------------------------|:----------------------------|:--------------------|:----------------------------------|:------------------|--------------------:|
| OTM1              | Q10              | -1.85%                                   | -61.64%                     | 159.09%             | 80.00%                            | 34.29%            |               0.782 |
| OTM5              | Q10              | -1.91%                                   | -113.17%                    | 210.62%             | 80.00%                            | 20.00%            |               0.77  |
| OTM4              | Q10              | -1.93%                                   | -95.17%                     | 192.62%             | 80.00%                            | 22.86%            |               0.773 |
| OTM7              | Q10              | -1.97%                                   | -151.92%                    | 249.37%             | 80.00%                            | 20.00%            |               0.766 |
| ATM               | Q10              | -2.05%                                   | -58.10%                     | 155.55%             | 74.29%                            | 42.86%            |               0.778 |

### 选券审计

| check_name     | value                                                      | passed   | note                                                                    |
|:---------------|:-----------------------------------------------------------|:---------|:------------------------------------------------------------------------|
| sample_window  | 2023-06-30 to 2026-05-27                                   | True     | short_sample_extension                                                  |
| source_engine  | ver2_downside_protection.strategy_engine.run_ver2_backtest | True     | continuous_30d daily MTM, not src.backtest.custom monthly segmented NAV |
| option_source  | data/raw/options_daily.csv                                 | True     | daily option chain                                                      |
| ATM_selection  | selected=35; skipped=0; avg_realized_moneyness=0.0006      | True     | target_moneyness=0.00%                                                  |
| OTM1_selection | selected=35; skipped=0; avg_realized_moneyness=0.0107      | True     | target_moneyness=1.00%                                                  |
| OTM2_selection | selected=35; skipped=0; avg_realized_moneyness=0.0178      | True     | target_moneyness=2.00%                                                  |
| OTM3_selection | selected=35; skipped=0; avg_realized_moneyness=0.0282      | True     | target_moneyness=3.00%                                                  |
| OTM4_selection | selected=35; skipped=0; avg_realized_moneyness=0.0403      | True     | target_moneyness=4.00%                                                  |
| OTM5_selection | selected=35; skipped=0; avg_realized_moneyness=0.0534      | True     | target_moneyness=5.00%                                                  |
| OTM7_selection | selected=35; skipped=0; avg_realized_moneyness=0.0739      | True     | target_moneyness=7.00%                                                  |
| daily_rows     | 49913                                                      | True     | 71 sleeves including BuyHold                                            |
| period_rows    | 2450                                                       | True     | surface period attribution rows                                         |

### 图表

- sharpe_daily_mean: `outputs/ver3_0_stepA_moneyness_refined_surface/figures/588000_sharpe_daily_mean_surface.png`
- annualized_return_cagr: `outputs/ver3_0_stepA_moneyness_refined_surface/figures/588000_annualized_return_cagr_surface.png`
- max_drawdown: `outputs/ver3_0_stepA_moneyness_refined_surface/figures/588000_max_drawdown_surface.png`
- option_leg_annualized_pnl_contribution: `outputs/ver3_0_stepA_moneyness_refined_surface/figures/588000_option_leg_annualized_pnl_contribution_surface.png`
- selected_nav_paths: `outputs/ver3_0_stepA_moneyness_refined_surface/figures/588000_selected_nav_paths.png`
