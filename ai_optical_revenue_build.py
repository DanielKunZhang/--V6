#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
DESKTOP_ROOT = Path("/Users/zhangkun/Desktop/AI个人投资公司")
REPORT_ROOT = DESKTOP_ROOT / "报表输出" / "LATEST"
OUTPUT_DIR = ROOT / "backtest_results" / "ai_optical_revenue_build"
CONFIG_PATH = ROOT / "ai_optical_revenue_build_config.json"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def scenario_values(values: list[float], multiplier: float) -> list[float]:
    return [round(float(v) * multiplier, 1) for v in values]


def build_payload(config: dict[str, Any], ticker: str, asof: str) -> dict[str, Any]:
    company = config["companies"][ticker]
    quarters = company["quarters"]
    scenarios = company.get("scenario_modifiers", {})
    rows: list[dict[str, Any]] = []
    scenario_totals = {
        name: [0.0 for _ in quarters]
        for name in ["bear", "base", "upside"]
    }
    segment_totals: dict[str, dict[str, list[float]]] = {}

    for segment in company["segments"]:
        segment_name = segment["name"]
        segment_totals[segment_name] = {
            name: [0.0 for _ in quarters]
            for name in ["bear", "base", "upside"]
        }
        for line in segment["lines"]:
            line_name = line["name"]
            base_values = [float(v) for v in line["values"]]
            line_payload: dict[str, Any] = {
                "segment": segment_name,
                "line": line_name,
                "driver": line.get("driver", ""),
            }
            for scenario in ["bear", "base", "upside"]:
                multiplier = float(scenarios.get(scenario, {}).get("line_multipliers", {}).get(line_name, 1.0))
                values = scenario_values(base_values, multiplier)
                line_payload[scenario] = values
                for idx, value in enumerate(values):
                    scenario_totals[scenario][idx] += value
                    segment_totals[segment_name][scenario][idx] += value
            rows.append(line_payload)

    mix = []
    ai_core_lines = {
        "200G EML laser chips",
        "CPO ultra-high-power lasers",
        "1.6T cloud transceivers",
        "OCS (R300 + R-series)",
    }
    for scenario in ["bear", "base", "upside"]:
        ai_values = [0.0 for _ in quarters]
        for row in rows:
            if row["line"] not in ai_core_lines:
                continue
            for idx, value in enumerate(row[scenario]):
                ai_values[idx] += value
        mix.append(
            {
                "scenario": scenario,
                "ai_core_revenue": ai_values,
                "total_revenue": scenario_totals[scenario],
                "ai_core_mix": [
                    round(ai_values[idx] / scenario_totals[scenario][idx], 4) if scenario_totals[scenario][idx] else 0
                    for idx in range(len(quarters))
                ],
            }
        )

    return {
        "asof": asof,
        "ticker": ticker,
        "company": company,
        "quarters": quarters,
        "rows": rows,
        "segment_totals": segment_totals,
        "scenario_totals": scenario_totals,
        "mix": mix,
        "version": config.get("version", ""),
    }


def write_csv(path: Path, payload: dict[str, Any]) -> None:
    quarters = payload["quarters"]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["scenario", "segment", "line", *quarters, "driver"])
        for row in payload["rows"]:
            for scenario in ["bear", "base", "upside"]:
                writer.writerow([scenario, row["segment"], row["line"], *row[scenario], row["driver"]])


def fmt_money(value: float) -> str:
    return f"${value:,.0f}"


def render_md(payload: dict[str, Any]) -> str:
    company = payload["company"]
    quarters = payload["quarters"]
    lines = [
        f"# {payload['ticker']} AI Optical Revenue Build v1",
        "",
        f"- 日期：`{payload['asof']}`",
        f"- 公司：{company['company']}",
        f"- 主题：{company['theme']}",
        f"- 单位：{company['unit']}",
        f"- 初始动作：`{company['initial_decision']}`",
        f"- 系统动作：{company['system_action']}",
        "",
        "## 重要边界",
        "",
        f"- {company['source_note']}",
        "- 这是第一层 revenue build，不是完整估值模型。",
        "- 下一层必须接毛利率、Opex、FCF、净现金/股数、估值倍数或 DCF。",
        "- 当前不能替代 V6AB 模拟盘，也不能作为人工追高理由。",
        "",
        "## 情景总收入",
        "",
        "| 情景 | " + " | ".join(quarters) + " |",
        "| --- | " + " | ".join(["---:"] * len(quarters)) + " |",
    ]
    for scenario in ["bear", "base", "upside"]:
        values = " | ".join(fmt_money(v) for v in payload["scenario_totals"][scenario])
        lines.append(f"| `{scenario}` | {values} |")

    lines.extend(["", "## AI 核心收入占比", "", "| 情景 | " + " | ".join(quarters) + " |", "| --- | " + " | ".join(["---:"] * len(quarters)) + " |"])
    for item in payload["mix"]:
        values = " | ".join(f"{v:.1%}" for v in item["ai_core_mix"])
        lines.append(f"| `{item['scenario']}` | {values} |")

    lines.extend(["", "## Base Case 业务线", "", "| Segment | Line | " + " | ".join(quarters) + " | Driver |", "| --- | --- | " + " | ".join(["---:"] * len(quarters)) + " | --- |"])
    for row in payload["rows"]:
        values = " | ".join(fmt_money(v) for v in row["base"])
        driver = str(row["driver"]).replace("|", "/")
        lines.append(f"| {row['segment']} | {row['line']} | {values} | {driver} |")

    lines.extend(["", "## 证据 Gate", ""])
    for gate in company.get("evidence_gates", []):
        lines.append(f"- {gate}")
    return "\n".join(lines) + "\n"


def esc(value: Any) -> str:
    import html

    return html.escape(str(value if value is not None else ""))


def render_html(payload: dict[str, Any]) -> str:
    company = payload["company"]
    quarters = payload["quarters"]

    total_rows = []
    for scenario in ["bear", "base", "upside"]:
        cells = "".join(f"<td>{esc(fmt_money(v))}</td>" for v in payload["scenario_totals"][scenario])
        total_rows.append(f"<tr><th>{esc(scenario.upper())}</th>{cells}</tr>")

    mix_rows = []
    for item in payload["mix"]:
        cells = "".join(f"<td>{v:.1%}</td>" for v in item["ai_core_mix"])
        mix_rows.append(f"<tr><th>{esc(item['scenario'].upper())}</th>{cells}</tr>")

    line_rows = []
    for row in payload["rows"]:
        cells = "".join(f"<td>{esc(fmt_money(v))}</td>" for v in row["base"])
        line_rows.append(
            f"<tr><td>{esc(row['segment'])}</td><td>{esc(row['line'])}</td>{cells}<td>{esc(row['driver'])}</td></tr>"
        )

    header = "".join(f"<th>{esc(q)}</th>" for q in quarters)
    gates = "".join(f"<li>{esc(gate)}</li>" for gate in company.get("evidence_gates", []))
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>{esc(payload['ticker'])} AI Optical Revenue Build</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 0; background: #f6f7f9; color: #18212f; }}
main {{ max-width: 1180px; margin: 0 auto; padding: 28px; }}
h1 {{ margin: 0 0 8px; font-size: 28px; }}
h2 {{ margin-top: 28px; font-size: 19px; }}
.panel {{ background: #fff; border: 1px solid #dfe3ea; border-radius: 8px; padding: 18px; margin-top: 16px; }}
.meta {{ color: #5b6675; line-height: 1.6; }}
.warning {{ border-left: 4px solid #b7791f; background: #fff8e8; padding: 12px 14px; margin-top: 14px; }}
table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
th, td {{ border-bottom: 1px solid #e5e8ef; padding: 9px 8px; text-align: right; vertical-align: top; }}
th:first-child, td:first-child, th:nth-child(2), td:nth-child(2), td:last-child {{ text-align: left; }}
thead th {{ background: #173b57; color: white; position: sticky; top: 0; }}
tbody th {{ text-align: left; }}
.driver {{ width: 34%; }}
ul {{ line-height: 1.7; }}
</style>
</head>
<body>
<main>
<h1>{esc(payload['ticker'])} AI Optical Revenue Build v1</h1>
<div class="meta">日期：{esc(payload['asof'])} · 公司：{esc(company['company'])} · 主题：{esc(company['theme'])} · 单位：{esc(company['unit'])}</div>
<div class="warning">这是第一层 revenue build，不是完整估值模型。当前动作：<b>{esc(company['initial_decision'])}</b>。必须完成主源验证、毛利/FCF层和估值纪律后，才允许进入交易复核。</div>

<section class="panel">
<h2>情景总收入</h2>
<table><thead><tr><th>Scenario</th>{header}</tr></thead><tbody>{''.join(total_rows)}</tbody></table>
</section>

<section class="panel">
<h2>AI 核心收入占比</h2>
<table><thead><tr><th>Scenario</th>{header}</tr></thead><tbody>{''.join(mix_rows)}</tbody></table>
</section>

<section class="panel">
<h2>Base Case 业务线</h2>
<table><thead><tr><th>Segment</th><th>Line</th>{header}<th class="driver">Driver</th></tr></thead><tbody>{''.join(line_rows)}</tbody></table>
</section>

<section class="panel">
<h2>证据 Gate</h2>
<ul>{gates}</ul>
<p class="meta">{esc(company['source_note'])}</p>
</section>
</main>
</body>
</html>
"""


def write_outputs(payload: dict[str, Any]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    ticker = payload["ticker"]
    files = {
        OUTPUT_DIR / "latest.json": json.dumps(payload, ensure_ascii=False, indent=2),
        OUTPUT_DIR / "latest.md": render_md(payload),
        OUTPUT_DIR / "latest.html": render_html(payload),
        REPORT_ROOT / f"{ticker}_AI_Optical_Revenue_Build_LATEST.json": json.dumps(payload, ensure_ascii=False, indent=2),
        REPORT_ROOT / f"{ticker}_AI_Optical_Revenue_Build_LATEST.md": render_md(payload),
        REPORT_ROOT / f"{ticker}_AI_Optical_Revenue_Build_LATEST.html": render_html(payload),
    }
    for path, content in files.items():
        path.write_text(content, encoding="utf-8")
    write_csv(OUTPUT_DIR / "latest.csv", payload)
    write_csv(REPORT_ROOT / f"{ticker}_AI_Optical_Revenue_Build_LATEST.csv", payload)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", default="LITE")
    parser.add_argument("--asof", required=True)
    args = parser.parse_args()
    config = read_json(CONFIG_PATH)
    payload = build_payload(config, args.ticker.upper(), args.asof)
    write_outputs(payload)
    print(render_md(payload))


if __name__ == "__main__":
    main()
