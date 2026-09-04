# ver3.0 Step A | 单 ETF 备兑 Sleeve 画像整理

## 1. 实验定位

本步骤先把每个 ETF 标的做清楚；不做组合、不做动态权重、不强制账户级统一周期。每个 ETF sleeve 独立生成净值曲线，后续 Step B / Step C 再用 return panel 加权。

共同样本：2022-09-30 至 2026-05-27。

## 2. 方法

日频口径使用 `R_CC = R_ETF + R_OptionLeg`。期权腿净 P&L 使用 `Premium - Payoff - Cost`；source paths 由 `continuous_30d` 引擎重建，上一周期 `period_end_date` 即下一周期 `rebalance_date`。TP80 / Touch-K 不进入当前 Step A 主线。

绩效字段沿用 ver2_metric_standardization 的命名：`annualized_return_cagr` 是主年化收益，`sharpe_daily_mean` 是主 Sharpe，`max_drawdown` 为正数口径。

## 3. 510300 Sleeve Card Summary

- primary: 510300_DTE30_D40_Q70_Hold
- classification: Positive Carry Overlay
- rationale: Net option leg is positive while Sharpe and drawdown are at least as good as BuyHold.
- caveat: Still sample-limited and not an arbitrage claim.

## 4. 510500 Sleeve Card Summary

- primary: 510500_DTE30_OTM5up_Q50_Hold
- classification: Defensive Overlay
- rationale: Net option leg is not positive, but drawdown improves enough with similar Sharpe.
- caveat: Use as risk-control sleeve, not income enhancement.

## 5. 159915 Sleeve Card Summary

- primary: 159915_DTE30_OTM5up_Q50_Hold
- classification: Defensive Overlay
- rationale: Net option leg is not positive, but drawdown improves enough with similar Sharpe.
- caveat: Use as risk-control sleeve, not income enhancement.

## 6. Cross-ETF Sleeve Classification

|   etf_code | sleeve_name                   | classification         | recommendation_status       | annualized_return_cagr   |   sharpe_daily_mean | max_drawdown   | option_leg_annualized_pnl_contribution   |
|-----------:|:------------------------------|:-----------------------|:----------------------------|:-------------------------|--------------------:|:---------------|:-----------------------------------------|
|     159915 | 159915_ETF_BuyHold            | Pure ETF Preferred     | backup_for_portfolio_layer  | 18.82%                   |               0.7   | 40.88%         | 0.00%                                    |
|     159915 | 159915_DTE30_D40_Q100_Hold    | Stress Test Only       | diagnostic_only             | 7.76%                    |               0.512 | 28.76%         | -13.08%                                  |
|     159915 | 159915_DTE30_OTM5up_Q50_Hold  | Defensive Overlay      | primary_for_portfolio_layer | 14.58%                   |               0.677 | 37.68%         | -5.53%                                   |
|     159915 | 159915_DTE30_OTM5up_Q100_Hold | Stress Test Only       | diagnostic_only             | 9.49%                    |               0.554 | 34.70%         | -11.06%                                  |
|     510300 | 510300_ETF_BuyHold            | Pure ETF Preferred     | rejected                    | 7.21%                    |               0.484 | 24.19%         | 0.00%                                    |
|     510300 | 510300_DTE30_ATM_Q100_Hold    | Stress Test Only       | diagnostic_only             | 4.69%                    |               0.528 | 12.87%         | -3.44%                                   |
|     510300 | 510300_DTE30_D40_Q50_Hold     | Positive Carry Overlay | backup_for_portfolio_layer  | 8.05%                    |               0.638 | 18.46%         | 0.18%                                    |
|     510300 | 510300_DTE30_D40_Q70_Hold     | Positive Carry Overlay | primary_for_portfolio_layer | 8.32%                    |               0.712 | 16.45%         | 0.25%                                    |
|     510300 | 510300_DTE30_D40_Q100_Hold    | Stress Test Only       | diagnostic_only             | 8.62%                    |               0.821 | 13.91%         | 0.36%                                    |
|     510500 | 510500_ETF_BuyHold            | Pure ETF Preferred     | backup_for_portfolio_layer  | 12.48%                   |               0.646 | 30.16%         | 0.00%                                    |
|     510500 | 510500_DTE30_D40_Q100_Hold    | Stress Test Only       | diagnostic_only             | 2.82%                    |               0.267 | 23.48%         | -10.33%                                  |
|     510500 | 510500_DTE30_OTM5up_Q50_Hold  | Defensive Overlay      | primary_for_portfolio_layer | 10.33%                   |               0.612 | 28.41%         | -2.50%                                   |
|     510500 | 510500_DTE30_OTM5up_Q100_Hold | Stress Test Only       | diagnostic_only             | 7.96%                    |               0.533 | 26.86%         | -5.00%                                   |

## 7. 推荐进入组合层的 Sleeve Set

conservative:
- 510300: 510300_DTE30_D40_Q50_Hold
- 510500: 510500_ETF_BuyHold
- 159915: 159915_ETF_BuyHold

balanced:
- 510300: 510300_DTE30_D40_Q70_Hold
- 510500: 510500_DTE30_OTM5up_Q50_Hold
- 159915: 159915_DTE30_OTM5up_Q50_Hold

defensive:
- 510300: 510300_DTE30_D40_Q70_Hold
- 510500: 510500_DTE30_OTM5up_Q50_Hold
- 159915: 159915_DTE30_OTM5up_Q50_Hold

这些只是 sleeve set，不在 Step A 中计算组合绩效。

## 8. 为 ver3.0 Step B / C 准备

Step B 可以直接读取 `outputs/ver3_0_stepA_single_etf_sleeves/panel/ver3_0_stepA_sleeve_return_panel_wide.csv` 做固定权重组合。Step C 可以基于这些 sleeve 或 ETF daily return 做波动率 / 协方差驱动的动态权重。Step A 不涉及均值方差优化。

## 9. 局限性

- 样本期有限，且覆盖 2024 年政策跳涨等强事件窗口；
- 高弹性 ETF 的备兑可能负 carry；
- TP80 / Touch-K 已从当前主线 Step A 排除；
- Q100 是 stress test；
- 组合层结果不能反推单 ETF 有效性；
- 本报告不使用确定性收益或 guaranteed-profit 表述。

## 10. 主候选和诊断候选

主候选：

|   etf_code | sleeve_name                  | classification         | reason                                                                                | caveat                                              |
|-----------:|:-----------------------------|:-----------------------|:--------------------------------------------------------------------------------------|:----------------------------------------------------|
|     159915 | 159915_DTE30_OTM5up_Q50_Hold | Defensive Overlay      | Net option leg is not positive, but drawdown improves enough with similar Sharpe.     | Use as risk-control sleeve, not income enhancement. |
|     510300 | 510300_DTE30_D40_Q70_Hold    | Positive Carry Overlay | Net option leg is positive while Sharpe and drawdown are at least as good as BuyHold. | Still sample-limited and not an arbitrage claim.    |
|     510500 | 510500_DTE30_OTM5up_Q50_Hold | Defensive Overlay      | Net option leg is not positive, but drawdown improves enough with similar Sharpe.     | Use as risk-control sleeve, not income enhancement. |

诊断 / 压力测试：

|   etf_code | sleeve_name                   | classification     | reason                                           |
|-----------:|:------------------------------|:-------------------|:-------------------------------------------------|
|     159915 | 159915_DTE30_D40_Q100_Hold    | Stress Test Only   | Q100 is retained as a full-coverage stress test. |
|     159915 | 159915_DTE30_OTM5up_Q100_Hold | Stress Test Only   | Q100 is retained as a full-coverage stress test. |
|     510300 | 510300_ETF_BuyHold            | Pure ETF Preferred | ETF-only baseline for comparison.                |
|     510300 | 510300_DTE30_ATM_Q100_Hold    | Stress Test Only   | Q100 is retained as a full-coverage stress test. |
|     510300 | 510300_DTE30_D40_Q100_Hold    | Stress Test Only   | Q100 is retained as a full-coverage stress test. |
|     510500 | 510500_DTE30_D40_Q100_Hold    | Stress Test Only   | Q100 is retained as a full-coverage stress test. |
|     510500 | 510500_DTE30_OTM5up_Q100_Hold | Stress Test Only   | Q100 is retained as a full-coverage stress test. |

## 11. Sanity Checks

| check_name                          | passed   | note                                                                             |
|:------------------------------------|:---------|:---------------------------------------------------------------------------------|
| uses_standardized_metrics           | True     | summary uses ver2 metric field names and summarize_daily_nav                     |
| no_portfolio_weighting_in_stepA     | True     | single ETF rows only                                                             |
| no_mean_variance_in_stepA           | True     | no covariance or optimizer is called                                             |
| each_etf_sleeve_independent         | True     | one independent sleeve path per ETF/spec                                         |
| no_forced_common_expiry_across_etfs | True     | source ETF paths keep their own selected option cycles                           |
| option_leg_net_pnl                  | True     | period option leg equals premium minus close/payoff liability and costs          |
| premium_not_immediate_profit        | True     | entry-day option P&L is cost/MTM based, not premium income                       |
| daily_panel_unique_sleeve_dates     | True     | daily panel has one consolidated return row per sleeve/date after same-day rolls |
| buyhold_option_fields_zero          | True     | BuyHold option fields are zero                                                   |
| deprecated_tp80_touch_absent        | True     | TP80 and Touch-K are excluded from the current Step A mainline                   |
| immediate_reopen_after_period_end   | True     | Next option cycle rebalances on the previous period_end_date                     |
| q100_stress_test_only               | True     | Q100 rows are stress tests                                                       |
| no_new_dte_added                    | True     | DTE30 only                                                                       |
| no_new_delta_grid_added             | True     | no added OTM/DTE grid                                                            |
| no_arbitrage_language               | True     | reports avoid arbitrage language                                                 |
| sleeve_return_panel_created         | True     | long and wide panels are populated                                               |
| classification_table_created        | True     | classification table is populated                                                |
| sleeve_cards_created                | True     | three ETF sleeve cards exist after report writing                                |
