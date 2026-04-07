"""
腾讯 Wheel 策略配置
"""

# ========== 富途 OpenD 连接配置 ==========
FUTU_CONFIG = {
    "host": "127.0.0.1",
    "port": 11111,           # Futu OpenD 默认端口
    "reload": True,
    # 账户设置（根据 get_acc_list 返回的 acc_id）
    # 模拟期权账户: 9865486 (有期权权限)
    # 真实账户: 13797052 (综合账户 8739)
    "sim_acc_id": "9865486",   # 模拟账户ID
    "real_acc_id": "281756481449956811",         # 真实账户ID（综合账户）
}

# ========== 标的配置 ==========
STOCK_CONFIG = {
    "ticker": "HK.00700",    # 腾讯（富途格式）
    "name": "腾讯控股",
    "lot_size": 100,         # 每手100股
    "currency": "HKD",
}

# ========== Iron Condor 策略参数 (2026-04-06 最终版 - 16年回测验证) ==========
IRON_CONDOR_CONFIG = {
    "ticker": "HK.00700",          # 腾讯（港股唯一流动性好的期权标的）
    "otm": 0.05,                   # 5% OTM（回测最优：年化+28.61%）
    "wing": 0.08,                  # 8% 翼宽（与OTM配合）
    "dte": 45,                     # 45天到期（2026-04-06长周期回测：DTE45全面优于DTE30）
    "min_premium": 900,            # 最低权利金 HKD（低于900不开仓）
    "estimated_credit_per_group": 2500,  # 每组估算权利金 HKD 2500（用于止损计算）

    # 风险控制参数（仓位控制+硬止损，不用动态OTM）
    "stop_loss_buffer": 1.5,       # 止损缓冲倍数
    "stop_loss_pct": 0.05,         # 总回撤5%止损
    "cooldown_days": 15,           # 冷却期15天
    "early_close_days": 2,         # 到期前2天提前平仓
}

# ========== 仓位管理 ==========
POSITION_CONFIG = {
    "max_premium_per_trade": 5000,    # 单次最大权利金 HKD
    "max_simultaneous_trades": 1,     # 最多同时开仓数（V7b验证: 先只开1组，6万HKD资金）
    "min_days_between_trades": 3,     # 最小开仓间隔天数
}

# ========== Wheel 策略参数（兼容旧代码） ==========
WHEEL_CONFIG = {
    "put": {
        "strike_delta": 0.10,
        "min_premium": 800,
        "dte_target": 30,
        "max_strike_below_current": 0.20,
    },
    "call": {
        "strike_delta": 0.10,
        "min_premium": 600,
        "dte_target": 30,
        "profit_target_pct": 0.15,
    },
    "position": {
        "max_portfolio_strike": 60000,
        "max_put_premium_ratio": 0.05,
        "max_simultaneous_legs": 2,
    },
}

# ========== 风险管理 ==========
RISK_CONFIG = {
    "max_daily_loss": 3000,       # 日内最大亏损 HKD（触发警报）
    "max_monthly_loss": 8000,     # 月度最大亏损 HKD（暂停策略）
    "stop_loss_pct": 0.15,        # 单腿止损线（股价跌破 15% 则强平）
    "emergency_exit": 0.25,       # 紧急止损线（跌破 25% 必须清仓）
}

# ========== 通知配置 ==========
NOTIFY_CONFIG = {
    "enabled": True,
    "email_password": "YHeYZUqHf5bpR2xe",  # 163邮箱SMTP授权码
    "wechat_webhook_url": "",  # 企业微信 webhook（不用可留空）
}

# ========== 运行模式 ==========
RUN_MODE = {
    "dry_run": False,              # 实盘模式
    "initial_capital": 60000,      # 初始资金 HKD 6万
    "check_interval": 60,          # 检查间隔（秒）
    "market_open_check": True,     # 只在交易时段检查
}

# ========== 日志配置 ==========
LOG_CONFIG = {
    "level": "INFO",
    "file": "logs/wheel_bot.log",
    "max_bytes": 10 * 1024 * 1024,  # 10MB
    "backup_count": 5,
}
