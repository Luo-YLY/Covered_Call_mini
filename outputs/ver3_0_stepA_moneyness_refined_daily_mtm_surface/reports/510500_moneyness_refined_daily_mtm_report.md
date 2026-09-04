## 510500

中盘弹性资产；重点观察轻度 OTM 与低覆盖率能否改善此前较差的备兑结果。

- 样本: 2022-09-30 至 2026-05-27；范围: main_stepA_common_sample。
- BuyHold: Sharpe 0.646，CAGR 12.48%，MDD 30.16%。
- Sharpe 最高点: OTM7 Q10，Sharpe 0.645，CAGR 12.19%，MDD 29.82%，期权腿 -0.37%。
- 读取: drawdown cushion with visible return cost；期权腿判断: near-flat option leg。

### Sharpe 前五

| moneyness_label   | coverage_label   |   sharpe_daily_mean | annualized_return_cagr   | max_drawdown   | option_leg_annualized_pnl_contribution   | avg_realized_moneyness   | recommendation_read                       |
|:------------------|:-----------------|--------------------:|:-------------------------|:---------------|:-----------------------------------------|:-------------------------|:------------------------------------------|
| OTM7              | Q10              |               0.645 | 12.19%                   | 29.82%         | -0.37%                                   | 6.77%                    | drawdown cushion with visible return cost |
| OTM5              | Q10              |               0.642 | 12.07%                   | 29.63%         | -0.50%                                   | 5.02%                    | drawdown cushion with visible return cost |
| OTM7              | Q20              |               0.642 | 11.88%                   | 29.64%         | -0.74%                                   | 6.77%                    | drawdown cushion with visible return cost |
| OTM4              | Q10              |               0.64  | 11.96%                   | 29.54%         | -0.61%                                   | 3.97%                    | drawdown cushion with visible return cost |
| OTM7              | Q30              |               0.639 | 11.58%                   | 29.48%         | -1.11%                                   | 6.77%                    | drawdown cushion with visible return cost |

### 各 moneyness 的最优覆盖率

| moneyness_label   | coverage_label   |   sharpe_daily_mean | annualized_return_cagr   | max_drawdown   | option_leg_annualized_pnl_contribution   | avg_realized_moneyness   |
|:------------------|:-----------------|--------------------:|:-------------------------|:---------------|:-----------------------------------------|:-------------------------|
| ATM               | Q10              |               0.634 | 11.60%                   | 28.70%         | -1.03%                                   | 0.14%                    |
| OTM1              | Q10              |               0.63  | 11.57%                   | 29.03%         | -1.04%                                   | 0.81%                    |
| OTM2              | Q10              |               0.626 | 11.52%                   | 29.40%         | -1.06%                                   | 1.85%                    |
| OTM3              | Q10              |               0.632 | 11.76%                   | 29.42%         | -0.81%                                   | 3.10%                    |
| OTM4              | Q10              |               0.64  | 11.96%                   | 29.54%         | -0.61%                                   | 3.97%                    |
| OTM5              | Q10              |               0.642 | 12.07%                   | 29.63%         | -0.50%                                   | 5.02%                    |
| OTM7              | Q10              |               0.645 | 12.19%                   | 29.82%         | -0.37%                                   | 6.77%                    |

### 期权腿前五

| moneyness_label   | coverage_label   | option_leg_annualized_pnl_contribution   | premium_capture_ratio_agg   | payoff_burden_agg   | positive_option_leg_period_rate   | assignment_rate   |   sharpe_daily_mean |
|:------------------|:-----------------|:-----------------------------------------|:----------------------------|:--------------------|:----------------------------------|:------------------|--------------------:|
| OTM7              | Q10              | -0.37%                                   | -74.09%                     | 171.54%             | 88.64%                            | 18.18%            |               0.645 |
| OTM5              | Q10              | -0.50%                                   | -66.93%                     | 164.38%             | 84.09%                            | 25.00%            |               0.642 |
| OTM4              | Q10              | -0.61%                                   | -62.43%                     | 159.88%             | 79.55%                            | 27.27%            |               0.64  |
| OTM7              | Q20              | -0.74%                                   | -74.09%                     | 171.54%             | 88.64%                            | 18.18%            |               0.642 |
| OTM3              | Q10              | -0.81%                                   | -67.79%                     | 165.24%             | 72.73%                            | 29.55%            |               0.632 |

### 选券审计

| check_name     | value                                                      | passed   | note                                                                    |
|:---------------|:-----------------------------------------------------------|:---------|:------------------------------------------------------------------------|
| sample_window  | 2022-09-30 to 2026-05-27                                   | True     | main_stepA_common_sample                                                |
| source_engine  | ver2_downside_protection.strategy_engine.run_ver2_backtest | True     | continuous_30d daily MTM, not src.backtest.custom monthly segmented NAV |
| option_source  | data/raw/options_daily.csv                                 | True     | daily option chain                                                      |
| ATM_selection  | selected=44; skipped=0; avg_realized_moneyness=0.0014      | True     | target_moneyness=0.00%                                                  |
| OTM1_selection | selected=44; skipped=0; avg_realized_moneyness=0.0081      | True     | target_moneyness=1.00%                                                  |
| OTM2_selection | selected=44; skipped=0; avg_realized_moneyness=0.0185      | True     | target_moneyness=2.00%                                                  |
| OTM3_selection | selected=44; skipped=0; avg_realized_moneyness=0.0310      | True     | target_moneyness=3.00%                                                  |
| OTM4_selection | selected=44; skipped=0; avg_realized_moneyness=0.0397      | True     | target_moneyness=4.00%                                                  |
| OTM5_selection | selected=44; skipped=0; avg_realized_moneyness=0.0502      | True     | target_moneyness=5.00%                                                  |
| OTM7_selection | selected=44; skipped=0; avg_realized_moneyness=0.0677      | True     | target_moneyness=7.00%                                                  |
| daily_rows     | 62551                                                      | True     | 71 sleeves including BuyHold                                            |
| period_rows    | 3080                                                       | True     | surface period attribution rows                                         |

### 图表

- sharpe_daily_mean: `outputs/ver3_0_stepA_moneyness_refined_daily_mtm_surface/figures/510500_sharpe_daily_mean_surface.png`
- sharpe_daily_mean_3d_surface: `outputs/ver3_0_stepA_moneyness_refined_daily_mtm_surface/figures/510500_sharpe_daily_mean_3d_surface.png`
- annualized_return_cagr: `outputs/ver3_0_stepA_moneyness_refined_daily_mtm_surface/figures/510500_annualized_return_cagr_surface.png`
- annualized_return_cagr_3d_surface: `outputs/ver3_0_stepA_moneyness_refined_daily_mtm_surface/figures/510500_annualized_return_cagr_3d_surface.png`
- max_drawdown: `outputs/ver3_0_stepA_moneyness_refined_daily_mtm_surface/figures/510500_max_drawdown_surface.png`
- max_drawdown_3d_surface: `outputs/ver3_0_stepA_moneyness_refined_daily_mtm_surface/figures/510500_max_drawdown_3d_surface.png`
- option_leg_annualized_pnl_contribution: `outputs/ver3_0_stepA_moneyness_refined_daily_mtm_surface/figures/510500_option_leg_annualized_pnl_contribution_surface.png`
- option_leg_annualized_pnl_contribution_3d_surface: `outputs/ver3_0_stepA_moneyness_refined_daily_mtm_surface/figures/510500_option_leg_annualized_pnl_contribution_3d_surface.png`
- selected_nav_paths: `outputs/ver3_0_stepA_moneyness_refined_daily_mtm_surface/figures/510500_selected_nav_paths.png`
