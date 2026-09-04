# ver3 Migration Plan

目标：让 ver3 变成清晰、可跟读、可复现的研究主线，同时不破坏 ver1/ver2 的历史证据。

## Phase 0: Workspace Isolation

状态：已完成。

已新增：

- `covered_call_mini_ver3.code-workspace`
- `ver3/README.md`
- `ver3/SOURCE_MAP.md`
- `ver3/RUNBOOK.md`
- `ver3/scripts/*.ps1`

这一阶段只改变 VSCode 视图和人工导航，不移动旧文件，不改 import，不改已完成实验输出。

## Phase 0.5: Project Folder Isolation

状态：已完成。

`ver3/` 现在可以作为单独项目文件夹打开，新增：

```text
ver3/.vscode/
ver3/PROJECT_LAYOUT.md
ver3/src/
ver3/configs/
ver3/docs/
ver3/outputs/
ver3/tests/
ver3/data/
```

这一阶段仍不搬迁已验证 Step B 源码和已完成输出，只把项目边界、未来落点和人工阅读入口放清楚。

## Phase 1: New Work Goes Into ver3 Source

状态：当前规则。

后续 Step B+、Step C、Step D 新增代码时，默认放在：

```text
ver3/src/covered_call_mini_ver3/<step_name>/
ver3/scripts/run_<step_name>.ps1
outputs/ver3_<step_name>/
```

每个 step 至少要有：

```text
config.py
io.py
metrics.py
validation.py
reporting.py
```

如果该 step 涉及组合构造、归因或绘图，再单独增加：

```text
portfolio.py
attribution.py
plotting.py
```

## Phase 2: Promote Step A Into Modules

状态：已部分完成。

Step A 三个真实 Python 入口已经迁入：

```text
ver3/scripts/python/
```

根目录 `scripts/run_ver3_0_stepA_*.py` 保留为兼容 wrapper。

下一步如果要让源码更好跟，可以把 Step A 中稳定逻辑继续拆进：

```text
ver3/src/covered_call_mini_ver3/stepA/
  config.py
  sleeve_engine.py
  sleeve_catalog.py
  reporting.py
  validation.py
```

届时 `ver3/scripts/python/run_ver3_0_stepA_*.py` 也可以继续变薄，只负责解析参数、调用模块、落输出。

## Phase 3: Reduce Frozen Dependencies

状态：暂缓。

当前 ver3 仍复用：

```text
src/metrics/ver2_metric_standard.py
ver2_downside_protection/config.py
ver2_downside_protection/strategy_engine.py
```

迁移原则：

- 指标口径可以先复制测试，再迁入 `ver3/src/covered_call_mini_ver3/common/metrics.py`。
- 旧 engine 不直接改；如果要迁入，先生成对照输出，确认 NAV、trade log、summary 逐项一致。
- 迁移前后必须保留同一输入、同一样本、同一参数的 regression check。

## Phase 4: Optional Physical Standalone Project

状态：只有在 ver3 进入稳定写作/交付阶段才考虑。

如果后面需要真的把 ver3 单独拎成一个小项目，再创建：

```text
covered_call_mini_ver3/
  src/
  scripts/
  configs/
  outputs/
  docs/
  tests/
```

当前仍不建议马上做完整物理拆仓，因为 Step A/Step B 仍依赖原仓库里的数据、旧指标口径和部分旧 engine。现在已经把 Step A 入口迁入 `ver3/`，后续再逐步模块化。
