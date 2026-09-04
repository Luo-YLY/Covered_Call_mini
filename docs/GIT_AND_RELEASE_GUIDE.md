# Git 仓库与项目交付规范

## 1. 当前主线

当前项目的持续维护主线包括：

- 根目录公共研究代码：`src/`、`scripts/`、`tests/`、`configs/`。
- 仍被当前流程依赖的冻结兼容层：`ver2_downside_protection/`。
- 内部研究实现：`ver3/` 负责组合研究，`ver4/` 负责单 ETF 周期验证；版本编号只用于技术追溯。
- 对外交付入口：`dashboard/`，统一承载组合研究、周期验证和交接说明。
- 证据层：经过筛选的 `outputs/ver3_*`、`outputs/ver4_*` 结果，目录名保留历史编号以维持可复现性。

`covered_call_mini_ver02/` 至 `covered_call_mini_ver1_5/`、旧 layer/multi-asset 目录及旧展示结果已在 2026-09-04 移出主线，保存在本地 Git 忽略目录 `dist/legacy_archive_20260904/`。它们不进入主线提交和交接包。

`ver2_downside_protection/` 中的配置与回测引擎仍被内部研究实现直接调用，因此暂时保留。它是冻结兼容实现，不是对外交付版本；迁移必须以测试和数值对照为门槛。

## 2. Git 边界

应该进入 Git：

- 可审阅的源码、测试、配置模板和研究说明。
- 小型、能说明研究结论或审计状态的 manifest、summary、report、audit 文件。
- 看板页面源码。

不应该进入 Git：

- `config/*.txt`、`.env`、令牌、密码、凭据和本机接口配置。
- `.runtime/`、`.tmp/`、Codex 调试目录、Python 缓存和 Office 临时目录。
- 大型原始行情、可再生逐日明细以及临时导出目录。
- `dist/` 下的发布目录、ZIP 和哈希旁车文件。

## 3. 建议提交顺序

主线收口或后续迭代时，不要把 `dist/`、大型输出和本机配置混入提交。建议按以下顺序拆分提交：

1. 源码与测试：公共引擎、冻结兼容层、组合研究与周期验证内部实现。
2. 研究配置与说明：`configs/`、README、方法文档和数据字典。
3. 小型审计与展示结果：manifest、summary、report、dashboard 页面。
4. 单独审阅现有已暂存的根目录结果更新，确认删除的旧图是否确实由新图替代。

每一步先运行 `git diff --cached --check`，再执行对应测试。不要在同一提交中混合源码修复、批量 CSV 重算、图片替换和仓库清理。

## 4. 打包

在仓库根目录运行：

```powershell
.\scripts\package_project_release.ps1 -Profile Final -ReleaseTag YYYYMMDD
```

正式交接生成一个完整包：

- `final`：源码、测试、统一看板、精选报告、必要图表和冻结输入数据。

确需拆分传输时，可单独生成：

- `source`：源码、测试、配置和文档；不含原始行情和研究输出。
- `demo`：在源码包基础上加入统一看板、精选研究结果和汇报材料。
- `inputs`：主线运行所需的冻结 ETF/期权输入，不含令牌、密码或接口配置。

每个包都包含：

- `RELEASE_README.md`：范围与限制。
- `GIT_SNAPSHOT.txt`：打包时的分支、提交和工作区状态。
- `FILE_INDEX.csv`：相对路径、字节数和 SHA-256。
- ZIP 文件及相邻的 `.sha256` 文件。

正式交接优先使用单一 `final` 包，避免接收方遗漏拆分文件。正式跨机器实验仍应核对 Python 环境、复跑验收，并且不得把访问凭据装入压缩包。

## 5. 发布前最低检查

- 最终交接包能够正常解压。
- ZIP 哈希与 `.sha256` 文件一致。
- 包内统一看板、两个内部研究页面及其 JavaScript 数据包均存在。
- 包内不存在 `.env`、token、secret、password、credential 命名的文件。
- Git 快照明确标注打包是否来自脏工作区；脏工作区包不能冒充某个提交的可重建发布版。
