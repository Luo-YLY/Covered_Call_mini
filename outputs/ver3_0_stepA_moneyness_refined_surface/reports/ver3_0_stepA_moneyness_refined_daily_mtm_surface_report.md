# ver3.0 Step A moneyness refined daily-MTM surface report

## 口径边界

- 本报告接替此前未完成的 moneyness 细网格任务，但不沿用 Monthly custom 回测。
- 选券与日频 NAV 均来自 `ver2_downside_protection.strategy_engine.run_ver2_backtest` 的 `continuous_30d` 日频 MTM 口径。
- moneyness 维度重新选券；coverage 维度在同一 Q100 选券路径上缩放 option leg，用于观察虚值程度 x 覆盖率曲面。
- 588000 因期权数据起点较晚，仍为 short-sample extension，不进入同样本主线替代结论。

## 总览

|   etf_code | sample_scope             |   buyhold_sharpe | buyhold_cagr   | best_point   |   best_sharpe | best_cagr   | best_mdd   | best_option_leg   | read                                                   |
|-----------:|:-------------------------|-----------------:|:---------------|:-------------|--------------:|:------------|:-----------|:------------------|:-------------------------------------------------------|
|     510300 | main_stepA_common_sample |            0.484 | 7.21%          | OTM4 Q100    |         0.753 | 9.31%       | 18.53%     | 1.25%             | dominates buyhold in this diagnostic grid              |
|     510050 | main_stepA_common_sample |            0.303 | 3.70%          | ATM Q100     |         0.752 | 6.69%       | 9.41%      | 1.92%             | dominates buyhold in this diagnostic grid              |
|     510500 | main_stepA_common_sample |            0.646 | 12.48%         | OTM7 Q10     |         0.645 | 12.19%      | 29.82%     | -0.37%            | drawdown cushion with visible return cost              |
|     159915 | main_stepA_common_sample |            0.7   | 18.82%         | OTM7 Q20     |         0.702 | 17.50%      | 39.86%     | -1.91%            | risk-adjusted defensive tradeoff, not a return upgrade |
|     588000 | short_sample_extension   |            0.785 | 23.90%         | OTM1 Q10     |         0.782 | 22.48%      | 34.26%     | -1.85%            | drawdown cushion with visible return cost              |

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

- sharpe_daily_mean: `outputs/ver3_0_stepA_moneyness_refined_surface/figures/510300_sharpe_daily_mean_surface.png`
- annualized_return_cagr: `outputs/ver3_0_stepA_moneyness_refined_surface/figures/510300_annualized_return_cagr_surface.png`
- max_drawdown: `outputs/ver3_0_stepA_moneyness_refined_surface/figures/510300_max_drawdown_surface.png`
- option_leg_annualized_pnl_contribution: `outputs/ver3_0_stepA_moneyness_refined_surface/figures/510300_option_leg_annualized_pnl_contribution_surface.png`
- selected_nav_paths: `outputs/ver3_0_stepA_moneyness_refined_surface/figures/510300_selected_nav_paths.png`

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

- sharpe_daily_mean: `outputs/ver3_0_stepA_moneyness_refined_surface/figures/510500_sharpe_daily_mean_surface.png`
- annualized_return_cagr: `outputs/ver3_0_stepA_moneyness_refined_surface/figures/510500_annualized_return_cagr_surface.png`
- max_drawdown: `outputs/ver3_0_stepA_moneyness_refined_surface/figures/510500_max_drawdown_surface.png`
- option_leg_annualized_pnl_contribution: `outputs/ver3_0_stepA_moneyness_refined_surface/figures/510500_option_leg_annualized_pnl_contribution_surface.png`
- selected_nav_paths: `outputs/ver3_0_stepA_moneyness_refined_surface/figures/510500_selected_nav_paths.png`

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

- sharpe_daily_mean: `outputs/ver3_0_stepA_moneyness_refined_surface/figures/159915_sharpe_daily_mean_surface.png`
- annualized_return_cagr: `outputs/ver3_0_stepA_moneyness_refined_surface/figures/159915_annualized_return_cagr_surface.png`
- max_drawdown: `outputs/ver3_0_stepA_moneyness_refined_surface/figures/159915_max_drawdown_surface.png`
- option_leg_annualized_pnl_contribution: `outputs/ver3_0_stepA_moneyness_refined_surface/figures/159915_option_leg_annualized_pnl_contribution_surface.png`
- selected_nav_paths: `outputs/ver3_0_stepA_moneyness_refined_surface/figures/159915_selected_nav_paths.png`

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
