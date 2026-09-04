# Git 仓库与项目交付规范

## 1. 当前主线

当前项目的持续维护主线包括：

- 根目录公共研究代码：`src/`、`scripts/`、`tests/`、`configs/`。
- 仍被当前流程依赖的冻结兼容层：`ver2_downside_protection/`。
- 当前实验层：`ver3/`、`ver4/`。
- 展示层：`ver3/dashboard/`、`ver4/dashboard/` 以及经过筛选的 `outputs/ver3_*`、`outputs/ver4_*` 结果。

`covered_call_mini_ver02/` 至 `covered_call_mini_ver1_5/`、旧 layer/multi-asset 目录及旧展示结果已在 2026-09-04 移出主线，保存在本地 Git 忽略目录 `dist/legacy_archive_20260904/`。它们不进入主线提交和交接包。

`ver2_downside_protection/` 中的配置与回测引擎仍被 ver3/ver4 直接调用，因此暂时保留。它是冻结兼容实现，不是当前研究版本；迁移必须以测试和数值对照为门槛。

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

1. 源码与测试：公共引擎、冻结兼容层、ver3、ver4。
2. 研究配置与说明：`configs/`、README、方法文档和数据字典。
3. 小型审计与展示结果：manifest、summary、report、dashboard 页面。
4. 单独审阅现有已暂存的根目录结果更新，确认删除的旧图是否确实由新图替代。

每一步先运行 `git diff --cached --check`，再执行对应测试。不要在同一提交中混合源码修复、批量 CSV 重算、图片替换和仓库清理。

## 4. 打包

在仓库根目录运行：

```powershell
.\scripts\package_project_release.ps1
```

默认生成三套包：

- `source`：源码、测试、配置和文档；不含原始行情和研究输出。
- `demo`：在源码包基础上加入 ver3/ver4 看板、最新 ver3.1 摘要、ver4 汇总报告和汇报材料。
- `inputs`：主线运行所需的冻结 ETF/期权输入，不含令牌、密码或接口配置。

每套包都包含：

- `RELEASE_README.md`：范围与限制。
- `GIT_SNAPSHOT.txt`：打包时的分支、提交和工作区状态。
- `FILE_INDEX.csv`：相对路径、字节数和 SHA-256。
- ZIP 文件及相邻的 `.sha256` 文件。

`source`、`demo` 与 `inputs` 应作为同一发布组交接。正式跨机器实验还应冻结 Python 环境并复跑验收，且不得把访问凭据装入压缩包。

## 5. 发布前最低检查

- 源码包和演示包能够正常解压。
- ZIP 哈希与 `.sha256` 文件一致。
- 演示包内两个看板 HTML 及其 JavaScript 数据包均存在。
- 包内不存在 `.env`、token、secret、password、credential 命名的文件。
- Git 快照明确标注打包是否来自脏工作区；脏工作区包不能冒充某个提交的可重建发布版。
