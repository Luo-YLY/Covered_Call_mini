# ver3.0 Step C 稳健性与稳定性诊断

Step C 是 Step B+ 之后的诊断层，不新增期权参数，也不做动态权重。

从仓库根目录运行：

```powershell
python -B ver3\scripts\python\run_stepC_robustness_stability_diagnostics.py --strict
```

轻量调试：

```powershell
python -B ver3\scripts\python\run_stepC_robustness_stability_diagnostics.py --strict --skip-plots
```

主输出目录：

```text
outputs/ver3_0_stepC_robustness_stability_diagnostics/
```

`ver3/outputs/` 下只保留轻量索引：

```text
ver3/outputs/ver3_0_stepC_output_index.md
```

报告语言：面向阅读的报告默认中文输出；CSV 字段名和指标名保留稳定英文标识。
