#!/usr/bin/env python3
"""
铁鹰策略自动调度器
- 每个美股交易日 09:33 AM ET 自动触发 main_ic_us.py --once
- 每个美股交易日 14:45 PM ET 自动触发 ic_monitor.py（盘后监控）
- 启动时补偿检查：若当天 09:33 ET 触发记录缺失，立即补跑
- 自动处理美国夏令时（EDT/EST）切换
- 常驻运行，通过 launchd 开机自启
"""

import socket
import subprocess
import sys
import logging
from datetime import datetime
from pathlib import Path

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

# ── 路径配置 ─────────────────────────────────────────────
SCRIPT_DIR   = Path(__file__).parent
LOG_FILE     = SCRIPT_DIR / "logs" / "scheduler.log"
MAIN_SCRIPT  = SCRIPT_DIR / "main_ic_us.py"
MONITOR_SCRIPT = SCRIPT_DIR / "ic_monitor.py"
LOG_FILE.parent.mkdir(exist_ok=True)

PYTHON = sys.executable
ET = pytz.timezone("America/New_York")

# ── 日志 ─────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════

def is_opend_running() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", 11111), timeout=3):
            return True
    except OSError:
        return False


def send_opend_alert():
    try:
        sys.path.insert(0, str(SCRIPT_DIR))
        from main_ic_us import EmailNotifier
        EmailNotifier().send_alert(
            "WARNING",
            "OpenD 未运行，今日策略未执行",
            "请检查富途 OpenD 是否已启动并登录（127.0.0.1:11111）",
        )
    except Exception as e:
        logger.error(f"发送告警邮件失败: {e}")


# ═══════════════════════════════════════════════════════════
# 任务函数（必须在 add_job 之前定义）
# ═══════════════════════════════════════════════════════════

def run_strategy(label="自动触发"):
    """开仓任务入口：检查 OpenD → 运行策略脚本"""
    now_et = datetime.now(ET).strftime("%Y-%m-%d %H:%M:%S ET")
    now_bj = datetime.now(pytz.timezone("Asia/Shanghai")).strftime("%H:%M:%S 北京")
    logger.info("=" * 55)
    logger.info(f"🦅 {label} Iron Condor  |  {now_et}  ({now_bj})")
    logger.info("=" * 55)

    if not is_opend_running():
        logger.error("❌ Futu OpenD 未运行，跳过今日执行，已发送告警邮件")
        send_opend_alert()
        return

    logger.info(f"✅ OpenD 已连接，启动 {MAIN_SCRIPT.name} --once ...")
    result = subprocess.run(
        [PYTHON, str(MAIN_SCRIPT), "--once"],
        capture_output=True, text=True, cwd=str(SCRIPT_DIR),
    )
    for line in result.stdout.splitlines():
        logger.info(f"  {line}")
    for line in result.stderr.splitlines():
        logger.warning(f"  {line}")

    if result.returncode != 0:
        logger.error(f"策略脚本异常退出 (exit code {result.returncode})")
    else:
        logger.info("✅ 本次执行完成")


def run_monitor():
    """盘后监控入口：检查 OpenD → 运行监控脚本"""
    now_et = datetime.now(ET).strftime("%Y-%m-%d %H:%M:%S ET")
    now_bj = datetime.now(pytz.timezone("Asia/Shanghai")).strftime("%H:%M:%S 北京")
    logger.info("=" * 55)
    logger.info(f"🔍 自动触发盘后监控  |  {now_et}  ({now_bj})")
    logger.info("=" * 55)

    if not is_opend_running():
        logger.warning("⚠️ Futu OpenD 未运行，跳过盘后监控")
        return

    logger.info(f"✅ OpenD 已连接，启动 {MONITOR_SCRIPT.name} ...")
    result = subprocess.run(
        [PYTHON, str(MONITOR_SCRIPT)],
        capture_output=True, text=True, cwd=str(SCRIPT_DIR),
    )
    for line in result.stdout.splitlines():
        logger.info(f"  {line}")
    for line in result.stderr.splitlines():
        logger.warning(f"  {line}")

    if result.returncode != 0:
        logger.error(f"监控脚本异常退出 (exit code {result.returncode})")
    else:
        logger.info("✅ 盘后监控完成")


def _catchup_if_missed():
    """
    启动时补偿：若今天 09:33–10:30 ET 内没有触发记录，立即补跑一次。
    防止 launchd 重启 / 机器唤醒导致漏触发。
    """
    now_et = datetime.now(ET)
    if now_et.weekday() >= 5:   # 周末不补
        return

    elapsed_min = (now_et.hour * 60 + now_et.minute) - (9 * 60 + 33)
    if not (0 <= elapsed_min <= 57):   # 09:33 ~ 10:30 ET 窗口
        return

    today_str = now_et.strftime("%Y-%m-%d")
    already_ran = False
    if LOG_FILE.exists():
        try:
            content = LOG_FILE.read_text(encoding="utf-8")
            already_ran = (f"🦅 自动触发 Iron Condor  |  {today_str}" in content
                           or f"🦅 补偿触发 Iron Condor  |  {today_str}" in content)
        except Exception:
            pass

    if not already_ran:
        logger.info(f"🔄 补偿触发：今日 {today_str} 09:33 ET 无记录，立即补跑")
        run_strategy(label="补偿触发")
    else:
        logger.info(f"✅ 今日 {today_str} 已有执行记录，无需补偿")


# ═══════════════════════════════════════════════════════════
# 调度配置
# ═══════════════════════════════════════════════════════════

scheduler = BlockingScheduler(timezone=ET)

# Job 1: 每日 09:33 AM ET 开仓检查
scheduler.add_job(
    run_strategy,
    CronTrigger(day_of_week="mon-fri", hour=9, minute=33, timezone=ET),
    id="iron_condor_daily",
    name="铁鹰策略每日触发",
    misfire_grace_time=300,
)

# Job 2: 每日 14:45 PM ET 盘后监控
scheduler.add_job(
    run_monitor,
    CronTrigger(day_of_week="mon-fri", hour=14, minute=45, timezone=ET),
    id="iron_condor_monitor",
    name="铁鹰盘后监控",
    misfire_grace_time=300,
)


# ═══════════════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    logger.info("🕐 铁鹰调度器已启动")
    logger.info("   ① 开仓任务: 每个美股交易日 09:33 AM ET（北京约 21:33 夏令 / 22:33 冬令）")
    logger.info("   ② 盘后监控: 每个美股交易日 14:45 PM ET（北京约 02:45+1 夏令 / 03:45+1 冬令）")
    logger.info("   ③ 补偿机制: 启动时若当日 09:33–10:30 ET 无记录，立即补跑")
    logger.info(f"   Python  : {PYTHON}")
    logger.info(f"   脚本    : {MAIN_SCRIPT}")
    logger.info(f"   监控    : {MONITOR_SCRIPT}")
    logger.info(f"   日志    : {LOG_FILE}")

    _catchup_if_missed()

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("调度器已停止")
