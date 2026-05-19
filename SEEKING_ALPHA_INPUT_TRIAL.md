# Seeking Alpha 输入源试验 v1

> 创建日期：2026-05-19
> 状态：阶段一 — 免费版观察期

---

## 0. 目标

验证 Seeking Alpha 免费 / Premium 是否能提高我们的研究效率、Radar 候选质量和反证质量。

本试验不直接产生买入建议，不接自动化爬虫，不绕 paywall，不替代 V6 / Radar / 主仓估值规则。

---

## 1. 核心问题

我们要回答：

- SA 是否能更早发现美股 Radar / V6-B 候选？
- SA 是否能减少我们漏掉的主题扩散标的？
- SA 是否能提供有价值的反方观点，帮助避免追高或 thesis 漂移？
- SA 是否能提高财报后复盘效率？
- SA Premium 是否值得付费？

---

## 2. 使用边界

**允许：**

- 搜索公开网页、标题、摘要、免费文章片段。
- 用户手动提供链接、标题、公开摘要，或少量自己概括的要点。
- 记录 SA 对某只股票的公开评级、观点分歧、财报争议点。
- 把 SA 信号作为 `external_signal_source = SeekingAlpha` 写入 Radar 样本。

**禁止：**

- 自动爬取 Seeking Alpha。
- 绕登录、绕 paywall。
- 复制 Premium / Alpha Picks 付费内容。
- 把付费文章、付费截图或长段原文搬运进本地文档。
- 直接照 SA 推荐买入。
- 把 SA rating 当成 release gate 或交易信号。

---

## 3. 试验周期

**阶段一：免费版观察期，2 周。**

样本数量：至少 10 个美股标的，优先覆盖：

| 标的 | 优先级 |
|---|---|
| `AAOI` | 高 |
| `COHR` | 高 |
| `WDC` | 高 |
| `AMBA` | 高 |
| `CEVA` | 高 |
| `LITE` | 高 |
| `MRVL` | 高 |
| `MU` | 高 |
| `ANET` | 高 |
| `TSM` | 高 |
| `PDD` | 高 |
| `ADBE` | 高 |
| `NVDA` | 高 |

**阶段二：** 如果免费版有明显价值，再试 Premium 1 个月或最短可取消方案。

---

## 4. 记录字段

记录文件：

```
backtest_results/external_signal_trials/seeking_alpha_trial.csv
```

字段说明：

| 字段 | 含义 |
|---|---|
| `date` | 记录日期 |
| `ticker` | 股票代码 |
| `source_type` | Free / Premium / UserProvided |
| `sa_signal_type` | Bullish / Bearish / QuantRating / EarningsPreview / EarningsReview / News / CommentDivergence |
| `sa_summary` | 50字以内摘要，不复制长文 |
| `our_system` | 美股Radar / V6-B / 主仓估值 / 反证 |
| `our_action` | Ignore / Watch / AddToRadarReview / AddToContrarianReview / EarningsReviewInput |
| `reason` | 为什么采纳或忽略 |
| `price_at_signal` | 当时价格 |
| `followup_7d` | 7日后表现 |
| `followup_30d` | 30日后表现 |
| `quality_score` | 1-5 |
| `notes` | 备注 |

---

## 5. 评分规则

### 5.1 候选发现价值

| 分数 | 标准 |
|---|---|
| 5 | SA 提前发现我们尚未覆盖但后续验证有效的高质量候选 |
| 4 | SA 强化了已有 Radar 候选，并提供新证据 |
| 3 | 信息有用但不改变判断 |
| 2 | 信息普通，基本是公开共识 |
| 1 | 噪音、标题党、滞后或误导 |

### 5.2 反证价值

| 分数 | 标准 |
|---|---|
| 5 | 明确指出我们忽略的关键风险，避免错误交易 |
| 4 | 提供有效反方框架 |
| 3 | 提醒了已知风险 |
| 2 | 泛泛而谈 |
| 1 | 没有实质反证 |

---

## 6. 接入流程

每次看到 SA 信号：

1. 记录 ticker 和摘要。
2. 判断它属于：候选发现 / 反证 / 财报复盘 / 情绪噪音
3. **不直接交易。**
4. 若有价值，进入：
   - 美股 Radar 复盘
   - V6-B universe review
   - 主仓估值反证
   - earnings review
5. 7日和30日后补结果。

---

## 7. 付费判断标准

只有满足以下任意两条，才考虑 Premium：

- 免费版连续 2 周产生 ≥ 5 条质量分 ≥ 4 的有效信号。
- 至少 2 条信号进入美股 Radar / V6-B 正式复盘。
- 至少 1 条反证帮助我们避免一次明显错误交易。
- 财报复盘效率明显提升。
- 它提供的信息我们从 Futu / IR / SEC / X Radar 很难替代。

**不付费条件：**

- 大多数信息是滞后共识。
- 信号质量低于 X Radar / Futu / 官方财报。
- 容易诱导我们追高。
- 不能形成可记录样本。
- 主要价值只是"看别人推荐股票"。

---

## 8. 成功定义

Seeking Alpha 对我们有效，不等于它推荐的股票涨了。

**有效定义：**

- 提高候选覆盖率。
- 提高反证质量。
- 提高财报复盘速度。
- 减少漏网机会。
- 不破坏仓位纪律。
- 不诱导规则外交易。

---

## 9. 试验结论模板

```markdown
# Seeking Alpha 输入源试验结论 — YYYY-MM-DD

## 样本统计
- 总样本数：
- 有效信号数：
- 质量分 ≥4：
- 进入 Radar / V6-B：
- 进入反证复盘：
- 明确噪音：

## 结论
- 是否继续免费版：
- 是否试 Premium：
- 是否接入 Daily Board：
- 是否进入美股 Radar SOP：

## 关键案例
| ticker | SA信号 | 我们动作 | 结果 | 评分 |
|---|---|---|---|---|

## 最终判断
Free / Premium / 不用
```

---

## 10. 当前结论

当前只进入免费版观察期。

**预期 alpha 贡献（测算）：**

| 使用方式 | 预期年化贡献 |
|---|---|
| 免费版 | 0%-0.5% |
| Premium | 0.5%-1.5% |
| Premium + 严格样本审计 | 1%-2% 潜力 |

Seeking Alpha 是外部输入源，不是交易系统。

---

> **一句话边界**：`Seeking Alpha` 当前处于外部输入源试验，不是交易信号，不自动化爬取，不绕 paywall；只用于美股 Radar / V6-B / 主仓反证的样本记录。
