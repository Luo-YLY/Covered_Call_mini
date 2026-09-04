# ver3.0 Step B+ 最大回撤约束 Sharpe 前沿

Step B+ 是 Step B 固定权重组合比较之后的静态权重前沿层。

从仓库根目录运行：

```powershell
python -B ver3\scripts\python\run_stepB_plus_mdd_constrained_sharpe_frontier.py --strict
```

主输出目录：

```text
outputs/ver3_0_stepB_plus_mdd_constrained_sharpe_frontier/
```

`ver3/outputs/` 下只保留 Step B+ 的轻量索引：

```text
ver3/outputs/ver3_0_stepB_plus_output_index.md
```

本步骤不修改 `src/metrics/` 或 `ver2_downside_protection/`。

报告语言：面向阅读的报告默认中文输出；CSV 字段名和指标名保留稳定英文标识。
