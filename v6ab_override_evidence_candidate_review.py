#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parent
DESKTOP_ROOT = Path("/Users/zhangkun/Desktop/AI个人投资公司")
REPORT_ROOT = DESKTOP_ROOT / "报表输出" / "LATEST"
OUT_DIR = ROOT / "backtest_results" / "v6ab_override_evidence_candidate_review"
DEFAULT_HIERARCHY = ROOT / "backtest_results" / "v6ab_theme_hierarchy_diagnostics" / "latest.json"
DEFAULT_HISTORICAL_EVIDENCE = ROOT / "backtest_results" / "v6ab_historical_evidence" / "latest.json"
DEFAULT_EVENT_FACTS = ROOT / "backtest_results" / "v6ab_event_facts" / "latest.json"

ACTIONABLE_TYPES = {
    "event_fact_revenue_acceleration",
    "event_fact_guidance_raise",
    "event_fact_margin_expansion",
    "event_fact_orders_backlog",
    "event_fact_capex_capacity",
    "event_fact_cloud_data_center",
    "event_fact_ai_accelerator",
}
NEGATIVE_TYPES = {
    "event_fact_inventory_correction",
    "event_fact_demand_slowdown",
    "event_fact_guidance_cut",
    "event_fact_margin_pressure",
    "event_fact_supply_constraint",
}
FILING_METADATA_TYPES = {
    "earnings_release",
    "quarterly_report",
    "annual_report",
    "business_update",
    "investor_presentation",
    "material_agreement",
    "sec_8k",
}
THEME_KEYWORDS = {
    "ai_platform": [
        "aws",
        "azure",
        "cloud",
        "copilot",
        "artificial intelligence",
        " ai ",
        "machine learning",
        "data center",
        "datacenter",
    ],
    "ai_memory": ["hbm", "high bandwidth memory", "dram", "nand", "memory", "storage", "ssd"],
    "ai_optical": ["optical", "interconnect", "transceiver", "coherent", "ethernet", "datacenter"],
    "ai_networking": ["networking", "ethernet", "switch", "fabric", "interconnect", "datacenter"],
    "semis_ai": ["semiconductor", "gpu", "accelerator", "wafer", "foundry", "ai processor", "chip"],
    "technology": ["cloud", "software", "digital", "subscription", "platform", "e-commerce", "advertising"],
}


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"missing input: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def parse_ts(value: Any) -> pd.Timestamp | None:
    try:
        if value in (None, ""):
            return None
        return pd.Timestamp(value).normalize()
    except Exception:
        return None


def visible(rows: list[dict[str, Any]], theme: str, asof: str) -> list[dict[str, Any]]:
    asof_ts = pd.Timestamp(asof).normalize()
    out: list[dict[str, Any]] = []
    for row in rows:
        if row.get("theme") != theme:
            continue
        source_ts = parse_ts(row.get("source_date"))
        expiry_ts = parse_ts(row.get("expiry_date"))
        if source_ts is not None and source_ts > asof_ts:
            continue
        if expiry_ts is not None and expiry_ts < asof_ts:
            continue
        out.append(row)
    return out


def theme_keyword_hit(theme: str, row: dict[str, Any]) -> bool:
    summary = f" {str(row.get('summary', '')).lower()} "
    keywords = THEME_KEYWORDS.get(theme, [])
    if not keywords:
        return True
    return any(keyword in summary for keyword in keywords)


def evidence_strength(rows: list[dict[str, Any]], theme: str) -> dict[str, Any]:
    positive = [row for row in rows if row.get("direction") == "positive"]
    negative = [row for row in rows if row.get("direction") == "negative"]
    raw_actionable = [
        row
        for row in positive
        if row.get("evidence_type") in ACTIONABLE_TYPES
        and row.get("actionable", True)
        and row.get("context_role") in {"actual_result", "guidance", None}
    ]
    actionable = [row for row in raw_actionable if theme_keyword_hit(theme, row)]
    high_quality = [row for row in actionable if row.get("fact_quality") == "HIGH"]
    medium_quality = [row for row in actionable if row.get("fact_quality") in {"HIGH", "MEDIUM"}]
    negative_actionable = [row for row in negative if row.get("evidence_type") in NEGATIVE_TYPES]
    filing_metadata = [row for row in rows if row.get("evidence_type") in FILING_METADATA_TYPES]
    tickers = sorted({str(row.get("ticker")) for row in rows if str(row.get("ticker", "")).startswith("US.")})
    actionable_tickers = sorted({str(row.get("ticker")) for row in actionable if str(row.get("ticker", "")).startswith("US.")})
    fact_types = sorted({str(row.get("evidence_type")) for row in actionable})

    raw_quality = 0.0
    for row in medium_quality:
        quality_mult = 1.2 if row.get("fact_quality") == "HIGH" else 1.0
        numeric_mult = 1.15 if row.get("numeric_present") else 1.0
        raw_quality += float(row.get("confidence", 0.5) or 0.5) * float(row.get("weight", 0.5) or 0.5) * quality_mult * numeric_mult
    raw_quality -= 0.65 * len(negative_actionable)
    raw_quality += 0.15 * min(len(actionable_tickers), 4)
    raw_quality += 0.10 * min(len(fact_types), 4)

    return {
        "total_rows": len(rows),
        "positive_rows": len(positive),
        "negative_rows": len(negative),
        "filing_metadata_rows": len(filing_metadata),
        "raw_actionable_rows": len(raw_actionable),
        "actionable_rows": len(actionable),
        "theme_keyword_rejected_rows": len(raw_actionable) - len(actionable),
        "high_quality_rows": len(high_quality),
        "medium_plus_rows": len(medium_quality),
        "negative_actionable_rows": len(negative_actionable),
        "unique_tickers": len(tickers),
        "actionable_unique_tickers": len(actionable_tickers),
        "actionable_fact_types": fact_types,
        "quality_score": round(raw_quality, 4),
        "sample_facts": [
            {
                "date": row.get("source_date"),
                "ticker": row.get("ticker"),
                "type": row.get("evidence_type"),
                "quality": row.get("fact_quality"),
                "summary": str(row.get("summary", ""))[:220],
            }
            for row in sorted(actionable, key=lambda item: str(item.get("source_date", "")), reverse=True)[:5]
        ],
    }


def review_decision(hrow: dict[str, Any], child: dict[str, Any], parent: dict[str, Any]) -> tuple[str, str]:
    market_adv = float(hrow.get("market_advantage", 0.0) or 0.0)
    score_adv = child["quality_score"] - parent["quality_score"]
    if child["actionable_rows"] >= 3 and child["actionable_unique_tickers"] >= 2 and market_adv >= 5 and score_adv >= 0.5:
        return "OVERRIDE_EVIDENCE_CANDIDATE", "事实、广度和相对市场领先同时成立，可进入离线 OVERRIDE 回测。"
    if child["actionable_rows"] >= 2 and child["actionable_unique_tickers"] >= 1 and market_adv >= 5:
        return "WATCH_OVERRIDE_EVIDENCE", "有部分差异化事实和市场领先，但广度或质量仍不足。"
    if child["filing_metadata_rows"] > child["actionable_rows"] * 2:
        return "METADATA_HEAVY_REJECT", "主要是 filing metadata，不能证明子主题独立。"
    return "INSUFFICIENT_DIFFERENTIATION", "证据或相对强弱不足，继续回归父主题/研究观察。"


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    hierarchy = load_json(args.hierarchy_json)
    all_rows: list[dict[str, Any]] = []
    for path in [args.historical_evidence_json, args.event_facts_json]:
        payload = load_json(path)
        all_rows.extend(payload.get("rows", []))

    source_rows = [
        row
        for row in hierarchy.get("rows", [])
        if row.get("decision") in {"MERGE_TO_PARENT", "OVERRIDE_READY_RESEARCH", "CHILD_STANDALONE_WATCH"}
    ]
    rows: list[dict[str, Any]] = []
    for hrow in source_rows:
        asof = str(hrow.get("asof"))
        child_theme = str(hrow.get("child_theme"))
        parent_theme = str(hrow.get("parent_theme"))
        child_strength = evidence_strength(visible(all_rows, child_theme, asof), child_theme)
        parent_strength = evidence_strength(visible(all_rows, parent_theme, asof), parent_theme)
        decision, reason = review_decision(hrow, child_strength, parent_strength)
        rows.append(
            {
                "asof": asof,
                "child_theme": child_theme,
                "parent_theme": parent_theme,
                "hierarchy_decision": hrow.get("decision"),
                "market_advantage": hrow.get("market_advantage"),
                "independence_score": hrow.get("independence_score"),
                "review_decision": decision,
                "reason": reason,
                "child": child_strength,
                "parent": parent_strength,
                "quality_score_advantage": round(child_strength["quality_score"] - parent_strength["quality_score"], 4),
            }
        )
    decision_counts: dict[str, int] = {}
    for row in rows:
        decision_counts[row["review_decision"]] = decision_counts.get(row["review_decision"], 0) + 1
    return {
        "asof": args.asof,
        "diagnostic_only": True,
        "hierarchy_json": str(args.hierarchy_json),
        "historical_evidence_json": str(args.historical_evidence_json),
        "event_facts_json": str(args.event_facts_json),
        "rows": rows,
        "decision_counts": decision_counts,
        "override_candidates": [row for row in rows if row["review_decision"] == "OVERRIDE_EVIDENCE_CANDIDATE"],
        "watch_candidates": [row for row in rows if row["review_decision"] == "WATCH_OVERRIDE_EVIDENCE"],
        "interpretation": [
            "该审查只评估 child theme 是否有差异化事实证据，不改变 classifier、PIT replay 或模拟盘。",
            "OVERRIDE 候选必须同时满足 actionable fact、跨 ticker 广度、相对父主题市场领先和证据质量优势。",
            "若样本主要是 filing metadata，则不能作为 child theme 独立主线证据。",
        ],
    }


def render_md(payload: dict[str, Any]) -> str:
    counts = payload.get("decision_counts", {})
    lines = [
        "# V6AB Override Evidence Candidate Review",
        "",
        f"- 日期：`{payload['asof']}`",
        "- 模拟盘动作：`NO_CHANGE`。",
        "- 目的：审查 child theme 是否具备可差异化、PIT 可见的 OVERRIDE 事实证据。",
        "",
        "## Summary",
        "",
        f"- reviewed rows：`{len(payload.get('rows', []))}`",
        f"- override evidence candidates：`{counts.get('OVERRIDE_EVIDENCE_CANDIDATE', 0)}`",
        f"- watch override evidence：`{counts.get('WATCH_OVERRIDE_EVIDENCE', 0)}`",
        f"- metadata heavy reject：`{counts.get('METADATA_HEAVY_REJECT', 0)}`",
        f"- insufficient differentiation：`{counts.get('INSUFFICIENT_DIFFERENTIATION', 0)}`",
        "",
        "## Candidate Rows",
        "",
        "| asof | child | parent | decision | market adv | child actionable | child tickers | score adv | reason |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    ranked = sorted(
        payload.get("rows", []),
        key=lambda row: (
            row["review_decision"] == "OVERRIDE_EVIDENCE_CANDIDATE",
            row["review_decision"] == "WATCH_OVERRIDE_EVIDENCE",
            float(row.get("quality_score_advantage", 0.0) or 0.0),
        ),
        reverse=True,
    )
    for row in ranked[:24]:
        child = row.get("child", {})
        lines.append(
            f"| `{row['asof']}` | `{row['child_theme']}` | `{row['parent_theme']}` | `{row['review_decision']}` | "
            f"{float(row.get('market_advantage', 0.0) or 0.0):+.1f} | {child.get('actionable_rows', 0)} | "
            f"{child.get('actionable_unique_tickers', 0)} | {float(row.get('quality_score_advantage', 0.0) or 0.0):+.2f} | "
            f"{row.get('reason')} |"
        )
    lines += [
        "",
        "## Top Evidence Samples",
        "",
    ]
    for row in ranked[:8]:
        child = row.get("child", {})
        lines.append(f"### {row['asof']} {row['child_theme']} -> {row['review_decision']}")
        facts = child.get("sample_facts", [])
        if not facts:
            lines.append("- no actionable child facts")
            continue
        for fact in facts[:3]:
            summary = str(fact.get("summary", "")).replace("|", "/")
            lines.append(f"- `{fact.get('date')}` `{fact.get('ticker')}` `{fact.get('type')}` {summary}")
    lines += ["", "## Interpretation", ""]
    lines.extend(f"- {item}" for item in payload.get("interpretation", []))
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Review differentiated evidence for V6AB child-theme OVERRIDE candidates.")
    parser.add_argument("--asof", default=str(date.today()))
    parser.add_argument("--hierarchy-json", type=Path, default=DEFAULT_HIERARCHY)
    parser.add_argument("--historical-evidence-json", type=Path, default=DEFAULT_HISTORICAL_EVIDENCE)
    parser.add_argument("--event-facts-json", type=Path, default=DEFAULT_EVENT_FACTS)
    parser.add_argument("--output-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    payload = build_payload(args)
    md = render_md(payload)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "latest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (args.output_dir / "latest.md").write_text(md + "\n", encoding="utf-8")
    pd.DataFrame(payload["rows"]).to_csv(args.output_dir / "latest.csv", index=False)
    (REPORT_ROOT / "V6AB_Override_Evidence_Candidate_Review_LATEST.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    (REPORT_ROOT / "V6AB_Override_Evidence_Candidate_Review_LATEST.md").write_text(md + "\n", encoding="utf-8")
    pd.DataFrame(payload["rows"]).to_csv(REPORT_ROOT / "V6AB_Override_Evidence_Candidate_Review_LATEST.csv", index=False)
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
