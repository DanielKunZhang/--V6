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
OUT_DIR = ROOT / "backtest_results" / "v6ab_override_evidence_gap_review"
DEFAULT_OVERRIDE_REVIEW = ROOT / "backtest_results" / "v6ab_override_evidence_candidate_review" / "latest.json"
DEFAULT_HIERARCHY = ROOT / "backtest_results" / "v6ab_theme_hierarchy_diagnostics" / "latest.json"
DEFAULT_HISTORICAL_EVIDENCE = ROOT / "backtest_results" / "v6ab_historical_evidence" / "latest.json"
DEFAULT_EVENT_FACTS = ROOT / "backtest_results" / "v6ab_event_facts" / "latest.json"

THEME_TARGETS = {
    "ai_platform": ["US.MSFT", "US.GOOGL", "US.AMZN", "US.META"],
    "ai_memory": ["US.MU", "US.WDC", "US.SNDK"],
    "ai_optical": ["US.COHR", "US.AAOI", "US.LITE", "US.CRDO", "US.ALAB"],
    "ai_networking": ["US.ANET", "US.AVGO", "US.MRVL", "US.CSCO"],
    "semis_ai": ["US.NVDA", "US.AMD", "US.TSM", "US.AVGO"],
}

THEME_FACT_GROUPS = {
    "ai_platform": {
        "cloud_ai_revenue": ["aws revenue", "azure", "google cloud", "cloud revenue", "cloud growth"],
        "ai_product_adoption": ["copilot", "gemini", "llama", "ai assistant", "generative ai"],
        "ai_capex_datacenter": ["ai capex", "data center", "datacenter", "gpu cluster", "cloud infrastructure"],
        "ad_recommendation_uplift": ["recommendation", "ranking", "ads ai", "advertising ai", "reels"],
    },
    "ai_memory": {
        "hbm_ai_server_demand": ["hbm", "high bandwidth memory", "ai server", "ai demand"],
        "dram_nand_pricing_cycle": ["dram", "nand", "pricing", "average selling price", "asp"],
        "supply_tightness_capacity": ["supply tight", "shortage", "capacity", "bit shipments", "utilization"],
        "inventory_trough_recovery": ["inventory", "digestion", "recovery", "cycle"],
    },
    "ai_optical": {
        "ai_datacenter_orders": ["ai data center", "datacenter", "hyperscale", "cloud customer", "order"],
        "optical_transceiver": ["optical", "transceiver", "800g", "1.6t", "coherent"],
        "ethernet_fabric_interconnect": ["ethernet", "fabric", "interconnect", "switch"],
        "customer_design_wins": ["design win", "customer win", "qualification", "ramp"],
    },
    "ai_networking": {
        "ethernet_ai_fabric": ["ethernet", "fabric", "switch", "networking"],
        "custom_ai_asic": ["custom ai", "asic", "accelerator", "xpu"],
        "hyperscaler_orders": ["hyperscale", "cloud customer", "order", "backlog"],
    },
    "semis_ai": {
        "accelerator_gpu_demand": ["gpu", "accelerator", "ai processor", "ai demand"],
        "foundry_capacity": ["foundry", "wafer", "advanced node", "capacity"],
        "advanced_packaging": ["advanced packaging", "cowos", "hbm", "interposer"],
    },
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


def text_for(row: dict[str, Any]) -> str:
    return f" {row.get('summary', '')} {row.get('evidence_type', '')} ".lower()


def group_hits(rows: list[dict[str, Any]], theme: str) -> dict[str, int]:
    hits: dict[str, int] = {}
    for group, keywords in THEME_FACT_GROUPS.get(theme, {}).items():
        hits[group] = sum(1 for row in rows if any(keyword in text_for(row) for keyword in keywords))
    return hits


def ticker_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        ticker = str(row.get("ticker", ""))
        if ticker.startswith("US."):
            counts[ticker] = counts.get(ticker, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def missing_targets(theme: str, historical_rows: list[dict[str, Any]], fact_rows: list[dict[str, Any]]) -> list[str]:
    targets = THEME_TARGETS.get(theme, [])
    historical_tickers = set(ticker_counts(historical_rows))
    fact_tickers = set(ticker_counts(fact_rows))
    out: list[str] = []
    for ticker in targets:
        if ticker not in historical_tickers:
            out.append(f"{ticker}:missing_historical_docs")
        elif ticker not in fact_tickers:
            out.append(f"{ticker}:no_actionable_fact")
    return out


def gap_decision(row: dict[str, Any], missing_groups: list[str], missing_tickers: list[str]) -> tuple[str, str]:
    market_adv = float(row.get("market_advantage", 0.0) or 0.0)
    hierarchy_decision = str(row.get("hierarchy_decision", ""))
    if hierarchy_decision == "OVERRIDE_READY_RESEARCH" or market_adv >= 7:
        return "P0_HARVEST_AND_FACT_RULE_REVIEW", "市场相对领先已出现，优先补 PIT-visible 事实，验证是否能升级 OVERRIDE。"
    if market_adv >= 4 and missing_groups:
        return "P1_FACT_PRECISION_REVIEW", "有相对领先雏形，但事实类别缺口明显，先补事实精度。"
    if missing_tickers:
        return "P2_COVERAGE_REVIEW", "主要问题是 ticker/doc 覆盖不足，先补 ledger 覆盖。"
    return "P3_WATCH_ONLY", "事实和市场领先都不足，保留观察，不加复杂规则。"


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    override_review = load_json(args.override_review_json)
    hierarchy = load_json(args.hierarchy_json)
    historical = load_json(args.historical_evidence_json)
    event_facts = load_json(args.event_facts_json)

    hierarchy_by_key = {
        (str(row.get("asof")), str(row.get("child_theme")), str(row.get("parent_theme"))): row
        for row in hierarchy.get("rows", [])
    }
    rows: list[dict[str, Any]] = []
    for review_row in override_review.get("rows", []):
        asof = str(review_row.get("asof"))
        child = str(review_row.get("child_theme"))
        parent = str(review_row.get("parent_theme"))
        hist_child = visible(historical.get("rows", []), child, asof)
        fact_child = visible(event_facts.get("rows", []), child, asof)
        fact_parent = visible(event_facts.get("rows", []), parent, asof)
        hits = group_hits(fact_child, child)
        missing_groups = [group for group, count in hits.items() if count == 0]
        missing_ticker_items = missing_targets(child, hist_child, fact_child)
        decision, reason = gap_decision(review_row, missing_groups, missing_ticker_items)
        hrow = hierarchy_by_key.get((asof, child, parent), {})
        rows.append(
            {
                "asof": asof,
                "child_theme": child,
                "parent_theme": parent,
                "hierarchy_decision": review_row.get("hierarchy_decision"),
                "review_decision": review_row.get("review_decision"),
                "gap_priority": decision,
                "reason": reason,
                "market_advantage": review_row.get("market_advantage"),
                "independence_score": review_row.get("independence_score"),
                "child_fact_precision": hrow.get("child_fact_precision"),
                "child_evidence_count": hrow.get("child_evidence_count"),
                "child_historical_rows": len(hist_child),
                "child_actionable_rows": len(fact_child),
                "parent_actionable_rows": len(fact_parent),
                "child_fact_group_hits": hits,
                "missing_fact_groups": missing_groups,
                "missing_ticker_coverage": missing_ticker_items,
                "child_historical_tickers": ticker_counts(hist_child),
                "child_actionable_tickers": ticker_counts(fact_child),
                "next_action": next_action(child, missing_groups, missing_ticker_items),
            }
        )

    priority_counts: dict[str, int] = {}
    theme_counts: dict[str, int] = {}
    missing_group_counts: dict[str, int] = {}
    for row in rows:
        priority_counts[row["gap_priority"]] = priority_counts.get(row["gap_priority"], 0) + 1
        theme_counts[row["child_theme"]] = theme_counts.get(row["child_theme"], 0) + 1
        for group in row["missing_fact_groups"]:
            missing_group_counts[f"{row['child_theme']}:{group}"] = missing_group_counts.get(f"{row['child_theme']}:{group}", 0) + 1
    return {
        "asof": args.asof,
        "diagnostic_only": True,
        "inputs": {
            "override_review_json": str(args.override_review_json),
            "hierarchy_json": str(args.hierarchy_json),
            "historical_evidence_json": str(args.historical_evidence_json),
            "event_facts_json": str(args.event_facts_json),
        },
        "summary": {
            "rows": len(rows),
            "priority_counts": priority_counts,
            "theme_counts": theme_counts,
            "missing_group_counts": dict(sorted(missing_group_counts.items(), key=lambda item: (-item[1], item[0]))),
        },
        "rows": sorted(
            rows,
            key=lambda item: (
                item["gap_priority"] == "P0_HARVEST_AND_FACT_RULE_REVIEW",
                item["gap_priority"] == "P1_FACT_PRECISION_REVIEW",
                float(item.get("market_advantage", 0.0) or 0.0),
            ),
            reverse=True,
        ),
        "interpretation": [
            "本报告只定位 evidence gap，不改变 classifier、回测候选或模拟盘。",
            "优先补 PIT 可见且 date-stamped 的具体经营事实，而不是降低 OVERRIDE gate。",
            "若 child theme 只有 metadata 或泛化收入增长，应回归父主题，避免把系统越做越复杂。",
        ],
    }


def next_action(theme: str, missing_groups: list[str], missing_tickers: list[str]) -> str:
    missing_docs = [item for item in missing_tickers if item.endswith(":missing_historical_docs")]
    no_facts = [item for item in missing_tickers if item.endswith(":no_actionable_fact")]
    if missing_docs and no_facts:
        return "同时补缺失 ticker 文件覆盖，并升级 fact extraction；已有文件但无 actionable facts 的 ticker 优先查具体经营表述。"
    if missing_docs:
        return "补齐目标 ticker 的 earnings release / 8-K business update / investor presentation，并重新跑 event fact ledger。"
    if no_facts:
        return "已有历史文件但未抽出 actionable facts；优先升级保守 fact extraction，避免只记录 filing metadata。"
    if missing_groups:
        groups = ", ".join(missing_groups[:3])
        return f"为 {theme} 增加保守 fact extraction 覆盖：{groups}；只接受具体客户/订单/分部收入/产能/定价事实。"
    return "暂不加规则；等待更多 PIT-visible 事实或市场相对领先。"


def render_md(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    lines = [
        "# V6AB Override Evidence Gap Review",
        "",
        f"- 日期：`{payload['asof']}`",
        "- 模拟盘动作：`NO_CHANGE`。",
        "- 目的：定位 child-theme OVERRIDE 失败时缺少哪些 PIT-visible 事实与 ticker 覆盖。",
        "",
        "## Summary",
        "",
        f"- reviewed rows：`{summary['rows']}`",
        "",
        "### Priority Counts",
        "",
    ]
    for key, count in summary["priority_counts"].items():
        lines.append(f"- `{key}`：{count}")
    lines += ["", "### Top Missing Fact Groups", ""]
    for key, count in list(summary["missing_group_counts"].items())[:16]:
        lines.append(f"- `{key}`：{count}")
    lines += [
        "",
        "## Gap Rows",
        "",
        "| asof | child | parent | priority | market adv | hist rows | facts | parent facts | missing groups | missing ticker coverage |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for row in payload["rows"][:24]:
        groups = ", ".join(row.get("missing_fact_groups", [])[:4]) or "-"
        tickers = ", ".join(row.get("missing_ticker_coverage", [])[:5]) or "-"
        lines.append(
            f"| `{row['asof']}` | `{row['child_theme']}` | `{row['parent_theme']}` | "
            f"`{row['gap_priority']}` | {float(row.get('market_advantage', 0.0) or 0.0):+.1f} | "
            f"{row['child_historical_rows']} | {row['child_actionable_rows']} | {row['parent_actionable_rows']} | "
            f"{groups} | {tickers} |"
        )
    lines += ["", "## P0 / P1 Next Actions", ""]
    for row in payload["rows"]:
        if not str(row.get("gap_priority", "")).startswith(("P0", "P1")):
            continue
        lines.append(f"- `{row['asof']}` `{row['child_theme']}`：{row['next_action']}")
    lines += ["", "## Interpretation", ""]
    lines.extend(f"- {item}" for item in payload.get("interpretation", []))
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnose missing PIT-visible evidence for V6AB OVERRIDE candidates.")
    parser.add_argument("--asof", default=str(date.today()))
    parser.add_argument("--override-review-json", type=Path, default=DEFAULT_OVERRIDE_REVIEW)
    parser.add_argument("--hierarchy-json", type=Path, default=DEFAULT_HIERARCHY)
    parser.add_argument("--historical-evidence-json", type=Path, default=DEFAULT_HISTORICAL_EVIDENCE)
    parser.add_argument("--event-facts-json", type=Path, default=DEFAULT_EVENT_FACTS)
    parser.add_argument("--output-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    payload = build_payload(args)
    md = render_md(payload)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    json_text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    (args.output_dir / "latest.json").write_text(json_text, encoding="utf-8")
    (args.output_dir / "latest.md").write_text(md + "\n", encoding="utf-8")
    pd.DataFrame(payload["rows"]).to_csv(args.output_dir / "latest.csv", index=False)
    (REPORT_ROOT / "V6AB_Override_Evidence_Gap_Review_LATEST.json").write_text(json_text, encoding="utf-8")
    (REPORT_ROOT / "V6AB_Override_Evidence_Gap_Review_LATEST.md").write_text(md + "\n", encoding="utf-8")
    pd.DataFrame(payload["rows"]).to_csv(REPORT_ROOT / "V6AB_Override_Evidence_Gap_Review_LATEST.csv", index=False)
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
