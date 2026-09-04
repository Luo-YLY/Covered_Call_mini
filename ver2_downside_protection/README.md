# ver2_downside_protection

`ver2_downside_protection` 是一个独立于 ver1 输出的下跌保护研究框架。它不修改 ver1 的核心代码，而是复用现有的期权选择、收益恒等式、交易成本和日期工具，在 ver2 目录中增加 selection log、downside metrics、bucket analysis、图表和 Markdown report。

## 研究范围

当前默认只运行：

- `510300`
- `510050`

默认策略：

- `BuyHold`
- `ITM5_100`
- `ITM2_100`
- `ATM_100`
- `OTM2_100`
- `OTM5_100`

`OTM5_50` 已在配置中预留，默认 `enabled: false`。

## 关键复用关系

- 期权选择：`src.options.selection.select_option`
- 期权权利金：`src.options.selection.option_mid_price`
- 收益恒等式：`src.backtest.accounting.covered_call_period_return`
- 交易成本：`ver2_downside_protection.cost_model.calculate_transaction_cost`
- 月末调仓日：`src.utils.dates.month_end_roll_dates`
- 到期日对齐：`src.utils.dates.nearest_trading_date_on_or_after`

## 字段映射

- ETF 价格使用 `data/raw/etf_prices.csv` 的 `adj_close`。
- 期权链默认使用 `data/raw/options_daily.csv` 的 `trade_date`、`underlying_etf`、`expiry`、`strike`、`close`。
- 若期权表有有效 `bid`/`ask`，权利金使用中间价；当前 raw options 通常没有该字段时，回退使用 `close`。
- 当前默认在缺失市场 bid/ask 时注入 `assumed_bid_ask_spread_pct: 0.05`，即假设期权 bid/ask 相对价差为 5%，卖出时成本为半个 spread。
- 成本输出包含 `raw_bid_ask_spread_pct`、`effective_bid_ask_spread_pct`、`bid_ask_spread_source`、`option_slippage_cost_return`、`bid_ask_spread_cost_return` 等字段，便于看板展示执行摩擦来源。
- `option_payoff_at_expiry` 在 ver2 selection log 中使用覆盖率调整后的每份 ETF 对应金额，即 `coverage_ratio * max(S_expiry - K, 0)`。
- `option_payoff_return_at_expiry` 保留收益率口径，即 `coverage_ratio * max(S_expiry - K, 0) / S_entry`。
- premium-income defensive 模块会进一步输出 `total_premium`、`intrinsic_value_at_entry = max(S_entry - K, 0)`、`extrinsic_value_at_entry = total_premium - intrinsic_value_at_entry`，并给出 total / intrinsic / extrinsic 三组 premium yield。
- `daily_mtm/ver2_daily_mtm.csv` 逐日记录期权标记价格、short call 负债、日频浮动盈亏和 `daily_mtm_nav`。
- `short_call_mtm_loss_return = max(当前期权负债收益率 - 开仓权利金收益率, 0)`，用于后续检查卖出 call 后的日频盯市浮亏。

## Premium-income defensive optimization

新增 `premium_income_defensive` 优化层，用于“用户不关心上涨截断，只关注权利金收入、下跌缓冲、最大回撤控制和收益曲线平滑”的场景。

新增策略：

- `ITM5_100`：目标行权价 `S * 0.95`
- `ITM2_100`：目标行权价 `S * 0.98`
- `ATM_100`：目标行权价最接近 `S`
- `OTM2_100`：目标行权价 `S * 1.02`
- `OTM5_100`：目标行权价 `S * 1.05`，保留为对照组

新增输出：

- `premium_income/ver2_premium_income_summary.csv`
- `premium_income/ver2_premium_decomposition_by_period.csv`
- `premium_income/ver2_defensive_strategy_ranking.csv`

主评分不使用 `upside_cost_mean` 和 `protection_cost_ratio`；两者只保留为辅助诊断。当前主评分为：

```text
primary_score =
    0.35 * annualized_extrinsic_premium_yield_rank
  + 0.25 * downside_cushion_ratio_rank
  + 0.25 * max_drawdown_improvement_rank
  + 0.15 * premium_capture_ratio_rank
```

ITM call 的高权利金会被拆分为 intrinsic value 和 extrinsic value。真正的期权收入重点看 `extrinsic_premium_yield` 与 `premium_capture_ratio`。

## ver2.0 Static Moneyness Ladder Baseline

`ver2.0 | Static Moneyness Ladder Baseline` 是当前静态 moneyness 梯度实验的 baseline checkpoint，不是最终策略方案。

本版本只比较 moneyness 梯度，不引入动态择时、IV/RV 条件、趋势过滤、覆盖率优化、DTE 对比或 collar/protective put。moneyness 定义为：

```text
moneyness = K / S - 1
```

其中 `K` 为 call 行权价，`S` 为建仓日 ETF 价格。负数表示 ITM call，0 表示 ATM，正数表示 OTM call。

核心输出：

```text
outputs/ver2_downside_protection/moneyness_gradient/ver2_0_moneyness_gradient_summary.csv
outputs/ver2_downside_protection/moneyness_gradient/ver2_0_moneyness_gradient_long.csv
outputs/ver2_downside_protection/moneyness_gradient/ver2_0_moneyness_correlation.csv
outputs/ver2_downside_protection/moneyness_gradient/figures/
outputs/ver2_downside_protection/reports/ver2_0_baseline_record.md
outputs/ver2_downside_protection/reports/ver2_0_manifest.json
```

生成方式：

```bash
python scripts/build_ver2_0_moneyness_gradient.py
```

## ver2.1 Non-ITM Covered Call DTE x Regime Diagnostic

`ver2.1` 是非实值备兑的 DTE x 市场状态诊断实验，不是最终动态策略。它基于 ver2.0 的静态 moneyness 梯度结论，将主策略空间收敛到 ATM、OTM 和 call delta <= 0.50 的结构；ITM 不再作为主方向。

核心设定：
- ETF: `510300`, `510050`
- rolling mode: `continuous_30d`
- coverage ratio: `100%`
- DTE: `DTE14_strict_window` window 7-21, `DTE14_nearest_continuous` target 14 with nearest-available fallback, `DTE30` window 20-45, `DTE45` window 35-60, `DTE60` window 50-75
- 主策略: `ATM_100`, `OTM2_100`, `OTM5_100`
- 若 `data/source/delta_enriched_options.csv` 中 delta 可用，则额外运行 `D50_100`, `D40_100`, `D30_100`, `D20_100`

状态变量只使用入场日前可见或入场日可见的信息，包括 trend、MA gap、rolling-high drawdown、RV 和可用时的 IV diagnostics。`policy_jump_like` 只用于事后归因，不作为择时信号；流动性不作为核心 regime variable，只保留为 execution quality diagnostics。

生成方式：
```bash
python scripts/run_ver2_1_dte_regime_diagnostic.py --config configs/ver2_downside_protection.yaml
```

输出：
```text
outputs/ver2_downside_protection/ver2_1_dte_regime/ver2_1_dte_moneyness_summary.csv
outputs/ver2_downside_protection/ver2_1_dte_regime/ver2_1_regime_conditional_performance.csv
outputs/ver2_downside_protection/ver2_1_dte_regime/ver2_1_down_then_rebound_events.csv
outputs/ver2_downside_protection/ver2_1_dte_regime/ver2_1_dte_robustness_ranking.csv
outputs/ver2_downside_protection/ver2_1_dte_regime/ver2_1_daily_mtm_stress_summary.csv
outputs/ver2_downside_protection/ver2_1_effective_coverage_summary.csv
outputs/ver2_downside_protection/ver2_1_full_account_metrics.csv
outputs/ver2_downside_protection/ver2_1_active_overlay_metrics.csv
outputs/ver2_downside_protection/reports/ver2_1_non_itm_dte_regime_diagnostic.md
```

## 运行方式

```bash
python scripts/run_ver2_downside_protection.py --config configs/ver2_downside_protection.yaml
```

可临时覆盖人工 bid/ask spread，用于看板或稳健性检查：

```bash
python scripts/run_ver2_downside_protection.py --config configs/ver2_downside_protection.yaml --assumed-bid-ask-spread-pct 0.10
```

后端也可以直接调用：

```python
config = with_transaction_cost_overrides(config, assumed_bid_ask_spread_pct=0.10)
```

或直接使用看板友好的运行入口：

```python
result = run_ver2_backtest_with_transaction_costs(
    config,
    assumed_bid_ask_spread_pct=0.10,
)
```

## 输出目录

```text
outputs/ver2_downside_protection/
  daily_mtm/
  nav/
  premium_income/
  summary_tables/
  downside_tables/
  selection_logs/
  figures/
    nav/
    drawdown/
    downside_bucket/
    scatter/
  reports/
```

## 防未来函数约束

选券只使用 `rebalance_date` 当天可见的期权链。默认执行口径为 `continuous_30d`：初始建仓日使用首个月末 ETF 交易日，之后在上一张 call 到期结算日立即尝试开下一张 DTE30 call，不等待下一个月末。若某天没有合适 DTE30 call，该段会保留为 ETF 持有收益，并写入 `selection_logs/ver2_skipped_periods.csv`。
