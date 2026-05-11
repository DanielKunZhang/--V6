# V6 Long-Term Research Roadmap

- Date: 2026-05-10
- Status: active roadmap
- Owner: Dingcle Capital / V6 Strategy Lab

## 一句话结论

V6 的长期方向不是把一个策略越改越复杂，而是建立多个独立 sleeve：先分别验证，再由组合层分配权重。

## 目标架构

```text
V6 Engine = 经典动量 / 相对强弱 / risk-on risk-off / 波动率控制 / 回撤刹车
V6-A Pool = AI Mega 固定核心池
V6-B Pool = Radar 动态机会池
V6-C Pool = ETF / 行业 / 全市场轮动池
Allocator = 根据近期表现、相关性、回撤、regime 分配 V6-A / V6-B / V6-C 权重
```

## 四阶段研发路线

1. 阶段 1：V6-B 单独回测
   只验证 Radar 动态池能不能赚钱，不能污染 V6-A baseline。

2. 阶段 2：V6-A vs V6-B 对比
   比较收益、回撤、Sharpe、OOS、rolling、黑天鹅、换手、相关性和可交易性。

3. 阶段 3：V6-A + V6-B 组合
   测试 70/30、50/50、动态权重等组合，目标是提高组合风险调整收益，而不是单纯提高名义收益。

4. 阶段 4：升级为 V6 资源池优化层
   只有 V6-B 稳定贡献后，才允许进入真实策略预算；必须先通过 deterministic replay、release gate、live preview 和模拟盘。

## 关键防作弊规则

- Radar universe 必须 point-in-time。
- 标的只能从 entry_date 之后参与历史回测。
- 每个标的必须记录 ticker、entry_date、exit_date、source、track、入池理由和反证条件。
- 禁止看完涨幅后倒填入池日期。
- 禁止为了提高回测结果手工删掉失败标的。
- 任何新增 universe 都要证明增量收益，而不是因为最近涨过就加入。
- 当前 live Radar 池只能做 live-forward 验证，不能机械回填到历史。
- 历史验证必须用 synthetic historical Radar generator 重建当时可发现的候选池。

## 当前执行口径

- V6-A 是当前 baseline。
- V6-B 是 challenger，不直接上线。
- Radar 是 Research Input，不再默认作为前台正股仓。
- 右尾期权默认取消，不作为系统常规模块。
- 后续等 Futu 历史 K 线额度刷新后，再补全 V6-B 数据并运行 full backtest。

## 2026-05-10 已落地工程件

- `v6_strategy_lab/configs/v6b_point_in_time_universe_seed_20260510.json`
  固定 V6-B Radar 动态池的 point-in-time schema。
- `v6b_universe_audit.py`
  审计入池/出池日期、source、reason、anti_thesis 和重复 active ticker。
- `v6_strategy_lab/configs/v6_allocator_policy_v1.json`
  固定 V6-A / V6-B / V6-C 第一版分配规则。
- `v6_allocator.py`
  根据 sleeve metrics 输出 allocator weights。
- `v6_strategy_lab/configs/v6_allocator_sample_metrics.csv`
  样例输入；当前会因 V6-B 缺少 point-in-time/OOS/replay 自动输出 `V6-A 100% / V6-B 0% / V6-C 0%`。
- `v6_strategy_lab/configs/v6b_entry_sizing_policy_v1.json`
  固定 V6-B 买入资格、选票、仓位、退出和评分系统。
- `v6b_score_universe.py`
  对 point-in-time Radar universe 做研究评分，生成 scorecard。
- `v6_strategy_lab/scorecards/v6b_scorecard_20260510_seed.md`
  当前种子评分结果；只用于研究排序，不是买入信号。
- `v6b_build_universe_config.py`
  将 point-in-time universe 和 scorecard 转成 backtest-compatible config。
- `v6_strategy_lab/configs/generated/v6b_generated_universe_20260510_seed.json`
  当前 2026-05-10 版本的自动生成回测配置。
- `v6_strategy_lab/reports/2026-05-10_v6b_validation_plan.md`
  固定 V6-B 的 live-forward 与 synthetic historical 双轨验证路线。

## 数据刷新后的下一步

1. 用 Futu 或其他可靠数据源补齐 V6-B tickers 的历史价格。
2. 先启动 live-forward simulation，从 2026-05-10 当前池往后记录，不和历史 synthetic 结果混在一起。
3. 设计 synthetic historical Radar generator，用历史当时可见信号生成候选池。
4. 再跑 V6-B standalone；当前生成配置已经区分 `eligible_only / watch_plus / full_active`，但正式历史检验必须避免把 2026-05-10 才入池的标的回填到更早年份。
5. 输出 V6-A vs V6-B 对比 metrics。
6. 生成 sleeve metrics CSV，交给 `v6_allocator.py`。
7. 如果 allocator 仍给 `0% V6-B`，说明 Radar 动态池还没有证明自己，不进入策略预算。
8. 将真实价格动量、流动性、拥挤度数据接入 `v6b_score_universe.py`，替换当前手动/占位评分。
