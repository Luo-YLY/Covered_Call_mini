# ver3 Data

这个目录只放 ver3 专属小型输入清单或数据说明。

不要把原始行情、期权日频大表或可再生中间结果复制进来。当前真实数据仍从仓库根目录读取：

```text
..\data\
..\outputs\ver3_*\
```

当前主线不得再把早期 multi-asset 或 ver2 输出作为运行输入。`ver2_downside_protection/` 仅保留为冻结兼容引擎；真实输入边界仍是根目录 `data/raw/`、`data/source/delta_enriched_options.csv` 和明确记录的 ver3 上游结果。

510050 的 ver3.0 extension 还需要两份已验收的冻结迁移输入：

```text
..\data\frozen_inputs\ver3_0_510050\ver2_1_daily_mtm.csv
..\data\frozen_inputs\ver3_0_510050\ver2_1_periods_with_regime.csv
```

它们只进入 `inputs` 交接包，不进入 Git 主线。
