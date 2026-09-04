# ETF备兑策略研究

本仓库是项目最终交接工作区，对外统一为一个研究产品，不再用版本号区分入口。

接收方请先阅读 [`HANDOFF.md`](HANDOFF.md)。

- 组合研究：从单 ETF 参数曲面进入固定权重、回撤约束前沿和稳健性诊断。
- 单 ETF 周期验证：按独立固定名义本金核算备兑周期现金流、上涨让渡与提前平仓。
- 最终看板：把上述两层证据合并在一个入口中，并附交接与研究边界说明。

研究输出仅用于研究与展示，不构成交易指令或收益保证。

## 项目结构

```text
dashboard/                 对外统一的最终研究看板入口
src/                       公共数据、期权、回测和指标代码
ver2_downside_protection/  仍被主线调用的冻结兼容引擎
ver3/                      组合研究内部实现、脚本、测试和页面
ver4/                      单 ETF 周期验证内部实现、脚本、测试和页面
configs/                   非秘密研究配置
data/raw/                  ETF 与期权输入数据
data/source/               target-delta 派生期权数据
outputs/ver3_*/            组合研究历史编号输出
outputs/ver4_*/            周期验证历史编号输出
outputs/presentation/      当前汇报材料
scripts/                   数据采集、主线兼容入口和发布脚本
tests/                     公共兼容引擎测试
docs/                      工程、Git 与交接说明
```

`ver2_downside_protection/`、`ver3/`、`ver4/` 是为复现与审计保留的内部技术路径，不再作为交付产品名称。删除、改名或重写这些路径之前，必须先完成依赖迁移并让全部对照测试通过。

## 环境

建议使用 Python 3.10 以上。主要依赖：

```text
numpy
pandas
scipy
matplotlib
pyyaml
pytest
```

访问凭据只从本机环境或未跟踪的 `config/*.txt` 读取，不得提交或装入交接包。

## 快速验收

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = "1"
python -m pytest -q tests ver3\tests ver4\tests
```

## 组合研究引擎

查看工程入口：

```powershell
.\ver3\scripts\ver3.ps1 list
.\ver3\scripts\ver3.ps1 doctor
```

运行当前目标 Delta 主实验：

```powershell
python ver3\scripts\python\run_ver3_1_effective_zone_target_delta.py
```

完整说明见 `ver3/README.md`、`ver3/RUNBOOK.md` 与 `ver3/SOURCE_MAP.md`。

## 单 ETF 周期验证引擎

运行单 ETF 周期现金流基线：

```powershell
python ver4\scripts\python\run_ver4_0_single_etf_cycle_cashflow.py --etf 510300
```

完整说明见 `ver4/README.md`。

## 看板

从仓库根目录启动静态服务：

```powershell
python -m http.server 8765 --bind 127.0.0.1
```

统一入口：`http://127.0.0.1:8765/dashboard/`

交接方无需按版本号寻找页面；组合研究和单 ETF 周期验证均从统一入口切换。

## 交接打包

```powershell
.\scripts\package_project_release.ps1 -Profile Final -ReleaseTag YYYYMMDD
```

`Final` 生成一个完整交接包，包含源码、测试、统一看板、精选研究结果和冻结输入数据。需要拆分传输时仍可使用：

- `Source`：源码、测试、配置和文档。
- `Demo`：源码加统一看板、看板依赖和精选研究结果。
- `Inputs`：主线运行所需的冻结输入数据，不含凭据。

每个 ZIP 均有独立 SHA-256 文件，包内包含 `GIT_SNAPSHOT.txt` 与逐文件 `FILE_INDEX.csv`。详细规则见 `docs/GIT_AND_RELEASE_GUIDE.md`。

## 历史内容

2026-09-04 主线收口时，早期项目副本、旧 layer/multi-asset 实验和旧展示目录已移出工作区主线，保存在 Git 忽略的本地 `dist/legacy_archive_20260904/` 中，便于必要时回查；它们不进入正式交接包。
