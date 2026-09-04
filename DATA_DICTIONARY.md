# Covered Call Mini Demo 数据字典

## data/raw/

`data/raw/` 保存本 mini demo 自带的 Tushare 原始数据和转换后的研究输入表。项目运行时从这里读取数据，不依赖外部目录。

主要文件：

```text
etf_prices.csv                  转换后的 ETF 日行情研究输入表
options.csv                     转换后的 ETF 期权行情研究输入表
etf_metadata.csv                ETF 元数据和风格分类
tushare_fund_daily_raw.csv      Tushare fund_daily 原始拉取结果
tushare_opt_basic_raw.csv       Tushare opt_basic 原始拉取结果
tushare_opt_daily_raw.csv       Tushare opt_daily 原始拉取结果
_etf_price_collection_status.csv ETF行情采集状态
_option_collection_status.csv    期权采集状态
```

## data/source/iv_style_rule_close_v1_periods.csv

`S8_IVStyleRule_Close_v1` 的逐期明细。该表以 `S7_IVStyleRule_v1` 的风格规则为基础，只新增最终组合层面的提前平仓管理。

新增字段：

```text
close_rule                       提前平仓规则名称，当前为 CloseRule_v1
close_triggered                  是否触发提前平仓，1=触发，0=未触发
close_date                       买回 short call 的日期
close_buyback_price              平仓买回同一张期权合约的价格
close_buyback_yield              平仓买回价格 / 期初ETF价格 * 覆盖率
close_price_source               买回价格来源，mid 或 close
close_iv_percentile              平仓触发日的 IV 分位数
close_iv_threshold               该 ETF 风格对应的平仓 IV 阈值
close_days_held                  从 roll 日到平仓日的持有天数
```

S8 的收益恒等式仍保持：

```text
R_cc = R_etf + premium_yield - upside_cost - cost
```

当触发提前平仓时，`upside_cost` 在 S8 中表示买回 short call 的支出，即 `close_buyback_yield`，不是到期被行权导致的上涨截断。

## data/source/iv_style_rule_close_v1_summary.csv

`S8_IVStyleRule_Close_v1` 的 ETF 级别绩效汇总。除常规绩效字段外，新增：

```text
close_trigger_rate               提前平仓触发比例
avg_days_to_close                平均触发平仓所需天数
close_buyback_cost               累计买回成本贡献
```

`etf_prices.csv` 主要字段：

```text
date                             日期
etf_code                         ETF代码
open/high/low/close              OHLC价格
adj_close                        复权/研究用收盘价
volume                           成交量
amount                           成交额
```

`options.csv` 主要字段：

```text
trade_date                       交易日
option_code                      期权合约代码
underlying_etf                   标的ETF代码
option_type                      C/P，当前回测只保留认购期权C
expiry                           到期日
strike                           行权价
close                            收盘价
volume                           成交量
open_interest                    持仓量
amount                           成交额
```

## data/source/data_quality_report.csv

由 `data/raw` 重新计算得到的数据质量表，逐数据集、逐字段统计缺失情况。

主要字段：

```text
dataset                          数据集名称
column                           字段名
rows                             行数
missing_count                    缺失值数量
missing_ratio                    缺失比例
synthetic_demo                   是否合成演示数据
```

## data/source/etf_universe_screen.csv

18 只 ETF 的评分前特征宽表。它保留 ETF 流动性、期权可得性、期权流动性、权利金、波动、数据完整度等中间指标。

## data/source/etf_suitability_scores.csv

用于筛选 ETF 的备兑适用性评分源表。18 只 ETF 都参与这一步，后续只选最终评分前五进入备兑增强策略回测。

主要字段：

```text
etf_code                         ETF代码
soft_suitability_score           硬门槛前的软评分
hard_gate_has_options            硬门槛：是否有期权
hard_gate_eligible_rolls         硬门槛：是否有可选月度roll
hard_gate_data_completeness      硬门槛：数据完整度是否达标
hard_gate_trading_days           硬门槛：交易天数是否达标
hard_gate_all                    硬门槛是否全部通过
suitability_score                最终评分，等于软评分乘以硬门槛示性函数
etf_liquidity_score              ETF流动性分数
option_availability_score        期权可得性分数
option_liquidity_score           期权流动性分数
premium_adequacy_score           权利金充足性分数
data_quality_score               数据质量分数
upside_truncation_risk_score     低上涨截断风险分数
synthetic_demo                   是否合成演示数据
```

## data/source/selected_top5_etfs.csv

根据 `etf_suitability_scores.csv` 的最终评分选出的前五 ETF。

## data/source/fixed_cc_strategy_summary.csv

ETF × 策略维度的回测绩效汇总源表。

主要字段：

```text
etf_code                         ETF代码
strategy                         策略名称
cumulative_return                累计收益
annualized_return                年化收益
annualized_volatility            年化波动率
sharpe_ratio                     夏普比率
sortino_ratio                    Sortino比率
max_drawdown                     最大回撤
calmar_ratio                     Calmar比率
excess_return_total              相对BuyHold累计超额收益
excess_return_annualized         相对BuyHold年化超额收益；口径为策略年化收益 - 同区间BuyHold年化收益
information_ratio                信息比率
average_premium_yield            平均权利金收益率
total_premium_contribution       累计权利金贡献
total_upside_truncation_cost     累计上涨截断成本
total_transaction_cost_drag      累计交易成本拖累
net_option_contribution          净期权贡献
assignment_frequency             被行权频率
average_coverage_ratio           平均覆盖比例
average_selected_delta           平均选中Delta
average_moneyness                平均虚实值程度
option_sale_success_rate         期权卖出成功率
```

## data/source/pnl_decomposition_by_roll.csv

按 ETF、策略、滚动周期拆解的收益明细源表。

核心恒等式：

```text
R_cc = R_etf + premium_yield - upside_cost - cost
```

主要字段：

```text
etf_code                         ETF代码
strategy                         策略名称
roll_date                        建仓日
end_date                         持有期结束日
S0                               期初ETF价格
ST                               期末ETF价格
K                                行权价
C0                               权利金
coverage_ratio                   覆盖比例
option_selected_flag             是否卖出期权
no_option_available_flag         是否无可用期权
selection_reason                 选券状态/原因
price_source                     期权价格来源
selected_delta                   选中Delta
selected_iv                      选中IV
days_to_expiry                   到期天数
moneyness                        虚实值程度
R_etf                            ETF收益
premium_yield                    权利金收益率
upside_cost                      上涨截断成本
cost                             交易成本
R_cc                             备兑策略收益
excess_return                    相对BuyHold超额收益
assignment_flag                  是否被行权
premium_contribution             权利金贡献
upside_cost_contribution         上涨截断成本贡献
transaction_cost_contribution    交易成本贡献
net_option_contribution          净期权贡献
synthetic_demo                   是否合成演示数据
```

## data/source/nav_by_strategy.csv

策略净值曲线源表。

主要字段：

```text
date                             日期
etf_code                         ETF代码
strategy                         策略名称
nav                              策略净值
synthetic_demo                   是否合成演示数据
```
# IV择时新增数据

## data/source/iv_timing_signals.csv

通用 ETF-specific 30D ATM IV proxy 和择时信号表。该表对纳入后续备兑策略回测的 ETF 生成每日或可用交易日的 IV 特征。

主要字段：

```text
trade_date                       期权链交易日
etf_code                         ETF代码
spot                             ETF复权收盘价
iv_30d_atm                       30D constant-maturity ATM IV proxy
call_iv_30d_atm                  ATM call IV
put_iv_30d_atm                   ATM put IV
atm_strike                       用于ATM proxy的行权价
near_expiry / next_expiry        用于期限插值的近端和远端到期日
near_dte / next_dte              近端和远端剩余期限
iv_quality_flag                  IV质量标签：interpolated / single_expiry / no_valid_iv等
iv_percentile_252                当前IV在ETF自身历史窗口中的分位数
iv_zscore_252                    当前IV相对ETF自身历史窗口的z-score
rv_20d / rv_30d                  20日/30日实现波动率
iv_rv_spread                     30D ATM IV - 20D RV
iv_rv_ratio                      30D ATM IV / 20D RV
iv_regime                        high_iv / normal_iv / low_iv / invalid
signal_valid                     IV择时信号是否可用
```
## data/raw/options_daily.csv

可选的日频ETF期权链标准化输入表。若该文件存在，`scripts/build_from_raw_data.py` 会优先使用它计算 `data/source/iv_timing_signals.csv`；若不存在，则回退使用 `data/raw/options.csv`。

生成方式：

```bash
python scripts/collect_daily_options.py --start-date 2021-01-01 --end-date 2026-06-03 --resume
```

字段结构与 `options.csv` 一致：

```text
trade_date                       期权行情日期
option_code                      期权合约代码
underlying_etf                   标的ETF代码
option_type                      C/P
expiry                           到期日
strike                           行权价
close                            收盘价
volume                           成交量
open_interest                    持仓量
amount                           成交额
```
