# README_CURRENT

当前仓库服务于 `/Users/zhangkun/Desktop/AI个人投资公司` 的程序化与备份层。新 AI 或新机器接手时，先读本文件，再读 `AI_WORK_SYNC_CURRENT.md` 和桌面端 `投资系统全景图_SYSTEM_OVERVIEW.html`。

## 当前生产口径

旧 `Iron Condor` 自动化链路已失效，不再作为上线、收益或风控依据。当前主线是：

| 模块 | 当前状态 | 作用 |
|---|---|---|
| `Daily Board / Central Risk Board` | active | 汇总今日动作、事件、V6异常、Radar复盘、组合风险 |
| `Cash Alpha V6-A` | `REAL_MANUAL_PILOT_ACTIVE` | 美股动量/防守切换小额人工 pilot，禁止无人值守实盘 |
| `V6-B / US Radar` | `research / SIM only` | 动态候选池、missing opportunity review、point-in-time 验证 |
| `A股 Radar` | `Phase 1A` | FutuAPI 拉行情与复盘，长江证券手动下单，不接委托接口 |
| `Value Wheel V2` | analyze-only | 基于估值与持仓约束生成建议，不自动下单 |
| `Cash Alpha V3 / IC` | paused / legacy | 低波现金增强备用线，未来重启需重新 gate |

## 最高目标

所有研究、估值、Radar、V6、仓位调整、报告和新功能都必须服务于：

> 在不牺牲长期安全性、不扩大毁灭性回撤风险的前提下，相对安全地快速增长资本。

执行前必须回答：是否提高组合预期收益、是否降低重大回撤或错误加仓风险、是否改善标的选择或仓位结构、是否符合投资哲学、是否形成实际动作或明确归档。

正式文件：

- `/Users/zhangkun/Desktop/AI个人投资公司/系统优化升级依据/AI个人投资公司_统一目标与系统协同原则_20260520.md`
- `/Users/zhangkun/Desktop/AI个人投资公司/投资系统全景图_SYSTEM_OVERVIEW.html`

## 冷启动读取顺序

1. `AI_WORK_SYNC_CURRENT.md`
2. `AI_HANDOFF_CURRENT.md`
3. `SYSTEM_OPERATIONS_CHECKLIST.md`
4. `V6_STRATEGY_LAB.md`
5. `CENTRAL_RISK_BOARD_SPEC.md`
6. `investment_screener/A_SHARE_SHORTLINE_SYSTEM_SPEC.md`
7. 桌面端 `投资系统全景图_SYSTEM_OVERVIEW.html`

## 常用命令

```bash
cd /Users/zhangkun/WorkBuddy/程序化/量化程序

# 刷新唯一 AI 同步文件
python3 collab_sync.py export-current

# 查看今天协作日志
python3 collab_sync.py today

# 生成中央风控看板
python3 central_risk_board.py --cadence daily

# 系统健康检查
python3 system_health_check.py

# V6-A guarded executor 默认 plan-only；实盘需额外 armed/confirm
python3 attack_engine_guarded_real_executor.py
```

## 硬边界

- 没有通过 reviewed / release gate / guarded runner 的链路，一律不允许真实自动下单。
- V6-A 当前只做小额人工 pilot；`kill switch`、managed state、reconciliation 和人工确认优先。
- stale data 模式下只允许刹车：BUY / ADD / ROTATE_IN 阻断；SELL 进入人工风险退出复核。
- A股 Radar 当前只做训练仓；真实交易由用户在长江证券手动下单，不写自动委托代码。
- 任何新功能如果不能解释对收益质量、风险控制、仓位结构或维护成本的增益，应降级或不做。
