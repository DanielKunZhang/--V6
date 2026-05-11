# H005: 等权 vs 逆波动权重，谁更稳定？

- Status: proposed
- Created: 2026-05-06
- Cadence: monthly

## 假设

V6-A 当前主推 `ATTACK_EQUAL_REPLAY`，但 robustness 阶段 `ATTACK_INV_VOL` 表现也接近。逆波动权重可能在回撤控制上更稳。

## 已知信息

第一轮 robustness audit：

- `ATTACK_EQUAL`: full 30.84% / max DD -22.83%
- `ATTACK_INV_VOL`: full 30.60% / max DD -22.22%

deterministic replay 当前主线：

- `ATTACK_EQUAL_REPLAY`: full 29.80% / max DD -21.13%

## 实验设计

- 重新生成 equal vs inverse vol replay。
- 对比 daily holdings、turnover、回撤、rolling 3y、黑天鹅窗口。
- 若 inverse vol 明显更稳，考虑作为 V6-B。

## 通过标准

- OOS Sharpe 不低于 equal。
- MaxDD 更低。
- 近期表现不明显落后。
- 交易复杂度不显著增加。

## 当前结论

优先级高，适合作为第一批 challenger。
