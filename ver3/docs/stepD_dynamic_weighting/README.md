# ver3.0 Step D：波动率控制的动态 sleeve 权重

Step D 是 Step C 之后的动态权重研究层。它只调整固定 sleeve 之间的组合资金权重，不重新选择期权、不改变 DTE/delta/moneyness/TP/Touch-K、不动态调整 q，也不引入 588000 主线长样本。

从仓库根目录运行：

```powershell
python -B ver3\scripts\python\run_stepD_volatility_controlled_dynamic_weighting.py --strict
```

轻量调试：

```powershell
python -B ver3\scripts\python\run_stepD_volatility_controlled_dynamic_weighting.py --strict --skip-plots
```

PowerShell wrapper：

```powershell
ver3\scripts\run_stepD_dynamic_weighting.ps1
```

真实输出目录：

```text
outputs/ver3_0_stepD_volatility_controlled_dynamic_weighting/
```

轻量索引：

```text
ver3/outputs/ver3_0_stepD_output_index.md
```

人工审查顺序建议：

1. `ver3/scripts/python/run_stepD_volatility_controlled_dynamic_weighting.py`
2. `ver3/src/covered_call_mini_ver3/stepD_dynamic_weighting/config.py`
3. `universe.py` 与 `signals.py`
4. `weights.py` 与 `rebalance.py`
5. `portfolio.py`、`metrics.py`、`turnover.py`
6. `validation.py` 与 `reporting.py`

核心输出优先看：

```text
summary/ver3_0_stepD_dynamic_strategy_summary.csv
summary/ver3_0_stepD_comparison_vs_static_baselines.csv
summary/ver3_0_stepD_recommendation_table.csv
weights/ver3_0_stepD_rebalance_weights.csv
turnover/ver3_0_stepD_turnover_summary.csv
cost/ver3_0_stepD_rebalance_cost_sensitivity.csv
reports/ver3_0_stepD_volatility_controlled_dynamic_weighting_report.md
```

报告默认中文输出；CSV 字段名保留英文稳定标识，便于后续 dashboard 和脚本读取。
