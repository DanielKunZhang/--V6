#!/usr/bin/env python3
"""
Iron Condor 执行层巡检（Phase 1）
=================================

职责：
- 不改变策略层止损/止盈决策
- 只检查实盘执行结构是否健康
- 发现残腿、状态漂移、本地记录错配时发告警

频率建议：
- 开仓后：5 / 15 / 35 分钟
- 持仓中：60 分钟
- 收盘前：1 次
"""

from __future__ import annotations

import argparse
import json
import logging
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from main_ic_us import (
    ASSETS,
    IC_CONFIG,
    FutuDataUS,
    IronCondorTraderUS,
    EmailNotifier,
    _append_execution_event,
    _load_ic_codes,
    _load_open_trade,
)


LOG_DIR = Path(__file__).parent / "logs"
LOG_FILE = LOG_DIR / "execution_guard.log"
STATE_FILE = LOG_DIR / "ic_execution_guard_state.json"

LOG_DIR.mkdir(exist_ok=True)

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


def _load_state() -> Dict:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(state: Dict) -> None:
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _severity_rank(level: str) -> int:
    return {"OK": 0, "WARNING": 1, "CRITICAL": 2}.get(level, 0)


def _build_trader(data: FutuDataUS, asset: Dict) -> IronCondorTraderUS:
    trader = IronCondorTraderUS(data)
    trader.dry_run = False
    trader.stock = {"ticker": asset["ticker"], "name": asset["name"]}
    trader.config = {
        **IC_CONFIG,
        "max_groups": asset["max_groups"],
        "hv20_threshold": asset.get("hv20_threshold", IC_CONFIG["hv20_threshold"]),
        "capital": asset["capital"],
    }
    return trader


def _analyze_asset(trader: IronCondorTraderUS, asset: Dict) -> Dict:
    asset_name = asset["name"]
    ticker_name = asset["ticker"].split(".")[1]
    positions = trader._get_positions_with_expiry()
    ic_codes_all = _load_ic_codes()
    ic_codes = sorted(c for c in ic_codes_all if ticker_name in c)
    open_trade = _load_open_trade(asset_name)

    issues: List[Dict] = []
    expiry_groups = defaultdict(list)
    for pos in positions:
        expiry_groups[str(pos.get("expiry") or "")].append(pos)

    def add_issue(level: str, message: str, details: str = "") -> None:
        issues.append({"level": level, "message": message, "details": details})

    if positions:
        if len(positions) % 4 != 0:
            add_issue(
                "CRITICAL",
                f"真实持仓腿数异常：{len(positions)} 条腿，不是 4 的整数倍",
                "疑似残腿或结构不完整",
            )

        for expiry, legs in sorted(expiry_groups.items()):
            qty_levels = sorted({abs(int(leg.get("qty", 0) or 0)) for leg in legs if int(leg.get("qty", 0) or 0) != 0})
            if len(legs) != 4:
                add_issue(
                    "CRITICAL",
                    f"{expiry} 结构不完整：仅 {len(legs)} 条腿",
                    f"qty级别={qty_levels or ['0']}",
                )
                continue
            if len(qty_levels) != 1:
                add_issue(
                    "CRITICAL",
                    f"{expiry} 组数不一致",
                    f"腿数量级={qty_levels}",
                )

        real_codes = sorted(pos.get("code", "") for pos in positions if pos.get("code"))
        if ic_codes:
            missing_in_broker = [code for code in ic_codes if code not in real_codes]
            if missing_in_broker:
                add_issue(
                    "WARNING",
                    "本地记录的 IC 腿未在富途持仓中找到",
                    ", ".join(missing_in_broker[:8]),
                )
        else:
            add_issue(
                "WARNING",
                "富途存在 IC 持仓，但本地 ic_open_codes 为空",
                f"真实持仓 {len(real_codes)} 条腿",
            )
    else:
        if ic_codes:
            add_issue(
                "WARNING",
                "本地 ic_open_codes 有记录，但富途未返回对应 IC 持仓",
                f"本地记录 {len(ic_codes)} 条腿",
            )
        if open_trade:
            add_issue(
                "WARNING",
                "本地 open_trade 有记录，但富途未返回对应 IC 持仓",
                f"open_trade expiry={open_trade.get('expiry', '')}",
            )

    if open_trade and positions:
        open_expiry = str(open_trade.get("expiry", "") or "")
        real_expiries = sorted(expiry for expiry in expiry_groups.keys() if expiry)
        if open_expiry and open_expiry not in real_expiries:
            add_issue(
                "WARNING",
                "open_trade 到期日与富途真实持仓不一致",
                f"open_trade={open_expiry}, real={real_expiries}",
            )

    level = "OK"
    if issues:
        level = max((issue["level"] for issue in issues), key=_severity_rank)

    details = " | ".join(
        f"{issue['message']}：{issue['details']}".rstrip("：")
        for issue in issues
    )
    if not details:
        details = "结构正常"

    return {
        "asset": asset_name,
        "ticker": asset["ticker"],
        "level": level,
        "issues": issues,
        "details": details,
        "position_count": len(positions),
        "tracked_code_count": len(ic_codes),
        "has_open_trade": bool(open_trade),
    }


def _emit_if_changed(
    summary: Dict,
    mode: str,
    notifier: EmailNotifier,
    state: Dict,
    dry_run: bool = False,
) -> None:
    asset = summary["asset"]
    level = summary["level"]
    details = summary["details"]
    issues = summary["issues"]

    signature = "OK" if level == "OK" else " || ".join(
        f"{issue['level']}::{issue['message']}::{issue['details']}"
        for issue in issues
    )
    previous = state.get(asset, {})
    prev_signature = previous.get("signature", "")
    prev_level = previous.get("level", "OK")

    state[asset] = {
        "level": level,
        "signature": signature,
        "mode": mode,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }

    if level == "OK":
        if prev_level != "OK":
            msg = f"[{asset}] 执行结构恢复正常"
            if not dry_run:
                _append_execution_event(
                    event_type="guard_resolved",
                    asset=asset,
                    level="INFO",
                    message="执行结构恢复正常",
                    details=f"模式={mode}",
                )
            logger.info(f"✅ {msg}")
        return

    if signature == prev_signature and level == prev_level:
        logger.info(f"⏭️ [{asset}] 异常未变化，跳过去重告警：{details}")
        return

    subject = f"[{asset}] 执行巡检 {level}"
    if not dry_run:
        _append_execution_event(
            event_type="execution_guard_alert",
            asset=asset,
            level=level,
            message=f"执行巡检发现异常（{mode})",
            details=details,
            extra={"mode": mode, "issues": issues},
        )
        notifier.send_alert(level if level in {"WARNING", "CRITICAL"} else "WARNING", subject, details)
    logger.warning(f"🚨 [{asset}] {mode} 巡检异常: {details}")


def run_guard(mode: str = "routine", dry_run: bool = False) -> List[Dict]:
    logger.info("=" * 55)
    logger.info(f"🛡️ Execution Guard 启动 | mode={mode}{' | dry-run' if dry_run else ''}")
    logger.info("=" * 55)

    data = FutuDataUS()
    if not data.connect():
        logger.error("❌ 无法连接 OpenD，巡检终止")
        return []

    notifier = EmailNotifier()
    state = _load_state()
    summaries: List[Dict] = []

    try:
        for asset in ASSETS:
            trader = _build_trader(data, asset)
            summary = _analyze_asset(trader, asset)
            summaries.append(summary)
            logger.info(
                f"[{summary['asset']}] {summary['level']} | "
                f"legs={summary['position_count']} tracked={summary['tracked_code_count']} | {summary['details']}"
            )
            _emit_if_changed(summary, mode, notifier, state, dry_run=dry_run)
    finally:
        data.close()
        if not dry_run:
            _save_state(state)

    overall = max((item["level"] for item in summaries), key=_severity_rank) if summaries else "OK"
    logger.info(f"✅ Execution Guard 完成 | overall={overall}")
    return summaries


def main() -> None:
    parser = argparse.ArgumentParser(description="Iron Condor 执行层巡检")
    parser.add_argument(
        "--mode",
        default="routine",
        choices=["post_open", "routine", "pre_close"],
        help="巡检模式",
    )
    parser.add_argument("--dry-run", action="store_true", help="只读巡检，不写状态、不发邮件")
    args = parser.parse_args()
    run_guard(mode=args.mode, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
