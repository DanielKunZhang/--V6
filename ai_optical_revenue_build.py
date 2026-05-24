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
                "evidence_level": line.get("evidence_level", "UNCLASSIFIED"),
                "evidence_note": line.get("evidence_note", ""),
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

    financials = build_financial_layer(company, quarters, scenario_totals)
    validation = build_validation(company, quarters, scenario_totals, segment_totals)
    decision = build_decision(company, financials)

    return {
        "asof": asof,
        "ticker": ticker,
        "company": company,
        "quarters": quarters,
        "rows": rows,
        "segment_totals": segment_totals,
        "scenario_totals": scenario_totals,
        "mix": mix,
        "financials": financials,
        "validation": validation,
        "decision": decision,
        "version": config.get("version", ""),
    }


def build_decision(company: dict[str, Any], financials: dict[str, Any]) -> dict[str, Any]:
    current = company.get("current_market", {})
    initial_decision = company.get("initial_decision", "")
    price = float(current.get("price", 0) or 0)
    bear_value = float(financials["bear"].get("value_per_share", 0))
    base_value = float(financials["base"].get("value_per_share", 0))
    upside_value = float(financials["upside"].get("value_per_share", 0))
    if not price:
        return {
            "action": "NO_PRICE_RESEARCH_ONLY",
            "reason": "No current price anchor.",
            "price": price,
            "base_discount": None,
            "upside_dependency": None,
        }
    base_discount = price / base_value if base_value else None
    upside_dependency = max(0.0, (price - bear_value) / max(upside_value - bear_value, 1.0))
    if initial_decision == "HIGH_BETA_RESEARCH_ONLY":
        if price > base_value:
            action = "DO_NOT_CHASE"
            reason = "High-beta optical name with price above rough base value; wait for Q2/Q3 proof, dilution clarity, customer risk review, and better entry."
        else:
            action = "HIGH_BETA_WATCH_ONLY"
            reason = "High-beta optical name cannot enter pilot from valuation alone; require Q2/Q3 proof, dilution clarity, customer risk review, and crowding reset."
    elif price > base_value:
        action = "DO_NOT_CHASE"
        reason = "Price is above rough base value; revenue upside may be real but common stock has no base-case margin of safety."
    elif upside_dependency > 0.35:
        action = "NEEDS_SOURCE_VALIDATION"
        reason = "Price already depends materially on AI upside; require source validation before any pilot review."
    elif price <= base_value * 0.8:
        action = "PILOT_REVIEW_AFTER_GATES"
        reason = "Price is below rough base value, but only after evidence gates pass and crowding is acceptable."
    else:
        action = "WATCH_WAIT_FOR_PULLBACK"
        reason = "Model suggests upside, but current setup still needs evidence and better entry discipline."
    return {
        "action": action,
        "reason": reason,
        "price": price,
        "price_date": current.get("price_date", ""),
        "price_source": current.get("source", ""),
        "bear_value": bear_value,
        "base_value": base_value,
        "upside_value": upside_value,
        "base_discount": base_discount,
        "upside_dependency": upside_dependency,
    }


def build_financial_layer(
    company: dict[str, Any],
    quarters: list[str],
    scenario_totals: dict[str, list[float]],
) -> dict[str, Any]:
    layer = company.get("financial_layer", {})
    out: dict[str, Any] = {}
    for scenario in ["bear", "base", "upside"]:
        assumptions = layer.get(scenario, {})
        revenue = scenario_totals[scenario]
        gross_margin = [float(v) for v in assumptions.get("gross_margin_pct", [0.0] * len(quarters))]
        operating_margin = [float(v) for v in assumptions.get("operating_margin_pct", [0.0] * len(quarters))]
        fcf_margin = [float(v) for v in assumptions.get("fcf_margin_pct", [0.0] * len(quarters))]
        gross_profit = [round(revenue[idx] * gross_margin[idx], 1) for idx in range(len(quarters))]
        operating_income = [round(revenue[idx] * operating_margin[idx], 1) for idx in range(len(quarters))]
        fcf = [round(revenue[idx] * fcf_margin[idx], 1) for idx in range(len(quarters))]
        annualized_exit_fcf = fcf[-1] * 4
        fcf_multiple = float(layer.get("valuation_multiples", {}).get(f"{scenario}_fcf_multiple", 0))
        net_cash = float(layer.get("net_cash_m", 0))
        shares = float(layer.get("diluted_shares_m", 0))
        equity_value = annualized_exit_fcf * fcf_multiple + net_cash
        value_per_share = equity_value / shares if shares else 0
        out[scenario] = {
            "gross_margin_pct": gross_margin,
            "operating_margin_pct": operating_margin,
            "fcf_margin_pct": fcf_margin,
            "gross_profit": gross_profit,
            "operating_income": operating_income,
            "fcf": fcf,
            "annualized_exit_fcf": annualized_exit_fcf,
            "fcf_multiple": fcf_multiple,
            "net_cash_m": net_cash,
            "diluted_shares_m": shares,
            "equity_value_m": equity_value,
            "value_per_share": value_per_share,
        }
    return out


def build_validation(
    company: dict[str, Any],
    quarters: list[str],
    scenario_totals: dict[str, list[float]],
    segment_totals: dict[str, dict[str, list[float]]],
) -> list[dict[str, Any]]:
    calibration = company.get("official_calibration", {})
    checks: list[dict[str, Any]] = []
    for quarter, facts in calibration.items():
        if quarter not in quarters:
            continue
        idx = quarters.index(quarter)
        if "total_revenue" in facts:
            model = scenario_totals["base"][idx]
            actual = float(facts["total_revenue"])
            checks.append(
                {
                    "quarter": quarter,
                    "metric": "total_revenue",
                    "model": model,
                    "official": actual,
                    "status": "PASS" if abs(model - actual) <= 1.0 else "CHECK",
                    "note": "Base model should reconcile to official actual quarter.",
                }
            )
        for segment_key, segment_name in [
            ("components", "Components"),
            ("systems", "Systems"),
            ("datacenter_communications", "Datacenter & Communications"),
            ("industrial", "Industrial"),
        ]:
            if segment_key not in facts or segment_name not in segment_totals:
                continue
            model = segment_totals[segment_name]["base"][idx]
            actual = float(facts[segment_key])
            checks.append(
                {
                    "quarter": quarter,
                    "metric": segment_key,
                    "model": model,
                    "official": actual,
                    "status": "PASS" if abs(model - actual) <= 1.0 else "CHECK",
                    "note": "Segment subtotal reconciliation.",
                }
            )
        if "revenue_guidance_low" in facts and "revenue_guidance_high" in facts:
            model = scenario_totals["base"][idx]
            low = float(facts["revenue_guidance_low"])
            high = float(facts["revenue_guidance_high"])
            checks.append(
                {
                    "quarter": quarter,
                    "metric": "revenue_guidance_range",
                    "model": model,
                    "official": f"{low:.0f}-{high:.0f}",
                    "status": "PASS" if low <= model <= high else "CHECK",
                    "note": "Base model should sit inside official guidance range.",
                }
            )
    return checks


def write_csv(path: Path, payload: dict[str, Any]) -> None:
    quarters = payload["quarters"]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["scenario", "segment", "line", "evidence_level", "evidence_note", *quarters, "driver"])
        for row in payload["rows"]:
            for scenario in ["bear", "base", "upside"]:
                writer.writerow([scenario, row["segment"], row["line"], row["evidence_level"], row["evidence_note"], *row[scenario], row["driver"]])


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

    lines.extend(
        [
            "",
            "## 主源校准",
            "",
            "| Quarter | Metric | Model | Official / Guide | Status | Note |",
            "| --- | --- | ---: | ---: | --- | --- |",
        ]
    )
    for check in payload.get("validation", []):
        model = check["model"]
        model_text = fmt_money(model) if isinstance(model, (int, float)) else str(model)
        official = check["official"]
        official_text = fmt_money(official) if isinstance(official, (int, float)) else str(official)
        lines.append(
            f"| {check['quarter']} | {check['metric']} | {model_text} | {official_text} | `{check['status']}` | {check['note']} |"
        )

    lines.extend(["", "## AI 核心收入占比", "", "| 情景 | " + " | ".join(quarters) + " |", "| --- | " + " | ".join(["---:"] * len(quarters)) + " |"])
    for item in payload["mix"]:
        values = " | ".join(f"{v:.1%}" for v in item["ai_core_mix"])
        lines.append(f"| `{item['scenario']}` | {values} |")

    lines.extend(
        [
            "",
        "## 简化财务层 / 定价锚",
            "",
            "| 情景 | Exit季度收入 | Exit FCF margin | 年化Exit FCF | FCF倍数 | 净现金 | 股数 | 粗略价值/股 |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for scenario in ["bear", "base", "upside"]:
        fin = payload["financials"][scenario]
        lines.append(
            f"| `{scenario}` | {fmt_money(payload['scenario_totals'][scenario][-1])} | "
            f"{fin['fcf_margin_pct'][-1]:.1%} | {fmt_money(fin['annualized_exit_fcf'])} | "
            f"{fin['fcf_multiple']:.1f}x | {fmt_money(fin['net_cash_m'])} | "
            f"{fin['diluted_shares_m']:.1f} | ${fin['value_per_share']:.0f} |"
        )

    decision = payload["decision"]
    base_discount = decision.get("base_discount")
    upside_dependency = decision.get("upside_dependency")
    lines.extend(
        [
            "",
            "## 动作判定",
            "",
            f"- 当前价格锚：`${decision['price']:.2f}`（{decision.get('price_date', '')}；{decision.get('price_source', '')}）",
            f"- Bear/Base/Upside 粗略价值：`${decision['bear_value']:.0f}` / `${decision['base_value']:.0f}` / `${decision['upside_value']:.0f}`",
            f"- Price/Base：`{base_discount:.2f}x`" if isinstance(base_discount, float) else "- Price/Base：`NA`",
            f"- Upside dependency：`{upside_dependency:.1%}`" if isinstance(upside_dependency, float) else "- Upside dependency：`NA`",
            f"- 动作：`{decision['action']}`",
            f"- 原因：{decision['reason']}",
        ]
    )

    lines.extend(["", "## Base Case 业务线", "", "| Segment | Line | Evidence | " + " | ".join(quarters) + " | Driver |", "| --- | --- | --- | " + " | ".join(["---:"] * len(quarters)) + " | --- |"])
    for row in payload["rows"]:
        values = " | ".join(fmt_money(v) for v in row["base"])
        driver = str(row["driver"]).replace("|", "/")
        evidence = f"`{row.get('evidence_level', '')}`"
        lines.append(f"| {row['segment']} | {row['line']} | {evidence} | {values} | {driver} |")

    lines.extend(["", "## 证据 Gate", ""])
    for gate in company.get("evidence_gates", []):
        lines.append(f"- {gate}")
    audit = company.get("external_report_audit")
    if isinstance(audit, dict):
        lines.extend(
            [
                "",
                "## 外部高弹性报告反向审计",
                "",
                f"- 来源：{audit.get('source', '')}",
                f"- 状态：`{audit.get('status', '')}`",
                f"- 系统使用：{audit.get('system_use', '')}",
                "",
                "### 外部报告目标价",
                "",
            ]
        )
        for key, value in audit.get("reported_targets", {}).items():
            lines.append(f"- `{key}`: `${float(value):,.0f}`")
        lines.extend(["", "### 可吸收点", ""])
        for point in audit.get("useful_points", []):
            lines.append(f"- {point}")
        lines.extend(["", "### 拒绝吸收", ""])
        for point in audit.get("rejected_points", []):
            lines.append(f"- {point}")
    lines.extend(["", "## 主源", ""])
    for source in company.get("official_sources", []):
        lines.append(f"- {source['name']}: {source['url']}")
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

    validation_rows = []
    for check in payload.get("validation", []):
        model = check["model"]
        model_text = fmt_money(model) if isinstance(model, (int, float)) else str(model)
        official = check["official"]
        official_text = fmt_money(official) if isinstance(official, (int, float)) else str(official)
        validation_rows.append(
            "<tr>"
            f"<td>{esc(check['quarter'])}</td>"
            f"<td>{esc(check['metric'])}</td>"
            f"<td>{esc(model_text)}</td>"
            f"<td>{esc(official_text)}</td>"
            f"<td><b>{esc(check['status'])}</b></td>"
            f"<td>{esc(check['note'])}</td>"
            "</tr>"
        )

    decision = payload["decision"]
    base_discount = decision.get("base_discount")
    upside_dependency = decision.get("upside_dependency")
    decision_html = (
        f"<p><b>Action:</b> {esc(decision['action'])}</p>"
        f"<p><b>Price:</b> ${decision['price']:.2f} · "
        f"<b>Bear/Base/Upside:</b> ${decision['bear_value']:.0f} / ${decision['base_value']:.0f} / ${decision['upside_value']:.0f}</p>"
        f"<p><b>Price/Base:</b> {base_discount:.2f}x · <b>Upside dependency:</b> {upside_dependency:.1%}</p>"
        f"<p class='meta'>{esc(decision['reason'])}</p>"
    )

    financial_rows = []
    for scenario in ["bear", "base", "upside"]:
        fin = payload["financials"][scenario]
        financial_rows.append(
            "<tr>"
            f"<th>{esc(scenario.upper())}</th>"
            f"<td>{esc(fmt_money(payload['scenario_totals'][scenario][-1]))}</td>"
            f"<td>{fin['fcf_margin_pct'][-1]:.1%}</td>"
            f"<td>{esc(fmt_money(fin['annualized_exit_fcf']))}</td>"
            f"<td>{fin['fcf_multiple']:.1f}x</td>"
            f"<td>{esc(fmt_money(fin['net_cash_m']))}</td>"
            f"<td>{fin['diluted_shares_m']:.1f}</td>"
            f"<td><b>${fin['value_per_share']:.0f}</b></td>"
            "</tr>"
        )

    line_rows = []
    for row in payload["rows"]:
        cells = "".join(f"<td>{esc(fmt_money(v))}</td>" for v in row["base"])
        line_rows.append(
            f"<tr><td>{esc(row['segment'])}</td><td>{esc(row['line'])}</td><td>{esc(row.get('evidence_level', ''))}</td>{cells}<td>{esc(row['driver'])}</td></tr>"
        )

    header = "".join(f"<th>{esc(q)}</th>" for q in quarters)
    gates = "".join(f"<li>{esc(gate)}</li>" for gate in company.get("evidence_gates", []))
    audit = company.get("external_report_audit")
    audit_html = ""
    if isinstance(audit, dict):
        targets = "".join(
            f"<tr><td>{esc(key)}</td><td>{esc(fmt_money(float(value)))}</td></tr>"
            for key, value in audit.get("reported_targets", {}).items()
        )
        useful = "".join(f"<li>{esc(point)}</li>" for point in audit.get("useful_points", []))
        rejected = "".join(f"<li>{esc(point)}</li>" for point in audit.get("rejected_points", []))
        audit_html = f"""
<section class="panel">
<h2>外部高弹性报告反向审计</h2>
<p><b>Status:</b> {esc(audit.get('status', ''))}</p>
<p class="meta">来源：{esc(audit.get('source', ''))}</p>
<p class="meta">{esc(audit.get('system_use', ''))}</p>
<table><thead><tr><th>Scenario</th><th>External target</th></tr></thead><tbody>{targets}</tbody></table>
<h3>可吸收点</h3>
<ul>{useful}</ul>
<h3>拒绝吸收</h3>
<ul>{rejected}</ul>
</section>
"""
    sources = "".join(
        f"<li><a href='{esc(source['url'])}'>{esc(source['name'])}</a> - {esc(source['use'])}</li>"
        for source in company.get("official_sources", [])
    )
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
<h2>主源校准</h2>
<table><thead><tr><th>Quarter</th><th>Metric</th><th>Model</th><th>Official / Guide</th><th>Status</th><th class="driver">Note</th></tr></thead><tbody>{''.join(validation_rows)}</tbody></table>
</section>

<section class="panel">
<h2>简化财务层 / 定价锚</h2>
<table><thead><tr><th>Scenario</th><th>Exit季度收入</th><th>Exit FCF margin</th><th>年化Exit FCF</th><th>FCF倍数</th><th>净现金</th><th>股数</th><th>粗略价值/股</th></tr></thead><tbody>{''.join(financial_rows)}</tbody></table>
<p class="meta">这是第二层 rough pricing anchor，用于检验收入假设是否能转化为现金流和估值；仍不是最终交易结论。</p>
</section>

<section class="panel">
<h2>动作判定</h2>
{decision_html}
</section>

<section class="panel">
<h2>Base Case 业务线</h2>
<table><thead><tr><th>Segment</th><th>Line</th><th>Evidence</th>{header}<th class="driver">Driver</th></tr></thead><tbody>{''.join(line_rows)}</tbody></table>
</section>

<section class="panel">
<h2>证据 Gate</h2>
<ul>{gates}</ul>
<p class="meta">{esc(company['source_note'])}</p>
</section>

{audit_html}

<section class="panel">
<h2>主源</h2>
<ul>{sources}</ul>
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


def render_compare_md(payloads: list[dict[str, Any]], asof: str) -> str:
    lines = [
        "# AI Optical / Rack-scale Revenue Build Compare",
        "",
        f"- 日期：`{asof}`",
        "- 用途：横向比较 AI optical / rack-scale 候选的收入模型、主源校准、估值吸收程度和动作。",
        "- 边界：研究工具，不自动交易，不替代完整估值报告。",
        "",
        "| Ticker | Company | Action | Price | Bear/Base/Upside | Price/Base | Upside dependency | Calibration | Evidence level |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for payload in payloads:
        decision = payload["decision"]
        checks = payload.get("validation", [])
        calibration = "PASS" if checks and all(c.get("status") == "PASS" for c in checks) else "CHECK"
        evidence_level = {
            "LITE": "product-level mixed",
            "COHR": "segment-level",
            "AAOI": "high-beta guide-level",
        }.get(payload["ticker"], "model")
        lines.append(
            f"| `{payload['ticker']}` | {payload['company']['company']} | `{decision['action']}` | "
            f"${decision['price']:.2f} | ${decision['bear_value']:.0f}/${decision['base_value']:.0f}/${decision['upside_value']:.0f} | "
            f"{decision['base_discount']:.2f}x | {decision['upside_dependency']:.1%} | `{calibration}` | {evidence_level} |"
        )
    lines.extend(
        [
            "",
            "## 当前结论",
            "",
            "- `LITE`：产品线模型更细，但价格已超过粗略 upside 锚，结论是 `DO_NOT_CHASE`。",
            "- `COHR`：主源分部证据更直接，但也已超过粗略 upside 锚，结论是 `DO_NOT_CHASE`。",
            "- `AAOI`：弹性最高，但质量、稀释、客户集中和执行风险最大；只作为 high-beta right-tail 样本。",
            "- 三者都只进入 V6AB/Radar evidence，不改变 V6AB V2 模拟盘。",
        ]
    )
    return "\n".join(lines) + "\n"


def render_compare_html(payloads: list[dict[str, Any]], asof: str) -> str:
    rows = []
    for payload in payloads:
        decision = payload["decision"]
        checks = payload.get("validation", [])
        calibration = "PASS" if checks and all(c.get("status") == "PASS" for c in checks) else "CHECK"
        evidence_level = {
            "LITE": "product-level mixed",
            "COHR": "segment-level",
            "AAOI": "high-beta guide-level",
        }.get(payload["ticker"], "model")
        rows.append(
            "<tr>"
            f"<td>{esc(payload['ticker'])}</td>"
            f"<td>{esc(payload['company']['company'])}</td>"
            f"<td><b>{esc(decision['action'])}</b></td>"
            f"<td>${decision['price']:.2f}</td>"
            f"<td>${decision['bear_value']:.0f} / ${decision['base_value']:.0f} / ${decision['upside_value']:.0f}</td>"
            f"<td>{decision['base_discount']:.2f}x</td>"
            f"<td>{decision['upside_dependency']:.1%}</td>"
            f"<td>{esc(calibration)}</td>"
            f"<td>{esc(evidence_level)}</td>"
            "</tr>"
        )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>AI Optical Revenue Build Compare</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin:0; background:#f6f7f9; color:#18212f; }}
main {{ max-width: 1120px; margin:0 auto; padding:28px; }}
.panel {{ background:#fff; border:1px solid #dfe3ea; border-radius:8px; padding:18px; }}
table {{ width:100%; border-collapse:collapse; font-size:13px; }}
th, td {{ border-bottom:1px solid #e5e8ef; padding:9px 8px; text-align:right; }}
th:first-child, td:first-child, th:nth-child(2), td:nth-child(2), th:nth-child(3), td:nth-child(3), td:last-child {{ text-align:left; }}
thead th {{ background:#173b57; color:white; }}
.note {{ color:#5b6675; line-height:1.6; }}
</style>
</head>
<body><main>
<h1>AI Optical / Rack-scale Revenue Build Compare</h1>
<p class="note">日期：{esc(asof)}。研究工具，不自动交易，不替代完整估值报告。</p>
<section class="panel">
<table><thead><tr><th>Ticker</th><th>Company</th><th>Action</th><th>Price</th><th>Bear/Base/Upside</th><th>Price/Base</th><th>Upside dependency</th><th>Calibration</th><th>Evidence</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
</section>
<section class="panel">
<h2>当前结论</h2>
<p>LITE 产品线模型更细，但价格已超过粗略 upside 锚，结论是 DO_NOT_CHASE。</p>
<p>COHR 主源分部证据更直接，但也已超过粗略 upside 锚，结论是 DO_NOT_CHASE。</p>
<p>AAOI 弹性最高，但质量、稀释、客户集中和执行风险最大；只作为 high-beta right-tail 样本。</p>
</section>
</main></body></html>
"""


def write_compare_outputs(payloads: list[dict[str, Any]], asof: str) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    md = render_compare_md(payloads, asof)
    html = render_compare_html(payloads, asof)
    data = json.dumps({"asof": asof, "payloads": payloads}, ensure_ascii=False, indent=2)
    for path, content in {
        OUTPUT_DIR / "latest_compare.md": md,
        OUTPUT_DIR / "latest_compare.html": html,
        OUTPUT_DIR / "latest_compare.json": data,
        REPORT_ROOT / "AI_Optical_Revenue_Build_Compare_LATEST.md": md,
        REPORT_ROOT / "AI_Optical_Revenue_Build_Compare_LATEST.html": html,
        REPORT_ROOT / "AI_Optical_Revenue_Build_Compare_LATEST.json": data,
    }.items():
        path.write_text(content, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", default="LITE")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--asof", required=True)
    args = parser.parse_args()
    config = read_json(CONFIG_PATH)
    tickers = list(config.get("companies", {}).keys()) if args.all else [args.ticker.upper()]
    payloads = []
    for ticker in tickers:
        payload = build_payload(config, ticker, args.asof)
        write_outputs(payload)
        payloads.append(payload)
    if len(payloads) > 1:
        write_compare_outputs(payloads, args.asof)
        print(render_compare_md(payloads, args.asof))
    else:
        print(render_md(payloads[0]))


if __name__ == "__main__":
    main()
