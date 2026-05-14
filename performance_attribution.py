#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from central_risk_board import extract_portfolio_meta, load_board_config, normalize_v6_name
from morning_brief import collect_v6


ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "backtest_results" / "performance_attribution"
SNAPSHOT_PATH = ROOT / "cash_alpha_v3_repo" / "backtest_results" / "futu_account_snapshot_latest.json"
PILOT_REVIEW_DIR = ROOT / "backtest_results" / "v6a_pilot_review"


CODE_OVERRIDES = {
    "HK.00181": {"display_name": "闽港控股", "sleeve": "Experimental", "theme": "其他/观察仓"},
    "HK.00700": {"display_name": "腾讯", "sleeve": "Value Main Book", "theme": "中国平台互联网"},
    "HK.09992": {"display_name": "泡泡玛特", "sleeve": "Value Main Book", "theme": "中国消费/IP"},
    "US.ADBE": {"display_name": "ADBE", "sleeve": "Value Main Book", "theme": "美国软件"},
    "US.CRDO": {"display_name": "CRDO", "sleeve": "Radar Overlay", "theme": "AI连接/交换"},
    "US.IT": {"display_name": "IT", "sleeve": "Value Main Book", "theme": "IT服务"},
    "US.NU": {"display_name": "NU", "sleeve": "Value Main Book", "theme": "拉美金融科技"},
    "US.NVDA": {"display_name": "NVDA", "sleeve": "Value Main Book", "theme": "AI半导体"},
    "US.PDD": {"display_name": "PDD", "sleeve": "Value Main Book", "theme": "中国平台互联网"},
}

UNDERLYING_OVERRIDES = {
    "ADBE": {"display_name": "ADBE", "sleeve": "Value Main Book", "theme": "美国软件"},
    "AAPL": {"display_name": "AAPL", "sleeve": "Experimental", "theme": "美国平台硬件"},
    "AMZN": {"display_name": "AMZN", "sleeve": "V6", "theme": "美国平台/云"},
    "AVGO": {"display_name": "AVGO", "sleeve": "V6", "theme": "AI半导体"},
    "BIL": {"display_name": "BIL", "sleeve": "V6", "theme": "现金类防守"},
    "CRDO": {"display_name": "CRDO", "sleeve": "Radar Overlay", "theme": "AI连接/交换"},
    "GLD": {"display_name": "GLD", "sleeve": "V6", "theme": "黄金防守"},
    "GOOGL": {"display_name": "GOOGL", "sleeve": "V6", "theme": "美国平台/AI"},
    "MSFT": {"display_name": "MSFT", "sleeve": "Experimental", "theme": "美国平台/软件"},
    "NTE": {"display_name": "网易", "sleeve": "Experimental", "theme": "中国平台互联网"},
    "NU": {"display_name": "NU", "sleeve": "Value Main Book", "theme": "拉美金融科技"},
    "NVDA": {"display_name": "NVDA", "sleeve": "Value Main Book", "theme": "AI半导体"},
    "PDD": {"display_name": "PDD", "sleeve": "Value Main Book", "theme": "中国平台互联网"},
    "POP": {"display_name": "泡泡玛特", "sleeve": "Value Main Book", "theme": "中国消费/IP"},
    "TCH": {"display_name": "腾讯", "sleeve": "Value Main Book", "theme": "中国平台互联网"},
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def latest_file(directory: Path, pattern: str) -> Path | None:
    if not directory.exists():
        return None
    files = sorted(directory.glob(pattern), key=lambda item: item.stat().st_mtime)
    return files[-1] if files else None


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


def option_underlying(code: str) -> str | None:
    match = re.match(r"^(?:US|HK)\.([A-Z]+)\d{6}[CP]\d+", code)
    if match:
        return match.group(1)
    return None


def is_option_code(code: str, qty: float) -> bool:
    if option_underlying(code):
        return True
    return abs(qty) < 10 and re.search(r"[CP]\d+$", code) is not None


def convert_pl_to_usd(value: float, currency: str, fx_hkd_per_usd: float) -> float:
    if currency == "HKD" and fx_hkd_per_usd > 0:
        return value / fx_hkd_per_usd
    return value


def classify_row(
    row: dict[str, Any],
    *,
    v6_codes: set[str],
    board_config: dict[str, Any],
    fx_hkd_per_usd: float,
    total_assets_usd: float | None,
    broker_equity_usd: float | None,
) -> dict[str, Any]:
    code = str(row.get("code") or "")
    qty = float(row.get("qty") or 0.0)
    market_value_usd = float(row.get("market_val_usd") or 0.0)
    unrealized_pl_local = float(row.get("unrealized_pl") or 0.0)
    currency = str(row.get("currency") or "USD")
    stock_name = str(row.get("stock_name") or "")
    underlying = option_underlying(code)
    is_option = is_option_code(code, qty)
    override = CODE_OVERRIDES.get(code)

    if code in v6_codes and qty > 0:
        display_name = normalize_v6_name(code)
        sleeve = "V6"
        theme = board_config.get("v6_themes", {}).get(code, "V6未映射主题")
    else:
        if override:
            display_name = str(override["display_name"])
            sleeve = str(override["sleeve"])
            theme = str(override["theme"])
        else:
            base = underlying or normalize_v6_name(code)
            base_override = UNDERLYING_OVERRIDES.get(base, {})
            display_name = str(base_override.get("display_name") or base or stock_name or code)
            sleeve = str(base_override.get("sleeve") or ("Experimental" if is_option else "Value Main Book"))
            theme = str(
                base_override.get("theme")
                or board_config.get("position_themes", {}).get(display_name)
                or "其他/待映射"
            )

    unrealized_pl_usd = round(convert_pl_to_usd(unrealized_pl_local, currency, fx_hkd_per_usd), 2)
    exposure_pct_total = round(market_value_usd / total_assets_usd * 100, 2) if total_assets_usd else None
    pnl_pct_total = round(unrealized_pl_usd / total_assets_usd * 100, 3) if total_assets_usd else None
    pnl_pct_broker = round(unrealized_pl_usd / broker_equity_usd * 100, 3) if broker_equity_usd else None

    return {
        "code": code,
        "display_name": display_name,
        "stock_name": stock_name,
        "underlying": underlying or display_name,
        "sleeve": sleeve,
        "theme": theme,
        "security_type": "option" if is_option else "stock",
        "qty": qty,
        "currency": currency,
        "market_value_usd": round(market_value_usd, 2),
        "unrealized_pl_usd": unrealized_pl_usd,
        "unrealized_pl_local": round(unrealized_pl_local, 2),
        "exposure_pct_total": exposure_pct_total,
        "pnl_pct_total": pnl_pct_total,
        "pnl_pct_broker": pnl_pct_broker,
    }


def aggregate_rows(rows: list[dict[str, Any]], key: str, total_assets_usd: float | None, broker_equity_usd: float | None) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    for row in rows:
        label = str(row[key])
        bucket = buckets.setdefault(
            label,
            {
                key: label,
                "positions": 0,
                "gross_market_value_usd": 0.0,
                "net_market_value_usd": 0.0,
                "unrealized_pl_usd": 0.0,
            },
        )
        bucket["positions"] += 1
        bucket["gross_market_value_usd"] += abs(float(row["market_value_usd"]))
        bucket["net_market_value_usd"] += float(row["market_value_usd"])
        bucket["unrealized_pl_usd"] += float(row["unrealized_pl_usd"])

    out: list[dict[str, Any]] = []
    for bucket in buckets.values():
        net = float(bucket["net_market_value_usd"])
        pl = float(bucket["unrealized_pl_usd"])
        bucket["gross_market_value_usd"] = round(float(bucket["gross_market_value_usd"]), 2)
        bucket["net_market_value_usd"] = round(net, 2)
        bucket["unrealized_pl_usd"] = round(pl, 2)
        bucket["net_exposure_pct_total"] = round(net / total_assets_usd * 100, 2) if total_assets_usd else None
        bucket["pnl_pct_total"] = round(pl / total_assets_usd * 100, 3) if total_assets_usd else None
        bucket["pnl_pct_broker"] = round(pl / broker_equity_usd * 100, 3) if broker_equity_usd else None
        out.append(bucket)
    out.sort(key=lambda item: abs(float(item["unrealized_pl_usd"])), reverse=True)
    return out


def build_v6_execution_summary() -> dict[str, Any]:
    latest = latest_file(PILOT_REVIEW_DIR, "*.json")
    if latest is None:
        return {}
    payload = read_json(latest)
    perf = payload.get("performance", {}) if isinstance(payload.get("performance"), dict) else {}
    by_ticker = perf.get("by_ticker", []) if isinstance(perf.get("by_ticker"), list) else []
    top_rows = []
    for row in by_ticker[:5]:
        top_rows.append(
            {
                "code": str(row.get("code") or ""),
                "market_val": float(row.get("market_val") or 0.0),
                "unrealized_pl": float(row.get("unrealized_pl") or 0.0),
                "unrealized_pl_pct": float(row.get("unrealized_pl_pct") or 0.0),
            }
        )
    return {
        "review_decision": str(payload.get("review_decision") or ""),
        "cost_basis_usd": float(perf.get("cost_basis_total") or 0.0),
        "market_value_usd": float(perf.get("market_val_total") or 0.0),
        "unrealized_pl_usd": float(perf.get("unrealized_pl") or 0.0),
        "unrealized_pl_pct": float(perf.get("unrealized_pl_pct") or 0.0),
        "top_rows": top_rows,
        "source": str(latest.relative_to(ROOT)),
    }


def build_payload() -> dict[str, Any]:
    board_config = load_board_config()
    portfolio_meta = extract_portfolio_meta()
    v6 = collect_v6()
    snapshot = read_json(SNAPSHOT_PATH)
    fx_hkd_per_usd = float(snapshot.get("fx_hkd_per_usd") or 7.8)
    total_assets_usd = portfolio_meta.get("total_assets_usd")
    broker_equity_usd = float(snapshot.get("net_liquidation_usd") or 0.0)
    covered_ratio = round(broker_equity_usd / total_assets_usd * 100, 2) if total_assets_usd else None
    uncovered_assets_usd = round(total_assets_usd - broker_equity_usd, 2) if total_assets_usd else None
    v6_codes = {str(code) for code, qty in (v6.get("positions") or {}).items() if float(qty) > 0}

    rows: list[dict[str, Any]] = []
    for row in snapshot.get("positions", []) or []:
        qty = float(row.get("qty") or 0.0)
        market_value_usd = float(row.get("market_val_usd") or 0.0)
        unrealized_pl = float(row.get("unrealized_pl") or 0.0)
        if qty == 0 and market_value_usd == 0 and unrealized_pl == 0:
            continue
        rows.append(
            classify_row(
                row,
                v6_codes=v6_codes,
                board_config=board_config,
                fx_hkd_per_usd=fx_hkd_per_usd,
                total_assets_usd=total_assets_usd,
                broker_equity_usd=broker_equity_usd,
            )
        )

    rows.sort(key=lambda item: abs(float(item["market_value_usd"])), reverse=True)
    total_unrealized_pl_usd = round(sum(float(row["unrealized_pl_usd"]) for row in rows), 2)
    total_market_value_usd = round(sum(float(row["market_value_usd"]) for row in rows), 2)
    gross_market_value_usd = round(sum(abs(float(row["market_value_usd"])) for row in rows), 2)

    by_sleeve = aggregate_rows(rows, "sleeve", total_assets_usd, broker_equity_usd)
    by_theme = aggregate_rows(rows, "theme", total_assets_usd, broker_equity_usd)
    top_contributors = sorted(rows, key=lambda item: float(item["unrealized_pl_usd"]), reverse=True)[:8]
    top_drags = sorted(rows, key=lambda item: float(item["unrealized_pl_usd"]))[:8]
    v6_execution = build_v6_execution_summary()

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "coverage": {
            "total_assets_usd": total_assets_usd,
            "broker_equity_usd": broker_equity_usd,
            "covered_ratio_pct": covered_ratio,
            "uncovered_assets_usd": uncovered_assets_usd,
            "gross_market_value_usd": gross_market_value_usd,
            "net_market_value_usd": total_market_value_usd,
            "unrealized_pl_usd": total_unrealized_pl_usd,
            "unrealized_pl_pct_total_assets": round(total_unrealized_pl_usd / total_assets_usd * 100, 3) if total_assets_usd else None,
            "unrealized_pl_pct_broker_equity": round(total_unrealized_pl_usd / broker_equity_usd * 100, 3) if broker_equity_usd else None,
            "source": str(SNAPSHOT_PATH.relative_to(ROOT)),
        },
        "rows": rows,
        "by_sleeve": by_sleeve,
        "by_theme": by_theme,
        "top_contributors": top_contributors,
        "top_drags": top_drags,
        "v6_execution": v6_execution,
        "known_limits": [
            "当前只对 Futu 执行账本做 live mark-to-market 归因；A股/港股通/RSU 还没有统一成本账本。",
            "total-account 分母来自 26年阶段性组合策略计划.html 的人工维护口径，不是自动净值曲线。",
            "衍生品目前按 broker market value + unrealized P/L 计入，尚未展开 delta-adjusted exposure。",
        ],
    }


def one_line_read(payload: dict[str, Any]) -> str:
    contributors = payload.get("top_contributors", [])
    drags = payload.get("top_drags", [])
    top_up = contributors[0]["display_name"] if contributors else "none"
    top_down = drags[0]["display_name"] if drags else "none"
    return f"当前 Futu 执行账本的浮盈主要来自 `{top_up}`，主要拖累来自 `{top_down}`；V6 当前更多是小仓验证，不是账户盈亏主因。"


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


def sleeve_display_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "sleeve": row["sleeve"],
            "positions": row["positions"],
            "net_mv": fmt_usd(row["net_market_value_usd"]),
            "gross_mv": fmt_usd(row["gross_market_value_usd"]),
            "pl": fmt_usd(row["unrealized_pl_usd"]),
            "exposure": fmt_pct(row["net_exposure_pct_total"]),
            "broker_pl": fmt_pct(row["pnl_pct_broker"]),
        }
        for row in payload["by_sleeve"]
    ]


def theme_display_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "theme": row["theme"],
            "positions": row["positions"],
            "net_mv": fmt_usd(row["net_market_value_usd"]),
            "pl": fmt_usd(row["unrealized_pl_usd"]),
            "exposure": fmt_pct(row["net_exposure_pct_total"]),
            "broker_pl": fmt_pct(row["pnl_pct_broker"]),
        }
        for row in payload["by_theme"][:10]
    ]


def contribution_display_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "name": row["display_name"],
            "code": row["code"],
            "sleeve": row["sleeve"],
            "theme": row["theme"],
            "mv": fmt_usd(row["market_value_usd"]),
            "pl": fmt_usd(row["unrealized_pl_usd"]),
            "broker_pl": fmt_pct(row["pnl_pct_broker"]),
        }
        for row in rows
    ]


def write_markdown(path: Path, payload: dict[str, Any]) -> None:
    coverage = payload["coverage"]
    lines = [
        "# Performance Attribution v1",
        "",
        f"- Generated: `{payload['generated_at']}`",
        f"- Broker snapshot source: `{coverage['source']}`",
        "",
        "## One-Line Read",
        "",
        f"- {one_line_read(payload)}",
        "",
        "## Coverage",
        "",
        f"- Total account denominator: `{fmt_usd(coverage['total_assets_usd'])}`",
        f"- Broker covered equity: `{fmt_usd(coverage['broker_equity_usd'])}`",
        f"- Coverage ratio: `{fmt_pct(coverage['covered_ratio_pct'])}`",
        f"- Uncovered assets: `{fmt_usd(coverage['uncovered_assets_usd'])}`",
        f"- Broker gross market value: `{fmt_usd(coverage['gross_market_value_usd'])}`",
        f"- Broker net market value: `{fmt_usd(coverage['net_market_value_usd'])}`",
        f"- Broker unrealized P/L: `{fmt_usd(coverage['unrealized_pl_usd'])}`",
        f"- Broker unrealized P/L vs broker equity: `{fmt_pct(coverage['unrealized_pl_pct_broker_equity'])}`",
        f"- Broker unrealized P/L vs total assets: `{fmt_pct(coverage['unrealized_pl_pct_total_assets'])}`",
        "",
        "## Sleeve Attribution",
        "",
    ]
    lines.extend(render_table(sleeve_display_rows(payload), [("sleeve", "sleeve"), ("positions", "positions"), ("net_mv", "net_mv"), ("gross_mv", "gross_mv"), ("pl", "unrealized_pl"), ("exposure", "total_exposure"), ("broker_pl", "broker_pl_contrib")]))
    lines.extend(["", "## Theme Attribution", ""])
    lines.extend(render_table(theme_display_rows(payload), [("theme", "theme"), ("positions", "positions"), ("net_mv", "net_mv"), ("pl", "unrealized_pl"), ("exposure", "total_exposure"), ("broker_pl", "broker_pl_contrib")]))
    lines.extend(["", "## Top Contributors", ""])
    lines.extend(render_table(contribution_display_rows(payload["top_contributors"]), [("name", "name"), ("code", "code"), ("sleeve", "sleeve"), ("theme", "theme"), ("mv", "market_value"), ("pl", "unrealized_pl"), ("broker_pl", "broker_pl_contrib")]))
    lines.extend(["", "## Top Drags", ""])
    lines.extend(render_table(contribution_display_rows(payload["top_drags"]), [("name", "name"), ("code", "code"), ("sleeve", "sleeve"), ("theme", "theme"), ("mv", "market_value"), ("pl", "unrealized_pl"), ("broker_pl", "broker_pl_contrib")]))

    if payload["v6_execution"]:
        v6 = payload["v6_execution"]
        lines.extend(
            [
                "",
                "## V6 Execution Attribution",
                "",
                f"- Review decision: `{v6['review_decision']}`",
                f"- Managed cost basis: `{fmt_usd(v6['cost_basis_usd'])}`",
                f"- Managed market value: `{fmt_usd(v6['market_value_usd'])}`",
                f"- Managed unrealized P/L: `{fmt_usd(v6['unrealized_pl_usd'])}`",
                f"- Managed unrealized P/L pct: `{fmt_pct(v6['unrealized_pl_pct'])}`",
                f"- Source: `{v6['source']}`",
                "",
            ]
        )
        v6_rows = [
            {
                "code": row["code"],
                "mv": fmt_usd(row["market_val"]),
                "pl": fmt_usd(row["unrealized_pl"]),
                "pl_pct": fmt_pct(row["unrealized_pl_pct"]),
            }
            for row in v6["top_rows"]
        ]
        lines.extend(render_table(v6_rows, [("code", "code"), ("mv", "market_value"), ("pl", "unrealized_pl"), ("pl_pct", "pl_pct")]))

    lines.extend(["", "## Known Limits", ""])
    for item in payload["known_limits"]:
        lines.append(f"- {item}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_html(payload: dict[str, Any]) -> str:
    coverage = payload["coverage"]
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Performance Attribution v1</title>
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
      background: linear-gradient(135deg, #0f172a, #1e293b);
      color: #fff;
      border-radius: 22px;
      padding: 24px 28px;
      box-shadow: 0 18px 50px rgba(15, 23, 42, 0.18);
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
      margin-top: 18px;
    }}
    .card {{
      background: #fff;
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
    h2 {{ margin: 26px 0 12px; font-size: 20px; }}
    table {{
      width: 100%;
      border-collapse: collapse;
      background: #fff;
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
    ul {{ margin: 10px 0 0; padding-left: 18px; }}
    @media (max-width: 900px) {{
      .grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="hero">
      <div style="font-size:12px;font-weight:800;opacity:.85;">Performance Attribution v1</div>
      <h1 style="margin:10px 0 8px;font-size:32px;">Broker-Covered Attribution Snapshot</h1>
      <div>{html.escape(one_line_read(payload))}</div>
    </div>
    <div class="grid">
      <div class="card"><div class="kicker">Total Denominator</div><div class="num">{html.escape(fmt_usd(coverage['total_assets_usd']))}</div></div>
      <div class="card"><div class="kicker">Broker Equity</div><div class="num">{html.escape(fmt_usd(coverage['broker_equity_usd']))}</div></div>
      <div class="card"><div class="kicker">Coverage Ratio</div><div class="num">{html.escape(fmt_pct(coverage['covered_ratio_pct']))}</div></div>
      <div class="card"><div class="kicker">Broker Unrealized P/L</div><div class="num">{html.escape(fmt_usd(coverage['unrealized_pl_usd']))}</div></div>
    </div>
    <h2>Sleeve Attribution</h2>
    {render_html_table(sleeve_display_rows(payload), [('sleeve', 'sleeve'), ('positions', 'positions'), ('net_mv', 'net_mv'), ('gross_mv', 'gross_mv'), ('pl', 'unrealized_pl'), ('exposure', 'total_exposure'), ('broker_pl', 'broker_pl_contrib')])}
    <h2>Theme Attribution</h2>
    {render_html_table(theme_display_rows(payload), [('theme', 'theme'), ('positions', 'positions'), ('net_mv', 'net_mv'), ('pl', 'unrealized_pl'), ('exposure', 'total_exposure'), ('broker_pl', 'broker_pl_contrib')])}
    <h2>Top Contributors</h2>
    {render_html_table(contribution_display_rows(payload['top_contributors']), [('name', 'name'), ('code', 'code'), ('sleeve', 'sleeve'), ('theme', 'theme'), ('mv', 'market_value'), ('pl', 'unrealized_pl'), ('broker_pl', 'broker_pl_contrib')])}
    <h2>Top Drags</h2>
    {render_html_table(contribution_display_rows(payload['top_drags']), [('name', 'name'), ('code', 'code'), ('sleeve', 'sleeve'), ('theme', 'theme'), ('mv', 'market_value'), ('pl', 'unrealized_pl'), ('broker_pl', 'broker_pl_contrib')])}
  </div>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate performance attribution snapshot.")
    parser.add_argument("--tag", default=datetime.now().strftime("%Y%m%dT%H%M%S"))
    args = parser.parse_args()

    payload = build_payload()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUT_DIR / f"performance_attribution_{args.tag}.json"
    md_path = OUT_DIR / f"performance_attribution_{args.tag}.md"
    html_path = OUT_DIR / f"performance_attribution_{args.tag}.html"

    latest_json = OUT_DIR / "latest.json"
    latest_md = OUT_DIR / "latest.md"
    latest_html = OUT_DIR / "latest.html"

    safe_payload = sanitize(payload)
    html_content = build_html(payload)
    json_path.write_text(json.dumps(safe_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(md_path, payload)
    html_path.write_text(html_content, encoding="utf-8")

    latest_json.write_text(json.dumps(safe_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    latest_md.write_text(md_path.read_text(encoding="utf-8"), encoding="utf-8")
    latest_html.write_text(html_content, encoding="utf-8")

    print("== Performance Attribution ==")
    print(f"JSON:   {json_path}")
    print(f"Report: {md_path}")
    print(f"HTML:   {html_path}")
    print(f"Broker equity coverage: {fmt_pct(payload['coverage']['covered_ratio_pct'])}")


if __name__ == "__main__":
    main()
