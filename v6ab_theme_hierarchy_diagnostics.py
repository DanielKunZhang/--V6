#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from v6ab_theme_mapping_experiment import PARENT_THEME


ROOT = Path(__file__).resolve().parent
DESKTOP_ROOT = Path("/Users/zhangkun/Desktop/AI个人投资公司")
REPORT_ROOT = DESKTOP_ROOT / "报表输出" / "LATEST"
OUT_DIR = ROOT / "backtest_results" / "v6ab_theme_hierarchy_diagnostics"
DEFAULT_REPLAY = ROOT / "backtest_results" / "v6ab_daily_evolution" / "pit_replay" / "latest_pit_classifier_replay.json"


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"missing input: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def fmt_pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{float(value):+.2%}"


def num(row: dict[str, Any], key: str, default: float = 0.0) -> float:
    try:
        return float(row.get(key, default) or default)
    except Exception:
        return default


def theme_by_id(snap: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(row.get("theme")): row for row in snap.get("themes", []) if row.get("theme")}


def independence_score(child: dict[str, Any], parent: dict[str, Any]) -> tuple[float, list[str]]:
    market_adv = num(child, "market_score") - num(parent, "market_score")
    fact = num(child, "fact_precision_score")
    evidence = num(child, "evidence_count")
    breadth = num(child, "breadth")
    entry = num(child, "entry_quality_score")
    payoff = num(child, "payoff_risk_score")
    position = num(child, "position_quality_score")
    child_126d = num(child.get("risk_skill_price_features", {}), "avg_126d_return")
    parent_126d = num(parent.get("risk_skill_price_features", {}), "avg_126d_return")
    rel_126d = child_126d - parent_126d

    score = 0.0
    reasons: list[str] = []
    if market_adv >= 5:
        score += 3
        reasons.append("child_market_advantage")
    elif market_adv <= -5:
        score -= 3
        reasons.append("parent_market_stronger")
    if rel_126d >= 0.05:
        score += 2
        reasons.append("child_126d_leadership")
    elif rel_126d <= -0.05:
        score -= 2
        reasons.append("parent_126d_leadership")
    if fact >= 45:
        score += 3
        reasons.append("fact_precision_ok")
    elif fact < 25:
        score -= 3
        reasons.append("low_fact_precision")
    if evidence >= 3:
        score += 2
        reasons.append("dated_evidence_depth")
    elif evidence == 0:
        score -= 2
        reasons.append("no_dated_evidence")
    if breadth >= 0.45:
        score += 2
        reasons.append("breadth_ok")
    elif breadth < 0.30:
        score -= 1
        reasons.append("narrow_breadth")
    if entry >= 45 and child.get("entry_quality_action") != "NO_ENTRY_EDGE":
        score += 2
        reasons.append("entry_quality_ok")
    elif child.get("entry_quality_action") == "NO_ENTRY_EDGE":
        score -= 2
        reasons.append("no_entry_edge")
    if payoff >= 25:
        score += 1
        reasons.append("payoff_risk_supported")
    if position >= 60:
        score += 1
        reasons.append("position_quality_supported")
    return score, reasons


def decision_for_row(
    child_theme: str,
    child: dict[str, Any],
    parent_theme: str,
    parent: dict[str, Any],
    snap: dict[str, Any],
    score: float,
    reasons: list[str],
) -> tuple[str, str]:
    parent_in_boost = parent_theme in set(snap.get("boost_allowlist", []))
    override = bool(snap.get("override_allowlist"))
    market_adv = num(child, "market_score") - num(parent, "market_score")
    child_126d = num(child.get("risk_skill_price_features", {}), "avg_126d_return")
    parent_126d = num(parent.get("risk_skill_price_features", {}), "avg_126d_return")
    differentiated = market_adv >= 5 or (child_126d - parent_126d) >= 0.05
    if override:
        return "KEEP_OVERRIDE_PATH", "已有 OVERRIDE，本诊断只记录，不合并。"
    if parent_in_boost and not differentiated:
        return "MERGE_TO_PARENT", "父主题也在 BOOST，且子主题没有明显相对领先；应回归父主题。"
    if parent_in_boost and score < 5:
        return "MERGE_TO_PARENT", "父主题也在 BOOST，且子主题独立性不足；应回归父主题。"
    if score >= 10 and differentiated and num(child, "fact_precision_score") >= 45 and num(child, "evidence_count") >= 3:
        return "OVERRIDE_READY_RESEARCH", "子主题可能具备独立主线资格；需要进入 OVERRIDE 候选审查。"
    if score >= 5:
        return "CHILD_STANDALONE_WATCH", "子主题有部分独立性，但证据或广度不足，保留观察。"
    if parent_in_boost:
        return "PARENT_CONFLICT_WATCH", "父子冲突存在，但独立性不够，不应升级子主题。"
    return "WATCH", "未形成父子冲突，作为普通层级样本记录。"


def build_rows(snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for snap in snapshots:
        by_theme = theme_by_id(snap)
        boost = set(snap.get("boost_allowlist", []))
        for child_theme, parent_theme in PARENT_THEME.items():
            if child_theme not in boost:
                continue
            child = by_theme.get(child_theme, {})
            parent = by_theme.get(parent_theme, {})
            if not child or not parent:
                continue
            score, reasons = independence_score(child, parent)
            decision, action = decision_for_row(child_theme, child, parent_theme, parent, snap, score, reasons)
            rows.append(
                {
                    "asof": snap.get("asof"),
                    "child_theme": child_theme,
                    "parent_theme": parent_theme,
                    "parent_in_boost": parent_theme in boost,
                    "override_active": bool(snap.get("override_allowlist")),
                    "decision": decision,
                    "action": action,
                    "independence_score": score,
                    "reasons": reasons,
                    "child_market": num(child, "market_score"),
                    "parent_market": num(parent, "market_score"),
                    "market_advantage": num(child, "market_score") - num(parent, "market_score"),
                    "child_fact_precision": num(child, "fact_precision_score"),
                    "child_evidence_count": int(num(child, "evidence_count")),
                    "child_breadth": num(child, "breadth"),
                    "child_entry_quality": num(child, "entry_quality_score"),
                    "child_entry_action": child.get("entry_quality_action"),
                    "child_payoff_risk": num(child, "payoff_risk_score"),
                    "child_position_quality": num(child, "position_quality_score"),
                    "child_signal_tier": child.get("signal_tier"),
                    "boost_allowlist": list(snap.get("boost_allowlist", [])),
                    "override_allowlist": list(snap.get("override_allowlist", [])),
                }
            )
    return rows


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    decisions: dict[str, int] = {}
    child_summary: dict[str, dict[str, Any]] = {}
    for row in rows:
        decisions[row["decision"]] = decisions.get(row["decision"], 0) + 1
        item = child_summary.setdefault(
            row["child_theme"],
            {"child_theme": row["child_theme"], "count": 0, "merge_to_parent": 0, "override_ready": 0, "avg_score": 0.0},
        )
        item["count"] += 1
        item["avg_score"] += float(row["independence_score"])
        if row["decision"] == "MERGE_TO_PARENT":
            item["merge_to_parent"] += 1
        if row["decision"] == "OVERRIDE_READY_RESEARCH":
            item["override_ready"] += 1
    for item in child_summary.values():
        item["avg_score"] = item["avg_score"] / item["count"] if item["count"] else 0.0
    return {
        "total_child_boost_rows": len(rows),
        "decision_counts": decisions,
        "child_summary": sorted(
            child_summary.values(),
            key=lambda item: (item["merge_to_parent"], item["override_ready"], item["count"]),
            reverse=True,
        ),
        "merge_rows": [row for row in rows if row["decision"] == "MERGE_TO_PARENT"],
        "override_ready_rows": [row for row in rows if row["decision"] == "OVERRIDE_READY_RESEARCH"],
    }


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    replay = load_json(args.replay_json)
    snapshots = sorted(replay.get("snapshots", []), key=lambda row: row["asof"])
    rows = build_rows(snapshots)
    summary = summarize(rows)
    return {
        "asof": args.asof,
        "replay_json": str(args.replay_json),
        "diagnostic_only": True,
        "policy": {
            "merge_to_parent": "父主题与子主题同时 BOOST 且子主题独立性不足时，优先回归父主题。",
            "override_ready_research": "只有 fact/evidence/market/breadth/entry 同时支持时，子主题才进入 OVERRIDE 候选审查。",
            "no_sim_change": "本诊断不改变 PIT replay、classifier 或 V6AB 模拟盘。",
        },
        **summary,
        "rows": rows,
    }


def render_md(payload: dict[str, Any]) -> str:
    decisions = payload.get("decision_counts", {})
    lines = [
        "# V6AB Theme Hierarchy Diagnostics",
        "",
        f"- 日期：`{payload['asof']}`",
        "- 模拟盘动作：`NO_CHANGE`。",
        "- 目的：判断 AI 子主题/行业子主题何时应回归父主题，何时才可能独立成为主线。",
        "",
        "## Summary",
        "",
        f"- child BOOST 样本：`{payload.get('total_child_boost_rows', 0)}`",
        f"- merge_to_parent：`{decisions.get('MERGE_TO_PARENT', 0)}`",
        f"- override_ready_research：`{decisions.get('OVERRIDE_READY_RESEARCH', 0)}`",
        f"- child_standalone_watch：`{decisions.get('CHILD_STANDALONE_WATCH', 0)}`",
        "",
        "## Child Summary",
        "",
        "| child | count | merge | override ready | avg score |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for row in payload.get("child_summary", []):
        lines.append(
            f"| `{row['child_theme']}` | {row['count']} | {row['merge_to_parent']} | "
            f"{row['override_ready']} | {float(row['avg_score']):+.2f} |"
        )
    lines += [
        "",
        "## Merge-To-Parent Rows",
        "",
        "| asof | child | parent | score | market adv | fact | evidence | reasons |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in payload.get("merge_rows", [])[:20]:
        lines.append(
            f"| `{row['asof']}` | `{row['child_theme']}` | `{row['parent_theme']}` | "
            f"{float(row['independence_score']):+.1f} | {float(row['market_advantage']):+.1f} | "
            f"{float(row['child_fact_precision']):.1f} | {row['child_evidence_count']} | "
            f"`{', '.join(row['reasons'])}` |"
        )
    lines += [
        "",
        "## Override-Ready Research Rows",
        "",
        "| asof | child | parent | score | market adv | fact | evidence | breadth | entry |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in payload.get("override_ready_rows", [])[:20]:
        lines.append(
            f"| `{row['asof']}` | `{row['child_theme']}` | `{row['parent_theme']}` | "
            f"{float(row['independence_score']):+.1f} | {float(row['market_advantage']):+.1f} | "
            f"{float(row['child_fact_precision']):.1f} | {row['child_evidence_count']} | "
            f"{float(row['child_breadth']):.2f} | {float(row['child_entry_quality']):.1f} |"
        )
    lines += [
        "",
        "## Interpretation",
        "",
        "- 这一步不是为了拟合收益，而是把“子主题必须证明自己不是父主题的重复叙事”制度化。",
        "- 若 override-ready 长期为 0，说明当前 historical evidence 还不能支持排他替换 V2，只能做 RESEARCH_OVERLAY。",
        "- 下一步应优先补能提高 fact precision 和 differentiated breadth 的 date-stamped evidence，而不是放宽 gate。",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnose V6AB parent/child theme hierarchy and override readiness.")
    parser.add_argument("--asof", default=str(date.today()))
    parser.add_argument("--replay-json", type=Path, default=DEFAULT_REPLAY)
    parser.add_argument("--output-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    payload = build_payload(args)
    md = render_md(payload)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "latest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (args.output_dir / "latest.md").write_text(md + "\n", encoding="utf-8")
    pd.DataFrame(payload["rows"]).to_csv(args.output_dir / "latest.csv", index=False)
    (REPORT_ROOT / "V6AB_Theme_Hierarchy_Diagnostics_LATEST.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    (REPORT_ROOT / "V6AB_Theme_Hierarchy_Diagnostics_LATEST.md").write_text(md + "\n", encoding="utf-8")
    pd.DataFrame(payload["rows"]).to_csv(REPORT_ROOT / "V6AB_Theme_Hierarchy_Diagnostics_LATEST.csv", index=False)
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
