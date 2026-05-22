#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from bisect import bisect_right
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parent
DESKTOP_ROOT = Path("/Users/zhangkun/Desktop/AI个人投资公司")
REPORT_ROOT = DESKTOP_ROOT / "报表输出" / "LATEST"
OUT_DIR = ROOT / "backtest_results" / "v6ab_pit_boost_failure_review"
DEFAULT_ATTRIBUTION = ROOT / "backtest_results" / "v6ab_daily_evolution" / "latest_pit_vs_v2_attribution.json"
DEFAULT_REPLAY = ROOT / "backtest_results" / "v6ab_daily_evolution" / "pit_replay" / "latest_pit_classifier_replay.json"


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"missing input: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def fmt_pct(value: float | None) -> str:
    if value is None or not np.isfinite(value):
        return "n/a"
    return f"{value:+.2%}"


def parse_theme_ids(top_text: str) -> list[str]:
    out: list[str] = []
    for part in str(top_text or "").split(","):
        part = part.strip()
        if not part or ":" not in part:
            continue
        out.append(part.split(":", 1)[0].strip())
    return out


def selected_text(row: dict[str, Any], key: str, fallback_key: str) -> str:
    return str(row.get(key) or row.get(fallback_key) or "")


def snapshot_index(snapshots: list[dict[str, Any]]) -> tuple[list[str], list[dict[str, Any]]]:
    ordered = sorted(snapshots, key=lambda row: row.get("asof", ""))
    return [str(row.get("asof", "")) for row in ordered], ordered


def snapshot_for_date(asofs: list[str], snapshots: list[dict[str, Any]], raw_date: str) -> dict[str, Any]:
    pos = bisect_right(asofs, raw_date) - 1
    if pos < 0:
        return {}
    return snapshots[pos]


def theme_map(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(row.get("theme")): row for row in snapshot.get("themes", []) if row.get("theme")}


def ticker_priority_for(snapshot: dict[str, Any], themes: list[str], limit: int = 5) -> list[dict[str, Any]]:
    theme_set = set(themes)
    rows = [row for row in snapshot.get("ticker_priority", []) if row.get("theme") in theme_set]
    return sorted(rows, key=lambda row: float(row.get("score", 0.0) or 0.0), reverse=True)[:limit]


def detail_values(row: dict[str, Any], key: str) -> list[float]:
    values: list[float] = []
    for detail in row.get("theme_details", []):
        try:
            values.append(float(detail.get(key, 0.0) or 0.0))
        except Exception:
            pass
    return values


def max_detail(row: dict[str, Any], key: str) -> float:
    values = detail_values(row, key)
    return max(values) if values else 0.0


def min_detail(row: dict[str, Any], key: str) -> float:
    values = detail_values(row, key)
    return min(values) if values else 0.0


def avg_detail(row: dict[str, Any], key: str) -> float:
    values = detail_values(row, key)
    return float(np.mean(values)) if values else 0.0


def any_action(row: dict[str, Any], action: str) -> bool:
    return any(str(detail.get("entry_quality_action", "")) == action for detail in row.get("theme_details", []))


def risk_skill_features(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "max_payoff_risk_score": max_detail(row, "payoff_risk_score"),
        "avg_payoff_risk_score": avg_detail(row, "payoff_risk_score"),
        "min_entry_quality_score": min_detail(row, "entry_quality_score"),
        "avg_entry_quality_score": avg_detail(row, "entry_quality_score"),
        "min_fact_precision_score": min_detail(row, "fact_precision_score"),
        "avg_fact_precision_score": avg_detail(row, "fact_precision_score"),
        "min_position_quality_score": min_detail(row, "position_quality_score"),
        "avg_position_quality_score": avg_detail(row, "position_quality_score"),
        "max_crowding_score": max_detail(row, "crowding_score"),
        "has_risk_review_theme": any_action(row, "RISK_REVIEW"),
        "has_capped_boost_theme": any_action(row, "CAPPED_BOOST_ONLY"),
        "has_no_entry_edge_theme": any_action(row, "NO_ENTRY_EDGE"),
    }


def summarize_cohort(rows: list[dict[str, Any]], name: str, predicate: Any) -> dict[str, Any]:
    selected = [row for row in rows if predicate(row)]
    deltas = [float(row.get("tier_minus_v2", 0.0) or 0.0) for row in selected]
    return {
        "cohort": name,
        "count": len(selected),
        "sum_delta": float(np.sum(deltas)) if deltas else 0.0,
        "avg_delta": float(np.mean(deltas)) if deltas else 0.0,
        "win_rate": float(np.mean([value > 0 for value in deltas])) if deltas else 0.0,
        "negative_months": int(np.sum([value < 0 for value in deltas])) if deltas else 0,
        "dates": [row.get("date") for row in selected],
    }


def correlation_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keys = [
        "max_payoff_risk_score",
        "avg_payoff_risk_score",
        "min_entry_quality_score",
        "avg_entry_quality_score",
        "min_fact_precision_score",
        "avg_fact_precision_score",
        "min_position_quality_score",
        "avg_position_quality_score",
        "max_crowding_score",
        "tier_turnover",
    ]
    out: list[dict[str, Any]] = []
    y = np.array([float(row.get("tier_minus_v2", 0.0) or 0.0) for row in rows], dtype=float)
    for key in keys:
        x = np.array([float(row.get(key, 0.0) or 0.0) for row in rows], dtype=float)
        if len(x) < 3 or np.std(x) == 0 or np.std(y) == 0:
            corr = 0.0
        else:
            corr = float(np.corrcoef(x, y)[0, 1])
        out.append({"metric": key, "corr_with_tier_delta": corr})
    return sorted(out, key=lambda row: abs(row["corr_with_tier_delta"]), reverse=True)


def build_risk_skill_attribution(rows: list[dict[str, Any]]) -> dict[str, Any]:
    enriched = []
    for row in rows:
        item = dict(row)
        item.update(risk_skill_features(row))
        enriched.append(item)
    cohorts = [
        summarize_cohort(enriched, "has_risk_review_theme", lambda row: row.get("has_risk_review_theme")),
        summarize_cohort(enriched, "has_capped_boost_theme", lambda row: row.get("has_capped_boost_theme")),
        summarize_cohort(enriched, "has_no_entry_edge_theme", lambda row: row.get("has_no_entry_edge_theme")),
        summarize_cohort(enriched, "max_payoff_risk_ge70", lambda row: float(row.get("max_payoff_risk_score", 0.0)) >= 70),
        summarize_cohort(enriched, "max_payoff_risk_ge55", lambda row: float(row.get("max_payoff_risk_score", 0.0)) >= 55),
        summarize_cohort(enriched, "min_entry_quality_lt50", lambda row: float(row.get("min_entry_quality_score", 0.0)) < 50),
        summarize_cohort(enriched, "min_fact_precision_lt20", lambda row: float(row.get("min_fact_precision_score", 0.0)) < 20),
        summarize_cohort(enriched, "max_crowding_ge90", lambda row: float(row.get("max_crowding_score", 0.0)) >= 90),
    ]
    return {
        "cohorts": sorted(cohorts, key=lambda row: row["sum_delta"]),
        "correlations": correlation_summary(enriched),
        "rows": enriched,
        "interpretation": [
            "risk skill attribution 只验证诊断分数是否解释 BOOST 正负贡献，不改变交易规则。",
            "若某 cohort 负贡献集中但同时误伤大量正样本，应优先考虑 capped/延迟确认，而不是硬删除。",
        ],
    }


def classify_failure(row: dict[str, Any], boosted: list[str], theme_details: list[dict[str, Any]]) -> list[str]:
    labels: list[str] = []
    date_year = int(str(row.get("date", "1900"))[:4])
    tier_delta = float(row.get("tier_minus_v2", 0.0) or 0.0)
    v2_top = set(parse_theme_ids(selected_text(row, "v2_selected", "v2_top")))
    tier_top = set(parse_theme_ids(selected_text(row, "tier_selected", "tier_top")))
    hard_top = set(parse_theme_ids(selected_text(row, "hard_selected", "hard_top")))
    boost_set = set(boosted)

    if tier_delta >= 0:
        return ["positive_boost"]
    if tier_delta <= -0.02 and not row.get("pit_override_allowlist"):
        labels.append("overboost_without_override")
    if date_year < 2022 and any(theme.startswith("ai_") for theme in boosted):
        labels.append("historical_taxonomy_mismatch")
    if len(boosted) == 1 and tier_delta <= -0.03:
        labels.append("narrow_theme_overfit")
    if float(row.get("tier_turnover", 0.0) or 0.0) > 1.0 and tier_delta <= -0.02:
        labels.append("turnover_drag")
    if {"precious_metals", "energy_resources"} & v2_top and not ({"precious_metals", "energy_resources"} & boost_set):
        labels.append("defensive_or_commodity_missed")
    if v2_top & {"semis_ai", "technology", "precious_metals"} and boost_set - v2_top and tier_delta <= -0.02:
        labels.append("theme_dilution")
    if (v2_top & (tier_top | hard_top)) and tier_delta <= -0.02:
        labels.append("expression_dilution")

    precision_risk = False
    for detail in theme_details:
        fundamental = float(detail.get("fundamental_score", 0.0) or 0.0)
        narrative = float(detail.get("narrative_score", 0.0) or 0.0)
        market_only = bool(detail.get("market_only", False))
        risk_penalty = float(detail.get("risk_penalty", 0.0) or 0.0)
        if market_only or fundamental < 20 or narrative < 20 or risk_penalty > 25:
            precision_risk = True
    if precision_risk and tier_delta <= -0.01:
        labels.append("evidence_precision_risk")

    return labels or ["unclassified_negative_boost"]


def recommended_fixes(labels: list[str]) -> list[str]:
    mapping = {
        "historical_taxonomy_mismatch": "补 2019-2021 历史主题 taxonomy：不要把所有成长/流动性/云软件行情硬映射成 AI infra。",
        "defensive_or_commodity_missed": "加入跨主题 regime 约束：贵金属/能源强势且 PIT 证据仅为 AI/平台时，BOOST 降级为 WATCH 或限制权重。",
        "theme_dilution": "提高 BOOST fact precision；宽泛平台/消费/AI 子主题不能稀释已胜出的 semis/technology/precious metals 表达。",
        "expression_dilution": "检查主题表达层：当主题重合但 tier 落后时，优先修 ticker/proxy selection 和换手，而不是加新 evidence。",
        "overboost_without_override": "BOOST 只能增强，不能靠弱证据替代 V2；无 override 的负贡献月份应进入降权训练集。",
        "narrow_theme_overfit": "单一窄主题 BOOST 需要更高证据门槛，尤其 ai_memory/ai_optical 这类高波动子主题。",
        "turnover_drag": "加入 BOOST turnover budget：新增主题若与现有 ETF 表达高度重叠，应限制换手或延迟确认。",
        "evidence_precision_risk": "把 filing metadata、market-only、低 fundamental/narrative 证据降权；优先补 date-stamped 订单、客户、capex、财报经营事实。",
        "positive_boost": "保留为正样本，用于确认哪些 evidence/taxonomy 组合真的提升 V2。",
    }
    out: list[str] = []
    for label in labels:
        if label in mapping and mapping[label] not in out:
            out.append(mapping[label])
    return out


def build_review(args: argparse.Namespace) -> dict[str, Any]:
    attribution = load_json(args.attribution_json)
    replay = load_json(args.replay_json)
    asofs, snapshots = snapshot_index(replay.get("snapshots", []))
    if not snapshots:
        raise SystemExit(f"empty replay snapshots: {args.replay_json}")

    active_rows = [
        row
        for row in attribution.get("rows", [])
        if row.get("pit_signal_tier") == "BOOST" or row.get("tier_active") or row.get("pit_boost_allowlist")
    ]
    review_rows: list[dict[str, Any]] = []
    for row in active_rows:
        snap = snapshot_for_date(asofs, snapshots, str(row.get("date")))
        boosted = list(row.get("pit_boost_allowlist") or snap.get("boost_allowlist") or [])
        details_by_theme = theme_map(snap)
        theme_details = [details_by_theme.get(theme, {"theme": theme}) for theme in boosted]
        labels = classify_failure(row, boosted, theme_details)
        risk_features = risk_skill_features({"theme_details": theme_details})
        review_rows.append(
            {
                "date": row.get("date"),
                "snapshot_asof": snap.get("asof"),
                "signal_tier": row.get("pit_signal_tier"),
                "tier_minus_v2": float(row.get("tier_minus_v2", 0.0) or 0.0),
                "overlay_minus_v2": float(row.get("overlay_minus_v2", 0.0) or 0.0),
                "hard_minus_v2": float(row.get("hard_minus_v2", 0.0) or 0.0),
                "v2_next_ret": float(row.get("v2_next_ret", 0.0) or 0.0),
                "tier_next_ret": float(row.get("tier_next_ret", 0.0) or 0.0),
                "boost_allowlist": boosted,
                "override_allowlist": list(row.get("pit_override_allowlist") or snap.get("override_allowlist") or []),
                "v2_top": row.get("v2_top", ""),
                "tier_top": row.get("tier_top", ""),
                "hard_top": row.get("hard_top", ""),
                "v2_selected": row.get("v2_selected", row.get("v2_top", "")),
                "tier_selected": row.get("tier_selected", row.get("tier_top", "")),
                "hard_selected": row.get("hard_selected", row.get("hard_top", "")),
                "tier_turnover": float(row.get("tier_turnover", 0.0) or 0.0),
                "theme_details": theme_details,
                **risk_features,
                "top_ticker_priority": ticker_priority_for(snap, boosted),
                "failure_labels": labels,
                "recommended_fixes": recommended_fixes(labels),
            }
        )

    negative = [row for row in review_rows if row["tier_minus_v2"] < 0]
    worst = sorted(review_rows, key=lambda row: row["tier_minus_v2"])[: int(args.worst_limit)]
    best = sorted(review_rows, key=lambda row: row["tier_minus_v2"], reverse=True)[: int(args.worst_limit)]
    label_counts: dict[str, int] = {}
    label_sum_delta: dict[str, float] = {}
    for row in review_rows:
        for label in row["failure_labels"]:
            label_counts[label] = label_counts.get(label, 0) + 1
            label_sum_delta[label] = label_sum_delta.get(label, 0.0) + row["tier_minus_v2"]

    return {
        "asof": args.asof,
        "attribution_json": str(args.attribution_json),
        "replay_json": str(args.replay_json),
        "active_boost_months": len(review_rows),
        "negative_boost_months": len(negative),
        "sum_tier_delta": float(np.sum([row["tier_minus_v2"] for row in review_rows])) if review_rows else 0.0,
        "avg_tier_delta": float(np.mean([row["tier_minus_v2"] for row in review_rows])) if review_rows else 0.0,
        "win_rate": float(np.mean([row["tier_minus_v2"] > 0 for row in review_rows])) if review_rows else 0.0,
        "label_summary": [
            {"label": label, "count": label_counts[label], "sum_tier_delta": label_sum_delta[label]}
            for label in sorted(label_counts, key=lambda key: (label_sum_delta[key], -label_counts[key]))
        ],
        "risk_skill_attribution": build_risk_skill_attribution(review_rows),
        "worst_months": worst,
        "best_months": best,
        "rows": review_rows,
        "next_actions": [
            "先修 historical taxonomy/regime mapping，重点覆盖 2020 的 liquidity-growth、technology、precious metals，而不是把历史行情全塞进 AI infra。",
            "把 BOOST 从简单 allowlist 改成质量门控：低 fact precision、market-only、无 override 的窄主题只能 WATCH 或 capped BOOST。",
            "对 expression_dilution 月份做 proxy/ticker 表达复盘，减少与 V2 已有 ETF 重叠导致的换手拖累。",
            "保留 positive_boost 样本，后续所有规则修改必须证明没有牺牲这些正样本。",
        ],
    }


def render_md(payload: dict[str, Any]) -> str:
    lines = [
        "# V6AB PIT BOOST Failure Review",
        "",
        f"- 日期：`{payload['asof']}`",
        f"- BOOST/tier active months：`{payload['active_boost_months']}`",
        f"- negative BOOST months：`{payload['negative_boost_months']}`",
        f"- sum tier delta：{fmt_pct(payload['sum_tier_delta'])}",
        f"- avg tier delta：{fmt_pct(payload['avg_tier_delta'])}",
        f"- win rate：{fmt_pct(payload['win_rate'])}",
        "- 模拟盘动作：`NO_CHANGE`，继续保持 `V6AB_SIM_CANDIDATE_V2_DYNAMIC_B_SIZING`。",
        "",
        "## Failure Labels",
        "",
        "| label | count | sum tier delta |",
        "| --- | ---: | ---: |",
    ]
    for row in payload["label_summary"]:
        lines.append(f"| `{row['label']}` | {row['count']} | {fmt_pct(row['sum_tier_delta'])} |")

    risk_attr = payload.get("risk_skill_attribution", {})
    lines += [
        "",
        "## Risk Skill Attribution",
        "",
        "| cohort | count | sum delta | avg | win rate | negative |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in risk_attr.get("cohorts", []):
        lines.append(
            f"| `{row.get('cohort')}` | {row.get('count', 0)} | {fmt_pct(row.get('sum_delta'))} | "
            f"{fmt_pct(row.get('avg_delta'))} | {fmt_pct(row.get('win_rate'))} | {row.get('negative_months', 0)} |"
        )
    lines += [
        "",
        "## Risk Skill Correlations",
        "",
        "| metric | corr with tier-v2 |",
        "| --- | ---: |",
    ]
    for row in risk_attr.get("correlations", [])[:8]:
        lines.append(f"| `{row.get('metric')}` | {float(row.get('corr_with_tier_delta', 0.0)):+.3f} |")

    lines += [
        "",
        "## Worst BOOST Months",
        "",
        "| date | snapshot | tier-v2 | boosted | labels | V2 selected | tier selected | turnover |",
        "| --- | --- | ---: | --- | --- | --- | --- | ---: |",
    ]
    for row in payload["worst_months"]:
        lines.append(
            f"| {row['date']} | {row.get('snapshot_asof')} | {fmt_pct(row['tier_minus_v2'])} | "
            f"`{', '.join(row.get('boost_allowlist', []))}` | `{', '.join(row.get('failure_labels', []))}` | "
            f"{row.get('v2_selected', row.get('v2_top', ''))} | {row.get('tier_selected', row.get('tier_top', ''))} | {row.get('tier_turnover', 0):.2f} |"
        )

    lines += [
        "",
        "## Evidence Detail For Worst Months",
        "",
    ]
    for row in payload["worst_months"][:8]:
        lines += [
            f"### {row['date']} ({fmt_pct(row['tier_minus_v2'])})",
            "",
            f"- BOOST：`{', '.join(row.get('boost_allowlist', []))}`",
            f"- labels：`{', '.join(row.get('failure_labels', []))}`",
            f"- V2 selected：{row.get('v2_selected', row.get('v2_top', ''))}",
            f"- tier selected：{row.get('tier_selected', row.get('tier_top', ''))}",
            "- theme scores：",
        ]
        for detail in row.get("theme_details", []):
            lines.append(
                f"  - `{detail.get('theme')}` market={detail.get('market_score', 'n/a')} "
                f"narrative={detail.get('narrative_score', 'n/a')} fundamental={detail.get('fundamental_score', 'n/a')} "
                f"history={detail.get('historical_depth_score', 'n/a')} risk={detail.get('risk_penalty', 'n/a')} "
                f"evidence={detail.get('evidence_count', 'n/a')} tier={detail.get('signal_tier', 'n/a')} "
                f"market_only={detail.get('market_only', 'n/a')}"
            )
        if row.get("top_ticker_priority"):
            tickers = ", ".join(
                f"{item.get('ticker')}:{item.get('theme')}({float(item.get('score', 0.0) or 0.0):.1f})"
                for item in row.get("top_ticker_priority", [])[:5]
            )
            lines.append(f"- ticker priority：{tickers}")
        lines.append(f"- recommended fixes：{'；'.join(row.get('recommended_fixes', []))}")
        lines.append("")

    lines += [
        "## Positive BOOST Control Samples",
        "",
        "| date | tier-v2 | boosted | V2 selected | tier selected |",
        "| --- | ---: | --- | --- | --- |",
    ]
    for row in payload["best_months"][:8]:
        lines.append(
            f"| {row['date']} | {fmt_pct(row['tier_minus_v2'])} | `{', '.join(row.get('boost_allowlist', []))}` | "
            f"{row.get('v2_selected', row.get('v2_top', ''))} | {row.get('tier_selected', row.get('tier_top', ''))} |"
        )

    lines += [
        "",
        "## Next Actions",
        "",
    ]
    lines.extend(f"- {item}" for item in payload["next_actions"])
    lines += [
        "",
        "## Interpretation",
        "",
        "- 这个报告不是为了手工挑答案，而是把失败类型制度化：后续任何规则修改都必须重新跑 PIT replay、bridge backtest、attribution 和 promotion gate。",
        "- 当前最大问题不是“方向错”，而是 BOOST 证据质量、历史主题 taxonomy、主题表达和换手控制还不够成熟。",
        "",
    ]
    return "\n".join(lines)


def write_csv(payload: dict[str, Any], path: Path) -> None:
    fields = [
        "date",
        "snapshot_asof",
        "signal_tier",
        "tier_minus_v2",
        "boost_allowlist",
        "failure_labels",
        "v2_top",
        "tier_top",
        "tier_turnover",
        "recommended_fixes",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in payload["rows"]:
            writer.writerow(
                {
                    "date": row.get("date"),
                    "snapshot_asof": row.get("snapshot_asof"),
                    "signal_tier": row.get("signal_tier"),
                    "tier_minus_v2": row.get("tier_minus_v2"),
                    "boost_allowlist": ", ".join(row.get("boost_allowlist", [])),
                    "failure_labels": ", ".join(row.get("failure_labels", [])),
                    "v2_top": row.get("v2_top", ""),
                    "tier_top": row.get("tier_top", ""),
                    "tier_turnover": row.get("tier_turnover", 0.0),
                    "recommended_fixes": " | ".join(row.get("recommended_fixes", [])),
                }
            )


def main() -> int:
    parser = argparse.ArgumentParser(description="Review PIT BOOST failure months against V2 attribution.")
    parser.add_argument("--attribution-json", type=Path, default=DEFAULT_ATTRIBUTION)
    parser.add_argument("--replay-json", type=Path, default=DEFAULT_REPLAY)
    parser.add_argument("--asof", default=str(date.today()))
    parser.add_argument("--worst-limit", type=int, default=12)
    args = parser.parse_args()

    payload = build_review(args)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    json_path = OUT_DIR / "latest.json"
    md_path = OUT_DIR / "latest.md"
    csv_path = OUT_DIR / "latest.csv"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_md(payload), encoding="utf-8")
    write_csv(payload, csv_path)

    (REPORT_ROOT / "V6AB_PIT_Boost_Failure_Review_LATEST.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (REPORT_ROOT / "V6AB_PIT_Boost_Failure_Review_LATEST.md").write_text(render_md(payload), encoding="utf-8")
    print(json.dumps({"json": str(json_path), "md": str(md_path), "csv": str(csv_path)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
