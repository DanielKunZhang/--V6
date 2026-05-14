#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from morning_brief import collect_events, collect_portfolio_futu, collect_portfolio_html, collect_v6


ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "backtest_results" / "central_risk_board"
CASH_ALPHA_FUTU_SNAPSHOT = ROOT / "cash_alpha_v3_repo" / "backtest_results" / "futu_account_snapshot_latest.json"
ATTACK_PREVIEW_DIR = ROOT / "backtest_results" / "attack_engine_live_preview"


SPECIAL_SLEEVES = {
    "V6 量化策略仓": "V6",
    "Radar": "Radar Overlay",
    "卫星实验": "Experimental",
    "富途现金": "Cash Buffer",
}

THEME_MAP = {
    "腾讯": "中国平台互联网",
    "PDD": "中国平台互联网",
    "TME": "中国平台互联网",
    "美的": "中国制造/家电",
    "招商银行": "中国金融",
    "泡泡玛特": "中国消费/IP",
    "NVDA": "AI半导体",
    "ADBE": "美国软件",
    "NU": "拉美金融科技",
    "IT": "IT服务",
    "富途现金": "现金缓冲",
    "V6 量化策略仓": "系统化进攻",
    "Radar": "动态研究输入",
    "卫星实验": "高弹性实验",
}

V6_THEME_MAP = {
    "US.AMZN": "美国平台/云",
    "US.AVGO": "AI半导体",
    "US.GOOGL": "美国平台/AI",
    "US.NVDA": "AI半导体",
    "US.BIL": "现金类防守",
    "US.GLD": "黄金防守",
}


def fmt_pct(value: float) -> str:
    return f"{value:.1f}%"


def fmt_usd(value: float | None) -> str:
    if value is None:
        return "—"
    return f"${value:,.0f}"


def fmt_dt(value: str) -> str:
    return value or "unknown"


def fmt_age_days(value: int | None) -> str:
    if value is None:
        return "unknown"
    return f"{value}d"


def fmt_age_hours(value: float | None) -> str:
    if value is None:
        return "unknown"
    return f"{value:.1f}h"


def sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): sanitize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    if hasattr(value, "isoformat") and callable(value.isoformat):
        try:
            return value.isoformat()
        except Exception:
            return str(value)
    return value


def classify_sleeve(name: str) -> str:
    if name in SPECIAL_SLEEVES:
        return SPECIAL_SLEEVES[name]
    return "Value Main Book"


def classify_theme(name: str) -> str:
    return THEME_MAP.get(name, "其他/待映射")


def normalize_v6_name(code: str) -> str:
    return code.replace("US.", "").replace("HK.", "")


def parse_dt(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        pass
    try:
        return datetime.combine(date.fromisoformat(value), datetime.min.time())
    except ValueError:
        return None


def latest_json_path(directory: Path) -> Path | None:
    if not directory.exists():
        return None
    files = sorted([path for path in directory.iterdir() if path.suffix == ".json"], key=lambda path: path.stat().st_mtime, reverse=True)
    return files[0] if files else None


def load_cached_futu_snapshot() -> dict[str, Any]:
    latest_attack_preview = latest_json_path(ATTACK_PREVIEW_DIR)
    candidates = [CASH_ALPHA_FUTU_SNAPSHOT, latest_attack_preview]
    for path in candidates:
        if not path or not path.exists():
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if raw:
            return {"raw": raw, "path": str(path)}
    return {"raw": {}, "path": ""}


def build_futu_snapshot() -> dict[str, Any]:
    live = collect_portfolio_futu()
    if live:
        positions = live.get("positions", {})
        long_mv_hkd = round(sum(float(item.get("mv_local", 0.0)) for item in positions.values()), 2)
        return {
            "available": True,
            "scope": "broker_account_only",
            "mode": "opend_live",
            "source": "futu_opend_live",
            "snapshot_path": "",
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "net_liquidation_usd": None,
            "available_cash_usd": None,
            "strategy_capital_usd": None,
            "positions_count": len([qty for qty in positions.values() if float(qty.get("qty", 0.0)) > 0]),
            "long_positions_market_value_usd": None,
            "long_positions_market_value_hkd": long_mv_hkd,
            "reserve_sellable_usd": None,
            "warnings": [],
        }

    cached = load_cached_futu_snapshot()
    raw = cached.get("raw", {})
    if not raw:
        return {
            "available": False,
            "scope": "broker_account_only",
            "mode": "unavailable",
            "source": "none",
            "snapshot_path": "",
            "timestamp": "",
            "net_liquidation_usd": None,
            "available_cash_usd": None,
            "strategy_capital_usd": None,
            "positions_count": 0,
            "long_positions_market_value_usd": None,
            "long_positions_market_value_hkd": None,
            "reserve_sellable_usd": None,
            "warnings": ["futu_snapshot_unavailable"],
        }

    summary = raw.get("position_summary", {}) if isinstance(raw.get("position_summary"), dict) else {}
    return {
        "available": True,
        "scope": "broker_account_only",
        "mode": "cached_snapshot",
        "source": raw.get("source", "cached_snapshot"),
        "snapshot_path": cached.get("path", ""),
        "timestamp": raw.get("timestamp", ""),
        "net_liquidation_usd": float(raw.get("net_liquidation_usd", 0.0)) if raw.get("net_liquidation_usd") is not None else None,
        "available_cash_usd": float(raw.get("available_cash_usd", 0.0)) if raw.get("available_cash_usd") is not None else None,
        "strategy_capital_usd": float(raw.get("strategy_capital_usd", 0.0)) if raw.get("strategy_capital_usd") is not None else None,
        "positions_count": int(summary.get("positions_count", len(raw.get("positions", [])))),
        "long_positions_market_value_usd": float(summary.get("long_positions_market_value_usd", 0.0)) if summary.get("long_positions_market_value_usd") is not None else None,
        "long_positions_market_value_hkd": None,
        "reserve_sellable_usd": float(summary.get("reserve_positions_sellable_usd", 0.0)) if summary.get("reserve_positions_sellable_usd") is not None else None,
        "warnings": raw.get("snapshot_warnings", []),
    }


def build_firm_snapshot(positions: list[dict[str, Any]]) -> dict[str, Any]:
    investable = [row for row in positions if row["current_pct"] > 0 and row["name"] != "富途现金"]
    sorted_rows = sorted(investable, key=lambda item: item["current_pct"], reverse=True)
    top5 = sorted_rows[:5]
    top2_sum = round(sum(item["current_pct"] for item in sorted_rows[:2]), 1)
    top3_sum = round(sum(item["current_pct"] for item in sorted_rows[:3]), 1)
    top5_sum = round(sum(item["current_pct"] for item in top5), 1)
    max_position = top5[0]["current_pct"] if top5 else 0.0
    return {
        "top5": top5,
        "top2_sum": top2_sum,
        "top3_sum": top3_sum,
        "top5_sum": top5_sum,
        "max_position": max_position,
    }


def build_sleeve_rows(positions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    for row in positions:
        sleeve = classify_sleeve(row["name"])
        bucket = buckets.setdefault(
            sleeve,
            {"sleeve": sleeve, "current_pct": 0.0, "names": [], "over_count": 0, "under_count": 0},
        )
        bucket["current_pct"] += float(row["current_pct"])
        if row["current_pct"] > 0:
            bucket["names"].append(row["name"])
        if row["status"] == "over":
            bucket["over_count"] += 1
        if row["status"] == "under":
            bucket["under_count"] += 1
    rows = []
    order = ["Value Main Book", "V6", "Radar Overlay", "Experimental", "Cash Buffer"]
    for sleeve in order:
        if sleeve not in buckets:
            continue
        row = buckets[sleeve]
        row["current_pct"] = round(row["current_pct"], 1)
        row["names"] = " / ".join(row["names"][:6]) if row["names"] else "—"
        rows.append(row)
    return rows


def build_theme_rows(positions: list[dict[str, Any]], v6_positions: dict[str, float]) -> list[dict[str, Any]]:
    theme_totals: dict[str, float] = {}
    for row in positions:
        pct = float(row["current_pct"])
        if pct <= 0:
            continue
        theme = classify_theme(row["name"])
        theme_totals[theme] = theme_totals.get(theme, 0.0) + pct

    for code in v6_positions:
        theme = V6_THEME_MAP.get(code, "V6未映射主题")
        # v1 先只标主题存在，不把 V6 managed state 二次计入总账户百分比，避免与主账本重复计算
        theme_totals.setdefault(theme, theme_totals.get(theme, 0.0))

    rows = [
        {"theme": theme, "current_pct": round(weight, 1)}
        for theme, weight in theme_totals.items()
        if weight > 0
    ]
    rows.sort(key=lambda item: item["current_pct"], reverse=True)
    return rows


def build_overlap_section(positions: list[dict[str, Any]], v6_positions: dict[str, float]) -> dict[str, Any]:
    main_names = {row["name"] for row in positions if classify_sleeve(row["name"]) == "Value Main Book" and row["current_pct"] > 0}
    v6_plain = {normalize_v6_name(code) for code, qty in v6_positions.items() if qty > 0}
    direct_overlap = sorted(main_names & v6_plain)

    main_themes = {classify_theme(row["name"]) for row in positions if classify_sleeve(row["name"]) == "Value Main Book" and row["current_pct"] > 0}
    v6_themes = {V6_THEME_MAP.get(code, "V6未映射主题") for code, qty in v6_positions.items() if qty > 0}
    thematic_overlap = sorted(main_themes & v6_themes)

    return {
        "direct_overlap": direct_overlap,
        "thematic_overlap": thematic_overlap,
    }


def build_freshness(payload_generated_at: str, portfolio_last_updated: str, v6_state_updated: str, futu_snapshot: dict[str, Any]) -> dict[str, Any]:
    now = parse_dt(payload_generated_at) or datetime.now()
    rows: list[dict[str, Any]] = []
    red_reasons: list[str] = []
    yellow_reasons: list[str] = []

    ledger_dt = parse_dt(portfolio_last_updated)
    ledger_age_days: int | None = None
    ledger_status = "RED"
    if ledger_dt:
        ledger_age_days = (now.date() - ledger_dt.date()).days
        ledger_status = "OK"
        if ledger_age_days >= 8:
            ledger_status = "RED"
            red_reasons.append(f"ledger_stale={ledger_age_days}d")
        elif ledger_age_days >= 4:
            ledger_status = "YELLOW"
            yellow_reasons.append(f"ledger_age={ledger_age_days}d")
    else:
        red_reasons.append("ledger_date_missing")
    rows.append(
        {
            "item": "Master risk ledger",
            "updated_at": portfolio_last_updated or "unknown",
            "age": fmt_age_days(ledger_age_days),
            "status": ledger_status,
            "note": "26年阶段性组合策略计划.html",
        }
    )

    v6_dt = parse_dt(v6_state_updated)
    v6_age_hours: float | None = None
    v6_status = "RED"
    if v6_dt:
        v6_age_hours = round((now - v6_dt).total_seconds() / 3600, 1)
        v6_status = "OK"
        if v6_age_hours >= 96:
            v6_status = "RED"
            red_reasons.append(f"v6_state_stale={v6_age_hours:.1f}h")
        elif v6_age_hours >= 48:
            v6_status = "YELLOW"
            yellow_reasons.append(f"v6_state_age={v6_age_hours:.1f}h")
    else:
        red_reasons.append("v6_state_missing")
    rows.append(
        {
            "item": "V6 managed state",
            "updated_at": v6_state_updated or "unknown",
            "age": fmt_age_hours(v6_age_hours),
            "status": v6_status,
            "note": "managed positions / blockers",
        }
    )

    futu_dt = parse_dt(futu_snapshot.get("timestamp", ""))
    futu_age_hours: float | None = None
    futu_status = "YELLOW"
    if futu_snapshot.get("available") and futu_dt:
        futu_age_hours = round((now - futu_dt).total_seconds() / 3600, 1)
        futu_status = "OK"
        if futu_age_hours >= 72:
            futu_status = "RED"
            red_reasons.append(f"futu_snapshot_stale={futu_age_hours:.1f}h")
        elif futu_age_hours >= 24:
            futu_status = "YELLOW"
            yellow_reasons.append(f"futu_snapshot_age={futu_age_hours:.1f}h")
    else:
        yellow_reasons.append("futu_snapshot_unavailable")
    rows.append(
        {
            "item": "Futu broker snapshot",
            "updated_at": futu_snapshot.get("timestamp", "unknown") or "unknown",
            "age": fmt_age_hours(futu_age_hours),
            "status": futu_status,
            "note": futu_snapshot.get("mode", "unknown"),
        }
    )

    return {
        "rows": rows,
        "red_reasons": red_reasons,
        "yellow_reasons": yellow_reasons,
    }


def classify_board_status(snapshot: dict[str, Any], themes: list[dict[str, Any]], alerts: list[dict[str, Any]], freshness: dict[str, Any]) -> tuple[str, list[str]]:
    reasons: list[str] = []
    top_theme = themes[0]["current_pct"] if themes else 0.0
    if snapshot["max_position"] >= 25.0:
        reasons.append(f"single_position>{snapshot['max_position']:.1f}%")
    if snapshot["top2_sum"] >= 50.0:
        reasons.append(f"top2_sum={snapshot['top2_sum']:.1f}%")
    if top_theme >= 45.0:
        reasons.append(f"top_theme={top_theme:.1f}%")
    reasons.extend(freshness.get("red_reasons", []))
    if reasons:
        return "RED", reasons

    yellow: list[str] = []
    if snapshot["max_position"] >= 15.0:
        yellow.append(f"single_position>{snapshot['max_position']:.1f}%")
    if snapshot["top3_sum"] >= 55.0:
        yellow.append(f"top3_sum={snapshot['top3_sum']:.1f}%")
    if len(alerts) >= 3:
        yellow.append(f"target_alerts={len(alerts)}")
    yellow.extend(freshness.get("yellow_reasons", []))
    if yellow:
        return "YELLOW", yellow
    return "GREEN", []


def render_table(rows: list[dict[str, Any]], columns: list[tuple[str, str]]) -> list[str]:
    if not rows:
        return ["_None_"]
    out = [
        "| " + " | ".join(label for _, label in columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in rows:
        out.append("| " + " | ".join(str(row.get(key, "")) for key, _ in columns) + " |")
    return out


def build_payload() -> dict[str, Any]:
    portfolio = collect_portfolio_html()
    v6 = collect_v6()
    events = collect_events(14)
    generated_at = datetime.now().isoformat(timespec="seconds")
    positions = portfolio.get("positions", [])
    alerts = portfolio.get("alerts", [])
    snapshot = build_firm_snapshot(positions)
    sleeves = build_sleeve_rows(positions)
    themes = build_theme_rows(positions, v6.get("positions", {}))
    overlap = build_overlap_section(positions, v6.get("positions", {}))
    futu_snapshot = build_futu_snapshot()
    freshness = build_freshness(generated_at, portfolio.get("last_updated", ""), v6.get("state_updated", ""), futu_snapshot)
    status, reasons = classify_board_status(snapshot, themes, alerts, freshness)
    return {
        "generated_at": generated_at,
        "portfolio_last_updated": portfolio.get("last_updated", ""),
        "status": status,
        "status_reasons": reasons,
        "portfolio_error": portfolio.get("error", ""),
        "firm_snapshot": snapshot,
        "sleeves": sleeves,
        "themes": themes[:8],
        "freshness": freshness,
        "futu_snapshot": futu_snapshot,
        "target_alerts": alerts,
        "v6": {
            "signal": v6.get("signal", "UNKNOWN"),
            "blockers": v6.get("blockers", []),
            "managed_positions": v6.get("positions", {}),
            "state_updated": v6.get("state_updated", ""),
        },
        "overlap": overlap,
        "events": events,
        "known_limits": [
            "v1 total-account view still relies on 26年阶段性组合策略计划.html as the master risk ledger.",
            "v1 does not yet explode V6 managed holdings into total-account percentage weights automatically.",
            "Futu snapshot is currently used as broker-level sanity/freshness only, not a full-firm denominator.",
            "theme mapping is partly manual and should be upgraded into a formal mapping table.",
        ],
    }


def write_markdown(path: Path, payload: dict[str, Any]) -> None:
    snapshot = payload["firm_snapshot"]
    lines = [
        "# Central Risk Board v1.1",
        "",
        f"- Generated: `{payload['generated_at']}`",
        f"- Master risk ledger date: `{payload['portfolio_last_updated']}`",
        f"- Overall status: `{payload['status']}`",
        f"- Status reasons: `{', '.join(payload['status_reasons']) or 'none'}`",
        "",
        "## One-Line Read",
        "",
    ]

    if payload["status"] == "RED":
        lines.append("- 当前不是“策略坏了”，而是总账户集中度仍然过高，核心风险继续集中在少数大仓与单一主题。")
    elif payload["status"] == "YELLOW":
        lines.append("- 当前总账户可运行，但集中度和目标偏离已经需要正式讨论，不能只靠感觉管理。")
    else:
        lines.append("- 当前总账户风险大体在可接受范围内，中央风险层未发现明显失真。")

    lines.extend(
        [
            "",
            "## Firm Snapshot",
            "",
            f"- Top 2 positions sum: `{fmt_pct(snapshot['top2_sum'])}`",
            f"- Top 3 positions sum: `{fmt_pct(snapshot['top3_sum'])}`",
            f"- Top 5 positions sum: `{fmt_pct(snapshot['top5_sum'])}`",
            f"- Largest single position: `{fmt_pct(snapshot['max_position'])}`",
            "",
            "### Top Positions",
            "",
        ]
    )
    top_rows = [
        {"name": row["name"], "current_pct": fmt_pct(row["current_pct"]), "target": row["target_short"], "action": row["action"]}
        for row in snapshot["top5"]
    ]
    lines.extend(render_table(top_rows, [("name", "position"), ("current_pct", "current"), ("target", "target"), ("action", "action")]))

    lines.extend(["", "## Sleeve Risk", ""])
    sleeve_rows = [
        {
            "sleeve": row["sleeve"],
            "current_pct": fmt_pct(row["current_pct"]),
            "over_count": row["over_count"],
            "under_count": row["under_count"],
            "names": row["names"],
        }
        for row in payload["sleeves"]
    ]
    lines.extend(
        render_table(
            sleeve_rows,
            [("sleeve", "sleeve"), ("current_pct", "current"), ("over_count", "over-target"), ("under_count", "under-target"), ("names", "main names")],
        )
    )

    lines.extend(["", "## Theme Concentration", ""])
    theme_rows = [{"theme": row["theme"], "current_pct": fmt_pct(row["current_pct"])} for row in payload["themes"]]
    lines.extend(render_table(theme_rows, [("theme", "theme"), ("current_pct", "current")]))

    lines.extend(["", "## Data Freshness", ""])
    freshness_rows = payload["freshness"]["rows"]
    lines.extend(
        render_table(
            freshness_rows,
            [("item", "item"), ("updated_at", "updated_at"), ("age", "age"), ("status", "status"), ("note", "note")],
        )
    )

    lines.extend(["", "## Futu Broker Snapshot", ""])
    futu_snapshot = payload["futu_snapshot"]
    if futu_snapshot["available"]:
        lines.append("- Scope: `Futu broker account only`; 这里只做经纪商层 sanity check，不替代总账户主账本。")
        lines.append(f"- Mode: `{futu_snapshot['mode']}`")
        lines.append(f"- Timestamp: `{fmt_dt(futu_snapshot['timestamp'])}`")
        lines.append(f"- Net liquidation: `{fmt_usd(futu_snapshot['net_liquidation_usd'])}`")
        lines.append(f"- Available cash: `{fmt_usd(futu_snapshot['available_cash_usd'])}`")
        lines.append(f"- Strategy capital (program view): `{fmt_usd(futu_snapshot['strategy_capital_usd'])}`")
        lines.append(f"- Positions count: `{futu_snapshot['positions_count']}`")
        lines.append(f"- Long market value: `{fmt_usd(futu_snapshot['long_positions_market_value_usd'])}`")
        lines.append(f"- Reserve sellable: `{fmt_usd(futu_snapshot['reserve_sellable_usd'])}`")
        if futu_snapshot.get("warnings"):
            lines.append(f"- Snapshot warnings: `{'; '.join(futu_snapshot['warnings'])}`")
    else:
        lines.append("- Futu broker snapshot unavailable. 中央风控仍可运行，但经纪商层 sanity check 暂时失明。")

    lines.extend(["", "## Overlap Risk", ""])
    direct = payload["overlap"]["direct_overlap"]
    thematic = payload["overlap"]["thematic_overlap"]
    lines.append(f"- Direct main-book vs V6 name overlap: `{', '.join(direct) if direct else 'none'}`")
    lines.append(f"- Thematic overlap between main-book and V6: `{', '.join(thematic) if thematic else 'none'}`")
    lines.append(f"- V6 operational signal: `{payload['v6']['signal']}`")
    lines.append(f"- V6 blockers: `{payload['v6']['blockers']}`")
    lines.append(f"- V6 managed state updated: `{fmt_dt(payload['v6']['state_updated'])}`")

    lines.extend(["", "## Target Drift Alerts", ""])
    alert_rows = [
        {"name": row["name"], "current_pct": fmt_pct(row["current_pct"]), "target": row["target_short"], "action": row["action"]}
        for row in payload["target_alerts"]
    ]
    lines.extend(render_table(alert_rows, [("name", "name"), ("current_pct", "current"), ("target", "target"), ("action", "action")]))

    lines.extend(["", "## Event Window (14d)", ""])
    event_rows = [
        {
            "date": row["date"],
            "domain": row.get("domain", ""),
            "days": row.get("_days", ""),
            "text": row.get("text", ""),
            "action": row.get("action", ""),
        }
        for row in payload["events"]
    ]
    lines.extend(render_table(event_rows, [("date", "date"), ("domain", "domain"), ("days", "days"), ("text", "event"), ("action", "action")]))

    lines.extend(["", "## Known Limits", ""])
    for item in payload["known_limits"]:
        lines.append(f"- {item}")

    lines.extend(["", "## Next Step", ""])
    lines.append("- v1.1 之后最重要的升级不是换策略，而是把 V6 managed holdings 真正折算进 total-account 分母，并把主题映射表正式配置化。")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the firm-level Central Risk Board.")
    parser.add_argument("--tag", default=datetime.now().strftime("%Y%m%d_v1_1"))
    args = parser.parse_args()

    payload = build_payload()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUT_DIR / f"central_risk_board_{args.tag}.json"
    md_path = OUT_DIR / f"central_risk_board_{args.tag}.md"
    latest_json = OUT_DIR / "latest.json"
    latest_md = OUT_DIR / "latest.md"

    safe_payload = sanitize(payload)
    json_path.write_text(json.dumps(safe_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(md_path, payload)
    latest_json.write_text(json.dumps(safe_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    latest_md.write_text(md_path.read_text(encoding="utf-8"), encoding="utf-8")

    print("== Central Risk Board ==")
    print(f"JSON:   {json_path}")
    print(f"Report: {md_path}")
    print(f"Status: {payload['status']}")


if __name__ == "__main__":
    main()
