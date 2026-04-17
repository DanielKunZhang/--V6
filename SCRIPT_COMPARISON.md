# 当前生产文件地图

## 当前生产入口

- `main_ic_us.py`：美股 IC 主程序
- `scheduler.py`：美东交易日自动调度
- `start_scheduler.sh`：守护启动入口
- `ic_monitor.py`：盘后监控
- `dynamic_composite_backtest.py`：当前回测基准对照

## 当前生产模型

- 标的：`QQQ / IWM / GLD`
- 结构：`P3.0% / C6.0% / Wing9% / DTE45`
- 资金：`$15k` 实际本金，`2x` 杠杆，`$30k` 名义资金
- 动态组数：`Config F=20x`

## 历史遗留文件

以下文件仅保留作历史参考，不再作为生产入口：

- `main.py`
- `main_ic.py`
- `run_live.sh`
- `run_ic_live.sh`
- `restart.sh`
- `com.futuwheel.plist`

## 原则

- 生产系统一律以美股多标的 IC 为准
- 港股 / 腾讯 / Wheel 相关脚本不再作为执行入口
- 如需改生产参数，先在回测中验证，再同步到实盘
