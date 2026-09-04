# ver3 实验看板

这是 ver3 当前实验结果的本地静态看板。它不修改旧版 `dashboard/`，也不重新运行回测，只读取当前已经落盘的 ver3 CSV 输出。

## 生成数据

```powershell
python ver3\scripts\python\build_ver3_dashboard_data.py
```

数据包输出到：

```text
outputs\ver3_0_dashboard_data\ver3_dashboard_data.js
```

## 打开方式

直接打开：

```text
ver3\dashboard\index.html
```

也可以在项目根目录启动静态服务：

```powershell
python -m http.server 8765
```

然后访问：

```text
http://localhost:8765/ver3/dashboard/
```

## 当前内容

- 总览：当前主候选、关键指标、NAV 和回撤。
- 单券：步骤 A 与补充实验的策略腿横向对比。
- 固定权重：步骤 B 的备兑精选组合与纯 ETF 基准。
- 前沿：步骤 B+ 的回撤约束夏普前沿和权重结构。
- 稳健性：步骤 C 的稳定性、滚动窗口、事件剔除和成本敏感性。
