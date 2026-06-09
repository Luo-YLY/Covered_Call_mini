# Covered Call Mini Demo

这是一个 ETF 备兑策略研究与回测 mini project。项目当前支持 ETF 适用性评分、固定月度备兑策略、基于日频期权链计算的 30D ATM IV proxy，以及 IV 分位数择时备兑策略。

当前研究主线：

```text
ETF日频行情 + ETF期权链
-> ETF备兑适用性评分
-> 选取适用性前五 ETF
-> 固定备兑与 IV择时备兑回测
-> 输出 source 表、中文表格、图表和报告
```

## 项目范围

当前从 18 只 ETF 标的池中按备兑适用性评分选取前五 ETF 进入策略回测：

```text
510300
510050
588000
159915
510500
```

适用性评分维度包括：

```text
ETF流动性
期权可得性
期权流动性
权利金充足性
低上涨截断风险
数据质量
```

最终评分会叠加硬门槛：

```text
最终评分 = 软评分
        * 是否有期权
        * 是否有可选月度roll
        * 数据完整度是否达标
        * 交易天数是否达标
```

## 策略列表

当前可执行策略：

```text
S0_BuyHold
S1_ATM_100_Monthly
S4_OTM5_100_Monthly
S5_IVTiming_ATM_Monthly
S6_IVTiming_OTM5_Monthly
S7_IVStyleRule_v1
S8_IVStyleRule_Close_v1
```

含义：

```text
S0_BuyHold
    买入持有，作为 ETF 基准。

S1_ATM_100_Monthly
    每月卖出接近平值的认购期权，100%覆盖。

S4_OTM5_100_Monthly
    每月卖出行权价约为 ETF 价格 105% 的认购期权，100%覆盖。

S5_IVTiming_ATM_Monthly
    基于日频 30D ATM IV proxy 的分位数择时策略。
    高IV regime：卖出 ATM，100%覆盖。
    正常IV regime：卖出 ATM，50%覆盖。
    低IV或信号无效：跳过卖出。

S6_IVTiming_OTM5_Monthly
    与 S5 使用同一套 IV 择时信号和覆盖比例规则。
    高IV regime：卖出 OTM5，100%覆盖。
    正常IV regime：卖出 OTM5，50%覆盖。
    低IV或信号无效：跳过卖出。

S7_IVStyleRule_v1
    风格分层组合策略。
    510300/510050 使用 RuleB_BroadBaseEnhanced + ATM。
    588000/159915/510500 使用 RuleD_HighIVOnly + OTM5。

S8_IVStyleRule_Close_v1
    在 S7 的风格规则基础上加入定制提前平仓。
    宽基 ETF：roll 日 IV 分位数 <15% 时不新卖期权；持仓期间 IV 分位数跌破 15%，且买回价 <= 开仓权利金 50%，则买回平仓。
    成长/高弹性 ETF：持仓期间 IV 分位数跌出 high_iv 区间，即 <70%，且买回价 <= 开仓权利金 50%，则买回平仓。
    平仓后本周期不再重新卖出期权，继续持有 ETF 到下个 roll。
```

`S2_Delta30_100_Monthly` 和 `S3_Delta30_50_Monthly` 仍保留在策略规格中，但当前主流程不展示，因为当前标准化期权数据没有稳定 delta 字段。

当前实验设计先用 `S5_IVTiming_ATM_Monthly` 检验 IV 择时是否能改善同一 ATM 选券规则下的备兑表现，再用 `S6_IVTiming_OTM5_Monthly` 作为 moneyness 对照。这样避免一开始做大规模 OTM 参数网格，降低过拟合和解释复杂度。

## IV规则实验框架

除主策略回测外，项目单独生成一组 IV 覆盖规则实验，避免把阈值、覆盖比例和 moneyness 混成大规模参数搜索。

实验分两层：

```text
core_atm
    ATM核心检验。固定选券为 ATM，只比较 IV regime 到覆盖比例的映射规则。

otm5_check
    OTM5稳健性检查。使用同一套 IV规则，检查 moneyness 改为 OTM5 后结论是否稳定。
```

当前只比较四个预设规则：

```text
RuleA_Current 当前保守版
    warmup_invalid 0%
    data_invalid   0%
    low_iv         0%
    normal_iv      50%
    high_iv        100%

RuleB_BroadBaseEnhanced 宽基稳健增强版
    warmup_invalid 100%
    data_invalid   0%
    low_iv         50%
    normal_iv      75%
    high_iv        100%

RuleC_GrowthDefensive 成长防守版
    warmup_invalid 0%
    data_invalid   0%
    low_iv         0%
    normal_iv      25%
    high_iv        75%

RuleD_HighIVOnly 高IV-only版
    warmup_invalid 0%
    data_invalid   0%
    low_iv         0%
    normal_iv      0%
    high_iv        100%
```

这个框架刻意不展开阈值网格。阈值仍固定为：

```text
low_iv <= 30%
high_iv >= 70%
```

也就是说，当前实验只回答一个问题：

```text
在固定 IV regime 划分下，不同覆盖比例规则是否更适合不同 ETF 风格？
```

对应输出：

```text
data/source/iv_rule_experiment_summary.csv
data/source/iv_rule_experiment_periods.csv
data/source/iv_rule_experiment_by_style.csv
data/source/iv_rule_regime_decomposition.csv
data/source/iv_rule_recommendation.csv
data/source/iv_style_rule_v1_summary.csv
data/source/iv_style_rule_v1_periods.csv
data/source/iv_style_rule_close_v1_summary.csv
data/source/iv_style_rule_close_v1_periods.csv
data/source/iv_valid_sample_strategy_summary.csv
tables/iv_rule_experiment_summary_cn.csv
tables/iv_rule_experiment_by_style_cn.csv
tables/iv_rule_recommendation_cn.csv
```

当前从规则实验得到的组合策略是：

```text
IVStyleRule_v1

宽基/大盘 ETF：
    510300, 510050
    使用 RuleB_BroadBaseEnhanced + ATM
    逻辑：宽基 ETF 的备兑收益不只来自高 IV；warm-up 阶段使用 ATM 100% fallback，低IV/正常IV 也保留中等覆盖，增强长期权利金收取。真实数据无效的 data_invalid 仍跳过。

成长/高弹性 ETF：
    588000, 159915, 510500
    使用 RuleD_HighIVOnly + OTM5
    逻辑：只在高IV补偿足够时卖出，且卖得更虚值，降低上涨截断成本。
```

在最终风格组合上，项目还单独生成提前平仓对照：

```text
IVStyleRule_Close_v1

BroadBase close rule:
    roll 日 IV percentile < 15%：不新卖期权。
    持仓期间 IV percentile < 15%
    且 buyback_price <= 50% * open_premium：买回平仓。

Growth close rule:
    持仓期间 IV percentile < 70%
    且 buyback_price <= 50% * open_premium：买回平仓。

平仓行为只用于回补已有 short call；平仓后本周期不再开新仓。
```

## 日频 IV 择时

IV 择时模块使用 ETF-specific 30D ATM IV proxy：

```text
日频 C/P 期权链
-> 选择每只 ETF 接近 ATM、剩余期限 20-45 天的 call/put
-> 使用 Black-Scholes 反解 call IV 和 put IV
-> call/put IV 平均
-> 对近端/远端期限做 30D constant-maturity 插值
-> 计算 ETF 自身历史 IV 分位数、z-score、RV、IV-RV spread
-> 标记 high_iv / normal_iv / low_iv / invalid regime
```

IV 信号优先使用：

```text
data/raw/options_daily.csv
```

如果该文件不存在，构建流程会回退到旧的月末快照：

```text
data/raw/options.csv
```

当前已经接入并生成了日频期权链：

```text
data/raw/tushare_opt_daily_full_raw.csv
data/raw/options_daily.csv
data/source/iv_timing_signals.csv
```

当前 IV 分位数配置：

```text
percentile_window = 252
min_percentile_observations = 252
```

也就是说，只有累积至少 252 个有效 IV 观测后，才会生成有效 IV regime。分位数按“最近 252 个有效 IV 观测”计算，而不是要求连续 252 个自然交易日都必须有可用期权链。

无效 IV 被拆成两类：

```text
warmup_invalid
    当日 IV proxy 可计算，但还没有累积满 252 个有效 IV 观测。

data_invalid
    当日 IV proxy 本身不可用，例如期权链不足、筛选后无合约或反解 IV 失败。
```

完整样本用于展示策略可执行性；`data/source/iv_valid_sample_strategy_summary.csv` 则从每只 ETF 第一个有效 IV regime 日期之后开始统计，用作 IV 择时效果的稳健性口径。

## 目录结构

```text
covered_call_mini/
  README.md
  DATA_DICTIONARY.md

  config/
    tushare_token.txt
    tushare_http_url.txt

  data/
    raw/
      etf_prices.csv
      options.csv
      options_daily.csv
      etf_metadata.csv
      tushare_fund_daily_raw.csv
      tushare_opt_basic_raw.csv
      tushare_opt_daily_raw.csv
      tushare_opt_daily_full_raw.csv
    source/
      data_quality_report.csv
      etf_universe_screen.csv
      etf_suitability_scores.csv
      selected_top5_etfs.csv
      iv_timing_signals.csv
      fixed_cc_strategy_summary.csv
      pnl_decomposition_by_roll.csv
      nav_by_strategy.csv

  figures/
  report/
  scripts/
  src/
  tables/
```

`data/raw/` 是研究输入数据，`data/source/` 是由脚本重建的中间结果。`tables/`、`figures/` 和 `report/` 是展示层输出。

## 常用命令

采集日频 ETF 期权链：

```bash
python scripts/collect_daily_options.py --start-date 2021-01-01 --end-date 2026-06-03 --sleep-seconds 0.05
```

从 `data/raw/` 重建 `data/source/`：

```bash
python scripts/build_from_raw_data.py
```

重建 source 表、中文表格、图表和报告：

```bash
python scripts/covered_call_mini_demo.py
```

语法检查：

```bash
python -m compileall src scripts
```

## 主要输出

```text
data/source/iv_timing_signals.csv
data/source/fixed_cc_strategy_summary.csv
data/source/pnl_decomposition_by_roll.csv
data/source/nav_by_strategy.csv

tables/top5_suitability_scores_cn.csv
tables/universe_suitability_audit_cn.csv
tables/top5_executable_strategy_summary_cn.csv
tables/top5_roll_decomposition_cn.csv
tables/iv_rule_experiment_summary_cn.csv
tables/iv_rule_experiment_by_style_cn.csv
tables/iv_rule_recommendation_cn.csv
data/source/iv_style_rule_close_v1_summary.csv
data/source/iv_style_rule_close_v1_periods.csv
data/source/iv_valid_sample_strategy_summary.csv

figures/top5_nav_curves_executable.png
figures/top5_relative_nav_vs_buyhold.png
figures/top5_annualized_return_heatmap.png
figures/top5_excess_return_heatmap.png
figures/top5_sharpe_heatmap.png
figures/top5_option_contribution_decomposition.png
figures/top5_option_success_and_assignment.png

report/focused_top5_executable_strategy_report.md
```

## 当前日频 IV 结果摘要

最近一次重建后：

```text
iv_timing_signals.csv 行数: 5135
IV来源: options_daily.csv
signal_valid=1: 3252
signal_valid=0: 1883

normal_iv: 1346
high_iv:   1092
low_iv:     814
warmup_invalid: 1255
data_invalid:    628
```

`S5_IVTiming_ATM_Monthly` 当前执行分布：

```text
high_iv_sell:           61
normal_iv_sell:         68
low_iv_skip:            55
warmup_invalid_skip:    72
data_invalid_skip:      69
```

`S6_IVTiming_OTM5_Monthly` 使用相同 IV regime 和覆盖比例规则，因此执行分布相同，但选券 moneyness 不同。

最近一次重建后的策略汇总要点：

```text
S5_IVTiming_ATM_Monthly
    用于检验 ATM 固定备兑 vs ATM IV择时。

S6_IVTiming_OTM5_Monthly
    用于检验 OTM5 固定备兑 vs OTM5 IV择时，以及 ATM择时 vs OTM5择时。
```

## Git 建议

当前目录还不是 Git 仓库，可以初始化 Git。建议先确认 `.gitignore`，避免提交 token、缓存和超大日频原始数据。

推荐初始化流程：

```bash
git init
git add README.md DATA_DICTIONARY.md .gitignore src scripts
git add data/source tables figures report
git commit -m "Add covered call IV timing research pipeline"
```

如果希望把 `data/raw/options_daily.csv` 和 `data/raw/tushare_opt_daily_full_raw.csv` 也纳入版本管理，建议使用 Git LFS；否则普通 Git 仓库会很快变重。

## 风险提示

本项目用于研究和回测展示，不构成实盘投资建议。备兑策略表现受样本区间、ETF行情路径、期权报价质量、交易成本假设、覆盖比例、选券规则和 IV 择时规则共同影响。
