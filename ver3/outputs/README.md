# ver3 Outputs

这里先作为输出索引目录，不复制大 CSV、PNG 或 daily 明细。

当前真实 ver3 输出仍在仓库根目录：

```text
..\outputs\ver3_0_stepA_single_etf_sleeves\
..\outputs\ver3_0_stepA_extension_510050_sleeve_clarification\
..\outputs\ver3_0_stepA_extension_588000_sleeve_clarification\
..\outputs\ver3_0_sleeve_diagnostics_report_pack\
..\outputs\ver3_0_stepB_fixed_weight_universe_comparison\
..\outputs\ver3_0_stepB_plus_mdd_constrained_sharpe_frontier\
..\outputs\ver3_0_stepC_robustness_stability_diagnostics\
```

后续如果某个新实验已经完全项目化，可以用脚本参数把输出定向到：

```text
ver3/outputs/<experiment_id>/
```

但在 Step A / Step B 旧输出还作为下游输入时，不建议搬迁这些目录。

当前 Step B+ 只在本目录保留轻量索引：

```text
ver3_0_stepB_plus_output_index.md
```

当前 Step C 只在本目录保留轻量索引：

```text
ver3_0_stepC_output_index.md
```
