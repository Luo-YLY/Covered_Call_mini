# Delta标准化层说明

第一阶段新增 `src/features/delta_surface.py`，用于把日频期权链统一补齐 Black-Scholes 口径的 `model_iv` 和 `model_delta`。

## 输入

```text
data/raw/options_daily.csv 或 data/raw/options.csv
data/raw/etf_prices.csv
```

构建流程在 `scripts/build_from_raw_data.py` 中执行，当前优先使用 `options_daily.csv` 生成全量标准化期权链。

## 输出

```text
data/source/delta_enriched_options.csv
```

核心新增字段：

```text
spot                         期权交易日对应 ETF adj_close
days_to_expiry               剩余自然日
years_to_expiry              days_to_expiry / 365
model_price_input            用于反解 IV 的期权价格，优先 bid/ask mid，否则 close
model_price_source           mid 或 close
model_iv                     由市场价格反解得到的 BS IV
model_delta                  由 model_iv 计算得到的 BS delta，call 为正，put 为负
model_abs_delta              abs(model_delta)
raw_delta                    原始数据中的 delta，如果存在
raw_implied_vol              原始数据中的 implied_vol，如果存在
iv_source_for_delta          model_iv 或 raw_implied_vol_fallback
delta_quality_flag           标准化质量标签
delta_valid                  model_delta 是否有效
moneyness                    strike / spot - 1
log_moneyness                log(strike / spot)
delta_standardization_rate   本次计算使用的无风险利率
```

## 质量标签

```text
valid_model_iv               成功由价格反解 IV 并计算 delta
raw_iv_fallback              价格反解失败，但使用原始 implied_vol 计算 delta
iv_failed                    IV 反解失败，且无可用原始 IV
invalid_dte                  剩余期限无效
invalid_price                价格无效
invalid_spot                 ETF 价格无效
invalid_strike               行权价无效
invalid_option_type          期权类型不是 C/P
delta_failed                 IV 有效但 delta 计算失败
```

当前构建结果：

```text
rows: 628895
delta_valid_rate: 86.56%
valid_model_iv: 544342
iv_failed: 75770
invalid_dte: 8749
invalid_price: 34
```
