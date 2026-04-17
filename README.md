# My Trading System

当前生产系统是美股多标的 `Iron Condor` 自动交易框架，主交易标的为 `QQQ / IWM / GLD`。

## 当前生产入口

- `main_ic_us.py`：主交易程序
- `scheduler.py`：自动调度器
- `start_scheduler.sh`：守护启动入口
- `ic_monitor.py`：盘后监控与日报
- `ic_execution_guard.py`：执行层结构巡检

## 快速开始

```bash
cd /Users/zhangkun/WorkBuddy/程序化/量化程序

# 干跑测试
python3 main_ic_us.py --once --dry-run

# 盘后监控
python3 ic_monitor.py

# 启动调度
bash start_scheduler.sh
```

## 文档入口

- `README_CURRENT.md`：当前生产配置和风控基准
- `LIVE_STARTUP.md`：启动与运行步骤
- `RISK_CONTROL.md`：风险控制说明
- `SCRIPT_COMPARISON.md`：当前与历史脚本地图

## Git 备份

仓库已配置：

- 本地 Git 身份：`DingcleZ <quanyi_zk@163.com>`
- 远程仓库：`origin = git@github.com:DanielKunZhang/my-trading-system-1.git`

日常备份建议使用：

```bash
./git_checkpoint.sh
./git_checkpoint.sh "checkpoint: update monitor and scheduler"
./git_checkpoint.sh "checkpoint: before market open" --push
```

说明：

- 默认会把当前仓库的已跟踪与未忽略文件加入提交
- 默认提交信息为当前时间戳
- 传入 `--push` 时会在提交后自动推送到 `origin/main`
