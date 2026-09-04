# ver3 Project Layout

这个目录现在可以作为一个单独的 VSCode 项目文件夹打开：

```text
C:\Users\WIN11\Desktop\CCFund\ETF备兑策略设计\covered_call_mini\ver3
```

它和根目录的 `covered_call_mini_ver3.code-workspace` 是两种入口：

- 打开 `ver3/` 文件夹：适合人工跟源码、加注释、看运行手册。
- 打开 `covered_call_mini_ver3.code-workspace`：适合同时看 ver3 源码、根目录脚本和输出目录。

## Folder Contract

```text
ver3/
  README.md
  PROJECT_LAYOUT.md
  SOURCE_MAP.md
  RUNBOOK.md
  MIGRATION_PLAN.md
  .vscode/
  src/
  scripts/
  configs/
  docs/
  outputs/
  tests/
  data/
```

## What Lives Here Now

| Folder | Current role |
| --- | --- |
| `.vscode/` | 直接打开 `ver3/` 文件夹时的 Python 路径和搜索排除设置。 |
| `scripts/` | Step A / Step B 真实 Python runner 和 PowerShell 薄包装器。 |
| `src/` | ver3 主源码位置；当前 Step B 已在 `ver3/src/covered_call_mini_ver3/stepB/`。 |
| `configs/` | 后续新增 ver3 配置快照或模板。 |
| `docs/` | 后续新增 ver3 专属说明。当前主规划仍在根目录 `docs/`。 |
| `outputs/` | 轻量索引目录；当前真实输出仍在根目录 `outputs/ver3_*`。 |
| `tests/` | 后续新增 ver3 regression/smoke tests。 |
| `data/` | 只放 ver3 专属小型输入清单或说明，不复制原始行情大文件。 |

## Source Of Truth

当前已经跑通并验证的 Step B 源码以这里为准：

```text
ver3/src/covered_call_mini_ver3/stepB/
ver3/scripts/python/ver3_0_stepB_fixed_weight_universe_comparison.py
```

仓库根目录 `scripts/ver3_0_stepB_fixed_weight_universe_comparison.py` 只作为兼容入口保留。

当前 Step A 真实 Python 脚本已经迁到：

```text
ver3/scripts/python/
```

仓库根目录 `scripts/run_ver3_0_stepA_*.py` 只作为兼容入口保留。

后续新 Step，例如 Step B+ / Step C，可以直接写进：

```text
ver3/src/covered_call_mini_ver3/
```

对应入口脚本可以先放在：

```text
ver3/scripts/
```

如果新脚本需要复用根目录数据或旧指标口径，在脚本开头显式加入 repo root 和 `../src` 到 `sys.path`，并在 `SOURCE_MAP.md` 里登记。
