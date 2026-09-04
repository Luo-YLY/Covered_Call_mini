# ETF Sleeve Card | 510300

## 1. 标的定位

核心宽基 / 相对低波动 / 主备兑候选

## 2. 候选 sleeve 列表

| sleeve_name                | classification         | recommendation_status       |
|:---------------------------|:-----------------------|:----------------------------|
| 510300_DTE30_ATM_Q100_Hold | Stress Test Only       | diagnostic_only             |
| 510300_DTE30_D40_Q100_Hold | Stress Test Only       | diagnostic_only             |
| 510300_DTE30_D40_Q50_Hold  | Positive Carry Overlay | backup_for_portfolio_layer  |
| 510300_DTE30_D40_Q70_Hold  | Positive Carry Overlay | primary_for_portfolio_layer |
| 510300_ETF_BuyHold         | Pure ETF Preferred     | rejected                    |

## 3. 核心绩效对比

| sleeve_name                | annualized_return_cagr   |   sharpe_daily_mean | max_drawdown   | option_leg_annualized_pnl_contribution   | p99_short_call_mtm_loss   |
|:---------------------------|:-------------------------|--------------------:|:---------------|:-----------------------------------------|:--------------------------|
| 510300_DTE30_ATM_Q100_Hold | 4.69%                    |               0.528 | 12.87%         | -3.44%                                   | 11.35%                    |
| 510300_DTE30_D40_Q100_Hold | 8.62%                    |               0.821 | 13.91%         | 0.36%                                    | 11.35%                    |
| 510300_DTE30_D40_Q50_Hold  | 8.05%                    |               0.638 | 18.46%         | 0.18%                                    | 5.68%                     |
| 510300_DTE30_D40_Q70_Hold  | 8.32%                    |               0.712 | 16.45%         | 0.25%                                    | 7.95%                     |
| 510300_ETF_BuyHold         | 7.21%                    |               0.484 | 24.19%         | 0.00%                                    | 0.00%                     |

## 4. Option-leg 质量

| sleeve_name                | premium_capture_ratio_agg   | payoff_burden_agg   | positive_option_leg_period_rate   | assignment_rate   | early_close_rate   |
|:---------------------------|:----------------------------|:--------------------|:----------------------------------|:------------------|:-------------------|
| 510300_DTE30_ATM_Q100_Hold | -14.79%                     | 112.24%             | 63.64%                            | 52.27%            | 0.00%              |
| 510300_DTE30_D40_Q100_Hold | 3.82%                       | 93.63%              | 75.00%                            | 40.91%            | 0.00%              |
| 510300_DTE30_D40_Q50_Hold  | 3.82%                       | 93.63%              | 75.00%                            | 40.91%            | 0.00%              |
| 510300_DTE30_D40_Q70_Hold  | 3.82%                       | 93.63%              | 75.00%                            | 40.91%            | 0.00%              |
| 510300_ETF_BuyHold         |                             |                     |                                   |                   | 0.00%              |

## 5. 风险路径

| sleeve_name                | max_drawdown   | p95_short_call_mtm_loss   | p99_short_call_mtm_loss   | max_short_call_mtm_loss   |
|:---------------------------|:---------------|:--------------------------|:--------------------------|:--------------------------|
| 510300_DTE30_ATM_Q100_Hold | 12.87%         | 2.69%                     | 11.35%                    | 23.83%                    |
| 510300_DTE30_D40_Q100_Hold | 13.91%         | 1.71%                     | 11.35%                    | 23.83%                    |
| 510300_DTE30_D40_Q50_Hold  | 18.46%         | 0.86%                     | 5.68%                     | 11.92%                    |
| 510300_DTE30_D40_Q70_Hold  | 16.45%         | 1.20%                     | 7.95%                     | 16.68%                    |
| 510300_ETF_BuyHold         | 24.19%         | 0.00%                     | 0.00%                     | 0.00%                     |

政策跳涨窗口涉及的 option 周期数：0。TP80 / Touch-K 已从当前 Step A 主线排除；Q100 仅作为 stress diagnostic，不作为默认组合层主线。

## 6. 执行与选券

| sleeve_name                | avg_actual_dte   | avg_entry_delta   | median_entry_delta   | avg_realized_moneyness   |   gap_periods | avg_active_coverage   |
|:---------------------------|:-----------------|:------------------|:---------------------|:-------------------------|--------------:|:----------------------|
| 510300_DTE30_ATM_Q100_Hold | 30.341           | 0.499             | 0.497                | 0.24%                    |             0 | 100.00%               |
| 510300_DTE30_D40_Q100_Hold | 30.341           | 0.405             | 0.415                | 1.40%                    |             0 | 100.00%               |
| 510300_DTE30_D40_Q50_Hold  | 30.341           | 0.405             | 0.415                | 1.40%                    |             0 | 50.00%                |
| 510300_DTE30_D40_Q70_Hold  | 30.341           | 0.405             | 0.415                | 1.40%                    |             0 | 70.00%                |
| 510300_ETF_BuyHold         |                  |                   |                      |                          |             0 | 0.00%                 |

## 7. Sleeve 分类

| sleeve_name                | classification         | reason                                                                                | caveat                                                           |
|:---------------------------|:-----------------------|:--------------------------------------------------------------------------------------|:-----------------------------------------------------------------|
| 510300_ETF_BuyHold         | Pure ETF Preferred     | ETF-only baseline for comparison.                                                     | No option leg.                                                   |
| 510300_DTE30_ATM_Q100_Hold | Stress Test Only       | Q100 is retained as a full-coverage stress test.                                      | Do not promote by default even when in-sample metrics look good. |
| 510300_DTE30_D40_Q50_Hold  | Positive Carry Overlay | Net option leg is positive while Sharpe and drawdown are at least as good as BuyHold. | Still sample-limited and not an arbitrage claim.                 |
| 510300_DTE30_D40_Q70_Hold  | Positive Carry Overlay | Net option leg is positive while Sharpe and drawdown are at least as good as BuyHold. | Still sample-limited and not an arbitrage claim.                 |
| 510300_DTE30_D40_Q100_Hold | Stress Test Only       | Q100 is retained as a full-coverage stress test.                                      | Do not promote by default even when in-sample metrics look good. |

## 8. 推荐进入组合层的 sleeve

- primary_sleeve_for_portfolio_layer: 510300_DTE30_D40_Q70_Hold
- backup_sleeve: 510300_DTE30_D40_Q50_Hold
- rejected_sleeves: 510300_ETF_BuyHold, 510300_DTE30_ATM_Q100_Hold, 510300_DTE30_D40_Q100_Hold
- rationale: Net option leg is positive while Sharpe and drawdown are at least as good as BuyHold.
- caveat: Still sample-limited and not an arbitrage claim.
