# H002: BIL / GLD 防守池是否仍然最优？

- Status: proposed
- Created: 2026-05-06
- Cadence: monthly / quarterly

## 假设

V6-A 防守池目前包含 BIL / GLD / CASH。不同利率、通胀、风险偏好环境下，防守资产可能发生变化。

## 可验证问题

- 风险关闭阶段，BIL / GLD / CASH 哪个贡献最大？
- 加入 TLT、IEF、SHY、UUP、DBC 是否改善风险关闭阶段表现？
- GLD 在 2024/2026 回撤窗口是否真起到防守作用？

## 实验设计

- 固定风险池，替换防守池。
- 保持交易成本和 rebalance 规则一致。
- 对比危机窗口和 rolling worst。

## 通过标准

- 防守池替换后，Full/OOS MaxDD 改善。
- OOS ann 不显著下降。
- 黑天鹅窗口更稳。

## 当前结论

未测试。
