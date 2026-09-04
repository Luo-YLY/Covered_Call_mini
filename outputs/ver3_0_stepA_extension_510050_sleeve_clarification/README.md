# ver3.0 Step A-Extension：510050 Single-ETF Sleeve Clarification

本目录保存 510050 单 ETF covered-call sleeve 画像。它是 Step A 的扩展，不覆盖既有 `510300/510500/159915` 输出，也不进入组合层。

## 运行方式

```powershell
python ver3\scripts\python\run_ver3_0_stepA_extension_510050_sleeve_clarification.py
```

## 样本与结论

| 项目 | 内容 |
| --- | --- |
| 源数据可用区间 | 2021-01-29 至 2026-05-27 |
| 正式指标区间 | 2022-09-30 至 2026-05-27 |
| 推荐 sleeve | `510050_DTE30_D40_Q70_Hold` |
| 分类 | `Positive Carry Overlay` |
| 510300 相关性判断 | high overlap; limited diversification but usable as second core |

Step B / Step B+ 可把该 panel 作为 alternative universe 的候选输入，但固定权重和组合层指标不在本步骤计算。
