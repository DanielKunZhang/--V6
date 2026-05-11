# V6 Strategy Lab

- Status: active
- Created: 2026-05-06
- Scope: V6 主策略的持续研究、挑战、复盘、升级和淘汰机制。

## 一句话结论

V6 Strategy Lab 的目标不是证明 V6-A 永远正确，而是建立一个小型量化基金式流程：持续提出策略假设、验证 challenger、监控主策略、在失效前降权或替换。

## 当前主策略

- 主策略：`V6-A ATTACK_EQUAL_REPLAY`
- 策略属性：美股高进攻动量 + 防守切换
- 当前阶段：`SIM_FIRST_CLOSED_LOOP_ACTIVE`
- 当前定位：`$5,000` V6-A 已在 Futu SIM 通过 managed state 完成下单、成交、reconciliation 闭环；真实小额 pilot 仍需人工明确发起

## V6 长期研发方向

V6 的长期方向不是把一个策略越改越复杂，而是像小型量化基金一样：底层 engine 慢变，universe 动态更新，多个 sleeve 独立验证后再由 allocator 做组合层风控。

```text
V6 Engine = 固定底层规则：经典动量 / 相对强弱 / risk-on risk-off / 波动率控制 / 回撤刹车
V6 Universe = 总候选池：V6-A Core Pool + V6-B Dynamic Pool + Defensive Pool
V6-A Core Pool = 低频更新的 AI mega / mega tech 核心池，当前 baseline
V6-B Dynamic Pool = 动态候选池生成与验证机制，目标是成为 V6 universe refresh engine
V6-C Pool = ETF / 行业 / 全市场 meta-rotation，未来 challenger
Allocator = 风控与资金分配器，根据近期表现、相关性、回撤、regime 分配 Core / Dynamic / Defensive 权重
```

研发路线：

1. `阶段 0：V6-A SIM-first 闭环`：先保证 V6-A baseline 的目标仓位、下单、退出、reconciliation 和 managed state 都能在模拟盘稳定运行。
2. `阶段 1：V6-B 单独回测`：只验证 Radar 动态池能不能赚钱，不能污染 V6-A baseline。
3. `阶段 2：V6-A vs V6-B 对比`：比较收益、回撤、Sharpe、OOS、rolling、黑天鹅、换手、可交易性。
4. `阶段 3：V6-A + V6-B 组合`：测试 `70/30`、`50/50`、动态权重等组合。
5. `阶段 4：V6-B 稳定贡献后升级`：只有通过 deterministic replay、release gate、live preview 和模拟盘后，才允许进入 V6 资源池优化层。

关键原则：

- `Engine Core` 必须经典、简单、可解释，不能因为 1-2 个月表现差就改。
- `Engine Parameters` 可以季度/半年做 challenger，但不能追着最近行情调参。
- Alpha 主要来自正确调整 universe，而不是过度优化 MACD/均线等短期参数。
- `V6-B` 不是整个 V6 Universe；它是动态候选池来源层，负责给 V6 Universe 提供新标的。
- Radar 是 `Research Input`，不是前台持仓层；V6-B 是动态 universe generator，最终下单仍由 V6 Engine + Allocator 决定。
- 任何新增 universe 都要证明增量收益，而不是因为最近涨过就加入历史回测。

## V6 调整治理：自动 vs 人工

V6 不追求“全自动频繁自我优化”。当前采用 `定期提醒 + 人工发起 + 证据晋级` 的治理方式。

| 组件 | 调整频率 | 自动化程度 | 规则 |
| --- | --- | --- | --- |
| `V6 Engine Core` | 半年或重大 regime 变化才考虑 | 不自动调整 | 只允许用 challenger 报告晋级，不能因短期表现差直接改生产规则 |
| `V6 Engine Parameters` | 季度复核 | 半自动研究，人工确认 | 可测试动量窗口、趋势窗口、再平衡频率、回撤阈值、top N，但必须走 OOS / rolling / black swan / robustness |
| `V6-A Core Pool` | 季度/半年低频复核 | 半自动扫描，人工确认 | 类似指数成分股维护；mega 也会变，但不能月度追热点替换 |
| `V6-B Dynamic Pool` | 周度观察，月度正式更新 | 半自动生成候选，人工确认入池 | 用 Radar、漏网复盘、主题扩散、预期上修和动量确认生成 point-in-time universe |
| `Allocator` | 周/月复核 | 先规则化，后续可半自动 | 作为风控层决定 Core / Dynamic / Defensive 权重，不是收益追逐器 |

当前执行口径：

- 每周邮件提醒：V6-A 状态、V6-B live-forward、是否触发异常、是否需要用户发起复盘。
- 每月邮件提醒：是否需要更新 V6-B Dynamic Pool，是否需要做 Missing Opportunity Review。
- 每季度邮件提醒：是否进入 Engine / Core Pool / Allocator revalidation。
- 任何 production 级调整，都必须先写入 `V6_STRATEGY_LAB.md`、AI Wiki 系统卡、Overview，再进入执行。
- 2026-05-11 起，V6-B SIM 暂停扩张；优先把 V6-A SIM-first 闭环跑稳定，V6-B 回到回测与动态 universe 生成器研发。

## 邮件报告要求

V6 需要像 V3 一样有定期邮件摘要，但邮件内容应偏“状态与提醒”，不直接自动触发真实交易。

当前已落地脚本：

```bash
python3 v6_reporting.py --period weekly
```

配置文件：

```text
v6_strategy_lab/configs/v6_reporting_policy_v1.json
```

输出目录：

```text
backtest_results/v6_reporting/
```

邮件默认关闭；只有显式传入 `--send-email` 才会尝试发送。

发送逻辑：

1. 优先复用 V3 的 `notifier.EmailNotifier`，读取本地 `.ic_env.local` 中已有的邮箱授权配置，默认收件人为 `quanyi_zk@163.com`。
2. 如果 V3 notifier 不可用，再 fallback 到 `V6_EMAIL_*` 环境变量。

邮件最小字段：

- V6-A 当前信号、目标持仓、实际持仓、偏离、回撤、异常订单
- V6-B 当前 universe、入池/出池候选、live-forward 表现、是否缺数据
- Allocator 当前建议权重：Core / Dynamic / Defensive
- 本周是否需要人工动作：`不动 / 复盘 / 刷新数据 / 重新 gate / 扩容讨论`
- 下一次固定复盘日期

邮件结论必须写成：

```text
本周动作：不动 / 需要用户确认 / 禁止实盘
```

不能把邮件做成自动下单触发器。

## 2026-05-10 今日已可落地事项

在 Futu 历史 K 线额度刷新前，今天先完成不消耗行情额度的工程底座：

1. `point-in-time universe` 格式固定
   - 配置：`v6_strategy_lab/configs/v6b_point_in_time_universe_seed_20260510.json`
   - 审计：`python3 v6b_universe_audit.py --config v6_strategy_lab/configs/v6b_point_in_time_universe_seed_20260510.json`
   - 当前种子池 9 个 active tickers，覆盖 `core_reacceleration / bottleneck_diffusion / turnaround_momentum` 三条轨。

2. `Allocator v1` 规则固定
   - 策略：`v6_strategy_lab/configs/v6_allocator_policy_v1.json`
   - 执行：`python3 v6_allocator.py --metrics <sleeve_metrics.csv>`
   - 当前默认逻辑：V6-B 没有通过 point-in-time / OOS / replay 前，权重固定为 `V6-A 100% / V6-B 0% / V6-C 0%`。

3. `V6-B release order` 固定
   - 先做 V6-B standalone。
   - 再做 V6-A vs V6-B。
   - 再做 V6-A + V6-B 组合。
   - 最后才允许 Allocator 给 V6-B 权重。

4. `V6-B 买入/选票/仓位/退出/评分系统` 固定
   - 策略：`v6_strategy_lab/configs/v6b_entry_sizing_policy_v1.json`
   - 评分覆盖：主题强度、基本面验证、预期修正、价格动量、流动性、拥挤/估值风险、反证清晰度、组合适配度。
   - 执行：`python3 v6b_score_universe.py --tag <tag>`
   - 当前输出：`v6_strategy_lab/scorecards/v6b_scorecard_20260510_seed.md`
   - 评分只决定研究排序，不是买入信号；买入仍需 V6-B standalone、V6-A 对比、Allocator 非零权重、risk-on 和 tradability 通过。

5. `评分 -> 回测配置` 接口固定
   - 执行：`python3 v6b_build_universe_config.py --tag 20260510_seed --scorecard v6_strategy_lab/scorecards/v6b_scorecard_20260510_seed.json`
   - 输出：`v6_strategy_lab/configs/generated/v6b_generated_universe_20260510_seed.json`
   - 当前生成四档：`v6a_base_only`、`v6b_eligible_only`、`v6b_watch_plus`、`v6b_full_active`。
   - 这一步保证未来回测不是手工改池子，而是按 point-in-time universe 和 scorecard 自动生成。

6. `cache-only probe` 已验证缺数据边界
   - 执行：`python3 v6b_radar_momentum_challenger.py --config v6_strategy_lab/configs/generated/v6b_generated_universe_20260510_seed.json --cache-only --tag generated_seed_probe`
   - 当前只有 `v6a_base_only` 可跑；V6-B variants 因 AMD、TSM、MU、ANET、WDC、INTC、AMKR、AMBA、CEVA 等缺历史缓存不能得出结论。
   - 输出：`backtest_results/v6b_radar_momentum/v6b_report_generated_seed_probe.md`

7. `验证分层` 固定为两轨
   - 轨道 A：`live-forward`，用当前 Radar 池在模拟盘持续记录，先跑至少 1 个月，工程稳定后再考虑小额 pilot。
   - 轨道 B：`synthetic historical Radar generator`，只用于历史回测，不能把今天才发现的赢家机械回填到过去。
   - 这两条轨道必须分开记账、分开报告、分开结论。

今天不能做的事：

- 不能消耗 Futu 历史 K 线额度继续拉全量数据。
- 不能宣称 V6-B 有收益贡献。
- 不能把 Radar 当前种子池直接放进历史回测并使用 2012-2026 全周期表现，因为这会形成未来函数。
- 不能把当前 scorecard 当作交易清单，因为价格动量、流动性和拥挤度还没有接入最新真实数据。
- 不能把 `generated_seed_probe` 中的 V6-A baseline 结果当作 V6-B 结果；它只是证明脚本链路和缺数据报告正常。
- 不能用当前 live Radar 池直接做历史回测；历史回测必须走 synthetic Radar generator。

## 目录结构

```text
v6_strategy_lab/
  README.md
  configs/
  hypotheses/
  reports/
  scorecards/
```

## 工作节奏

### 每日

- 检查订单、仓位、OpenD、reconciliation 状态
- 不做策略层判断，除非触发异常

### 每周

- 复盘 V6-A 本周表现
- 检查理论仓位 vs 实际仓位
- 检查是否出现未成交、部分成交、异常偏离
- 判断是否继续模拟、暂停、或准备小额 pilot

### 每月

- 提出 3-5 个 challenger 假设
- 至少完成 1 个可回测 challenger
- 对比 V6-A 与 challenger 的 OOS、回撤、Sharpe、黑天鹅窗口

### 每季度

- 完整 revalidation：
  - deterministic replay
  - release gate
  - robustness / parameter neighbor
  - black swan windows
  - rolling 3y/5y
  - live tradability
- 决定是否维持、降权、暂停或替换 V6-A

## Challenger 提升规则

Challenger 不能因为某个单点指标好看就替代 V6-A。至少要满足：

1. OOS Sharpe 不低于 V6-A
2. Full/OOS MaxDD 不明显恶化
3. Rolling 3y worst ann 不低于 V6-A，或有明确风险收益补偿
4. 黑天鹅窗口不比 V6-A 明显差
5. 最近两年表现不能靠单一月份贡献
6. 参数邻域稳定
7. 可交易性不差于 V6-A
8. 若相关性很高，必须明显优于 V6-A；若相关性较低，可作为组合增强候选

## 降权 / 暂停规则

V6-A 出现以下情况时，进入降权或暂停讨论：

- 实盘/模拟盘回撤超过历史正常区间
- 连续多次信号切换失效
- 理论信号和实际成交长期偏离
- 滑点、成交、最小下单单位导致真实结果明显差于 preview
- rolling 3y / rolling 5y 最新重算明显恶化
- 防守资产失效，风险关闭时仍出现异常亏损

## 当前第一批假设

详见：

- `v6_strategy_lab/hypotheses/H001_ai_momentum_decay.md`
- `v6_strategy_lab/hypotheses/H002_defensive_pool_optimization.md`
- `v6_strategy_lab/hypotheses/H003_non_ai_momentum_expansion.md`
- `v6_strategy_lab/hypotheses/H004_regime_filter_tightening.md`
- `v6_strategy_lab/hypotheses/H005_equal_vs_inverse_vol_weighting.md`
- `v6_strategy_lab/hypotheses/H006_radar_momentum_challenger.md`

## 当前边界

- Strategy Lab 不直接改 V6-A 生产逻辑。
- Strategy Lab 不直接下单。
- 所有 challenger 都必须先 research，再 replay，再 preview，再 sim。
- 任何替换主策略的决定必须有报告证据。
