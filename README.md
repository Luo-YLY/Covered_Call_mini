# ETF备兑策略研究

本仓库是项目最终交接工作区，对外统一为一个研究产品，不再用版本号区分入口。

使用前请先阅读 [`PROJECT_GUIDE.md`](PROJECT_GUIDE.md)；最终交付复验步骤见
[`DELIVERY_CHECKLIST.md`](DELIVERY_CHECKLIST.md)。

- 组合研究：从单 ETF 参数曲面进入固定权重、回撤约束前沿和稳健性诊断。
- 单 ETF 周期验证：按独立固定名义本金核算备兑周期现金流、上涨让渡与提前平仓。
- 最终看板：把上述两层证据合并在一个入口中，并附交接与研究边界说明。

研究输出仅用于研究与展示，不构成交易指令或收益保证。

## 项目结构

```text
dashboard/                 对外统一的最终研究看板及原始数据入口
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

安装看板、回测和验收所需依赖：

```powershell
python -m pip install -r requirements.txt
```

如需同时使用 AkShare 或 Tushare 数据采集脚本，再安装可选采集依赖：

```powershell
python -m pip install -r requirements-collectors.txt
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

从仓库根目录启动本地看板服务：

```powershell
.\start_dashboard.ps1
```

需要指定端口时使用 `.\start_dashboard.ps1 -Port 8766`。

统一入口：`http://127.0.0.1:8765/dashboard/`

专用服务仍然只绑定本机回环地址，并提供受限的“在文件资源管理器中查看”功能；只允许定位交接目录 `data/` 与 `outputs/` 中的已存在数据文件。

交接方无需按版本号寻找页面；组合研究和单 ETF 周期验证均从统一入口切换。

### 添加新的ETF数据

统一看板中的“数据与回测”接收三类通用CSV输入，数据来源不限：

- `etf_daily`：ETF日行情；
- `option_contracts`：期权合约基础信息；
- `option_daily`：期权日行情。

ETF元数据不是必填项。系统会按六位ETF代码从三张原始表中提取记录，校验字段和共同样本，生成标准化行情与 Black-Scholes Delta 派生表，并将结果隔离保存在 `data/user_submissions/<ETF代码>/`。看板已有ETF无需重新上传，会与新增ETF统一出现在数据包选择器中。用户可在系统自动识别的可用期权范围内设置开始和结束日期，并选择目标Delta、ATM或OTM比例以及覆盖比例。现有ETF和新增ETF使用同一套动态回测与周期证据生成链路。

页面采用项目通用字段约定，并兼容现有原始数据中的常见列名。系统只校验字段、数据类型、关联关系和共同样本，不认证文件的外部来源。新增数据只有通过ETF行情、相关期权合约、期权日行情、DTE20～45认购合约、有效Delta、至少12个可闭合月度周期和至少12个可实际选出期权的月度周期检查后，才标记为“完整研究可用”。

最终包提供五只逐交易日完整覆盖的手动上传样本：`510050、510300、159919、159915、159922`，位于 `data/sample_uploads/five_etf_daily/`。前三只样本区间为2021-01-04至2026-06-03，后两只自期权上市后的2022-09-19开始；五券共同区间为2022-09-19至2026-06-03。每个目录中的三张CSV可以直接在“数据与回测”页面选择。

每次运行都会生成复利净值、回撤、逐期持仓与期权选择账本、固定名义本金现金流、滚动12期现金流、市场情景归因和计算审计。点击“确认更新看板”后，结果写入 `outputs/user_backtests/published.json`，并进入“单ETF周期验证”的ETF选择器；同代码展示最近一次确认的自选区间结果，其他ETF结果不会被覆盖。

“单ETF周期验证”主页也可直接运行上述自选回测，新结果会当场替换整页周期现金流、账本、事后诊断、上涨让渡、路径、市场情景和择时分析。“组合研究”中的“自选组合”允许2至8只ETF分别设置权重、虚值规则和覆盖率，在共同可用的月度周期上按月末固定权重再平衡，并在周期内使用ETF与期权日收盘逐日盯市。缺失期权报价时沿用最近收盘，结果页会披露每条策略腿的精确报价覆盖率；月末MTM必须与原周期结算收益对账。该口径与原静态日频组合主线分开展示。

如需从 AkShare 生成一组通用CSV，可使用：

```powershell
python scripts\collect_akshare_etf_inputs.py --symbol 588080 --start-date 20240501 --end-date 20250630 --output-dir .runtime\akshare_588080_input
```

该采集程序目前面向上交所ETF期权，只适用于具有真实上市ETF期权的标的。没有对应ETF期权的ETF会停止并报告缺少有效合约，不会用股指期权或模拟合约替代。AkShare历史期权日行情不提供成交额和持仓量时，这两列保留为空值；回测使用收盘价并沿用项目的假设价差成本。

## 交接打包

交接前先运行统一验收：

```powershell
.\scripts\verify_delivery.ps1
```

看板服务运行后，可通过真实上传接口复验五只ETF、五张参数图谱和五券日频组合：

```powershell
python scripts\run_five_etf_acceptance.py --base-url http://127.0.0.1:8765
```

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
