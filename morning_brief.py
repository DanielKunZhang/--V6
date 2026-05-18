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


def collect_workflow_actions(events: list[dict]) -> list[dict]:
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
    # A股 Radar 是小资金短线实验仓，若当天有交易/候选，应日更复盘。
    if today.weekday() < 5:
        add(
            "LOW",
            "Radar-CN",
            "A股 Radar 日更复盘（仅当今天有候选/交易/观察标的时执行）",
            "复盘 A股Radar",
            "A股 Radar 需要高频训练；无交易或无候选则可忽略",
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
    rows = ""
    for a in actions:
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
    return (
        "<table style=\"width:100%;font-size:13px;border-collapse:collapse\">"
        "<tr style=\"background:#f5f5f5\">"
        "<th style=\"padding:4px 6px;text-align:left;width:72px\">优先级</th>"
        "<th style=\"padding:4px 6px;text-align:left\">事项</th>"
        "<th style=\"padding:4px 6px;text-align:left;width:120px\">你对AI说</th>"
        "</tr>"
        f"{rows}</table>"
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
) -> str:
    today_str = date.today().isoformat()
    sig_icon, sig_text = SIGNAL_LABEL.get(v6["signal"], ("❓", v6["signal"]))
    lines = [f"📋 早间简报 · {today_str}", ""]

    lines += ["🎯 [今日动作清单]"]
    if workflow_actions:
        for a in workflow_actions:
            lines.append(
                f"   {a['priority']:<4} [{a['domain']}] {a['item']} → 对AI说：{a['trigger']}"
            )
    else:
        lines.append("   ✅ 今日无必须动作。默认策略：等待。")
    lines.append("")

    lines += [
        "⚙️  [V6]",
        f"   Reconciliation : {'PASS ✓' if not v6['recon_events'] else '⚠️ 有异常'}",
        f"   换仓信号       : {sig_icon} {sig_text}",
        "   Pending订单    : " + ("无" if v6["pending_count"] == 0 else f"⚠️ {v6['pending_count']}笔"),
    ]
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

    v6        = collect_v6()
    port_html = collect_portfolio_html()
    futu      = collect_portfolio_futu()   # 仅用于 V6 实时价格，失败不影响主报告
    events    = collect_events(days_ahead=7)
    todos     = collect_todos()
    quota     = collect_kline_quota()
    workflows = collect_workflow_actions(events)

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

    html_content = build_html(v6, port_html, futu, events, todos, quota, workflows)
    plain_text   = build_plain(v6, port_html, futu, events, todos, quota, workflows)

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
