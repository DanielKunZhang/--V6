#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parent
DESKTOP_ROOT = Path("/Users/zhangkun/Desktop/AI个人投资公司")
REPORT_ROOT = DESKTOP_ROOT / "报表输出" / "LATEST"
OUT_DIR = ROOT / "backtest_results" / "v6ab_override_readiness"
DEFAULT_REPLAY = ROOT / "backtest_results" / "v6ab_daily_evolution" / "pit_replay" / "latest_pit_classifier_replay.json"
DEFAULT_ATTRIBUTION = ROOT / "backtest_results" / "v6ab_daily_evolution" / "latest_pit_vs_v2_attribution.json"


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"missing input: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def fmt_pct(value: float | None) -> str:
    if value is None or not np.isfinite(value):
        return "n/a"
    return f"{value:+.2%}"


def override_ready_theme(row: dict[str, Any]) -> bool:
    if row.get("market_only"):
        return False
    return (
        float(row.get("market_score", 0.0) or 0.0) >= 90
        and float(row.get("breadth", 0.0) or 0.0) >= 0.80
        and int(row.get("evidence_count", 0) or 0) >= 25
        and float(row.get("fundamental_score", 0.0) or 0.0) >= 20
        and float(row.get("historical_depth_score", 0.0) or 0.0) >= 28
        and float(row.get("risk_penalty", 0.0) or 0.0) <= 5
        and float(row.get("mainline_score", 0.0) or 0.0) >= 58
    )


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    replay = load_json(args.replay_json)
    attribution = load_json(args.attribution_json)
    attr_by_date = {row.get("date"): row for row in attribution.get("rows", [])}
    rows: list[dict[str, Any]] = []
    for snap in replay.get("snapshots", []):
        themes = [row for row in snap.get("themes", []) if override_ready_theme(row)]
        if not themes:
            continue
        attr = attr_by_date.get(snap.get("asof"), {})
        rows.append(
            {
                "date": snap.get("asof"),
                "override_ready_themes": [row.get("theme") for row in themes],
                "theme_details": themes,
                "hard_minus_v2": float(attr.get("hard_minus_v2", 0.0) or 0.0),
                "overlay_minus_v2": float(attr.get("overlay_minus_v2", 0.0) or 0.0),
                "tier_minus_v2": float(attr.get("tier_minus_v2", 0.0) or 0.0),
                "guarded_minus_v2": float(attr.get("guarded_minus_v2", 0.0) or 0.0),
                "hard_selected": attr.get("hard_selected", ""),
                "tier_selected": attr.get("tier_selected", ""),
                "guarded_selected": attr.get("guarded_selected", ""),
                "v2_selected": attr.get("v2_selected", ""),
            }
        )
    hard_deltas = [row["hard_minus_v2"] for row in rows]
    overlay_deltas = [row["overlay_minus_v2"] for row in rows]
    guarded_deltas = [row["guarded_minus_v2"] for row in rows]
    return {
        "asof": args.asof,
        "replay_json": str(args.replay_json),
        "attribution_json": str(args.attribution_json),
        "candidate_months": len(rows),
        "hard_sum_delta": float(np.sum(hard_deltas)) if hard_deltas else 0.0,
        "hard_win_rate": float(np.mean([value > 0 for value in hard_deltas])) if hard_deltas else 0.0,
        "overlay_sum_delta": float(np.sum(overlay_deltas)) if overlay_deltas else 0.0,
        "guarded_sum_delta": float(np.sum(guarded_deltas)) if guarded_deltas else 0.0,
        "rows": rows,
        "decision": "NO_OVERRIDE_PROMOTION" if not rows or float(np.sum(hard_deltas)) <= 0 else "REVIEW_OVERRIDE_RULE",
        "interpretation": [
            "OVERRIDE 不能只看单主题市场/事实强度；必须证明排他替换 V2 比 overlay/guarded 更好。",
            "若 hard replacement 在候选月份整体为负，说明该证据只能支持 BOOST/overlay，不能支持 OVERRIDE。",
        ],
    }


def render_md(payload: dict[str, Any]) -> str:
    lines = [
        "# V6AB OVERRIDE Readiness Review",
        "",
        f"- 日期：`{payload['asof']}`",
        f"- candidate months：`{payload['candidate_months']}`",
        f"- hard sum delta：{fmt_pct(payload['hard_sum_delta'])}",
        f"- hard win rate：{fmt_pct(payload['hard_win_rate'])}",
        f"- overlay sum delta：{fmt_pct(payload['overlay_sum_delta'])}",
        f"- guarded sum delta：{fmt_pct(payload['guarded_sum_delta'])}",
        f"- decision：`{payload['decision']}`",
        "- 模拟盘动作：`NO_CHANGE`。",
        "",
        "## Candidate Months",
        "",
        "| date | themes | hard-v2 | overlay-v2 | tier-v2 | guarded-v2 | V2 selected | hard selected | guarded selected |",
        "| --- | --- | ---: | ---: | ---: | ---: | --- | --- | --- |",
    ]
    for row in payload["rows"]:
        lines.append(
            f"| {row['date']} | `{', '.join(row['override_ready_themes'])}` | {fmt_pct(row['hard_minus_v2'])} | "
            f"{fmt_pct(row['overlay_minus_v2'])} | {fmt_pct(row['tier_minus_v2'])} | {fmt_pct(row['guarded_minus_v2'])} | "
            f"{row.get('v2_selected', '')} | {row.get('hard_selected', '')} | {row.get('guarded_selected', '')} |"
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
    parser = argparse.ArgumentParser(description="Review whether PIT evidence is strong enough for OVERRIDE.")
    parser.add_argument("--asof", default=str(date.today()))
    parser.add_argument("--replay-json", type=Path, default=DEFAULT_REPLAY)
    parser.add_argument("--attribution-json", type=Path, default=DEFAULT_ATTRIBUTION)
    parser.add_argument("--output-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    payload = build_payload(args)
    md = render_md(payload)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "latest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.output_dir / "latest.md").write_text(md, encoding="utf-8")
    (REPORT_ROOT / "V6AB_Override_Readiness_LATEST.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (REPORT_ROOT / "V6AB_Override_Readiness_LATEST.md").write_text(md, encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
