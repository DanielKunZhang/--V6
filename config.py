"""
富途连接配置 + 历史遗留策略配置

说明：
- 当前美股 IC 实盘主程序使用 `main_ic_us.py` 与 `scheduler.py`
- 本文件当前核心用途是提供 `FUTU_CONFIG`
- 其余港股 / Wheel / 旧版 Iron Condor 配置仅为历史兼容，不代表当前实盘参数
"""

import os

from env_utils import load_local_env

load_local_env()

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

# ========== 当前生产参数（供人工参考，不是主程序读取源） ==========
CURRENT_PRODUCTION_CONFIG = {
    "assets": ["US.QQQ", "US.IWM", "US.GLD"],
    "actual_capital_usd": 15_000,
    "leverage": 2.0,
    "nominal_capital_usd": 30_000,
    "put_otm": 0.03,
    "call_otm": 0.06,
    "wing_width": 0.09,
    "dte": 45,
    "dynamic_config": "F=20x",
    "hv20_thresholds": {"QQQ": 0.25, "IWM": 0.25, "GLD": 0.18},
    "vix_hard_stop_hv": 0.39,
    "vix_cooldown_hv": 0.28,
    "vix_deleverage_hv": 0.22,
}

# ========== 历史兼容配置（仅供旧脚本 import，不代表当前生产） ==========
STOCK_CONFIG = {
    "ticker": "HK.00700",
    "name": "腾讯控股",
    "lot_size": 100,         # 每手100股
    "currency": "HKD",
}

# ========== 历史港股 IC 配置（兼容旧代码） ==========
IRON_CONDOR_CONFIG = {
    "ticker": "HK.00700",
    "otm": 0.05,
    "wing": 0.08,
    "dte": 45,
    "min_premium": 900,
    "estimated_credit_per_group": 2500,

    # 风险控制参数（仓位控制+硬止损，不用动态OTM）
    "stop_loss_buffer": 1.5,       # 止损缓冲倍数
    "stop_loss_pct": 0.05,         # 总回撤5%止损
    "cooldown_days": 15,           # 冷却期15天
    "early_close_days": 2,         # 到期前2天提前平仓
}

# ========== 历史仓位管理（兼容旧代码） ==========
POSITION_CONFIG = {
    "max_premium_per_trade": 5000,    # 单次最大权利金 HKD
    "max_simultaneous_trades": 1,     # 最多同时开仓数（V7b验证: 先只开1组，6万HKD资金）
    "min_days_between_trades": 3,     # 最小开仓间隔天数
}

# ========== 历史 Wheel 策略参数（兼容旧代码） ==========
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

# ========== 历史风险管理（兼容旧代码） ==========
RISK_CONFIG = {
    "max_daily_loss": 3000,       # 日内最大亏损 HKD（触发警报）
    "max_monthly_loss": 8000,     # 月度最大亏损 HKD（暂停策略）
    "stop_loss_pct": 0.15,        # 单腿止损线（股价跌破 15% 则强平）
    "emergency_exit": 0.25,       # 紧急止损线（跌破 25% 必须清仓）
}

# ========== 历史通知配置（兼容旧代码） ==========
NOTIFY_CONFIG = {
    "enabled": True,
    "email_password": os.environ.get("IC_EMAIL_PASSWORD", ""),
    "wechat_webhook_url": "",
}

# ========== 历史运行模式（兼容旧代码） ==========
RUN_MODE = {
    "dry_run": False,
    "initial_capital": 60000,
    "check_interval": 60,
    "market_open_check": True,
}

# ========== 历史日志配置（兼容旧代码） ==========
LOG_CONFIG = {
    "level": "INFO",
    "file": "logs/wheel_bot.log",
    "max_bytes": 10 * 1024 * 1024,
    "backup_count": 5,
}
