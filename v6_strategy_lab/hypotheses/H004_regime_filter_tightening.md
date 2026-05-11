# H004: 是否需要更严格的 regime filter？

- Status: proposed
- Created: 2026-05-06
- Cadence: monthly / quarterly

## 假设

V6-A 的主要风险来自动量退潮时防守切换不够快。更严格的 regime filter 可能降低回撤，但可能牺牲收益。

## 可验证问题

- 2024 最大回撤和 2026 YTD 回撤是否来自 regime filter 过慢？
- 加入更短周期市场动量、波动率、drawdown stop 是否改善？
- 防守过早是否显著降低收益？

## 实验设计

- 调整 market_ma、market_mom、hv_cap、dd_stop、dd_soft。
- 做参数邻域测试。
- 对比收益损失 vs 回撤改善。

## 通过标准

- MaxDD 明显改善。
- Full/OOS ann 下降不超过可接受范围。
- rolling worst 明显改善。

## 当前结论

未测试。
