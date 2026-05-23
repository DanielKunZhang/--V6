#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
DESKTOP_ROOT = Path("/Users/zhangkun/Desktop/AI个人投资公司")
REPORT_ROOT = DESKTOP_ROOT / "报表输出" / "LATEST"
OUTPUT_DIR = ROOT / "backtest_results" / "ai_core_long_compounder_radar"
CONFIG_PATH = ROOT / "ai_core_long_compounder_config.json"
WATCHLIST_PATH = ROOT / "investment_screener" / "watchlist.json"


def read_json(path: Path) -> Any:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def to_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def valuation_status(price: float | None, floor: float | None, base: float | None, ceiling: float | None) -> tuple[str, str]:
    if base is None or base <= 0:
        return "NEEDS_VALUATION", "没有完成估值锚，先估值，不讨论加仓"
    if price is None or price <= 0:
        return "NO_PRICE", "没有可用价格，只能保留估值框架"
    ratio = price / base
    if floor and price <= floor * 1.10:
        return "HIGH_CONVICTION_ZONE", f"价格约为 V_floor 的 {price / floor:.2f}x"
    if ratio <= 0.80:
        return "CORE_BUILD_ZONE", f"价格约为 V_base 的 {ratio:.2f}x"
    if ratio <= 0.90:
        return "STARTER_CORE_ZONE", f"价格约为 V_base 的 {ratio:.2f}x"
    if ratio <= 1.00:
        return "WATCH_POSITION_ZONE", f"价格约为 V_base 的 {ratio:.2f}x"
    if ceiling and price >= ceiling * 0.90:
        return "OVER_BULL_CEILING", f"价格接近或高于 Bull ceiling，约为 V_base 的 {ratio:.2f}x"
    return "ABOVE_BASE_WAIT", f"价格高于 V_base，约为 V_base 的 {ratio:.2f}x"


def action_for(candidate: dict[str, Any], status: str, watch: dict[str, Any]) -> str:
    tier = str(candidate.get("trust_tier", "RESEARCH"))
    if status == "NEEDS_VALUATION":
        return "RESEARCH_VALUATION_FIRST"
    if status == "OVER_BULL_CEILING":
        return "DO_NOT_CHASE"
    if status == "ABOVE_BASE_WAIT":
        return "WATCH_WAIT_FOR_PULLBACK"
    if tier == "HIGH_TRUST_CORE" and status in {"WATCH_POSITION_ZONE", "STARTER_CORE_ZONE", "CORE_BUILD_ZONE", "HIGH_CONVICTION_ZONE"}:
        if "HOLD_NO_ADD" in str(watch.get("notes", "")):
            return "HOLD_NO_ADD_UNTIL_CONCENTRATION_OK"
        return "PULLBACK_REVIEW"
    if tier in {"HIGH_TRUST_CANDIDATE", "UPGRADE_CANDIDATE"} and status in {"STARTER_CORE_ZONE", "CORE_BUILD_ZONE", "HIGH_CONVICTION_ZONE"}:
        return "STARTER_OR_UPGRADE_REVIEW"
    if tier in {"HIGH_TRUST_CANDIDATE", "UPGRADE_CANDIDATE"} and status == "WATCH_POSITION_ZONE":
        return "WATCH_REVIEW_ONLY"
    return "RESEARCH_ONLY"


def build_rows(config: dict[str, Any], watchlist: dict[str, Any]) -> list[dict[str, Any]]:
    stocks = watchlist.get("stocks", {}) if isinstance(watchlist, dict) else {}
    rows: list[dict[str, Any]] = []
    for candidate in config.get("core_candidates", []):
        ticker = str(candidate.get("ticker", "")).upper()
        watch = stocks.get(ticker, {}) if isinstance(stocks, dict) else {}
        price = to_float(watch.get("last_price_at_analysis"))
        floor = to_float(watch.get("floor"))
        base = to_float(watch.get("v_base_geo_adjusted") or watch.get("v_base"))
        ceiling = to_float(watch.get("ceiling"))
        status, status_reason = valuation_status(price, floor, base, ceiling)
        action = action_for(candidate, status, watch)
        rows.append(
            {
                "ticker": ticker,
                "company": watch.get("company", ""),
                "pool": candidate.get("pool", ""),
                "trust_tier": candidate.get("trust_tier", ""),
                "thesis_trend": candidate.get("thesis_trend", ""),
                "valuation_status": status,
                "action": action,
                "last_price": price,
                "v_floor": floor,
                "v_base": base,
                "v_bull": ceiling,
                "status_reason": status_reason,
                "role": candidate.get("role", ""),
                "next_earnings": watch.get("next_earnings", ""),
                "last_analysis_date": watch.get("last_analysis_date", ""),
                "gates": "; ".join(candidate.get("gates", [])),
                "notes": str(watch.get("notes", ""))[:260],
            }
        )
    return rows


def sort_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tier_order = {
        "HIGH_TRUST_CORE": 0,
        "HIGH_TRUST_CANDIDATE": 1,
        "UPGRADE_CANDIDATE": 2,
        "RADAR_CANDIDATE": 3,
    }
    action_order = {
        "PULLBACK_REVIEW": 0,
        "STARTER_OR_UPGRADE_REVIEW": 1,
        "WATCH_REVIEW_ONLY": 2,
        "HOLD_NO_ADD_UNTIL_CONCENTRATION_OK": 3,
        "WATCH_WAIT_FOR_PULLBACK": 4,
        "DO_NOT_CHASE": 5,
        "RESEARCH_VALUATION_FIRST": 6,
        "RESEARCH_ONLY": 7,
    }
    return sorted(
        rows,
        key=lambda r: (
            tier_order.get(str(r.get("trust_tier", "")), 9),
            action_order.get(str(r.get("action", "")), 9),
            str(r.get("ticker", "")),
        ),
    )


def render_md(payload: dict[str, Any]) -> str:
    rows = payload["rows"]
    lines = [
        "# AI Core Long Compounder Radar",
        "",
        f"- 日期：`{payload['asof']}`",
        "- 定位：寻找 AI 大时代可长期逢低加仓的少数高信任复利候选。",
        "- 边界：周度研究雷达，不自动交易，不替代估值报告，不使用富途 K 线额度。",
        "",
        "## 当前动作摘要",
        "",
    ]
    action_counts: dict[str, int] = {}
    for row in rows:
        action_counts[str(row["action"])] = action_counts.get(str(row["action"]), 0) + 1
    for action, count in sorted(action_counts.items()):
        lines.append(f"- `{action}`：{count}")
    lines.extend(
        [
            "",
            "## 候选表",
            "",
            "| 标的 | 核心利润池 | 信任层级 | thesis | 估值状态 | 动作 | 价格/V_base | 关键门槛 |",
            "| --- | --- | --- | --- | --- | --- | ---: | --- |",
        ]
    )
    for row in rows:
        price = row.get("last_price")
        base = row.get("v_base")
        ratio = ""
        if isinstance(price, (int, float)) and isinstance(base, (int, float)) and base:
            ratio = f"{price:.2f}/{base:.2f} ({price/base:.2f}x)"
        gates = str(row.get("gates", "")).replace("|", "/")[:120]
        lines.append(
            f"| `{row.get('ticker', '')}` | {row.get('pool', '')} | `{row.get('trust_tier', '')}` | "
            f"`{row.get('thesis_trend', '')}` | `{row.get('valuation_status', '')}` | `{row.get('action', '')}` | "
            f"{ratio} | {gates} |"
        )
    lines.extend(
        [
            "",
            "## 使用规则",
            "",
            "- 只有 `PULLBACK_REVIEW` 或 `STARTER_OR_UPGRADE_REVIEW` 才进入人工加仓/升级复核。",
            "- `WATCH_WAIT_FOR_PULLBACK` 和 `DO_NOT_CHASE` 只等待，不因为好公司而追高。",
            "- `RESEARCH_VALUATION_FIRST` 必须先完成 AI-Core SOP v2.6 或对应框架估值。",
            "- NVDA 超过核心仓的部分仍按趋势增强处理，不自动视为永久底仓。",
            "- 每次动作必须回到主仓风险预算和 opportunity cost，不和 V6AB/A股 Radar 仓位混用。",
        ]
    )
    return "\n".join(lines) + "\n"


def _fmt_money(value: Any) -> str:
    if isinstance(value, (int, float)):
        return f"${value:,.2f}"
    return "-"


def _escape(value: Any) -> str:
    import html

    return html.escape(str(value if value is not None else ""))


def render_html(payload: dict[str, Any]) -> str:
    rows = payload["rows"]
    action_labels = {
        "PULLBACK_REVIEW": "可复核",
        "STARTER_OR_UPGRADE_REVIEW": "可复核",
        "WATCH_REVIEW_ONLY": "只复核",
        "HOLD_NO_ADD_UNTIL_CONCENTRATION_OK": "持有不加",
        "WATCH_WAIT_FOR_PULLBACK": "等回撤",
        "DO_NOT_CHASE": "不追高",
        "RESEARCH_VALUATION_FIRST": "先估值",
        "RESEARCH_ONLY": "只研究",
    }
    action_classes = {
        "PULLBACK_REVIEW": "good",
        "STARTER_OR_UPGRADE_REVIEW": "good",
        "WATCH_REVIEW_ONLY": "watch",
        "HOLD_NO_ADD_UNTIL_CONCENTRATION_OK": "hold",
        "WATCH_WAIT_FOR_PULLBACK": "wait",
        "DO_NOT_CHASE": "bad",
        "RESEARCH_VALUATION_FIRST": "research",
        "RESEARCH_ONLY": "research",
    }
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(str(row.get("action", "")), []).append(row)

    cards = []
    for action in [
        "PULLBACK_REVIEW",
        "STARTER_OR_UPGRADE_REVIEW",
        "HOLD_NO_ADD_UNTIL_CONCENTRATION_OK",
        "WATCH_WAIT_FOR_PULLBACK",
        "DO_NOT_CHASE",
        "RESEARCH_VALUATION_FIRST",
        "RESEARCH_ONLY",
    ]:
        group = groups.get(action, [])
        if not group:
            continue
        tickers = " / ".join(str(r.get("ticker", "")) for r in group)
        cards.append(
            f"<div class='summary-card {action_classes.get(action, 'research')}'>"
            f"<div class='summary-label'>{_escape(action_labels.get(action, action))}</div>"
            f"<div class='summary-count'>{len(group)}</div>"
            f"<div class='summary-tickers'>{_escape(tickers)}</div>"
            f"</div>"
        )

    row_html = []
    for row in rows:
        action = str(row.get("action", ""))
        price = row.get("last_price")
        base = row.get("v_base")
        ratio = "-"
        if isinstance(price, (int, float)) and isinstance(base, (int, float)) and base:
            ratio = f"{price / base:.2f}x"
        gates = [g.strip() for g in str(row.get("gates", "")).split(";") if g.strip()]
        gate_html = "".join(f"<span>{_escape(g)}</span>" for g in gates[:5]) or "<span>待补</span>"
        row_html.append(
            f"<tr>"
            f"<td><strong>{_escape(row.get('ticker', ''))}</strong><div class='company'>{_escape(row.get('company', ''))}</div></td>"
            f"<td>{_escape(row.get('pool', ''))}</td>"
            f"<td><span class='pill tier'>{_escape(row.get('trust_tier', ''))}</span><br><span class='trend'>{_escape(row.get('thesis_trend', ''))}</span></td>"
            f"<td><span class='pill {action_classes.get(action, 'research')}'>{_escape(action_labels.get(action, action))}</span><div class='sub'>{_escape(row.get('valuation_status', ''))}</div></td>"
            f"<td><strong>{_fmt_money(price)}</strong><div class='sub'>V_base {_fmt_money(base)} / {ratio}</div></td>"
            f"<td><div class='gates'>{gate_html}</div></td>"
            f"</tr>"
        )

    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<style>
body {{
  margin: 0;
  padding: 0;
  background: #f5f7fb;
  color: #18212f;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif;
}}
.wrap {{
  max-width: 1120px;
  margin: 0 auto;
  padding: 28px 22px 36px;
}}
.header {{
  background: #ffffff;
  border: 1px solid #dfe5ef;
  border-radius: 8px;
  padding: 22px 24px;
}}
h1 {{
  margin: 0 0 8px;
  font-size: 24px;
  letter-spacing: 0;
}}
.meta {{
  color: #5d6b82;
  font-size: 14px;
  line-height: 1.6;
}}
.summary {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 12px;
  margin: 16px 0;
}}
.summary-card {{
  background: #ffffff;
  border: 1px solid #dfe5ef;
  border-left: 5px solid #8090a8;
  border-radius: 8px;
  padding: 14px;
}}
.summary-card.good {{ border-left-color: #16845b; }}
.summary-card.hold {{ border-left-color: #4d6fd6; }}
.summary-card.wait {{ border-left-color: #b7791f; }}
.summary-card.bad {{ border-left-color: #c2410c; }}
.summary-card.research {{ border-left-color: #6b7280; }}
.summary-label {{ color: #526174; font-size: 13px; }}
.summary-count {{ font-size: 28px; font-weight: 750; margin-top: 4px; }}
.summary-tickers {{ color: #27364a; font-size: 13px; margin-top: 4px; line-height: 1.35; }}
.section {{
  background: #ffffff;
  border: 1px solid #dfe5ef;
  border-radius: 8px;
  overflow: hidden;
}}
table {{
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
}}
th {{
  background: #eef3f9;
  color: #35445a;
  font-size: 12px;
  text-align: left;
  padding: 10px 12px;
}}
td {{
  border-top: 1px solid #e5ebf3;
  padding: 12px;
  vertical-align: top;
  font-size: 13px;
  line-height: 1.45;
}}
th:nth-child(1), td:nth-child(1) {{ width: 110px; }}
th:nth-child(2), td:nth-child(2) {{ width: 230px; }}
th:nth-child(3), td:nth-child(3) {{ width: 160px; }}
th:nth-child(4), td:nth-child(4) {{ width: 170px; }}
th:nth-child(5), td:nth-child(5) {{ width: 135px; }}
.company, .sub, .trend {{ color: #66758a; font-size: 12px; margin-top: 3px; }}
.pill {{
  display: inline-block;
  border-radius: 999px;
  padding: 3px 8px;
  font-size: 12px;
  font-weight: 650;
  background: #e8edf5;
  color: #344256;
}}
.pill.good {{ background: #dff5ea; color: #0d6b49; }}
.pill.hold {{ background: #e3eafd; color: #2b4bb3; }}
.pill.wait {{ background: #fff3d7; color: #8a5a00; }}
.pill.bad {{ background: #ffe4d8; color: #9a3412; }}
.pill.research {{ background: #edf0f4; color: #4b5563; }}
.gates span {{
  display: inline-block;
  background: #f4f7fb;
  border: 1px solid #e1e7f0;
  border-radius: 6px;
  padding: 3px 6px;
  margin: 0 5px 5px 0;
  color: #435269;
  font-size: 12px;
}}
.rules {{
  margin-top: 14px;
  background: #ffffff;
  border: 1px solid #dfe5ef;
  border-radius: 8px;
  padding: 16px 20px;
  color: #334155;
  font-size: 13px;
  line-height: 1.7;
}}
.rules ul {{ margin: 8px 0 0 18px; padding: 0; }}
</style>
</head>
<body>
<div class="wrap">
  <div class="header">
    <h1>AI Core Long Compounder Radar</h1>
    <div class="meta">日期：{_escape(payload['asof'])}</div>
    <div class="meta">目标：寻找 AI 大时代少数可长期逢低加仓的高信任复利股。</div>
    <div class="meta">边界：周度研究雷达，不自动交易，不替代估值报告，不使用富途 K 线额度。</div>
  </div>
  <div class="summary">
    {''.join(cards)}
  </div>
  <div class="section">
    <table>
      <thead>
        <tr>
          <th>标的</th>
          <th>核心利润池</th>
          <th>信任/趋势</th>
          <th>动作/状态</th>
          <th>价格锚</th>
          <th>关键门槛</th>
        </tr>
      </thead>
      <tbody>
        {''.join(row_html)}
      </tbody>
    </table>
  </div>
  <div class="rules">
    <strong>使用规则</strong>
    <ul>
      <li>只有“可复核”才进入人工加仓/升级复核。</li>
      <li>“等回撤”和“不追高”只等待，不因为好公司而追高。</li>
      <li>“先估值”必须先完成 AI-Core SOP v2.6 或对应框架估值。</li>
      <li>NVDA 超过核心仓的部分仍按趋势增强处理，不自动视为永久底仓。</li>
      <li>每次动作必须回到主仓风险预算和 opportunity cost，不和 V6AB/A股 Radar 仓位混用。</li>
    </ul>
  </div>
</div>
</body>
</html>"""


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build AI-era long compounder weekly radar.")
    parser.add_argument("--asof", default=datetime.now().date().isoformat())
    parser.add_argument("--config", default=str(CONFIG_PATH))
    parser.add_argument("--watchlist", default=str(WATCHLIST_PATH))
    args = parser.parse_args()

    config = read_json(Path(args.config))
    watchlist = read_json(Path(args.watchlist))
    rows = sort_rows(build_rows(config, watchlist))
    payload = {
        "version": config.get("version", "ai_core_long_compounder_radar_v1"),
        "asof": args.asof,
        "row_count": len(rows),
        "principle": config.get("principle", ""),
        "rows": rows,
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    json_text = json.dumps(payload, ensure_ascii=False, indent=2)
    md = render_md(payload)
    html = render_html(payload)
    (OUTPUT_DIR / "latest.json").write_text(json_text, encoding="utf-8")
    (OUTPUT_DIR / "latest.md").write_text(md, encoding="utf-8")
    (OUTPUT_DIR / "latest.html").write_text(html, encoding="utf-8")
    write_csv(OUTPUT_DIR / "latest.csv", rows)
    (REPORT_ROOT / "AI_Core_Long_Compounder_Radar_LATEST.json").write_text(json_text, encoding="utf-8")
    (REPORT_ROOT / "AI_Core_Long_Compounder_Radar_LATEST.md").write_text(md, encoding="utf-8")
    (REPORT_ROOT / "AI_Core_Long_Compounder_Radar_LATEST.html").write_text(html, encoding="utf-8")
    write_csv(REPORT_ROOT / "AI_Core_Long_Compounder_Radar_LATEST.csv", rows)
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
