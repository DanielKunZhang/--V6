#!/usr/bin/env python3
"""
美股 Iron Condor 实盘交易脚本（非对称铁鹰 + 2x杠杆 + 动态组数）

当前实盘配置（2026-04-12 确认）：
  标的: QQQ $18k + IWM $6k + GLD $6k（名义资本 $30k）
  实际本金: $15k，2x 杠杆；动态组数基于 IC_MANUAL_CAPITAL × LEVERAGE 计算
  非对称OTM: Put 3.0% / Call 6.0%
  翼宽 Wing: 9%
  DTE: 45天（月度/季度期权）
  VIX硬止损: HV20 ≥ 39% 强平；HV20 < 28% 才恢复开仓
  HV20开仓阈值: QQQ≤25%, IWM≤25%, GLD≤18%（纯HV口径）

回测基准（2010-2025，16年，$15k实际资本）：
  当前实盘基准：动态组数 Config F=20x → 年化 +38.99%，最大回撤 -12.0%，夏普 2.64
  固定组数基线：年化 +30.49%，最大回撤 -6.49%，夏普 2.63
  HV说明：历史波动率使用纯HV20；BS定价时 IV 估算 = HV20 × 1.15
"""

import os
import time
import json
import logging
import sys
import argparse
import fcntl
from pathlib import Path
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Set

from capacity_utils import build_capacity_policy, build_capacity_snapshot, capacity_band
from env_utils import load_local_env

load_local_env()

# ── IC 持仓追踪文件（只操作策略自己开的期权，不误碰 Wheel/正股）──────
_IC_STATE_FILE        = Path(__file__).parent / "logs" / "ic_open_codes.json"
_IC_COOLDOWN_FILE     = Path(__file__).parent / "logs" / "ic_cooldown_state.json"
_IC_VIX_HARDSTOP_FILE = Path(__file__).parent / "logs" / "ic_vix_hardstop.json"
_IC_OPEN_TRADE_FILE   = Path(__file__).parent / "logs" / "ic_open_trade.json"
_IC_ASSET_RISK_FILE   = Path(__file__).parent / "logs" / "ic_asset_risk_state.json"
_IC_TRADE_HISTORY_CSV = Path(__file__).parent / "logs" / "trade_history.csv"
_IC_EXECUTION_EVENTS_FILE = Path(__file__).parent / "logs" / "ic_execution_events.jsonl"
_IC_EXECUTION_GUARD_STATE_FILE = Path(__file__).parent / "logs" / "ic_execution_guard_state.json"
_MAIN_RUN_LOCK_FILE   = Path(__file__).parent / "logs" / "main_ic_us.lock"


def _load_cooldown_state() -> Dict:
    """读取各标的上次平仓日期（用于实现5天开仓冷却期）"""
    try:
        if _IC_COOLDOWN_FILE.exists():
            return json.loads(_IC_COOLDOWN_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_cooldown_state(state: Dict):
    """持久化冷却状态"""
    _IC_COOLDOWN_FILE.parent.mkdir(exist_ok=True)
    _IC_COOLDOWN_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _load_vix_hardstop_state() -> Dict:
    """读取各标的 VIX 硬止损状态（是否处于硬止损恢复等待期）"""
    try:
        if _IC_VIX_HARDSTOP_FILE.exists():
            return json.loads(_IC_VIX_HARDSTOP_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_vix_hardstop_state(state: Dict):
    _IC_VIX_HARDSTOP_FILE.parent.mkdir(exist_ok=True)
    _IC_VIX_HARDSTOP_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _set_vix_hard_stop(asset_name: str):
    """VIX 硬止损触发时，记录进入硬止损状态"""
    state = _load_vix_hardstop_state()
    state[asset_name] = date.today().isoformat()
    _save_vix_hardstop_state(state)
    logger.info(f"[{asset_name}] 🚨 VIX 硬止损状态已记录，等待 HV20 < {VIX_COOLDOWN_HV:.0%} 恢复")


def _is_vix_hard_stopped(asset_name: str) -> bool:
    """检查标的是否处于 VIX 硬止损恢复等待期"""
    return asset_name in _load_vix_hardstop_state()


def _clear_vix_hard_stop(asset_name: str):
    """HV20 回落到冷却阈值以下时，解除 VIX 硬止损状态"""
    state = _load_vix_hardstop_state()
    if asset_name in state:
        state.pop(asset_name)
        _save_vix_hardstop_state(state)
        logger.info(f"[{asset_name}] ✅ VIX 硬止损解除")


def _load_asset_risk_state() -> Dict:
    """读取单标的权益峰值状态（用于回撤止损，与回测口径对齐）"""
    try:
        if _IC_ASSET_RISK_FILE.exists():
            return json.loads(_IC_ASSET_RISK_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_asset_risk_state(state: Dict):
    _IC_ASSET_RISK_FILE.parent.mkdir(exist_ok=True)
    _IC_ASSET_RISK_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _load_execution_guard_state() -> Dict:
    """读取执行巡检状态，用于日报展示。"""
    try:
        if _IC_EXECUTION_GUARD_STATE_FILE.exists():
            return json.loads(_IC_EXECUTION_GUARD_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _load_realized_pnl_by_asset() -> Dict[str, float]:
    """从 trade_history.csv 汇总各标的已实现盈亏。"""
    import csv as _csv

    realized: Dict[str, float] = {}
    if not _IC_TRADE_HISTORY_CSV.exists():
        return realized

    try:
        with open(_IC_TRADE_HISTORY_CSV, "r", encoding="utf-8") as f:
            reader = _csv.DictReader(f)
            for row in reader:
                if row.get("action") != "CLOSE":
                    continue
                asset = str(row.get("asset", "") or "").strip()
                if not asset:
                    continue
                try:
                    pnl = float(row.get("realized_pnl", 0) or 0)
                except Exception:
                    pnl = 0.0
                realized[asset] = realized.get(asset, 0.0) + pnl
    except Exception:
        return {}
    return realized


def _compute_asset_strategy_equity(asset_name: str, asset_capital: float, unrealized_pl: float) -> Dict:
    """
    计算单标的当前策略权益。
    口径：初始分配资金 + 历史已实现盈亏 + 当前未实现盈亏
    """
    realized_map = _load_realized_pnl_by_asset()
    realized_pnl = float(realized_map.get(asset_name, 0.0) or 0.0)
    baseline_equity = float(asset_capital or 0.0) + realized_pnl
    current_equity = baseline_equity + float(unrealized_pl or 0.0)
    return {
        "realized_pnl": realized_pnl,
        "baseline_equity": baseline_equity,
        "current_equity": current_equity,
    }


def _update_asset_peak_equity(asset_name: str, baseline_equity: float, current_equity: float) -> Dict:
    """
    更新/读取单标的权益峰值状态。
    峰值至少不低于 baseline_equity，避免首次接入时在亏损点把峰值记低。
    """
    state = _load_asset_risk_state()
    asset_state = state.get(asset_name, {})
    prev_peak = float(asset_state.get("peak_equity", 0.0) or 0.0)
    peak_equity = max(prev_peak, baseline_equity, current_equity)
    asset_state.update({
        "peak_equity": round(peak_equity, 2),
        "last_equity": round(current_equity, 2),
        "baseline_equity": round(baseline_equity, 2),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    })
    state[asset_name] = asset_state
    _save_asset_risk_state(state)
    return asset_state


# ── 实盘绩效持久化（trade_history.csv）─────────────────────────────────

def _load_open_trade(asset_name: str) -> Dict:
    """读取当前已开仓的交易元数据（开仓日期、行权价、权利金等）"""
    try:
        if _IC_OPEN_TRADE_FILE.exists():
            data = json.loads(_IC_OPEN_TRADE_FILE.read_text(encoding="utf-8"))
            return data.get(asset_name, {})
    except Exception:
        pass
    return {}


def _save_open_trade(asset_name: str, trade: Dict):
    """保存开仓元数据"""
    _IC_OPEN_TRADE_FILE.parent.mkdir(exist_ok=True)
    try:
        data = json.loads(_IC_OPEN_TRADE_FILE.read_text(encoding="utf-8")) if _IC_OPEN_TRADE_FILE.exists() else {}
    except Exception:
        data = {}
    data[asset_name] = trade
    _IC_OPEN_TRADE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _clear_open_trade(asset_name: str):
    """平仓后清除开仓元数据"""
    try:
        if _IC_OPEN_TRADE_FILE.exists():
            data = json.loads(_IC_OPEN_TRADE_FILE.read_text(encoding="utf-8"))
            data.pop(asset_name, None)
            _IC_OPEN_TRADE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _append_trade_history(row: Dict):
    """追加一条交易记录到 trade_history.csv（开仓 OPEN 或平仓 CLOSE）"""
    import csv as _csv
    _IC_TRADE_HISTORY_CSV.parent.mkdir(exist_ok=True)
    fields = ["date", "time", "asset", "action", "expiry",
              "sell_put", "sell_call", "buy_put", "buy_call",
              "groups", "net_premium", "days_held", "realized_pnl", "close_reason"]
    write_header = not _IC_TRADE_HISTORY_CSV.exists()
    with open(_IC_TRADE_HISTORY_CSV, "a", newline="", encoding="utf-8") as f:
        writer = _csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        if write_header:
            writer.writeheader()
        writer.writerow({k: row.get(k, "") for k in fields})


def _record_close_date(asset_name: str):
    """平仓时记录当天日期，触发冷却期计时"""
    state = _load_cooldown_state()
    state[asset_name] = date.today().isoformat()
    _save_cooldown_state(state)
    logger.info(f"[{asset_name}] 📝 冷却期开始：{state[asset_name]}")


def _load_ic_codes() -> Set[str]:
    """读取 IC 策略已开仓的期权代码集合"""
    try:
        if _IC_STATE_FILE.exists():
            data = json.loads(_IC_STATE_FILE.read_text(encoding="utf-8"))
            return set(data.get("codes", []))
    except Exception:
        pass
    return set()


def _save_ic_codes(codes: Set[str]):
    """持久化 IC 策略持仓代码"""
    _IC_STATE_FILE.parent.mkdir(exist_ok=True)
    _IC_STATE_FILE.write_text(
        json.dumps({"codes": sorted(codes)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _add_ic_codes(new_codes: List[str]):
    """开仓后追加代码"""
    existing = _load_ic_codes()
    existing.update(new_codes)
    _save_ic_codes(existing)


def _remove_ic_codes(closed_codes: List[str]):
    """平仓后移除代码"""
    existing = _load_ic_codes()
    for c in closed_codes:
        existing.discard(c)
    _save_ic_codes(existing)


def _append_execution_event(
    event_type: str,
    asset: str,
    level: str,
    message: str,
    details: str = "",
    extra: Optional[Dict] = None,
):
    """记录执行层事件，供日报/监控统一读取。"""
    _IC_EXECUTION_EVENTS_FILE.parent.mkdir(exist_ok=True)
    payload = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "event_type": event_type,
        "asset": asset,
        "level": level,
        "message": message,
        "details": details,
        "extra": extra or {},
    }
    with open(_IC_EXECUTION_EVENTS_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _load_recent_execution_events(hours: int = 48, limit: int = 20) -> List[Dict]:
    """读取最近执行事件，供日报/监控展示。"""
    if not _IC_EXECUTION_EVENTS_FILE.exists():
        return []

    cutoff = datetime.now() - timedelta(hours=hours)
    events = []
    try:
        with open(_IC_EXECUTION_EVENTS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    ts = datetime.fromisoformat(event.get("ts"))
                    if ts >= cutoff:
                        events.append(event)
                except Exception:
                    continue
    except Exception:
        return []

    return events[-limit:]


def _compute_live_position_capacity_summary(data=None, dry_run: bool = False) -> List[Dict]:
    """
    生成每个标的的实时持仓组数 / 当前理论允许上限 / 是否还能再开。
    """
    summaries = []
    own_data = data is None
    data_obj = data or FutuDataUS()
    if own_data:
        data_obj.connect()

    try:
        for asset in ASSETS:
            trader = IronCondorTraderUS(data_obj)
            trader.dry_run = dry_run
            trader.stock = {"ticker": asset["ticker"], "name": asset["name"]}
            trader.config = {
                **IC_CONFIG,
                "max_groups": asset["max_groups"],
                "hv20_threshold": asset.get("hv20_threshold", IC_CONFIG["hv20_threshold"]),
                "capital": asset["capital"],
            }

            existing_groups, total_legs = trader.check_existing_positions()
            market_cond = trader._check_market_conditions()
            hv20 = float(market_cond.get("hv20", 0.0) or 0.0)

            group_limits = trader._compute_group_limits(hv20)
            base_groups = group_limits["base_groups"]
            full_max_groups = group_limits["full_max_groups"]
            effective_max_groups = group_limits["effective_max_groups"]

            blocked_reason = ""

            if not market_cond.get("can_open", True):
                blocked_reason = market_cond.get("reason", "市场条件不允许开仓")
            elif _is_vix_hard_stopped(asset["name"]):
                if hv20 >= VIX_COOLDOWN_HV:
                    blocked_reason = f"VIX硬止损恢复等待（HV20={hv20:.1%}，需<{VIX_COOLDOWN_HV:.0%}）"
            else:
                cooldown_days = trader.config.get("cooldown_days", 5)
                cooldown_state = _load_cooldown_state()
                last_close_str = cooldown_state.get(asset["name"])
                if last_close_str:
                    try:
                        last_close = date.fromisoformat(last_close_str)
                        days_since = (date.today() - last_close).days
                        if days_since < cooldown_days:
                            remaining = cooldown_days - days_since
                            blocked_reason = f"冷却期中（还剩{remaining}天）"
                    except ValueError:
                        pass

                if not blocked_reason:
                    holiday_warning = trader._check_holiday_risk()
                    if holiday_warning:
                        blocked_reason = f"长假风险预警：{holiday_warning}"

            if not blocked_reason and existing_groups >= effective_max_groups:
                blocked_reason = f"已有{existing_groups}组，达到/超过当前上限{effective_max_groups}组"

            can_add = (blocked_reason == "") and existing_groups >= 0 and existing_groups < effective_max_groups
            summaries.append({
                "name": asset["name"],
                "ticker": asset["ticker"],
                "hv20": hv20,
                "existing_groups": existing_groups,
                "existing_legs": total_legs,
                "allowed_groups": effective_max_groups,
                "base_groups": base_groups,
                "full_max_groups": full_max_groups,
                "can_add": can_add,
                "blocked_reason": blocked_reason,
            })
    finally:
        if own_data:
            data_obj.close()

    return summaries


PRESSURE_MONITOR_CONFIG = {
    "short_warn_pct": 0.03,          # 距 short strike ≤3%：黄灯
    "short_alert_pct": 0.015,        # 距 short strike ≤1.5%：橙灯
    "breakeven_warn_pct": 0.03,      # 距盈亏平衡 ≤3%：黄灯
    "breakeven_alert_pct": 0.015,    # 距盈亏平衡 ≤1.5%：橙灯
    "stop_warn_pct": 0.03,           # 距价格止损 ≤3%：橙灯
    "stop_critical_pct": 0.015,      # 距价格止损 ≤1.5%：红灯
    "loss_warn_ratio": 0.20,         # 当前浮亏 / 最大亏损 ≥20%：黄灯
    "loss_alert_ratio": 0.35,        # 当前浮亏 / 最大亏损 ≥35%：橙灯
    "loss_critical_ratio": 0.50,     # 当前浮亏 / 最大亏损 ≥50%：红灯
}


def _format_pressure_distance(pct: Optional[float]) -> str:
    if pct is None:
        return "-"
    if pct < 0:
        return f"已突破 {abs(pct):.1%}"
    return f"{pct:.1%}"


def _classify_pressure_level(
    dist_short_pct: Optional[float],
    dist_be_pct: Optional[float],
    dist_stop_pct: Optional[float],
    loss_ratio: float,
    imbalanced: bool,
) -> Dict:
    cfg = PRESSURE_MONITOR_CONFIG

    if imbalanced:
        return {
            "level": "critical",
            "label": "🔴 红灯",
            "color": "#c62828",
            "title": "结构不完整",
            "suggestion": "存在残腿/组数不一致，先修复结构，再谈持有。",
        }

    if dist_stop_pct is not None and dist_stop_pct <= 0:
        return {
            "level": "critical",
            "label": "🔴 红灯",
            "color": "#c62828",
            "title": "已触发止损区",
            "suggestion": "已进入价格止损区，优先执行风控或人工确认。",
        }

    if (
        loss_ratio >= cfg["loss_critical_ratio"]
        or (dist_stop_pct is not None and dist_stop_pct <= cfg["stop_critical_pct"])
        or (dist_be_pct is not None and dist_be_pct <= 0)
    ):
        return {
            "level": "critical",
            "label": "🔴 红灯",
            "color": "#c62828",
            "title": "接近硬风控",
            "suggestion": "接近止损/盈亏平衡失守，建议今晚重点盯盘，必要时提前减仓。",
        }

    if (
        loss_ratio >= cfg["loss_alert_ratio"]
        or (dist_short_pct is not None and dist_short_pct <= 0)
        or (dist_short_pct is not None and dist_short_pct <= cfg["short_alert_pct"])
        or (dist_be_pct is not None and dist_be_pct <= cfg["breakeven_alert_pct"])
        or (dist_stop_pct is not None and dist_stop_pct <= cfg["stop_warn_pct"])
    ):
        return {
            "level": "alert",
            "label": "🟠 橙灯",
            "color": "#ef6c00",
            "title": "严肃监控区",
            "suggestion": "短腿附近压力较大，禁止同标的继续加仓，关注盘中方向延续。",
        }

    if (
        loss_ratio >= cfg["loss_warn_ratio"]
        or (dist_short_pct is not None and dist_short_pct <= cfg["short_warn_pct"])
        or (dist_be_pct is not None and dist_be_pct <= cfg["breakeven_warn_pct"])
    ):
        return {
            "level": "warn",
            "label": "🟡 黄灯",
            "color": "#f9a825",
            "title": "进入关注区",
            "suggestion": "组合开始受压，关注后续是否继续向短腿逼近。",
        }

    return {
        "level": "normal",
        "label": "🟢 绿灯",
        "color": "#2e7d32",
        "title": "正常持有区",
        "suggestion": "仍在舒适区，按系统纪律继续观察。",
    }


def _compute_live_pressure_summary(data=None, dry_run: bool = False) -> List[Dict]:
    """
    生成当前实盘持仓的压力分级摘要。
    输出用于日报、监控器和实盘人工盯盘。
    """
    summaries = []
    own_data = data is None
    data_obj = data or FutuDataUS()
    if own_data:
        data_obj.connect()

    try:
        import re
        from collections import defaultdict

        for asset in ASSETS:
            trader = IronCondorTraderUS(data_obj)
            trader.dry_run = dry_run
            trader.stock = {"ticker": asset["ticker"], "name": asset["name"]}
            trader.config = {
                **IC_CONFIG,
                "max_groups": asset["max_groups"],
                "hv20_threshold": asset.get("hv20_threshold", IC_CONFIG["hv20_threshold"]),
                "capital": asset["capital"],
            }

            current_price = trader.get_current_price()
            positions = trader._get_positions_with_expiry()
            if not positions:
                continue

            grouped = defaultdict(list)
            for pos in positions:
                grouped[pos.get("expiry")].append(pos)

            for expiry, legs in grouped.items():
                parsed = {
                    "sell_put": None,
                    "buy_put": None,
                    "sell_call": None,
                    "buy_call": None,
                }
                net_premium_per_share = 0.0
                unrealized_pl = 0.0
                qty_list = []
                strike_by_code = {}

                for leg in legs:
                    code = leg.get("code", "")
                    qty = int(leg.get("qty", 0) or 0)
                    if qty == 0:
                        continue
                    qty_list.append(abs(qty))
                    unrealized_pl += float(leg.get("unrealized_pl", 0.0) or 0.0)

                    m = re.search(r"([CP])(\d+)$", code)
                    if not m:
                        continue
                    option_type = m.group(1)
                    strike = int(m.group(2)) / 1000.0
                    strike_by_code[code] = strike
                    if option_type == "P":
                        if qty < 0:
                            parsed["sell_put"] = strike
                            net_premium_per_share += float(leg.get("cost_price", 0.0) or 0.0)
                        else:
                            parsed["buy_put"] = strike
                            net_premium_per_share -= float(leg.get("cost_price", 0.0) or 0.0)
                    else:
                        if qty < 0:
                            parsed["sell_call"] = strike
                            net_premium_per_share += float(leg.get("cost_price", 0.0) or 0.0)
                        else:
                            parsed["buy_call"] = strike
                            net_premium_per_share -= float(leg.get("cost_price", 0.0) or 0.0)

                if not qty_list:
                    continue

                groups = min(qty_list)
                imbalanced = len(legs) != 4 or len(set(qty_list)) != 1 or any(v is None for v in parsed.values())
                sell_put = float(parsed["sell_put"] or 0.0)
                buy_put = float(parsed["buy_put"] or 0.0)
                sell_call = float(parsed["sell_call"] or 0.0)
                buy_call = float(parsed["buy_call"] or 0.0)
                put_w = max(sell_put - buy_put, 0.0)
                call_w = max(buy_call - sell_call, 0.0)
                wing = max(put_w, call_w, 0.0)
                max_profit = max(net_premium_per_share * 100 * groups, 0.0)
                max_loss = max(wing * 100 * groups - max_profit, 0.0)
                be_lower = sell_put - net_premium_per_share if sell_put else None
                be_upper = sell_call + net_premium_per_share if sell_call else None
                stop_put = sell_put - 0.5 * put_w if put_w > 0 else None
                stop_call = sell_call + 0.5 * call_w if call_w > 0 else None

                side = "上侧"
                dist_short_pct = dist_be_pct = dist_stop_pct = None
                if current_price and sell_put and sell_call:
                    upper_short = (sell_call - current_price) / current_price
                    lower_short = (current_price - sell_put) / current_price
                    side = "上侧" if upper_short <= lower_short else "下侧"
                    if side == "上侧":
                        dist_short_pct = upper_short
                        dist_be_pct = ((be_upper - current_price) / current_price) if be_upper else None
                        dist_stop_pct = ((stop_call - current_price) / current_price) if stop_call else None
                    else:
                        dist_short_pct = lower_short
                        dist_be_pct = ((current_price - be_lower) / current_price) if be_lower else None
                        dist_stop_pct = ((current_price - stop_put) / current_price) if stop_put else None

                loss_ratio = (max(0.0, -unrealized_pl) / max_loss) if max_loss > 0 else 0.0
                pressure = _classify_pressure_level(
                    dist_short_pct=dist_short_pct,
                    dist_be_pct=dist_be_pct,
                    dist_stop_pct=dist_stop_pct,
                    loss_ratio=loss_ratio,
                    imbalanced=imbalanced,
                )
                summaries.append({
                    "name": asset["name"],
                    "ticker": asset["ticker"],
                    "expiry": expiry.isoformat() if hasattr(expiry, "isoformat") else str(expiry or ""),
                    "groups": groups,
                    "legs": len(legs),
                    "current_price": float(current_price or 0.0),
                    "pressure_side": side,
                    "short_put": sell_put,
                    "short_call": sell_call,
                    "breakeven_lower": be_lower,
                    "breakeven_upper": be_upper,
                    "stop_put": stop_put,
                    "stop_call": stop_call,
                    "dist_short_pct": dist_short_pct,
                    "dist_be_pct": dist_be_pct,
                    "dist_stop_pct": dist_stop_pct,
                    "dist_short_str": _format_pressure_distance(dist_short_pct),
                    "dist_be_str": _format_pressure_distance(dist_be_pct),
                    "dist_stop_str": _format_pressure_distance(dist_stop_pct),
                    "unrealized_pl": round(unrealized_pl, 2),
                    "max_profit": round(max_profit, 2),
                    "max_loss": round(max_loss, 2),
                    "loss_ratio": round(loss_ratio, 4),
                    "loss_ratio_str": f"{loss_ratio:.0%}",
                    "imbalanced": imbalanced,
                    "level": pressure["level"],
                    "level_label": pressure["label"],
                    "level_color": pressure["color"],
                    "pressure_title": pressure["title"],
                    "suggestion": pressure["suggestion"],
                })
    finally:
        if own_data:
            data_obj.close()

    summaries.sort(
        key=lambda item: (
            {"critical": 3, "alert": 2, "warn": 1, "normal": 0}.get(item["level"], 0),
            -(item.get("loss_ratio", 0.0) or 0.0),
        ),
        reverse=True,
    )
    return summaries


def _round_option_price(price: float) -> float:
    """
    将期权价格四舍五入到富途API要求的精度。

    美股期权 Penny Pilot 规则（QQQ/IWM/GLD 均在内）：
      价格 < $3.00  → 最小报价单位 $0.01
      价格 >= $3.00 → 最小报价单位 $0.05（但交易所实际多为 $0.01，统一用 $0.01 安全）

    富途 API 拒绝超过2位小数的价格（如 $8.525），所以统一四舍五入到 $0.01。
    最低报价 $0.01，避免提交 $0.00。
    """
    rounded = round(price, 2)
    return max(rounded, 0.01)


def _escalate_close_price(close_side_is_buy: bool, bid: float, ask: float, round_num: int) -> float:
    """
    平仓递进价格（3轮）：
      round 0: mid 价（(bid+ask)/2）
      round 1: 75% 向市价方向（buy→ask, sell→bid）
      round 2: 市价 + 3% 缓冲（确保成交）
    """
    if bid <= 0 and ask <= 0:
        return 0.01
    mid = (bid + ask) / 2 if (bid > 0 and ask > 0) else max(bid, ask)
    if close_side_is_buy:   # 买入平仓（空头期权）→ 价格向 ask 靠拢
        levels = [mid, mid + 0.5 * (ask - mid), ask * 1.03]
    else:                    # 卖出平仓（多头期权）→ 价格向 bid 靠拢
        levels = [mid, mid - 0.5 * (mid - bid), bid * 0.97]
    return _round_option_price(levels[min(round_num, 2)])


def _escalate_open_price(open_side_is_buy: bool, bid: float, ask: float, round_num: int) -> float:
    """开仓递进价格：mid → 75%向市价 → market±3% 缓冲。"""
    if bid <= 0 and ask <= 0:
        return 0.01

    if bid <= 0:
        bid = ask
    if ask <= 0:
        ask = bid

    mid = (bid + ask) / 2 if (bid > 0 and ask > 0) else max(bid, ask, 0.01)
    if open_side_is_buy:
        levels = [mid, mid + 0.5 * (ask - mid), ask * 1.03]
    else:
        levels = [mid, mid - 0.5 * (mid - bid), bid * 0.97]
    return _round_option_price(levels[min(round_num, 2)])


class _ProcessFileLock:
    """简单文件锁，防止实盘主程序或调度器双实例并发。"""

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


# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ============ 多标的配置（当前实盘：非对称铁鹰 P3.0%/C6.0% + 2x杠杆 + 动态组数 Config F=20x）============
# 三标的相关性：QQQ-IWM 0.634，QQQ-GLD 0.248，IWM-GLD 0.342
# 分散效果：GLD 最佳对冲（与股票低相关），IWM 提供小盘分散
# 当前实盘基准（2010-2025，16年）：动态Config F=20x → 年化+38.99%，最大回撤-12.0%，夏普2.64
# 固定组数基线：年化+30.49%，最大回撤-6.49%，夏普2.63
# 2x杠杆实现：名义$30k（QQQ $18k / IWM $6k / GLD $6k），实际本金$15k + 融资$15k
# HV20阈值说明：使用纯HV20（与Finviz/富途口径一致，无×1.15通胀）
ASSETS = [
    {"ticker": "US.QQQ", "name": "QQQ", "capital": 18_000, "max_groups": 4, "hv20_threshold": 0.25},   # 纳斯达克100: 纯HV≤25%（Scenario C）
    {"ticker": "US.IWM", "name": "IWM", "capital": 6_000,  "max_groups": 2, "hv20_threshold": 0.25},   # 罗素2000小盘: 纯HV≤25%（Scenario C）
    {"ticker": "US.GLD", "name": "GLD", "capital": 6_000,  "max_groups": 2, "hv20_threshold": 0.18},   # 黄金ETF: 纯HV≤18%（Scenario C）
]

# 兼容旧代码引用（取第一个标的）
STOCK_CONFIG = {"ticker": ASSETS[0]["ticker"], "name": ASSETS[0]["name"]}

# Iron Condor 共享参数（三个标的使用相同策略参数）
IC_CONFIG = {
    "put_otm": 0.030,                  # Put侧 3.0% OTM（972组扫描最优：Scenario C P3.0%/C6.0%/W9%/DTE45）
    "call_otm": 0.060,                 # Call侧 6.0% OTM（972组扫描最优：夏普2.63, Calmar4.70）
    "otm_distance": 0.05,              # 对称OTM fallback（慢熊防御/兼容旧代码用）
    "wing_width": 0.09,                # 9% Wing（扩宽翼宽增加期权流动性，与更长DTE配合）
    "entry_mode": "pre_expiry",        # 到期前入场
    "entry_days_before_expiry": 45,    # DTE=45（月度/季度期权，更长时间价值衰减）
    "cooldown_days": 5,                # 开仓冷却期（每标的独立计算）
    "max_groups": 1,                   # fallback默认值（实际被ASSETS[x]["max_groups"]覆盖：QQQ=4, IWM=2, GLD=2）
    "min_iv": 0.0,
    "early_close_days": 2,             # 到期前2天强制平仓
    "min_premium": 30,                 # 最低权利金（IWM/GLD权利金较小，调低门槛）
    "estimated_credit_per_group": 100, # 每组估算权利金（三标的均值）
    "profit_target_pct": 0.50,         # 50%止盈目标
    "hv20_threshold": 0.25,            # HV20上限（fallback；实际由ASSETS[x]["hv20_threshold"]覆盖）
    "slow_bear_threshold_20d": -0.07,  # 慢熊检测
    "slow_bear_defense": "increase_otm",
    "slow_bear_otm_increase": 0.25,
}

# VIX / HV20 风险控制阈值（与 composite_backtest.py 回测保持一致）
VIX_HARD_STOP_HV   = 0.39   # HV20 ≥ 39%：触发硬止损，强平所有持仓（回测中 VIX_HARD_STOP_HV）
VIX_COOLDOWN_HV    = 0.28   # HV20 < 28%：硬止损解除，恢复开仓（回测中 VIX_COOLDOWN_HV）
VIX_DELEVERAGE_HV  = 0.22   # HV20 > 22%：建议将杠杆从2x降至1x（回测中 VIX_DELEVERAGE）

# 总初始本金
REAL_CAPITAL    = 15_000  # 实际投入资本（USD）
LEVERAGE        = 2.0     # 杠杆倍率（融资$15k，名义$30k）
MARGIN_RATE     = 0.055   # 融资年利率 5.5%（富途保证金利率）
INITIAL_CAPITAL = REAL_CAPITAL  # 别名，保持与旧代码兼容

# 动态组数配置（配置F=20x上限，与回测 dynamic_composite_backtest.py 对齐）
# effective_groups = base_groups × (IC_MANUAL_CAPITAL × LEVERAGE / total_initial_capital)，受 cap 限制
DYNAMIC_SIZING    = True   # 是否启用动态组数（False=固定组数，与旧行为一致）
GROUPS_CAP_MULT   = 20     # 组数上限倍数：base_groups × 20（QQQ=80, IWM=40, GLD=40）
IC_MANUAL_CAPITAL = 15_000 # ← 手动指定本金（USD），用于动态组数计算，勿依赖账户总资产 API
                            # 当 IC 专用资金变化时（如从$15K增至$20K），手动修改此值即可
OPEN_ROUND_WAIT_SECONDS = (90, 90, 60)
OPEN_REPAIR_WAIT_SECONDS = (15, 20, 30)

# 容量控制（基于当前 QQQ/IWM/GLD 期权链流动性与单腿执行方式）
CAPACITY_CONTROL = {
    "enabled": True,
    "soft_actual_capital_usd": 100_000,          # ≤$100k：当前执行架构下通常无明显流动性压力
    "auto_downgrade_to_e_actual_usd": 200_000,   # ≥$200k：自动从 F=20x 降到 E=15x
    "hard_review_actual_usd": 300_000,           # ≥$300k：已接近当前执行架构舒适上限
    "downgrade_cap_mult": 15,
    "inter_batch_sleep_sec": 2.0,
    "min_relevant_book_qty": {"QQQ": 1, "IWM": 1, "GLD": 1},
    "batch_groups": {
        "small":  {"QQQ": 8, "IWM": 4, "GLD": 4},   # < $100k
        "medium": {"QQQ": 6, "IWM": 3, "GLD": 3},   # $100k ~ $200k
        "large":  {"QQQ": 4, "IWM": 2, "GLD": 2},   # ≥ $200k
    },
}

# ============ 邮件通知 ============
EMAIL_CONFIG = {
    "smtp_server": "smtp.163.com",
    "smtp_port": 465,
    "sender": "quanyi_zk@163.com",
    "password": os.environ.get("IC_EMAIL_PASSWORD", ""),
    "recipient": "quanyi_zk@163.com",
}


class EmailNotifier:
    """美股多标的 Iron Condor 邮件通知器（自包含）"""

    def __init__(self):
        self.cfg = EMAIL_CONFIG
        self.enabled = bool(self.cfg.get("password"))

    def _send(self, subject: str, body: str) -> bool:
        if not self.enabled:
            logger.warning(f"邮件未配置，跳过: {subject}")
            return False
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.cfg["sender"]
            msg["To"] = self.cfg["recipient"]
            msg.attach(MIMEText(body, "html"))
            with smtplib.SMTP_SSL(self.cfg["smtp_server"], self.cfg["smtp_port"]) as s:
                s.login(self.cfg["sender"], self.cfg["password"])
                s.sendmail(self.cfg["sender"], self.cfg["recipient"], msg.as_string())
            logger.info("📧 邮件已发送")
            return True
        except Exception as e:
            logger.error(f"📧 邮件发送失败: {e}")
            return False

    def _ts(self) -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def send_startup(self) -> bool:
        subject = "🦅 Iron Condor 多标的策略启动（实盘 2x杠杆）"
        body = f"""
<h3>🦅 Iron Condor 非对称铁鹰策略已启动</h3>
<table border="1" cellpadding="6" style="border-collapse:collapse">
<tr><td><b>标的</b></td><td>QQQ $18k（base 4组） + IWM $6k（base 2组） + GLD $6k（base 2组）</td></tr>
<tr><td><b>动态组数</b></td><td>Config F=20x，按 IC_MANUAL_CAPITAL × LEVERAGE 等比扩仓</td></tr>
<tr><td><b>OTM（非对称）</b></td><td>Put 3.0% / Call 6.0%，Wing=9%, DTE=45</td></tr>
<tr><td><b>实际本金</b></td><td>${REAL_CAPITAL:,} USD（2x杠杆，名义$30,000）</td></tr>
<tr><td><b>融资成本</b></td><td>{MARGIN_RATE*100:.1f}%/年 = ${REAL_CAPITAL*MARGIN_RATE:,.0f}/年</td></tr>
<tr><td><b>HV20开仓阈值</b></td><td>QQQ/IWM: ≤25%，GLD: ≤18%（超过即禁止新开仓）</td></tr>
<tr><td><b>HV20降杠杆阈值</b></td><td>HV20 &gt; 22%：仅在允许开仓时，max_groups 减半</td></tr>
<tr><td><b>HV20硬止损阈值</b></td><td>HV20 ≥ 39%：强平所有持仓；HV20 &lt; 28%：恢复开仓</td></tr>
<tr><td><b>价格止损</b></td><td>标的穿入翼宽50%（short strike ± 0.5×wing）</td></tr>
<tr><td><b>资金止损</b></td><td>单标的策略权益相对峰值回撤 &gt; 5%</td></tr>
</table>
<p><b>启动时间</b>: {self._ts()}</p>
"""
        return self._send(subject, body)

    def send_open(self, expiry: str, strikes: Dict, net_premium: float,
                  groups: int, hv20: float, asset: str = "QQQ",
                  current_price: float = 0.0) -> bool:
        # ── 风险指标计算 ──────────────────────────────────
        sell_put  = strikes.get("sell_put_k", 0)
        buy_put   = strikes.get("buy_put_k", 0)
        sell_call = strikes.get("sell_call_k", 0)
        buy_call  = strikes.get("buy_call_k", 0)
        wing      = sell_put - buy_put          # 翼宽（两边对称，取Put边）
        premium_per_share = net_premium / (100 * groups) if groups else 0

        max_profit = net_premium                # 最大盈利 = 收到的权利金
        max_loss   = wing * 100 * groups - net_premium   # 最大亏损（买腿封顶）
        be_lower   = sell_put  - premium_per_share       # 下轨盈亏平衡点
        be_upper   = sell_call + premium_per_share       # 上轨盈亏平衡点
        rr_ratio   = max_profit / max_loss if max_loss > 0 else 0

        # 盈利区间宽度（相对当前价格）
        profit_zone_pct = (be_upper - be_lower) / current_price * 100 if current_price > 0 else 0

        subject = (f"✅ {asset} Iron Condor 开仓 | 到期 {expiry} | "
                   f"收 ${net_premium:.0f} / 最大亏 ${max_loss:.0f}")
        body = f"""
<h3>✅ {asset} Iron Condor 开仓成功</h3>
<table border="1" cellpadding="6" style="border-collapse:collapse;min-width:360px">
<tr style="background:#f2f2f2"><td colspan="2"><b>📋 基本信息</b></td></tr>
<tr><td>标的</td><td><b>{asset}</b>{"  当前价 ${:.2f}".format(current_price) if current_price else ""}</td></tr>
<tr><td>到期日</td><td>{expiry}</td></tr>
<tr><td>开仓时 HV20</td><td>{hv20:.1%}</td></tr>

<tr style="background:#f2f2f2"><td colspan="2"><b>📐 行权价结构</b></td></tr>
<tr><td>Put 边</td><td>Buy ${buy_put:.0f} ← Sell ${sell_put:.0f}</td></tr>
<tr><td>盈利区间</td><td><b>${sell_put:.0f} ~ ${sell_call:.0f}</b>{"  ({:.1f}% 宽)".format(profit_zone_pct) if profit_zone_pct else ""}</td></tr>
<tr><td>Call 边</td><td>Sell ${sell_call:.0f} → Buy ${buy_call:.0f}</td></tr>

<tr style="background:#f2f2f2"><td colspan="2"><b>💰 盈亏指标</b></td></tr>
<tr><td>净权利金（最大盈利）</td><td style="color:#2e7d32"><b>+${max_profit:.0f}</b></td></tr>
<tr><td>最大亏损（买腿封顶）</td><td style="color:#c62828"><b>-${max_loss:.0f}</b></td></tr>
<tr><td>盈亏比（收益/风险）</td><td><b>1 : {1/rr_ratio:.1f}</b>{"  ✅" if rr_ratio >= 0.15 else "  ⚠️"}</td></tr>
<tr><td>盈亏平衡区间</td><td>${be_lower:.0f} ~ ${be_upper:.0f}</td></tr>
</table>
<p style="color:#888;font-size:12px">
  翼宽 ${wing:.0f}（{wing/current_price*100:.1f}% of 正股价）·
  止盈目标 ${max_profit*0.5:.0f}（50%）·
  止损触发 ${max_profit*2:.0f}（2倍权利金）
</p>
<p><b>时间</b>: {self._ts()}</p>
"""
        return self._send(subject, body)

    def send_alert(self, level: str, message: str, details: str = "") -> bool:
        emoji = {"WARNING": "⚠️", "CRITICAL": "🚨"}.get(level, "ℹ️")
        subject = f"{emoji} Iron Condor 警报 | {message[:50]}"
        body = f"""
<h3>{emoji} Iron Condor 警报</h3>
<p><b>级别</b>: {level}</p>
<p><b>消息</b>: {message}</p>
{"<p><b>详情</b>: " + details + "</p>" if details else ""}
<p><b>时间</b>: {self._ts()}</p>
"""
        return self._send(subject, body)

    def send_daily_summary(self, asset_results: list) -> bool:
        """每日运行摘要，无论是否开仓都发送"""
        today = datetime.now().strftime("%Y-%m-%d")
        recent_events = _load_recent_execution_events(hours=36, limit=12)
        execution_guard_state = _load_execution_guard_state()
        live_position_summary = _compute_live_position_capacity_summary(dry_run=False)
        pressure_summary = _compute_live_pressure_summary(dry_run=False)
        capacity = build_capacity_snapshot(
            assets=ASSETS,
            actual_capital=IC_MANUAL_CAPITAL,
            leverage=LEVERAGE,
            groups_cap_mult=GROUPS_CAP_MULT,
            capacity_control=CAPACITY_CONTROL,
        )
        asset_rows = ""
        for r in asset_results:
            name    = r.get("name", "")
            action  = r.get("action", "-")
            reason  = r.get("reason", "")
            hv20    = r.get("hv20", "")
            premium = r.get("net_premium", 0)
            hv20_str = f"{hv20:.1%}" if isinstance(hv20, float) and hv20 > 0 else "-"
            premium_str = f"${premium:.0f}" if premium else "-"
            color   = "#4CAF50" if r.get("opened") else ("#FF9800" if r.get("closed") else "#555555")
            asset_rows += (
                f"<tr>"
                f"<td><b>{name}</b></td>"
                f"<td style='color:{color}'>{action}</td>"
                f"<td>{reason}</td>"
                f"<td>{hv20_str}</td>"
                f"<td>{premium_str}</td>"
                f"</tr>"
            )
        capacity_rows = ""
        for asset in capacity["per_asset"]:
            capacity_rows += (
                f"<tr>"
                f"<td><b>{asset['name']}</b></td>"
                f"<td>{asset['estimated_groups']}组 / {asset['estimated_legs']}腿</td>"
                f"<td>${asset['base_capital']:,.0f} ({asset['allocation_pct']:.0%})</td>"
                f"<td>≤{asset['batch_limit']}组/批</td>"
                f"</tr>"
            )
        live_position_rows = ""
        for item in live_position_summary:
            status = "✅ 可再开" if item["can_add"] else "⛔ 不再开"
            color = "#2e7d32" if item["can_add"] else "#c62828"
            live_position_rows += (
                f"<tr>"
                f"<td><b>{item['name']}</b></td>"
                f"<td>{item['existing_groups']}组 / {item['existing_legs']}腿</td>"
                f"<td>{item['allowed_groups']}组</td>"
                f"<td style='color:{color}'>{status}</td>"
                f"<td>{item['blocked_reason'] or '-'}</td>"
                f"</tr>"
            )
        pressure_html = ""
        if pressure_summary:
            pressure_rows = ""
            for item in pressure_summary:
                pl_color = "#2e7d32" if item["unrealized_pl"] >= 0 else "#c62828"
                pressure_rows += (
                    f"<tr>"
                    f"<td><b>{item['name']}</b></td>"
                    f"<td>${item['current_price']:.2f}</td>"
                    f"<td>{item['groups']}组 / {item['pressure_side']}</td>"
                    f"<td>{item['dist_short_str']}</td>"
                    f"<td>{item['dist_be_str']}</td>"
                    f"<td>{item['dist_stop_str']}</td>"
                    f"<td style='color:{pl_color}'>${item['unrealized_pl']:+,.0f} / {item['loss_ratio_str']}</td>"
                    f"<td style='color:{item['level_color']}'><b>{item['level_label']}</b></td>"
                    f"<td>{item['suggestion']}</td>"
                    f"</tr>"
                )
            pressure_html = f"""
<h3>🚦 持仓压力监控</h3>
<table border="1" cellpadding="6" style="border-collapse:collapse;font-family:monospace;width:100%;margin-top:8px">
<tr style="background:#f2f2f2">
  <th>标的</th><th>现价</th><th>持仓/受压侧</th><th>距短腿</th><th>距盈亏平衡</th><th>距价格止损</th><th>浮盈亏 / 最大亏损</th><th>等级</th><th>建议</th>
</tr>
{pressure_rows}
</table>
<p style="font-size:12px;color:#888">分级口径：距 short strike ≤3% 黄灯、≤1.5% 橙灯；距价格止损 ≤1.5% 或浮亏达到最大亏损 50% 红灯。</p>
"""
        guard_html = ""
        if execution_guard_state:
            guard_rows = ""
            for asset in ASSETS:
                item = execution_guard_state.get(asset["name"], {})
                level = str(item.get("level", "UNKNOWN"))
                color = "#2e7d32" if level == "OK" else "#e65100" if level == "WARNING" else "#c62828" if level == "CRITICAL" else "#555555"
                label = "✅ 正常" if level == "OK" else "⚠️ 警告" if level == "WARNING" else "🚨 严重" if level == "CRITICAL" else "-"
                guard_rows += (
                    f"<tr>"
                    f"<td><b>{asset['name']}</b></td>"
                    f"<td style='color:{color}'>{label}</td>"
                    f"<td>{item.get('mode', '-')}</td>"
                    f"<td>{str(item.get('updated_at', '-')).replace('T', ' ')}</td>"
                    f"</tr>"
                )
            guard_html = f"""
<h3>🛡️ 执行巡检健康状态</h3>
<table border="1" cellpadding="6" style="border-collapse:collapse;font-family:monospace;width:100%;margin-top:8px">
<tr style="background:#f2f2f2">
  <th>标的</th><th>状态</th><th>最近模式</th><th>最近巡检时间</th>
</tr>
{guard_rows}
</table>
<p style="font-size:12px;color:#888">Execution Guard 只负责结构完整性与状态一致性检查，不参与策略层止损/止盈判断。</p>
"""
        else:
            guard_html = """
<h3>🛡️ 执行巡检健康状态</h3>
<p style="color:#888">尚未生成 Execution Guard 状态文件；待巡检任务首次运行后，这里会显示 QQQ / IWM / GLD 的执行健康状态。</p>
"""
        cap_label = (
            f"E={capacity['cap_mult']}x（容量自动降档）"
            if capacity["auto_downgraded"]
            else f"F={capacity['cap_mult']}x"
        )
        warning_html = ""
        if capacity["auto_downgraded"]:
            warning_html += (
                f"<p style='color:#e65100'><b>容量降档</b>: 实际本金已达 "
                f"${capacity['downgrade_threshold']:,.0f}，当前有效动态上限为 {cap_label}。</p>"
            )
        if capacity["needs_review"]:
            warning_html += (
                f"<p style='color:#c62828'><b>容量复核</b>: 实际本金已达 "
                f"${capacity['review_threshold']:,.0f}，建议优先关注分批执行、腿级深度与成交冲击。</p>"
            )
        events_html = ""
        if recent_events:
            event_rows = ""
            for event in reversed(recent_events):
                color = "#c62828" if event.get("level") == "CRITICAL" else "#e65100" if event.get("level") == "WARNING" else "#555555"
                asset = event.get("asset", "-")
                ts = event.get("ts", "").replace("T", " ")
                event_rows += (
                    f"<tr>"
                    f"<td>{ts}</td>"
                    f"<td><b>{asset}</b></td>"
                    f"<td style='color:{color}'>{event.get('message', '')}</td>"
                    f"<td>{event.get('details', '')}</td>"
                    f"</tr>"
                )
            events_html = f"""
<h3>🛠️ 最近执行事件</h3>
<table border="1" cellpadding="6" style="border-collapse:collapse;font-family:monospace;width:100%">
<tr style="background:#f2f2f2">
  <th>时间</th><th>标的</th><th>事件</th><th>详情</th>
</tr>
{event_rows}
</table>
"""
        subject = f"📊 铁鹰日报 {today} | {'有开仓' if any(r.get('opened') for r in asset_results) else '无开仓'}"
        body = f"""
<h3>📊 铁鹰策略每日运行报告</h3>
<p><b>日期</b>: {today} &nbsp;|&nbsp; <b>执行时间</b>: {self._ts()}</p>
<table border="1" cellpadding="6" style="border-collapse:collapse;font-family:monospace;width:100%">
<tr style="background:#f2f2f2">
  <th>标的</th><th>操作</th><th>原因/备注</th><th>HV20</th><th>权利金</th>
</tr>
{asset_rows}
</table>
<h3>📦 当前容量与预计组数</h3>
<table border="1" cellpadding="6" style="border-collapse:collapse;font-family:monospace;width:100%">
<tr><td><b>实际本金</b></td><td>${capacity['actual_capital']:,.0f}</td><td><b>名义资金</b></td><td>${capacity['nominal_capital']:,.0f}（{capacity['leverage']:.1f}x）</td></tr>
<tr><td><b>容量档位</b></td><td>{capacity['band_label']} / 成交难度{capacity['difficulty']}</td><td><b>动态上限</b></td><td>{cap_label}</td></tr>
<tr><td><b>预计总组数</b></td><td>{capacity['total_groups']}组</td><td><b>预计总腿数</b></td><td>{capacity['total_legs']}腿</td></tr>
</table>
<table border="1" cellpadding="6" style="border-collapse:collapse;font-family:monospace;width:100%;margin-top:8px">
<tr style="background:#f2f2f2">
  <th>标的</th><th>预计组数</th><th>基准分配</th><th>单批建议</th>
</tr>
{capacity_rows}
</table>
<h3>🧮 实时持仓 vs 当前允许上限</h3>
<table border="1" cellpadding="6" style="border-collapse:collapse;font-family:monospace;width:100%;margin-top:8px">
<tr style="background:#f2f2f2">
  <th>标的</th><th>真实持仓</th><th>当前允许上限</th><th>今晚是否可再开</th><th>备注</th>
</tr>
{live_position_rows}
</table>
{warning_html}
{guard_html}
{pressure_html}
{events_html}
<p style="color:#888;font-size:12px">自动发送 · 铁鹰量化系统</p>
"""
        return self._send(subject, body)


# ============ 数据源 ============
class FutuDataUS:
    """富途美股数据源"""
    
    def __init__(self, host="127.0.0.1", port=11111):
        from futu import OpenQuoteContext
        self.quote_ctx = OpenQuoteContext(host=host, port=port)
        self.subscribed = set()
    
    def connect(self) -> bool:
        logger.info("🔌 连接富途 OpenD (127.0.0.1:11111)...")
        self.quote_ctx.start()
        time.sleep(1)
        logger.info("✅ 已连接")
        return True
    
    def get_stock_quote(self, ticker: str) -> Dict:
        """获取正股价格"""
        from futu import RET_OK
        # 先订阅
        self.quote_ctx.subscribe([ticker], ["QUOTE"])
        time.sleep(0.5)
        
        ret, data = self.quote_ctx.get_stock_quote([ticker])
        if ret == RET_OK and not data.empty:
            return {
                "last_price": float(data.iloc[0]["last_price"]),
                "open_price": float(data.iloc[0]["open_price"]),
            }
        return {}
    
    def get_option_chain(self, ticker: str) -> Optional:
        """获取期权链"""
        from futu import RET_OK, OptionType, OptionCondType
        ret, data = self.quote_ctx.get_option_chain(
            ticker, 
            option_type=OptionType.ALL,
            option_cond_type=OptionCondType.OTM,
        )
        if ret == RET_OK and not data.empty:
            return data
        return None
    
    def get_option_expiration_dates(self, ticker: str) -> List:
        """获取美股期权到期日列表"""
        from futu import RET_OK
        from datetime import timedelta
        import pytz
        # 先订阅
        self.quote_ctx.subscribe([ticker], ["QUOTE"])
        time.sleep(0.5)

        # 用美东时间作为基准，避免北京时间与 API 服务器时间不一致导致日期偏移
        et_now = datetime.now(pytz.timezone("America/New_York"))
        today_et = et_now.date()
        ret, data = self.quote_ctx.get_option_expiration_date(ticker)
        if ret == RET_OK and not data.empty:
            expiries = []
            for _, row in data.iterrows():
                # 美股返回的是距离今天（美东）的天数
                distance = int(row.get("option_expiry_date_distance", 999))
                exp = today_et + timedelta(days=distance)
                expiries.append(exp)
            return sorted(set(expiries))
        return []
    
    def subscribe(self, codes: List[str], subtypes: List[str]) -> bool:
        """订阅行情"""
        for code in codes:
            if code not in self.subscribed:
                self.quote_ctx.subscribe([code], subtypes)
                self.subscribed.add(code)
        time.sleep(0.5)
        return True
    
    def get_order_book(self, code: str) -> Dict:
        """获取摆盘（bid/ask）"""
        from futu import RET_OK
        ret, data = self.quote_ctx.get_order_book(code)
        bid = ask = 0.0
        bid_qty_10 = ask_qty_10 = 0
        if ret == RET_OK and data:
            bid_list = data.get("Bid", [])
            ask_list = data.get("Ask", [])
            if bid_list:
                bid = float(bid_list[0][0])
                for level in bid_list[:10]:
                    if isinstance(level, (list, tuple)) and len(level) >= 2:
                        try:
                            bid_qty_10 += int(float(level[1]))
                        except Exception:
                            pass
            if ask_list:
                ask = float(ask_list[0][0])
                for level in ask_list[:10]:
                    if isinstance(level, (list, tuple)) and len(level) >= 2:
                        try:
                            ask_qty_10 += int(float(level[1]))
                        except Exception:
                            pass
        return {"bid": bid, "ask": ask, "bid_qty_10": bid_qty_10, "ask_qty_10": ask_qty_10}

    def get_market_snapshot(self, codes: List[str]) -> Dict[str, Dict]:
        """批量获取期权快照（bid/ask/volume/open_interest）"""
        from futu import RET_OK
        ret, data = self.quote_ctx.get_market_snapshot(codes)
        if ret != RET_OK or data is None or data.empty:
            return {}
        result = {}
        for _, row in data.iterrows():
            code = str(row.get("code", ""))
            result[code] = {
                "bid": float(row.get("bid_price", 0) or 0),
                "ask": float(row.get("ask_price", 0) or 0),
                "volume": int(float(row.get("volume", 0) or 0)),
                "open_interest": int(float(row.get("open_interest", row.get("option_open_interest", 0)) or 0)),
            }
        return result
    
    def close(self):
        self.quote_ctx.close()


# ============ 实盘交易核心 ============
class IronCondorTraderUS:
    """美股 Iron Condor 实盘交易"""

    def __init__(self, data: FutuDataUS):
        self.data = data
        self.config = IC_CONFIG
        self.stock = STOCK_CONFIG
        self.dry_run = True  # 默认模拟模式
        self.check_interval = 300  # 5分钟检查一次（守护模式用）
        self.notifier = EmailNotifier()

    def _capacity_band(self, actual_capital: float) -> str:
        return capacity_band(actual_capital, CAPACITY_CONTROL)

    def _build_capacity_policy(self) -> Dict:
        return build_capacity_policy(
            actual_capital=IC_MANUAL_CAPITAL,
            groups_cap_mult=GROUPS_CAP_MULT,
            capacity_control=CAPACITY_CONTROL,
        )

    def _compute_group_limits(self, hv20: float) -> Dict:
        base_groups = self.config["max_groups"]
        capacity_policy = self._build_capacity_policy()
        effective_cap_mult = capacity_policy["cap_mult"]
        groups_cap = base_groups * effective_cap_mult

        if DYNAMIC_SIZING:
            total_initial = sum(a["capital"] for a in ASSETS)
            nominal_capital = IC_MANUAL_CAPITAL * LEVERAGE
            scale = nominal_capital / max(total_initial, 1)
            full_max_groups = min(groups_cap, max(base_groups, int(base_groups * scale)))
        else:
            total_initial = sum(a["capital"] for a in ASSETS)
            nominal_capital = IC_MANUAL_CAPITAL * LEVERAGE
            scale = 1.0
            full_max_groups = base_groups

        effective_max_groups = max(1, full_max_groups // 2) if hv20 > VIX_DELEVERAGE_HV else full_max_groups

        return {
            "base_groups": base_groups,
            "capacity_policy": capacity_policy,
            "groups_cap": groups_cap,
            "total_initial": total_initial,
            "nominal_capital": nominal_capital,
            "scale": scale,
            "full_max_groups": full_max_groups,
            "effective_max_groups": effective_max_groups,
            "deleveraged": effective_max_groups < full_max_groups,
        }

    def _get_batch_limit(self, asset_name: str, requested_groups: int) -> int:
        policy = self._build_capacity_policy()
        return max(1, min(requested_groups, int(policy["batch_groups"].get(asset_name, requested_groups))))

    def _enrich_leg_liquidity(self, legs: List[Dict]) -> List[Dict]:
        codes = [leg["code"] for leg in legs]
        snapshot_map = self.data.get_market_snapshot(codes)
        enriched = []
        for leg in legs:
            snap = snapshot_map.get(leg["code"], {})
            ob = self.data.get_order_book(leg["code"])
            bid = snap.get("bid", leg.get("bid_price", ob.get("bid", 0)))
            ask = snap.get("ask", leg.get("ask_price", ob.get("ask", 0)))
            mid = (bid + ask) / 2 if bid > 0 and ask > 0 else max(bid, ask, 0.01)
            spread_pct = ((ask - bid) / mid) if mid > 0 and ask >= bid else 0.0
            enriched.append({
                **leg,
                "bid_price": bid,
                "ask_price": ask,
                "volume": int(snap.get("volume", 0) or 0),
                "open_interest": int(snap.get("open_interest", 0) or 0),
                "bid_qty_10": int(ob.get("bid_qty_10", 0) or 0),
                "ask_qty_10": int(ob.get("ask_qty_10", 0) or 0),
                "spread_pct": spread_pct,
            })
        return enriched

    def _check_leg_liquidity(self, legs: List[Dict]) -> Dict:
        asset_name = self.stock.get("name", "")
        min_book = CAPACITY_CONTROL["min_relevant_book_qty"].get(asset_name, 1)
        warnings = []
        for leg in legs:
            relevant_book = leg.get("bid_qty_10", 0) if leg.get("side") == "sell" else leg.get("ask_qty_10", 0)
            if leg.get("side") == "sell" and leg.get("bid_price", 0) <= 0:
                return {"ok": False, "reason": f"{leg['code']} 无买一价"}
            if leg.get("side") == "buy" and leg.get("ask_price", 0) <= 0:
                return {"ok": False, "reason": f"{leg['code']} 无卖一价"}
            if relevant_book < min_book:
                return {"ok": False, "reason": f"{leg['code']} 盘口深度不足({relevant_book})"}
            if leg.get("volume", 0) <= 1:
                warnings.append(f"{leg['code']} volume={leg.get('volume', 0)}")
            if leg.get("open_interest", 0) == 0:
                warnings.append(f"{leg['code']} OI=0")
        return {"ok": True, "warnings": warnings}
    
    def _get_account_equity(self) -> float:
        """
        通过富途 API 读取账户总资产（现金+持仓市值），用于动态组数计算。
        返回 0.0 表示查询失败（调用方会降级为基线组数）。
        """
        from config import FUTU_CONFIG
        from futu import OpenSecTradeContext, TrdEnv, RET_OK

        try:
            trd_env = TrdEnv.SIMULATE if self.dry_run else TrdEnv.REAL
            acc_id_key = "sim_acc_id" if self.dry_run else "real_acc_id"
            acc_id = int(FUTU_CONFIG.get(acc_id_key, "281756481449956811"))

            trade_ctx = OpenSecTradeContext(
                host=FUTU_CONFIG["host"],
                port=FUTU_CONFIG["port"],
                filter_trdmarket="US",
                security_firm="FUTUSECURITIES",
            )
            ret, data = trade_ctx.accinfo_query(trd_env=trd_env, acc_id=acc_id)
            trade_ctx.close()

            if ret == RET_OK and data is not None and not data.empty:
                total_assets = float(data.iloc[0].get("total_assets", 0))
                logger.info(f"💰 账户总资产: ${total_assets:,.2f}")
                return total_assets
            else:
                logger.warning(f"⚠️ 账户查询失败: ret={ret}")
                return 0.0
        except Exception as e:
            logger.error(f"⚠️ 获取账户净值异常: {e}")
            return 0.0

    def _remaining_qty(self, tracker: Dict) -> int:
        return max(0, int(tracker["qty"]) - int(tracker.get("filled_qty", 0)))

    def _clear_tracker_order(self, tracker: Dict):
        tracker["order_id"] = None
        tracker["submitted_qty"] = 0
        tracker["last_price"] = 0.0

    def _place_open_leg_order(self, tracker: Dict, price: float, qty: int, trd_env, acc_id: int) -> Dict:
        from config import FUTU_CONFIG
        from futu import OpenSecTradeContext, OrderType, RET_OK

        delay = 0.5
        last_error = None
        for attempt in range(5):
            trade_ctx = None
            try:
                trade_ctx = OpenSecTradeContext(
                    host=FUTU_CONFIG["host"],
                    port=FUTU_CONFIG["port"],
                    security_firm="FUTUSECURITIES",
                )
                ret, data = trade_ctx.place_order(
                    code=tracker["code"],
                    price=price,
                    qty=qty,
                    trd_side=tracker["order_side"],
                    order_type=OrderType.NORMAL,
                    adjust_limit=0,
                    trd_env=trd_env,
                    acc_id=acc_id,
                )
                if ret == RET_OK:
                    return {
                        "success": True,
                        "order_id": data.iloc[0]["order_id"],
                        "price": price,
                    }
                last_error = str(data)
                if "操作过快" in last_error and attempt < 4:
                    logger.warning(
                        f"   ⚠️ {tracker['code']} 触发频率限制，{delay:.1f}秒后重试 ({attempt + 1}/5)..."
                    )
                    time.sleep(delay)
                    delay *= 2
                    continue
                return {"success": False, "order_id": None, "error": last_error}
            except Exception as e:
                last_error = str(e)
                if attempt < 4:
                    time.sleep(delay)
                    delay *= 2
                    continue
                return {"success": False, "order_id": None, "error": last_error}
            finally:
                if trade_ctx:
                    trade_ctx.close()

        return {"success": False, "order_id": None, "error": last_error or "max retries exceeded"}

    def _query_order_state(self, trade_ctx, order_id, trd_env, acc_id: int) -> Optional[Dict]:
        from futu import RET_OK

        ret, od = trade_ctx.order_list_query(
            order_id=order_id,
            trd_env=trd_env,
            acc_id=acc_id,
        )
        if ret != RET_OK or od is None or od.empty:
            return None

        row = od.iloc[0]
        status = str(row.get("order_status", ""))
        dealt_qty = int(row.get("dealt_qty", 0) or 0)
        avg_price = float(
            row.get("dealt_avg_price", row.get("price", row.get("order_price", 0))) or 0
        )
        inactive_status = {"FILLED_ALL", "11", "CANCELLED_ALL", "15", "FAILED", "21", "DELETED", "23"}
        is_filled = status in {"FILLED_ALL", "11"} or ("FILLED_ALL" in status and dealt_qty > 0)
        is_inactive = status in inactive_status or any(
            flag in status for flag in ("FILLED_ALL", "CANCELLED_ALL", "FAILED", "DELETED")
        )
        return {
            "status": status,
            "dealt_qty": dealt_qty,
            "avg_price": avg_price,
            "is_filled": is_filled,
            "is_inactive": is_inactive,
            "is_active": not is_inactive,
        }

    def _cancel_order_with_retry(self, cancel_ctx, order_id, code: str, trd_env, acc_id: int) -> bool:
        from futu import ModifyOrderOp, RET_OK

        for retry in range(3):
            try:
                ret_cancel, data = cancel_ctx.modify_order(
                    modify_order_op=ModifyOrderOp.CANCEL,
                    order_id=order_id,
                    qty=0,
                    price=0,
                    trd_env=trd_env,
                    acc_id=acc_id,
                )
                if ret_cancel == RET_OK:
                    logger.info(f"   ✅ {code} 订单已撤销")
                    return True
                err_msg = str(data)
                if "CANCELLED_ALL" in err_msg or "当前状态为CANCELLED_ALL" in err_msg:
                    logger.info(f"   ℹ️ {code} 订单已是取消状态")
                    return True
                logger.warning(f"   ⚠️ 撤单失败 ({retry + 1}/3): {code}, {err_msg}")
            except Exception as e:
                logger.warning(f"   ⚠️ 撤单异常 ({retry + 1}/3): {code}, {e}")
            time.sleep(1)
        return False

    def _repair_incomplete_condor(self, trackers: List[Dict], trd_env, acc_id: int) -> Dict:
        from config import FUTU_CONFIG
        from futu import OpenSecTradeContext

        asset_name = self.stock.get("name", "?")
        logger.warning("🧩 检测到未完成铁鹰，启动自动补腿...")
        start_msg = f"[{asset_name}] 开仓出现未完成铁鹰，启动自动补腿"
        _append_execution_event(
            event_type="repair_start",
            asset=asset_name,
            level="WARNING",
            message="启动自动补腿",
            details="开仓未 4/4 全成，系统开始自动补足缺失腿",
        )
        self.notifier.send_alert("WARNING", start_msg, "开仓未 4/4 全成，系统开始自动补足缺失腿")

        query_ctx = OpenSecTradeContext(
            host=FUTU_CONFIG["host"],
            port=FUTU_CONFIG["port"],
            security_firm="FUTUSECURITIES",
        )
        cancel_ctx = OpenSecTradeContext(
            host=FUTU_CONFIG["host"],
            port=FUTU_CONFIG["port"],
            security_firm="FUTUSECURITIES",
        )

        try:
            for tracker in trackers:
                order_id = tracker.get("order_id")
                if not order_id:
                    continue
                state = self._query_order_state(query_ctx, order_id, trd_env, acc_id)
                dealt_qty = min(
                    (state or {}).get("dealt_qty", 0),
                    int(tracker.get("submitted_qty", self._remaining_qty(tracker))),
                )
                avg_price = (state or {}).get("avg_price", tracker.get("last_price", 0.0))
                if dealt_qty > 0:
                    tracker["filled_qty"] += dealt_qty
                    tracker["filled_notional"] += dealt_qty * avg_price
                if self._remaining_qty(tracker) > 0 and state and state.get("is_active"):
                    self._cancel_order_with_retry(cancel_ctx, order_id, tracker["code"], trd_env, acc_id)
                self._clear_tracker_order(tracker)

            for tracker in trackers:
                while self._remaining_qty(tracker) > 0:
                    remaining_qty = self._remaining_qty(tracker)
                    repaired = False

                    for repair_round, wait_seconds in enumerate(OPEN_REPAIR_WAIT_SECONDS):
                        quote = self.get_bid_ask([tracker["code"]]).get(tracker["code"], {})
                        bid = quote.get("bid", tracker["leg"].get("bid_price", 0))
                        ask = quote.get("ask", tracker["leg"].get("ask_price", 0))
                        aggressive_round = min(repair_round + 1, 2)
                        repair_price = _escalate_open_price(
                            tracker["side"] == "buy",
                            bid,
                            ask,
                            aggressive_round,
                        )
                        logger.warning(
                            f"   🔧 补腿 {tracker['code']} 余量 {remaining_qty} 张 | "
                            f"第{repair_round + 1}轮 @ ${repair_price:.2f} "
                            f"(bid={bid:.2f} ask={ask:.2f})"
                        )
                        result = self._place_open_leg_order(
                            tracker,
                            repair_price,
                            remaining_qty,
                            trd_env,
                            acc_id,
                        )
                        if not result.get("success"):
                            logger.warning(
                                f"   ⚠️ 补腿提交失败: {tracker['code']} | {result.get('error', 'unknown')}"
                            )
                            continue

                        tracker["order_id"] = result["order_id"]
                        tracker["submitted_qty"] = remaining_qty
                        tracker["last_price"] = result["price"]
                        time.sleep(wait_seconds)

                        state = self._query_order_state(query_ctx, tracker["order_id"], trd_env, acc_id)
                        dealt_qty = min((state or {}).get("dealt_qty", 0), remaining_qty)
                        avg_price = (state or {}).get("avg_price", repair_price)
                        if dealt_qty > 0:
                            tracker["filled_qty"] += dealt_qty
                            tracker["filled_notional"] += dealt_qty * avg_price

                        if self._remaining_qty(tracker) <= 0:
                            logger.info(f"   ✅ {tracker['code']} 已补齐")
                            self._clear_tracker_order(tracker)
                            repaired = True
                            break

                        if state and state.get("is_active"):
                            self._cancel_order_with_retry(
                                cancel_ctx, tracker["order_id"], tracker["code"], trd_env, acc_id
                            )
                        self._clear_tracker_order(tracker)
                        logger.warning(f"   ⚠️ {tracker['code']} 补腿后仍缺 {self._remaining_qty(tracker)} 张")

                    if not repaired:
                        break

            unresolved = [tracker for tracker in trackers if self._remaining_qty(tracker) > 0]
            if unresolved:
                partial_fills = []
                for tracker in trackers:
                    if tracker.get("filled_qty", 0) <= 0:
                        continue
                    avg_price = (
                        tracker["filled_notional"] / tracker["filled_qty"]
                        if tracker["filled_qty"] > 0 else tracker.get("last_price", 0.0)
                    )
                    partial_fills.append({
                        "code": tracker["code"],
                        "dealt_qty": tracker["filled_qty"],
                        "qty": tracker["qty"],
                        "order_id": tracker.get("order_id"),
                        "status": "FULL_FILLED" if tracker["filled_qty"] >= tracker["qty"] else "PARTIAL_FILLED",
                        "side": tracker["side"],
                        "price": avg_price,
                    })
                unresolved_codes = [tracker["code"] for tracker in unresolved]
                failure_details = f"未补齐腿: {', '.join(unresolved_codes)}"
                _append_execution_event(
                    event_type="repair_failed",
                    asset=asset_name,
                    level="CRITICAL",
                    message="自动补腿失败",
                    details=failure_details,
                    extra={"partial_fills": partial_fills},
                )
                self.notifier.send_alert(
                    "CRITICAL",
                    f"[{asset_name}] 自动补腿失败",
                    failure_details,
                )
                return {
                    "success": False,
                    "reason": f"自动补腿后仍有 {len(unresolved)} 条腿未补齐",
                    "partial_fills": partial_fills,
                }

            logger.info("✅ 自动补腿完成，4条腿结构已补齐")
            repaired_codes = [tracker["code"] for tracker in trackers]
            details = f"补腿完成: {', '.join(repaired_codes)}"
            _append_execution_event(
                event_type="repair_success",
                asset=asset_name,
                level="WARNING",
                message="自动补腿成功",
                details=details,
            )
            self.notifier.send_alert(
                "WARNING",
                f"[{asset_name}] 自动补腿成功",
                details,
            )
            return {"success": True, "repaired": True, "repair_summary": details}
        finally:
            query_ctx.close()
            cancel_ctx.close()

    def check_existing_positions(self) -> tuple:
        """
        检查当前是否已有当前标的的铁鹰持仓
        返回 (group_count, total_legs) 元组
        """
        try:
            positions = self._get_positions_with_expiry()
            if not positions:
                logger.info("📋 当前无持仓")
                return (0, 0)

            from collections import defaultdict

            grouped = defaultdict(list)
            for pos in positions:
                grouped[str(pos.get("expiry") or "unknown")].append(pos)

            total_legs = len(positions)
            total_groups = 0
            imbalanced = False

            logger.info(f"📋 当前{self.stock['name']}期权持仓: {total_legs} 腿")
            for expiry, legs in grouped.items():
                abs_qtys = [abs(int(leg.get("qty", 0) or 0)) for leg in legs if int(leg.get("qty", 0) or 0) != 0]
                expiry_groups = max(abs_qtys) if abs_qtys else 0
                total_groups += expiry_groups
                distinct_qtys = sorted(set(abs_qtys))

                logger.info(
                    f"   到期 {expiry}: {len(legs)} 腿 / {expiry_groups} 组 "
                    f"(腿数量级={distinct_qtys if distinct_qtys else [0]})"
                )
                for leg in legs:
                    logger.info(f"   {leg['code']}: {leg['qty']} 张 @ {leg.get('cost_price', 'N/A')}")

                if len(legs) != 4 or len(distinct_qtys) > 1:
                    imbalanced = True

            logger.info(f"📋 当前{self.stock['name']}总计: {total_groups} 组 Iron Condor / {total_legs} 腿")

            if imbalanced:
                logger.critical("🚨🚨🚨 检测到不平衡头寸！")
                logger.critical("   可能存在残腿、数量不一致或多组结构不完整")
                logger.critical("⚠️  策略将暂停新开仓，请先手动处理不平衡头寸！")

            return (total_groups, total_legs)
        except Exception as e:
            logger.error(f"查询持仓失败: {e}")
            return (-1, -1)  # 查询失败时返回特殊值，让调用者暂停开仓

    def _evaluate_risk(self) -> Dict:
        """
        实时风险评估（集成 ic_risk_monitor）
        
        计算当前持仓的风险指标：
        - 最大盈利/亏损
        - 盈亏平衡点
        - 亏损概率
        - 盈亏比
        
        根据阈值自动触发止损/止盈
        """
        from ic_risk_monitor import calculate_ic_metrics
        
        positions = self._get_positions_with_expiry()
        if not positions:
            return {"triggered": False, "action": "HOLD", "reason": ""}
        
        # 获取当前正股价格
        current_price = self.get_current_price()
        if not current_price:
            logger.warning("⚠️ 无法获取正股价格，跳过风险评估")
            return {"triggered": False, "action": "HOLD", "reason": "无法获取股价"}
        
        # 按到期日分组计算每组风险
        from collections import defaultdict
        groups = defaultdict(list)
        for pos in positions:
            if pos.get("expiry"):
                groups[pos["expiry"]].append(pos)
        
        total_risk_info = []
        
        import re as _re
        for expiry, legs in groups.items():
            if len(legs) < 4:
                continue

            # 解析行权价和净权利金
            strikes = {}
            net_premium_per_share = 0

            for leg in legs:
                code = leg.get("code", "")
                price = leg.get("cost_price", 0)
                qty = leg.get("qty", 0)
                side = "sell" if qty < 0 else "buy"  # Futu: qty<0=空头(卖出), qty>0=多头(买入)

                # 从期权代码解析行权价（格式：US.QQQ260508C615000 → strike=615.0）
                # 代码末尾数字为行权价×1000（整数），如 C615000 = $615
                m = _re.search(r"([CP])(\d+)$", code)
                if m:
                    option_type = m.group(1)  # "C" or "P"
                    strike = int(m.group(2)) / 1000.0
                else:
                    option_type = "C" if "C" in code.upper() else "P"
                    strike = 0

                # 判断期权类型
                if option_type == "P":
                    if side == "sell":
                        strikes["sell_put"] = strike
                        net_premium_per_share += price
                    else:
                        strikes["buy_put"] = strike
                        net_premium_per_share -= price
                else:
                    if side == "sell":
                        strikes["sell_call"] = strike
                        net_premium_per_share += price
                    else:
                        strikes["buy_call"] = strike
                        net_premium_per_share -= price
            
            if len(strikes) >= 4:
                contract_count = min(
                    abs(int(leg.get("qty", 0)))
                    for leg in legs
                    if leg.get("qty", 0)
                )

                # ── 价格穿越止损（优先级高，匹配回测 stop_loss_buffer=1.5）──────
                # 回测逻辑：stop_put  = sell_put  - 0.5 × put_wing
                #           stop_call = sell_call + 0.5 × call_wing
                # 含义：标的价格穿入翼宽的50%处即平仓（空头行权价已深度受损）
                put_w  = strikes.get("sell_put", 0)  - strikes.get("buy_put", 0)
                call_w = strikes.get("buy_call", 0)  - strikes.get("sell_call", 0)
                stop_put  = strikes.get("sell_put", 0)  - 0.5 * put_w
                stop_call = strikes.get("sell_call", 0) + 0.5 * call_w
                if put_w > 0 and call_w > 0:   # 只有四腿齐全时才检查
                    if current_price <= stop_put or current_price >= stop_call:
                        direction = "下行" if current_price <= stop_put else "上行"
                        return {
                            "triggered": True,
                            "action": "CLOSE_ALL",
                            "reason": (
                                f"价格穿越止损（{direction}）: 当前${current_price:.2f}，"
                                f"止损线 ${stop_put:.2f}~${stop_call:.2f}（翼宽50%）"
                            ),
                            "details": (
                                f"到期 {expiry}：short_put=${strikes.get('sell_put',0):.2f} "
                                f"short_call=${strikes.get('sell_call',0):.2f}，"
                                f"翼宽 put={put_w:.2f}/call={call_w:.2f}"
                            )
                        }

                # 计算风险指标（用于报告与策略层止盈/止损）
                metrics = calculate_ic_metrics(
                    current_price=current_price,
                    sell_put_strike=strikes.get("sell_put", 0),
                    buy_put_strike=strikes.get("buy_put", 0),
                    sell_call_strike=strikes.get("sell_call", 0),
                    buy_call_strike=strikes.get("buy_call", 0),
                    net_premium_per_share=net_premium_per_share,
                    expiry=expiry,
                    currency="USD",
                    contract_count=contract_count,
                )

                total_risk_info.append({
                    "expiry": expiry,
                    "metrics": metrics,
                    "positions": legs,
                    "strikes": strikes,
                })

                # 打印风险报告
                m = metrics
                logger.info(f"📊 到期日 {expiry} 风险分析:")
                logger.info(f"   💰 权利金: ${m['max_profit']:.0f}")
                logger.info(f"   📈 最大盈利: +${m['max_profit']:.0f}")
                logger.info(f"   📉 最大亏损: -${m['max_loss']:.0f}")
                logger.info(f"   ⚖️ 盈亏比: 1:{m['risk_reward_ratio']:.2f}")
                logger.info(f"   🎯 盈亏平衡: ${m['breakeven_lower']:.0f} ~ ${m['breakeven_upper']:.0f}")
                logger.info(f"   🛑 价格止损: ${stop_put:.2f} / ${stop_call:.2f}（翼宽50%）")

        if not total_risk_info:
            return {"triggered": False, "action": "HOLD", "reason": ""}

        # ── 单标的权益峰值回撤止损（与回测 stop_loss_pct=0.05 对齐）─────
        stop_loss_pct  = self.config.get("stop_loss_pct", 0.05)   # 5%，与回测一致
        asset_capital  = self.config.get("capital", INITIAL_CAPITAL / len(ASSETS))
        total_unrealized_pl = sum(p.get("unrealized_pl", 0) for p in positions)
        asset_name = self.stock["name"]
        equity_info = _compute_asset_strategy_equity(
            asset_name=asset_name,
            asset_capital=asset_capital,
            unrealized_pl=total_unrealized_pl,
        )
        if self.dry_run:
            existing_peak_state = _load_asset_risk_state().get(asset_name, {})
            prev_peak_equity = float(existing_peak_state.get("peak_equity", 0.0) or 0.0)
            peak_equity = max(
                prev_peak_equity,
                equity_info["baseline_equity"],
                equity_info["current_equity"],
            )
        else:
            peak_state = _update_asset_peak_equity(
                asset_name=asset_name,
                baseline_equity=equity_info["baseline_equity"],
                current_equity=equity_info["current_equity"],
            )
            peak_equity = float(
                peak_state.get("peak_equity", equity_info["baseline_equity"])
                or equity_info["baseline_equity"]
            )
        drawdown_pct = (
            (equity_info["current_equity"] - peak_equity) / peak_equity
            if peak_equity > 0 else 0.0
        )

        if total_unrealized_pl < 0:
            if drawdown_pct <= -stop_loss_pct:
                return {
                    "triggered": True,
                    "action": "CLOSE_ALL",
                    "reason": (
                        f"权益回撤止损: 回撤 {abs(drawdown_pct)*100:.1f}% > "
                        f"{stop_loss_pct*100:.0f}%（峰值 ${peak_equity:.0f} → 当前 ${equity_info['current_equity']:.0f}）"
                    ),
                    "details": (
                        f"基线权益 ${equity_info['baseline_equity']:.0f} / "
                        f"已实现 ${equity_info['realized_pnl']:+.0f} / "
                        f"未实现 ${total_unrealized_pl:+.0f}"
                    ),
                }

        # ── 止盈（回测未建模；实盘保留作运营增强，预期提升资金效率）──
        # 50% 止盈：期权时间价值衰减后提前锁定利润，释放保证金开新仓
        # TODO: 待评估是否加入回测后纳入标准参数体系
        max_profit = max((r["metrics"]["max_profit"] for r in total_risk_info), default=0)
        profit_target_pct = self.config.get("profit_target_pct", 0.50)
        if total_unrealized_pl > 0 and max_profit > 0:
            profit_pct = total_unrealized_pl / max_profit
            if profit_pct >= profit_target_pct:
                return {
                    "triggered": True,
                    "action": "PARTIAL_CLOSE",
                    "reason": f"止盈: 盈利 {profit_pct*100:.0f}% ≥ 目标 {profit_target_pct*100:.0f}%",
                    "details": f"盈利 ${total_unrealized_pl:.0f} / 最大权利金 ${max_profit:.0f}"
                }

        return {"triggered": False, "action": "HOLD", "reason": ""}

    def get_current_price(self) -> float:
        """获取正股当前价格"""
        quote = self.data.get_stock_quote(self.stock["ticker"])
        if quote:
            return quote.get("last_price", 0)
        return 0
    
    def calculate_strikes(self, S: float, dte: int, otm: Optional[float] = None,
                          put_otm_override: float = None,
                          call_otm_override: float = None) -> Dict:
        """计算铁鹰行权价（支持非对称 put_otm / call_otm）
        otm: 可选，同时覆盖两侧OTM（兼容旧代码）
        put_otm_override/call_otm_override: 分别覆盖两侧（保留非对称，慢熊防御用）"""
        wing = self.config["wing_width"]

        if put_otm_override is not None and call_otm_override is not None:
            # 慢熊防御：按比例放大非对称 OTM，保留 put/call 比例
            put_otm = put_otm_override
            call_otm = call_otm_override
        elif otm is not None:
            # 兼容旧代码：对称覆盖
            put_otm = call_otm = otm
        else:
            # 非对称铁鹰：put 侧更近，call 侧更远
            put_otm  = self.config.get("put_otm",  self.config["otm_distance"])
            call_otm = self.config.get("call_otm", self.config["otm_distance"])

        # PUT边：sell更接近价内（行权价更高）
        buy_put_k  = round(S * (1 - put_otm  - wing), 0)  # 更虚值
        sell_put_k = round(S * (1 - put_otm),         0)  # 更接近价内

        # CALL边：sell更接近价内（行权价更低）
        sell_call_k = round(S * (1 + call_otm),         0)  # 更接近价内
        buy_call_k  = round(S * (1 + call_otm + wing),  0)  # 更虚值

        return {
            "buy_put_k": buy_put_k,
            "sell_put_k": sell_put_k,
            "sell_call_k": sell_call_k,
            "buy_call_k": buy_call_k,
            "current_price": S,
        }
    
    def find_option_codes(self, strikes: Dict, expiry: date) -> Dict:
        """通过期权链API找到对应行权价的期权代码"""
        from futu import RET_OK, OptionType
        
        codes = {}
        expiry_str = expiry.strftime("%Y-%m-%d")
        
        # 获取CALL期权链
        ret, data = self.data.quote_ctx.get_option_chain(
            self.stock["ticker"],
            option_type=OptionType.CALL,
            start=expiry_str,
            end=expiry_str,
        )
        
        if ret == RET_OK and not data.empty:
            for name, target_k in [
                ("sell_call", strikes["sell_call_k"]),
                ("buy_call", strikes["buy_call_k"]),
            ]:
                data["strike_dist"] = abs(data["strike_price"].astype(float) - target_k)
                closest = data.loc[data["strike_dist"].idxmin()]
                codes[name] = str(closest["code"])
                logger.info(f"  {name}: {closest['code']} @ ${closest['strike_price']}")
        else:
            logger.warning(f"  ⚠️ CALL期权链为空 (ret={ret}, expiry={expiry_str})")

        # 获取PUT期权链
        ret, data = self.data.quote_ctx.get_option_chain(
            self.stock["ticker"],
            option_type=OptionType.PUT,
            start=expiry_str,
            end=expiry_str,
        )

        if ret == RET_OK and not data.empty:
            for name, target_k in [
                ("sell_put", strikes["sell_put_k"]),
                ("buy_put", strikes["buy_put_k"]),
            ]:
                data["strike_dist"] = abs(data["strike_price"].astype(float) - target_k)
                closest = data.loc[data["strike_dist"].idxmin()]
                codes[name] = str(closest["code"])
                logger.info(f"  {name}: {closest['code']} @ ${closest['strike_price']}")
        else:
            logger.warning(f"  ⚠️ PUT期权链为空 (ret={ret}, expiry={expiry_str})")
        
        return codes
    
    def get_bid_ask(self, options: List[str]) -> Dict:
        """获取期权bid/ask价格"""
        prices = {}
        self.data.subscribe(options, ["ORDER_BOOK"])
        snapshot_map = self.data.get_market_snapshot(options)
        
        for code in options:
            ob = self.data.get_order_book(code)
            snap = snapshot_map.get(code, {})
            bid = snap.get("bid", ob["bid"])
            ask = snap.get("ask", ob["ask"])
            prices[code] = {
                "bid": bid,
                "ask": ask,
                "mid": round((bid + ask) / 2, 2) if bid > 0 and ask > 0 else 0,
                "volume": int(snap.get("volume", 0) or 0),
                "open_interest": int(snap.get("open_interest", 0) or 0),
                "bid_qty_10": int(ob.get("bid_qty_10", 0) or 0),
                "ask_qty_10": int(ob.get("ask_qty_10", 0) or 0),
            }
            logger.info(
                f"  {code}: bid={bid:.2f} ask={ask:.2f} "
                f"vol={prices[code]['volume']} oi={prices[code]['open_interest']} "
                f"book10={prices[code]['bid_qty_10']}/{prices[code]['ask_qty_10']}"
            )
        
        return prices
    
    def open_position(self, groups_to_open=1) -> Dict:
        """开仓 Iron Condor
        groups_to_open: 要开的组数（默认1组）"""
        ticker = self.stock["ticker"]
        
        logger.info(f"📊 计划开仓组数: {groups_to_open}")
        
        # 2. 获取正股价格
        price = self.get_current_price()
        if not price:
            logger.error("❌ 无法获取正股价格")
            return {"success": False, "reason": "无法获取正股价格"}
        
        logger.info(f"📈 {ticker} 当前价: ${price:.2f}")
        
        # 2.5 市场条件检查（HV20过滤 + 慢熊检测）
        market_cond = self._check_market_conditions()
        if not market_cond["can_open"]:
            logger.warning(f"⚠️ 市场条件不允许开仓: {market_cond['reason']}")
            return {"success": False, "reason": market_cond["reason"]}
        
        # 根据市场条件调整OTM距离（保留非对称比例）
        slow_bear_put_otm = None
        slow_bear_call_otm = None
        if market_cond["adjust_otm"] > 0:
            base_otm = self.config.get("otm_distance", 0.05)
            target_otm = market_cond["adjust_otm"]
            scale = target_otm / base_otm if base_otm > 0 else 5.0
            slow_bear_put_otm = self.config.get("put_otm", base_otm) * scale
            slow_bear_call_otm = self.config.get("call_otm", base_otm) * scale
            logger.info(
                f"🛡️ 慢熊防御：OTM按{scale:.1f}x放大，"
                f"Put {self.config.get('put_otm',0):.1%}→{slow_bear_put_otm:.1%}，"
                f"Call {self.config.get('call_otm',0):.1%}→{slow_bear_call_otm:.1%}"
            )
        
        # 3. 获取近期到期日
        expiries = self.data.get_option_expiration_dates(ticker)
        if not expiries:
            logger.error("❌ 无法获取期权到期日")
            return {"success": False, "reason": "无法获取到期日"}
        
            # 找到符合DTE的到期日（自适应：选择最接近目标DTE的）
        target_dte = self.config["entry_days_before_expiry"]
        import pytz as _pytz
        today = datetime.now(_pytz.timezone("America/New_York")).date()  # 美东日期

        # 尝试多个DTE层级（从小到大，找到第一个有流动性的）
        dte_options = [target_dte, target_dte + 7, target_dte + 14, target_dte + 21]
        
        for attempt_dte in dte_options:
            # 自适应选择最接近目标DTE的到期日
            valid_exps = [e for e in expiries if e >= today]
            if valid_exps:
                target_expiry = min(valid_exps, key=lambda e: abs((e - today).days - attempt_dte))
                actual_dte = (target_expiry - today).days
            else:
                continue
            
            logger.info(f"📅 尝试到期日: {target_expiry} (DTE={actual_dte})")
            
            # 4. 计算行权价
            strikes = self.calculate_strikes(
                price, actual_dte,
                put_otm_override=slow_bear_put_otm,
                call_otm_override=slow_bear_call_otm,
            )
            logger.info(f"  行权价: PUT {strikes['buy_put_k']}/{strikes['sell_put_k']} | CALL {strikes['sell_call_k']}/{strikes['buy_call_k']}")
            
            # 5. 获取期权代码
            codes = self.find_option_codes(strikes, target_expiry)
            logger.info(f"  期权代码: {codes}")
            
            # 6. 获取bid/ask
            # 期权代码必须找齐4条腿，否则直接认定无流动性
            if len(codes) < 4:
                logger.warning(f"⚠️ DTE={actual_dte} 期权代码不完整({len(codes)}/4)，尝试更长周期...")
                continue

            prices = self.get_bid_ask(list(codes.values()))

            # 检查是否有有效价格（必须有bid价格，否则无流动性）
            valid = bool(prices) and all(p.get("bid", 0) > 0 or p.get("ask", 0) > 0 for p in prices.values())
            if not valid:
                logger.warning(f"⚠️ DTE={actual_dte} 无流动性，尝试更长周期...")
                continue
            
            # 找到一个有流动性的就 break
            logger.info(f"✅ 找到流动性好的期权 DTE={actual_dte}")
            break
        else:
            # 所有DTE都试过了还是没流动性
            logger.warning("⚠️ 所有DTE都没有流动性，跳过开仓")
            return {"success": False, "reason": "期权无流动性"}
        
        # 7. 构建订单
        legs = []
        for name, code in codes.items():
            side = "buy" if "buy" in name else "sell"
            leg_type = name.split("_")[1]
            p = prices.get(code, {})
            # 价格策略：sell用bid（确保成交），buy用ask
            if side == "sell":
                # 卖出用买一价，四舍五入到富途要求精度
                order_price = _round_option_price(p.get("bid", p.get("mid", 0.01)))
            else:
                # 买入用卖一价，四舍五入到富途要求精度
                order_price = _round_option_price(p.get("ask", p.get("mid", 0.01)))

            # bid=0 的腿无法交易，跳过
            if side == "sell" and p.get("bid", 0) <= 0:
                logger.warning(f"⚠️ {code} 无买一价（bid=0），无流动性")
                return {"success": False, "reason": f"{code} 无流动性"}

            legs.append({
                "code": code,
                "side": side,           # buy/sell
                "type": leg_type,       # put/call
                "order_price": order_price,
                "bid_price": p.get("bid", 0),
                "ask_price": p.get("ask", 0),
                "volume": p.get("volume", 0),
                "open_interest": p.get("open_interest", 0),
                "bid_qty_10": p.get("bid_qty_10", 0),
                "ask_qty_10": p.get("ask_qty_10", 0),
                "expiry": str(target_expiry),
            })

        legs = self._enrich_leg_liquidity(legs)
        liquidity_check = self._check_leg_liquidity(legs)
        if not liquidity_check.get("ok"):
            logger.warning(f"⚠️ 流动性闸门拦截: {liquidity_check.get('reason')}")
            return {"success": False, "reason": f"流动性不足: {liquidity_check.get('reason')}"}
        if liquidity_check.get("warnings"):
            logger.warning(f"⚠️ 腿级流动性预警: {'; '.join(liquidity_check['warnings'])}")

        # 8. 计算权利金（使用 side 字段，不依赖列表索引顺序）
        sell_credits = sum(leg["order_price"] for leg in legs if leg["side"] == "sell")
        buy_debits   = sum(leg["order_price"] for leg in legs if leg["side"] == "buy")
        net_premium = (sell_credits - buy_debits) * 100  # 1手=100股
        total_premium = net_premium * groups_to_open  # 总权利金

        logger.info(f"💰 单组权利金: ${net_premium:.2f}")
        logger.info(f"💰 预估总权利金 ({groups_to_open}组): ${total_premium:.2f}")

        # 9. 最低权利金检查（检查总权利金）
        min_premium = self.config.get("min_premium", 100)
        if total_premium < min_premium:
            logger.warning(f"⚠️ 总权利金 ${total_premium:.2f} < 最低 ${min_premium}，跳过开仓")
            return {"success": False, "reason": f"总权利金 ${total_premium:.2f} 低于最低 ${min_premium}"}

        # 10. 执行下单或模拟
        if self.dry_run:
            logger.info("\n⚠️ 模拟模式，不执行真实下单")
            batch_limit = self._get_batch_limit(self.stock.get("name", ""), groups_to_open)
            return {
                "success": True,
                "dry_run": True,
                "strikes": strikes,
                "expiry": str(target_expiry),
                "codes": codes,
                "prices": prices,
                "net_premium": total_premium,
                "legs": legs,
                "batch_limit": batch_limit,
            }
        else:
            asset_name = self.stock.get("name", "")
            batch_limit = self._get_batch_limit(asset_name, groups_to_open)
            if groups_to_open > batch_limit:
                logger.warning(f"⚠️ [{asset_name}] 触发分批开仓: {groups_to_open}组 → 每批{batch_limit}组")

            remaining = groups_to_open
            batch_results = []
            total_net_premium = 0.0
            repair_notes = []
            while remaining > 0:
                batch_groups = min(remaining, batch_limit)
                logger.info(f"[{asset_name}] 🚚 执行批次: {batch_groups}组（剩余 {remaining}组）")
                batch_result = self.execute_orders(legs, batch_groups)
                batch_results.append(batch_result)
                if batch_result.get("repair_summary"):
                    repair_notes.append(batch_result["repair_summary"])
                if not batch_result.get("success"):
                    logger.error(f"[{asset_name}] ❌ 批次失败，停止后续批次")
                    if not total_net_premium:
                        return batch_result
                    return {
                        "success": False,
                        "reason": batch_result.get("reason", "分批开仓失败"),
                        "partial_success": True,
                        "batch_results": batch_results,
                        "net_premium": total_net_premium,
                    }
                total_net_premium += batch_result.get("net_premium", 0)
                remaining -= batch_groups
                if remaining > 0:
                    time.sleep(CAPACITY_CONTROL["inter_batch_sleep_sec"])

            result = {
                "success": True,
                "batch_results": batch_results,
                "net_premium": total_net_premium,
                "repair_summary": "；".join(repair_notes) if repair_notes else "",
            }
            if result.get("success"):
                self.notifier.send_open(
                    expiry=str(target_expiry),
                    strikes=strikes,
                    net_premium=result.get("net_premium", 0),
                    groups=groups_to_open,
                    hv20=market_cond.get("hv20", 0.0),
                    asset=self.stock.get("name", ""),
                    current_price=price,
                )
                # ── 实盘绩效持久化：记录开仓元数据 ──────────────────
                asset_name = self.stock.get("name", "")
                _save_open_trade(asset_name, {
                    "entry_date": date.today().isoformat(),
                    "expiry": str(target_expiry),
                    "sell_put":  strikes.get("sell_put_k", 0),
                    "sell_call": strikes.get("sell_call_k", 0),
                    "buy_put":   strikes.get("buy_put_k", 0),
                    "buy_call":  strikes.get("buy_call_k", 0),
                    "groups":    groups_to_open,
                    "net_credit": result.get("net_premium", 0),
                })
                _append_trade_history({
                    "date":     date.today().isoformat(),
                    "time":     datetime.now().strftime("%H:%M:%S"),
                    "asset":    asset_name,
                    "action":   "OPEN",
                    "expiry":   str(target_expiry),
                    "sell_put":  strikes.get("sell_put_k", 0),
                    "sell_call": strikes.get("sell_call_k", 0),
                    "buy_put":   strikes.get("buy_put_k", 0),
                    "buy_call":  strikes.get("buy_call_k", 0),
                    "groups":    groups_to_open,
                    "net_premium": result.get("net_premium", 0),
                    "days_held": 0,
                    "realized_pnl": "",
                    "close_reason": "",
                })
                equity_info = _compute_asset_strategy_equity(
                    asset_name=asset_name,
                    asset_capital=self.config.get("capital", INITIAL_CAPITAL / len(ASSETS)),
                    unrealized_pl=0.0,
                )
                _update_asset_peak_equity(
                    asset_name=asset_name,
                    baseline_equity=equity_info["baseline_equity"],
                    current_equity=equity_info["current_equity"],
                )
                logger.info(f"📝 [{asset_name}] 开仓记录已写入 trade_history.csv")
            return result

    def execute_orders(self, legs: List[Dict], groups_to_open=1) -> Dict:
        """
        执行4条腿的下单（美股版）
        groups_to_open: 要开的组数（默认1组）

        价格策略（3轮）：
          第1轮：中间价 (bid+ask)/2
          第2轮：偏激进中间价（向市价推进 75%）
          第3轮：buy→ask*1.03 / sell→bid*0.97

        若仍未 4/4 全成，则自动进入补腿流程，优先补足缺失腿，避免残腿暴露。
        """
        from config import FUTU_CONFIG
        from futu import OpenSecTradeContext, TrdSide, TrdEnv

        logger.info("\n🚀 开始执行下单（3轮递进 + 自动补腿）...")

        acc_id = int(FUTU_CONFIG.get("real_acc_id", "281756481449956811"))
        trd_env = TrdEnv.REAL

        logger.info(f"📋 使用账户: {acc_id} (REAL)")

        trackers = []
        for leg in legs:
            code = leg["code"]
            side = leg["side"]
            order_side = TrdSide.SELL if side == "sell" else TrdSide.BUY
            bid = leg.get("bid_price", leg.get("bid", 0.0))
            ask = leg.get("ask_price", leg.get("ask", 0.0))
            trackers.append({
                "leg": leg,
                "code": code,
                "side": side,
                "qty": groups_to_open,
                "order_side": order_side,
                "filled_qty": 0,
                "filled_notional": 0.0,
                "order_id": None,
                "submitted_qty": 0,
                "last_price": 0.0,
                "bid": bid,
                "ask": ask,
            })

        pending = list(trackers)
        round_labels = ["第1轮(mid价)", "第2轮(偏激进)", "第3轮(市价缓冲)"]
        partial_detected = False

        monitor_ctx = OpenSecTradeContext(
            host=FUTU_CONFIG["host"],
            port=FUTU_CONFIG["port"],
            security_firm="FUTUSECURITIES",
        )
        cancel_ctx = OpenSecTradeContext(
            host=FUTU_CONFIG["host"],
            port=FUTU_CONFIG["port"],
            security_firm="FUTUSECURITIES",
        )

        try:
            for round_num, wait_seconds in enumerate(OPEN_ROUND_WAIT_SECONDS):
                if not pending:
                    break

                logger.info(f"📝 开仓{round_labels[round_num]}：提交 {len(pending)} 条腿")
                quote_map = self.get_bid_ask([tracker["code"] for tracker in pending])
                next_pending = []

                for tracker in pending:
                    remaining_qty = self._remaining_qty(tracker)
                    quote = quote_map.get(tracker["code"], {})
                    bid = quote.get("bid", tracker["bid"])
                    ask = quote.get("ask", tracker["ask"])
                    tracker["bid"] = bid
                    tracker["ask"] = ask
                    order_price = _escalate_open_price(tracker["side"] == "buy", bid, ask, round_num)
                    result = self._place_open_leg_order(tracker, order_price, remaining_qty, trd_env, acc_id)
                    if result.get("success"):
                        tracker["order_id"] = result["order_id"]
                        tracker["submitted_qty"] = remaining_qty
                        tracker["last_price"] = result["price"]
                        logger.info(
                            f"   ✅ {tracker['code']} 已提交: {tracker['order_id']} "
                            f"@ ${result['price']:.2f} x {remaining_qty}"
                        )
                    else:
                        logger.error(f"   ❌ {tracker['code']} 提交失败: {result.get('error', 'unknown')}")
                    next_pending.append(tracker)
                    time.sleep(0.3)

                pending = next_pending
                logger.info(f"⏳ {round_labels[round_num]} 等待 {wait_seconds}s 成交...")
                time.sleep(wait_seconds)

                round_pending = []
                filled_count = 0
                for tracker in pending:
                    if not tracker.get("order_id"):
                        round_pending.append(tracker)
                        continue

                    state = self._query_order_state(monitor_ctx, tracker["order_id"], trd_env, acc_id)
                    if not state:
                        logger.warning(f"   ⚠️ 无法查询 {tracker['code']} 成交状态，转入下一阶段")
                        if round_num < len(OPEN_ROUND_WAIT_SECONDS) - 1:
                            self._cancel_order_with_retry(cancel_ctx, tracker["order_id"], tracker["code"], trd_env, acc_id)
                            self._clear_tracker_order(tracker)
                        round_pending.append(tracker)
                        continue

                    dealt_qty = min(state["dealt_qty"], tracker["submitted_qty"])
                    if dealt_qty > 0:
                        tracker["filled_qty"] += dealt_qty
                        tracker["filled_notional"] += dealt_qty * state["avg_price"]

                    remaining_qty = self._remaining_qty(tracker)
                    if remaining_qty <= 0:
                        filled_count += 1
                        logger.info(
                            f"   ✅ {tracker['code']} 已全成 ({tracker['filled_qty']}/{tracker['qty']}) "
                            f"@ ${state['avg_price']:.2f}"
                        )
                        self._clear_tracker_order(tracker)
                        continue

                    if dealt_qty > 0:
                        partial_detected = True
                        logger.warning(f"   ⚠️ {tracker['code']} 部分成交: {tracker['filled_qty']}/{tracker['qty']}")
                        round_pending.append(tracker)
                        continue

                    logger.warning(
                        f"   ⚠️ {tracker['code']} 未全成 (状态={state['status']}，剩余 {remaining_qty} 张)"
                    )
                    if round_num < len(OPEN_ROUND_WAIT_SECONDS) - 1 and state.get("is_active"):
                        self._cancel_order_with_retry(cancel_ctx, tracker["order_id"], tracker["code"], trd_env, acc_id)
                        self._clear_tracker_order(tracker)
                    round_pending.append(tracker)

                if filled_count == len(trackers):
                    pending = []
                    break
                if partial_detected:
                    logger.warning("🔴 检测到部分成交，停止常规挂单并进入自动补腿")
                    pending = round_pending
                    break

                pending = round_pending

            if pending:
                repair_result = self._repair_incomplete_condor(trackers, trd_env, acc_id)
                if not repair_result.get("success"):
                    logger.critical("🚨 自动补腿后仍存在残留头寸，请立即人工复核")
                    return repair_result
                repair_summary = repair_result.get("repair_summary", "")
            else:
                repair_summary = ""
        finally:
            monitor_ctx.close()
            cancel_ctx.close()

        logger.info("✅ 4条腿全部成交！铁鹰策略建仓成功")
        submitted_results = []
        net_premium = 0.0
        for tracker in trackers:
            avg_price = (
                tracker["filled_notional"] / tracker["filled_qty"]
                if tracker["filled_qty"] > 0 else tracker.get("last_price", 0.0)
            )
            submitted_results.append({
                "code": tracker["code"],
                "order_id": tracker.get("order_id"),
                "price": avg_price,
                "success": True,
                "qty": tracker["qty"],
                "side": tracker["side"],
            })
            logger.info(f"   📊 {tracker['code']} @ ${avg_price:.2f}")
            if tracker["side"] == "sell":
                net_premium += avg_price * 100 * tracker["qty"]
            else:
                net_premium -= avg_price * 100 * tracker["qty"]

        opened_codes = [tracker["code"] for tracker in trackers]
        _add_ic_codes(opened_codes)
        logger.info(f"📝 IC 持仓代码已记录: {opened_codes}")

        return {
            "success": True,
            "legs": submitted_results,
            "net_premium": net_premium,
            "expiry": legs[0].get("expiry", "unknown"),
            "repair_summary": repair_summary,
        }

    # ============ 平仓机制（从港股脚本移植）============
    def _is_today_trading_day(self) -> bool:
        """判断今天是否为美股交易日（以美东时间为准）"""
        import pytz
        from futu import OpenQuoteContext, Market
        from config import FUTU_CONFIG

        # 美股交易日以美东时间日期为准，不能用本机北京时间
        et_today = datetime.now(pytz.timezone("America/New_York")).date()

        quote_ctx = OpenQuoteContext(host=FUTU_CONFIG["host"], port=FUTU_CONFIG["port"])
        ret, data = quote_ctx.request_trading_days(
            market=Market.US,
            start=et_today.isoformat(),
            end=et_today.isoformat(),
        )
        quote_ctx.close()

        # request_trading_days 返回可能是 list 或 DataFrame，需要兼容处理
        if ret == 0:
            if hasattr(data, 'empty'):  # DataFrame
                is_trading = not data.empty
            else:  # list
                is_trading = len(data) > 0

            if is_trading:
                logger.info(f"📅 今日（美东）{et_today} 是美股交易日")
                return True
        logger.info(f"🔴 今日（美东）{et_today} 非美股交易日（节假日或周末），跳过")
        return False

    def _get_positions_with_expiry(self) -> List[Dict]:
        """
        获取 IC 策略自己开的期权持仓（通过 ic_open_codes.json 精确匹配）。
        不会误读账户中其他标的的 Wheel Sell Put / Covered Call。

        注意：
        - dry-run 也读取真实账户持仓
        - dry-run 只做演练，不会真实下单
        """
        import re
        from futu import OpenSecTradeContext, TrdEnv
        from config import FUTU_CONFIG

        positions = []
        try:
            trd_env = TrdEnv.REAL
            acc_id_key = "real_acc_id"
            acc_id = int(FUTU_CONFIG.get(acc_id_key, "281756481449956811"))

            # ── 精确过滤：只操作 IC 策略自己记录的代码 ──────────────
            ic_codes = _load_ic_codes()
            ticker_name = self.stock["ticker"].split(".")[1]
            ic_codes_this_asset = {c for c in ic_codes if ticker_name in c}

            matched = None
            max_attempts = 3 if ic_codes_this_asset else 1
            for attempt in range(1, max_attempts + 1):
                trade_ctx = OpenSecTradeContext(
                    host=FUTU_CONFIG["host"],
                    port=FUTU_CONFIG["port"],
                    filter_trdmarket="US",
                    security_firm="FUTUSECURITIES",
                )
                ret, pos_data = trade_ctx.position_list_query(
                    trd_env=trd_env,
                    acc_id=acc_id,
                    refresh_cache=True,
                )
                trade_ctx.close()

                if ret != 0 or pos_data is None or pos_data.empty:
                    matched = None
                elif ic_codes:
                    # 精确匹配：只取本标的（ticker_name）的 IC 代码，
                    # 避免 QQQ Trader 误读 IWM/GLD 代码（三标的代码混存于同一文件）
                    matched = pos_data[pos_data["code"].isin(ic_codes_this_asset)]
                else:
                    # 首次运行、追踪文件不存在时，退化为名称过滤（兼容旧行为）
                    logger.warning(
                        "⚠️ ic_open_codes.json 不存在，使用标的名称模糊过滤。"
                        "如账户中有同标的 Wheel 持仓，请手动确认后再运行。"
                    )
                    matched = pos_data[pos_data["code"].str.contains(ticker_name, na=False)]

                if matched is not None and not matched.empty:
                    break

                if ic_codes_this_asset and attempt < max_attempts:
                    logger.warning(
                        f"[{ticker_name}] ⚠️ 富途持仓查询未匹配到已记录的IC代码，"
                        f"重试 {attempt}/{max_attempts - 1}"
                    )
                    time.sleep(0.8)

            if matched is None or matched.empty:
                if ic_codes_this_asset:
                    logger.warning(
                        f"[{ticker_name}] ⚠️ ic_open_codes.json 记录了 {len(ic_codes_this_asset)} 条腿，"
                        "但富途当前持仓查询未返回匹配持仓；按0持仓返回，需人工核对是否已平仓或查询异常"
                    )
                return []

            for _, row in matched.iterrows():
                qty = int(row.get("qty", 0))
                if qty == 0:
                    continue  # 已平仓，跳过
                code = row["code"]
                m = re.search(rf"{ticker_name}(\d{{6}})([CP])(\d+)", code)
                if m:
                    try:
                        expiry = datetime.strptime(m.group(1), "%y%m%d").date()
                    except ValueError:
                        expiry = None
                else:
                    expiry = None
                positions.append({
                    "code": code,
                    "expiry": expiry,
                    "qty": qty,
                    "side": row.get("position_side", "N/A"),
                    "unrealized_pl": float(row.get("unrealized_pl", 0) or 0),
                    "cost_price": float(row.get("cost_price", 0) or 0),
                })
        except Exception as e:
            logger.error(f"获取持仓失败: {e}")

        return positions

    def _should_close_today(self) -> bool:
        """
        判断今天是否需要触发平仓（到期前1个美股交易日）
        
        使用 prev_n_trading_day 确保在正确的交易日平仓，
        避免假期导致无法平仓的问题。
        """
        early_close_days = self.config.get("early_close_days", 1)
        import pytz as _pytz
        today = datetime.now(_pytz.timezone("America/New_York")).date()  # 美东日期

        positions = self._get_positions_with_expiry()
        if not positions:
            return False

        # 按到期日分组
        expiry_set = set(p["expiry"] for p in positions if p["expiry"])
        for expiry in expiry_set:
            # 计算"到期前第 N 个美股交易日"
            close_trigger_day = self._prev_n_us_trading_day(expiry, n=early_close_days)
            days_left = (expiry - today).days
            # 实际提前了多少自然日（正常应 = early_close_days，长假时会更大）
            days_advanced = (expiry - close_trigger_day).days

            logger.info(
                f"📋 到期日 {expiry}：平仓触发日 = {close_trigger_day}，"
                f"今天 = {today}，剩余 {days_left} 自然日"
            )

            # 长假预警：实际提前超过预期
            if days_advanced > early_close_days + 1:
                msg = (
                    f"到期日 {expiry} 前有长假（连续 {days_advanced - early_close_days} 天不可交易），"
                    f"平仓触发日提前至 {close_trigger_day}（提前 {days_advanced} 自然日），"
                    f"预计损失部分 Theta（约 {days_advanced - early_close_days} 天）。"
                    f"如需手动调整，请在 {close_trigger_day} 前处理。"
                )
                logger.warning(f"📅 长假平仓预警: {msg}")
                self.notifier.send_alert("WARNING", "长假平仓预警", msg)

            # 平仓判断
            if today >= close_trigger_day:
                logger.warning(
                    f"⚠️ 今天({today}) >= 平仓触发日({close_trigger_day})，"
                    f"需要对 {expiry} 到期的持仓执行平仓！"
                )
                return True

        return False

    def _prev_n_us_trading_day(self, ref_date: date, n: int = 1) -> date:
        """
        从 ref_date 往前数第 n 个美股交易日

        例如：ref_date = 2026-05-01（到期日），n=1
          → 返回 2026-04-30（若为美股交易日），
            若30日是节假日则继续往前找到 29日……
        """
        from futu import OpenQuoteContext, Market
        from config import FUTU_CONFIG
        
        # 向前查询最多60个自然日
        look_back = 60
        start = ref_date - timedelta(days=look_back)
        end = ref_date - timedelta(days=1)
        
        quote_ctx = OpenQuoteContext(host=FUTU_CONFIG["host"], port=FUTU_CONFIG["port"])
        ret, data = quote_ctx.request_trading_days(
            market=Market.US,
            start=start.isoformat(),   # Futu API 标准参数名
            end=end.isoformat(),
        )
        quote_ctx.close()
        
        if ret != 0 or data is None:
            # API 失败时降级：往前数 n 个自然日
            logger.warning("美股交易日历获取失败，降级使用自然日")
            return ref_date - timedelta(days=n)

        # Futu returns list of dicts {"time": "YYYY-MM-DD"} or DataFrame
        rows = data if isinstance(data, list) else (
            data.to_dict("records") if hasattr(data, "to_dict") else []
        )
        trading_days = []
        for row in rows:
            try:
                if isinstance(row, dict):
                    t = row.get("time") or row.get("TIME") or row.get("calendar_date")
                elif isinstance(row, str):
                    t = row
                elif hasattr(row, "date"):
                    trading_days.append(row.date())
                    continue
                else:
                    t = str(row)
                if t:
                    trading_days.append(datetime.strptime(str(t)[:10], "%Y-%m-%d").date())
            except Exception:
                pass
        trading_days = sorted(set(trading_days))

        if not trading_days:
            logger.warning("美股交易日历获取失败，降级使用自然日")
            return ref_date - timedelta(days=n)
        
        if len(trading_days) >= n:
            return trading_days[-n]
        else:
            return ref_date - timedelta(days=n)

    def _check_holiday_risk(self) -> Optional[str]:
        """
        检测未来7天内是否有美股市场假期（工作日不可交易）。
        若距下一个假期 ≤ 3 个交易日，返回警告字符串；否则返回 None。
        """
        from futu import OpenQuoteContext, Market, RET_OK
        from config import FUTU_CONFIG
        import pytz

        et_today = datetime.now(pytz.timezone("America/New_York")).date()
        look_ahead_end = et_today + timedelta(days=7)

        try:
            quote_ctx = OpenQuoteContext(host=FUTU_CONFIG["host"], port=FUTU_CONFIG["port"])
            ret, data = quote_ctx.request_trading_days(
                market=Market.US,
                start=(et_today + timedelta(days=1)).isoformat(),
                end=look_ahead_end.isoformat(),
            )
            quote_ctx.close()
        except Exception as e:
            logger.warning(f"⚠️ 长假检查 API 异常: {e}")
            return None

        if ret != 0 or data is None:
            return None

        # 解析交易日集合
        rows = data if isinstance(data, list) else (
            data.to_dict("records") if hasattr(data, "to_dict") else []
        )
        trading_days_set = set()
        for row in rows:
            try:
                t = row.get("time") if isinstance(row, dict) else str(row)
                if t:
                    trading_days_set.add(datetime.strptime(str(t)[:10], "%Y-%m-%d").date())
            except Exception:
                pass

        # API 正常但返回空集 → 无法判断，安全起见不拦截开仓
        if not trading_days_set:
            logger.warning("⚠️ 长假检查：交易日历为空，跳过假期检测")
            return None

        # 找出未来7天中工作日但非交易日的日期（即假期）
        holiday_dates = []
        d = et_today + timedelta(days=1)
        while d <= look_ahead_end:
            if d.weekday() < 5 and d not in trading_days_set:
                holiday_dates.append(d)
            d += timedelta(days=1)

        if not holiday_dates:
            return None

        # 计算今天到第一个假期的交易日数
        first_holiday = holiday_dates[0]
        trading_days_until = sum(1 for d in trading_days_set if et_today < d < first_holiday)

        if trading_days_until <= 3:
            return (
                f"美国市场假期预警：{first_holiday} 休市，"
                f"距今仅 {trading_days_until} 个交易日，"
                f"期权流动性可能不足，跳过新开仓"
            )
        return None

    def close_all_positions(self, close_reason: str = "") -> Dict:
        """平仓当前标的的所有铁鹰期权持仓（反向下单）
        close_reason: 平仓原因（用于 trade_history.csv 记录）
        """
        from futu import OpenSecTradeContext, TrdSide, OrderType, TrdEnv, RET_OK
        from config import FUTU_CONFIG

        logger.info("=" * 50)
        logger.info(f"🔴 开始执行平仓  原因: {close_reason or '手动'}")
        logger.info("=" * 50)

        positions = self._get_positions_with_expiry()
        if not positions:
            logger.info("当前无持仓，无需平仓")
            return {"success": True, "closed": 0}

        # 记录平仓前浮盈亏（用于计算已实现盈亏）
        pre_close_pnl = sum(p.get("unrealized_pl", 0) for p in positions)
        logger.info(f"📊 平仓前浮盈亏: ${pre_close_pnl:+,.2f}")

        trd_env = TrdEnv.SIMULATE if self.dry_run else TrdEnv.REAL
        acc_id_key = "sim_acc_id" if self.dry_run else "real_acc_id"
        acc_id = int(FUTU_CONFIG.get(acc_id_key, "281756481449956811"))

        trade_ctx = None
        if not self.dry_run:
            trade_ctx = OpenSecTradeContext(
                host=FUTU_CONFIG["host"],
                port=FUTU_CONFIG["port"],
                filter_trdmarket="US",
                security_firm="FUTUSECURITIES",
            )
        closed = 0
        successfully_closed_codes: List[str] = []

        submitted_orders = []  # 记录已提交订单，用于后续成交验证

        for pos in positions:
            code = pos["code"]
            holding_qty = pos["qty"]  # 负=空头(卖出), 正=多头(买入)
            qty = abs(holding_qty)
            if qty == 0:
                continue

            # 确定平仓方向：用qty符号，比position_side字符串更可靠
            # 空头(qty<0, 卖出的期权) → 买入平仓
            # 多头(qty>0, 买入的期权) → 卖出平仓
            if holding_qty < 0:
                close_side = TrdSide.BUY
                side_label = "买入平仓"
            else:
                close_side = TrdSide.SELL
                side_label = "卖出平仓"

            # 获取实时盘口
            p = self.get_bid_ask([code])
            prices = p.get(code, {})
            bid = prices.get("bid", 0.0)
            ask = prices.get("ask", 0.0)
            raw_mid = (bid + ask) / 2 if bid > 0 and ask > 0 else 0.01
            mid = _round_option_price(raw_mid)  # 富途价格精度要求：≤2位小数

            logger.info(f"📤 {side_label} {code}  数量={qty}  价格=${mid:.2f}  (bid={bid:.2f} ask={ask:.2f})")

            if self.dry_run:
                logger.info(f"   [模拟] 平仓订单已提交")
                closed += 1
                continue

            ret, data = trade_ctx.place_order(
                code=code,
                price=mid,
                qty=qty,
                trd_side=close_side,
                order_type=OrderType.NORMAL,
                adjust_limit=0,
                trd_env=trd_env,
                acc_id=acc_id,
            )
            if ret == RET_OK:
                order_id = data.iloc[0]["order_id"]
                logger.info(f"   ✅ 平仓订单已提交: {order_id}")
                closed += 1
                successfully_closed_codes.append(code)
                submitted_orders.append({
                    "code": code, "order_id": order_id, "qty": qty,
                    "close_side_is_buy": (close_side == TrdSide.BUY),
                    "bid": bid, "ask": ask,
                })
            else:
                logger.error(f"   ❌ 平仓下单失败: {data}")

        if trade_ctx:
            trade_ctx.close()
        logger.info(f"🔴 平仓完成：共提交 {closed}/{len(positions)} 腿")

        if self.dry_run:
            logger.info("🧪 Dry-run 平仓演练完成：未修改 ic_open_codes / trade_history / cooldown 状态")
            return {"success": True, "dry_run": True, "closed": closed, "total": len(positions)}

        # ── 3轮递进价格等待成交（mid → 75%价差 → 市价+3% 缓冲）──────────
        if submitted_orders and not self.dry_run:
            from futu import ModifyOrderOp as _MOp
            verify_ctx = None
            try:
                verify_ctx = OpenSecTradeContext(
                    host=FUTU_CONFIG["host"],
                    port=FUTU_CONFIG["port"],
                    filter_trdmarket="US",
                    security_firm="FUTUSECURITIES",
                )
                pending = list(submitted_orders)  # 当前轮待验证的订单

                # 紧急平仓（止损/VIX硬止损）：直接从第2轮（75%向市价）开始，60秒/轮
                # 正常平仓（到期/止盈）：从第1轮（mid）开始，120秒/轮
                _urgent = close_reason in ("STOP_LOSS", "VIX_HARD_STOP")
                _start_round = 1 if _urgent else 0
                _round_wait  = 60 if _urgent else 120
                round_labels = ["第1轮(mid价)", "第2轮(75%价差)", "第3轮(市价+3%)"]

                for round_num in range(_start_round, 3):
                    round_label = round_labels[round_num]
                    logger.info(f"⏳ 平仓 {round_label}：等待{_round_wait}秒...")
                    time.sleep(_round_wait)

                    still_pending = []
                    for o in pending:
                        ret_q, od = verify_ctx.order_list_query(
                            order_id=o["order_id"],
                            trd_env=trd_env,
                            acc_id=acc_id,
                        )
                        if ret_q == RET_OK and not od.empty:
                            status    = str(od.iloc[0]["order_status"])
                            dealt_qty = int(od.iloc[0].get("dealt_qty", 0) or 0)
                            if dealt_qty >= o["qty"] or "FILLED_ALL" in status or status == "11":
                                logger.info(f"   ✅ {o['code']} 已成交 ({dealt_qty}张)")
                            else:
                                still_pending.append(o)
                                logger.warning(f"   ⚠️ {o['code']} 未成交 ({dealt_qty}/{o['qty']} 状态={status})")
                        else:
                            logger.warning(f"   ⚠️ 无法查询 {o['code']} 成交状态，视为未成交")
                            still_pending.append(o)

                    pending = still_pending
                    if not pending:
                        logger.info("✅ 所有平仓订单已成交")
                        break

                    if round_num < 2:
                        # 取消未成交订单，以更激进价格重新提交
                        logger.info(f"   🔄 {len(pending)} 条腿未成交，取消后以 {['第2轮','第3轮'][round_num]} 价格重新提交...")
                        new_pending = []
                        for o in pending:
                            # 1. 撤销旧订单（若撤单失败说明已成交，跳过重新提交）
                            cancel_ok = False
                            try:
                                ret_cancel, _ = verify_ctx.modify_order(
                                    modify_order_op=_MOp.CANCEL,
                                    order_id=o["order_id"],
                                    qty=0, price=0,
                                    trd_env=trd_env,
                                    acc_id=acc_id,
                                )
                                cancel_ok = (ret_cancel == RET_OK)
                            except Exception as _ce:
                                logger.warning(f"   ⚠️ 撤单异常 {o['code']}: {_ce}")
                            if not cancel_ok:
                                logger.info(f"   ℹ️ {o['code']} 撤单失败（可能已成交），跳过重新提交")
                                continue

                            # 2. 刷新盘口，以递进价格重新提交
                            fresh = self.get_bid_ask([o["code"]])
                            fp = fresh.get(o["code"], {})
                            new_bid = fp.get("bid", o["bid"])
                            new_ask = fp.get("ask", o["ask"])
                            new_price = _escalate_close_price(o["close_side_is_buy"], new_bid, new_ask, round_num + 1)
                            logger.info(f"   💱 {o['code']} 重新提交 ${new_price:.2f}  (bid={new_bid:.2f} ask={new_ask:.2f})")

                            close_side_enum = TrdSide.BUY if o["close_side_is_buy"] else TrdSide.SELL
                            ret_new, d_new = verify_ctx.place_order(
                                code=o["code"],
                                price=new_price,
                                qty=o["qty"],
                                trd_side=close_side_enum,
                                order_type=OrderType.NORMAL,
                                adjust_limit=0,
                                trd_env=trd_env,
                                acc_id=acc_id,
                            )
                            if ret_new == RET_OK:
                                o["order_id"] = d_new.iloc[0]["order_id"]
                                o["bid"] = new_bid
                                o["ask"] = new_ask
                                new_pending.append(o)
                                logger.info(f"   ✅ {o['code']} 重新提交成功: {o['order_id']}")
                            else:
                                logger.error(f"   ❌ {o['code']} 重新提交失败: {d_new}")
                        pending = new_pending
                else:
                    # for 循环未 break → 3 轮后仍有未成交
                    if pending:
                        unfilled_codes = [o["code"] for o in pending]
                        msg = f"平仓3轮后仍有 {len(unfilled_codes)} 条腿未成交: {unfilled_codes}"
                        logger.critical(f"🚨 {msg}")
                        logger.critical("   请立即在富途APP检查并手动处理！")
                        self.notifier.send_alert("CRITICAL", "平仓3轮未成交", msg)

            except Exception as e:
                logger.error(f"成交验证异常: {e}")
            finally:
                if verify_ctx:
                    verify_ctx.close()

        # ── 只从追踪文件移除已成功提交平仓的代码 ──────────────
        # 注意：下单失败的腿保留在 ic_open_codes.json，防止持仓失控
        if successfully_closed_codes:
            _remove_ic_codes(successfully_closed_codes)
            logger.info(f"📝 IC 持仓代码已清除: {successfully_closed_codes}")
        failed_codes = [p["code"] for p in positions if p["code"] not in successfully_closed_codes]
        if failed_codes:
            logger.error(f"❌ 以下腿平仓失败，仍保留在追踪文件: {failed_codes}")
            logger.error("   请手动在富途APP平仓后，再手动清理 ic_open_codes.json")

        # ── 实盘绩效持久化：记录平仓历史 ────────────────────────
        if closed > 0:
            asset_name = self.stock["name"]
            open_trade = _load_open_trade(asset_name)
            entry_date_str = open_trade.get("entry_date", "")
            days_held = 0
            if entry_date_str:
                try:
                    days_held = (date.today() - date.fromisoformat(entry_date_str)).days
                except ValueError:
                    pass
            _append_trade_history({
                "date":         date.today().isoformat(),
                "time":         datetime.now().strftime("%H:%M:%S"),
                "asset":        asset_name,
                "action":       "CLOSE",
                "expiry":       open_trade.get("expiry", ""),
                "sell_put":     open_trade.get("sell_put", ""),
                "sell_call":    open_trade.get("sell_call", ""),
                "buy_put":      open_trade.get("buy_put", ""),
                "buy_call":     open_trade.get("buy_call", ""),
                "groups":       open_trade.get("groups", ""),
                "net_premium":  open_trade.get("net_credit", ""),
                "days_held":    days_held,
                "realized_pnl": round(pre_close_pnl, 2),
                "close_reason": close_reason,
            })
            _clear_open_trade(asset_name)
            logger.info(f"📝 [{asset_name}] 平仓记录已写入 trade_history.csv  realized_pnl=${pre_close_pnl:+,.2f}")
            equity_info = _compute_asset_strategy_equity(
                asset_name=asset_name,
                asset_capital=self.config.get("capital", INITIAL_CAPITAL / len(ASSETS)),
                unrealized_pl=0.0,
            )
            _update_asset_peak_equity(
                asset_name=asset_name,
                baseline_equity=equity_info["baseline_equity"],
                current_equity=equity_info["current_equity"],
            )

        # 平仓成功后记录冷却期开始日期（匹配回测 cooldown_days=5）
        if closed > 0:
            _record_close_date(self.stock["name"])

        return {"success": True, "closed": closed, "total": len(positions)}

    def _check_market_conditions(self) -> Dict:
        """
        检查市场条件：HV20波动率过滤 + 慢熊检测
        
        返回:
            {
                "can_open": bool,      # 是否可以开仓
                "adjust_otm": float,   # 需要调整的OTM距离（0表示不调整）
                "reason": str,         # 原因描述
                "hv20": float,         # 当前HV20值
                "cumulative_20d": float, # 20日累计收益率
            }
        """
        import pandas as pd
        import numpy as np
        from futu import RET_OK, KLType
        
        ticker = self.stock["ticker"]
        today = date.today()
        start_date = (today - timedelta(days=60)).isoformat()  # 取60天数据以确保有20个交易日
        
        try:
            # 获取历史K线数据
            ret, data, next_page = self.data.quote_ctx.request_history_kline(
                code=ticker,
                start=start_date,
                end=today.isoformat(),
                ktype=KLType.K_DAY,
                max_count=100,
            )
            
            if ret != RET_OK or data is None or data.empty:
                logger.warning("⚠️ 无法获取历史K线，跳过市场条件检查")
                return {"can_open": True, "adjust_otm": 0.0, "reason": "无法获取历史数据", "hv20": 0.0, "cumulative_20d": 0.0}
            
            # 提取收盘价序列
            closes = data["close"].astype(float)
            if len(closes) < 20:
                logger.warning(f"⚠️ 历史数据不足 {len(closes)} 天，跳过市场条件检查")
                return {"can_open": True, "adjust_otm": 0.0, "reason": "历史数据不足", "hv20": 0.0, "cumulative_20d": 0.0}
            
            # 计算HV20（使用backtest_real中的historical_volatility函数）
            from backtest_real import historical_volatility
            hv20 = historical_volatility(closes, window=20)
            
            # 计算20日累计收益率
            if len(closes) >= 20:
                price_20d_ago = closes.iloc[-20]
                price_current = closes.iloc[-1]
                cumulative_20d = (price_current - price_20d_ago) / price_20d_ago
            else:
                cumulative_20d = 0.0
            
            hv20_threshold = self.config.get("hv20_threshold", 0.20)
            logger.info(
                f"📊 HV20检查: 当前={hv20:.3f}, 开仓阈值={hv20_threshold:.0%}, "
                f"降杠杆阈值={VIX_DELEVERAGE_HV:.0%}, 硬止损阈值={VIX_HARD_STOP_HV:.0%}, "
                f"20日累计收益率={cumulative_20d:.3%}"
            )
            
            # HV20过滤
            if hv20 > hv20_threshold:
                return {
                    "can_open": False,
                    "adjust_otm": 0.0,
                    "reason": f"触发开仓过滤：HV20={hv20:.1%} > 开仓阈值{hv20_threshold:.0%}",
                    "hv20": hv20,
                    "cumulative_20d": cumulative_20d,
                }
            
            # 慢熊检测
            slow_bear_threshold = self.config.get("slow_bear_threshold_20d", -0.07)
            if cumulative_20d <= slow_bear_threshold:
                defense = self.config.get("slow_bear_defense", "increase_otm")
                if defense == "pause":
                    return {
                        "can_open": False,
                        "adjust_otm": 0.0,
                        "reason": f"20日累计收益率 {cumulative_20d:.3%} ≤ 阈值 {slow_bear_threshold:.1%}（慢熊市场）",
                        "hv20": hv20,
                        "cumulative_20d": cumulative_20d,
                    }
                elif defense == "increase_otm":
                    otm_increase = self.config.get("slow_bear_otm_increase", 0.25)
                    return {
                        "can_open": True,
                        "adjust_otm": otm_increase,  # 返回需要增加的OTM距离
                        "reason": f"20日累计收益率 {cumulative_20d:.3%} ≤ 阈值 {slow_bear_threshold:.1%}（慢熊市场，增大OTM至{otm_increase:.0%}）",
                        "hv20": hv20,
                        "cumulative_20d": cumulative_20d,
                    }
            
            # 所有检查通过
            return {
                "can_open": True,
                "adjust_otm": 0.0,
                "reason": "市场条件正常",
                "hv20": hv20,
                "cumulative_20d": cumulative_20d,
            }
            
        except Exception as e:
            logger.error(f"市场条件检查异常: {e}")
            # 异常时禁止开仓：宁可错过机会，不可在未知条件下开仓
            return {"can_open": False, "adjust_otm": 0.0, "reason": f"市场条件检查异常，禁止开仓: {e}", "hv20": 0.0, "cumulative_20d": 0.0}

    def _check_stop_loss(self) -> Dict:
        """
        止损检查
        
        规则1 - 单组止损：单组亏损 > 2倍权利金时强制平仓
        规则2 - 全局止损：总亏损 > 20% 时全部平仓观望
        
        返回: {"triggered": bool, "reason": str, "details": str}
        """
        positions = self._get_positions_with_expiry()
        if not positions:
            return {"triggered": False, "reason": "", "details": ""}
        
        # 统计总未实现盈亏
        total_unrealized_pl = sum(p["unrealized_pl"] for p in positions)
        
        # 估算开仓时收到的权利金
        leg_count = len(positions)
        group_count = max(1, leg_count // 4)
        # 使用配置中的估算权利金
        estimated_credit_per_group = self.config.get("estimated_credit_per_group", 1000)
        total_estimated_credit = estimated_credit_per_group * group_count
        
        logger.info(f"📊 止损检查: 未实现亏损=${total_unrealized_pl:.2f}, 估算权利金=${total_estimated_credit:.2f}")
        
        # 规则1：单组止损（亏损 > 2倍权利金）
        if group_count > 0:
            avg_loss_per_group = abs(total_unrealized_pl) / group_count
            if avg_loss_per_group > estimated_credit_per_group * 2:
                return {
                    "triggered": True,
                    "reason": f"单组亏损 ${avg_loss_per_group:.0f} > 2倍权利金 ${estimated_credit_per_group * 2}",
                    "details": f"总亏损 ${total_unrealized_pl:.0f}，共 {group_count} 组，平均 ${avg_loss_per_group:.0f}/组"
                }
        
        # 规则2：全局止损（单标的亏损 > 20%）
        # 使用各标的独立资金（QQQ $18k / IWM $6k / GLD $6k）而非总资金
        asset_capital = self.config.get("capital", INITIAL_CAPITAL / len(ASSETS))
        total_loss_pct = abs(total_unrealized_pl) / asset_capital
        if total_loss_pct > 0.20:
            return {
                "triggered": True,
                "reason": f"标的亏损 {total_loss_pct*100:.1f}% > 止损线 20%（${asset_capital:.0f}/标的）",
                "details": f"未实现亏损 ${total_unrealized_pl:.0f}，标的资金 ${asset_capital:.0f}"
            }
        
        return {"triggered": False, "reason": "", "details": ""}

    def check_and_manage(self) -> Dict:
        """
        检查并管理单个标的的仓位（每次循环调用）

        流程：
          0. VIX硬止损检查（HV20≥39% → 强平所有持仓）
          1. 风险评估 → 止盈/止损平仓
          2. 到期前平仓检查
          3. 开仓检查
        注意：交易日校验由调用方（run_all_assets）统一做一次
        """
        ticker = self.stock["ticker"]
        name   = self.stock["name"]

        # ── VIX 硬止损检查（优先级最高，匹配回测 VIX_HARD_STOP_HV=0.39）──────
        market_cond = self._check_market_conditions()
        hv20 = market_cond.get("hv20", 0.0)

        if hv20 >= VIX_HARD_STOP_HV:
            if not self.dry_run and not _is_vix_hard_stopped(name):
                _set_vix_hard_stop(name)
            positions = self._get_positions_with_expiry()
            if positions:
                msg = f"HV20={hv20:.1%} >= {VIX_HARD_STOP_HV:.0%}，触发VIX硬止损，强平所有持仓"
                logger.critical(f"[{name}] 🚨 {msg}")
                if not self.dry_run:
                    self.notifier.send_alert("CRITICAL", f"[{name}] VIX硬止损触发", msg)
                return self.close_all_positions(close_reason="VIX_HARD_STOP")
            else:
                logger.info(f"[{name}] 🚨 VIX硬止损中（HV20={hv20:.1%}），无持仓，等待恢复")
                return {"success": True, "skipped": True,
                        "reason": f"[{name}] VIX硬止损中，等待HV20<{VIX_COOLDOWN_HV:.0%}"}

        # ── VIX 硬止损恢复检查（HV20 必须降至 28% 以下才解除，与回测对齐）──
        if _is_vix_hard_stopped(name):
            if hv20 < VIX_COOLDOWN_HV:
                if not self.dry_run:
                    _clear_vix_hard_stop(name)
                logger.info(f"[{name}] ✅ VIX恢复，HV20={hv20:.1%} < {VIX_COOLDOWN_HV:.0%}，解除硬止损")
            else:
                logger.info(
                    f"[{name}] 🚨 VIX硬止损恢复等待中，HV20={hv20:.1%} >= {VIX_COOLDOWN_HV:.0%}，"
                    f"需降至{VIX_COOLDOWN_HV:.0%}以下才恢复开仓"
                )
                return {"success": True, "skipped": True,
                        "reason": f"[{name}] VIX硬止损恢复等待（HV20={hv20:.1%}，需<{VIX_COOLDOWN_HV:.0%}）"}

        # ── 风险评估（止盈/止损）────────────────────────
        risk_result = self._evaluate_risk()
        if risk_result.get("action") == "CLOSE_ALL":
            logger.warning(f"[{name}] 🛑 触发自动止损: {risk_result['reason']}")
            if not self.dry_run:
                self.notifier.send_alert("CRITICAL", f"[{name}] 触发自动止损: {risk_result['reason']}", risk_result.get("details", ""))
            close_result = self.close_all_positions(close_reason="STOP_LOSS")
            close_result["reason"] = risk_result.get("reason", "STOP_LOSS")
            close_result["result_type"] = "close"
            return close_result
        elif risk_result.get("action") == "PARTIAL_CLOSE":
            logger.warning(f"[{name}] ⚠️ 触发提前平仓: {risk_result['reason']}")
            if not self.dry_run:
                self.notifier.send_alert("WARNING", f"[{name}] 提前平仓: {risk_result['reason']}", risk_result.get("details", ""))
            close_result = self.close_all_positions(close_reason="PROFIT_TARGET")
            close_result["reason"] = risk_result.get("reason", "PROFIT_TARGET")
            close_result["result_type"] = "close"
            return close_result

        # 注意：不再调用 _check_stop_loss()（使用估算权利金$100，易误触发）
        # _evaluate_risk() 已实现：价格穿越止损（翼宽50%）+ 单标的权益峰值回撤5%，与回测一致

        # ── 到期平仓检查 ──────────────────────────────
        if self._should_close_today():
            logger.info(f"[{name}] 🔴 触发到期平仓...")
            if not self.dry_run:
                self.notifier.send_alert("WARNING", f"[{name}] 到期前平仓触发", "持仓已到平仓触发日")
            close_result = self.close_all_positions(close_reason="EXPIRY")
            close_result["reason"] = "到期前平仓触发"
            close_result["result_type"] = "close"
            return close_result

        # ── 冷却期检查（匹配回测 cooldown_days=5：任意平仓后5天内不开新仓）──
        cooldown_days = self.config.get("cooldown_days", 5)
        cooldown_state = _load_cooldown_state()
        last_close_str = cooldown_state.get(name)
        if last_close_str:
            try:
                last_close = date.fromisoformat(last_close_str)
                days_since = (date.today() - last_close).days
                if days_since < cooldown_days:
                    remaining = cooldown_days - days_since
                    logger.info(
                        f"[{name}] ⏳ 冷却期中（{days_since}/{cooldown_days}天），"
                        f"还剩{remaining}天，跳过开仓"
                    )
                    return {"success": True, "skipped": True,
                            "reason": f"[{name}] 冷却期中（还剩{remaining}天）"}
            except ValueError:
                pass

        # ── 长假风险检查（距假期≤3个交易日时跳过开仓，邮件预警）──────
        holiday_warning = self._check_holiday_risk()
        if holiday_warning:
            logger.warning(f"[{name}] 📅 {holiday_warning}")
            if not self.dry_run:
                self.notifier.send_alert("WARNING", f"[{name}] 长假风险预警", holiday_warning)
            return {"success": True, "skipped": True, "reason": f"[{name}] 长假风险预警"}

        # ── 开仓检查 ─────────────────────────────────
        existing, total_legs = self.check_existing_positions()

        if existing == -1 or total_legs == -1:
            logger.critical(f"[{name}] 🛑 持仓查询失败，暂停新开仓！")
            return {"success": False, "skipped": True, "reason": f"[{name}] 持仓查询失败"}

        if total_legs > 0 and (total_legs % 4 != 0):
            logger.critical(f"[{name}] 🛑 不平衡头寸（{total_legs}腿），暂停新开仓！")
            return {"success": False, "skipped": True, "reason": f"[{name}] 不平衡头寸({total_legs}腿)"}

        group_limits = self._compute_group_limits(hv20)
        base_groups = group_limits["base_groups"]
        capacity_policy = group_limits["capacity_policy"]
        groups_cap = group_limits["groups_cap"]
        total_initial = group_limits["total_initial"]
        nominal_capital = group_limits["nominal_capital"]
        scale = group_limits["scale"]
        full_max_groups = group_limits["full_max_groups"]
        effective_max_groups = group_limits["effective_max_groups"]

        if self.dry_run:
            summary_reason = (
                market_cond.get("reason")
                if not market_cond.get("can_open", True)
                else (f"已有{existing}组，达到当前上限" if existing >= effective_max_groups else "可继续观察/开仓")
            )
            logger.info(
                f"[{name}] 🧭 状态摘要: 现有{existing}组 / 当前上限{effective_max_groups}组"
                f" / 结构上{'可再开' if market_cond.get('can_open', True) and existing < effective_max_groups else '不可再开'}"
                f" / 原因: {summary_reason}"
            )

        if not market_cond.get("can_open", True):
            logger.warning(f"[{name}] 🚫 {market_cond.get('reason', '市场条件不允许开仓')}")
            return {
                "success": True,
                "skipped": True,
                "reason": f"[{name}] {market_cond.get('reason', '市场条件不允许开仓')}",
            }

        # ── 开盘时间检查（仅美东 9:33 后才允许开仓）────────────
        import pytz
        et_now = datetime.now(pytz.timezone("America/New_York"))
        et_open = et_now.replace(hour=9, minute=33, second=0, microsecond=0)
        et_close = et_now.replace(hour=16, minute=0, second=0, microsecond=0)
        if not (et_open <= et_now < et_close):
            logger.info(f"[{name}] ⏰ 当前美东时间 {et_now.strftime('%H:%M')}，不在开仓窗口(09:33-16:00)，跳过开仓")
            return {"success": True, "skipped": True, "reason": f"[{name}] 非开仓时段 (ET {et_now.strftime('%H:%M')})"}

        # ── 动态组数计算（配置F=20x，与回测对齐）──────────────────
        if DYNAMIC_SIZING:
            logger.info(
                f"[{name}] 📈 动态组数: 指定本金${IC_MANUAL_CAPITAL:,}×{LEVERAGE:.0f}x"
                f"=${nominal_capital:,.0f} / 基准${total_initial:,} "
                f"= {scale:.2f}x → {full_max_groups}组 (base={base_groups}, cap={groups_cap})"
            )
            if capacity_policy.get("auto_downgraded"):
                logger.warning(
                    f"[{name}] 🛡️ 容量降档生效：实际本金 ${IC_MANUAL_CAPITAL:,.0f} ≥ "
                    f"${CAPACITY_CONTROL['auto_downgrade_to_e_actual_usd']:,.0f}，"
                    f"Config F=20x 自动降为 E=15x"
                )
            if IC_MANUAL_CAPITAL >= CAPACITY_CONTROL["hard_review_actual_usd"]:
                logger.warning(
                    f"[{name}] 🚨 当前实际本金 ${IC_MANUAL_CAPITAL:,.0f} 已接近当前执行架构舒适上限，"
                    f"请优先关注分批成交与流动性"
                )
        # ── 降杠杆控制（HV20 > 22% 时组数减半，与回测对齐）──────────
        if group_limits["deleveraged"]:
            logger.warning(
                f"[{name}] ⚠️ 触发降杠杆：HV20={hv20:.1%} > 降杠杆阈值{VIX_DELEVERAGE_HV:.0%}，"
                f"max_groups {full_max_groups}→{effective_max_groups}"
            )

        if existing >= effective_max_groups:
            logger.info(f"[{name}] ⚠️ 已有{existing}组持仓，达到上限({effective_max_groups})，跳过")
            return {"success": True, "skipped": True, "reason": f"[{name}] 已达持仓上限({effective_max_groups}组)"}

        # ── 执行开仓 ─────────────────────────────────
        groups_to_open = effective_max_groups - existing
        logger.info(f"[{name}] 📊 可开仓组数: {groups_to_open} (现有{existing}组，上限{effective_max_groups}组{'，降杠杆模式' if effective_max_groups < full_max_groups else ''})")
        result = self.open_position(groups_to_open)

        if not result.get("success") and result.get("partial_fills"):
            pf_list = result["partial_fills"]
            logger.critical(f"[{name}] 🚨 不平衡头寸警报！共 {len(pf_list)} 条残留腿，请立即在富途APP处理！")
            for pf in pf_list:
                logger.critical(f"  - {pf['code']} ({pf['side']}): {pf['dealt_qty']}/{pf['qty']}张 @ ${pf['price']}")

        return result


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="美股 Iron Condor 实盘交易")
    parser.add_argument("--dry-run", action="store_true", help="模拟模式，不真实下单")
    parser.add_argument("--once", action="store_true", help="执行一次退出")
    parser.add_argument("--daemon", action="store_true", help="常驻运行（默认）")
    args = parser.parse_args()

    # 默认模式
    if not args.daemon and not args.once:
        args.once = True

    logger.info("="*50)
    logger.info("🦅 美股 Iron Condor 实盘交易")
    logger.info("="*50)
    if args.dry_run:
        logger.info("⚠️ 模拟模式 (--dry-run)")
        logger.info("🔎 实盘演练口径：只读真实持仓/行情，不提交真实订单，不改平仓状态")
    if args.once:
        logger.info("🔄 单次执行模式 (--once)")
    if args.daemon:
        logger.info("👁️ 常驻运行模式 (--daemon)")

    run_lock = None
    if not args.dry_run:
        run_lock = _ProcessFileLock(_MAIN_RUN_LOCK_FILE)
        if not run_lock.acquire():
            logger.warning("⚠️ 已有一个实盘 main_ic_us 实例在运行，本次跳过，避免重复开仓")
            return

    # 连接数据源
    data = FutuDataUS()
    if not data.connect():
        logger.error("连接失败")
        if run_lock:
            run_lock.release()
        return

    check_interval = 300  # 5分钟

    def run_one_cycle(send_email: bool = True):
        """执行一轮检查，返回 True 表示应继续运行"""
        # ── 交易日检查 ────────────────────────────────────────────
        _trader_check = IronCondorTraderUS(data)
        _trader_check.dry_run = args.dry_run
        if not _trader_check._is_today_trading_day():
            logger.info("🔴 今日非美股交易日，本轮跳过")
            return True  # 继续运行，等待下一个交易日

        # ── 逐标的执行检查/管理 ──────────────────────────────────
        asset_results = []
        notifier = _trader_check.notifier

        for asset in ASSETS:
            logger.info("")
            logger.info(f"{'─'*50}")
            logger.info(f"[{asset['name']}] 🦅 开始处理 {asset['ticker']}")
            logger.info(f"{'─'*50}")

            trader = IronCondorTraderUS(data)
            trader.dry_run = args.dry_run
            trader.stock = {"ticker": asset["ticker"], "name": asset["name"]}
            trader.config = {**IC_CONFIG, "max_groups": asset["max_groups"], "hv20_threshold": asset.get("hv20_threshold", IC_CONFIG["hv20_threshold"]), "capital": asset["capital"]}

            result = trader.check_and_manage()

            # 收集市场条件（用于日报）
            try:
                mc = trader._check_market_conditions()
                hv20 = mc.get("hv20", 0.0)
            except Exception:
                hv20 = 0.0

            summary_entry = {"name": asset["name"], "hv20": hv20}

            if result.get("success"):
                if result.get("skipped"):
                    logger.info(f"[{asset['name']}] ⏭️ 跳过: {result.get('reason', '')}")
                    summary_entry.update({"action": "跳过", "reason": result.get("reason", ""), "opened": False, "closed": False})
                elif result.get("closed", 0):
                    logger.info(f"[{asset['name']}] 🔴 平仓完成: {result.get('reason', '')}")
                    summary_entry.update({
                        "action": "🔴 平仓",
                        "reason": result.get("reason", "平仓完成"),
                        "opened": False,
                        "closed": True,
                    })
                else:
                    net_premium = result.get("net_premium", 0)
                    repair_summary = result.get("repair_summary", "")
                    reason = f"到期日={result.get('expiry','N/A')}"
                    if repair_summary:
                        reason += f"｜{repair_summary}"
                    logger.info(f"[{asset['name']}] ✅ 流程完成  到期日={result.get('expiry','N/A')}  权利金=${net_premium:.2f}")
                    summary_entry.update({"action": "✅ 开仓", "reason": reason, "net_premium": net_premium, "opened": True, "closed": False})
            else:
                logger.warning(f"[{asset['name']}] ⚠️ 未执行: {result.get('reason','')}")
                closed = "close" in str(result.get("reason", "")).lower() or result.get("closed", False)
                summary_entry.update({"action": "🔴 平仓" if closed else "⚠️ 未开仓", "reason": result.get("reason", ""), "opened": False, "closed": closed})

            asset_results.append(summary_entry)

        # ── 日报邮件 ──────────────────────────────────────────────
        if send_email and not args.dry_run:
            notifier.send_daily_summary(asset_results)

        return True

    try:
        if args.daemon:
            # 实盘启动通知（仅一次）
            if not args.dry_run:
                IronCondorTraderUS(data).notifier.send_startup()

            cycle = 0
            last_email_date = None  # 记录上次发邮件的日期，每天只发一次
            while True:
                cycle += 1
                now = datetime.now()
                logger.info(f"🔄 [Daemon] 第 {cycle} 轮检查 {now.strftime('%Y-%m-%d %H:%M:%S')}")
                try:
                    today = now.date()
                    should_email = (today != last_email_date)  # 每天首轮才发日报
                    run_one_cycle(send_email=should_email)
                    if should_email:
                        last_email_date = today
                except Exception as e:
                    logger.error(f"❌ 本轮异常: {e}", exc_info=True)
                # 非交易时段（周末/深夜美股休市）拉长间隔至30分钟，减少空转
                hour_utc8 = datetime.now().hour
                is_us_session = 21 <= hour_utc8 or hour_utc8 < 6  # 美股交易时段（北京时间）
                sleep_sec = check_interval if is_us_session else 1800
                logger.info(f"⏳ 等待 {sleep_sec} 秒后进行下一轮检查...")
                time.sleep(sleep_sec)
        else:
            # --once 模式（默认）
            if not args.dry_run:
                IronCondorTraderUS(data).notifier.send_startup()
            run_one_cycle(send_email=True)

    finally:
        data.close()
        if run_lock:
            run_lock.release()


if __name__ == "__main__":
    main()
