# ETF Sleeve Card | 510500

## 1. 标的定位

中盘弹性 / 潜在防御 overlay

## 2. 候选 sleeve 列表

| sleeve_name                    | classification     | recommendation_status       |
|:-------------------------------|:-------------------|:----------------------------|
| 510500_DTE30_D40_Q100_Hold     | Stress Test Only   | diagnostic_only             |
| 510500_DTE30_OTM5up_Q100_Hold  | Stress Test Only   | diagnostic_only             |
| 510500_DTE30_OTM5up_Q100_TP80  | Stress Test Only   | diagnostic_only             |
| 510500_DTE30_OTM5up_Q50_Hold   | Pure ETF Preferred | rejected                    |
| 510500_DTE30_OTM5up_Q50_TP80   | Diagnostic Only    | diagnostic_only             |
| 510500_DTE30_OTM5up_Q50_TouchK | Stress Test Only   | diagnostic_only             |
| 510500_ETF_BuyHold             | Pure ETF Preferred | primary_for_portfolio_layer |

## 3. 核心绩效对比

| sleeve_name                    | annualized_return_cagr   |   sharpe_daily_mean | max_drawdown   | option_leg_annualized_pnl_contribution   | p99_short_call_mtm_loss   |
|:-------------------------------|:-------------------------|--------------------:|:---------------|:-----------------------------------------|:--------------------------|
| 510500_DTE30_D40_Q100_Hold     | 6.59%                    |               0.491 | 23.93%         | -5.45%                                   | 9.66%                     |
| 510500_DTE30_OTM5up_Q100_Hold  | 8.87%                    |               0.547 | 28.91%         | -2.76%                                   | 6.23%                     |
| 510500_DTE30_OTM5up_Q100_TP80  | 9.26%                    |               0.561 | 29.04%         | -2.35%                                   | 6.23%                     |
| 510500_DTE30_OTM5up_Q50_Hold   | 10.14%                   |               0.584 | 29.42%         | -1.38%                                   | 3.12%                     |
| 510500_DTE30_OTM5up_Q50_TP80   | 10.33%                   |               0.59  | 29.49%         | -1.17%                                   | 3.12%                     |
| 510500_DTE30_OTM5up_Q50_TouchK | 9.42%                    |               0.537 | 29.42%         | -1.86%                                   | 0.43%                     |
| 510500_ETF_BuyHold             | 11.22%                   |               0.595 | 30.16%         | 0.00%                                    | 0.00%                     |

## 4. Option-leg 质量

| sleeve_name                    | premium_capture_ratio_agg   | payoff_burden_agg   | positive_option_leg_period_rate   | assignment_rate   | early_close_rate   |
|:-------------------------------|:----------------------------|:--------------------|:----------------------------------|:------------------|:-------------------|
| 510500_DTE30_D40_Q100_Hold     | -31.63%                     | 129.08%             | 65.91%                            | 43.18%            | 0.00%              |
| 510500_DTE30_OTM5up_Q100_Hold  | -55.61%                     | 153.06%             | 84.09%                            | 15.91%            | 0.00%              |
| 510500_DTE30_OTM5up_Q100_TP80  | -47.38%                     | 144.53%             | 88.64%                            | 11.36%            | 88.64%             |
| 510500_DTE30_OTM5up_Q50_Hold   | -55.61%                     | 153.06%             | 84.09%                            | 15.91%            | 0.00%              |
| 510500_DTE30_OTM5up_Q50_TP80   | -47.38%                     | 144.53%             | 88.64%                            | 11.36%            | 88.64%             |
| 510500_DTE30_OTM5up_Q50_TouchK | -75.12%                     | 168.28%             | 77.27%                            | 0.00%             | 22.73%             |
| 510500_ETF_BuyHold             |                             |                     |                                   |                   | 0.00%              |

## 5. 风险路径

| sleeve_name                    | max_drawdown   | p95_short_call_mtm_loss   | p99_short_call_mtm_loss   | max_short_call_mtm_loss   |
|:-------------------------------|:---------------|:--------------------------|:--------------------------|:--------------------------|
| 510500_DTE30_D40_Q100_Hold     | 23.93%         | 3.64%                     | 9.66%                     | 18.57%                    |
| 510500_DTE30_OTM5up_Q100_Hold  | 28.91%         | 1.40%                     | 6.23%                     | 15.42%                    |
| 510500_DTE30_OTM5up_Q100_TP80  | 29.04%         | 1.18%                     | 6.23%                     | 15.42%                    |
| 510500_DTE30_OTM5up_Q50_Hold   | 29.42%         | 0.70%                     | 3.12%                     | 7.71%                     |
| 510500_DTE30_OTM5up_Q50_TP80   | 29.49%         | 0.59%                     | 3.12%                     | 7.71%                     |
| 510500_DTE30_OTM5up_Q50_TouchK | 29.42%         | 0.17%                     | 0.43%                     | 1.80%                     |
| 510500_ETF_BuyHold             | 30.16%         | 0.00%                     | 0.00%                     | 0.00%                     |

政策跳涨窗口涉及的 option 周期数：12。Touch-K / Q100 均只作为 appendix 或 stress，不作为默认组合层主线。

## 6. 执行与选券

| sleeve_name                    | avg_actual_dte   | avg_entry_delta   | median_entry_delta   | avg_realized_moneyness   |   gap_periods | avg_active_coverage   |
|:-------------------------------|:-----------------|:------------------|:---------------------|:-------------------------|--------------:|:----------------------|
| 510500_DTE30_D40_Q100_Hold     | 29.614           | 0.390             | 0.390                | 1.74%                    |             0 | 100.00%               |
| 510500_DTE30_OTM5up_Q100_Hold  | 29.614           | 0.129             | 0.127                | 6.79%                    |             0 | 100.00%               |
| 510500_DTE30_OTM5up_Q100_TP80  | 29.614           | 0.129             | 0.127                | 6.79%                    |             0 | 62.47%                |
| 510500_DTE30_OTM5up_Q50_Hold   | 29.614           | 0.129             | 0.127                | 6.79%                    |             0 | 50.00%                |
| 510500_DTE30_OTM5up_Q50_TP80   | 29.614           | 0.129             | 0.127                | 6.79%                    |             0 | 31.24%                |
| 510500_DTE30_OTM5up_Q50_TouchK | 29.614           | 0.129             | 0.127                | 6.79%                    |             0 | 44.83%                |
| 510500_ETF_BuyHold             |                  |                   |                      |                          |             0 | 0.00%                 |

## 7. Sleeve 分类

| sleeve_name                    | classification     | reason                                                        | caveat                                                           |
|:-------------------------------|:-------------------|:--------------------------------------------------------------|:-----------------------------------------------------------------|
| 510500_ETF_BuyHold             | Pure ETF Preferred | ETF-only baseline for comparison.                             | No option leg.                                                   |
| 510500_DTE30_D40_Q100_Hold     | Stress Test Only   | Q100 is retained as a full-coverage stress test.              | Do not promote by default even when in-sample metrics look good. |
| 510500_DTE30_OTM5up_Q50_Hold   | Pure ETF Preferred | Covered-call sleeve does not improve the ETF baseline enough. | Keep as pure ETF or diagnostic reference.                        |
| 510500_DTE30_OTM5up_Q100_Hold  | Stress Test Only   | Q100 is retained as a full-coverage stress test.              | Do not promote by default even when in-sample metrics look good. |
| 510500_DTE30_OTM5up_Q50_TP80   | Diagnostic Only    | TP80 close-and-wait is a path-management diagnostic.          | Closed cycles wait to original expiry; no immediate rewrite.     |
| 510500_DTE30_OTM5up_Q100_TP80  | Stress Test Only   | Q100 is retained as a full-coverage stress test.              | Do not promote by default even when in-sample metrics look good. |
| 510500_DTE30_OTM5up_Q50_TouchK | Stress Test Only   | Touch-K is retained as rejected appendix diagnostic.          | Not a default portfolio-layer sleeve.                            |

## 8. 推荐进入组合层的 sleeve

- primary_sleeve_for_portfolio_layer: 510500_ETF_BuyHold
- backup_sleeve:
- rejected_sleeves: 510500_DTE30_D40_Q100_Hold, 510500_DTE30_OTM5up_Q50_Hold, 510500_DTE30_OTM5up_Q100_Hold, 510500_DTE30_OTM5up_Q50_TP80, 510500_DTE30_OTM5up_Q100_TP80, 510500_DTE30_OTM5up_Q50_TouchK
- rationale: ETF-only baseline for comparison.
- caveat: No option leg.
