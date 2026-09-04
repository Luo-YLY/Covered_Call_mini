# ETF Sleeve Card | 159915

## 1. 标的定位

成长弹性 / 高波动 / 高右尾风险

## 2. 候选 sleeve 列表

| sleeve_name                   | classification     | recommendation_status       |
|:------------------------------|:-------------------|:----------------------------|
| 159915_DTE30_D40_Q100_Hold    | Stress Test Only   | diagnostic_only             |
| 159915_DTE30_OTM5up_Q100_Hold | Stress Test Only   | diagnostic_only             |
| 159915_DTE30_OTM5up_Q50_Hold  | Defensive Overlay  | primary_for_portfolio_layer |
| 159915_ETF_BuyHold            | Pure ETF Preferred | backup_for_portfolio_layer  |

## 3. 核心绩效对比

| sleeve_name                   | annualized_return_cagr   |   sharpe_daily_mean | max_drawdown   | option_leg_annualized_pnl_contribution   | p99_short_call_mtm_loss   |
|:------------------------------|:-------------------------|--------------------:|:---------------|:-----------------------------------------|:--------------------------|
| 159915_DTE30_D40_Q100_Hold    | 7.76%                    |               0.512 | 28.76%         | -13.08%                                  | 23.31%                    |
| 159915_DTE30_OTM5up_Q100_Hold | 9.49%                    |               0.554 | 34.70%         | -11.06%                                  | 20.91%                    |
| 159915_DTE30_OTM5up_Q50_Hold  | 14.58%                   |               0.677 | 37.68%         | -5.53%                                   | 10.45%                    |
| 159915_ETF_BuyHold            | 18.82%                   |               0.7   | 40.88%         | 0.00%                                    | 0.00%                     |

## 4. Option-leg 质量

| sleeve_name                   | premium_capture_ratio_agg   | payoff_burden_agg   | positive_option_leg_period_rate   | assignment_rate   | early_close_rate   |
|:------------------------------|:----------------------------|:--------------------|:----------------------------------|:------------------|:-------------------|
| 159915_DTE30_D40_Q100_Hold    | -56.58%                     | 154.03%             | 68.18%                            | 38.64%            | 0.00%              |
| 159915_DTE30_OTM5up_Q100_Hold | -77.51%                     | 174.96%             | 75.00%                            | 27.27%            | 0.00%              |
| 159915_DTE30_OTM5up_Q50_Hold  | -77.51%                     | 174.96%             | 75.00%                            | 27.27%            | 0.00%              |
| 159915_ETF_BuyHold            |                             |                     |                                   |                   | 0.00%              |

## 5. 风险路径

| sleeve_name                   | max_drawdown   | p95_short_call_mtm_loss   | p99_short_call_mtm_loss   | max_short_call_mtm_loss   |
|:------------------------------|:---------------|:--------------------------|:--------------------------|:--------------------------|
| 159915_DTE30_D40_Q100_Hold    | 28.76%         | 5.13%                     | 23.31%                    | 60.84%                    |
| 159915_DTE30_OTM5up_Q100_Hold | 34.70%         | 3.44%                     | 20.91%                    | 58.78%                    |
| 159915_DTE30_OTM5up_Q50_Hold  | 37.68%         | 1.72%                     | 10.45%                    | 29.39%                    |
| 159915_ETF_BuyHold            | 40.88%         | 0.00%                     | 0.00%                     | 0.00%                     |

政策跳涨窗口涉及的 option 周期数：0。TP80 / Touch-K 已从当前 Step A 主线排除；Q100 仅作为 stress diagnostic，不作为默认组合层主线。

## 6. 执行与选券

| sleeve_name                   | avg_actual_dte   | avg_entry_delta   | median_entry_delta   | avg_realized_moneyness   |   gap_periods | avg_active_coverage   |
|:------------------------------|:-----------------|:------------------|:---------------------|:-------------------------|--------------:|:----------------------|
| 159915_DTE30_D40_Q100_Hold    | 30.341           | 0.385             | 0.374                | 2.49%                    |             0 | 100.00%               |
| 159915_DTE30_OTM5up_Q100_Hold | 30.341           | 0.249             | 0.237                | 5.21%                    |             0 | 100.00%               |
| 159915_DTE30_OTM5up_Q50_Hold  | 30.341           | 0.249             | 0.237                | 5.21%                    |             0 | 50.00%                |
| 159915_ETF_BuyHold            |                  |                   |                      |                          |             0 | 0.00%                 |

## 7. Sleeve 分类

| sleeve_name                   | classification     | reason                                                                            | caveat                                                           |
|:------------------------------|:-------------------|:----------------------------------------------------------------------------------|:-----------------------------------------------------------------|
| 159915_ETF_BuyHold            | Pure ETF Preferred | ETF-only baseline for comparison.                                                 | No option leg.                                                   |
| 159915_DTE30_D40_Q100_Hold    | Stress Test Only   | Q100 is retained as a full-coverage stress test.                                  | Do not promote by default even when in-sample metrics look good. |
| 159915_DTE30_OTM5up_Q50_Hold  | Defensive Overlay  | Net option leg is not positive, but drawdown improves enough with similar Sharpe. | Use as risk-control sleeve, not income enhancement.              |
| 159915_DTE30_OTM5up_Q100_Hold | Stress Test Only   | Q100 is retained as a full-coverage stress test.                                  | Do not promote by default even when in-sample metrics look good. |

## 8. 推荐进入组合层的 sleeve

- primary_sleeve_for_portfolio_layer: 159915_DTE30_OTM5up_Q50_Hold
- backup_sleeve: 159915_ETF_BuyHold
- rejected_sleeves: 159915_DTE30_D40_Q100_Hold, 159915_DTE30_OTM5up_Q100_Hold
- rationale: Net option leg is not positive, but drawdown improves enough with similar Sharpe.
- caveat: Use as risk-control sleeve, not income enhancement.
