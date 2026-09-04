# ver3.0 看板输出索引

生成方式：

```powershell
python ver3\scripts\python\build_ver3_dashboard_data.py
```

页面入口：

```text
C:\Users\WIN11\Desktop\CCFund\ETF备兑策略设计\covered_call_mini\ver3\dashboard\index.html
```

数据包：

```text
C:\Users\WIN11\Desktop\CCFund\ETF备兑策略设计\covered_call_mini\outputs\ver3_0_dashboard_data\ver3_dashboard_data.js
```

说明：`ver3/dashboard/` 保存轻量静态页面，真实数据包保存到根目录 `outputs/`，避免把大型可再生输出塞进 `ver3/outputs/`。
