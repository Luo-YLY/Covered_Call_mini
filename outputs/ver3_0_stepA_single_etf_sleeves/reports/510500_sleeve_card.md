# ETF Sleeve Card | 510500

## 1. 标的定位

中盘弹性 / 潜在防御 overlay

## 2. 候选 sleeve 列表

| sleeve_name                   | classification     | recommendation_status       |
|:------------------------------|:-------------------|:----------------------------|
| 510500_DTE30_D40_Q100_Hold    | Stress Test Only   | diagnostic_only             |
| 510500_DTE30_OTM5up_Q100_Hold | Stress Test Only   | diagnostic_only             |
| 510500_DTE30_OTM5up_Q50_Hold  | Defensive Overlay  | primary_for_portfolio_layer |
| 510500_ETF_BuyHold            | Pure ETF Preferred | backup_for_portfolio_layer  |

## 3. 核心绩效对比

| sleeve_name                   | annualized_return_cagr   |   sharpe_daily_mean | max_drawdown   | option_leg_annualized_pnl_contribution   | p99_short_call_mtm_loss   |
|:------------------------------|:-------------------------|--------------------:|:---------------|:-----------------------------------------|:--------------------------|
| 510500_DTE30_D40_Q100_Hold    | 2.82%                    |               0.267 | 23.48%         | -10.33%                                  | 12.78%                    |
| 510500_DTE30_OTM5up_Q100_Hold | 7.96%                    |               0.533 | 26.86%         | -5.00%                                   | 11.00%                    |
| 510500_DTE30_OTM5up_Q50_Hold  | 10.33%                   |               0.612 | 28.41%         | -2.50%                                   | 5.50%                     |
| 510500_ETF_BuyHold            | 12.48%                   |               0.646 | 30.16%         | 0.00%                                    | 0.00%                     |

## 4. Option-leg 质量

| sleeve_name                   | premium_capture_ratio_agg   | payoff_burden_agg   | positive_option_leg_period_rate   | assignment_rate   | early_close_rate   |
|:------------------------------|:----------------------------|:--------------------|:----------------------------------|:------------------|:-------------------|
| 510500_DTE30_D40_Q100_Hold    | -59.93%                     | 157.38%             | 65.91%                            | 43.18%            | 0.00%              |
| 510500_DTE30_OTM5up_Q100_Hold | -66.93%                     | 164.38%             | 84.09%                            | 25.00%            | 0.00%              |
| 510500_DTE30_OTM5up_Q50_Hold  | -66.93%                     | 164.38%             | 84.09%                            | 25.00%            | 0.00%              |
| 510500_ETF_BuyHold            |                             |                     |                                   |                   | 0.00%              |

## 5. 风险路径

| sleeve_name                   | max_drawdown   | p95_short_call_mtm_loss   | p99_short_call_mtm_loss   | max_short_call_mtm_loss   |
|:------------------------------|:---------------|:--------------------------|:--------------------------|:--------------------------|
| 510500_DTE30_D40_Q100_Hold    | 23.48%         | 3.14%                     | 12.78%                    | 26.90%                    |
| 510500_DTE30_OTM5up_Q100_Hold | 26.86%         | 1.61%                     | 11.00%                    | 25.62%                    |
| 510500_DTE30_OTM5up_Q50_Hold  | 28.41%         | 0.81%                     | 5.50%                     | 12.81%                    |
| 510500_ETF_BuyHold            | 30.16%         | 0.00%                     | 0.00%                     | 0.00%                     |

政策跳涨窗口涉及的 option 周期数：0。TP80 / Touch-K 已从当前 Step A 主线排除；Q100 仅作为 stress diagnostic，不作为默认组合层主线。

## 6. 执行与选券

| sleeve_name                   | avg_actual_dte   | avg_entry_delta   | median_entry_delta   | avg_realized_moneyness   |   gap_periods | avg_active_coverage   |
|:------------------------------|:-----------------|:------------------|:---------------------|:-------------------------|--------------:|:----------------------|
| 510500_DTE30_D40_Q100_Hold    | 30.341           | 0.389             | 0.384                | 1.77%                    |             0 | 100.00%               |
| 510500_DTE30_OTM5up_Q100_Hold | 30.341           | 0.197             | 0.197                | 5.02%                    |             0 | 100.00%               |
| 510500_DTE30_OTM5up_Q50_Hold  | 30.341           | 0.197             | 0.197                | 5.02%                    |             0 | 50.00%                |
| 510500_ETF_BuyHold            |                  |                   |                      |                          |             0 | 0.00%                 |

## 7. Sleeve 分类

| sleeve_name                   | classification     | reason                                                                            | caveat                                                           |
|:------------------------------|:-------------------|:----------------------------------------------------------------------------------|:-----------------------------------------------------------------|
| 510500_ETF_BuyHold            | Pure ETF Preferred | ETF-only baseline for comparison.                                                 | No option leg.                                                   |
| 510500_DTE30_D40_Q100_Hold    | Stress Test Only   | Q100 is retained as a full-coverage stress test.                                  | Do not promote by default even when in-sample metrics look good. |
| 510500_DTE30_OTM5up_Q50_Hold  | Defensive Overlay  | Net option leg is not positive, but drawdown improves enough with similar Sharpe. | Use as risk-control sleeve, not income enhancement.              |
| 510500_DTE30_OTM5up_Q100_Hold | Stress Test Only   | Q100 is retained as a full-coverage stress test.                                  | Do not promote by default even when in-sample metrics look good. |

## 8. 推荐进入组合层的 sleeve

- primary_sleeve_for_portfolio_layer: 510500_DTE30_OTM5up_Q50_Hold
- backup_sleeve: 510500_ETF_BuyHold
- rejected_sleeves: 510500_DTE30_D40_Q100_Hold, 510500_DTE30_OTM5up_Q100_Hold
- rationale: Net option leg is not positive, but drawdown improves enough with similar Sharpe.
- caveat: Use as risk-control sleeve, not income enhancement.
