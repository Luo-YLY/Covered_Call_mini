# ETF Sleeve Card | 510300

## 1. 标的定位

核心宽基 / 相对低波动 / 主备兑候选

## 2. 候选 sleeve 列表

| sleeve_name                  | classification         | recommendation_status       |
|:-----------------------------|:-----------------------|:----------------------------|
| 510300_DTE30_ATM_Q100_Hold   | Stress Test Only       | diagnostic_only             |
| 510300_DTE30_D40_Q100_Hold   | Stress Test Only       | diagnostic_only             |
| 510300_DTE30_D40_Q100_TP80   | Stress Test Only       | diagnostic_only             |
| 510300_DTE30_D40_Q100_TouchK | Stress Test Only       | diagnostic_only             |
| 510300_DTE30_D40_Q50_Hold    | Positive Carry Overlay | backup_for_portfolio_layer  |
| 510300_DTE30_D40_Q70_Hold    | Positive Carry Overlay | primary_for_portfolio_layer |
| 510300_DTE30_D40_Q70_TP80    | Diagnostic Only        | diagnostic_only             |
| 510300_ETF_BuyHold           | Pure ETF Preferred     | rejected                    |

## 3. 核心绩效对比

| sleeve_name                  | annualized_return_cagr   |   sharpe_daily_mean | max_drawdown   | option_leg_annualized_pnl_contribution   | p99_short_call_mtm_loss   |
|:-----------------------------|:-------------------------|--------------------:|:---------------|:-----------------------------------------|:--------------------------|
| 510300_DTE30_ATM_Q100_Hold   | 7.38%                    |               0.76  | 12.83%         | 0.08%                                    | 7.35%                     |
| 510300_DTE30_D40_Q100_Hold   | 8.18%                    |               0.737 | 14.84%         | 0.98%                                    | 6.06%                     |
| 510300_DTE30_D40_Q100_TP80   | 8.20%                    |               0.72  | 15.38%         | 1.05%                                    | 6.06%                     |
| 510300_DTE30_D40_Q100_TouchK | 4.31%                    |               0.343 | 24.39%         | -2.05%                                   | 0.39%                     |
| 510300_DTE30_D40_Q50_Hold    | 7.33%                    |               0.578 | 18.93%         | 0.49%                                    | 3.03%                     |
| 510300_DTE30_D40_Q70_Hold    | 7.70%                    |               0.645 | 17.19%         | 0.69%                                    | 4.24%                     |
| 510300_DTE30_D40_Q70_TP80    | 7.71%                    |               0.636 | 17.32%         | 0.73%                                    | 4.24%                     |
| 510300_ETF_BuyHold           | 6.20%                    |               0.431 | 24.19%         | 0.00%                                    | 0.00%                     |

## 4. Option-leg 质量

| sleeve_name                  | premium_capture_ratio_agg   | payoff_burden_agg   | positive_option_leg_period_rate   | assignment_rate   | early_close_rate   |
|:-----------------------------|:----------------------------|:--------------------|:----------------------------------|:------------------|:-------------------|
| 510300_DTE30_ATM_Q100_Hold   | 0.34%                       | 97.11%              | 65.91%                            | 45.45%            | 0.00%              |
| 510300_DTE30_D40_Q100_Hold   | 6.49%                       | 90.96%              | 72.73%                            | 38.64%            | 0.00%              |
| 510300_DTE30_D40_Q100_TP80   | 6.93%                       | 90.33%              | 77.27%                            | 31.82%            | 68.18%             |
| 510300_DTE30_D40_Q100_TouchK | -13.52%                     | 108.21%             | 38.64%                            | 0.00%             | 68.18%             |
| 510300_DTE30_D40_Q50_Hold    | 6.49%                       | 90.96%              | 72.73%                            | 38.64%            | 0.00%              |
| 510300_DTE30_D40_Q70_Hold    | 6.49%                       | 90.96%              | 72.73%                            | 38.64%            | 0.00%              |
| 510300_DTE30_D40_Q70_TP80    | 6.93%                       | 90.33%              | 77.27%                            | 31.82%            | 68.18%             |
| 510300_ETF_BuyHold           |                             |                     |                                   |                   | 0.00%              |

## 5. 风险路径

| sleeve_name                  | max_drawdown   | p95_short_call_mtm_loss   | p99_short_call_mtm_loss   | max_short_call_mtm_loss   |
|:-----------------------------|:---------------|:--------------------------|:--------------------------|:--------------------------|
| 510300_DTE30_ATM_Q100_Hold   | 12.83%         | 3.05%                     | 7.35%                     | 18.18%                    |
| 510300_DTE30_D40_Q100_Hold   | 14.84%         | 2.03%                     | 6.06%                     | 16.81%                    |
| 510300_DTE30_D40_Q100_TP80   | 15.38%         | 2.03%                     | 6.06%                     | 16.81%                    |
| 510300_DTE30_D40_Q100_TouchK | 24.39%         | 0.00%                     | 0.39%                     | 0.64%                     |
| 510300_DTE30_D40_Q50_Hold    | 18.93%         | 1.02%                     | 3.03%                     | 8.41%                     |
| 510300_DTE30_D40_Q70_Hold    | 17.19%         | 1.42%                     | 4.24%                     | 11.77%                    |
| 510300_DTE30_D40_Q70_TP80    | 17.32%         | 1.42%                     | 4.24%                     | 11.77%                    |
| 510300_ETF_BuyHold           | 24.19%         | 0.00%                     | 0.00%                     | 0.00%                     |

政策跳涨窗口涉及的 option 周期数：14。Touch-K / Q100 均只作为 appendix 或 stress，不作为默认组合层主线。

## 6. 执行与选券

| sleeve_name                  | avg_actual_dte   | avg_entry_delta   | median_entry_delta   | avg_realized_moneyness   |   gap_periods | avg_active_coverage   |
|:-----------------------------|:-----------------|:------------------|:---------------------|:-------------------------|--------------:|:----------------------|
| 510300_DTE30_ATM_Q100_Hold   | 29.614           | 0.513             | 0.510                | 0.08%                    |             0 | 100.00%               |
| 510300_DTE30_D40_Q100_Hold   | 29.614           | 0.397             | 0.397                | 1.46%                    |             0 | 100.00%               |
| 510300_DTE30_D40_Q100_TP80   | 29.614           | 0.397             | 0.397                | 1.46%                    |             0 | 75.62%                |
| 510300_DTE30_D40_Q100_TouchK | 29.614           | 0.397             | 0.397                | 1.46%                    |             0 | 48.43%                |
| 510300_DTE30_D40_Q50_Hold    | 29.614           | 0.397             | 0.397                | 1.46%                    |             0 | 50.00%                |
| 510300_DTE30_D40_Q70_Hold    | 29.614           | 0.397             | 0.397                | 1.46%                    |             0 | 70.00%                |
| 510300_DTE30_D40_Q70_TP80    | 29.614           | 0.397             | 0.397                | 1.46%                    |             0 | 52.93%                |
| 510300_ETF_BuyHold           |                  |                   |                      |                          |             0 | 0.00%                 |

## 7. Sleeve 分类

| sleeve_name                  | classification         | reason                                                                                | caveat                                                           |
|:-----------------------------|:-----------------------|:--------------------------------------------------------------------------------------|:-----------------------------------------------------------------|
| 510300_ETF_BuyHold           | Pure ETF Preferred     | ETF-only baseline for comparison.                                                     | No option leg.                                                   |
| 510300_DTE30_ATM_Q100_Hold   | Stress Test Only       | Q100 is retained as a full-coverage stress test.                                      | Do not promote by default even when in-sample metrics look good. |
| 510300_DTE30_D40_Q50_Hold    | Positive Carry Overlay | Net option leg is positive while Sharpe and drawdown are at least as good as BuyHold. | Still sample-limited and not an arbitrage claim.                 |
| 510300_DTE30_D40_Q70_Hold    | Positive Carry Overlay | Net option leg is positive while Sharpe and drawdown are at least as good as BuyHold. | Still sample-limited and not an arbitrage claim.                 |
| 510300_DTE30_D40_Q100_Hold   | Stress Test Only       | Q100 is retained as a full-coverage stress test.                                      | Do not promote by default even when in-sample metrics look good. |
| 510300_DTE30_D40_Q70_TP80    | Diagnostic Only        | TP80 close-and-wait is a path-management diagnostic.                                  | Closed cycles wait to original expiry; no immediate rewrite.     |
| 510300_DTE30_D40_Q100_TP80   | Stress Test Only       | Q100 is retained as a full-coverage stress test.                                      | Do not promote by default even when in-sample metrics look good. |
| 510300_DTE30_D40_Q100_TouchK | Stress Test Only       | Touch-K is retained as rejected appendix diagnostic.                                  | Not a default portfolio-layer sleeve.                            |

## 8. 推荐进入组合层的 sleeve

- primary_sleeve_for_portfolio_layer: 510300_DTE30_D40_Q70_Hold
- backup_sleeve: 510300_DTE30_D40_Q50_Hold
- rejected_sleeves: 510300_ETF_BuyHold, 510300_DTE30_ATM_Q100_Hold, 510300_DTE30_D40_Q100_Hold, 510300_DTE30_D40_Q70_TP80, 510300_DTE30_D40_Q100_TP80, 510300_DTE30_D40_Q100_TouchK
- rationale: Net option leg is positive while Sharpe and drawdown are at least as good as BuyHold.
- caveat: Still sample-limited and not an arbitrage claim.
