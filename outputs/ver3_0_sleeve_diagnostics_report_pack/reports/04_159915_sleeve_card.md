# ETF Sleeve Card | 159915

## 1. 标的定位

成长弹性 / 高波动 / 高右尾风险

## 2. 候选 sleeve 列表

| sleeve_name                    | classification     | recommendation_status       |
|:-------------------------------|:-------------------|:----------------------------|
| 159915_DTE30_D40_Q100_Hold     | Stress Test Only   | diagnostic_only             |
| 159915_DTE30_OTM5up_Q100_Hold  | Stress Test Only   | diagnostic_only             |
| 159915_DTE30_OTM5up_Q100_TP80  | Stress Test Only   | diagnostic_only             |
| 159915_DTE30_OTM5up_Q50_Hold   | Defensive Overlay  | primary_for_portfolio_layer |
| 159915_DTE30_OTM5up_Q50_TP80   | Diagnostic Only    | diagnostic_only             |
| 159915_DTE30_OTM5up_Q50_TouchK | Stress Test Only   | diagnostic_only             |
| 159915_ETF_BuyHold             | Pure ETF Preferred | backup_for_portfolio_layer  |

## 3. 核心绩效对比

| sleeve_name                    | annualized_return_cagr   |   sharpe_daily_mean | max_drawdown   | option_leg_annualized_pnl_contribution   | p99_short_call_mtm_loss   |
|:-------------------------------|:-------------------------|--------------------:|:---------------|:-----------------------------------------|:--------------------------|
| 159915_DTE30_D40_Q100_Hold     | 10.82%                   |               0.637 | 29.38%         | -9.07%                                   | 16.90%                    |
| 159915_DTE30_OTM5up_Q100_Hold  | 12.44%                   |               0.644 | 36.77%         | -7.01%                                   | 14.88%                    |
| 159915_DTE30_OTM5up_Q100_TP80  | 14.02%                   |               0.699 | 37.28%         | -5.53%                                   | 14.88%                    |
| 159915_DTE30_OTM5up_Q50_Hold   | 15.80%                   |               0.722 | 38.65%         | -3.51%                                   | 7.44%                     |
| 159915_DTE30_OTM5up_Q50_TP80   | 16.60%                   |               0.746 | 38.90%         | -2.77%                                   | 7.44%                     |
| 159915_DTE30_OTM5up_Q50_TouchK | 16.26%                   |               0.648 | 39.94%         | -1.62%                                   | 0.62%                     |
| 159915_ETF_BuyHold             | 17.66%                   |               0.67  | 40.88%         | 0.00%                                    | 0.00%                     |

## 4. Option-leg 质量

| sleeve_name                    | premium_capture_ratio_agg   | payoff_burden_agg   | positive_option_leg_period_rate   | assignment_rate   | early_close_rate   |
|:-------------------------------|:----------------------------|:--------------------|:----------------------------------|:------------------|:-------------------|
| 159915_DTE30_D40_Q100_Hold     | -39.10%                     | 136.55%             | 70.45%                            | 36.36%            | 0.00%              |
| 159915_DTE30_OTM5up_Q100_Hold  | -65.55%                     | 163.00%             | 81.82%                            | 25.00%            | 0.00%              |
| 159915_DTE30_OTM5up_Q100_TP80  | -51.74%                     | 148.91%             | 86.36%                            | 15.91%            | 84.09%             |
| 159915_DTE30_OTM5up_Q50_Hold   | -65.55%                     | 163.00%             | 81.82%                            | 25.00%            | 0.00%              |
| 159915_DTE30_OTM5up_Q50_TP80   | -51.74%                     | 148.91%             | 86.36%                            | 15.91%            | 84.09%             |
| 159915_DTE30_OTM5up_Q50_TouchK | -30.28%                     | 124.60%             | 65.91%                            | 0.00%             | 38.64%             |
| 159915_ETF_BuyHold             |                             |                     |                                   |                   | 0.00%              |

## 5. 风险路径

| sleeve_name                    | max_drawdown   | p95_short_call_mtm_loss   | p99_short_call_mtm_loss   | max_short_call_mtm_loss   |
|:-------------------------------|:---------------|:--------------------------|:--------------------------|:--------------------------|
| 159915_DTE30_D40_Q100_Hold     | 29.38%         | 4.89%                     | 16.90%                    | 51.60%                    |
| 159915_DTE30_OTM5up_Q100_Hold  | 36.77%         | 2.75%                     | 14.88%                    | 50.23%                    |
| 159915_DTE30_OTM5up_Q100_TP80  | 37.28%         | 2.36%                     | 14.88%                    | 50.23%                    |
| 159915_DTE30_OTM5up_Q50_Hold   | 38.65%         | 1.38%                     | 7.44%                     | 25.11%                    |
| 159915_DTE30_OTM5up_Q50_TP80   | 38.90%         | 1.18%                     | 7.44%                     | 25.11%                    |
| 159915_DTE30_OTM5up_Q50_TouchK | 39.94%         | 0.27%                     | 0.62%                     | 1.38%                     |
| 159915_ETF_BuyHold             | 40.88%         | 0.00%                     | 0.00%                     | 0.00%                     |

政策跳涨窗口涉及的 option 周期数：12。Touch-K / Q100 均只作为 appendix 或 stress，不作为默认组合层主线。

## 6. 执行与选券

| sleeve_name                    | avg_actual_dte   | avg_entry_delta   | median_entry_delta   | avg_realized_moneyness   |   gap_periods | avg_active_coverage   |
|:-------------------------------|:-----------------|:------------------|:---------------------|:-------------------------|--------------:|:----------------------|
| 159915_DTE30_D40_Q100_Hold     | 29.614           | 0.400             | 0.400                | 2.12%                    |             0 | 100.00%               |
| 159915_DTE30_OTM5up_Q100_Hold  | 29.614           | 0.203             | 0.192                | 6.31%                    |             0 | 100.00%               |
| 159915_DTE30_OTM5up_Q100_TP80  | 29.614           | 0.203             | 0.192                | 6.31%                    |             0 | 63.60%                |
| 159915_DTE30_OTM5up_Q50_Hold   | 29.614           | 0.203             | 0.192                | 6.31%                    |             0 | 50.00%                |
| 159915_DTE30_OTM5up_Q50_TP80   | 29.614           | 0.203             | 0.192                | 6.31%                    |             0 | 31.80%                |
| 159915_DTE30_OTM5up_Q50_TouchK | 29.614           | 0.203             | 0.192                | 6.31%                    |             0 | 40.79%                |
| 159915_ETF_BuyHold             |                  |                   |                      |                          |             0 | 0.00%                 |

## 7. Sleeve 分类

| sleeve_name                    | classification     | reason                                                                            | caveat                                                           |
|:-------------------------------|:-------------------|:----------------------------------------------------------------------------------|:-----------------------------------------------------------------|
| 159915_ETF_BuyHold             | Pure ETF Preferred | ETF-only baseline for comparison.                                                 | No option leg.                                                   |
| 159915_DTE30_D40_Q100_Hold     | Stress Test Only   | Q100 is retained as a full-coverage stress test.                                  | Do not promote by default even when in-sample metrics look good. |
| 159915_DTE30_OTM5up_Q50_Hold   | Defensive Overlay  | Net option leg is not positive, but drawdown improves enough with similar Sharpe. | Use as risk-control sleeve, not income enhancement.              |
| 159915_DTE30_OTM5up_Q100_Hold  | Stress Test Only   | Q100 is retained as a full-coverage stress test.                                  | Do not promote by default even when in-sample metrics look good. |
| 159915_DTE30_OTM5up_Q50_TP80   | Diagnostic Only    | TP80 close-and-wait is a path-management diagnostic.                              | Closed cycles wait to original expiry; no immediate rewrite.     |
| 159915_DTE30_OTM5up_Q100_TP80  | Stress Test Only   | Q100 is retained as a full-coverage stress test.                                  | Do not promote by default even when in-sample metrics look good. |
| 159915_DTE30_OTM5up_Q50_TouchK | Stress Test Only   | Touch-K is retained as rejected appendix diagnostic.                              | Not a default portfolio-layer sleeve.                            |

## 8. 推荐进入组合层的 sleeve

- primary_sleeve_for_portfolio_layer: 159915_DTE30_OTM5up_Q50_Hold
- backup_sleeve: 159915_ETF_BuyHold
- rejected_sleeves: 159915_DTE30_D40_Q100_Hold, 159915_DTE30_OTM5up_Q100_Hold, 159915_DTE30_OTM5up_Q50_TP80, 159915_DTE30_OTM5up_Q100_TP80, 159915_DTE30_OTM5up_Q50_TouchK
- rationale: Net option leg is not positive, but drawdown improves enough with similar Sharpe.
- caveat: Use as risk-control sleeve, not income enhancement.
