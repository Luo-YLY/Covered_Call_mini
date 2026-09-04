# ver3 Script Wrappers

这里的 PowerShell 文件是薄包装器，方便你在 VSCode 的 ver3 工作区里直接运行当前实验。

它们不包含策略逻辑。Step A 的真实 Python 脚本已经迁入：

```text
ver3/scripts/python/run_ver3_0_stepA_single_etf_sleeves.py
ver3/scripts/python/run_ver3_0_stepA_extension_510050_sleeve_clarification.py
ver3/scripts/python/run_ver3_0_stepA_extension_588000_sleeve_clarification.py
ver3/scripts/python/run_ver3_0_stepA_moneyness_refined_surface.py
```

根目录 `scripts/run_ver3_0_stepA_*.py` 只保留兼容入口。其他真实逻辑仍在：

```text
早期集中 sleeve 诊断报告构建器已在 2026-09-04 主线收口时归档；当前以 ver3.1 报告、看板和各实验自身 manifest 为交接入口。
ver3/scripts/python/ver3_0_stepB_fixed_weight_universe_comparison.py
ver3/src/covered_call_mini_ver3/
```

推荐读源码时先打开 `ver3/SOURCE_MAP.md`。
