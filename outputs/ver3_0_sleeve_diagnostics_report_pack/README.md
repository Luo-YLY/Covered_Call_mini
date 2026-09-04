# ver3.0 Sleeve Diagnostics Report Pack

本目录是 ver3.0 已完成 single-ETF sleeve 诊断的集中阅读入口。

它不移动、不替代原始实验输出。每个来源实验仍保留自己的完整目录、panel、figures、audit 和可复现契约；这里仅收集轻量 Markdown 报告、面向阅读的汇总表，以及虚值-覆盖率诊断图。

## 报告入口

| 集中报告 | 类型 | ETF | 来源 |
| --- | --- | --- | --- |
| [reports/00_ver3_universe_strategy_direction.md](reports/00_ver3_universe_strategy_direction.md) | strategy_direction | - | `outputs/ver3_0_stepA_extension_588000_sleeve_clarification/strategy/ver3_0_universe_strategy_direction.md` |
| [reports/01_stepA_main_single_etf_master_report.md](reports/01_stepA_main_single_etf_master_report.md) | master_report | 510300,510500,159915 | `outputs/ver3_0_stepA_single_etf_sleeves/reports/ver3_0_stepA_single_etf_sleeve_master_report.md` |
| [reports/02_510300_sleeve_card.md](reports/02_510300_sleeve_card.md) | sleeve_card | 510300 | `outputs/ver3_0_stepA_single_etf_sleeves/reports/510300_sleeve_card.md` |
| [reports/03_510500_sleeve_card.md](reports/03_510500_sleeve_card.md) | sleeve_card | 510500 | `outputs/ver3_0_stepA_single_etf_sleeves/reports/510500_sleeve_card.md` |
| [reports/04_159915_sleeve_card.md](reports/04_159915_sleeve_card.md) | sleeve_card | 159915 | `outputs/ver3_0_stepA_single_etf_sleeves/reports/159915_sleeve_card.md` |
| [reports/05_510050_extension_master_report.md](reports/05_510050_extension_master_report.md) | master_report | 510050 | `outputs/ver3_0_stepA_extension_510050_sleeve_clarification/reports/ver3_0_stepA_extension_510050_sleeve_master_report.md` |
| [reports/06_510050_sleeve_card.md](reports/06_510050_sleeve_card.md) | sleeve_card | 510050 | `outputs/ver3_0_stepA_extension_510050_sleeve_clarification/cards/510050_sleeve_card.md` |
| [reports/07_588000_extension_master_report.md](reports/07_588000_extension_master_report.md) | master_report | 588000 | `outputs/ver3_0_stepA_extension_588000_sleeve_clarification/reports/ver3_0_stepA_extension_588000_sleeve_master_report.md` |
| [reports/08_588000_sleeve_card.md](reports/08_588000_sleeve_card.md) | sleeve_card | 588000 | `outputs/ver3_0_stepA_extension_588000_sleeve_clarification/cards/588000_sleeve_card.md` |

## 主推荐

| ETF | Sleeve | 分类 | 状态 | CAGR | Sharpe | MDD | 期权腿年化净贡献 |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: |
| 159915 | `159915_DTE30_OTM5up_Q50_Hold` | Defensive Overlay | primary_for_portfolio_layer | 15.80% | 0.722 | 38.65% | -3.51% |
| 510050 | `510050_DTE30_D40_Q70_Hold` | Positive Carry Overlay | primary_for_portfolio_layer | 4.72% | 0.449 | 14.70% | 1.11% |
| 510300 | `510300_DTE30_D40_Q70_Hold` | Positive Carry Overlay | primary_for_portfolio_layer | 7.70% | 0.645 | 17.19% | 0.69% |
| 510500 | `510500_ETF_BuyHold` | Pure ETF Preferred | primary_for_portfolio_layer | 11.22% | 0.595 | 30.16% | 0.00% |
| 588000 | `588000_ETF_BuyHold` | Growth Extension Sleeve | primary_for_short_sample_extension | 23.90% | 0.785 | 36.48% | 0.00% |

## 虚值-覆盖率 3D 诊断

- 点图：`figures/ver3_0_sleeve_moneyness_coverage_sharpe_3d.png`
- 曲面图：`figures/ver3_0_sleeve_moneyness_coverage_sharpe_surface.png`
- 点表：`summary/ver3_0_sleeve_diagnostics_moneyness_coverage_3d_points.csv`
- 点数：28
- X 轴：`moneyness_axis`，优先使用 `median_realized_moneyness`，缺失时使用 `avg_realized_moneyness`。
- Y 轴：`coverage_axis`，优先使用 `avg_active_coverage`，缺失时从 sleeve 命名中的 `Qxx` 推断。
- Z 轴：`sharpe_daily_mean`。
- 注意：`D40` 是 Delta 选券，不是固定虚值；图中展示的是历史实际实现虚值。曲面由离散候选点三角剖分插值得到，仅作形状诊断。

## 每 ETF 细虚值参数曲面

这部分使用 raw option chain 重新按目标虚值选券，把虚值轴细化为 `ATM / OTM1 / OTM2 / OTM3 / OTM4 / OTM5 / OTM7`，覆盖率为 `Q10` 到 `Q100`。它用于完善单 ETF 诊断和生成更平滑的参数曲面，不直接改写 Step B/C/D 主线策略结论。

口径说明：该细网格已经切换为 continuous DTE30 daily MTM 口径；moneyness 轴重新选券，coverage 轴缩放同一 Q100 option leg。它仍是 Step A 单 ETF 诊断，不自动成为组合层候选。

| ETF | 细虚值网格 | 覆盖率网格 | 真实格点 | 样本 |
| --- | --- | --- | ---: | --- |
| 159915 | ATM, OTM1, OTM2, OTM3, OTM4, OTM5, OTM7 | Q10, Q20, Q30, Q40, Q50, Q60, Q70, Q80, Q90, Q100 | 70 | 2022-09-30 - 2026-05-27 |
| 510050 | ATM, OTM1, OTM2, OTM3, OTM4, OTM5, OTM7 | Q10, Q20, Q30, Q40, Q50, Q60, Q70, Q80, Q90, Q100 | 70 | 2022-09-30 - 2026-05-27 |
| 510300 | ATM, OTM1, OTM2, OTM3, OTM4, OTM5, OTM7 | Q10, Q20, Q30, Q40, Q50, Q60, Q70, Q80, Q90, Q100 | 70 | 2022-09-30 - 2026-05-27 |
| 510500 | ATM, OTM1, OTM2, OTM3, OTM4, OTM5, OTM7 | Q10, Q20, Q30, Q40, Q50, Q60, Q70, Q80, Q90, Q100 | 70 | 2022-09-30 - 2026-05-27 |
| 588000 | ATM, OTM1, OTM2, OTM3, OTM4, OTM5, OTM7 | Q10, Q20, Q30, Q40, Q50, Q60, Q70, Q80, Q90, Q100 | 70 | 2023-06-30 - 2026-05-27 |

曲面 Sharpe 高点（非推荐）：

| ETF | 规则 | 覆盖率 | Sharpe | CAGR | MDD | 期权腿年化贡献 |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| 159915 | OTM7 | Q20 | 0.702 | 17.50% | 39.86% | -1.91% |
| 510050 | ATM | Q100 | 0.752 | 6.69% | 9.41% | 1.92% |
| 510300 | OTM4 | Q100 | 0.753 | 9.31% | 18.53% | 1.25% |
| 510500 | OTM7 | Q10 | 0.645 | 12.19% | 29.82% | -0.37% |
| 588000 | OTM1 | Q10 | 0.782 | 22.48% | 34.26% | -1.85% |

- 正式报告：`outputs/ver3_0_stepA_moneyness_refined_daily_mtm_surface/reports/ver3_0_stepA_moneyness_refined_daily_mtm_surface_report.md`
- 网格表：`summary/ver3_0_sleeve_moneyness_refined_surface_grid.csv`
- BuyHold 基准：`summary/ver3_0_sleeve_moneyness_refined_buyhold_baseline.csv`
- 元数据：`summary/ver3_0_sleeve_moneyness_refined_surface_metadata.csv`
- 图索引：`summary/ver3_0_sleeve_moneyness_refined_surface_figures.csv`
- 最优点：`summary/ver3_0_sleeve_moneyness_refined_surface_best_points.csv`
- 图目录：`figures/moneyness_refined_surface/`
- 图数量：25
- 格点数量：350
- BuyHold 行数：5
- 注意：本细网格采用 continuous DTE30 daily MTM 口径，主要回答曲面形状和参数敏感性；它与当前 ver3 诊断口径可比，但仍不改写 Step B/C/D 冻结主线。

## 每 ETF 动态回测曲面

这部分把每只 ETF 单独展开成 `虚值/Delta 规则 × 覆盖率` 网格。覆盖率不是读取原始候选点，而是在日频层面重算：

`组合日收益 = ETF 底仓日收益 + 覆盖率 × 满覆盖期权腿日收益`

因此每一个覆盖率格点都对应一条可复算的动态净值路径。曲面只是对这些真实格点做插值展示，不能把插值点当作新增选券实验。

| ETF | 已有虚值/Delta 规则 | 动态回测格点 | 样本 | 来源 |
| --- | --- | ---: | --- | --- |
| 510050 | ATM, OTM2, OTM5, D50, D40, D30, D20 | 70 | 2022-09-19 - 2026-05-27 | `ver2_1_dte30_full_rule_grid` |
| 510300 | ATM, D40, OTM5_up | 30 | 2022-09-19 - 2026-05-27 | `ver2_6_stepA_available_rules` |
| 510500 | ATM, D40, OTM5_up | 30 | 2022-09-19 - 2026-05-27 | `ver2_6_stepA_available_rules` |
| 159915 | ATM, D40, OTM5_up | 30 | 2022-09-19 - 2026-05-27 | `ver2_6_stepA_available_rules` |
| 588000 | ATM, D40, OTM5_up | 30 | 2023-06-30 - 2026-05-27 | `ver3_stepA_588000_q100_scaled` |

Sharpe 最优格点：

| ETF | 规则 | 覆盖率 | Sharpe | CAGR | MDD | 期权腿年化贡献 |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| 159915 | ATM | Q70 | 0.797 | 13.89% | 29.26% | -6.40% |
| 510050 | ATM | Q100 | 0.695 | 6.14% | 10.32% | 2.18% |
| 510300 | ATM | Q100 | 0.758 | 7.36% | 12.83% | 0.08% |
| 510500 | OTM +5% | Q10 | 0.594 | 11.01% | 29.85% | -0.28% |
| 588000 | ATM | Q10 | 0.777 | 22.23% | 34.21% | -2.05% |

- 网格表：`summary/ver3_0_sleeve_parameter_surface_grid.csv`
- 元数据：`summary/ver3_0_sleeve_parameter_surface_metadata.csv`
- 图索引：`summary/ver3_0_sleeve_parameter_surface_figures.csv`
- 最优点：`summary/ver3_0_sleeve_parameter_surface_best_points.csv`
- 图目录：`figures/parameter_surface/`
- 图数量：20
- 格点数量：190

## 汇总表

- `summary/ver3_0_sleeve_diagnostics_report_manifest.csv`
- `summary/ver3_0_sleeve_diagnostics_combined_classification.csv`
- `summary/ver3_0_sleeve_diagnostics_primary_recommendations.csv`
- `summary/ver3_0_sleeve_diagnostics_correlation_references.csv`
- `summary/ver3_0_sleeve_diagnostics_moneyness_coverage_3d_points.csv`
- `summary/ver3_0_sleeve_moneyness_refined_surface_grid.csv`
- `summary/ver3_0_sleeve_moneyness_refined_buyhold_baseline.csv`
- `summary/ver3_0_sleeve_moneyness_refined_surface_metadata.csv`
- `summary/ver3_0_sleeve_moneyness_refined_surface_figures.csv`
- `summary/ver3_0_sleeve_moneyness_refined_surface_best_points.csv`
- `summary/ver3_0_sleeve_parameter_surface_grid.csv`
- `summary/ver3_0_sleeve_parameter_surface_metadata.csv`
- `summary/ver3_0_sleeve_parameter_surface_figures.csv`
- `summary/ver3_0_sleeve_parameter_surface_best_points.csv`

## 边界

这是报告包，不是新组合实验层。它不运行组合权重、不改写 Step B/C/D 结果，也不引入新的组合主线策略。细虚值曲面已经作为 Step A 单 ETF 诊断增强层单独落在 `outputs/ver3_0_stepA_moneyness_refined_daily_mtm_surface/`；它可以用于判断参数曲面形状，但不自动提升任何 ATM/Q100 等格点为组合主候选。
