# V6 Stale Data Risk Exit Policy — v1

- 创建日期：2026-05-18
- 状态：设计文档，待工程实现
- 触发背景：2026-05-18 AVGO BUY 预览因 signal_date=2026-05-05（age_days=13 > max=7）被 release gate 阻断。该行为对 BUY 是正确的，但暴露出现有 gate 逻辑对所有订单类型一刀切的问题——旧数据不能阻断刹车。
- 关联文件：`attack_engine_release_gate.py`、`v6a_guarded_runner.py`、`v6_reporting.py`、`morning_brief.py`、`system_health_check.py`

---

## 一、核心原则

**有 K 线时用完整信号；没有 K 线时只允许刹车，不允许踩油门。**

1. **新鲜历史 K 线是进攻动作的前提。** BUY / ADD / ROTATE_IN 必须基于有效信号。信号过期即意味着市场结构未知，此时进攻等于盲目押注。

2. **K 线不足或信号过期时，禁止所有进攻动作。** 不允许降级使用旧 replay 信号作为买入依据，不允许用替代数据源绕过此限制。

3. **风险退出不能完全依赖历史 K 线。** 已有持仓的风险暴露是实时存在的，不随数据可用性消失。无法刷新信号时，系统仍需具备触发风险退出提醒的能力。

4. **旧数据不能让系统进攻，但也不能让系统失去刹车。** 这是本文档的核心约束，所有设计决策均服从于此。

5. **当前阶段一律不自动下单。** 无论何种模式，所有执行动作均须人工确认。

6. **1000 万 RMB 总资产之前不新增付费数据源。** 当前以 Futu OpenD / FutuAPI 为主；EODHD / Tiingo / Polygon / Nasdaq Data Link 等仅作为未来规模升级项。Futu 历史 K 线额度不足时，不用付费源绕过进攻信号 gate，而是进入 STALE_DATA_MODE。

---

## 二、状态定义

### NORMAL_MODE

- 条件：历史 K 线额度充足，`signal_freshness_gate` 检查通过（`signal_age_days ≤ max_allowed`）
- 行为：完整信号体系生效，进攻和防守动作均按正常 gate 逻辑处理

### STALE_DATA_MODE

- 条件：历史 K 线额度不足（Futu 每月限额耗尽），或 `signal_freshness_gate` 检查失败（`signal_age_days > max_allowed`）
- 行为：进攻动作一律阻断；防守动作（风险退出/人工减仓）降级为"生成提醒"模式，须人工确认

### EMERGENCY_REVIEW_MODE

- 条件：已有持仓触发实时风控阈值（如单仓亏损超预设阈值、持仓市值大幅缩水、用户主动标记）
- 行为：只允许减仓/退出操作，不允许任何买入；强制人工确认；当前阶段不允许无人值守自动卖出
- 触发方式：当前版本由用户手动声明，未来版本可接入实时快照自动检测

---

## 三、订单类型分类

| 订单类型 | 方向 | 描述 |
|---|---|---|
| `BUY` | 进攻 | 新建仓，系统首次买入某标的 |
| `ADD` | 进攻 | 加仓，增加现有持仓权重 |
| `ROTATE_IN` | 进攻 | 轮换买入，买入新标的同时减出旧标的 |
| `MODEL_ROTATION_SELL` | 防守/中性 | 策略模型驱动的减仓或换出，非紧急风险触发 |
| `RISK_EXIT_SELL` | 防守 | 风险驱动的减仓或清仓，基于亏损阈值、持仓异常或外部冲击 |
| `MANUAL_RISK_REDUCE` | 防守 | 用户手动判断的减仓，不要求系统信号支持 |

---

## 四、Release Gate 行为矩阵

### NORMAL_MODE（历史 K 线充足，信号新鲜）

| 订单类型 | Gate 行为 |
|---|---|
| `BUY` | 进入正常 gate，通过则允许生成执行卡 |
| `ADD` | 进入正常 gate，通过则允许生成执行卡 |
| `ROTATE_IN` | 进入正常 gate，通过则允许生成执行卡 |
| `MODEL_ROTATION_SELL` | 进入正常 gate，通过则允许生成执行卡 |
| `RISK_EXIT_SELL` | 进入风险 gate（条件更宽松），生成执行卡并提示人工确认 |
| `MANUAL_RISK_REDUCE` | 跳过信号 gate，直接生成执行卡，等待人工确认 |

### STALE_DATA_MODE（K 线不足或信号过期）

| 订单类型 | Gate 行为 |
|---|---|
| `BUY` | **一律阻断**，日报标注"进攻信号过期，已阻断" |
| `ADD` | **一律阻断**，日报标注"进攻信号过期，已阻断" |
| `ROTATE_IN` | **一律阻断**，买入侧阻断；如有配套 SELL 侧，单独评估 |
| `MODEL_ROTATION_SELL` | **默认阻断**，但用户可人工复核并主动确认执行；日报注明需人工判断 |
| `RISK_EXIT_SELL` | **允许**生成"人工确认风险退出提醒"，不自动下单，不使用过期信号作为依据 |
| `MANUAL_RISK_REDUCE` | **允许**生成执行卡，标注为"用户主动风险减仓"，等待确认后人工执行 |

> **设计意图**：进攻型订单的执行依赖对市场结构的判断（趋势、动量、相对强弱），这些判断来自历史 K 线信号。信号过期意味着这些判断已失效，因此进攻必须阻断。防守型订单的执行依据是持仓本身的风险状态，与历史 K 线无直接关联，因此应当保留通道，但仍须人工确认。

### EMERGENCY_REVIEW_MODE（实时风控阈值触发）

| 订单类型 | Gate 行为 |
|---|---|
| `BUY` / `ADD` / `ROTATE_IN` | **硬性阻断，无例外** |
| `MODEL_ROTATION_SELL` | 允许，须人工确认 |
| `RISK_EXIT_SELL` | 允许，须人工确认，优先级 HIGH |
| `MANUAL_RISK_REDUCE` | 允许，须人工确认，优先级 HIGH |

> **当前阶段额外约束**：即使在 EMERGENCY_REVIEW_MODE，所有减仓/退出操作均不允许无人值守自动执行。系统只生成执行卡和高优先级提醒，等待用户在富途客户端手动完成。

---

## 五、风险退出可用数据源

在历史 K 线额度耗尽时，以下数据源**允许**用于支持防守决策：

| 数据源 | 用途 |
|---|---|
| V6 managed state | 确认哪些持仓属于 V6 管理范围，避免误卖主仓 |
| 实时价格 / bid-ask | 通过 Futu 实时快照获取，不依赖历史 K 线额度 |
| 成本价或执行价记录 | 来自 managed state 或 reconciliation 记录 |
| 持仓市值 | 实时快照计算 |
| 预设最大亏损阈值 | 在策略配置或 Central Risk Board 中预先写死 |
| 用户手动输入的风险判断 | MANUAL_RISK_REDUCE 场景，用户主动声明减仓意图 |

以下数据源**不允许**用于触发任何自动交易：

| 禁止使用 | 原因 |
|---|---|
| 过期 replay signal | 信号有效期外的市场结构判断不可信 |
| 未经验证的替代数据（如爬取的非官方行情） | 数据质量无法保证，不能用于真实资金决策 |
| 未达到资产门槛前新增的付费替代数据源 | 当前成本收益不匹配；1000 万 RMB 总资产前不新增订阅 |
| 旧 K 线信号直接降级为新买入依据 | 本质上仍是过期信号，包装形式不改变其失效本质 |

---

## 六、当前阶段执行口径

当前 V6 处于手动 pilot 阶段，工程层尚未实现 order-side-aware gate。在完成第七节的工程改造之前，执行口径如下：

1. **只做报告和提醒，不自动下单，不修改真实持仓。**
2. **信号新鲜度检查（`signal_freshness_gate`）维持现行逻辑**，即对所有订单类型统一检查 `signal_age_days`。
3. **如果系统生成的预览中出现 SELL 类订单被阻断**，需人工判断该 SELL 是否属于 `RISK_EXIT_SELL` 或 `MANUAL_RISK_REDUCE`，若是则手动处理，不等待 K 线额度恢复。
4. **如果触发 RISK_EXIT_SELL**，只生成 Markdown 执行卡，格式如下：

```markdown
## 风险退出提醒 — [日期]

优先级：HIGH
订单类型：RISK_EXIT_SELL
标的：[代码]
持仓来源：V6 managed state
触发原因：[用户声明 / 亏损阈值 / 实时价格异常]

当前持仓：[数量]
成本价：[price]
当前价：[实时快照]
浮亏：[计算值]

建议动作：减仓 [数量] 股，限价单 [参考价]

⚠️ 历史K线信号处于 STALE_DATA_MODE，本提醒仅基于实时价格和持仓记录。
⚠️ 执行前请在富途客户端确认当前市价，不要依赖本卡中的价格作为唯一依据。

用户确认后，在富途客户端手动执行。
```

5. **用户确认后，才允许进入下一步人工执行。**

---

## 七、后续工程改造建议

以下组件需要在未来版本中完成改造，以实现本文档描述的 order-side-aware gate 逻辑：

### `attack_engine_release_gate.py`

- **现状**：对所有订单类型统一检查 `signal_freshness_gate`，信号过期即阻断
- **改造方向**：
  - 读取每个订单的 `order_intent` 字段（`BUY / ADD / ROTATE_IN / MODEL_ROTATION_SELL / RISK_EXIT_SELL / MANUAL_RISK_REDUCE`）
  - 进攻型订单（`BUY / ADD / ROTATE_IN`）维持现行严格 gate
  - 防守型订单（`RISK_EXIT_SELL / MANUAL_RISK_REDUCE`）绕过信号新鲜度检查，进入风险 gate
  - `MODEL_ROTATION_SELL` 在 STALE_DATA_MODE 下输出"需人工复核"标记，不硬性阻断也不自动放行

### `v6a_guarded_runner.py`

- **现状**：统一处理所有订单，不区分订单意图
- **改造方向**：
  - 解析订单的 `order_intent`，路由到不同处理逻辑
  - STALE_DATA_MODE 下跳过进攻型订单，保留防守型订单的执行卡生成
  - 在执行预览中明确标注每个订单的 intent 和当前 gate 状态

### `v6_reporting.py`

- **现状**：日报中不区分"进攻信号过期阻断"和"风险退出提醒"
- **改造方向**：
  - 新增两个独立报告区块：
    - `STALE_DATA_BLOCKED`：列出因信号过期被阻断的进攻型订单
    - `RISK_EXIT_PENDING`：列出待人工确认的风险退出提醒
  - 两个区块的处理优先级不同，不能混在一起

### `morning_brief.py`

- **现状**：今日动作清单未区分风险退出提醒优先级
- **改造方向**：
  - 如果存在待处理的 `RISK_EXIT_SELL` 提醒，放到今日动作清单 **HIGH** 优先级，不得淹没在低优先级任务中
  - 如果处于 STALE_DATA_MODE，在早间邮件顶部加一行警示：`⚠️ V6 当前处于 STALE_DATA_MODE，进攻信号已过期，所有 BUY/ADD 已阻断`

### `system_health_check.py`

- **现状**：检查核心文件存在性，未覆盖 stale data policy
- **改造方向**：
  - 新增检查项：`v6_stale_data_risk_exit_policy_v1.md` 存在
  - 新增检查项：`attack_engine_release_gate.py` 是否已实现 order-side-aware 逻辑（检查函数签名或注释标记）

---

## 八、与当前 AVGO 事件的解释

**事件**：2026-05-18，V6-A plan-only 预览中 `US.AVGO BUY` 被 release gate 阻断。

**阻断原因**：`signal_date = 2026-05-05`，`age_days = 13`，超过 `max_allowed = 7`，`signal_freshness_gate` 返回 FAIL。

**判断**：**此次阻断是正确行为。**

- `AVGO BUY` 是进攻型订单（`order_intent = BUY`）
- 进攻型订单要求信号新鲜，过期信号不能作为买入依据
- 此时历史 K 线额度不足（Futu 月度限额耗尽），信号无法刷新
- 正确行为：阻断 BUY，等待 K 线额度恢复（约 2026-06-01）后重新评估

**注意**：如果未来出现 `AVGO SELL` 类订单，**不能简单套用相同逻辑**。

- 若该 SELL 属于 `MODEL_ROTATION_SELL`：在 STALE_DATA_MODE 下默认阻断，但用户可以人工复核并主动确认
- 若该 SELL 属于 `RISK_EXIT_SELL`：不受信号新鲜度约束，应生成风险退出提醒，由用户决定是否执行
- 若该 SELL 属于 `MANUAL_RISK_REDUCE`：直接生成执行卡，等待用户确认

**当前 AVGO 持仓状态**：managed state 记录 `US.AVGO 2` 股，无风险退出触发条件，无需生成 RISK_EXIT_SELL 提醒。AVGO 目前属于正常持有，等待 K 线额度恢复后正常评估是否继续持有或调仓。

---

## 九、里程碑

| 里程碑 | 条件 | 当前状态 |
|---|---|---|
| M1：设计文档完成 | 本文档 | ✅ 完成 |
| M2：`attack_engine_release_gate.py` 改造 | 实现 order-side-aware gate | 🔲 待实现 |
| M3：`v6a_guarded_runner.py` 改造 | 路由逻辑按 order_intent 分叉 | 🔲 待 M2 |
| M4：`v6_reporting.py` 改造 | 日报区分阻断类型 | 🔲 待 M3 |
| M5：`morning_brief.py` 改造 | 风险退出提醒进入 HIGH 优先级 | 🔲 待 M4 |
| M6：`system_health_check.py` 改造 | 覆盖 stale data policy 检查 | 🔲 待 M1 |

---

> **一句话设计原则**：有 K 线时用完整信号；没有 K 线时只允许刹车，不允许踩油门。
