# 用户提交ETF数据

该目录由统一看板的“添加ETF”功能在本机写入。

每次提交均使用独立目录，保留 Tushare `fund_daily`、`opt_basic`、`opt_daily` 三张原始CSV，以及标准化行情、Delta派生表和 `manifest.json`。ETF元数据不是必填项。

用户提交不会覆盖项目当前主线的 `data/raw/`、`data/source/` 或既有研究输出。除本说明文件外，运行时提交内容默认不纳入 Git。
