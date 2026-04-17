# 美股 IC 迁移指南

## 目标

迁移当前生产系统：

- `main_ic_us.py`
- `scheduler.py`
- `ic_monitor.py`
- `start_scheduler.sh`

## 环境准备

```bash
python3 --version
pip3 install -r requirements.txt
```

## 必要前置

- 安装富途牛牛并开启 `OpenD API`
- 确认端口：`127.0.0.1:11111`
- 设置邮件环境变量：

```bash
echo "export IC_EMAIL_PASSWORD='你的163 SMTP授权码'" >> ~/.zshrc
source ~/.zshrc
```

## 迁移步骤

```bash
cd /Users/zhangkun/WorkBuddy/程序化/量化程序
python3 main_ic_us.py --once --dry-run
python3 ic_monitor.py
bash start_scheduler.sh
```

## 关键参数

- 实际本金：`IC_MANUAL_CAPITAL = 15000`
- 杠杆：`LEVERAGE = 2.0`
- 名义资金：`$30,000`
- 动态组数：`Config F=20x`

## 验证项

- `main_ic_us.py --once --dry-run` 正常
- `ic_monitor.py` 正常
- `tail -f logs/scheduler_daemon.log` 有调度输出
- OpenD 正常连接
