# covered_call_mini

ETF 备兑策略研究工程，当前以 `ver3` 与 `ver4` 为双主线。

- `ver3`：从单 ETF 参数曲面进入固定权重、回撤约束前沿、稳健性与动态权重研究。
- `ver4`：按独立固定名义本金核算单 ETF 备兑周期现金流、上涨让渡与提前平仓。

研究输出仅用于研究与展示，不构成交易指令或收益保证。

## 项目结构

```text
src/                       公共数据、期权、回测和指标代码
ver2_downside_protection/  ver3/ver4 仍在调用的冻结兼容引擎
ver3/                      ver3 主线源码、脚本、测试和看板
ver4/                      ver4 主线源码、脚本、测试和看板
configs/                   非秘密研究配置
data/raw/                  ETF 与期权输入数据
data/source/               target-delta 派生期权数据
outputs/ver3_*/            ver3 研究输出
outputs/ver4_*/            ver4 研究输出
outputs/presentation/      当前汇报材料
scripts/                   数据采集、主线兼容入口和发布脚本
tests/                     公共兼容引擎测试
docs/                      工程、Git 与交接说明
```

`ver2_downside_protection/` 只作为冻结兼容引擎保留，不再代表当前研究版本。删除或重写它之前，必须让 ver3/ver4 的对照测试通过。

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

## ver3

查看工程入口：

```powershell
.\ver3\scripts\ver3.ps1 list
.\ver3\scripts\ver3.ps1 doctor
```

运行当前 ver3.1 target-delta 主实验：

```powershell
python ver3\scripts\python\run_ver3_1_effective_zone_target_delta.py
```

完整说明见 `ver3/README.md`、`ver3/RUNBOOK.md` 与 `ver3/SOURCE_MAP.md`。

## ver4

运行单 ETF 周期现金流基线：

```powershell
python ver4\scripts\python\run_ver4_0_single_etf_cycle_cashflow.py --etf 510300
```

完整说明见 `ver4/README.md`。

## 看板

从仓库根目录启动一个静态服务即可同时打开两个看板：

```powershell
python -m http.server 8765 --bind 127.0.0.1
```

- ver3：`http://127.0.0.1:8765/ver3/dashboard/`
- ver4：`http://127.0.0.1:8765/ver4/dashboard/`

## 交接打包

```powershell
.\scripts\package_project_release.ps1 -Profile All -ReleaseTag YYYYMMDD
```

默认生成：

- `source`：源码、测试、配置和文档。
- `demo`：源码加看板数据、精选研究结果与汇报材料。
- `inputs`：主线运行所需的冻结输入数据，不含凭据。

每个 ZIP 均有独立 SHA-256 文件，包内包含 `GIT_SNAPSHOT.txt` 与逐文件 `FILE_INDEX.csv`。详细规则见 `docs/GIT_AND_RELEASE_GUIDE.md`。

## 历史内容

2026-09-04 主线收口时，早期 ver1/ver2 项目副本、旧 layer/multi-asset 实验和旧展示目录已移出工作区主线，保存在 Git 忽略的本地 `dist/legacy_archive_20260904/` 中，便于必要时回查；它们不进入主线提交和正式交接包。
