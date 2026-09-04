# ver3 Tests

后续新增 ver3 smoke tests 或 regression checks 放这里。

建议优先覆盖：

- Step B fixed-weight NAV 口径：每日收益加权后 cumprod。
- selected-vs-pure 对照字段。
- Universe A/B 固定 sleeve 和权重没有混入 forbidden tokens。
- 588000 不进入主长样本组合。
- `sharpe_daily_mean` 继续沿用标准化指标口径。
