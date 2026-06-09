# 前五ETF备兑策略聚焦报告

本报告选取备兑适用性评分前五 ETF：510300, 510050, 588000, 159915, 510500。

数据流程：本报告以本项目 `data/raw/` 中自带的 Tushare raw/converted data 为起点，18 只 ETF 只参与第一步备兑适用性评分；评分前五 ETF 才进入后续备兑增强策略回测。

评分规则：先计算流动性、期权可得性、期权流动性、权利金充足性、低上涨截断风险和数据质量等软评分；再把“有期权”“有可选月度 roll”“数据完整度达标”“交易天数达标”等硬性条件作为示性函数乘到软评分上。硬性门槛未通过的 ETF 不进入后续策略对比。

只展示当前可执行策略：买入持有、ATM全覆盖月度备兑、OTM5全覆盖月度备兑。Delta30 和 IV 相关内容因缺少 delta/implied_vol 暂不展示。

## 前五ETF适用性评分

```text
 ETF代码   备兑适用性总分  ETF流动性分数    期权可得性分数   期权流动性分数  权利金充足性分数  低上涨截断风险分数     数据质量分数
510300 92.263105 98.058340  99.561902 97.883009 55.630587 100.000000  98.912429
510050 89.008560 80.409120 100.000000 97.907533 56.694871 100.000000  98.912429
588000 85.323541 99.149263  73.389820 96.762899 97.481168  33.333333 100.000000
159915 83.992686 97.501375  82.465287 90.422091 80.801466  66.666667  49.673601
510500 81.269162 84.667946  81.994687 95.477394 59.892483  60.000000  99.673601
```

## 策略比较结论

- 510300：绝对年化收益最高的是 **IV风格规则+提前平仓v1 (IV Style Close v1)**（年化收益 4.95%）。备兑策略中相对 BuyHold 最好的是 **ATM全覆盖月度备兑 (ATM 100%)**，年化超额收益 0.70%，结论为跑赢 BuyHold。
- 510050：绝对年化收益最高的是 **IV风格规则+提前平仓v1 (IV Style Close v1)**（年化收益 1.27%）。备兑策略中相对 BuyHold 最好的是 **ATM全覆盖月度备兑 (ATM 100%)**，年化超额收益 3.24%，结论为跑赢 BuyHold。
- 588000：绝对年化收益最高的是 **IV风格规则v1 (IV Style Rule v1)**（年化收益 6.56%）。备兑策略中相对 BuyHold 最好的是 **IV择时OTM5月度备兑 (IV Timing OTM5)**，年化超额收益 -7.41%，结论为跑输 BuyHold。
- 159915：绝对年化收益最高的是 **买入持有 (BuyHold)**（年化收益 6.04%）。备兑策略中相对 BuyHold 最好的是 **IV择时OTM5月度备兑 (IV Timing OTM5)**，年化超额收益 -2.06%，结论为跑输 BuyHold。
- 510500：绝对年化收益最高的是 **买入持有 (BuyHold)**（年化收益 3.53%）。备兑策略中相对 BuyHold 最好的是 **IV择时ATM月度备兑 (IV Timing ATM)**，年化超额收益 -5.01%，结论为跑输 BuyHold。

## 图表清单

- `figures/top5_nav_curves_executable.png`
- `figures/top5_relative_nav_vs_buyhold.png`
- `figures/top5_annualized_return_heatmap.png`
- `figures/top5_excess_return_heatmap.png`
- `figures/top5_sharpe_heatmap.png`
- `figures/top5_option_contribution_decomposition.png`
- `figures/top5_option_success_and_assignment.png`

全量评分审计表：`tables/universe_suitability_audit_cn.csv`
