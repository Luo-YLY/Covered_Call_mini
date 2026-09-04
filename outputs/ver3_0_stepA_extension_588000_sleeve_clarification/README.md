# ver3.0 Step A-Extension：588000 Single-ETF Sleeve Clarification

本目录保存 588000 单 ETF covered-call sleeve 画像。它是 short-sample tech-growth extension，不覆盖既有 Step A / 510050 extension 输出，也不运行组合层。

## 运行方式

```powershell
python ver3\scripts\python\run_ver3_0_stepA_extension_588000_sleeve_clarification.py
```

## 样本与结论

| 项目 | 内容 |
| --- | --- |
| 实际回测区间 | 2023-06-30 至 2026-05-27 |
| 推荐 sleeve | `588000_ETF_BuyHold` |
| 分类 | `Growth Extension Sleeve` |
| 定位 | short-sample tech-growth extension only |

Step B-Extension 可读取 `panel/ver3_0_stepA_extension_588000_sleeve_return_panel_wide.csv`，但主线 Step B 不应被 588000 拖短样本。
