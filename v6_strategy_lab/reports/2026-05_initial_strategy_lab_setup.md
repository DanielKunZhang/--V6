# V6 Strategy Lab 初始设置报告

- Date: 2026-05-06
- Status: initialized

## 已完成

- 建立 V6 Strategy Lab 目录。
- 明确 V6-A 是当前主策略。
- 建立每月 challenger 假设机制。
- 建立季度 revalidation 机制。
- 建立第一版 challenger scorecard。

## 当前 Baseline

`V6-A ATTACK_EQUAL_REPLAY`

- Full ann: 29.80%
- OOS ann: 36.43%
- Full max DD: -21.13%
- OOS Sharpe: 1.18
- Rolling 3y worst ann: 7.20%
- Rolling 5y worst ann: 10.64%
- min equity: 94.41%

## 第一批 Hypotheses

1. H001: AI Mega Momentum 是否正在衰退？
2. H002: BIL / GLD 防守池是否仍然最优？
3. H003: 是否加入非 AI 动量资产？
4. H004: 是否需要更严格的 regime filter？
5. H005: 等权 vs 逆波动权重，谁更稳定？

## 下一步建议

优先做 H005，因为它已经有 robustness 阶段的接近结果，最容易转成 V6-B challenger。

其次做 H002，验证防守池是否可以降低 2024/2026 回撤。
