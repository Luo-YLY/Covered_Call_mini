# ver4.0 周期现金流看板

运行新实验后先构建数据包：

```powershell
python ver4\scripts\python\build_ver4_dashboard_data.py
```

从仓库根目录启动静态服务：

```powershell
python -m http.server 8765
```

打开：

```text
http://127.0.0.1:8765/ver4/dashboard/
```

看板只展示固定名义本金、独立结算的周期账本。它不展示复利净值、CAGR 或 Sharpe。
