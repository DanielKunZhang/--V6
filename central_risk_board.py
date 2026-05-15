#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import importlib
import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

from morning_brief import HTML_PORTFOLIO, collect_events, collect_portfolio_futu, collect_portfolio_html, collect_v6


ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "backtest_results" / "central_risk_board"
CONFIG_PATH = ROOT / "central_risk_board_config.json"
STRUCTURED_LEDGER_PATH = ROOT / "central_risk_master_ledger.json"
CASH_ALPHA_FUTU_SNAPSHOT = ROOT / "cash_alpha_v3_repo" / "backtest_results" / "futu_account_snapshot_latest.json"
ATTACK_PREVIEW_DIR = ROOT / "backtest_results" / "attack_engine_live_preview"
RADAR_SAMPLE_LOOP_PATH = ROOT / "backtest_results" / "radar_sample_loop" / "latest.json"

DEFAULT_CONFIG = {
    "board": {
        "event_window_days": 21,
        "manual_events": [
            {
                "date": "2026-05-26",
                "domain": "V6治理",
                "text": "balanced challenger cutover 决策补充检查",
                "action": "按 cutover SOP 检查执行质量、回撤、偏离、自动化稳定性；禁止临场跳步骤。",
            },
            {
                "date": "2026-06-01",
                "domain": "V6-B治理",
                "text": "V6-B 数据链路与 challenger 链路补充检查",
                "action": "按 6月1日_V6B_执行卡执行 universe audit、synthetic history、challenger、allocator。",
            },
        ],
    },
    "special_sleeves": {
        "V6 量化策略仓": "V6",
        "Radar": "Radar Overlay",
        "卫星实验": "Experimental",
        "富途现金": "Cash Buffer",
    },
    "position_themes": {
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
        "AMZN": "美国平台/云",
        "AVGO": "AI半导体",
        "GOOGL": "美国平台/AI",
        "BIL": "现金类防守",
        "GLD": "黄金防守",
    },
    "v6_themes": {
        "US.AMZN": "美国平台/云",
        "US.AVGO": "AI半导体",
        "US.GOOGL": "美国平台/AI",
        "US.NVDA": "AI半导体",
        "US.BIL": "现金类防守",
        "US.GLD": "黄金防守",
    },
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


def load_board_config() -> dict[str, Any]:
    if CONFIG_PATH.exists():
        try:
            raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                merged = json.loads(json.dumps(DEFAULT_CONFIG, ensure_ascii=False))
                if isinstance(raw.get("board"), dict):
                    merged["board"].update(raw["board"])
                for key in ("special_sleeves", "position_themes", "v6_themes"):
                    if isinstance(raw.get(key), dict):
                        merged[key].update(raw[key])
                return merged
        except Exception:
            pass
    return DEFAULT_CONFIG


def classify_sleeve(name: str, config: dict[str, Any]) -> str:
    return config["special_sleeves"].get(name, "Value Main Book")


def classify_theme(name: str, config: dict[str, Any]) -> str:
    return config["position_themes"].get(name, "其他/待映射")


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


def load_radar_sample_loop_summary() -> dict[str, Any]:
    if not RADAR_SAMPLE_LOOP_PATH.exists():
        return {"available": False, "sample_count": 0, "by_source": {}, "pending_forward_review": 0, "source": str(RADAR_SAMPLE_LOOP_PATH)}
    try:
        payload = json.loads(RADAR_SAMPLE_LOOP_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"available": False, "sample_count": 0, "by_source": {}, "pending_forward_review": 0, "source": str(RADAR_SAMPLE_LOOP_PATH)}
    rows = payload.get("rows", []) if isinstance(payload.get("rows"), list) else []
    by_source: dict[str, int] = {}
    pending = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        source = str(row.get("source_channel") or "unknown")
        by_source[source] = by_source.get(source, 0) + 1
        if str(row.get("review_verdict") or "").startswith("PENDING"):
            pending += 1
    return {
        "available": True,
        "sample_count": int(payload.get("sample_count") or len(rows)),
        "by_source": by_source,
        "pending_forward_review": pending,
        "source": str(RADAR_SAMPLE_LOOP_PATH),
    }


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


def parse_wan_usd(text: str) -> float | None:
    match = re.search(r"([\d.]+)\s*万\s*USD", text)
    if not match:
        return None
    return round(float(match.group(1)) * 10000, 2)


def extract_portfolio_meta() -> dict[str, Any]:
    if not HTML_PORTFOLIO.exists():
        return {"total_assets_usd": None, "futu_executable_assets_usd": None, "source": str(HTML_PORTFOLIO), "notes": ["portfolio_html_missing"]}
    content = HTML_PORTFOLIO.read_text(encoding="utf-8")
    notes: list[str] = []

    total_assets_usd = None
    total_patterns = [
        r"合计总资产约\s*<strong>([\d.]+\s*万\s*USD)</strong>",
        r"全资产约\s*<strong>([\d.]+\s*万\s*USD)</strong>",
        r"全资产：约\s*([\d.]+\s*万\s*USD)",
    ]
    for pattern in total_patterns:
        match = re.search(pattern, content)
        if match:
            total_assets_usd = parse_wan_usd(match.group(1))
            break
    if total_assets_usd is None:
        notes.append("total_assets_usd_not_found")

    futu_assets_usd = None
    futu_patterns = [
        r"当前富途账户约\s*<strong>([\d.]+\s*万\s*USD)</strong>",
        r"富途账户约\s*<strong>([\d.]+\s*万\s*USD)</strong>",
        r"富途这\s*([\d.]+\s*万\s*USD)",
    ]
    for pattern in futu_patterns:
        match = re.search(pattern, content)
        if match:
            futu_assets_usd = parse_wan_usd(match.group(1))
            break
    if futu_assets_usd is None:
        notes.append("futu_executable_assets_usd_not_found")

    return {
        "total_assets_usd": total_assets_usd,
        "futu_executable_assets_usd": futu_assets_usd,
        "source": str(HTML_PORTFOLIO),
        "source_type": "html_fallback",
        "notes": notes,
    }


def position_status(row: dict[str, Any]) -> str:
    current_pct = float(row.get("current_pct") or 0.0)
    target_min = row.get("target_min")
    target_max = row.get("target_max")
    status = str(row.get("status") or "")
    if status:
        return status
    if target_max is not None and current_pct > float(target_max) + 0.5:
        return "over"
    if target_min is not None and float(target_min) > 2 and current_pct < float(target_min) - 1:
        return "under"
    return "ok"


def normalize_structured_position(row: dict[str, Any]) -> dict[str, Any]:
    clean = {
        "name": str(row.get("name") or "").strip(),
        "current_pct": round(float(row.get("current_pct") or 0.0), 1),
        "target_min": row.get("target_min"),
        "target_max": row.get("target_max"),
        "target_short": str(row.get("target_short") or "—"),
        "action": str(row.get("action") or ""),
    }
    if clean["target_min"] is not None:
        clean["target_min"] = float(clean["target_min"])
    if clean["target_max"] is not None:
        clean["target_max"] = float(clean["target_max"])
    if row.get("sleeve"):
        clean["sleeve"] = str(row["sleeve"])
    if row.get("theme"):
        clean["theme"] = str(row["theme"])
    clean["status"] = position_status({**row, **clean})
    return clean


def compare_ledgers(structured_positions: list[dict[str, Any]], html_positions: list[dict[str, Any]]) -> dict[str, Any]:
    structured = {row["name"]: row for row in structured_positions}
    html_rows = {row["name"]: row for row in html_positions}
    missing_in_structured = sorted(set(html_rows) - set(structured))
    missing_in_html = sorted(set(structured) - set(html_rows))
    pct_diffs = []
    for name in sorted(set(structured) & set(html_rows)):
        diff = round(float(structured[name].get("current_pct") or 0.0) - float(html_rows[name].get("current_pct") or 0.0), 2)
        if abs(diff) >= 0.2:
            pct_diffs.append(
                {
                    "name": name,
                    "structured_pct": structured[name].get("current_pct"),
                    "html_pct": html_rows[name].get("current_pct"),
                    "diff": diff,
                }
            )
    return {
        "html_source": str(HTML_PORTFOLIO),
        "html_last_updated": "",
        "missing_in_structured": missing_in_structured,
        "missing_in_html": missing_in_html,
        "pct_diffs": pct_diffs,
        "status": "OK" if not missing_in_structured and not missing_in_html and not pct_diffs else "CHECK",
    }


def load_structured_master_ledger() -> dict[str, Any]:
    if not STRUCTURED_LEDGER_PATH.exists():
        return {}
    try:
        raw = json.loads(STRUCTURED_LEDGER_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"error": f"structured_ledger_parse_error={exc}"}
    if not isinstance(raw, dict):
        return {"error": "structured_ledger_not_object"}
    positions_raw = raw.get("positions", [])
    if not isinstance(positions_raw, list):
        return {"error": "structured_ledger_positions_not_list"}
    positions = [normalize_structured_position(row) for row in positions_raw if isinstance(row, dict) and str(row.get("name") or "").strip()]
    return {
        "last_updated": str(raw.get("updated_at") or ""),
        "positions": positions,
        "alerts": [row for row in positions if row["status"] == "over"],
        "ledger_id": str(raw.get("ledger_id") or ""),
        "version": str(raw.get("version") or ""),
        "raw": raw,
    }


def load_master_ledger() -> dict[str, Any]:
    structured = load_structured_master_ledger()
    html_portfolio = collect_portfolio_html()
    if structured and not structured.get("error"):
        raw = structured.get("raw", {})
        meta = {
            "total_assets_usd": float(raw.get("total_assets_usd")) if raw.get("total_assets_usd") is not None else None,
            "futu_executable_assets_usd": float(raw.get("futu_executable_assets_usd")) if raw.get("futu_executable_assets_usd") is not None else None,
            "source": str(STRUCTURED_LEDGER_PATH),
            "source_type": "structured_json",
            "notes": [],
        }
        reconciliation = compare_ledgers(structured["positions"], html_portfolio.get("positions", []) if not html_portfolio.get("error") else [])
        reconciliation["html_last_updated"] = html_portfolio.get("last_updated", "")
        return {
            "portfolio": {
                "last_updated": structured.get("last_updated", ""),
                "positions": structured["positions"],
                "alerts": structured["alerts"],
                "error": "",
                "ledger_id": structured.get("ledger_id", ""),
                "ledger_version": structured.get("version", ""),
            },
            "meta": meta,
            "reconciliation": reconciliation,
        }

    html_meta = extract_portfolio_meta()
    if structured.get("error"):
        html_meta.setdefault("notes", []).append(structured["error"])
    return {
        "portfolio": html_portfolio,
        "meta": html_meta,
        "reconciliation": {"status": "FALLBACK", "html_source": str(HTML_PORTFOLIO), "html_last_updated": html_portfolio.get("last_updated", "")},
    }


def build_futu_snapshot() -> dict[str, Any]:
    live = collect_portfolio_futu()
    if live:
        positions = live.get("positions", {})
        positions_map: dict[str, dict[str, Any]] = {}
        long_mv_hkd = 0.0
        long_mv_usd = 0.0
        for code, item in positions.items():
            qty = float(item.get("qty", 0.0))
            mv_local = float(item.get("mv_local", 0.0))
            mv_usd = mv_local if code.startswith("US.") else None
            long_mv_hkd += mv_local
            if mv_usd:
                long_mv_usd += mv_usd
            positions_map[code] = {
                "qty": qty,
                "market_val_local": mv_local,
                "market_val_usd": mv_usd,
                "stock_name": item.get("stock_name", ""),
            }
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
            "positions_count": len([item for item in positions.values() if float(item.get("qty", 0.0)) > 0]),
            "long_positions_market_value_usd": round(long_mv_usd, 2) if long_mv_usd > 0 else None,
            "long_positions_market_value_hkd": round(long_mv_hkd, 2),
            "reserve_sellable_usd": None,
            "positions_map": positions_map,
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
            "positions_map": {},
            "warnings": ["futu_snapshot_unavailable"],
        }

    positions_map: dict[str, dict[str, Any]] = {}
    for row in raw.get("positions", []) or []:
        code = str(row.get("code", ""))
        if not code:
            continue
        positions_map[code] = {
            "qty": float(row.get("qty", 0.0) or 0.0),
            "market_val_usd": float(row.get("market_val_usd", 0.0) or 0.0),
            "market_val_local": float(row.get("market_val", 0.0) or 0.0),
            "stock_name": row.get("stock_name", ""),
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
        "positions_map": positions_map,
        "warnings": raw.get("snapshot_warnings", []),
    }


def resolve_cadence(requested: str) -> str:
    if requested in {"daily", "weekly"}:
        return requested
    return "weekly" if datetime.now().weekday() == 0 else "daily"


def cadence_label(cadence: str) -> str:
    return "Weekly Formal Board" if cadence == "weekly" else "Daily Light Check"


def position_sleeve(row: dict[str, Any], config: dict[str, Any]) -> str:
    return str(row.get("sleeve") or classify_sleeve(row["name"], config))


def position_theme(row: dict[str, Any], config: dict[str, Any]) -> str:
    return str(row.get("theme") or classify_theme(row["name"], config))


def build_v6_allocated_positions(
    base_positions: list[dict[str, Any]],
    v6_positions: dict[str, float],
    futu_snapshot: dict[str, Any],
    portfolio_meta: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    total_assets_usd = portfolio_meta.get("total_assets_usd")
    existing_names = {row["name"] for row in base_positions}
    position_map = futu_snapshot.get("positions_map", {}) or {}
    out: list[dict[str, Any]] = []
    warnings: list[str] = []

    if not total_assets_usd:
        return {"positions": [], "current_pct": 0.0, "warnings": ["total_assets_denominator_missing"]}

    for code, qty in v6_positions.items():
        if float(qty) <= 0:
            continue
        plain = normalize_v6_name(code)
        if plain in existing_names:
            warnings.append(f"skip_existing_{plain}")
            continue
        snap = position_map.get(code, {})
        mv_usd = snap.get("market_val_usd")
        if mv_usd is None or float(mv_usd) <= 0:
            warnings.append(f"missing_market_value_{code}")
            continue
        pct = round(float(mv_usd) / float(total_assets_usd) * 100, 1)
        if pct <= 0:
            continue
        out.append(
            {
                "name": plain,
                "current_pct": pct,
                "target_min": None,
                "target_max": None,
                "target_short": "V6 managed",
                "action": "由 V6 managed state 管理",
                "status": "ok",
                "sleeve": "V6",
                "theme": config["v6_themes"].get(code, "V6未映射主题"),
                "synthetic": True,
                "source": "futu_v6_managed_state",
                "market_val_usd": round(float(mv_usd), 2),
                "qty": float(qty),
                "code": code,
            }
        )

    return {
        "positions": out,
        "current_pct": round(sum(row["current_pct"] for row in out), 1),
        "warnings": warnings,
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


def build_sleeve_rows(positions: list[dict[str, Any]], config: dict[str, Any]) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    for row in positions:
        sleeve = position_sleeve(row, config)
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
        row["names"] = " / ".join(row["names"][:8]) if row["names"] else "—"
        rows.append(row)
    return rows


def build_theme_rows(positions: list[dict[str, Any]], config: dict[str, Any]) -> list[dict[str, Any]]:
    theme_totals: dict[str, float] = {}
    for row in positions:
        pct = float(row["current_pct"])
        if pct <= 0:
            continue
        theme = position_theme(row, config)
        theme_totals[theme] = theme_totals.get(theme, 0.0) + pct

    rows = [{"theme": theme, "current_pct": round(weight, 1)} for theme, weight in theme_totals.items() if weight > 0]
    rows.sort(key=lambda item: item["current_pct"], reverse=True)
    return rows


def build_mapping_quality(positions: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    unmapped = []
    for row in positions:
        if float(row["current_pct"]) <= 0:
            continue
        theme = position_theme(row, config)
        if theme in {"其他/待映射", "V6未映射主题"}:
            unmapped.append({"name": row["name"], "current_pct": row["current_pct"], "theme": theme})
    unmapped.sort(key=lambda item: item["current_pct"], reverse=True)
    return {
        "unmapped_count": len(unmapped),
        "unmapped_weight": round(sum(float(item["current_pct"]) for item in unmapped), 1),
        "unmapped_positions": unmapped,
    }


def build_ledger_quality(
    portfolio: dict[str, Any],
    portfolio_meta: dict[str, Any],
    positions: list[dict[str, Any]],
    reconciliation: dict[str, Any],
) -> dict[str, Any]:
    issues: list[str] = []
    if portfolio.get("error"):
        issues.append(f"portfolio_parse_error={portfolio['error']}")
    if not portfolio.get("last_updated") or portfolio.get("last_updated") == "未知":
        issues.append("portfolio_last_updated_missing")
    if portfolio_meta.get("total_assets_usd") is None:
        issues.append("total_assets_usd_missing")
    if portfolio_meta.get("futu_executable_assets_usd") is None:
        issues.append("futu_executable_assets_usd_missing")
    if portfolio_meta.get("notes"):
        issues.extend(str(item) for item in portfolio_meta["notes"])
    if not positions:
        issues.append("portfolio_positions_missing")
    pct_sum = round(sum(float(row.get("current_pct") or 0.0) for row in positions), 1)
    if pct_sum < 95.0 or pct_sum > 105.0:
        issues.append(f"position_pct_sum_out_of_range={pct_sum:.1f}%")
    if reconciliation.get("status") == "CHECK":
        issues.append("structured_vs_html_reconciliation_check")
    return {
        "status": "OK" if not issues else "CHECK",
        "issues": issues,
        "position_count": len(positions),
        "position_pct_sum": pct_sum,
        "source": portfolio_meta.get("source", str(HTML_PORTFOLIO)),
        "source_type": portfolio_meta.get("source_type", "unknown"),
        "reconciliation": reconciliation,
    }


def normalize_event(item: dict[str, Any], source: str) -> dict[str, Any] | None:
    try:
        d = date.fromisoformat(str(item["date"]))
    except (KeyError, ValueError):
        return None
    row = dict(item)
    row["_date_obj"] = d
    row["_days"] = (d - date.today()).days
    row["source"] = source
    return row


def build_event_rows(config: dict[str, Any]) -> list[dict[str, Any]]:
    days = int(config.get("board", {}).get("event_window_days") or 21)
    today = date.today()
    cutoff = today + date.resolution * days
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    for row in collect_events(days):
        key = (str(row.get("date", "")), str(row.get("domain", "")), str(row.get("text", "")))
        seen.add(key)
        rows.append({**row, "source": "events_calendar"})

    for item in config.get("board", {}).get("manual_events", []):
        if not isinstance(item, dict):
            continue
        row = normalize_event(item, "central_risk_board_config")
        if not row:
            continue
        if not (today <= row["_date_obj"] <= cutoff):
            continue
        key = (str(row.get("date", "")), str(row.get("domain", "")), str(row.get("text", "")))
        if key in seen:
            continue
        rows.append(row)
        seen.add(key)

    rows.sort(key=lambda item: item["_date_obj"])
    return rows


def build_overlap_section(base_positions: list[dict[str, Any]], v6_positions: dict[str, float], config: dict[str, Any]) -> dict[str, Any]:
    main_names = {row["name"] for row in base_positions if position_sleeve(row, config) == "Value Main Book" and row["current_pct"] > 0}
    v6_plain = {normalize_v6_name(code) for code, qty in v6_positions.items() if qty > 0}
    direct_overlap = sorted(main_names & v6_plain)

    main_themes = {position_theme(row, config) for row in base_positions if position_sleeve(row, config) == "Value Main Book" and row["current_pct"] > 0}
    v6_themes = {config["v6_themes"].get(code, "V6未映射主题") for code, qty in v6_positions.items() if qty > 0}
    thematic_overlap = sorted(main_themes & v6_themes)

    return {"direct_overlap": direct_overlap, "thematic_overlap": thematic_overlap}


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
    rows.append({"item": "Master risk ledger", "updated_at": portfolio_last_updated or "unknown", "age": fmt_age_days(ledger_age_days), "status": ledger_status, "note": "26年阶段性组合策略计划.html"})

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
    rows.append({"item": "V6 managed state", "updated_at": v6_state_updated or "unknown", "age": fmt_age_hours(v6_age_hours), "status": v6_status, "note": "managed positions / blockers"})

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
    rows.append({"item": "Futu broker snapshot", "updated_at": futu_snapshot.get("timestamp", "unknown") or "unknown", "age": fmt_age_hours(futu_age_hours), "status": futu_status, "note": futu_snapshot.get("mode", "unknown")})

    return {"rows": rows, "red_reasons": red_reasons, "yellow_reasons": yellow_reasons}


def classify_board_status(
    snapshot: dict[str, Any],
    themes: list[dict[str, Any]],
    alerts: list[dict[str, Any]],
    freshness: dict[str, Any],
    ledger_quality: dict[str, Any],
    mapping_quality: dict[str, Any],
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    top_theme = themes[0]["current_pct"] if themes else 0.0
    if snapshot["max_position"] >= 25.0:
        reasons.append(f"single_position>{snapshot['max_position']:.1f}%")
    if snapshot["top2_sum"] >= 50.0:
        reasons.append(f"top2_sum={snapshot['top2_sum']:.1f}%")
    if top_theme >= 45.0:
        reasons.append(f"top_theme={top_theme:.1f}%")
    if ledger_quality.get("status") != "OK":
        reasons.append("ledger_quality_check")
    if float(mapping_quality.get("unmapped_weight") or 0.0) >= 5.0:
        reasons.append(f"unmapped_theme_weight={mapping_quality['unmapped_weight']:.1f}%")
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
    if mapping_quality.get("unmapped_count"):
        yellow.append(f"unmapped_theme_count={mapping_quality['unmapped_count']}")
    yellow.extend(freshness.get("yellow_reasons", []))
    if yellow:
        return "YELLOW", yellow
    return "GREEN", []


def build_expansion_gate(status: str, radar_sample_loop: dict[str, Any], v6: dict[str, Any]) -> dict[str, Any]:
    blockers: list[str] = []
    if status == "RED":
        blockers.append("central_risk_red_no_expansion")
    if int(radar_sample_loop.get("pending_forward_review") or 0) > 0:
        blockers.append("radar_forward_review_pending")
    if str(v6.get("signal") or "").upper() == "BLOCKED":
        blockers.append("v6_operational_signal_blocked")

    return {
        "status": "BLOCK_EXPANSION" if blockers else "ALLOW_NEXT_REVIEW",
        "blockers": blockers,
        "allowed_actions": [
            "允许研究、复盘、生成 preview；禁止扩容和未确认自动交易"
            if blockers
            else "允许继续小额试运行或按 SOP 进入下一阶段"
        ],
        "rules": [
            "Central Risk Board 为总闸门；当总账户 RED 时，V6 / Radar / Overlay 只能做小额 pilot、研究和复盘，不能扩容。",
            "Radar 样本必须先进入闭环表，跑出 5/10/20/60 日真实表现后，才允许讨论预算。",
            "V6-A balanced cutover 即使技术通过，也只能在 2026-05-26 SOP 输出 GO 后再进入受控切换。",
        ],
    }


def render_table(rows: list[dict[str, Any]], columns: list[tuple[str, str]]) -> list[str]:
    if not rows:
        return ["_None_"]
    out = ["| " + " | ".join(label for _, label in columns) + " |", "| " + " | ".join("---" for _ in columns) + " |"]
    for row in rows:
        out.append("| " + " | ".join(str(row.get(key, "")) for key, _ in columns) + " |")
    return out


def render_html_table(rows: list[dict[str, Any]], columns: list[tuple[str, str]]) -> str:
    if not rows:
        return "<p>None</p>"
    head = "".join(f"<th>{html.escape(label)}</th>" for _, label in columns)
    body_rows = []
    for row in rows:
        tds = "".join(f"<td>{html.escape(str(row.get(key, '')))}</td>" for key, _ in columns)
        body_rows.append(f"<tr>{tds}</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body_rows)}</tbody></table>"


def build_payload(requested_cadence: str) -> dict[str, Any]:
    config = load_board_config()
    cadence = resolve_cadence(requested_cadence)
    master_ledger = load_master_ledger()
    portfolio = master_ledger["portfolio"]
    v6 = collect_v6()
    generated_at = datetime.now().isoformat(timespec="seconds")
    portfolio_meta = master_ledger["meta"]
    ledger_reconciliation = master_ledger["reconciliation"]
    base_positions = portfolio.get("positions", [])
    alerts = portfolio.get("alerts", [])
    futu_snapshot = build_futu_snapshot()
    v6_allocated = build_v6_allocated_positions(base_positions, v6.get("positions", {}), futu_snapshot, portfolio_meta, config)
    positions = [*base_positions, *v6_allocated["positions"]]
    snapshot = build_firm_snapshot(positions)
    sleeves = build_sleeve_rows(positions, config)
    themes = build_theme_rows(positions, config)
    overlap = build_overlap_section(base_positions, v6.get("positions", {}), config)
    freshness = build_freshness(generated_at, portfolio.get("last_updated", ""), v6.get("state_updated", ""), futu_snapshot)
    ledger_quality = build_ledger_quality(portfolio, portfolio_meta, base_positions, ledger_reconciliation)
    mapping_quality = build_mapping_quality(positions, config)
    radar_sample_loop = load_radar_sample_loop_summary()
    events = build_event_rows(config)
    status, reasons = classify_board_status(snapshot, themes, alerts, freshness, ledger_quality, mapping_quality)
    expansion_gate = build_expansion_gate(status, radar_sample_loop, v6)
    return {
        "version": "v1.5",
        "requested_cadence": requested_cadence,
        "cadence": cadence,
        "cadence_label": cadence_label(cadence),
        "generated_at": generated_at,
        "portfolio_last_updated": portfolio.get("last_updated", ""),
        "portfolio_error": portfolio.get("error", ""),
        "portfolio_meta": portfolio_meta,
        "ledger_reconciliation": ledger_reconciliation,
        "status": status,
        "status_reasons": reasons,
        "firm_snapshot": snapshot,
        "sleeves": sleeves,
        "themes": themes[:10],
        "ledger_quality": ledger_quality,
        "mapping_quality": mapping_quality,
        "radar_sample_loop": radar_sample_loop,
        "expansion_gate": expansion_gate,
        "freshness": freshness,
        "futu_snapshot": futu_snapshot,
        "target_alerts": alerts,
        "v6": {
            "signal": v6.get("signal", "UNKNOWN"),
            "blockers": v6.get("blockers", []),
            "managed_positions": v6.get("positions", {}),
            "state_updated": v6.get("state_updated", ""),
        },
        "v6_allocated": v6_allocated,
        "overlap": overlap,
        "events": events,
        "event_window_days": int(config.get("board", {}).get("event_window_days") or 21),
        "known_limits": [
            "total-account 主账本已优先读取 central_risk_master_ledger.json；若结构化账本缺失或损坏，才回退到 26年阶段性组合策略计划.html。",
            "结构化主账本当前仍需要人工更新，但已经可被机器校验、版本化、与 HTML 交叉核对。",
            "V6 曝露目前只对 master ledger 缺失的 managed names 做增量折算，避免与已入账主仓名称双重计算。",
            "Futu snapshot 仍然主要承担 broker-level sanity / freshness，不是完整全资产分母来源。",
            "theme mapping 已配置化并有未映射报警，但映射质量仍取决于后续持续补表。",
            "Radar / V6-B 必须先经过样本闭环表和 Central Risk Board，不能从“发现强势标的”直接跳到“扩大交易”。",
        ],
    }


def build_top_rows(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"name": row["name"], "current_pct": fmt_pct(row["current_pct"]), "target": row["target_short"], "action": row["action"]} for row in snapshot["top5"]]


def build_sleeve_display_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "sleeve": row["sleeve"],
            "current_pct": fmt_pct(row["current_pct"]),
            "over_count": row["over_count"],
            "under_count": row["under_count"],
            "names": row["names"],
        }
        for row in payload["sleeves"]
    ]


def build_theme_display_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"theme": row["theme"], "current_pct": fmt_pct(row["current_pct"])} for row in payload["themes"]]


def build_alert_display_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"name": row["name"], "current_pct": fmt_pct(row["current_pct"]), "target": row["target_short"], "action": row["action"]} for row in payload["target_alerts"]]


def build_event_display_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"date": row["date"], "domain": row.get("domain", ""), "days": row.get("_days", ""), "text": row.get("text", ""), "action": row.get("action", ""), "source": row.get("source", "")} for row in payload["events"]]


def build_v6_embedded_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "code": row.get("code", ""),
            "name": row["name"],
            "qty": int(row.get("qty", 0)),
            "market_val_usd": fmt_usd(row.get("market_val_usd")),
            "current_pct": fmt_pct(row["current_pct"]),
            "theme": row.get("theme", ""),
        }
        for row in payload["v6_allocated"]["positions"]
    ]


def build_mapping_display_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"name": row["name"], "current_pct": fmt_pct(row["current_pct"]), "theme": row["theme"]}
        for row in payload["mapping_quality"]["unmapped_positions"]
    ]


def one_line_read(payload: dict[str, Any]) -> str:
    if payload["status"] == "RED":
        return "当前不是“策略坏了”，而是总账户集中度仍然过高，核心风险继续集中在少数大仓与单一主题。"
    if payload["status"] == "YELLOW":
        return "当前总账户可运行，但集中度和目标偏离已经需要正式讨论，不能只靠感觉管理。"
    return "当前总账户风险大体在可接受范围内，中央风险层未发现明显失真。"


def write_markdown(path: Path, payload: dict[str, Any]) -> None:
    snapshot = payload["firm_snapshot"]
    portfolio_meta = payload["portfolio_meta"]
    lines = [
        f"# Central Risk Board {payload['version']}",
        "",
        f"- Cadence: `{payload['cadence']}` ({payload['cadence_label']})",
        f"- Generated: `{payload['generated_at']}`",
        f"- Master risk ledger date: `{payload['portfolio_last_updated']}`",
        f"- Overall status: `{payload['status']}`",
        f"- Status reasons: `{', '.join(payload['status_reasons']) or 'none'}`",
        "",
        "## One-Line Read",
        "",
        f"- {one_line_read(payload)}",
        "",
        "## Capital Base",
        "",
        f"- Total account denominator: `{fmt_usd(portfolio_meta.get('total_assets_usd'))}`",
        f"- Futu executable capital base: `{fmt_usd(portfolio_meta.get('futu_executable_assets_usd'))}`",
        f"- V6 embedded exposure added into denominator: `{fmt_pct(payload['v6_allocated']['current_pct'])}`",
        f"- Master ledger source type: `{payload['ledger_quality'].get('source_type', 'unknown')}`",
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
    lines.extend(render_table(build_top_rows(snapshot), [("name", "position"), ("current_pct", "current"), ("target", "target"), ("action", "action")]))

    lines.extend(["", "## Sleeve Risk", ""])
    lines.extend(render_table(build_sleeve_display_rows(payload), [("sleeve", "sleeve"), ("current_pct", "current"), ("over_count", "over-target"), ("under_count", "under-target"), ("names", "main names")]))

    lines.extend(["", "## Theme Concentration", ""])
    lines.extend(render_table(build_theme_display_rows(payload), [("theme", "theme"), ("current_pct", "current")]))

    if payload["v6_allocated"]["positions"]:
        lines.extend(["", "## V6 Embedded Exposure", ""])
        lines.extend(render_table(build_v6_embedded_rows(payload), [("code", "code"), ("name", "name"), ("qty", "qty"), ("market_val_usd", "market_value"), ("current_pct", "total_account_pct"), ("theme", "theme")]))

    lines.extend(["", "## Data Freshness", ""])
    lines.extend(render_table(payload["freshness"]["rows"], [("item", "item"), ("updated_at", "updated_at"), ("age", "age"), ("status", "status"), ("note", "note")]))

    lines.extend(["", "## Master Ledger Quality", ""])
    lines.append(f"- Status: `{payload['ledger_quality']['status']}`")
    lines.append(f"- Source: `{payload['ledger_quality']['source']}`")
    lines.append(f"- Source type: `{payload['ledger_quality'].get('source_type', 'unknown')}`")
    lines.append(f"- Parsed positions: `{payload['ledger_quality']['position_count']}`")
    lines.append(f"- Position pct sum: `{fmt_pct(payload['ledger_quality'].get('position_pct_sum', 0.0))}`")
    lines.append(f"- Issues: `{', '.join(payload['ledger_quality']['issues']) if payload['ledger_quality']['issues'] else 'none'}`")
    reconciliation = payload["ledger_quality"].get("reconciliation", {})
    lines.append(f"- HTML reconciliation status: `{reconciliation.get('status', 'unknown')}`")
    if reconciliation.get("missing_in_structured") or reconciliation.get("missing_in_html") or reconciliation.get("pct_diffs"):
        lines.append(f"- Missing in structured: `{', '.join(reconciliation.get('missing_in_structured', [])) or 'none'}`")
        lines.append(f"- Missing in HTML: `{', '.join(reconciliation.get('missing_in_html', [])) or 'none'}`")
        lines.append(f"- Pct diffs: `{reconciliation.get('pct_diffs', [])}`")

    lines.extend(["", "## Theme Mapping Quality", ""])
    lines.append(f"- Unmapped positions: `{payload['mapping_quality']['unmapped_count']}`")
    lines.append(f"- Unmapped weight: `{fmt_pct(payload['mapping_quality']['unmapped_weight'])}`")
    lines.extend(render_table(build_mapping_display_rows(payload), [("name", "name"), ("current_pct", "current"), ("theme", "theme")]))

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

    lines.extend(["", "## Expansion Gate", ""])
    gate = payload["expansion_gate"]
    radar_loop = payload["radar_sample_loop"]
    lines.append(f"- Status: `{gate['status']}`")
    lines.append(f"- Blockers: `{', '.join(gate['blockers']) if gate['blockers'] else 'none'}`")
    lines.append(f"- Allowed actions: `{'; '.join(gate['allowed_actions'])}`")
    lines.append(f"- Radar sample loop: `{radar_loop.get('sample_count', 0)}` samples, `{radar_loop.get('pending_forward_review', 0)}` pending forward review")
    by_source = radar_loop.get("by_source", {}) or {}
    if by_source:
        lines.append(f"- Sample source mix: `{', '.join(f'{k}={v}' for k, v in by_source.items())}`")
    for rule in gate["rules"]:
        lines.append(f"- {rule}")

    lines.extend(["", "## Target Drift Alerts", ""])
    lines.extend(render_table(build_alert_display_rows(payload), [("name", "name"), ("current_pct", "current"), ("target", "target"), ("action", "action")]))

    lines.extend(["", f"## Event Window ({payload['event_window_days']}d)", ""])
    lines.extend(render_table(build_event_display_rows(payload), [("date", "date"), ("domain", "domain"), ("days", "days"), ("text", "event"), ("action", "action"), ("source", "source")]))

    lines.extend(["", "## Known Limits", ""])
    for item in payload["known_limits"]:
        lines.append(f"- {item}")

    lines.extend(["", "## Next Step", ""])
    lines.append("- 现在最重要的升级不是换策略，而是继续提高 total-account 主账本的自动化程度，并让主题映射和 sleeve attribution 进入稳定维护。")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_html(payload: dict[str, Any]) -> str:
    snapshot = payload["firm_snapshot"]
    top_rows = build_top_rows(snapshot)
    sleeve_rows = build_sleeve_display_rows(payload)
    theme_rows = build_theme_display_rows(payload)
    v6_rows = build_v6_embedded_rows(payload)
    freshness_rows = payload["freshness"]["rows"]
    alert_rows = build_alert_display_rows(payload)
    event_rows = build_event_display_rows(payload)
    mapping_rows = build_mapping_display_rows(payload)
    portfolio_meta = payload["portfolio_meta"]
    status_color = {"GREEN": "#16a34a", "YELLOW": "#d97706", "RED": "#dc2626"}.get(payload["status"], "#2563eb")

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Central Risk Board {payload['cadence_label']}</title>
  <style>
    body {{
      margin: 0;
      padding: 24px;
      background: #f5f7fb;
      color: #0f172a;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", sans-serif;
      line-height: 1.55;
    }}
    .wrap {{
      max-width: 1120px;
      margin: 0 auto;
    }}
    .hero {{
      background: linear-gradient(135deg, #0f172a, #1e293b);
      color: white;
      border-radius: 22px;
      padding: 24px 28px;
      box-shadow: 0 18px 50px rgba(15, 23, 42, 0.18);
    }}
    .chips {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 14px;
    }}
    .chip {{
      border-radius: 999px;
      padding: 6px 12px;
      font-size: 12px;
      font-weight: 700;
      background: rgba(255,255,255,0.12);
      border: 1px solid rgba(255,255,255,0.12);
    }}
    .status {{
      background: {status_color};
      color: white;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
      margin-top: 18px;
    }}
    .card {{
      background: white;
      border-radius: 18px;
      padding: 18px;
      box-shadow: 0 10px 28px rgba(15, 23, 42, 0.08);
    }}
    .kicker {{
      color: #64748b;
      font-size: 12px;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: .04em;
    }}
    .num {{
      margin-top: 8px;
      font-size: 28px;
      font-weight: 800;
    }}
    h2 {{
      margin: 26px 0 12px;
      font-size: 20px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      background: white;
      border-radius: 16px;
      overflow: hidden;
      box-shadow: 0 8px 24px rgba(15, 23, 42, 0.06);
    }}
    th, td {{
      padding: 11px 12px;
      border-bottom: 1px solid #e2e8f0;
      text-align: left;
      vertical-align: top;
      font-size: 13px;
    }}
    th {{
      background: #e2e8f0;
      color: #334155;
      font-size: 12px;
      font-weight: 800;
    }}
    .note {{
      margin-top: 12px;
      color: #475569;
      font-size: 13px;
    }}
    ul {{
      margin: 10px 0 0;
      padding-left: 18px;
    }}
    @media (max-width: 900px) {{
      .grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="hero">
      <div style="font-size:12px;font-weight:800;opacity:.85;">Central Risk Board {payload['version']}</div>
      <h1 style="margin:10px 0 8px;font-size:32px;">{html.escape(payload['cadence_label'])}</h1>
      <div>{html.escape(one_line_read(payload))}</div>
      <div class="chips">
        <div class="chip status">{html.escape(payload['status'])}</div>
        <div class="chip">Generated {html.escape(payload['generated_at'])}</div>
        <div class="chip">Ledger {html.escape(payload['portfolio_last_updated'])}</div>
        <div class="chip">Top2 {html.escape(fmt_pct(snapshot['top2_sum']))}</div>
        <div class="chip">Largest {html.escape(fmt_pct(snapshot['max_position']))}</div>
        <div class="chip">V6 Embedded {html.escape(fmt_pct(payload['v6_allocated']['current_pct']))}</div>
      </div>
    </div>

    <div class="grid">
      <div class="card"><div class="kicker">Total Denominator</div><div class="num">{html.escape(fmt_usd(portfolio_meta.get('total_assets_usd')))}</div></div>
      <div class="card"><div class="kicker">Futu Executable Base</div><div class="num">{html.escape(fmt_usd(portfolio_meta.get('futu_executable_assets_usd')))}</div></div>
      <div class="card"><div class="kicker">Top Theme</div><div class="num">{html.escape(theme_rows[0]['theme'] if theme_rows else '—')}</div></div>
      <div class="card"><div class="kicker">Top Theme Weight</div><div class="num">{html.escape(theme_rows[0]['current_pct'] if theme_rows else '—')}</div></div>
    </div>

    <h2>Top Positions</h2>
    {render_html_table(top_rows, [('name', 'position'), ('current_pct', 'current'), ('target', 'target'), ('action', 'action')])}

    <h2>Sleeve Risk</h2>
    {render_html_table(sleeve_rows, [('sleeve', 'sleeve'), ('current_pct', 'current'), ('over_count', 'over-target'), ('under_count', 'under-target'), ('names', 'main names')])}

    <h2>Theme Concentration</h2>
    {render_html_table(theme_rows, [('theme', 'theme'), ('current_pct', 'current')])}

    {"<h2>V6 Embedded Exposure</h2>" + render_html_table(v6_rows, [('code', 'code'), ('name', 'name'), ('qty', 'qty'), ('market_val_usd', 'market_value'), ('current_pct', 'total_account_pct'), ('theme', 'theme')]) if v6_rows else ""}

    <h2>Data Freshness</h2>
    {render_html_table(freshness_rows, [('item', 'item'), ('updated_at', 'updated_at'), ('age', 'age'), ('status', 'status'), ('note', 'note')])}

    <h2>Master Ledger Quality</h2>
    <table>
      <thead><tr><th>item</th><th>value</th></tr></thead>
      <tbody>
        <tr><td>status</td><td>{html.escape(str(payload['ledger_quality']['status']))}</td></tr>
        <tr><td>source</td><td>{html.escape(str(payload['ledger_quality']['source']))}</td></tr>
        <tr><td>source type</td><td>{html.escape(str(payload['ledger_quality'].get('source_type', 'unknown')))}</td></tr>
        <tr><td>parsed positions</td><td>{html.escape(str(payload['ledger_quality']['position_count']))}</td></tr>
        <tr><td>position pct sum</td><td>{html.escape(fmt_pct(payload['ledger_quality'].get('position_pct_sum', 0.0)))}</td></tr>
        <tr><td>HTML reconciliation</td><td>{html.escape(str(payload['ledger_quality'].get('reconciliation', {}).get('status', 'unknown')))}</td></tr>
        <tr><td>issues</td><td>{html.escape(', '.join(payload['ledger_quality']['issues']) if payload['ledger_quality']['issues'] else 'none')}</td></tr>
      </tbody>
    </table>

    <h2>Theme Mapping Quality</h2>
    <div class="card">
      <ul>
        <li>Unmapped positions: {html.escape(str(payload['mapping_quality']['unmapped_count']))}</li>
        <li>Unmapped weight: {html.escape(fmt_pct(payload['mapping_quality']['unmapped_weight']))}</li>
      </ul>
    </div>
    {render_html_table(mapping_rows, [('name', 'name'), ('current_pct', 'current'), ('theme', 'theme')]) if mapping_rows else ""}

    <h2>Target Drift Alerts</h2>
    {render_html_table(alert_rows, [('name', 'name'), ('current_pct', 'current'), ('target', 'target'), ('action', 'action')])}

    <h2>Event Window</h2>
    {render_html_table(event_rows, [('date', 'date'), ('domain', 'domain'), ('days', 'days'), ('text', 'event'), ('action', 'action'), ('source', 'source')])}

    <h2>Overlap Risk</h2>
    <div class="card">
      <ul>
        <li>Direct main-book vs V6 overlap: {html.escape(', '.join(payload['overlap']['direct_overlap']) if payload['overlap']['direct_overlap'] else 'none')}</li>
        <li>Thematic overlap: {html.escape(', '.join(payload['overlap']['thematic_overlap']) if payload['overlap']['thematic_overlap'] else 'none')}</li>
        <li>V6 signal: {html.escape(payload['v6']['signal'])}</li>
        <li>V6 blockers: {html.escape(str(payload['v6']['blockers']))}</li>
      </ul>
    </div>

    <h2>Expansion Gate</h2>
    <div class="card">
      <ul>
        <li>Status: {html.escape(str(payload['expansion_gate']['status']))}</li>
        <li>Blockers: {html.escape(', '.join(payload['expansion_gate']['blockers']) if payload['expansion_gate']['blockers'] else 'none')}</li>
        <li>Allowed actions: {html.escape('; '.join(payload['expansion_gate']['allowed_actions']))}</li>
        <li>Radar sample loop: {html.escape(str(payload['radar_sample_loop'].get('sample_count', 0)))} samples, {html.escape(str(payload['radar_sample_loop'].get('pending_forward_review', 0)))} pending forward review</li>
        <li>Rules: {html.escape(' / '.join(payload['expansion_gate']['rules']))}</li>
      </ul>
    </div>

    <div class="note">
      自动化建议：daily 仅看异常，weekly 才做正式调整。当前邮件版已经支持两种 cadence，可挂到 launchd。
    </div>
  </div>
</body>
</html>
"""


def send_email(subject: str, html_content: str) -> bool:
    try:
        notifier = importlib.import_module("notifier").EmailNotifier()
        sent = bool(notifier.send(subject, html_content, is_html=True))
        if sent:
            print(f"✓ 邮件已发送 → {getattr(notifier, 'recipient', '?')}")
        else:
            print("⚠️ 邮件发送失败")
        return sent
    except Exception as exc:
        print(f"✗ notifier 不可用: {exc}")
        return False


def build_email_subject(payload: dict[str, Any]) -> str:
    cadence = "Weekly" if payload["cadence"] == "weekly" else "Daily"
    status = payload["status"]
    extra = f" · {len(payload['target_alerts'])} alerts" if payload["target_alerts"] else ""
    return f"🛡️ Central Risk Board {cadence} {date.today()} · {status}{extra}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the firm-level Central Risk Board.")
    parser.add_argument("--tag", default=datetime.now().strftime("%Y%m%dT%H%M%S"))
    parser.add_argument("--cadence", choices=["auto", "daily", "weekly"], default="weekly")
    parser.add_argument("--email", action="store_true")
    args = parser.parse_args()

    payload = build_payload(args.cadence)
    cadence = payload["cadence"]
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    base = OUT_DIR / f"central_risk_board_{cadence}_{args.tag}"
    json_path = Path(f"{base}.json")
    md_path = Path(f"{base}.md")
    html_path = Path(f"{base}.html")

    latest_json = OUT_DIR / "latest.json"
    latest_md = OUT_DIR / "latest.md"
    latest_html = OUT_DIR / "latest.html"
    cadence_latest_json = OUT_DIR / f"latest_{cadence}.json"
    cadence_latest_md = OUT_DIR / f"latest_{cadence}.md"
    cadence_latest_html = OUT_DIR / f"latest_{cadence}.html"

    safe_payload = sanitize(payload)
    html_content = build_html(payload)
    json_path.write_text(json.dumps(safe_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(md_path, payload)
    html_path.write_text(html_content, encoding="utf-8")

    latest_json.write_text(json.dumps(safe_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    latest_md.write_text(md_path.read_text(encoding="utf-8"), encoding="utf-8")
    latest_html.write_text(html_content, encoding="utf-8")

    cadence_latest_json.write_text(json.dumps(safe_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    cadence_latest_md.write_text(md_path.read_text(encoding="utf-8"), encoding="utf-8")
    cadence_latest_html.write_text(html_content, encoding="utf-8")

    print("== Central Risk Board ==")
    print(f"Cadence: {payload['cadence']} ({payload['cadence_label']})")
    print(f"JSON:    {json_path}")
    print(f"Report:  {md_path}")
    print(f"HTML:    {html_path}")
    print(f"Status:  {payload['status']}")
    print(f"V6 add:  {payload['v6_allocated']['current_pct']:.1f}% of total account")

    if args.email:
        send_email(build_email_subject(payload), html_content)


if __name__ == "__main__":
    main()
