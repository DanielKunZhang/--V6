#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "backtest_results" / "monthly_research_review"
CENTRAL_RISK_DIR = ROOT / "backtest_results" / "central_risk_board"
ATTRIBUTION_DIR = ROOT / "backtest_results" / "performance_attribution"
WEEKLY_REVIEW_DIR = ROOT / "backtest_results" / "v6_weekly_review"
BACKLOG_DIR = ROOT / "backtest_results" / "v6_research_backlog"
OVERLAY_DIR = ROOT / "backtest_results" / "overlay_trade_journal"
MISSING_REVIEW_PATH = ROOT / "backtest_results" / "v6b_missing_opportunity_review" / "latest.json"
REGISTRY_PATH = ROOT / "v6_strategy_lab" / "configs" / "v6b_candidate_registry_v1.json"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def latest_file(directory: Path, pattern: str) -> Path | None:
    if not directory.exists():
        return None
    files = sorted(directory.glob(pattern), key=lambda item: item.stat().st_mtime)
    return files[-1] if files else None


def optional_json(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    try:
        return read_json(path)
    except Exception:
        return {}


def fmt_usd(value: float | None) -> str:
    if value is None:
        return "—"
    if abs(value) < 100:
        return f"${value:,.2f}"
    return f"${value:,.0f}"


def fmt_pct(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:.1f}%"


def summarize_registry() -> dict[str, Any]:
    payload = optional_json(REGISTRY_PATH)
    entries = payload.get("entries", []) if isinstance(payload.get("entries"), list) else []
    counts: dict[str, int] = {}
    top_watch: list[str] = []
    for entry in entries:
        status = str(entry.get("registry_status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
        if status in {"watch_add_candidate", "theme_watch"} and len(top_watch) < 8:
            top_watch.append(str(entry.get("ticker") or ""))
    return {
        "entry_count": len(entries),
        "status_counts": counts,
        "top_watch": top_watch,
    }


def build_payload() -> dict[str, Any]:
    central_path = (CENTRAL_RISK_DIR / "latest_weekly.json") if (CENTRAL_RISK_DIR / "latest_weekly.json").exists() else (CENTRAL_RISK_DIR / "latest.json")
    attribution_path = ATTRIBUTION_DIR / "latest.json"
    overlay_path = OVERLAY_DIR / "latest.json"
    weekly_path = latest_file(WEEKLY_REVIEW_DIR, "*.json")
    backlog_path = latest_file(BACKLOG_DIR, "*.json")

    central = optional_json(central_path)
    attribution = optional_json(attribution_path)
    overlay = optional_json(overlay_path)
    weekly = optional_json(weekly_path)
    backlog = optional_json(backlog_path)
    missing = optional_json(MISSING_REVIEW_PATH)
    registry = summarize_registry()

    backlog_items = backlog if isinstance(backlog, list) else []
    top_backlog = backlog_items[:6]
    missing_summary = missing.get("summary", {}) if isinstance(missing.get("summary"), dict) else {}

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "month_tag": datetime.now().strftime("%Y-%m"),
        "sources": {
            "central_risk": str(central_path.relative_to(ROOT)) if central_path.exists() else "",
            "performance_attribution": str(attribution_path.relative_to(ROOT)) if attribution_path.exists() else "",
            "weekly_review": str(weekly_path.relative_to(ROOT)) if weekly_path else "",
            "research_backlog": str(backlog_path.relative_to(ROOT)) if backlog_path else "",
            "overlay_journal": str(overlay_path.relative_to(ROOT)) if overlay_path.exists() else "",
            "missing_review": str(MISSING_REVIEW_PATH.relative_to(ROOT)) if MISSING_REVIEW_PATH.exists() else "",
            "registry": str(REGISTRY_PATH.relative_to(ROOT)),
        },
        "central_risk": central,
        "attribution": attribution,
        "weekly_review": weekly,
        "backlog_items": top_backlog,
        "overlay": overlay,
        "missing_summary": {
            "critical_miss_count": int(missing_summary.get("critical_miss_count") or 0),
            "watch_miss_count": int(missing_summary.get("watch_miss_count") or 0),
            "coverage_gap_count": int(missing_summary.get("coverage_gap_count") or 0),
            "theme_wakeup_count": int(missing_summary.get("theme_wakeup_count") or 0),
            "critical_miss_tickers": [str(item) for item in missing_summary.get("critical_miss_tickers", [])],
            "theme_wakeups": [str(item) for item in missing_summary.get("theme_wakeups", [])],
        },
        "registry_summary": registry,
    }


def one_line_read(payload: dict[str, Any]) -> str:
    risk = payload.get("central_risk", {})
    weekly = payload.get("weekly_review", {})
    status = str(risk.get("status") or "UNKNOWN")
    decision = str(weekly.get("decision") or "No weekly decision")
    return f"当前月度主线仍然是 `V6-A 治理 + 账户集中度收敛 + V6-B 研究供给链准备`；中央风控 `{status}`，最近 V6 周复盘结论 `{decision}`。"


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
    body = []
    for row in rows:
        tds = "".join(f"<td>{html.escape(str(row.get(key, '')))}</td>" for key, _ in columns)
        body.append(f"<tr>{tds}</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def backlog_display_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for item in payload["backlog_items"]:
        rows.append(
            {
                "priority": item.get("priority", ""),
                "lane": item.get("lane", ""),
                "title": item.get("title", ""),
                "next": item.get("next_step", ""),
            }
        )
    return rows


def write_markdown(path: Path, payload: dict[str, Any]) -> None:
    risk = payload.get("central_risk", {})
    attribution = payload.get("attribution", {})
    coverage = attribution.get("coverage", {}) if isinstance(attribution.get("coverage"), dict) else {}
    overlay_stats = (payload.get("overlay", {}) or {}).get("stats", {})
    missing = payload["missing_summary"]
    registry = payload["registry_summary"]
    weekly = payload.get("weekly_review", {})

    lines = [
        "# Monthly Research Review v1",
        "",
        f"- Generated: `{payload['generated_at']}`",
        f"- Month Tag: `{payload['month_tag']}`",
        "",
        "## One-Line Read",
        "",
        f"- {one_line_read(payload)}",
        "",
        "## Firm Risk Snapshot",
        "",
        f"- Central risk status: `{risk.get('status', 'UNKNOWN')}`",
        f"- Status reasons: `{', '.join(risk.get('status_reasons', [])) if risk.get('status_reasons') else 'none'}`",
        f"- Largest single position: `{risk.get('firm_snapshot', {}).get('max_position', '—')}`",
        f"- Top theme weight: `{risk.get('themes', [{}])[0].get('current_pct', '—') if risk.get('themes') else '—'}`",
        "",
        "## Performance Attribution Snapshot",
        "",
        f"- Broker coverage ratio: `{fmt_pct(coverage.get('covered_ratio_pct'))}`",
        f"- Broker unrealized P/L: `{fmt_usd(coverage.get('unrealized_pl_usd'))}`",
        f"- Broker unrealized P/L vs broker equity: `{fmt_pct(coverage.get('unrealized_pl_pct_broker_equity'))}`",
        f"- Broker unrealized P/L vs total assets: `{fmt_pct(coverage.get('unrealized_pl_pct_total_assets'))}`",
        "",
        "## V6 Operating Snapshot",
        "",
        f"- Weekly review decision: `{weekly.get('decision', 'UNKNOWN')}`",
        f"- Pilot review decision: `{weekly.get('pilot_review_decision', 'UNKNOWN')}`",
        f"- Managed unrealized P/L: `{weekly.get('managed_unrealized_pl_pct_points', '—')}` pct-points",
        f"- Top3 concentration: `{round(float(weekly.get('top3_weight', 0.0)) * 100, 1) if weekly.get('top3_weight') is not None else '—'}%`",
        "",
        "## Radar / V6-B Supply Chain",
        "",
        f"- Registry entry count: `{registry['entry_count']}`",
        f"- Registry status counts: `{registry['status_counts']}`",
        f"- Critical misses: `{missing['critical_miss_count']}`",
        f"- Theme wakeups: `{missing['theme_wakeup_count']}`",
        f"- Coverage gaps: `{missing['coverage_gap_count']}`",
        f"- Priority watch names: `{', '.join(registry['top_watch']) if registry['top_watch'] else 'none'}`",
        "",
        "## Overlay Lab Snapshot",
        "",
        f"- Closed sample count: `{overlay_stats.get('closed_sample_count', 0)}`",
        f"- Live or watch count: `{overlay_stats.get('live_or_watch_count', 0)}`",
        f"- Overlay realized P/L: `{fmt_usd(overlay_stats.get('total_realized_pnl_usd'))}`",
        "",
        "## Top Backlog",
        "",
    ]
    lines.extend(render_table(backlog_display_rows(payload), [("priority", "priority"), ("lane", "lane"), ("title", "title"), ("next", "next step")]))
    lines.extend(["", "## Current Judgment", ""])
    lines.append("- 6月1日前，最该做的是把 `风控 / 归因 / review / overlay 样本登记 / V6-B 执行卡` 固化；不是提前给 V6-B 申请生产预算。")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_html(payload: dict[str, Any]) -> str:
    risk = payload.get("central_risk", {})
    attribution = payload.get("attribution", {})
    coverage = attribution.get("coverage", {}) if isinstance(attribution.get("coverage"), dict) else {}
    overlay_stats = (payload.get("overlay", {}) or {}).get("stats", {})
    missing = payload["missing_summary"]
    registry = payload["registry_summary"]
    weekly = payload.get("weekly_review", {})

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Monthly Research Review</title>
  <style>
    body {{
      margin: 0;
      padding: 24px;
      background: #f5f7fb;
      color: #0f172a;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", sans-serif;
      line-height: 1.55;
    }}
    .wrap {{ max-width: 1100px; margin: 0 auto; }}
    .hero {{
      background: linear-gradient(135deg, #111827, #1f2937);
      color: #fff;
      border-radius: 22px;
      padding: 24px 28px;
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
    .kicker {{ color: #64748b; font-size: 12px; font-weight: 800; text-transform: uppercase; }}
    .num {{ margin-top: 8px; font-size: 28px; font-weight: 800; }}
    h2 {{ margin: 26px 0 12px; font-size: 20px; }}
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
    th {{ background: #e2e8f0; color: #334155; font-size: 12px; font-weight: 800; }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="hero">
      <div style="font-size:12px;font-weight:800;opacity:.85;">Monthly Research Review v1</div>
      <h1 style="margin:10px 0 8px;font-size:32px;">Current-Month Governance Snapshot</h1>
      <div>{html.escape(one_line_read(payload))}</div>
    </div>
    <div class="grid">
      <div class="card"><div class="kicker">Central Risk</div><div class="num">{html.escape(str(risk.get('status', 'UNKNOWN')))}</div></div>
      <div class="card"><div class="kicker">Broker Coverage</div><div class="num">{html.escape(fmt_pct(coverage.get('covered_ratio_pct')))}</div></div>
      <div class="card"><div class="kicker">Critical Misses</div><div class="num">{missing['critical_miss_count']}</div></div>
      <div class="card"><div class="kicker">Overlay Samples</div><div class="num">{overlay_stats.get('closed_sample_count', 0)}</div></div>
    </div>
    <h2>Top Backlog</h2>
    {render_html_table(backlog_display_rows(payload), [('priority', 'priority'), ('lane', 'lane'), ('title', 'title'), ('next', 'next step')])}
    <h2>Current Snapshot</h2>
    <table>
      <thead><tr><th>dimension</th><th>value</th></tr></thead>
      <tbody>
        <tr><td>Central risk status</td><td>{html.escape(str(risk.get('status', 'UNKNOWN')))}</td></tr>
        <tr><td>Weekly V6 decision</td><td>{html.escape(str(weekly.get('decision', 'UNKNOWN')))}</td></tr>
        <tr><td>Broker unrealized P/L</td><td>{html.escape(fmt_usd(coverage.get('unrealized_pl_usd')))}</td></tr>
        <tr><td>Registry status counts</td><td>{html.escape(str(registry['status_counts']))}</td></tr>
        <tr><td>Theme wakeups</td><td>{missing['theme_wakeup_count']}</td></tr>
        <tr><td>Overlay live or watch</td><td>{overlay_stats.get('live_or_watch_count', 0)}</td></tr>
      </tbody>
    </table>
  </div>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate monthly research review snapshot.")
    parser.add_argument("--tag", default=datetime.now().strftime("%Y%m%dT%H%M%S"))
    args = parser.parse_args()

    payload = build_payload()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUT_DIR / f"monthly_research_review_{args.tag}.json"
    md_path = OUT_DIR / f"monthly_research_review_{args.tag}.md"
    html_path = OUT_DIR / f"monthly_research_review_{args.tag}.html"

    latest_json = OUT_DIR / "latest.json"
    latest_md = OUT_DIR / "latest.md"
    latest_html = OUT_DIR / "latest.html"

    html_content = build_html(payload)
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(md_path, payload)
    html_path.write_text(html_content, encoding="utf-8")

    latest_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    latest_md.write_text(md_path.read_text(encoding="utf-8"), encoding="utf-8")
    latest_html.write_text(html_content, encoding="utf-8")

    print("== Monthly Research Review ==")
    print(f"JSON:   {json_path}")
    print(f"Report: {md_path}")
    print(f"HTML:   {html_path}")
    print(f"Month:  {payload['month_tag']}")


if __name__ == "__main__":
    main()
