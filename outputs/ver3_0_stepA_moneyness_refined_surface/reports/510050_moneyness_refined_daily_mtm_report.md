## 510050

大盘偏蓝筹资产；作为更防御型 ETF 的同标尺 moneyness 参照。

- 样本: 2022-09-30 至 2026-05-27；范围: main_stepA_common_sample。
- BuyHold: Sharpe 0.303，CAGR 3.70%，MDD 21.59%。
- Sharpe 最高点: ATM Q100，Sharpe 0.752，CAGR 6.69%，MDD 9.41%，期权腿 1.92%。
- 读取: dominates buyhold in this diagnostic grid；期权腿判断: positive option leg。

### Sharpe 前五

| moneyness_label   | coverage_label   |   sharpe_daily_mean | annualized_return_cagr   | max_drawdown   | option_leg_annualized_pnl_contribution   | avg_realized_moneyness   | recommendation_read                       |
|:------------------|:-----------------|--------------------:|:-------------------------|:---------------|:-----------------------------------------|:-------------------------|:------------------------------------------|
| ATM               | Q100             |               0.752 | 6.69%                    | 9.41%          | 1.92%                                    | -0.04%                   | dominates buyhold in this diagnostic grid |
| ATM               | Q90              |               0.698 | 6.44%                    | 10.29%         | 1.73%                                    | -0.04%                   | dominates buyhold in this diagnostic grid |
| OTM2              | Q100             |               0.669 | 7.09%                    | 12.08%         | 2.49%                                    | 2.03%                    | dominates buyhold in this diagnostic grid |
| ATM               | Q80              |               0.643 | 6.19%                    | 11.17%         | 1.54%                                    | -0.04%                   | dominates buyhold in this diagnostic grid |
| OTM2              | Q90              |               0.628 | 6.78%                    | 13.07%         | 2.24%                                    | 2.03%                    | dominates buyhold in this diagnostic grid |

### 各 moneyness 的最优覆盖率

| moneyness_label   | coverage_label   |   sharpe_daily_mean | annualized_return_cagr   | max_drawdown   | option_leg_annualized_pnl_contribution   | avg_realized_moneyness   |
|:------------------|:-----------------|--------------------:|:-------------------------|:---------------|:-----------------------------------------|:-------------------------|
| ATM               | Q100             |               0.752 | 6.69%                    | 9.41%          | 1.92%                                    | -0.04%                   |
| OTM1              | Q100             |               0.544 | 5.17%                    | 12.09%         | 0.59%                                    | 1.11%                    |
| OTM2              | Q100             |               0.669 | 7.09%                    | 12.08%         | 2.49%                                    | 2.03%                    |
| OTM3              | Q100             |               0.605 | 6.74%                    | 14.36%         | 2.26%                                    | 2.99%                    |
| OTM4              | Q100             |               0.572 | 6.63%                    | 15.29%         | 2.23%                                    | 3.93%                    |
| OTM5              | Q100             |               0.508 | 6.03%                    | 17.51%         | 1.75%                                    | 5.12%                    |
| OTM7              | Q100             |               0.45  | 5.46%                    | 19.17%         | 1.30%                                    | 7.03%                    |

### 期权腿前五

| moneyness_label   | coverage_label   | option_leg_annualized_pnl_contribution   | premium_capture_ratio_agg   | payoff_burden_agg   | positive_option_leg_period_rate   | assignment_rate   |   sharpe_daily_mean |
|:------------------|:-----------------|:-----------------------------------------|:----------------------------|:--------------------|:----------------------------------|:------------------|--------------------:|
| OTM2              | Q100             | 2.49%                                    | 19.82%                      | 77.63%              | 77.27%                            | 31.82%            |               0.669 |
| OTM3              | Q100             | 2.26%                                    | 24.05%                      | 73.40%              | 84.09%                            | 25.00%            |               0.605 |
| OTM2              | Q90              | 2.24%                                    | 19.82%                      | 77.63%              | 77.27%                            | 31.82%            |               0.628 |
| OTM4              | Q100             | 2.23%                                    | 31.55%                      | 65.90%              | 84.09%                            | 20.45%            |               0.572 |
| OTM3              | Q90              | 2.03%                                    | 24.05%                      | 73.40%              | 84.09%                            | 25.00%            |               0.573 |

### 选券审计

| check_name     | value                                                      | passed   | note                                                                    |
|:---------------|:-----------------------------------------------------------|:---------|:------------------------------------------------------------------------|
| sample_window  | 2022-09-30 to 2026-05-27                                   | True     | main_stepA_common_sample                                                |
| source_engine  | ver2_downside_protection.strategy_engine.run_ver2_backtest | True     | continuous_30d daily MTM, not src.backtest.custom monthly segmented NAV |
| option_source  | data/raw/options_daily.csv                                 | True     | daily option chain                                                      |
| ATM_selection  | selected=44; skipped=0; avg_realized_moneyness=-0.0004     | True     | target_moneyness=0.00%                                                  |
| OTM1_selection | selected=44; skipped=0; avg_realized_moneyness=0.0111      | True     | target_moneyness=1.00%                                                  |
| OTM2_selection | selected=44; skipped=0; avg_realized_moneyness=0.0203      | True     | target_moneyness=2.00%                                                  |
| OTM3_selection | selected=44; skipped=0; avg_realized_moneyness=0.0299      | True     | target_moneyness=3.00%                                                  |
| OTM4_selection | selected=44; skipped=0; avg_realized_moneyness=0.0393      | True     | target_moneyness=4.00%                                                  |
| OTM5_selection | selected=44; skipped=0; avg_realized_moneyness=0.0512      | True     | target_moneyness=5.00%                                                  |
| OTM7_selection | selected=44; skipped=0; avg_realized_moneyness=0.0703      | True     | target_moneyness=7.00%                                                  |
| daily_rows     | 62551                                                      | True     | 71 sleeves including BuyHold                                            |
| period_rows    | 3080                                                       | True     | surface period attribution rows                                         |

### 图表

- sharpe_daily_mean: `outputs/ver3_0_stepA_moneyness_refined_surface/figures/510050_sharpe_daily_mean_surface.png`
- annualized_return_cagr: `outputs/ver3_0_stepA_moneyness_refined_surface/figures/510050_annualized_return_cagr_surface.png`
- max_drawdown: `outputs/ver3_0_stepA_moneyness_refined_surface/figures/510050_max_drawdown_surface.png`
- option_leg_annualized_pnl_contribution: `outputs/ver3_0_stepA_moneyness_refined_surface/figures/510050_option_leg_annualized_pnl_contribution_surface.png`
- selected_nav_paths: `outputs/ver3_0_stepA_moneyness_refined_surface/figures/510050_selected_nav_paths.png`
