#!/usr/bin/env python3
"""
铁鹰策略自动调度器
- 每个美股交易日 09:33 AM ET 自动触发 main_ic_us.py --once
- 开仓后 5 / 15 / 35 分钟执行结构巡检
- 持仓期间每 60 分钟执行一次结构巡检
- 收盘前执行一次结构巡检
- 每个美股交易日 14:45 PM ET 自动触发 ic_monitor.py（盘后监控）
- 启动时补偿检查：若当天 09:33 ET 触发记录缺失，立即补跑
- 自动处理美国夏令时（EDT/EST）切换
- 常驻运行，通过 launchd 开机自启
"""

import socket
import subprocess
import sys
import logging
import os
import fcntl
from datetime import datetime
from pathlib import Path

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

# ── 路径配置 ─────────────────────────────────────────────
SCRIPT_DIR   = Path(__file__).parent
LOG_FILE     = SCRIPT_DIR / "logs" / "scheduler.log"
LOCK_FILE    = SCRIPT_DIR / "logs" / "scheduler.lock"
MAIN_SCRIPT  = SCRIPT_DIR / "main_ic_us.py"
MONITOR_SCRIPT = SCRIPT_DIR / "ic_monitor.py"
GUARD_SCRIPT = SCRIPT_DIR / "ic_execution_guard.py"
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


class _ProcessFileLock:
    def __init__(self, path: Path):
        self.path = path
        self.handle = None

    def acquire(self) -> bool:
        self.path.parent.mkdir(exist_ok=True)
        self.handle = open(self.path, "a+", encoding="utf-8")
        try:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.handle.seek(0)
            self.handle.truncate()
            self.handle.write(str(os.getpid()))
            self.handle.flush()
            return True
        except BlockingIOError:
            return False

    def release(self):
        if not self.handle:
            return
        try:
            self.handle.seek(0)
            self.handle.truncate()
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        except Exception:
            pass
        try:
            self.handle.close()
        except Exception:
            pass
        self.handle = None


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


def run_execution_guard(mode="routine", label="执行巡检"):
    """执行层巡检：只检查结构异常，不改变策略层决策。"""
    now_et = datetime.now(ET).strftime("%Y-%m-%d %H:%M:%S ET")
    now_bj = datetime.now(pytz.timezone("Asia/Shanghai")).strftime("%H:%M:%S 北京")
    logger.info("=" * 55)
    logger.info(f"🛡️ {label}  |  {now_et}  ({now_bj})")
    logger.info("=" * 55)

    if not is_opend_running():
        logger.warning("⚠️ Futu OpenD 未运行，跳过执行巡检")
        return

    logger.info(f"✅ OpenD 已连接，启动 {GUARD_SCRIPT.name} --mode {mode} ...")
    result = subprocess.run(
        [PYTHON, str(GUARD_SCRIPT), "--mode", mode],
        capture_output=True, text=True, cwd=str(SCRIPT_DIR),
    )
    for line in result.stdout.splitlines():
        logger.info(f"  {line}")
    for line in result.stderr.splitlines():
        logger.warning(f"  {line}")

    if result.returncode != 0:
        logger.error(f"执行巡检异常退出 (exit code {result.returncode})")
    else:
        logger.info("✅ 执行巡检完成")


def _catchup_if_missed():
    """
    启动时补偿：若今天 09:33–10:30 ET 内没有触发记录，立即补跑一次。
    防止 launchd 重启 / 机器唤醒导致漏触发。
    """
    now_et = datetime.now(ET)
    if now_et.weekday() >= 5:   # 周末不补
        return

    elapsed_min = (now_et.hour * 60 + now_et.minute) - (9 * 60 + 33)
    if not (0 <= elapsed_min <= 387):   # 09:33 ~ 16:00 ET 窗口（覆盖全交易日）
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
# misfire_grace_time=23400 = 6.5小时：Mac睡眠后唤醒，只要在收盘前（16:03 ET）都会补跑
scheduler.add_job(
    run_strategy,
    CronTrigger(day_of_week="mon-fri", hour=9, minute=33, timezone=ET),
    id="iron_condor_daily",
    name="铁鹰策略每日触发",
    misfire_grace_time=23400,
    max_instances=1,
    coalesce=True,
)

# Job 1.1-1.3: 开仓后 5 / 15 / 35 分钟结构巡检
scheduler.add_job(
    run_execution_guard,
    CronTrigger(day_of_week="mon-fri", hour=9, minute=38, timezone=ET),
    kwargs={"mode": "post_open", "label": "开仓后巡检（+5m）"},
    id="iron_condor_guard_post_open_5",
    name="开仓后巡检 +5m",
    misfire_grace_time=1800,
    max_instances=1,
    coalesce=True,
)
scheduler.add_job(
    run_execution_guard,
    CronTrigger(day_of_week="mon-fri", hour=9, minute=48, timezone=ET),
    kwargs={"mode": "post_open", "label": "开仓后巡检（+15m）"},
    id="iron_condor_guard_post_open_15",
    name="开仓后巡检 +15m",
    misfire_grace_time=1800,
    max_instances=1,
    coalesce=True,
)
scheduler.add_job(
    run_execution_guard,
    CronTrigger(day_of_week="mon-fri", hour=10, minute=8, timezone=ET),
    kwargs={"mode": "post_open", "label": "开仓后巡检（+35m）"},
    id="iron_condor_guard_post_open_35",
    name="开仓后巡检 +35m",
    misfire_grace_time=1800,
    max_instances=1,
    coalesce=True,
)

# Job 1.4: 持仓期间每 60 分钟巡检一次
scheduler.add_job(
    run_execution_guard,
    CronTrigger(day_of_week="mon-fri", hour="11-15", minute=8, timezone=ET),
    kwargs={"mode": "routine", "label": "盘中结构巡检"},
    id="iron_condor_guard_hourly",
    name="盘中结构巡检",
    misfire_grace_time=1800,
    max_instances=1,
    coalesce=True,
)

# Job 1.5: 收盘前巡检
scheduler.add_job(
    run_execution_guard,
    CronTrigger(day_of_week="mon-fri", hour=15, minute=50, timezone=ET),
    kwargs={"mode": "pre_close", "label": "收盘前巡检"},
    id="iron_condor_guard_pre_close",
    name="收盘前巡检",
    misfire_grace_time=1800,
    max_instances=1,
    coalesce=True,
)

# Job 0: 每30分钟检查一次今日是否漏跑（处理Mac睡眠唤醒场景）
scheduler.add_job(
    _catchup_if_missed,
    CronTrigger(day_of_week="mon-fri", hour="9-16", minute="*/30", timezone=ET),
    id="iron_condor_catchup",
    name="漏跑补偿检查",
    misfire_grace_time=1800,
    max_instances=1,
    coalesce=True,
)

# Job 2: 每日 14:45 PM ET 盘后监控
# misfire_grace_time=7200 = 2小时宽限
scheduler.add_job(
    run_monitor,
    CronTrigger(day_of_week="mon-fri", hour=14, minute=45, timezone=ET),
    id="iron_condor_monitor",
    name="铁鹰盘后监控",
    misfire_grace_time=7200,
    max_instances=1,
    coalesce=True,
)


# ═══════════════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    process_lock = _ProcessFileLock(LOCK_FILE)
    if not process_lock.acquire():
        logger.warning("⚠️ 已有一个 scheduler 实例在运行，本次退出，避免重复触发")
        sys.exit(0)

    logger.info("🕐 铁鹰调度器已启动")
    logger.info("   ① 开仓任务: 每个美股交易日 09:33 AM ET（北京约 21:33 夏令 / 22:33 冬令）")
    logger.info("   ② 执行巡检: 开仓后 +5m / +15m / +35m，盘中每60分钟一次，15:50 ET 收盘前复核")
    logger.info("   ③ 盘后监控: 每个美股交易日 14:45 PM ET（北京约 02:45+1 夏令 / 03:45+1 冬令）")
    logger.info("   ④ 补偿机制: 启动时若当日 09:33–10:30 ET 无记录，立即补跑")
    logger.info(f"   Python  : {PYTHON}")
    logger.info(f"   脚本    : {MAIN_SCRIPT}")
    logger.info(f"   巡检    : {GUARD_SCRIPT}")
    logger.info(f"   监控    : {MONITOR_SCRIPT}")
    logger.info(f"   日志    : {LOG_FILE}")

    _catchup_if_missed()

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("调度器已停止")
    finally:
        process_lock.release()
