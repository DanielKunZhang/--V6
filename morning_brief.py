#!/usr/bin/env python3
"""
Morning Brief — 每日早间一屏总览（全投资体系版）
运行时间：北京时间 09:00（在 v6_daily_report_runner 08:30 之后）

覆盖域：
- [V6]       reconciliation状态 + managed positions + 换仓信号
- [价值投资]  全资产口径持仓监控（从 26年阶段性组合策略计划.html 读取，用户定期手动更新）
- [估值]      事件日历（财报/重要日期）
- [Radar]     K线额度状态，V6-B待办
- [待办]      AI_COLLAB_LOG.md 中各域待办事项

用法：
  python3 morning_brief.py              # 生成 + 发送邮件
  python3 morning_brief.py --no-email   # 只打印，不发邮件
"""

from __future__ import annotations

import argparse
import csv
import importlib
import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT            = Path(__file__).resolve().parent
COLLAB_LOG      = ROOT / "AI_COLLAB_LOG.md"
EVENTS_CAL      = ROOT / "events_calendar.json"
DECISION_LOG    = Path("/Users/zhangkun/Desktop/AI个人投资公司/交易决策日志/decision_log.csv")
FRIEND_ALPHA_LOG = Path("/Users/zhangkun/Desktop/AI个人投资公司/朋友Alpha影子跟踪/friend_alpha_shadow_log.csv")
X_RADAR_DAILY   = Path("/Users/zhangkun/Desktop/AI个人投资公司/信息源扫描/X_Radar/daily")
V6A_STATE       = ROOT / "backtest_results" / "v6a_state" / "v6a_managed_positions_real_281756481449956811.json"
RECON_DIR       = ROOT / "backtest_results" / "v6a_reconciliation"
RUNNER_DIR      = ROOT / "backtest_results" / "v6a_guarded_runner"
OUTPUT_DIR      = ROOT / "backtest_results" / "morning_brief"
HTML_PORTFOLIO  = Path("/Users/zhangkun/Desktop/AI个人投资公司/26年阶段性组合策略计划.html")

REAL_ACC_ID = 281756481449956811
RELEASE_GATE_DIR      = ROOT / "backtest_results" / "attack_engine_release_gate"
SA_TRIAL_SPEC         = ROOT / "SEEKING_ALPHA_INPUT_TRIAL.md"
SA_TRIAL_CSV          = ROOT / "backtest_results" / "external_signal_trials" / "seeking_alpha_trial.csv"
US_RADAR_13F_WATCHLIST = ROOT / "us_radar_13f_watchlist.json"
US_RADAR_13F_SYSTEM_INPUT = ROOT / "backtest_results" / "us_radar_13f_system_input" / "latest.json"
VALUATION_ROUTER_CONFIG = ROOT / "valuation_sop_router_config.json"
OPTIONALITY_OVERLAY_QUEUE = ROOT / "optionality_overlay_review_queue.json"
AI_CORE_LONG_COMPOUNDER_RADAR = Path("/Users/zhangkun/Desktop/AI个人投资公司/报表输出/LATEST/AI_Core_Long_Compounder_Radar_LATEST.json")
COMPANY_RESEARCH_DIR = Path("/Users/zhangkun/Desktop/AI个人投资公司/公司研究")
V6AB_LEGACY_FORWARD_WATCH = ROOT / "backtest_results" / "v6ab_legacy_preservation_forward_watch" / "latest.json"
A_SHARE_CLASSIFICATION_LEDGER = Path("/Users/zhangkun/Desktop/AI个人投资公司/报表输出/LATEST/A股Radar主线分类准度Ledger_LATEST.json")
THEME_EVIDENCE_A_SHARE_OFFICIAL_SCAN = Path("/Users/zhangkun/Desktop/AI个人投资公司/报表输出/LATEST/A股官方政策白名单扫描_LATEST.json")
THEME_EVIDENCE_LEDGER = Path("/Users/zhangkun/Desktop/AI个人投资公司/报表输出/LATEST/Theme_Evidence_人工搜集_LATEST.json")
THEME_EVIDENCE_A_SHARE_INBOX = Path("/Users/zhangkun/Desktop/AI个人投资公司/信息源扫描/Theme_Evidence_Inbox/A股Radar_人工信息搜集_INBOX.md")
THEME_EVIDENCE_V6AB_INBOX = Path("/Users/zhangkun/Desktop/AI个人投资公司/信息源扫描/Theme_Evidence_Inbox/V6AB_人工信息搜集_INBOX.md")


# ── helpers ──────────────────────────────────────────────────────────────────

def read_json(path: Path) -> Any:
    if not path.exists():
        return {} if path.suffix == ".json" else []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def latest_json_in(directory: Path) -> dict:
    if not directory.exists():
        return {}
    files = sorted(
        [f for f in directory.iterdir() if f.suffix == ".json"],
        key=lambda f: f.stat().st_mtime, reverse=True
    )
    return read_json(files[0]) if files else {}


def latest_daily_release_gate_file() -> Path | None:
    if not RELEASE_GATE_DIR.exists():
        return None
    files = sorted(
        RELEASE_GATE_DIR.glob("attack_engine_release_gate_v6_daily_auto_*_plan_only_gate.json"),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    return files[0] if files else None


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def _orders_path_from_gate(payload: dict) -> Path | None:
    for check in payload.get("checks", []):
        if check.get("name") != "live_preview_orders_exist":
            continue
        detail = str(check.get("detail", "")).strip()
        if not detail:
            return None
        path = Path(detail)
        return path if path.is_absolute() else ROOT / path
    return None


def _count_order_sides_from_gate(payload: dict) -> tuple[int, int]:
    orders_path = _orders_path_from_gate(payload)
    if not orders_path or not orders_path.exists():
        return 0, 0
    buy_count = 0
    sell_count = 0
    with orders_path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            side = str(row.get("side") or row.get("action") or "").upper()
            qty = _to_float(row.get("preview_qty") or row.get("qty") or row.get("quantity") or row.get("target_qty"))
            notional = _to_float(row.get("preview_order_value") or row.get("estimated_notional_usd") or row.get("notional_usd"))
            if abs(qty) <= 0 and abs(notional) <= 0:
                continue
            if "BUY" in side:
                buy_count += 1
            elif "SELL" in side:
                sell_count += 1
    return buy_count, sell_count


def _strip_html(text: str) -> str:
    """去除 HTML 标签，合并多余空白"""
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', text)).strip()


def _shorten_target(text: str) -> str:
    """从目标文本中提取简短的百分比范围，如 '18-22%' 或 '0%'"""
    if not text:
        return "—"
    # 优先匹配范围（兼容 "18-22%" 和 "0%-3%" 两种格式）
    rm = re.search(r'(\d+\.?\d*)\s*%?\s*[-–]\s*(\d+\.?\d*)\s*%', text)
    if rm:
        return f"{rm.group(1)}-{rm.group(2)}%"
    # 匹配单值
    sm = re.search(r'(\d+\.?\d*)\s*%', text)
    if sm:
        return f"{sm.group(1)}%"
    return text[:20] if len(text) > 20 else text


# ── V6 状态 ──────────────────────────────────────────────────────────────────

def collect_v6() -> dict:
    state   = read_json(V6A_STATE)
    recon   = latest_json_in(RECON_DIR)
    summary = recon.get("summary", {})

    runs_dir = RUNNER_DIR / "runs"
    runner   = latest_json_in(runs_dir) if runs_dir.exists() else latest_json_in(RUNNER_DIR)

    return {
        "positions":     state.get("positions", {}),
        "pending_count": len(state.get("pending_orders", [])),
        "state_updated": state.get("updated_at", "unknown"),
        "recon_events":  summary.get("events", []),
        "signal":        runner.get("decision", "UNKNOWN") if runner else "UNKNOWN",
        "blockers":      runner.get("blockers", []) if runner else [],
    }


# ── 全资产口径持仓（从 HTML 文件读取）─────────────────────────────────────────

def collect_portfolio_html() -> dict:
    """
    从 26年阶段性组合策略计划.html（用户定期手动更新）解析全资产口径持仓数据。
    包含富途账户 + 腾讯RSU + A股 + 港股通，约 38.9 万 USD。
    """
    if not HTML_PORTFOLIO.exists():
        return {"error": f"未找到 HTML 文件：{HTML_PORTFOLIO}"}

    try:
        content = HTML_PORTFOLIO.read_text(encoding="utf-8")

        # 提取最后更新日期（标题里有 "最后更新 2026-05-11"）
        date_match = re.search(r'最后更新[：:]?\s*(\d{4}-\d{2}-\d{2})', content)
        last_updated = date_match.group(1) if date_match else "未知"

        # 定位 targets section
        targets_start = content.find('<section id="targets">')
        if targets_start == -1:
            return {"error": "HTML 中未找到 <section id=\"targets\">"}
        targets_end = content.find('</section>', targets_start)
        targets_html = content[targets_start:targets_end]

        # 提取 tbody
        tbody_match = re.search(r'<tbody>(.*?)</tbody>', targets_html, re.DOTALL)
        if not tbody_match:
            return {"error": "targets section 中未找到 tbody"}
        tbody = tbody_match.group(1)

        positions = []
        for row_html in re.findall(r'<tr>(.*?)</tr>', tbody, re.DOTALL):
            cells_raw = re.findall(r'<td[^>]*>(.*?)</td>', row_html, re.DOTALL)
            cells = [_strip_html(c) for c in cells_raw]
            if len(cells) < 3:
                continue

            name_raw     = cells[0]
            current_text = cells[1]
            target_text  = cells[2]
            action       = cells[4] if len(cells) > 4 else ""

            # 简化名称：取"（"或" / "或"/"之前的部分
            name = re.split(r'[（/]', name_raw.replace(' / ', '/'))[0].strip()

            # 解析当前仓位（取第一个 ≤100 的百分比）
            pct_candidates = [float(p) for p in re.findall(r'(\d+\.?\d*)\s*%', current_text)
                              if float(p) <= 100]
            current_pct = pct_candidates[0] if pct_candidates else 0.0

            # 解析目标范围（兼容 "18-22%" 和 "0%-3%" 两种格式）
            range_match = re.search(r'(\d+\.?\d*)\s*%?\s*[-–]\s*(\d+\.?\d*)\s*%', target_text)
            if range_match:
                target_min = float(range_match.group(1))
                target_max = float(range_match.group(2))
            else:
                t_pcts = [float(p) for p in re.findall(r'(\d+\.?\d*)\s*%', target_text)
                          if float(p) <= 100]
                if t_pcts:
                    target_min = target_max = t_pcts[0]
                else:
                    target_min = target_max = None

            # 状态判断
            # over: 超出目标上限（有意义的超配）
            # under: 低于目标下限 且 目标本身 >2%（建仓中 / 待加仓）
            # ok: 在目标范围内
            status = "ok"
            if target_max is not None and current_pct > target_max + 0.5:
                status = "over"
            elif target_min is not None and target_min > 2 and current_pct < target_min - 1:
                status = "under"

            positions.append({
                "name":         name,
                "current_pct":  round(current_pct, 1),
                "target_min":   target_min,
                "target_max":   target_max,
                "target_short": _shorten_target(target_text),
                "action":       action,
                "status":       status,
            })

        alerts = [p for p in positions if p["status"] == "over"]

        return {
            "last_updated": last_updated,
            "positions":    positions,
            "alerts":       alerts,
        }

    except Exception as e:
        return {"error": str(e)}


# ── Futu API（仅用于 V6 实时价格补充）────────────────────────────────────────

def collect_portfolio_futu() -> dict | None:
    """仅通过 Futu API 拉取 V6 仓位实时市值，不用于主持仓监控"""
    try:
        from futu import OpenSecTradeContext, TrdMarket, TrdEnv, SecurityFirm, RET_OK
        ctx = OpenSecTradeContext(
            filter_trdmarket=TrdMarket.NONE,
            host="127.0.0.1", port=11111,
            security_firm=SecurityFirm.FUTUSECURITIES
        )
        ret_p, pos_df = ctx.position_list_query(
            trd_env=TrdEnv.REAL, acc_id=REAL_ACC_ID, refresh_cache=True
        )
        ret_f, funds = ctx.accinfo_query(
            trd_env=TrdEnv.REAL, acc_id=REAL_ACC_ID, refresh_cache=True
        )
        ctx.close()

        if ret_p != RET_OK or ret_f != RET_OK:
            return None

        pos_map = {}
        for _, row in pos_df.iterrows():
            code = row["code"]
            qty  = float(row["qty"])
            if qty > 0:
                pos_map[code] = {
                    "qty":       qty,
                    "mv_local":  float(row["market_val"]),
                    "pl_pct":    float(row.get("pl_ratio_avg_cost", 0)),
                }

        total_assets_hkd = float(funds.iloc[0]["total_assets"])
        return {"positions": pos_map, "total_assets_hkd": total_assets_hkd}

    except Exception:
        return None


# ── 事件日历 ──────────────────────────────────────────────────────────────────

def collect_events(days_ahead: int = 7) -> list[dict]:
    raw = read_json(EVENTS_CAL)
    if not isinstance(raw, list):
        return []
    today  = date.today()
    cutoff = today + timedelta(days=days_ahead)
    events = []
    for item in raw:
        if not isinstance(item, dict) or "_comment" in item:
            continue
        try:
            d = date.fromisoformat(item["date"])
        except (KeyError, ValueError):
            continue
        if today <= d <= cutoff:
            item["_days"]     = (d - today).days
            item["_date_obj"] = d
            events.append(item)
    events.sort(key=lambda x: x["_date_obj"])
    return events


# ── 13F quarterly learning window ───────────────────────────────────────────

def collect_13f_learning_window(today: date | None = None) -> dict:
    """Return current quarterly 13F learning reminder state.

    The reminder is intentionally lightweight: it asks the user to trigger
    the quarterly learning workflow, but does not scrape, trade, or infer
    current positions automatically from delayed 13F data.
    """
    today = today or date.today()
    config = read_json(US_RADAR_13F_WATCHLIST)
    windows = config.get("review_windows", []) if isinstance(config, dict) else []
    managers = config.get("managers", []) if isinstance(config, dict) else []

    for window in windows:
        try:
            month = int(window["month"])
            start_day = int(window["start_day"])
            end_day = int(window["end_day"])
        except Exception:
            continue
        if today.month == month and start_day <= today.day <= end_day:
            p0 = [m.get("name", "") for m in managers if m.get("priority") == "P0"]
            p1_count = sum(1 for m in managers if m.get("priority") == "P1")
            p2_count = sum(1 for m in managers if m.get("priority") == "P2")
            return {
                "active": True,
                "quarter": str(window.get("quarter", "")),
                "window": f"{today.year}-{month:02d}-{start_day:02d} 至 {today.year}-{month:02d}-{end_day:02d}",
                "p0_managers": p0,
                "p1_count": p1_count,
                "p2_count": p2_count,
                "watchlist_path": str(US_RADAR_13F_WATCHLIST.relative_to(ROOT)),
            }
    return {"active": False}


def collect_13f_system_actions(today: date | None = None, days_ahead: int = 3) -> list[dict[str, Any]]:
    """Read machine-readable 13F outputs and return actionable system tasks.

    These are not trade signals. They are Radar/V6-B/valuation tasks created
    only after a 13F learning pass has produced explicit system fields.
    """
    today = today or date.today()
    payload = read_json(US_RADAR_13F_SYSTEM_INPUT)
    rows = payload.get("rows", []) if isinstance(payload, dict) else []
    actions: list[dict[str, Any]] = []
    v6b_candidates: list[dict[str, Any]] = []
    for row in rows:
        if str(row.get("status", "")).upper() != "OPEN":
            continue
        if row.get("priority") not in {"P0", "P1"}:
            continue
        try:
            deadline = date.fromisoformat(str(row.get("review_deadline", "")))
        except ValueError:
            continue
        days = (deadline - today).days
        if days < -7 or days > days_ahead:
            continue
        ticker = str(row.get("ticker", "")).replace("US.", "")
        if row.get("position_role") == "V6B_candidate":
            v6b_candidates.append({**row, "ticker_short": ticker})
            continue
        actions.append({
            "priority": "MED",
            "ticker": ticker,
            "item": f"{ticker} 13F系统输入：{row.get('system_effect', '')}",
            "trigger": f"复盘 {ticker}",
            "reason": f"{row.get('next_system_action', '')}；13F不是买入信号：{row.get('no_trade_reason', '')}",
        })
    if v6b_candidates:
        tickers = " / ".join(str(row.get("ticker_short", "")) for row in v6b_candidates[:8])
        top_deadline = min(str(row.get("review_deadline", "9999-12-31")) for row in v6b_candidates)
        reason_parts = []
        for row in v6b_candidates[:4]:
            reason_parts.append(f"{row.get('ticker_short')}: {row.get('next_system_action')}")
        actions.append({
            "priority": "MED",
            "ticker": tickers,
            "item": f"13F V6-B候选刷新：{tickers}",
            "trigger": "复盘 V6-B",
            "reason": f"最早截止 {top_deadline}；" + "；".join(reason_parts) + "；13F不是买入信号，必须等point-in-time和估值现实检查。",
        })
    return actions


# ── K线额度 ──────────────────────────────────────────────────────────────────

def collect_kline_quota() -> dict | None:
    try:
        from futu import OpenQuoteContext, RET_OK
        ctx = OpenQuoteContext(host="127.0.0.1", port=11111)
        ret, data = ctx.get_history_kl_quota(get_detail=False)
        ctx.close()
        if ret != RET_OK:
            return None
        if isinstance(data, tuple):
            # data = (used, remaining, detail_list)
            used_q      = int(data[0])
            remaining_q = int(data[1])
            total_q     = used_q + remaining_q
        else:
            row     = data.iloc[0]
            total_q = int(row.get("total_quota", 0))
            used_q  = int(row.get("used_quota", 0))
        return {"used": used_q, "total": total_q}
    except Exception:
        return None


# ── Stale data mode detection ────────────────────────────────────────────────

def collect_stale_data_status() -> dict:
    """Read the latest release gate JSON and detect STALE_DATA_MODE.

    Returns a dict with:
      is_stale              — signal_freshness_gate failed
      sell_orders_need_review — SELL orders present in stale mode
      sell_order_count      — number of SELL orders
      buy_order_count       — number of BUY orders blocked
      signal_date           — latest_signal_date from gate summary
      gate_file             — filename of the gate JSON that was read
    """
    gate_file = latest_daily_release_gate_file()
    if not gate_file:
        return {"is_stale": False, "sell_orders_need_review": False,
                "sell_order_count": 0, "buy_order_count": 0, "signal_date": "", "gate_file": ""}
    payload = read_json(gate_file)

    # Prefer explicit field from new gate format; fall back to scanning checks
    stale = bool(payload.get("stale_data_mode", False))
    if not stale:
        stale = any(
            c.get("name") == "signal_freshness_gate" and not c.get("passed")
            for c in payload.get("checks", [])
        )

    inferred_buy_count, inferred_sell_count = _count_order_sides_from_gate(payload)
    sell_count = int(payload.get("sell_order_count", inferred_sell_count))
    buy_count = int(payload.get("buy_order_count", inferred_buy_count))
    sell_review = bool(payload.get("sell_orders_need_review", stale and sell_count > 0))
    return {
        "is_stale": stale,
        "sell_orders_need_review": sell_review,
        "sell_order_count": sell_count,
        "buy_order_count": buy_count,
        "signal_date": str(payload.get("summary", {}).get("latest_signal_date", "")),
        "gate_file": gate_file.name,
    }


# ── collab 待办 ──────────────────────────────────────────────────────────────

def collect_todos() -> dict[str, list[str]]:
    if not COLLAB_LOG.exists():
        return {}
    text   = COLLAB_LOG.read_text(encoding="utf-8")
    cutoff = date.today() - timedelta(days=14)
    todos: dict[str, list[str]] = {}

    domain_pat = re.compile(r"\[([A-Za-z\u4e00-\u9fff][^\]]*)\]\s*\[待办\]\s*(.+)")
    plain_pat  = re.compile(r"\[待办\]\s*(.+)")
    date_pat   = re.compile(r"^## (\d{4}-\d{2}-\d{2})")

    in_range = False
    for line in text.splitlines():
        m = date_pat.match(line)
        if m:
            try:
                in_range = date.fromisoformat(m.group(1)) >= cutoff
            except ValueError:
                in_range = False
            continue
        if not in_range:
            continue
        dm = domain_pat.search(line)
        if dm:
            content = re.sub(r"^\[.*?\]\s*", "", dm.group(2).strip())
            todos.setdefault(dm.group(1), []).append(content)
            continue
        pm = plain_pat.search(line)
        if pm:
            content = re.sub(r"^\[.*?\]\s*", "", pm.group(1).strip())
            todos.setdefault("通用", []).append(content)
    return todos


# ── 今日工作流动作清单 ───────────────────────────────────────────────────────

def _keyword_for_event(event: dict) -> str:
    domain = event.get("domain", "")
    text = event.get("text", "")
    action = event.get("action", "")
    joined = f"{text} {action}"
    upper = joined.upper()

    for sym in ["PDD", "NVDA", "MSFT", "GOOGL", "AAPL", "ADBE", "AAOI", "MU", "COHR", "LITE"]:
        if sym in upper:
            if "财报" in joined or "估值" in joined or domain in {"估值", "价值投资"}:
                return f"复盘 {sym}"
            return f"研究 {sym}"

    if "V6-A" in joined or "Pilot" in joined or "pilot" in joined:
        return "V6 Pilot 总结"
    if "V6-B" in joined or "standalone" in joined or "回测" in joined:
        return "复盘 V6-B"
    if "A股" in joined or "SH." in joined or "SZ." in joined or "纽威数控" in joined or "绿的谐波" in joined or "三丰智能" in joined:
        return "复盘 A股Radar"
    if "X" in joined or "信息源" in joined:
        return "X Radar 扫描"
    if domain == "Radar":
        return "复盘 Radar"
    if domain == "估值":
        return "估值更新"
    return "复盘"


def _read_csv_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))
    except Exception:
        return []


def _known_valuation_tickers() -> set[str]:
    config = read_json(VALUATION_ROUTER_CONFIG)
    tickers = set(config.get("ticker_overrides", {}).keys())
    tickers.update({"PDD", "NU", "AAPL", "MCO", "SPGI", "AAOI", "COHR", "LITE", "MU", "VECO", "ASX"})
    return {t.upper().replace("US.", "") for t in tickers}


def _extract_known_tickers(text: str, known: set[str]) -> set[str]:
    upper = str(text or "").upper()
    found: set[str] = set()
    for ticker in known:
        if re.search(rf"(?<![A-Z0-9.])(?:US\.)?{re.escape(ticker)}(?![A-Z0-9])", upper):
            found.add(ticker)
    return found


def _recent_research_tickers(today: date, known: set[str], lookback_days: int = 7) -> set[str]:
    if not COMPANY_RESEARCH_DIR.exists():
        return set()
    cutoff = today - timedelta(days=lookback_days)
    tickers: set[str] = set()
    for path in COMPANY_RESEARCH_DIR.glob("*/*.md"):
        try:
            if datetime.fromtimestamp(path.stat().st_mtime).date() < cutoff:
                continue
        except OSError:
            continue
        tickers.update(_extract_known_tickers(f"{path.parent.name} {path.name}", known))
    return tickers


def collect_valuation_sop_actions(today: date, events: list[dict]) -> list[dict]:
    """
    Surface valuation framework routing only when a ticker is already active in
    the research/event flow. This turns the SOP choice into a system input while
    avoiding a daily checklist of every configured ticker.
    """
    try:
        router = importlib.import_module("valuation_sop_router")
    except Exception:
        return []

    config = read_json(VALUATION_ROUTER_CONFIG)
    known = _known_valuation_tickers()
    active_tickers: set[str] = set()
    for event in events:
        if int(event.get("_days", 999)) > 3:
            continue
        active_tickers.update(_extract_known_tickers(f"{event.get('text', '')} {event.get('action', '')}", known))

    actions: list[dict] = []
    for ticker in sorted(active_tickers):
        selected = router.select_framework(ticker, [], config)
        framework_key = selected.get("framework_key", "SOP_v2.5")
        framework_name = selected.get("framework_name", framework_key)
        priority = "MED"
        actions.append({
            "priority": priority,
            "item": f"{ticker} 估值体系自动选择：{framework_name}",
            "trigger": f"估值 {ticker}",
            "reason": (
                f"valuation_sop_router：{selected.get('why_this_framework', '')}；"
                f"先选框架再估值，输出需回写 {', '.join(selected.get('system_feedback_targets', []))}；"
                "估值报告必须输出 Optionality Review：NO_OPTION / WATCH_OPTION / DEFINED_RISK_REVIEW；"
                "不得自动交易期权"
            ),
        })
    return actions


def _parse_iso_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)[:10]).date()
    except ValueError:
        return None


def collect_optionality_overlay_actions(today: date) -> list[dict]:
    """
    Surface manual option-expression review tasks only.

    This is not a trading signal and must not alter V6/V6AB/A-share Radar logic.
    Queue items are expected to be created by valuation work, V6AB/V6-B research,
    or validated cross-market Radar research.
    """
    payload = read_json(OPTIONALITY_OVERLAY_QUEUE)
    if not isinstance(payload, dict):
        return []

    actions: list[dict] = []
    for item in payload.get("items", []):
        if not isinstance(item, dict):
            continue
        status = str(item.get("status", "")).upper()
        if status not in {"WATCH_OPTION", "DEFINED_RISK_REVIEW"}:
            continue

        ticker = str(item.get("ticker") or item.get("symbol") or "UNKNOWN").upper()
        source = str(item.get("source_system") or "UNKNOWN")
        thesis = str(item.get("thesis") or item.get("reason") or "").strip()
        review_date = _parse_iso_date(item.get("review_date") or item.get("next_review_date"))
        event_date = _parse_iso_date(item.get("event_date") or item.get("event_window_start"))

        due_dates = [d for d in [review_date, event_date] if d is not None]
        days_to_due = min((d - today).days for d in due_dates) if due_dates else None

        required = ["max_loss_plan", "event_window", "invalidation", "exit_plan"]
        missing = [field for field in required if not str(item.get(field) or "").strip()]

        if status == "DEFINED_RISK_REVIEW":
            if missing:
                priority = "MED"
            elif days_to_due is not None and days_to_due <= 3:
                priority = "HIGH" if days_to_due <= 0 else "MED"
            else:
                priority = "LOW"
        else:
            priority = "LOW"
            if days_to_due is not None and days_to_due <= 3:
                priority = "MED"

        if days_to_due is not None and days_to_due > 14 and status == "WATCH_OPTION":
            continue

        item_label = f"{ticker} Optionality Overlay：{status}"
        trigger = f"复核期权表达 {ticker}"
        reason_parts = [
            f"来源={source}",
            "只做人工复核，不自动交易，不改变 V6/V6AB/A股 Radar 正股规则",
        ]
        if thesis:
            reason_parts.append(f"thesis={thesis[:120]}")
        if review_date:
            reason_parts.append(f"review_date={review_date.isoformat()}")
        if event_date:
            reason_parts.append(f"event_date={event_date.isoformat()}")
        if missing:
            reason_parts.append(f"缺少 defined-risk 字段：{', '.join(missing)}")
        else:
            reason_parts.append("必须复核 max loss / invalidation / exit plan 后才允许人工决定")

        actions.append({
            "priority": priority,
            "item": item_label,
            "trigger": trigger,
            "reason": "；".join(reason_parts),
        })

    return actions


def _date_from_decision(row: dict) -> date | None:
    decision_id = row.get("decision_id", "")
    m = re.match(r"(\d{8})", decision_id)
    if m:
        try:
            return datetime.strptime(m.group(1), "%Y%m%d").date()
        except ValueError:
            pass
    decision_time = row.get("decision_time", "")
    try:
        return datetime.fromisoformat(decision_time[:16]).date()
    except ValueError:
        return None


def _parse_iso_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def summarize_v6ab_theme_evidence(payload: Any, today: date, limit: int = 5) -> str:
    """Extract recent V6AB manual evidence worth primary-source review."""
    if not isinstance(payload, dict):
        return ""
    rows = payload.get("rows", [])
    if not isinstance(rows, list):
        return ""
    keywords = (
        "AI infrastructure",
        "AI infra",
        "AI chip",
        "AI chips",
        "Nvidia",
        "NVDA",
        "Micron",
        "MU",
        "Lumentum",
        "Coherent",
        "LITE",
        "datacenter",
        "data center",
        "electrification",
        "power",
        "ServiceNow",
        "NOW",
        "Microsoft",
        "MSFT",
        "Amazon",
        "AMZN",
        "Qualcomm",
        "AMD",
        "chip stocks",
        "semis",
    )
    items: list[str] = []
    for row in rows:
        source_inbox = str(row.get("source_inbox", ""))
        if "V6AB_" not in source_inbox:
            continue
        row_date = _parse_iso_date(row.get("date"))
        if row_date is None or (today - row_date).days > 3:
            continue
        haystack = f"{row.get('theme', '')} {row.get('summary', '')}"
        if not any(k.lower() in haystack.lower() for k in keywords):
            continue
        source_type = str(row.get("source_type", ""))
        summary = str(row.get("summary", "")).strip()
        theme = str(row.get("theme", "")).strip()
        if not summary:
            continue
        tag = "免费标题" if source_type != "seeking_alpha_premium_title" else "Premium标题"
        short_summary = summary if len(summary) <= 100 else f"{summary[:97].rstrip()}..."
        items.append(f"{theme}: {short_summary}（{tag}，需主源验证）")
        if len(items) >= limit:
            break
    return "；".join(items)


def collect_workflow_actions(events: list[dict], stale_status: dict | None = None) -> list[dict]:
    """
    Daily 报告的任务中枢：只告诉用户今天该做什么、用什么关键词触发。
    不在这里做投资分析，也不自动触发交易。
    """
    today = date.today()
    actions: list[dict] = []

    def add(priority: str, domain: str, item: str, trigger: str, reason: str) -> None:
        key = (domain, item, trigger)
        if any((a["domain"], a["item"], a["trigger"]) == key for a in actions):
            return
        for a in actions:
            if a["trigger"] == trigger:
                order = {"HIGH": 0, "MED": 1, "LOW": 2}
                if order.get(priority, 9) < order.get(a["priority"], 9):
                    a["priority"] = priority
                if reason not in a["reason"]:
                    a["reason"] = f"{a['reason']}；{reason}"
                return
        actions.append({
            "priority": priority,
            "domain": domain,
            "item": item,
            "trigger": trigger,
            "reason": reason,
        })

    # 1) 事件日历：今天/未来3天作为动作提醒，未来7天仍在事件区展示。
    for e in events:
        days = int(e.get("_days", 999))
        if days > 3:
            continue
        priority = "HIGH" if days == 0 else ("MED" if days <= 2 else "LOW")
        day_label = "今天" if days == 0 else ("明天" if days == 1 else f"{days}天后")
        add(
            priority,
            e.get("domain", "事件"),
            e.get("text", ""),
            _keyword_for_event(e),
            f"事件日历：{day_label}，需要提前准备或触发对应流程",
        )

    # 2) 交易决策日志：PLANNED 且到期/临近，提示进入对应复盘/重估流程。
    for row in _read_csv_rows(DECISION_LOG):
        status = (row.get("status") or "").upper()
        if status not in {"PLANNED", "EXECUTED", "CLOSED"}:
            continue
        d = _date_from_decision(row)
        if d is None:
            continue
        days = (d - today).days
        if days < -7 or days > 3:
            continue

        symbol = row.get("symbol", "")
        system = row.get("system_source", "")
        setup = row.get("setup_type", "")
        if system == "主仓" or setup == "Earnings_ReUnderwrite":
            trigger = f"复盘 {symbol}"
            item = f"{symbol} 主仓财报重估 / Thesis Re-underwrite"
        elif "Radar-CN" in system or "CN_" in setup:
            trigger = "复盘 A股Radar"
            item = f"{symbol} A股Radar 样本复盘"
        elif "V6" in system or "Radar" in system:
            trigger = f"复盘 {system}"
            item = f"{symbol} {system} 样本复盘"
        else:
            trigger = f"复盘 {symbol}"
            item = f"{symbol} 决策日志复盘"

        priority = "HIGH" if days <= 0 else ("MED" if days <= 2 else "LOW")
        add(
            priority,
            "工作流",
            item,
            trigger,
            f"decision_log.csv 状态={status}，目标日期 {d.isoformat()}",
        )

    # 3) Friend Alpha：样本达到阶段门槛时才提醒，不每天制造噪音。
    friend_rows = _read_csv_rows(FRIEND_ALPHA_LOG)
    sample_count = len([r for r in friend_rows if any((v or "").strip() for v in r.values())])
    if sample_count in {20, 50}:
        add(
            "HIGH",
            "Friend Alpha",
            f"Friend Alpha 已累计 {sample_count} 个样本",
            "复盘 Friend Alpha",
            "达到20/50样本门槛，需要判断是否继续观察或制度化",
        )

    # 4) 固定节奏提醒：把机制收敛为 Daily 顶部的人工入口。
    theme_evidence = read_json(THEME_EVIDENCE_LEDGER)
    evidence_due_count = int(theme_evidence.get("due_count") or 0) if isinstance(theme_evidence, dict) else 0
    v6ab_evidence_focus = summarize_v6ab_theme_evidence(theme_evidence, today)
    official_scan = read_json(THEME_EVIDENCE_A_SHARE_OFFICIAL_SCAN)
    official_status = str(official_scan.get("status", "UNKNOWN")) if isinstance(official_scan, dict) else "UNKNOWN"
    official_rows = int(official_scan.get("row_count") or 0) if isinstance(official_scan, dict) else 0
    official_failures = official_scan.get("failures", []) if isinstance(official_scan, dict) else []
    official_failed_count = sum(1 for item in official_failures if isinstance(item, dict) and item.get("status") == "FAILED")
    add(
        "MED" if today.weekday() < 5 else "LOW",
        "Theme Evidence",
        "A股 Radar 人工信息搜集：政策/产业/公告/板块异动",
        "记录 A股主题证据",
        f"官方白名单扫描已自动处理政府/交易所公开源，状态={official_status}，命中 {official_rows} 条，失败源 {official_failed_count} 个；报告见 {THEME_EVIDENCE_A_SHARE_OFFICIAL_SCAN.with_suffix('.md')}。人工只补系统失败/需复核的官方源、巨潮/交易所公司公告、以及有政策或产业支撑的财联社/东方财富板块异动，写入 {THEME_EVIDENCE_A_SHARE_INBOX}；INBOX 只放待处理新信息，处理入 ledger 后可删除已处理行。富途板块热度已自动生成，不需要人工重复抄纯涨幅榜。重点搜人形机器人、半导体设备、低空经济、AI应用、算力、AI服务器供应链/MLCC被动元件、电力设备、新型工业化、设备更新、国产替代。只记录政策明确、订单/产能/客户/业绩验证、龙头中军同步、产业链瓶颈或强反证；不记录纯涨幅榜/无来源观点/情绪标题。当前 evidence 到期复核 {evidence_due_count} 条",
    )
    add(
        "MED" if official_failed_count else "LOW",
        "Radar-CN",
        "A股官方信息源稳定性巡检",
        "巡检A股官方源",
        f"查看 A股官方政策白名单扫描_LATEST：若失败源>0 或连续多日命中=0，则提醒我优化白名单 URL/RSS/关键词；若命中官方政策，检查是否与富途板块热度和候选结构共振。当前状态={official_status}，命中={official_rows}，失败源={official_failed_count}",
    )
    add(
        "MED" if v6ab_evidence_focus or today.weekday() == 4 else "LOW",
        "Theme Evidence",
        "V6AB / 美股 Radar 人工信息搜集：财报、SEC、13F、产业链扩散",
        "记录 V6AB主题证据",
        f"把本周看到的高质量线索写入 {THEME_EVIDENCE_V6AB_INBOX}；INBOX 只放待处理新信息，处理入 ledger 后可删除已处理行，历史看 Theme_Evidence_人工搜集_LATEST。搜集建议：SEC EDGAR/公司IR/财报电话会/13F/Fed/BEA/产业链公开报道；重点搜 AI infra、semis、power、data center、HBM、光模块、云capex，以及 2020 technology/precious metals、2022 energy/inflation/defensive 历史主线证据。只记录财报/订单/capex/供应链瓶颈/机构持仓/宏观数据或强反证；不记录泛泛新闻。只做 evidence，不改变 V2 模拟盘"
        + (f"；今日需人工复核：{v6ab_evidence_focus}" if v6ab_evidence_focus else ""),
    )

    # A股 Radar 是小资金短线实验仓，若当天有交易/候选，应日更复盘。
    if today.weekday() < 5:
        classification_ledger = read_json(A_SHARE_CLASSIFICATION_LEDGER)
        due_count = int(classification_ledger.get("due_count") or 0) if isinstance(classification_ledger, dict) else 0
        add(
            "MED",
            "Radar-CN",
            "A股 Radar Phase 1A 纪律记录",
            "复盘 A股Radar",
            f"当前是中频主题轮动训练系统，不打板不盯盘；每日记录候选、信号来源、为什么是启动初期、触发/冷却/失效、主观干预和复盘覆盖率；主线分类到期复核 {due_count} 条，30笔完整样本前不改规则",
        )
        add(
            "LOW",
            "Radar-CN",
            "A股 Radar 日更复盘（仅当今天有候选/交易/观察标的时执行）",
            "复盘 A股Radar",
            "A股 Radar 需要高频训练；无交易或无候选则可忽略",
        )

    # A股 Radar 周五自动发现链路：只生成 AddToRadar 候选，不自动入池或交易。
    if today.weekday() == 4:
        add(
            "LOW",
            "Radar-CN",
            "A股 Radar 周度新主题/新标的扫描与概念持续性校验",
            "扫描 A股Radar 新候选",
            "每周五自动发现新主题/新标的，只生成 AddToRadar 候选；重点区分政策/产业主线与短命游资概念，需人工确认后才写入观察池",
        )

    # 美股 Radar / V6-B 以周度或事件驱动为主，不做每日噪音提醒。
    if today.weekday() == 4:
        add(
            "LOW",
            "Radar-US",
            "美股 Radar / V6-B 周度样本复盘",
            "复盘 V6-B",
            "美股 Radar/V6-B 是周度或事件驱动复盘，不需要每天人工处理",
        )

    # Optionality Overlay 是表达层，不是独立信号源。每周只做一次候选清点，
    # 避免用户忘记从主仓估值、V6AB/V6-B 强主线和已验证跨市场研究中提取有限亏损表达候选。
    if today.weekday() == 4:
        add(
            "LOW",
            "Optionality Overlay",
            "周度清点：是否有候选需要进入 Optionality Review 队列",
            "清点期权表达候选",
            "只从主仓/进攻价值投 thesis、V6AB/V6-B 强主线、已验证跨市场研究中提取；输出只能是 NO_OPTION / WATCH_OPTION / DEFINED_RISK_REVIEW；不得自动交易期权，必须先写明 max loss / event window / invalidation / exit plan",
        )

    # AI 大时代长期核心复利股：周度查看候选是否进入击球区。
    # 这是主仓研究雷达，不自动交易，不和 V6AB/A股 Radar 仓位混用。
    if today.weekday() == 4:
        ai_core_payload = read_json(AI_CORE_LONG_COMPOUNDER_RADAR)
        rows = ai_core_payload.get("rows", []) if isinstance(ai_core_payload, dict) else []
        actionable = [
            r for r in rows
            if isinstance(r, dict) and r.get("action") in {"PULLBACK_REVIEW", "STARTER_OR_UPGRADE_REVIEW"}
        ]
        tickers = "、".join(str(r.get("ticker", "")) for r in actionable[:5]) or "暂无"
        add(
            "MED" if actionable else "LOW",
            "AI Core",
            "AI Core Long Compounder Radar 周度复核",
            "复核AI核心复利股",
            f"查看 AI_Core_Long_Compounder_Radar_LATEST：目标是寻找 AI 大时代少数可长期逢低加仓的高信任复利股；当前需人工复核候选={tickers}。只做估值/thesis/击球区复核，不自动交易，不追高，不替代主仓风险预算",
        )

    # 跨市场同步防污染检查：定期提醒用户让 AI 审查 V6AB / A股 Radar 的共享成果。
    # 只同步方法论与验证结论；具体阈值、买点、市场结构信号默认隔离。
    if today.weekday() == 4:
        add(
            "MED",
            "跨市场同步",
            "检查 V6AB / A股 Radar 最近成果是否正确同步，是否存在规则污染",
            "检查跨市场同步污染：请审查最近 V6AB 和 A股 Radar 的成果，哪些方法论可以共享，哪些具体规则/阈值/信号必须隔离，是否有污染风险。",
            "每周一次；读取 跨市场研究同步_LATEST.md，只同步 SHARE，隔离 QUARANTINE，迁移项必须留在 VALIDATION_QUEUE",
        )

    # Seeking Alpha 输入源试验：交易日每日提醒，用户按 X Radar 节奏整理前一日公开信号。
    # 只有在试验规格文件存在时才提醒（避免试验结束后继续噪音）。
    if today.weekday() < 5 and SA_TRIAL_SPEC.exists():
        add(
            "LOW",
            "美股Radar",
            "Seeking Alpha 输入源试验：整理前一日 SA 公开链接/标题/摘要",
            "记录 SA 信号",
            "只整理公开信息，不自动爬取，不绕paywall；用于美股Radar / V6-B / 主仓反证；见 SEEKING_ALPHA_INPUT_TRIAL.md",
        )

    # 13F quarterly learning: after each 13F filing deadline window, remind
    # the user to ask AI to update the Radar learning notes. This is a
    # learning/research workflow, not a buy/sell signal.
    q13f = collect_13f_learning_window(today)
    if q13f.get("active"):
        p0 = "、".join(q13f.get("p0_managers", [])[:3]) or "P0名单"
        add(
            "MED",
            "美股Radar",
            f"13F 季度学习窗口开启：{q13f.get('quarter')}，更新 P0/P1 基金与自营交易公司样本",
            "更新13F学习",
            f"窗口 {q13f.get('window')}；先看 {p0}，再看 P1×{q13f.get('p1_count', 0)} / P2×{q13f.get('p2_count', 0)}；只用于完善 Radar skills，不自动交易",
        )

    for row in collect_13f_system_actions(today):
        add(
            row["priority"],
            "13F系统输入",
            row["item"],
            row["trigger"],
            row["reason"],
        )

    for row in collect_valuation_sop_actions(today, events):
        add(
            row["priority"],
            "估值",
            row["item"],
            row["trigger"],
            row["reason"],
        )

    for row in collect_optionality_overlay_actions(today):
        add(
            row["priority"],
            "Optionality Overlay",
            row["item"],
            row["trigger"],
            row["reason"],
        )

    # V6AB qualified legacy preservation 仍处于 WATCH：每日只提示观察/复核，不改变 V2 模拟盘。
    watch_payload = read_json(V6AB_LEGACY_FORWARD_WATCH)
    watch_obs = watch_payload.get("latest_observation", {}) if isinstance(watch_payload, dict) else {}
    if today.weekday() < 5:
        add(
            "LOW",
            "V6",
            "V6AB qualified legacy preservation WATCH ledger 连续观察",
            "运行 V6AB WATCH ledger",
            "记录 V2 / original PIT / qualified preservation 三套选择、protection 是否触发和阻止的替换；仅纸面观察，不替换 V2",
        )
    if watch_obs:
        decision_date = str(watch_obs.get("decision_date", ""))
        status = str(watch_obs.get("status", "UNKNOWN"))
        blocked = ", ".join(watch_obs.get("blocked_replacements", [])[:3]) if isinstance(watch_obs.get("blocked_replacements"), list) else ""
        if watch_obs.get("legacy_preservation_applied"):
            add(
                "MED",
                "V6",
                f"V6AB legacy protection 触发复核：{decision_date}",
                "复核 V6AB legacy WATCH",
                f"forward WATCH status={status}，blocked={blocked or '-'}；确认是 PIT 过度替换还是 qualified 过度保护，不改变模拟盘",
            )
        else:
            add(
                "LOW",
                "V6",
                f"V6AB legacy WATCH 无触发：{decision_date}",
                "复核 V6AB legacy WATCH",
                "连续无触发说明保护层可能足够低频；继续累积 5-10 个交易日观察，不改变模拟盘",
            )
    add(
        "LOW",
        "V6",
        "V6AB 非 AI 历史主线证据补强",
        "补强 V6AB 非AI主线证据",
        "优先补 2020 liquidity/technology/precious metals、2022 energy/inflation/defensive、2024-2026 AI infra/semis/power/data center 的 PIT 可见证据",
    )
    add(
        "LOW",
        "V6",
        "V6AB WATCH promotion 条件草案",
        "定义 V6AB WATCH 晋级条件",
        "后续把 WATCH -> PAPER_SHADOW -> PAPER_SIM_CANDIDATE 的门槛写清楚；当前 qualified preservation 不能替换 V2",
    )

    # 非交易日也给出明确状态，避免 Daily/Weekly 邮件看起来“没有今日待办”。
    if today.weekday() >= 5:
        add(
            "LOW",
            "通用",
            "非交易日系统维护/研究日",
            "无需操作",
            "可选：整理交易决策日志、阅读估值报告、准备下周观察清单；没有必须动作",
        )

    # 5) X Radar：只在交易日提示轻量扫描，避免周末噪音。
    today_daily = X_RADAR_DAILY / f"{today.isoformat()}_X_Radar_Daily.md"
    if today.weekday() < 5 and not today_daily.exists():
        add(
            "LOW",
            "Radar",
            "今日 X Radar 尚未整理",
            "X Radar 扫描",
            "可选择把高价值X链接/文字贴给Claude整理；不是交易触发器",
        )

    # 6) Stale data mode — 进攻信号过期时注入警告和风险退出提醒
    if stale_status and stale_status.get("is_stale"):
        signal_date = stale_status.get("signal_date", "未知")
        add(
            "MED",
            "V6",
            f"V6 处于 STALE_DATA_MODE（最近信号日期：{signal_date}）",
            "复盘 V6-A",
            "K线额度不足或信号过期；BUY/ADD 已阻断；等待约月初额度恢复（~2026-06-01）后重新评估",
        )
        if stale_status.get("sell_orders_need_review") and stale_status.get("sell_order_count", 0) > 0:
            sell_count = stale_status["sell_order_count"]
            add(
                "HIGH",
                "V6",
                f"⚠️ RISK_EXIT_PENDING：{sell_count} 笔 SELL 订单需人工复核",
                "复盘 V6-A 风险退出",
                "STALE_DATA_MODE 下防守型订单须人工判断是否属于 RISK_EXIT_SELL / MANUAL_RISK_REDUCE；确认后在富途客户端手动执行",
            )

    order = {"HIGH": 0, "MED": 1, "LOW": 2}
    return sorted(actions, key=lambda a: (order.get(a["priority"], 9), a["domain"], a["item"]))


# ── 格式化 HTML ───────────────────────────────────────────────────────────────

SIGNAL_LABEL = {
    "BLOCKED": ("🟢", "无换仓信号，持仓不动"),
    "PASS":    ("🔄", "有换仓信号，等待人工确认"),
    "UNKNOWN": ("❓", "信号状态未知"),
}
DOMAIN_EMOJI = {"V6": "⚙️", "价值投资": "📊", "估值": "🔍", "Radar": "📡", "通用": "📌"}


def _portfolio_html(port_html: dict | None) -> str:
    if port_html is None:
        return "<p style='color:#888'>持仓数据不可用</p>"
    if "error" in port_html:
        return f"<p style='color:#c0392b'>持仓数据读取失败：{port_html['error']}</p>"

    positions    = port_html["positions"]
    alerts       = port_html["alerts"]
    last_updated = port_html.get("last_updated", "未知")

    # 告警横幅
    banner = ""
    if alerts:
        items = "".join(
            f"<li><b>{r['name']}</b> 当前 {r['current_pct']}% → 目标 {r['target_short']}</li>"
            for r in alerts
        )
        banner = (
            "<div style=\"background:#fff3cd;border-left:4px solid #f39c12;"
            "padding:8px 12px;margin:8px 0;border-radius:4px\">"
            f"⚠️ <b>仓位超目标 {len(alerts)} 项</b>"
            f"<ul style=\"margin:4px 0 0 16px;padding:0\">{items}</ul></div>"
        )

    rows_html = ""
    for p in positions:
        if p["status"] == "over":
            icon = "🔴"
            pct_color = "#e74c3c"
        elif p["status"] == "under":
            icon = "🔵"
            pct_color = "#3498db"
        else:
            icon = "✅"
            pct_color = "#27ae60"

        rows_html += (
            "<tr>"
            f"<td style=\"padding:3px 6px\">{icon} {p['name']}</td>"
            f"<td style=\"padding:3px 6px;text-align:right;font-weight:bold;color:{pct_color}\">"
            f"{p['current_pct']}%</td>"
            f"<td style=\"padding:3px 6px;text-align:right;color:#888\">{p['target_short']}</td>"
            f"<td style=\"padding:3px 6px;font-size:12px;color:#666\">{p['action']}</td>"
            "</tr>"
        )

    return (
        banner
        + "<table style=\"width:100%;font-size:13px;border-collapse:collapse\">"
        + "<tr style=\"background:#f5f5f5\">"
        + "<th style=\"padding:3px 6px;text-align:left\">标的（全资产口径）</th>"
        + "<th style=\"padding:3px 6px;text-align:right\">当前%</th>"
        + "<th style=\"padding:3px 6px;text-align:right\">阶段目标</th>"
        + "<th style=\"padding:3px 6px;text-align:left\">当前动作</th>"
        + "</tr>"
        + rows_html
        + "</table>"
        + f"<p style=\"margin:6px 0 0;font-size:11px;color:#999\">"
        + "🔴超目标 &nbsp; 🔵低于目标（建仓中）&nbsp; ✅正常"
        + f" &nbsp;｜ 全资产口径（富途+RSU+A股+港股通），文件更新于 {last_updated}</p>"
    )


def _events_html(events: list[dict]) -> str:
    if not events:
        return "<p style='color:#888'>未来7天无预设事件</p>"
    rows = ""
    for e in events:
        d = e["_days"]
        day_str = "今天" if d == 0 else ("明天" if d == 1 else f"{d}天后")
        action  = (
            f"<br><span style='color:#666;font-size:12px'>→ {e['action']}</span>"
            if e.get("action") else ""
        )
        emoji = DOMAIN_EMOJI.get(e.get("domain", ""), "📅")
        rows += (
            "<tr>"
            f"<td style=\"padding:3px 6px;white-space:nowrap\">"
            f"{e['date']} <span style=\"color:#888\">({day_str})</span></td>"
            f"<td style=\"padding:3px 6px\">{emoji} [{e.get('domain','')}] {e['text']}{action}</td>"
            "</tr>"
        )
    return f'<table style="width:100%;font-size:13px;border-collapse:collapse">{rows}</table>'


def _todos_html(todos: dict) -> str:
    if not todos:
        return "<p style='color:#888'>暂无待办</p>"
    html = ""
    for domain in ["V6", "价值投资", "估值", "Radar", "通用"]:
        items = todos.get(domain, [])
        if not items:
            continue
        emoji = DOMAIN_EMOJI.get(domain, "•")
        lis   = "".join(f'<li style="margin:3px 0">{i}</li>' for i in items[:5])
        html += (
            f'<div style="margin:8px 0"><b>{emoji} [{domain}]</b>'
            f'<ul style="margin:4px 0 0 16px;padding:0">{lis}</ul></div>'
        )
    return html or "<p style='color:#888'>暂无待办</p>"


def _workflow_actions_html(actions: list[dict]) -> str:
    if not actions:
        return (
            "<div style=\"background:#f6ffed;border-left:4px solid #52c41a;"
            "padding:8px 12px;margin:8px 0;border-radius:4px\">"
            "✅ 今日无必须动作。默认策略：等待，不主动增加系统复杂度。</div>"
        )

    color = {"HIGH": "#e74c3c", "MED": "#f39c12", "LOW": "#3498db"}
    label = {"HIGH": "必须处理", "MED": "建议准备", "LOW": "可选"}
    must_actions = [a for a in actions if a.get("priority") == "HIGH"]
    suggested_actions = [a for a in actions if a.get("priority") == "MED"]
    optional_actions = [a for a in actions if a.get("priority") == "LOW"]
    rows = ""
    for a in must_actions[:5]:
        c = color.get(a["priority"], "#888")
        rows += (
            "<tr>"
            f"<td style=\"padding:4px 6px;white-space:nowrap;color:{c};font-weight:bold\">"
            f"{label.get(a['priority'], a['priority'])}</td>"
            f"<td style=\"padding:4px 6px\">[{a['domain']}] {a['item']}<br>"
            f"<span style=\"color:#666;font-size:12px\">{a['reason']}</span></td>"
            f"<td style=\"padding:4px 6px;white-space:nowrap\">"
            f"<code>{a['trigger']}</code></td>"
            "</tr>"
        )
    if not rows:
        rows = (
            "<tr><td colspan=\"3\" style=\"padding:6px;color:#666\">"
            "今日无必须动作。默认策略：等待，不主动增加系统复杂度。</td></tr>"
        )
    optional_html = ""
    queue_actions = suggested_actions + optional_actions
    if queue_actions:
        optional_items = "".join(
            f"<li style=\"margin:2px 0\">[{a['domain']}] {a['item']} "
            f"<code>{a['trigger']}</code></li>"
            for a in queue_actions[:8]
        )
        optional_html = (
            "<div style=\"margin-top:8px;color:#666;font-size:12px\">"
            "<b>建议准备/研究队列：</b>"
            f"<ul style=\"margin:4px 0 0 16px;padding:0\">{optional_items}</ul>"
            "</div>"
        )
    return (
        "<table style=\"width:100%;font-size:13px;border-collapse:collapse\">"
        "<tr style=\"background:#f5f5f5\">"
        "<th style=\"padding:4px 6px;text-align:left;width:72px\">优先级</th>"
        "<th style=\"padding:4px 6px;text-align:left\">事项</th>"
        "<th style=\"padding:4px 6px;text-align:left;width:120px\">你对AI说</th>"
        "</tr>"
        f"{rows}</table>"
        f"{optional_html}"
        "<p style=\"margin:6px 0 0;font-size:11px;color:#999\">"
        "原则：先分析，再归档；主仓走财报重估/估值更新，Radar走样本复盘。</p>"
    )


def build_html(
    v6: dict,
    port_html: dict | None,
    futu: dict | None,
    events: list,
    todos: dict,
    quota: dict | None,
    workflow_actions: list[dict],
    stale_status: dict | None = None,
) -> str:
    today_str = date.today().strftime("%Y年%m月%d日")
    now_str   = datetime.now().strftime("%H:%M")

    sig_icon, sig_text = SIGNAL_LABEL.get(v6["signal"], ("❓", v6["signal"]))
    recon_ok = "PASS ✓" if not v6["recon_events"] else f"⚠️ {len(v6['recon_events'])} 个异常"

    # V6 持仓行（从 Futu 取实时价，不可用则只显示数量）
    v6_rows = ""
    COSTS = {"US.AMZN": 271.73, "US.AVGO": 427.38, "US.BIL": 91.48,
             "US.GLD": 434.43, "US.GOOGL": 394.56}
    futu_pos = futu["positions"] if futu else {}

    for code, qty in v6["positions"].items():
        cost   = COSTS.get(code, 0)
        ticker = code.replace("US.", "")
        if code in futu_pos:
            mv_local = futu_pos[code]["mv_local"]
            cur = mv_local / qty if qty else 0
            pnl = (cur - cost) * qty
            pct = (cur - cost) / cost * 100 if cost else 0
            color = "#e74c3c" if pnl < 0 else "#27ae60"
            v6_rows += (
                f"<tr><td style=\"padding:2px 6px\">{ticker}</td>"
                f"<td style=\"padding:2px 6px;text-align:right\">{int(qty)}</td>"
                f"<td style=\"padding:2px 6px;text-align:right\">{cur:.2f}</td>"
                f"<td style=\"padding:2px 6px;text-align:right;color:{color}\">"
                f"{pnl:+.2f} ({pct:+.1f}%)</td></tr>"
            )
        else:
            v6_rows += (
                f"<tr><td style=\"padding:2px 6px\">{ticker}</td>"
                f"<td style=\"padding:2px 6px;text-align:right\">{int(qty)}</td>"
                f"<td style=\"padding:2px 6px;text-align:right\">—</td>"
                f"<td style=\"padding:2px 6px;text-align:right\">—</td></tr>"
            )

    quota_html = ""
    if quota:
        used, total_q = quota["used"], quota["total"]
        pct_q   = used / total_q * 100 if total_q else 0
        color_q = "#e74c3c" if pct_q > 80 else ("#f39c12" if pct_q > 60 else "#27ae60")
        quota_html = (
            f"<p style=\"margin:4px 0;font-size:13px\">📡 历史K线额度："
            f"<b style=\"color:{color_q}\">{used}/{total_q}（{pct_q:.0f}%已用）</b></p>"
        )

    stale_banner_html = ""
    if stale_status and stale_status.get("is_stale"):
        signal_date = stale_status.get("signal_date", "未知")
        buy_count = stale_status.get("buy_order_count", 0)
        sell_count = stale_status.get("sell_order_count", 0)
        sell_review = stale_status.get("sell_orders_need_review", False)
        blocked_line = (
            f"&nbsp;&nbsp;🔴 <b>STALE_DATA_BLOCKED</b>：{buy_count} 笔 BUY 已阻断，信号过期"
            if buy_count > 0 else ""
        )
        review_line = (
            f"&nbsp;&nbsp;🟡 <b>RISK_EXIT_PENDING</b>：{sell_count} 笔 SELL 需人工复核"
            if sell_review and sell_count > 0 else ""
        )
        stale_banner_html = (
            "<div style=\"background:#fff7ed;border:2px solid #f97316;"
            "padding:8px 12px;border-radius:6px;margin:6px 0\">"
            f"⚠️ <b>V6 当前处于 STALE_DATA_MODE — 进攻信号已过期（{signal_date}）</b><br>"
            "<span style=\"font-size:12px;color:#78350f\">"
            "有K线时用完整信号；没有K线时只允许刹车，不允许踩油门。所有 BUY/ADD 已阻断。</span>"
            + (f"<br><span style=\"font-size:12px\">{blocked_line}</span>" if blocked_line else "")
            + (f"<br><span style=\"font-size:12px\">{review_line}</span>" if review_line else "")
            + "</div>"
        )

    # 全局告警横幅
    global_alerts = ""
    if port_html and not port_html.get("error") and port_html.get("alerts"):
        names = "、".join(r["name"] for r in port_html["alerts"])
        global_alerts = (
            "<div style=\"background:#fff3cd;border:1px solid #f39c12;"
            "padding:8px 12px;border-radius:6px;margin-bottom:12px\">"
            f"⚠️ <b>仓位超目标：{names}</b> — 需要减仓处理</div>"
        )

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
  body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;font-size:14px;color:#222;max-width:640px;margin:0 auto;padding:16px}}
  h2{{color:#1a1a2e;border-bottom:2px solid #1a1a2e;padding-bottom:6px;margin-bottom:4px}}
  h3{{color:#2c3e50;margin:18px 0 6px;font-size:15px}}
  table{{border-collapse:collapse;width:100%}}
  th{{background:#f0f0f0;padding:3px 6px;text-align:left;font-size:13px}}
  .footer{{margin-top:20px;font-size:11px;color:#999;border-top:1px solid #eee;padding-top:8px}}
</style>
</head><body>

<h2>📋 早间简报 · {today_str}</h2>
<p style="color:#888;margin:-6px 0 12px;font-size:12px">生成于 {now_str} · Dingcle AI 投资公司</p>

{global_alerts}

<h3>🎯 今日动作清单（工作流入口）</h3>
{_workflow_actions_html(workflow_actions)}

<h3>⚙️ [V6] 量化策略</h3>
{stale_banner_html}
<table style="font-size:13px">
  <tr><td style="padding:2px 6px;width:120px">Reconciliation</td><td>{recon_ok}</td></tr>
  <tr><td style="padding:2px 6px">换仓信号</td><td>{sig_icon} {sig_text}</td></tr>
  <tr><td style="padding:2px 6px">Pending 订单</td><td>{"无" if v6["pending_count"]==0 else f"⚠️ {v6['pending_count']} 笔"}</td></tr>
</table>
<table style="font-size:13px;margin-top:6px">
  <tr style="background:#f5f5f5"><th>标的</th><th style="text-align:right">数量</th><th style="text-align:right">现价</th><th style="text-align:right">浮盈亏</th></tr>
  {v6_rows}
</table>

<h3>📊 [价值投资] 持仓权重监控（全资产口径）</h3>
{_portfolio_html(port_html)}

<h3>📅 [估值] 近期事件</h3>
{_events_html(events)}
{quota_html}

<h3>📌 当前待办（近14天）</h3>
{_todos_html(todos)}

<div class="footer">
  morning_brief.py · 每日北京时间 09:00 自动发送<br>
  持仓数据：26年阶段性组合策略计划.html（用户手动更新）· V6实时价：Futu OpenD · 事件：events_calendar.json<br>
  添加事件：编辑 events_calendar.json &nbsp;｜&nbsp; 添加待办：python3 collab_sync.py add-gpt "[域] [待办] 内容"
</div>
</body></html>"""


def build_plain(
    v6: dict,
    port_html: dict | None,
    futu: dict | None,
    events: list,
    todos: dict,
    quota: dict | None,
    workflow_actions: list[dict],
    stale_status: dict | None = None,
) -> str:
    today_str = date.today().isoformat()
    sig_icon, sig_text = SIGNAL_LABEL.get(v6["signal"], ("❓", v6["signal"]))
    lines = [f"📋 早间简报 · {today_str}", ""]

    lines += ["🎯 [今日动作清单]"]
    if workflow_actions:
        must_actions = [a for a in workflow_actions if a.get("priority") == "HIGH"]
        queue_actions = [a for a in workflow_actions if a.get("priority") != "HIGH"]
        if must_actions:
            lines.append("   必须处理：")
            for a in must_actions[:5]:
                lines.append(
                    f"   HIGH [{a['domain']}] {a['item']} → 对AI说：{a['trigger']}"
                )
        else:
            lines.append("   ✅ 今日无必须动作。默认策略：等待。")
        if queue_actions:
            lines.append("   建议准备/研究队列：")
        for a in queue_actions[:8]:
            lines.append(
                f"   {a['priority']:<4} [{a['domain']}] {a['item']} → 对AI说：{a['trigger']}"
            )
    else:
        lines.append("   ✅ 今日无必须动作。默认策略：等待。")
    lines.append("")

    v6_lines = ["⚙️  [V6]"]
    if stale_status and stale_status.get("is_stale"):
        signal_date = stale_status.get("signal_date", "未知")
        v6_lines.append(f"   ⚠️ STALE_DATA_MODE（信号日期：{signal_date}）— 所有 BUY/ADD 已阻断")
        if stale_status.get("sell_orders_need_review") and stale_status.get("sell_order_count", 0) > 0:
            v6_lines.append(f"   🟡 RISK_EXIT_PENDING：{stale_status['sell_order_count']} 笔 SELL 需人工复核")
    v6_lines += [
        f"   Reconciliation : {'PASS ✓' if not v6['recon_events'] else '⚠️ 有异常'}",
        f"   换仓信号       : {sig_icon} {sig_text}",
        "   Pending订单    : " + ("无" if v6["pending_count"] == 0 else f"⚠️ {v6['pending_count']}笔"),
    ]
    lines += v6_lines
    for code, qty in v6["positions"].items():
        lines.append(f"     {code.replace('US.',''):<8} × {int(qty)}")

    if port_html and "error" not in port_html:
        alerts    = port_html.get("alerts", [])
        positions = port_html.get("positions", [])
        last_upd  = port_html.get("last_updated", "?")
        lines += ["", f"📊 [价值投资] 全资产口径（更新至{last_upd}）"]
        if alerts:
            lines.append("   ⚠️ 超目标告警：")
            for r in alerts:
                lines.append(f"   🔴 {r['name']:<14} {r['current_pct']:>5.1f}%  目标 {r['target_short']}")
        for p in positions:
            if p["status"] == "over":
                continue  # already shown above
            icon = "🔵" if p["status"] == "under" else "✅"
            lines.append(
                f"   {icon} {p['name']:<14} {p['current_pct']:>5.1f}%  目标 {p['target_short']}"
            )
    elif port_html and "error" in port_html:
        lines += ["", f"📊 [价值投资] 读取失败：{port_html['error']}"]

    if events:
        lines += ["", "📅 [事件日历]"]
        for e in events:
            d       = e["_days"]
            day_str = "今天" if d == 0 else ("明天" if d == 1 else f"{d}天后")
            lines.append(f"   {e['date']} ({day_str}) [{e.get('domain','')}] {e['text']}")

    if quota:
        lines += ["", f"📡 [K线额度] {quota['used']}/{quota['total']} 已用"]

    all_todos = [(dom, item) for dom, items in todos.items() for item in items[:3]]
    if all_todos:
        lines += ["", "📌 [待办]"]
        for dom, item in all_todos:
            lines.append(f"   {DOMAIN_EMOJI.get(dom,'•')} [{dom}] {item}")

    return "\n".join(lines)


# ── 邮件 ─────────────────────────────────────────────────────────────────────

def send_email(subject: str, html_content: str) -> bool:
    try:
        notifier = importlib.import_module("notifier").EmailNotifier()
        sent = bool(notifier.send(subject, html_content, is_html=True))
        if sent:
            print(f"✓ 邮件已发送 → {getattr(notifier,'recipient','?')}")
        else:
            print("⚠️  邮件发送失败")
        return sent
    except Exception as e:
        print(f"✗ notifier 不可用: {e}")
        return False


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-email", "--dry-run", action="store_true")
    args = parser.parse_args()

    print(f"[{datetime.now().strftime('%H:%M:%S')}] 生成早间简报（全投资体系版）...")

    v6           = collect_v6()
    port_html    = collect_portfolio_html()
    futu         = collect_portfolio_futu()   # 仅用于 V6 实时价格，失败不影响主报告
    events       = collect_events(days_ahead=7)
    todos        = collect_todos()
    quota        = collect_kline_quota()
    stale_status = collect_stale_data_status()
    workflows    = collect_workflow_actions(events, stale_status=stale_status)

    # 打印持仓监控状态
    if port_html and "error" not in port_html:
        n_pos    = len(port_html.get("positions", []))
        n_alerts = len(port_html.get("alerts", []))
        last_upd = port_html.get("last_updated", "?")
        print(f"  持仓监控：{n_pos} 个仓位，{n_alerts} 项超目标告警（HTML更新至 {last_upd}）")
    elif port_html and "error" in port_html:
        print(f"  持仓监控：HTML读取失败（{port_html['error']}）")

    if futu:
        print(f"  Futu实时价：已连接（V6仓位实时浮盈可用）")
    else:
        print(f"  Futu实时价：OpenD未运行，V6仓位显示—")

    if quota:
        print(f"  K线额度：{quota['used']}/{quota['total']}")

    html_content = build_html(v6, port_html, futu, events, todos, quota, workflows, stale_status=stale_status)
    plain_text   = build_plain(v6, port_html, futu, events, todos, quota, workflows, stale_status=stale_status)

    if stale_status.get("is_stale"):
        print(f"  ⚠️  V6 STALE_DATA_MODE（信号日期：{stale_status.get('signal_date', '未知')}）")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    tag = datetime.now().strftime("%Y%m%dT%H%M%S")
    (OUTPUT_DIR / f"morning_brief_{tag}.html").write_text(html_content, encoding="utf-8")
    (OUTPUT_DIR / "latest.html").write_text(html_content, encoding="utf-8")

    print("\n" + plain_text + "\n")

    if not args.no_email:
        alert_count = len(port_html.get("alerts", [])) if port_html and "error" not in port_html else 0
        subject = (
            f"📋 早间简报 {date.today()} · V6 {v6['signal']}"
            + (f" · ⚠️{alert_count}项超目标" if alert_count else "")
        )
        send_email(subject, html_content)
    else:
        print("(--no-email: 跳过发送)")


if __name__ == "__main__":
    sys.exit(main())
