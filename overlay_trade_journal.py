#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
REGISTER_PATH = ROOT / "overlay_trade_register.csv"
OUT_DIR = ROOT / "backtest_results" / "overlay_trade_journal"


def parse_float(value: str) -> float | None:
    text = (value or "").strip().replace("$", "").replace("%", "").replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


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


def load_rows() -> list[dict[str, Any]]:
    if not REGISTER_PATH.exists():
        return []
    with REGISTER_PATH.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        rows = []
        for row in reader:
            rows.append(
                {
                    **row,
                    "budget_usd": parse_float(row.get("budget_usd", "")),
                    "premium_debit_usd": parse_float(row.get("premium_debit_usd", "")),
                    "max_loss_usd": parse_float(row.get("max_loss_usd", "")),
                    "realized_pnl_usd": parse_float(row.get("realized_pnl_usd", "")),
                    "return_pct": parse_float(row.get("return_pct", "")),
                }
            )
        return rows


def build_payload() -> dict[str, Any]:
    rows = load_rows()
    active_statuses = {"watch", "research_ready", "planned", "opened", "active"}
    closed_rows = [row for row in rows if str(row.get("status", "")).lower() == "closed"]
    live_rows = [row for row in rows if str(row.get("status", "")).lower() in active_statuses]

    lane_counts: dict[str, int] = {}
    status_counts: dict[str, int] = {}
    for row in rows:
        lane = str(row.get("lane") or "unknown")
        status = str(row.get("status") or "unknown")
        lane_counts[lane] = lane_counts.get(lane, 0) + 1
        status_counts[status] = status_counts.get(status, 0) + 1

    pnl_values = [float(row["realized_pnl_usd"]) for row in closed_rows if row.get("realized_pnl_usd") is not None]
    return_values = [float(row["return_pct"]) for row in closed_rows if row.get("return_pct") is not None]
    total_realized = round(sum(pnl_values), 2) if pnl_values else 0.0
    win_count = len([value for value in pnl_values if value > 0])
    loss_count = len([value for value in pnl_values if value < 0])
    win_rate = round(win_count / len(pnl_values) * 100, 1) if pnl_values else None
    avg_return_pct = round(sum(return_values) / len(return_values), 2) if return_values else None

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "register_path": str(REGISTER_PATH.relative_to(ROOT)),
        "total_rows": len(rows),
        "lane_counts": lane_counts,
        "status_counts": status_counts,
        "active_rows": live_rows,
        "closed_rows": closed_rows,
        "stats": {
            "closed_sample_count": len(closed_rows),
            "live_or_watch_count": len(live_rows),
            "total_realized_pnl_usd": total_realized,
            "win_count": win_count,
            "loss_count": loss_count,
            "win_rate_pct": win_rate,
            "avg_return_pct": avg_return_pct,
        },
        "known_limits": [
            "这本账当前只记录 Radar-Sourced Overlay / Lane A / Lane B 样本，不记录主仓或 V6。",
            "只有 status=closed 且写明 realized_pnl_usd 的记录，才算真实样本。",
            "research_ready / watch 只代表准备状态，不计入策略胜率。",
        ],
    }


def one_line_read(payload: dict[str, Any]) -> str:
    stats = payload["stats"]
    if stats["closed_sample_count"] == 0:
        return "当前 Overlay 账本还处于样本建立前期，重点不是评估胜率，而是保证每一笔候选都进入同口径登记。"
    return f"当前 Overlay 已有 `{stats['closed_sample_count']}` 笔真实样本，累计实现盈亏 `{fmt_usd(stats['total_realized_pnl_usd'])}`。"


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


def active_display_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for row in payload["active_rows"]:
        rows.append(
            {
                "case_id": row.get("case_id", ""),
                "status": row.get("status", ""),
                "lane": row.get("lane", ""),
                "underlying": row.get("underlying", ""),
                "structure": row.get("structure", ""),
                "budget": fmt_usd(row.get("budget_usd")),
                "max_loss": fmt_usd(row.get("max_loss_usd")),
                "notes": row.get("notes", ""),
            }
        )
    return rows


def closed_display_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for row in payload["closed_rows"]:
        rows.append(
            {
                "case_id": row.get("case_id", ""),
                "lane": row.get("lane", ""),
                "underlying": row.get("underlying", ""),
                "pnl": fmt_usd(row.get("realized_pnl_usd")),
                "return_pct": fmt_pct(row.get("return_pct")),
                "review": row.get("review", ""),
            }
        )
    return rows


def write_markdown(path: Path, payload: dict[str, Any]) -> None:
    stats = payload["stats"]
    lines = [
        "# Overlay Trade Journal",
        "",
        f"- Generated: `{payload['generated_at']}`",
        f"- Register: `{payload['register_path']}`",
        "",
        "## One-Line Read",
        "",
        f"- {one_line_read(payload)}",
        "",
        "## Stats",
        "",
        f"- Total rows: `{payload['total_rows']}`",
        f"- Closed sample count: `{stats['closed_sample_count']}`",
        f"- Live or watch count: `{stats['live_or_watch_count']}`",
        f"- Total realized P/L: `{fmt_usd(stats['total_realized_pnl_usd'])}`",
        f"- Win rate: `{fmt_pct(stats['win_rate_pct'])}`",
        f"- Average return: `{fmt_pct(stats['avg_return_pct'])}`",
        "",
        "## Active / Watch Register",
        "",
    ]
    lines.extend(render_table(active_display_rows(payload), [("case_id", "case"), ("status", "status"), ("lane", "lane"), ("underlying", "underlying"), ("structure", "structure"), ("budget", "budget"), ("max_loss", "max_loss"), ("notes", "notes")]))
    lines.extend(["", "## Closed Sample Register", ""])
    lines.extend(render_table(closed_display_rows(payload), [("case_id", "case"), ("lane", "lane"), ("underlying", "underlying"), ("pnl", "realized_pnl"), ("return_pct", "return"), ("review", "review")]))
    lines.extend(["", "## Known Limits", ""])
    for item in payload["known_limits"]:
        lines.append(f"- {item}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_html(payload: dict[str, Any]) -> str:
    stats = payload["stats"]
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Overlay Trade Journal</title>
  <style>
    body {{
      margin: 0;
      padding: 24px;
      background: #f7f8fc;
      color: #0f172a;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", sans-serif;
      line-height: 1.55;
    }}
    .wrap {{ max-width: 1040px; margin: 0 auto; }}
    .hero {{
      background: linear-gradient(135deg, #111827, #374151);
      color: white;
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
      <div style="font-size:12px;font-weight:800;opacity:.85;">Overlay Trade Journal</div>
      <h1 style="margin:10px 0 8px;font-size:32px;">Radar-Sourced Overlay Sample Register</h1>
      <div>{html.escape(one_line_read(payload))}</div>
    </div>
    <div class="grid">
      <div class="card"><div class="kicker">Total Rows</div><div class="num">{payload['total_rows']}</div></div>
      <div class="card"><div class="kicker">Closed Samples</div><div class="num">{stats['closed_sample_count']}</div></div>
      <div class="card"><div class="kicker">Live or Watch</div><div class="num">{stats['live_or_watch_count']}</div></div>
      <div class="card"><div class="kicker">Realized P/L</div><div class="num">{html.escape(fmt_usd(stats['total_realized_pnl_usd']))}</div></div>
    </div>
    <h2>Active / Watch Register</h2>
    {render_html_table(active_display_rows(payload), [('case_id', 'case'), ('status', 'status'), ('lane', 'lane'), ('underlying', 'underlying'), ('structure', 'structure'), ('budget', 'budget'), ('max_loss', 'max_loss'), ('notes', 'notes')])}
    <h2>Closed Sample Register</h2>
    {render_html_table(closed_display_rows(payload), [('case_id', 'case'), ('lane', 'lane'), ('underlying', 'underlying'), ('pnl', 'realized_pnl'), ('return_pct', 'return'), ('review', 'review')])}
  </div>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize overlay sample register.")
    parser.add_argument("--tag", default=datetime.now().strftime("%Y%m%dT%H%M%S"))
    args = parser.parse_args()

    payload = build_payload()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUT_DIR / f"overlay_trade_journal_{args.tag}.json"
    md_path = OUT_DIR / f"overlay_trade_journal_{args.tag}.md"
    html_path = OUT_DIR / f"overlay_trade_journal_{args.tag}.html"

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

    print("== Overlay Trade Journal ==")
    print(f"JSON:   {json_path}")
    print(f"Report: {md_path}")
    print(f"HTML:   {html_path}")
    print(f"Rows:   {payload['total_rows']}")


if __name__ == "__main__":
    main()
