# ver4.0 单 ETF 备兑周期现金流诊断

`ver4.0` 是独立于 `ver3` 的新实验主线。它不再以复利净值、CAGR 或多 ETF 组合优化作为主要结论，而是回答单一 ETF 底仓在每一个备兑交易周期中的现金流、上涨让渡和可执行性。

## 核算原则

- 每个交易周期以相同的固定名义本金重新计量，默认 `100`。
- 上一期盈亏不滚入下一期；累计结果是非复利累计损益，而不是账户净值。
- `gross_premium_cash` 仅表示开仓时收取的权利金现金流；产品经济结果使用扣除行权/平仓损失和交易摩擦后的 `net_option_pnl_cash`。
- 日频 MTM 仅展示单个周期内的浮动风险，不能被拼接为 ver4.0 的主净值曲线。
- BuyHold 是同一周期的 ETF 底仓基准。`relative_to_buyhold_pnl_cash` 等于期权腿净收益，不把“收到权利金”误称为额外净收益。

## 当前范围

1. 单 ETF，单独运行。
2. 静态 DTE30、100% 覆盖的 ATM + D10/D20/D30/D40/D50 网格。
3. 每个期权周期的固定名义本金账本、12 周期滚动现金收入、事后市场环境归因与数据完整性校验。
4. 不做多 ETF 组合，不做动态权重，不做 IV 择时，不把任何收益概率表述为保证。

IV Rank 开仓门槛、覆盖率扩展、随机交易日缺失压力和目标现金收入重抽样将作为后续独立模块接入，而不是修改这一静态基线。

## 运行

从仓库根目录运行：

```powershell
python ver4\scripts\python\run_ver4_0_single_etf_cycle_cashflow.py --etf 510300
```

仅检查配置与输入边界，不运行网格：

```powershell
python ver4\scripts\python\run_ver4_0_single_etf_cycle_cashflow.py --etf 510300 --dry-run
```

默认输出到：

```text
outputs/ver4_0_single_etf_cycle_cashflow/<ETF代码>/
```

构建并打开周期现金流看板：

```powershell
python ver4\scripts\python\build_ver4_dashboard_data.py
python -m http.server 8765
```

访问 `http://127.0.0.1:8765/ver4/dashboard/`。

## 核心输出

- `period/ver4_0_cycle_ledger.csv`：逐期现金账本，是主分析表。
- `daily_mtm/ver4_0_cycle_daily_mtm.csv`：按周期重置后的日频盯市，不含跨周期复利 NAV。
- `summary/ver4_0_cycle_cashflow_summary.csv`：每个参数组合的周期现金流汇总。
- `summary/ver4_0_rolling_12_cycle_cashflow.csv`：滚动 12 个周期的非复利现金收入。
- `regime/ver4_0_cycle_regime_attribution.csv`：下跌、震荡、上涨和强上涨周期归因。
- `audit/ver4_0_validation_summary.csv`：会计恒等式、样本与输出检查。

## 模块边界

| 模块 | 责任 |
| --- | --- |
| `engine_adapter.py` | 复用冻结的交易引擎，仅生成真实交易周期。 |
| `ledger.py` | 将每个周期重置为固定名义本金，生成现金账本与周期内 MTM。 |
| `metrics.py` | 汇总非复利现金流、上涨让渡与滚动 12 周期结果。 |
| `regime.py` | 生成事后市场环境归因；不参与开仓决策。 |
| `validation.py` | 校验现金流、收益分解、无复利主账本及输出完整性。 |
| `pipeline.py` | 编排运行、写出结果与生成研究说明。 |
