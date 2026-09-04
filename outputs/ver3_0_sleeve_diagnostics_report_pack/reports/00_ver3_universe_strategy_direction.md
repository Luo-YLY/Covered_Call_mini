# ver3.0 Universe Strategy Direction

ver3.0 后续不再只有单一 universe。主线组合层和短样本扩展必须分开，不能因为 588000 的期权数据较晚而拖短主线 Step B / Step B+ 的共同样本。

## 1. Main Growth-Diversified Universe

`510300 + 510500 + 159915`

- `510300`：大盘核心 / positive carry covered-call candidate。
- `510500`：中盘弹性 / pure ETF growth-diversification sleeve。它不是 covered-call 主力，但仍有 growth-diversification 价值。
- `159915`：创业板成长弹性 / defensive overlay candidate。

这是主线 Step B / Step B+ 的默认样本，不加入 588000。

## 2. Alternative Defensive-Income Universe

`510300 + 510050 + 159915`

- 用 `510050` 替代 `510500`。
- 目标不是增强风格分散化，而是检验 `510050` 是否能成为第二个大盘备兑核心。
- 需要明确 `510050` 与 `510300` 的高相关性和风格重叠问题。

## 3. Tech-Growth Short-Sample Extension Universe

`510300 + 510050 + 159915 + 588000`

或

`510300 + 510500 + 159915 + 588000`

- `588000` 不纳入主线样本。
- `588000` 只作为 short-sample extension。
- 它的价值在于科创成长 / 硬科技扩展，用来观察是否提供额外收益弹性，或是否适合 defensive covered-call overlay。
- 后续如果进入组合层，应标注为 `short_sample_robustness` 或 `extension_only`。
- 组合层必须区分主线样本与短样本扩展样本。

## 4. Step B 命名建议

- `Main_Growth_Diversified_Universe`
- `Alternative_Defensive_Income_Universe`
- `Tech_Growth_Extension_Universe_A`
- `Tech_Growth_Extension_Universe_B`
