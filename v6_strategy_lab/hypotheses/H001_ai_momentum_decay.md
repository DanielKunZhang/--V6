# H001: AI Mega Momentum 是否正在衰退？

- Status: proposed
- Created: 2026-05-06
- Cadence: monthly

## 假设

V6-A 当前风险池高度依赖 AI / mega cap / 科技动量。如果 AI 主线动量衰退，而其他行业动量增强，V6-A 可能需要加入新的风险池或降低 AI 暴露。

## 可验证问题

- AI 相关资产的 3/6/12 个月动量是否低于非 AI 动量资产？
- V6-A 最近收益是否主要来自少数 AI 资产？
- 若排除 AI 主线，是否仍能保持 OOS Sharpe？

## 实验设计

- 构造 AI-heavy 风险池 vs non-AI momentum 风险池。
- 跑同样 regime filter 和防守池。
- 对比 Full/OOS/recent/rolling/black swan。

## 通过标准

- non-AI 或 mixed pool 的 OOS Sharpe 不低于 V6-A。
- MaxDD 不明显恶化。
- 最近两年收益来源更分散。

## 当前结论

未测试。
