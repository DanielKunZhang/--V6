#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any, Callable

import numpy as np


ROOT = Path(__file__).resolve().parent
DESKTOP_ROOT = Path("/Users/zhangkun/Desktop/AI个人投资公司")
REPORT_ROOT = DESKTOP_ROOT / "报表输出" / "LATEST"
OUT_DIR = ROOT / "backtest_results" / "v6ab_boost_gate_experiment"
DEFAULT_REVIEW = ROOT / "backtest_results" / "v6ab_pit_boost_failure_review" / "latest.json"


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"missing input: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def fmt_pct(value: float | None) -> str:
    if value is None or not np.isfinite(value):
        return "n/a"
    return f"{value:+.2%}"


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


def all_market_only_without_facts(row: dict[str, Any]) -> bool:
    details = row.get("theme_details", [])
    if not details:
        return False
    return all(
        bool(detail.get("market_only"))
        and float(detail.get("evidence_count", 0.0) or 0.0) <= 2
        and float(detail.get("fundamental_score", 0.0) or 0.0) <= 0
        for detail in details
    )


def has_weak_pre2022_ai(row: dict[str, Any]) -> bool:
    year = int(str(row.get("date", "9999"))[:4])
    if year >= 2022:
        return False
    for detail in row.get("theme_details", []):
        theme = str(detail.get("theme", ""))
        if not theme.startswith("ai_"):
            continue
        evidence = float(detail.get("evidence_count", 0.0) or 0.0)
        fundamental = float(detail.get("fundamental_score", 0.0) or 0.0)
        historical = float(detail.get("historical_depth_score", 0.0) or 0.0)
        if evidence < 8 or fundamental < 18 or historical < 25:
            return True
    return False


def narrow_weak_fact(row: dict[str, Any]) -> bool:
    boosted = row.get("boost_allowlist", [])
    if len(boosted) != 1:
        return False
    return min_detail(row, "narrative_score") < 18 or min_detail(row, "fundamental_score") < 24


def defensive_conflict(row: dict[str, Any]) -> bool:
    defensive = {"precious_metals", "energy_resources"}
    v2_top = {part.split(":", 1)[0].strip() for part in str(row.get("v2_top", "")).split(",") if ":" in part}
    tier_top = {part.split(":", 1)[0].strip() for part in str(row.get("tier_top", "")).split(",") if ":" in part}
    boosted = set(row.get("boost_allowlist", []))
    defensive_v2 = v2_top & defensive
    if not defensive_v2:
        return False
    if defensive_v2 & tier_top:
        return False
    return not (boosted & defensive)


def high_turnover_expression(row: dict[str, Any]) -> bool:
    return float(row.get("tier_turnover", 0.0) or 0.0) > 1.0 and not row.get("override_allowlist")


def weak_fact_precision(row: dict[str, Any]) -> bool:
    return (
        min_detail(row, "narrative_score") < 15
        or min_detail(row, "fundamental_score") < 15
        or max_detail(row, "risk_penalty") > 25
    )


def evaluate(rows: list[dict[str, Any]], name: str, drop_rule: Callable[[dict[str, Any]], bool]) -> dict[str, Any]:
    kept = [row for row in rows if not drop_rule(row)]
    dropped = [row for row in rows if drop_rule(row)]
    dropped_positive = [row for row in dropped if float(row.get("tier_minus_v2", 0.0) or 0.0) > 0]
    dropped_negative = [row for row in dropped if float(row.get("tier_minus_v2", 0.0) or 0.0) < 0]
    kept_deltas = [float(row.get("tier_minus_v2", 0.0) or 0.0) for row in kept]
    dropped_deltas = [float(row.get("tier_minus_v2", 0.0) or 0.0) for row in dropped]
    return {
        "candidate": name,
        "kept_months": len(kept),
        "dropped_months": len(dropped),
        "dropped_positive_months": len(dropped_positive),
        "dropped_negative_months": len(dropped_negative),
        "kept_sum_delta": float(np.sum(kept_deltas)) if kept_deltas else 0.0,
        "dropped_sum_delta": float(np.sum(dropped_deltas)) if dropped_deltas else 0.0,
        "kept_win_rate": float(np.mean([value > 0 for value in kept_deltas])) if kept_deltas else 0.0,
        "positive_damage": float(np.sum([row["tier_minus_v2"] for row in dropped_positive])) if dropped_positive else 0.0,
        "negative_removed": float(-np.sum([row["tier_minus_v2"] for row in dropped_negative])) if dropped_negative else 0.0,
        "dropped_dates": [row.get("date") for row in dropped],
    }


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    review = load_json(args.review_json)
    rows = review.get("rows", [])
    rules: list[tuple[str, Callable[[dict[str, Any]], bool]]] = [
        ("baseline_keep_all", lambda row: False),
        ("drop_all_market_only_without_facts", all_market_only_without_facts),
        ("drop_weak_pre2022_ai", has_weak_pre2022_ai),
        ("drop_narrow_weak_fact", narrow_weak_fact),
        ("drop_ex_ante_defensive_displacement", defensive_conflict),
        ("drop_ex_ante_high_turnover_no_override", high_turnover_expression),
        ("drop_weak_fact_precision", weak_fact_precision),
        (
            "drop_balanced_risk_set",
            lambda row: (
                has_weak_pre2022_ai(row)
                or narrow_weak_fact(row)
                or high_turnover_expression(row)
                or (defensive_conflict(row) and weak_fact_precision(row))
            ),
        ),
    ]
    candidates = [evaluate(rows, name, rule) for name, rule in rules]
    baseline = candidates[0]
    for row in candidates:
        row["improvement_vs_baseline"] = row["kept_sum_delta"] - baseline["kept_sum_delta"]
        row["damage_ratio"] = (
            row["positive_damage"] / row["negative_removed"] if row["negative_removed"] > 0 else None
        )
    ranked = sorted(candidates, key=lambda row: (row["kept_sum_delta"], -row["positive_damage"]), reverse=True)
    return {
        "asof": args.asof,
        "review_json": str(args.review_json),
        "baseline_sum_delta": baseline["kept_sum_delta"],
        "candidates": candidates,
        "ranked": ranked,
        "decision_rule": "候选门控只有在 kept_sum_delta 改善、positive_damage 可控、kept_months 不过低时，才允许进入正式 classifier/backtest。",
    }


def render_md(payload: dict[str, Any]) -> str:
    lines = [
        "# V6AB BOOST Gate Experiment",
        "",
        f"- 日期：`{payload['asof']}`",
        f"- baseline BOOST sum delta：{fmt_pct(payload['baseline_sum_delta'])}",
        "- 用途：离线评估候选门控是否误伤正样本；本报告不改变 classifier、不改变模拟盘。",
        "",
        "## Candidate Rules",
        "",
        "| candidate | kept | dropped | drop + | drop - | kept sum | improvement | positive damage | negative removed | damage ratio | kept win |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in payload["ranked"]:
        ratio = row.get("damage_ratio")
        ratio_text = "n/a" if ratio is None else f"{ratio:.2f}"
        lines.append(
            f"| `{row['candidate']}` | {row['kept_months']} | {row['dropped_months']} | "
            f"{row['dropped_positive_months']} | {row['dropped_negative_months']} | "
            f"{fmt_pct(row['kept_sum_delta'])} | {fmt_pct(row['improvement_vs_baseline'])} | "
            f"{fmt_pct(row['positive_damage'])} | {fmt_pct(row['negative_removed'])} | {ratio_text} | "
            f"{fmt_pct(row['kept_win_rate'])} |"
        )
    lines += [
        "",
        "## Interpretation",
        "",
        f"- {payload['decision_rule']}",
        "- 如果一个规则通过减少 active 月份让结果更差，说明它太严或切错样本，必须回退。",
        "- 候选规则只能使用当时可见的市场结构、theme scores、evidence scores、proposed turnover 和 override 状态；不能使用事后 failure label。",
        "- 下一步应优先选择“低误伤、真减少负贡献”的 ex-ante 门控，再进入完整 PIT replay / bridge / promotion gate。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline evaluate candidate BOOST gates before changing classifier rules.")
    parser.add_argument("--review-json", type=Path, default=DEFAULT_REVIEW)
    parser.add_argument("--asof", default=str(date.today()))
    args = parser.parse_args()

    payload = build_payload(args)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    md = render_md(payload)
    (OUT_DIR / "latest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT_DIR / "latest.md").write_text(md, encoding="utf-8")
    (REPORT_ROOT / "V6AB_Boost_Gate_Experiment_LATEST.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (REPORT_ROOT / "V6AB_Boost_Gate_Experiment_LATEST.md").write_text(md, encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
