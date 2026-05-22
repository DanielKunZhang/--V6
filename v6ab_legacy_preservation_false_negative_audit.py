#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import v6ab_legacy_winner_preservation_experiment as legacy


ROOT = Path(__file__).resolve().parent
DESKTOP_ROOT = Path("/Users/zhangkun/Desktop/AI个人投资公司")
REPORT_ROOT = DESKTOP_ROOT / "报表输出" / "LATEST"
OUT_DIR = ROOT / "backtest_results" / "v6ab_legacy_preservation_false_negative_audit"
DEFAULT_EXPERIMENT = ROOT / "backtest_results" / "v6ab_legacy_winner_preservation_experiment" / "latest.json"


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"missing input: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def fmt_pct(value: float | None) -> str:
    if value is None or not np.isfinite(value):
        return "n/a"
    return f"{value:+.2%}"


def rows_by_name(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(row.get("candidate")): row for row in payload.get("rows", [])}


def build_audit(payload: dict[str, Any]) -> dict[str, Any]:
    v1_by_date = {row["date"]: row for row in payload.get("month_review", [])}
    qualified_by_date = {row["date"]: row for row in payload.get("qualified_month_review", [])}
    false_negative_rows = []
    for raw_date, v1_row in v1_by_date.items():
        if raw_date in qualified_by_date:
            continue
        delta_if_skipped = -float(v1_row.get("legacy_guarded_minus_original", 0.0) or 0.0)
        decision = "SKIP_WAS_CORRECT" if delta_if_skipped >= -0.005 else "POSSIBLE_FALSE_NEGATIVE"
        if delta_if_skipped < -0.02:
            decision = "FALSE_NEGATIVE_RISK"
        false_negative_rows.append(
            {
                "date": raw_date,
                "preservation_candidates": v1_row.get("preserved_themes", []),
                "v2_next_ret": v1_row.get("v2_next_ret"),
                "original_guarded_next_ret": v1_row.get("original_guarded_next_ret"),
                "v1_guarded_next_ret": v1_row.get("legacy_guarded_next_ret"),
                "qualified_skipped_delta_vs_original": delta_if_skipped,
                "v1_guard_delta_vs_original": v1_row.get("legacy_guarded_minus_original"),
                "decision": decision,
                "v2_selected": v1_row.get("v2_selected", ""),
                "original_guarded_selected": v1_row.get("original_guarded_selected", ""),
                "v1_guarded_selected": v1_row.get("legacy_guarded_selected", ""),
            }
        )
    by_name = rows_by_name(payload)
    qualified = by_name.get("legacy_preserve_qualified_v6ab_dynamic_b", {})
    original = by_name.get("original_pit_guarded_v6ab_dynamic_b", {})
    base = by_name.get("baseline_v2_v6ab_dynamic_b", {})
    qs = qualified.get("stats", {})
    os = original.get("stats", {})
    bs = base.get("stats", {})
    risk_rows = [row for row in false_negative_rows if row["decision"] == "FALSE_NEGATIVE_RISK"]
    possible_rows = [row for row in false_negative_rows if row["decision"] == "POSSIBLE_FALSE_NEGATIVE"]
    decision = "PASS_FALSE_NEGATIVE_AUDIT"
    action = "qualified v2 未发现明显漏保，保留 RESEARCH_OVERLAY；下一步做更严格 promotion gate。"
    if risk_rows:
        decision = "FAIL_FALSE_NEGATIVE_AUDIT"
        action = "qualified v2 存在明显漏保风险，必须补资格条件后再继续。"
    elif possible_rows:
        decision = "WATCH_FALSE_NEGATIVE_RISK"
        action = "qualified v2 存在轻微漏保样本，需继续观察，不晋级。"
    return {
        "asof": payload.get("asof"),
        "experiment_json": str(DEFAULT_EXPERIMENT),
        "decision": {
            "tier": decision,
            "action": action,
            "false_negative_count": len(false_negative_rows),
            "false_negative_risk_count": len(risk_rows),
            "possible_false_negative_count": len(possible_rows),
            "qualified_ann_vs_v2": float(qs.get("ann_ret", 0.0) or 0.0) - float(bs.get("ann_ret", 0.0) or 0.0),
            "qualified_ann_vs_original_pit": float(qs.get("ann_ret", 0.0) or 0.0) - float(os.get("ann_ret", 0.0) or 0.0),
            "qualified_sharpe_vs_v2": float(qs.get("sharpe", 0.0) or 0.0) - float(bs.get("sharpe", 0.0) or 0.0),
        },
        "false_negative_rows": sorted(false_negative_rows, key=lambda row: float(row["qualified_skipped_delta_vs_original"])),
        "interpretation": [
            "本审计只检查 qualified v2 相对 v1 放弃保护的月份，是否漏保了本该保护的 legacy winner。",
            "delta 定义：qualified 跳过保护后相对 original PIT 的结果变化；正数说明跳过保护是对的，负数说明可能漏保。",
            "审计不改变模拟盘，只决定 qualified v2 是否有资格进入更严格 promotion gate。",
        ],
    }


def render_md(payload: dict[str, Any]) -> str:
    decision = payload["decision"]
    lines = [
        "# V6AB Legacy Preservation False Negative Audit",
        "",
        f"- 日期：`{payload['asof']}`",
        "- 模拟盘动作：`NO_CHANGE`。",
        f"- 决策：`{decision['tier']}` — {decision['action']}",
        f"- qualified ann vs V2：`{fmt_pct(decision['qualified_ann_vs_v2'])}`",
        f"- qualified ann vs original PIT：`{fmt_pct(decision['qualified_ann_vs_original_pit'])}`",
        f"- skipped protection months：`{decision['false_negative_count']}`",
        f"- false negative risk：`{decision['false_negative_risk_count']}`",
        "",
        "## Skipped Protection Rows",
        "",
        "| date | skipped candidates | skipped delta vs PIT | decision | V2 selected | PIT selected | v1 guarded selected |",
        "| --- | --- | ---: | --- | --- | --- | --- |",
    ]
    for row in payload.get("false_negative_rows", []):
        lines.append(
            f"| `{row['date']}` | `{', '.join(row.get('preservation_candidates', []))}` | "
            f"{fmt_pct(row.get('qualified_skipped_delta_vs_original'))} | `{row.get('decision')}` | "
            f"{row.get('v2_selected', '')} | {row.get('original_guarded_selected', '')} | {row.get('v1_guarded_selected', '')} |"
        )
    lines += ["", "## Interpretation", ""]
    lines.extend(f"- {item}" for item in payload.get("interpretation", []))
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit false negatives introduced by V6AB qualified legacy preservation.")
    parser.add_argument("--asof", default=str(date.today()))
    parser.add_argument("--experiment-json", type=Path, default=DEFAULT_EXPERIMENT)
    parser.add_argument("--output-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    experiment = load_json(args.experiment_json)
    payload = build_audit(experiment)
    payload["asof"] = args.asof
    md = render_md(payload)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "latest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (args.output_dir / "latest.md").write_text(md, encoding="utf-8")
    pd.DataFrame(payload["false_negative_rows"]).to_csv(args.output_dir / "latest.csv", index=False)
    (REPORT_ROOT / "V6AB_Legacy_Preservation_False_Negative_Audit_LATEST.md").write_text(md, encoding="utf-8")
    (REPORT_ROOT / "V6AB_Legacy_Preservation_False_Negative_Audit_LATEST.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
