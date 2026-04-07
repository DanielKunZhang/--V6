# 🚀 4月8日实盘启动指南

## 启动前准备

### 1️⃣ 配置邮箱密码

编辑 `config.py`，找到这行：

```python
"email_password": "YOUR_EMAIL_PASSWORD",
```

改为你的163邮箱SMTP密码（不是登录密码，是SMTP授权码）：

> 在163邮箱 -> 设置 -> POP3/SMTP/IMAP -> 开启SMTP -> 获取授权码

```python
"email_password": "xxxxxxyyyyyzzzzz",
```

### 2️⃣ 确认富途牛牛

- 打开富途牛牛 App
- 设置 → OpenD API → 启动并登录
- 确认状态显示"已连接"

---

## 4月8日启动流程

```bash
cd wheel_tencent

# 启动策略
./run_live.sh start

# 查看状态
./run_live.sh status

# 查看日志
./run_live.sh log
```

---

## 策略参数

| 参数 | 值 |
|------|-----|
| 初始资金 | HKD 50,000 |
| OTM | 5% |
| Wing | 8% |
| DTE | 7天 |
| 检查间隔 | 60秒 |

---

## 运行监控

### 每日收益
策略会在每天收盘后发送邮件汇总，包含：
- 今日收取的权利金
- 累计权利金
- 当日损益

### 交易通知
开仓/平仓时会自动发邮件通知

### 警报
如果触发止损或异常，会发邮件警报

---

## 停止策略

```bash
./run_live.sh stop
```

---

## 常见问题

**Q: 收不到邮件？**
A: 检查 config.py 中的 email_password 是否正确（是SMTP授权码，不是登录密码）

**Q: 连接富途失败？**
A: 确认富途牛牛已打开，OpenD API 已启动并登录

**Q: 想暂停策略？**
A: 运行 `./run_live.sh stop`，下次再用 `./run_live.sh start` 启动

---

⚠️ 风险提示
- 本策略为历史回测结果，实盘可能有差异
- 初始资金 5万港币，充分风险后后再加大
- 遇到极端行情可能导致较大亏损