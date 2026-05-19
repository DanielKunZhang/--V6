# 2026Q1 Situational Awareness 13F 对美股 Radar 的增益

日期：2026-05-19  
来源：SEC 13F-HR，Situational Awareness LP，报告期 2026-03-31，申报日 2026-05-15 / SEC 页面显示 2026-05-18 生效。

## 一页结论

这份 13F 对我们的美股 Radar 有帮助，但不是“照抄持仓买入”的帮助。它最大的价值是三点：

1. 验证 AI 基础设施主题仍然很集中：数据中心、电力、算力云、矿转算力、存储和半导体制造仍是主线。
2. 揭示一条重要风险信号：它在 Q1 大幅增加半导体和 AI CapEx 龙头的 put 名义暴露，说明专业资金在保留 AI 基建多头的同时，已经明显防范 AI 半导体拥挤交易回撤。
3. 对我们的 Radar 增益应体现在候选池分层、拥挤度惩罚和对冲信号，而不是新增前台大仓。

## Q1 结构

13F 表内价值合计约 136.77 亿美元，42 条记录。按 13F 名义 value 粗分：

| 类型 | 名义 value | 含义 |
|---|---:|---|
| Put | 约 84.59 亿美元 | 主要集中在 SMH、NVDA、ORCL、AVGO、AMD、MU、TSM、ASML |
| Long stock | 约 38.56 亿美元 | 主要集中在 BE、SNDK、CRWV、IREN、CORZ、APLD |
| Call | 约 13.62 亿美元 | 主要集中在 MU、SNDK、TSM、CRWV、BE |

重要限制：13F 期权 value 是底层证券名义价值口径，不等于真实期权权利金，不等于 delta，不等于净多空。因此只能用于判断方向偏好和风险结构，不能当成仓位比例。

## 最大持仓 / 表达

| 标的 | 类型 | 名义 value | Radar 解读 |
|---|---:|---:|---|
| SMH | Put | 20.43 亿美元 | 半导体整体拥挤度对冲信号 |
| NVDA | Put | 15.68 亿美元 | 对 AI 核心龙头回撤风险有明显保护 |
| ORCL | Put | 10.73 亿美元 | AI 云 / CapEx 交易中，对估值和兑现风险防守 |
| AVGO | Put | 10.06 亿美元 | ASIC / networking 龙头拥挤度防守 |
| AMD | Put | 9.69 亿美元 | AI 加速器预期交易防守 |
| BE | Long | 8.79 亿美元 | AI 电力 / 燃料电池 / 数据中心供电主线仍被重仓 |
| SNDK | Long + Call | 约 11.13 亿美元 | 存储 / NAND / 数据增长受益链，Q1 明显增强 |
| MU | Call + Put + Long | 约 10.12 亿美元 | HBM/存储是主线，但用双向期权表达，不能简单解读为裸多 |
| CRWV | Long + Call | 约 6.97 亿美元 | 新 AI 云平台仍是核心观察对象 |
| IREN | Long | 4.01 亿美元 | 矿转算力 / AI data center 仍在主线内 |
| CORZ | Long | 3.89 亿美元 | 数据中心 / 算力基础设施，但较 Q4 略降 |
| APLD | Long | 3.20 亿美元 | Applied Digital 仍被保留并小幅增持 |

## 相比 2025Q4 的关键变化

| 变化 | 解读 |
|---|---|
| 总 13F value 从约 55.17 亿美元升至约 136.77 亿美元 | 主要由大规模 put 名义暴露增加驱动，不应简单理解为权益多头翻倍 |
| Put 从几乎没有变成约 84.59 亿美元 | 对 AI 半导体和 AI CapEx 交易的防守显著增强 |
| Long stock 约 39.14 亿美元降至约 38.56 亿美元 | 现货多头总量基本稳定，不是无脑扩多 |
| Call 从约 15.94 亿美元降至约 13.62 亿美元 | 右尾表达仍有，但比 Q4 略收敛 |
| 新增 / 强化：AMD、ASML、AVGO、MU、NVDA、ORCL、SMH、TSM 的 put | 核心 AI 链条进入“主线仍对，但拥挤度必须管理”的阶段 |
| 退出 / 未见：COHR、LITE、CIFR、HUT、TSEM、EQT、KRC、LBRT | 部分二阶扩散票和能源/地产类表达被清理，不宜只因曾在旧 Radar 中出现就继续保留高优先级 |

## 对美股 Radar 的具体增益

### 1. 新增一个机构拥挤度/对冲信号

Radar 不应只看“谁被重仓买入”，还要看“同一主题是否被大规模 put 对冲”。建议增加字段：

- `institutional_long_validation`
- `institutional_put_hedge_signal`
- `theme_crowding_penalty`
- `needs_pullback_or_event_gate`

规则口径：

- 若个股被重仓 long 且无明显 put 对冲，可作为主题验证加分。
- 若个股/行业出现大额 put，对主线不扣死，但必须增加拥挤度惩罚和回撤等待要求。
- 若同一主题同时有 long 小票和 put 大票，说明资金可能在做“多瓶颈/卖龙头 beta 或保护 beta”的结构，不能把所有 AI 票等同处理。

### 2. 美股 Radar 候选池调整

| 优先级 | 标的 | 动作 |
|---|---|---|
| P1 | `SNDK` | 从观察提升为重点复核：long + call 都大，符合存储链再定价，但必须做估值现实检查 |
| P1 | `BE` | 继续作为 AI 电力 / 数据中心供电核心样本，不直接追高 |
| P1 | `CRWV` | 新云平台核心样本；高波动，只适合 Radar/V6-B，不适合主观大仓 |
| P1 | `IREN / APLD / CORZ` | AI data center / 矿转算力链继续跟踪，必须强制加入“融资、客户、capex、折旧”四项反证 |
| P2 | `MU` | 主线强，但期权结构双向，维持“HBM/存储瓶颈候选 + 不追高” |
| P2 | `TSM / AVGO / AMD` | 继续作为 AI 制造 / ASIC / 加速器锚，不因 put 直接看空，但提高买点纪律 |
| P3 | `COHR / LITE` | 被 13F 清出不代表 thesis 破，但优先级下调，需靠自身订单/业绩重新证明 |

### 3. 对我们当前持仓的启发

#### NVDA

对 NVDA 的启发不是“卖”，而是“不要忽视事件风险”。Situational Awareness 持有巨额 NVDA put，说明 AI 核心龙头即使 thesis 强，也可能需要在财报和估值兑现阶段管理回撤。

对我们当前策略的结论：维持 26 策略文件里的纪律，FY2027 Q1 财报前不新增；财报强通过才保留 12%-15%，中性回 10%-12%，未通过先降进攻部分。

#### AVGO / AMD / TSM / MU

这些仍是 Radar / V6-B 的重要 universe，但不应因为机构关注就直接变成主观进攻仓。尤其 MU、AVGO、TSM 已在本地 13F 共识研究和 Radar 体系中出现，下一步应该是等 6月1日数据额度恢复后进入 V6-B 正式验证。

#### ADBE

这份 13F 对 ADBE 没有直接增益。它强化的是 AI 基础设施链，不是软件错杀链。ADBE 仍按我们自己的 Q2 / CEO gate 走，不因为这份 13F 改变。

## 最终操作结论

1. 不新增主观前台仓。
2. 美股 Radar 增加“机构 put 对冲 / 主题拥挤度”维度。
3. `SNDK / BE / CRWV / IREN / APLD / CORZ` 进入 6月1日后美股 Radar / V6-B 重点复核清单。
4. `MU / TSM / AVGO / AMD` 继续保留在 AI 制造与瓶颈层，但买点纪律提高，不追高。
5. `COHR / LITE` 从高优先级候选降为需要重新证明的观察项。
6. 对 NVDA 当前持仓没有立即动作，但强化“财报前不新增、财报后按 gate 处理进攻部分”的纪律。

## 来源

- SEC EDGAR：Situational Awareness LP 2026Q1 13F-HR，Accession `0002045724-26-000008`
- SEC EDGAR：Situational Awareness LP 2025Q4 13F-HR，Accession `0002045724-26-000002`
