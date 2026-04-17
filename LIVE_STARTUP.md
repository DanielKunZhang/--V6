# 美股 IC 启动指南

当前生产系统以 `main_ic_us.py` + `scheduler.py` 为准，交易标的为 `QQQ / IWM / GLD`。

## 启动前检查

```bash
ls -l .ic_env.local
```

- 需已配置 `.ic_env.local`，内容示例：`IC_EMAIL_PASSWORD='你的163 SMTP授权码'`
- 打开富途牛牛 → `OpenD API` → 启动并登录
- 确认 OpenD 端口 `127.0.0.1:11111`

## 手动测试

```bash
cd /Users/zhangkun/WorkBuddy/程序化/量化程序
python3 main_ic_us.py --once --dry-run
python3 ic_monitor.py
```

## 启动生产调度

```bash
cd /Users/zhangkun/WorkBuddy/程序化/量化程序
bash start_scheduler.sh
tail -f logs/scheduler_daemon.log
```

## 停止调度

```bash
pkill -f "scheduler.py"
```

## 当前生产参数

- 标的：`QQQ / IWM / GLD`
- 资金：`$15,000` 实际本金，`2x` 杠杆，`$30,000` 名义资金
- 配置：`Put 3.0% / Call 6.0% / Wing 9% / DTE 45`
- 动态组数：`Config F=20x`
- 风控：`HV20` 三层口径 —— 开仓阈值 `QQQ/IWM 25% / GLD 18%`，降杠杆阈值 `22%`，硬止损 `39%`，恢复 `28%`
