#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parent
DESKTOP_ROOT = Path("/Users/zhangkun/Desktop/AI个人投资公司")
REPORT_ROOT = DESKTOP_ROOT / "报表输出" / "LATEST"
OUT_DIR = ROOT / "backtest_results" / "v6ab_daily_evolution"

DEFAULT_X_RADAR = ROOT / "research_snapshots" / "20260519" / "2026-05-19_X_Radar_Daily.md"
DEFAULT_13F = ROOT / "us_radar_13f_system_input_seed.csv"
DEFAULT_VALUATION = ROOT / "research_snapshots" / "20260520" / "radar_order_valuation_seed_after_NEE_20260520.csv"

TICKER_RE = re.compile(r"`([^`]+)`")
SOURCE_WEIGHTS = {
    "market": 1.00,
    "x_radar": 0.75,
    "seeking_alpha": 0.70,
    "earnings": 0.80,
    "13f": 0.55,
    "manual": 0.65,
    "valuation": 0.55,
}
THEME_ALIASES = [
    ("AI infra", "ai_infra"),
    ("AI Infrastructure", "ai_infra"),
    ("AI data center", "ai_power_datacenter"),
    ("data center", "ai_power_datacenter"),
    ("AI networking", "ai_networking"),
    ("AI optical", "ai_optical"),
    ("optical", "ai_optical"),
    ("HBM", "ai_memory"),
    ("memory", "ai_memory"),
    ("Semis", "semis_ai"),
    ("semi", "semis_ai"),
    ("Search", "ai_platform"),
    ("Google", "ai_platform"),
    ("AI power", "ai_power_datacenter"),
    ("regulated utility", "ai_power_datacenter"),
    ("AI accelerator", "semis_ai"),
    ("GPU", "semis_ai"),
    ("manufacturing anchor", "semis_ai"),
    ("core reacceleration", "semis_ai"),
    ("custom ASIC", "ai_networking"),
    ("high-speed connectivity", "ai_optical"),
    ("rack-scale connectivity", "ai_optical"),
    ("photonics", "ai_optical"),
    ("storage", "ai_memory"),
    ("HDD", "ai_memory"),
    ("advanced packaging", "semis_ai"),
    ("OSAT", "semis_ai"),
    ("robotics", "robotics_automation"),
    ("industrial automation", "robotics_automation"),
]
ACTION_TOKENS = {
    "AddToRadar",
    "ReviewRisk",
    "UpdateThesis",
    "ReadMore",
    "NoAction",
}
TICKER_THEME_OVERRIDES = {
    "US.NVDA": "semis_ai",
    "US.AMD": "semis_ai",
    "US.TSM": "semis_ai",
    "US.AVGO": "ai_networking",
    "US.ANET": "ai_networking",
    "US.MRVL": "ai_networking",
    "US.NOK": "ai_optical",
    "US.COHR": "ai_optical",
    "US.AAOI": "ai_optical",
    "US.LITE": "ai_optical",
    "US.CRDO": "ai_optical",
    "US.ALAB": "ai_optical",
    "US.MU": "ai_memory",
    "US.WDC": "ai_memory",
    "US.SNDK": "ai_memory",
    "US.IREN": "ai_power_datacenter",
    "US.BE": "ai_power_datacenter",
    "US.APLD": "ai_power_datacenter",
    "US.CORZ": "ai_power_datacenter",
    "US.NEE": "ai_power_datacenter",
    "US.ETN": "ai_power_datacenter",
    "US.GEV": "ai_power_datacenter",
    "US.CEG": "ai_power_datacenter",
    "US.GOOGL": "ai_platform",
    "US.MSFT": "ai_platform",
    "US.META": "ai_platform",
    "US.AMZN": "ai_platform",
    "US.TSLA": "robotics_automation",
    "US.ROK": "robotics_automation",
    "US.HON": "robotics_automation",
    "US.IR": "robotics_automation",
}


def normalize_ticker(raw: str) -> str:
    token = raw.strip().replace("，", ",")
    token = token.strip(" `;；、/，,")
    if not token or token in ACTION_TOKENS:
        return ""
    if token in {"MAG7", "IPO链", "ES"}:
        return token
    if "." in token:
        return token.upper()
    if re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,8}", token):
        return "US." + token.replace(".", "_").upper() if token == "BRK.B" else "US." + token.upper()
    return token


def expand_ticker_token(raw: str) -> list[str]:
    parts = re.split(r"[/,，、\s]+", raw.strip())
    return [ticker for ticker in (normalize_ticker(part) for part in parts) if ticker]


def infer_theme(text: str) -> str:
    lower = text.lower()
    for key, theme in THEME_ALIASES:
        if key.lower() in lower:
            return theme
    return "unclassified"


def direction_from_text(text: str) -> str:
    lower = text.lower()
    if any(word in lower for word in ["put", "risk", "penalty", "hedge", "crowding", "不买", "风险", "惩罚"]):
        if any(word in lower for word in ["long", "validation", "确认", "strong"]):
            return "mixed"
        return "negative"
    if any(word in lower for word in ["long", "validation", "addtoradar", "确认", "强化", "candidate", "可复核"]):
        return "positive"
    return "neutral"


def confidence_from_importance(text: str, default: float = 0.55) -> float:
    lower = text.lower()
    if "high" in lower or "p0" in lower:
        return 0.80
    if "medium" in lower or "p1" in lower:
        return 0.62
    if "low" in lower or "p2" in lower:
        return 0.42
    return default


def freshness(asof: str, source_date: str) -> float:
    try:
        days = (pd.to_datetime(asof).date() - pd.to_datetime(source_date).date()).days
    except Exception:
        days = 7
    if days <= 1:
        return 1.0
    if days <= 7:
        return 0.85
    if days <= 30:
        return 0.65
    if days <= 90:
        return 0.35
    return 0.15


def expiry_from_source(source_date: str, days: int) -> str:
    try:
        base = pd.to_datetime(source_date).date()
    except Exception:
        base = date.today()
    return str(base + timedelta(days=days))


def add_row(rows: list[dict[str, Any]], **kwargs: Any) -> None:
    base = {
        "asof": "",
        "theme": "unclassified",
        "ticker": "",
        "source": "",
        "source_path": "",
        "source_date": "",
        "evidence_type": "",
        "confidence": 0.5,
        "direction": "neutral",
        "freshness": 0.5,
        "expiry_date": "",
        "summary": "",
        "weight": 0.5,
    }
    base.update(kwargs)
    base["confidence"] = round(float(base["confidence"]), 4)
    base["freshness"] = round(float(base["freshness"]), 4)
    base["weight"] = round(float(base["weight"]), 4)
    rows.append(base)


def parse_x_radar(path: Path, asof: str) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    source_date = "2026-05-19"
    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        if not line.startswith("|") or "`" not in line:
            continue
        tickers: list[str] = []
        for item in TICKER_RE.findall(line):
            tickers.extend(expand_ticker_token(item))
        if not tickers:
            continue
        default_theme = infer_theme(line)
        confidence = confidence_from_importance(line, 0.58)
        direction = direction_from_text(line)
        for ticker in tickers:
            if ticker in {"US.SPY", "US.QQQ", "US.ES", "US.MAG7"} and "盈利集中" in line:
                continue
            theme = TICKER_THEME_OVERRIDES.get(ticker, default_theme)
            add_row(
                rows,
                asof=asof,
                theme=theme,
                ticker=ticker,
                source="x_radar",
                source_path=str(path),
                source_date=source_date,
                evidence_type="narrative_or_risk",
                confidence=confidence,
                direction=direction,
                freshness=freshness(asof, source_date),
                expiry_date=expiry_from_source(source_date, 14),
                summary=line.strip("| "),
                weight=SOURCE_WEIGHTS["x_radar"],
            )
    return rows


def parse_13f(path: Path, asof: str) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    df = pd.read_csv(path)
    rows: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        ticker = normalize_ticker(str(row.get("ticker", "")))
        theme = TICKER_THEME_OVERRIDES.get(ticker, infer_theme(str(row.get("theme", ""))))
        conf = min(0.9, 0.35 + float(row.get("institutional_validation", 0) or 0) / 10.0)
        hedge = str(row.get("institutional_hedge_signal", ""))
        direction = "mixed" if "hedge" in hedge.lower() or "put" in hedge.lower() else "positive"
        add_row(
            rows,
            asof=asof,
            theme=theme,
            ticker=ticker,
            source="13f",
            source_path=str(path),
            source_date=str(row.get("as_of", asof)),
            evidence_type="institutional_validation",
            confidence=conf,
            direction=direction,
            freshness=freshness(asof, str(row.get("as_of", asof))),
            expiry_date=str(row.get("review_deadline", "")),
            summary=f"{row.get('source_managers', '')}; action={row.get('next_system_action', '')}; no_trade={row.get('no_trade_reason', '')}",
            weight=SOURCE_WEIGHTS["13f"],
        )
    return rows


def parse_valuation(path: Path, asof: str) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    df = pd.read_csv(path)
    rows: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        ticker = normalize_ticker(str(row.get("ticker", "")))
        theme = TICKER_THEME_OVERRIDES.get(ticker, infer_theme(str(row.get("theme", ""))))
        score = float(row.get("valuation_reality_score", 50) or 50)
        verdict = str(row.get("valuation_verdict", ""))
        direction = "positive" if score >= 68 and "NEEDS_PULLBACK" in verdict else "mixed"
        if "TOO_MUCH_NARRATIVE" in verdict:
            direction = "negative"
        source_date = str(row.get("last_updated", asof))
        add_row(
            rows,
            asof=asof,
            theme=theme,
            ticker=ticker,
            source="valuation",
            source_path=str(path),
            source_date=source_date,
            evidence_type="valuation_reality",
            confidence=min(0.85, 0.35 + score / 100.0 * 0.5),
            direction=direction,
            freshness=freshness(asof, source_date),
            expiry_date=expiry_from_source(source_date, 30),
            summary=f"{row.get('company', '')}: {verdict}; {row.get('trade_posture_override', '')}; {row.get('source_note', '')}",
            weight=SOURCE_WEIGHTS["valuation"],
        )
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def render_md(rows: list[dict[str, Any]], asof: str) -> str:
    by_source: dict[str, int] = {}
    by_theme: dict[str, int] = {}
    for row in rows:
        by_source[row["source"]] = by_source.get(row["source"], 0) + 1
        by_theme[row["theme"]] = by_theme.get(row["theme"], 0) + 1
    top_theme = sorted(by_theme.items(), key=lambda item: item[1], reverse=True)[:8]
    lines = [
        "# V6AB Evidence Ledger v1",
        "",
        f"- 日期：`{asof}`",
        f"- 证据数：`{len(rows)}`",
        "- 边界：证据账本只影响研究分数、allowlist、ranking 和 sleeve cap hint；不直接触发交易。",
        "",
        "## 来源统计",
        "",
    ]
    for source, count in sorted(by_source.items()):
        lines.append(f"- `{source}`：{count}")
    lines += ["", "## 主题覆盖", ""]
    for theme, count in top_theme:
        lines.append(f"- `{theme}`：{count}")
    lines += [
        "",
        "## 样例证据",
        "",
        "| theme | ticker | source | type | confidence | direction | summary |",
        "| --- | --- | --- | --- | ---: | --- | --- |",
    ]
    for row in rows[:20]:
        summary = str(row["summary"]).replace("|", "/")[:140]
        lines.append(
            f"| {row['theme']} | `{row['ticker']}` | {row['source']} | {row['evidence_type']} | "
            f"{row['confidence']:.2f} | {row['direction']} | {summary} |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build V6AB Daily Evolution evidence ledger v1.")
    parser.add_argument("--asof", default=str(date.today()))
    parser.add_argument("--x-radar", type=Path, default=DEFAULT_X_RADAR)
    parser.add_argument("--13f", type=Path, default=DEFAULT_13F)
    parser.add_argument("--valuation", type=Path, default=DEFAULT_VALUATION)
    parser.add_argument("--output-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    rows: list[dict[str, Any]] = []
    rows.extend(parse_x_radar(args.x_radar, args.asof))
    rows.extend(parse_13f(args.__dict__["13f"], args.asof))
    rows.extend(parse_valuation(args.valuation, args.asof))
    rows = [row for row in rows if row.get("ticker")]

    args.output_dir.mkdir(parents=True, exist_ok=True)
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    payload = {"asof": args.asof, "rows": rows}
    md = render_md(rows, args.asof)
    (args.output_dir / "latest_evidence_ledger.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(args.output_dir / "latest_evidence_ledger.csv", rows)
    (args.output_dir / "latest_evidence_ledger.md").write_text(md, encoding="utf-8")
    (REPORT_ROOT / "V6AB_Evidence_Ledger_LATEST.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(REPORT_ROOT / "V6AB_Evidence_Ledger_LATEST.csv", rows)
    (REPORT_ROOT / "V6AB_Evidence_Ledger_LATEST.md").write_text(md, encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
