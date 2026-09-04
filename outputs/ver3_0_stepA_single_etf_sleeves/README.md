# ver3.0 Step A：Single-ETF Covered-Call Sleeve Clarification

本目录保存 ver3.0 Step A 的实验输出。Step A 的职责是先把单 ETF 的 covered-call sleeve 解释清楚：每个 ETF 自己适合哪种期权覆盖方式、风险收益特征如何、是否值得进入后续组合层。

## 运行方式

在仓库根目录运行：

```powershell
python scripts\run_ver3_0_stepA_single_etf_sleeves.py
```

## 样本与范围

| 项目 | 内容 |
| --- | --- |
| 样本区间 | 2022-09-19 到 2026-05-27 |
| ETF 范围 | `510300`、`510500`、`159915` |
| sanity check | 18/18 通过 |

当前主结论：

| ETF | 推荐 sleeve | 分类 |
| --- | --- | --- |
| `510300` | `510300_DTE30_D40_Q70_Hold` | Positive Carry Overlay |
| `510500` | `510500_ETF_BuyHold` | Pure ETF Preferred |
| `159915` | `159915_DTE30_OTM5up_Q50_Hold` | Defensive Overlay |

## 输出说明

| 路径 | 说明 |
| --- | --- |
| `daily/ver3_0_stepA_single_etf_sleeve_daily_nav.csv` | 单 ETF sleeve 日频净值与收益 |
| `period/ver3_0_stepA_single_etf_period_attribution.csv` | 持仓期归因与期权腿贡献 |
| `summary/ver3_0_stepA_single_etf_sleeve_summary.csv` | sleeve 级绩效汇总 |
| `summary/ver3_0_stepA_sleeve_classification_table.csv` | sleeve 分类与推荐表 |
| `panel/ver3_0_stepA_sleeve_return_panel_long.csv` | 后续组合实验使用的长表收益面板 |
| `panel/ver3_0_stepA_sleeve_return_panel_wide.csv` | 后续组合实验使用的宽表收益面板 |
| `figures/` | 可再生成图表 |
| `reports/` | 阅读型报告和 sleeve 卡片 |
| `audit/ver3_0_stepA_sanity_checks.csv` | sanity check 结果 |

## 下游契约

Step B 固定权重组合实验应优先读取：

- `panel/ver3_0_stepA_sleeve_return_panel_wide.csv`
- `panel/ver3_0_stepA_sleeve_return_panel_long.csv`

Step A 不产生组合权重，不解释组合层收益，也不做动态优化。组合层问题从 Step B 开始处理。
