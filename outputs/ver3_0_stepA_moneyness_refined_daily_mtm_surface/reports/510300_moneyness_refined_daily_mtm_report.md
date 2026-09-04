## 510300

大盘核心资产；用于检验更细 OTM 梯度是否改变 510300 的 Step A 画像。

- 样本: 2022-09-30 至 2026-05-27；范围: main_stepA_common_sample。
- BuyHold: Sharpe 0.484，CAGR 7.21%，MDD 24.19%。
- Sharpe 最高点: OTM4 Q100，Sharpe 0.753，CAGR 9.31%，MDD 18.53%，期权腿 1.25%。
- 读取: dominates buyhold in this diagnostic grid；期权腿判断: positive option leg。

### Sharpe 前五

| moneyness_label   | coverage_label   |   sharpe_daily_mean | annualized_return_cagr   | max_drawdown   | option_leg_annualized_pnl_contribution   | avg_realized_moneyness   | recommendation_read                                    |
|:------------------|:-----------------|--------------------:|:-------------------------|:---------------|:-----------------------------------------|:-------------------------|:-------------------------------------------------------|
| OTM4              | Q100             |               0.753 | 9.31%                    | 18.53%         | 1.25%                                    | 3.84%                    | dominates buyhold in this diagnostic grid              |
| OTM4              | Q90              |               0.728 | 9.13%                    | 19.11%         | 1.12%                                    | 3.84%                    | dominates buyhold in this diagnostic grid              |
| OTM1              | Q100             |               0.709 | 6.99%                    | 12.87%         | -1.20%                                   | 0.81%                    | risk-adjusted defensive tradeoff, not a return upgrade |
| OTM4              | Q80              |               0.701 | 8.95%                    | 19.69%         | 1.00%                                    | 3.84%                    | dominates buyhold in this diagnostic grid              |
| OTM2              | Q100             |               0.701 | 7.58%                    | 16.02%         | -0.53%                                   | 2.06%                    | dominates buyhold in this diagnostic grid              |

### 各 moneyness 的最优覆盖率

| moneyness_label   | coverage_label   |   sharpe_daily_mean | annualized_return_cagr   | max_drawdown   | option_leg_annualized_pnl_contribution   | avg_realized_moneyness   |
|:------------------|:-----------------|--------------------:|:-------------------------|:---------------|:-----------------------------------------|:-------------------------|
| ATM               | Q80              |               0.538 | 5.30%                    | 14.70%         | -2.75%                                   | 0.24%                    |
| OTM1              | Q100             |               0.709 | 6.99%                    | 12.87%         | -1.20%                                   | 0.81%                    |
| OTM2              | Q100             |               0.701 | 7.58%                    | 16.02%         | -0.53%                                   | 2.06%                    |
| OTM3              | Q100             |               0.653 | 7.57%                    | 18.06%         | -0.43%                                   | 3.10%                    |
| OTM4              | Q100             |               0.753 | 9.31%                    | 18.53%         | 1.25%                                    | 3.84%                    |
| OTM5              | Q100             |               0.636 | 8.01%                    | 20.56%         | 0.14%                                    | 5.14%                    |
| OTM7              | Q100             |               0.608 | 8.00%                    | 22.13%         | 0.24%                                    | 7.02%                    |

### 期权腿前五

| moneyness_label   | coverage_label   | option_leg_annualized_pnl_contribution   | premium_capture_ratio_agg   | payoff_burden_agg   | positive_option_leg_period_rate   | assignment_rate   |   sharpe_daily_mean |
|:------------------|:-----------------|:-----------------------------------------|:----------------------------|:--------------------|:----------------------------------|:------------------|--------------------:|
| OTM4              | Q100             | 1.25%                                    | 18.84%                      | 78.61%              | 86.36%                            | 13.64%            |               0.753 |
| OTM4              | Q90              | 1.12%                                    | 18.84%                      | 78.61%              | 86.36%                            | 13.64%            |               0.728 |
| OTM4              | Q80              | 1.00%                                    | 18.84%                      | 78.61%              | 86.36%                            | 13.64%            |               0.701 |
| OTM4              | Q70              | 0.87%                                    | 18.84%                      | 78.61%              | 86.36%                            | 13.64%            |               0.673 |
| OTM4              | Q60              | 0.75%                                    | 18.84%                      | 78.61%              | 86.36%                            | 13.64%            |               0.645 |

### 选券审计

| check_name     | value                                                      | passed   | note                                                                    |
|:---------------|:-----------------------------------------------------------|:---------|:------------------------------------------------------------------------|
| sample_window  | 2022-09-30 to 2026-05-27                                   | True     | main_stepA_common_sample                                                |
| source_engine  | ver2_downside_protection.strategy_engine.run_ver2_backtest | True     | continuous_30d daily MTM, not src.backtest.custom monthly segmented NAV |
| option_source  | data/raw/options_daily.csv                                 | True     | daily option chain                                                      |
| ATM_selection  | selected=44; skipped=0; avg_realized_moneyness=0.0024      | True     | target_moneyness=0.00%                                                  |
| OTM1_selection | selected=44; skipped=0; avg_realized_moneyness=0.0081      | True     | target_moneyness=1.00%                                                  |
| OTM2_selection | selected=44; skipped=0; avg_realized_moneyness=0.0206      | True     | target_moneyness=2.00%                                                  |
| OTM3_selection | selected=44; skipped=0; avg_realized_moneyness=0.0310      | True     | target_moneyness=3.00%                                                  |
| OTM4_selection | selected=44; skipped=0; avg_realized_moneyness=0.0384      | True     | target_moneyness=4.00%                                                  |
| OTM5_selection | selected=44; skipped=0; avg_realized_moneyness=0.0514      | True     | target_moneyness=5.00%                                                  |
| OTM7_selection | selected=44; skipped=0; avg_realized_moneyness=0.0702      | True     | target_moneyness=7.00%                                                  |
| daily_rows     | 62551                                                      | True     | 71 sleeves including BuyHold                                            |
| period_rows    | 3080                                                       | True     | surface period attribution rows                                         |

### 图表

- sharpe_daily_mean: `outputs/ver3_0_stepA_moneyness_refined_daily_mtm_surface/figures/510300_sharpe_daily_mean_surface.png`
- sharpe_daily_mean_3d_surface: `outputs/ver3_0_stepA_moneyness_refined_daily_mtm_surface/figures/510300_sharpe_daily_mean_3d_surface.png`
- annualized_return_cagr: `outputs/ver3_0_stepA_moneyness_refined_daily_mtm_surface/figures/510300_annualized_return_cagr_surface.png`
- annualized_return_cagr_3d_surface: `outputs/ver3_0_stepA_moneyness_refined_daily_mtm_surface/figures/510300_annualized_return_cagr_3d_surface.png`
- max_drawdown: `outputs/ver3_0_stepA_moneyness_refined_daily_mtm_surface/figures/510300_max_drawdown_surface.png`
- max_drawdown_3d_surface: `outputs/ver3_0_stepA_moneyness_refined_daily_mtm_surface/figures/510300_max_drawdown_3d_surface.png`
- option_leg_annualized_pnl_contribution: `outputs/ver3_0_stepA_moneyness_refined_daily_mtm_surface/figures/510300_option_leg_annualized_pnl_contribution_surface.png`
- option_leg_annualized_pnl_contribution_3d_surface: `outputs/ver3_0_stepA_moneyness_refined_daily_mtm_surface/figures/510300_option_leg_annualized_pnl_contribution_3d_surface.png`
- selected_nav_paths: `outputs/ver3_0_stepA_moneyness_refined_daily_mtm_surface/figures/510300_selected_nav_paths.png`
