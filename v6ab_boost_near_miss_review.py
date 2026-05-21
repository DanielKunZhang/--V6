#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from bisect import bisect_right
from datetime import date
from pathlib import Path
from typing import Any, Callable

import numpy as np


ROOT = Path(__file__).resolve().parent
DESKTOP_ROOT = Path("/Users/zhangkun/Desktop/AI个人投资公司")
REPORT_ROOT = DESKTOP_ROOT / "报表输出" / "LATEST"
OUT_DIR = ROOT / "backtest_results" / "v6ab_boost_near_miss_review"
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


def parse_selected(text: str) -> set[str]:
    out: set[str] = set()
    for part in str(text or "").split(","):
        part = part.strip()
        if not part or ":" not in part:
            continue
        out.add(part.split(":", 1)[0].strip())
    return out


def max_detail(row: dict[str, Any], key: str) -> float:
    values = []
    for detail in row.get("theme_details", []):
        try:
            values.append(float(detail.get(key, 0.0) or 0.0))
        except Exception:
            pass
    return max(values) if values else 0.0


def min_detail(row: dict[str, Any], key: str) -> float:
    values = []
    for detail in row.get("theme_details", []):
        try:
            values.append(float(detail.get(key, 0.0) or 0.0))
        except Exception:
            pass
    return min(values) if values else 0.0


def any_detail(row: dict[str, Any], key: str) -> bool:
    return any(bool(detail.get(key)) for detail in row.get("theme_details", []))


def quality_summary(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "max_market": max_detail(row, "market_score"),
        "max_narrative": max_detail(row, "narrative_score"),
        "max_fundamental": max_detail(row, "fundamental_score"),
        "max_history": max_detail(row, "historical_depth_score"),
        "max_evidence": max_detail(row, "evidence_count"),
        "max_breadth": max_detail(row, "breadth"),
        "max_risk": max_detail(row, "risk_penalty"),
        "min_fundamental": min_detail(row, "fundamental_score"),
        "any_market_only": any_detail(row, "market_only"),
    }


def low_turnover_fact_backed(row: dict[str, Any]) -> bool:
    q = row["quality"]
    return (
        float(row.get("overlay_turnover", 0.0) or 0.0) <= 0.80
        and q["max_market"] >= 75
        and q["max_evidence"] >= 3
        and (q["max_fundamental"] >= 20 or q["max_narrative"] >= 20 or q["max_history"] >= 25)
        and q["max_risk"] < 25
    )


def low_turnover_market_confirmed(row: dict[str, Any]) -> bool:
    q = row["quality"]
    return (
        float(row.get("overlay_turnover", 0.0) or 0.0) <= 0.80
        and q["max_market"] >= 85
        and q["max_breadth"] >= 0.80
        and q["max_risk"] < 20
    )


def low_turnover_theme_overlap(row: dict[str, Any]) -> bool:
    v2_selected = parse_selected(row.get("v2_selected", ""))
    allowlist = set(row.get("allowlist", []))
    return float(row.get("overlay_turnover", 0.0) or 0.0) <= 0.80 and bool(v2_selected & allowlist)


def low_turnover_fact_or_overlap(row: dict[str, Any]) -> bool:
    return low_turnover_fact_backed(row) or low_turnover_theme_overlap(row)


def evaluate(rows: list[dict[str, Any]], name: str, rule: Callable[[dict[str, Any]], bool]) -> dict[str, Any]:
    picked = [row for row in rows if rule(row)]
    deltas = [float(row.get("overlay_minus_v2", 0.0) or 0.0) for row in picked]
    positive = [value for value in deltas if value > 0]
    negative = [value for value in deltas if value < 0]
    return {
        "candidate": name,
        "picked_months": len(picked),
        "sum_overlay_delta": float(np.sum(deltas)) if deltas else 0.0,
        "avg_overlay_delta": float(np.mean(deltas)) if deltas else 0.0,
        "win_rate": float(np.mean([value > 0 for value in deltas])) if deltas else 0.0,
        "positive_sum": float(np.sum(positive)) if positive else 0.0,
        "negative_sum": float(np.sum(negative)) if negative else 0.0,
        "picked_dates": [row.get("date") for row in picked],
    }


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    attribution = load_json(args.attribution_json)
    replay = load_json(args.replay_json)
    asofs, snapshots = snapshot_index(replay.get("snapshots", []))
    rows: list[dict[str, Any]] = []
    for attr in attribution.get("rows", []):
        if not attr.get("pit_active"):
            continue
        if attr.get("tier_active") or attr.get("pit_boost_allowlist"):
            continue
        allowlist = list(attr.get("pit_allowlist") or [])
        if not allowlist:
            continue
        snap = snapshot_for_date(asofs, snapshots, str(attr.get("date")))
        by_theme = theme_map(snap)
        details = [by_theme.get(theme, {"theme": theme}) for theme in allowlist]
        row = {
            "date": attr.get("date"),
            "snapshot_asof": snap.get("asof"),
            "allowlist": allowlist,
            "overlay_minus_v2": float(attr.get("overlay_minus_v2", 0.0) or 0.0),
            "hard_minus_v2": float(attr.get("hard_minus_v2", 0.0) or 0.0),
            "overlay_turnover": float(attr.get("overlay_turnover", 0.0) or 0.0),
            "v2_selected": attr.get("v2_selected", attr.get("v2_top", "")),
            "overlay_selected": attr.get("overlay_selected", attr.get("overlay_top", "")),
            "theme_details": details,
        }
        row["quality"] = quality_summary(row)
        rows.append(row)

    rules: list[tuple[str, Callable[[dict[str, Any]], bool]]] = [
        ("low_turnover_fact_backed", low_turnover_fact_backed),
        ("low_turnover_market_confirmed", low_turnover_market_confirmed),
        ("low_turnover_theme_overlap", low_turnover_theme_overlap),
        ("low_turnover_fact_or_overlap", low_turnover_fact_or_overlap),
    ]
    cohorts = [evaluate(rows, name, rule) for name, rule in rules]
    return {
        "asof": args.asof,
        "attribution_json": str(args.attribution_json),
        "replay_json": str(args.replay_json),
        "near_miss_months": len(rows),
        "overlay_sum_delta_all": float(np.sum([row["overlay_minus_v2"] for row in rows])) if rows else 0.0,
        "overlay_win_rate_all": float(np.mean([row["overlay_minus_v2"] > 0 for row in rows])) if rows else 0.0,
        "cohorts": cohorts,
        "best_near_misses": sorted(rows, key=lambda row: row["overlay_minus_v2"], reverse=True)[: int(args.limit)],
        "worst_near_misses": sorted(rows, key=lambda row: row["overlay_minus_v2"])[: int(args.limit)],
        "rows": rows,
        "interpretation": [
            "near-miss 指 PIT 有 allowlist 但还未升为 BOOST 的 WATCH 月份。",
            "本报告只评估是否存在可解释的低换手 BOOST 候选，不改变 classifier 和模拟盘。",
            "只有 ex-ante cohort 同时满足样本数、正贡献、低误伤，才值得进入正式 bridge backtest。",
        ],
    }


def render_md(payload: dict[str, Any]) -> str:
    lines = [
        "# V6AB BOOST Near-Miss Review",
        "",
        f"- 日期：`{payload['asof']}`",
        f"- near-miss months：`{payload['near_miss_months']}`",
        f"- overlay sum delta all：{fmt_pct(payload['overlay_sum_delta_all'])}",
        f"- overlay win rate all：{fmt_pct(payload['overlay_win_rate_all'])}",
        "- 模拟盘动作：`NO_CHANGE`。",
        "",
        "## Ex-Ante Cohorts",
        "",
        "| cohort | picked | sum overlay delta | avg | win rate | positive | negative | dates |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in sorted(payload["cohorts"], key=lambda item: item["sum_overlay_delta"], reverse=True):
        lines.append(
            f"| `{row['candidate']}` | {row['picked_months']} | {fmt_pct(row['sum_overlay_delta'])} | "
            f"{fmt_pct(row['avg_overlay_delta'])} | {fmt_pct(row['win_rate'])} | "
            f"{fmt_pct(row['positive_sum'])} | {fmt_pct(row['negative_sum'])} | "
            f"`{', '.join(row['picked_dates'][:12])}` |"
        )

    lines += [
        "",
        "## Best Near-Misses",
        "",
        "| date | allowlist | overlay-v2 | hard-v2 | turnover | quality | V2 selected | overlay selected |",
        "| --- | --- | ---: | ---: | ---: | --- | --- | --- |",
    ]
    for row in payload["best_near_misses"]:
        q = row["quality"]
        quality = (
            f"mkt={q['max_market']:.1f}, fact={max(q['max_fundamental'], q['max_narrative'], q['max_history']):.1f}, "
            f"ev={q['max_evidence']:.0f}, risk={q['max_risk']:.1f}"
        )
        lines.append(
            f"| {row['date']} | `{', '.join(row['allowlist'])}` | {fmt_pct(row['overlay_minus_v2'])} | "
            f"{fmt_pct(row['hard_minus_v2'])} | {row['overlay_turnover']:.2f} | {quality} | "
            f"{row.get('v2_selected', '')} | {row.get('overlay_selected', '')} |"
        )

    lines += [
        "",
        "## Worst Near-Misses",
        "",
        "| date | allowlist | overlay-v2 | hard-v2 | turnover | quality | V2 selected | overlay selected |",
        "| --- | --- | ---: | ---: | ---: | --- | --- | --- |",
    ]
    for row in payload["worst_near_misses"]:
        q = row["quality"]
        quality = (
            f"mkt={q['max_market']:.1f}, fact={max(q['max_fundamental'], q['max_narrative'], q['max_history']):.1f}, "
            f"ev={q['max_evidence']:.0f}, risk={q['max_risk']:.1f}"
        )
        lines.append(
            f"| {row['date']} | `{', '.join(row['allowlist'])}` | {fmt_pct(row['overlay_minus_v2'])} | "
            f"{fmt_pct(row['hard_minus_v2'])} | {row['overlay_turnover']:.2f} | {quality} | "
            f"{row.get('v2_selected', '')} | {row.get('overlay_selected', '')} |"
        )

    lines += [
        "",
        "## Interpretation",
        "",
    ]
    lines.extend(f"- {item}" for item in payload["interpretation"])
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Review PIT WATCH near-misses that may deserve BOOST research.")
    parser.add_argument("--asof", default=str(date.today()))
    parser.add_argument("--attribution-json", type=Path, default=DEFAULT_ATTRIBUTION)
    parser.add_argument("--replay-json", type=Path, default=DEFAULT_REPLAY)
    parser.add_argument("--limit", type=int, default=12)
    parser.add_argument("--output-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    payload = build_payload(args)
    md = render_md(payload)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "latest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.output_dir / "latest.md").write_text(md, encoding="utf-8")
    (REPORT_ROOT / "V6AB_Boost_Near_Miss_Review_LATEST.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (REPORT_ROOT / "V6AB_Boost_Near_Miss_Review_LATEST.md").write_text(md, encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
