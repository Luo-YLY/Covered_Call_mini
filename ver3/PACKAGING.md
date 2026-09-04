# ver3 打包说明

ver3 已并入项目级交接流程，不再单独复制历史 ver2/multi-asset 输出构建 standalone 目录。

从仓库根目录运行：

```powershell
.\scripts\package_project_release.ps1 -Profile Source -ReleaseTag YYYYMMDD
.\scripts\package_project_release.ps1 -Profile Demo -ReleaseTag YYYYMMDD
.\scripts\package_project_release.ps1 -Profile Inputs -ReleaseTag YYYYMMDD
```

- `source` 包含 ver3/ver4、公共源码、冻结兼容引擎、测试与文档。
- `demo` 额外包含 ver3/ver4 看板数据、精选结果和汇报材料。
- `inputs` 包含主线运行所需的冻结 ETF/期权数据，不包含访问凭据。

每个包都生成 Git 快照、逐文件 SHA-256 索引和 ZIP 哈希。验收与排除规则见 `../docs/GIT_AND_RELEASE_GUIDE.md`。
