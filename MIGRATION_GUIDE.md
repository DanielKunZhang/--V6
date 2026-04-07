# 策略迁移指南

## 换电脑后如何继续 Iron Condor 策略

### 1️⃣ 环境准备

**安装依赖:**
```bash
# Python 3.10+
python3 --version

# 安装富途 API
pip install futu-api

# 其他依赖
pip install pandas numpy
```

### 2️⃣ 复制文件

将整个 `wheel_tencent/` 文件夹复制到新电脑:
```bash
# 方式1: U盘/移动硬盘
cp -r wheel_tencent/ ~/WheelBuddy/

# 方式2: 云盘 (iCloud/Dropbox/Google Drive)
# 建议用云盘同步，状态会自动保存
```

或者用 Git:
```bash
# 在新电脑克隆
git clone git@github.com:yourusername/wheel_tencent.git
```

### 3️⃣ 关键文件说明

| 文件 | 作用 |
|------|------|
| `config.py` | 策略参数配置 |
| `run_ic.py` | 实盘运行脚本 |
| `iron_condor.py` | 回测核心代码 |
| `backtest_real.py` | 数据获取 |
| `.env` | API 密钥等 (如有) |

### 4️⃣ 配置富途 OpenD

新电脑需要安装富途牛牛并:
1. 打开「OpenD 模拟交易」
2. 确认端口 11111
3. 获取新电脑的 `machine_id`

### 5️⃣ 启动策略

```bash
cd wheel_tencent
python3 run_ic.py --dry-run   # 先模拟
# 或
python3 run_ic.py            # 真实交易
```

### 6️⃣ 同步状态 (可选)

如果用了云盘同步，状态文件会自动同步:
- `logs/` - 运行日志
- `positions.json` - 当前持仓
- `state.json` - 策略状态

---

## 📋 快速检查清单

- [ ] Python 3.10+ 安装
- [ ] 富途牛牛 + OpenD 开启
- [ ] `wheel_tencent/` 复制
- [ ] `pip install futu-api`
- [ ] 配置检查 (`config.py`)
- [ ] 测试运行 (`python3 run_ic.py --dry-run`)

---

## ⚠️ 注意事项

1. **machine_id**: 每台电脑的 machine_id 不同，换电脑后需要在富途重新获取
2. **持仓同步**: 如果原电脑有持仓，手动记录后到新电脑重建
3. **模拟 vs 真实**: 先用 `--dry-run` 测试，确认正常后再切真实

## 🔗 获取帮助

有问题看:
- `iron_condor.py --help`
- `run_ic.py --help`
- `STRATEGY_SNAPSHOT.md` - 策略快照