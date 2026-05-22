#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parent
DESKTOP_ROOT = Path("/Users/zhangkun/Desktop/AI个人投资公司")
REPORT_ROOT = DESKTOP_ROOT / "报表输出" / "LATEST"
OUT_DIR = ROOT / "backtest_results" / "a_share_radar_v6ab_transfer_review"

DEFAULT_PLAN_JSON = REPORT_ROOT / "A股短线Radar下周一计划_LATEST.json"
DEFAULT_THEMES_CSV = REPORT_ROOT / "A股短线Radar主线评分_LATEST.csv"
DEFAULT_CANDIDATES_CSV = REPORT_ROOT / "A股短线Radar候选_LATEST.csv"
DEFAULT_REVIEW_JSON = REPORT_ROOT / "A股短线Radar复盘_LATEST.json"
DEFAULT_FEEDBACK_JSON = REPORT_ROOT / "A股短线Radar复盘反哺_LATEST.json"
DEFAULT_STRICT_TRACKER_JSON = REPORT_ROOT / "A股短线Radar规则过严样本追踪_LATEST.json"

NOISE_TOKENS = [
    "仅有level a快照",
    "需补k线",
    "互动易",
    "蹭热点",
    "概念",
    "传闻",
    "未验证",
]
REALITY_TOKENS = [
    "订单",
    "业绩",
    "涨停潮",
    "成交额",
    "放量",
    "主升",
    "国产替代",
    "政策",
]


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def to_float(value: Any, default: float = 0.0) -> float:
    try:
        if pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def quality_from_text(text: str) -> tuple[int, list[str], list[str]]:
    lower = text.lower()
    noise = [token for token in NOISE_TOKENS if token in lower]
    reality = [token for token in REALITY_TOKENS if token in lower]
    score = 50 + min(len(reality), 4) * 10 - min(len(noise), 4) * 12
    return max(0, min(100, score)), reality, noise


def evaluate_theme(row: dict[str, Any]) -> dict[str, Any]:
    score = to_float(row.get("score"))
    phase = str(row.get("phase", ""))
    reason = str(row.get("reason", ""))
    precision, reality, noise = quality_from_text(reason + " " + phase)
    member_count = to_float(row.get("member_count"))
    hot_count = to_float(row.get("hot_count"))
    limit_count = to_float(row.get("limit_proxy_count"))
    breadth = hot_count / member_count if member_count > 0 else 0.0
    if score >= 30 and "主升" in phase and breadth >= 0.50 and precision >= 55:
        tier = "MAINLINE_WATCH_PLUS"
        action = "可作为短周期主线重点观察，但仍需候选买点验证。"
    elif score >= 24 and "主升" in phase:
        tier = "MAINLINE_WATCH"
        action = "主线成立但强度或事实精度不足，观察为主。"
    else:
        tier = "ROTATION_OR_ARCHIVE"
        action = "只归档或复盘，不作为训练仓主线。"
    return {
        "theme": str(row.get("theme", "")),
        "theme_score": score,
        "phase": phase,
        "member_count": int(member_count),
        "hot_count": int(hot_count),
        "limit_proxy_count": int(limit_count),
        "breadth": round(breadth, 4),
        "fact_precision_score": precision,
        "reality_tokens": reality,
        "noise_tokens": noise,
        "tier": tier,
        "action": action,
    }


def evaluate_candidate(row: dict[str, Any]) -> dict[str, Any]:
    reason_text = " ".join(
        str(row.get(col, ""))
        for col in ["reason", "entry_trigger", "no_buy_condition", "action_detail", "exit_detail"]
    )
    precision, reality, noise = quality_from_text(reason_text)
    mode = str(row.get("mode", ""))
    action = str(row.get("action", ""))
    role = str(row.get("role", ""))
    amount = to_float(row.get("amount_rmb"))
    has_entry = to_float(row.get("pullback_buy")) > 0 or to_float(row.get("breakout_buy")) > 0
    has_stop = to_float(row.get("stop")) > 0 or to_float(row.get("hard_stop")) > 0
    has_no_buy = bool(str(row.get("no_buy_condition", "")).strip())
    high_accel_guard = "高开" in str(row.get("no_buy_condition", "")) or "不追" in action
    role_ok = role in {"龙头", "中军"}
    liquidity_ok = amount >= 2_000_000_000

    expression_score = 0
    expression_score += 25 if has_entry else 0
    expression_score += 25 if has_stop else 0
    expression_score += 20 if has_no_buy else 0
    expression_score += 15 if high_accel_guard else 0
    expression_score += 15 if liquidity_ok else 0
    expression_score = min(100, expression_score)

    if "WATCH_ONLY" in mode or "仅实时观察" in action:
        tier = "WATCH_ONLY"
        next_action = "继续只观察；若复盘显示规则过严，再进入 WATCH_ONLY_PLUS。"
    elif role_ok and expression_score >= 80 and precision >= 50 and liquidity_ok:
        tier = "PAPER_TRADE_READY"
        next_action = "可用于模拟触发统计，仍不代表真实自动交易。"
    else:
        tier = "WATCH"
        next_action = "保留观察，补足买点/止损/禁买条件或事实精度。"
    return {
        "symbol": str(row.get("symbol", "")),
        "name": str(row.get("name", "")),
        "theme": str(row.get("theme", "")),
        "role": role,
        "mode": mode,
        "action": action,
        "score": to_float(row.get("score")),
        "theme_score": to_float(row.get("theme_score")),
        "amount_yi": round(amount / 100_000_000, 2),
        "fact_precision_score": precision,
        "expression_score": expression_score,
        "reality_tokens": reality,
        "noise_tokens": noise,
        "has_entry": has_entry,
        "has_stop": has_stop,
        "has_no_buy_condition": has_no_buy,
        "high_accel_guard": high_accel_guard,
        "tier": tier,
        "next_action": next_action,
    }


def counts_by(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key, ""))
        out[value] = out.get(value, 0) + 1
    return out


def review_summary(review: dict[str, Any], feedback: dict[str, Any], tracker: dict[str, Any]) -> dict[str, Any]:
    review_rows = review.get("rows", []) if isinstance(review, dict) else []
    feedback_rows = feedback.get("rows", []) if isinstance(feedback, dict) else []
    tracker_rows = tracker.get("rows", []) if isinstance(tracker, dict) else []
    evaluated_tracker = [
        row
        for row in tracker_rows
        if str(row.get("d1_status", "")).startswith("evaluated")
        or str(row.get("d3_status", "")).startswith("evaluated")
        or str(row.get("d5_status", "")).startswith("evaluated")
    ]
    return {
        "review_rows": len(review_rows),
        "review_class_counts": counts_by(review_rows, "review_class"),
        "feedback_rows": len(feedback_rows),
        "watch_only_plus_rows": sum(row.get("feedback_action") == "DATA_BACKFILL_AND_WATCH_ONLY_PLUS" for row in feedback_rows),
        "strict_tracker_rows": len(tracker_rows),
        "strict_tracker_evaluated_rows": len(evaluated_tracker),
    }


def decide_system_tier(
    plan: dict[str, Any],
    theme_rows: list[dict[str, Any]],
    candidate_rows: list[dict[str, Any]],
    sample: dict[str, Any],
) -> dict[str, Any]:
    mainline_plus = [row for row in theme_rows if row["tier"] == "MAINLINE_WATCH_PLUS"]
    paper_ready = [row for row in candidate_rows if row["tier"] == "PAPER_TRADE_READY"]
    review_rows = int(sample.get("review_rows", 0))
    evaluated = int(sample.get("strict_tracker_evaluated_rows", 0))
    live_snapshot_used = bool(plan.get("live_snapshot_used", False))

    blockers: list[str] = []
    if not live_snapshot_used:
        blockers.append("no_live_snapshot")
    if review_rows < 20:
        blockers.append("sample_size_lt20")
    if evaluated < 20:
        blockers.append("strict_tracker_evaluated_lt20")
    if not mainline_plus:
        blockers.append("no_mainline_watch_plus")
    if not paper_ready:
        blockers.append("no_paper_trade_ready_candidate")

    if not blockers:
        tier = "MANUAL_SMALL_CAP_REVIEW"
        action = "可进入人工小额训练仓评审，但仍需人手确认，不允许自动真钱。"
    elif mainline_plus and paper_ready:
        tier = "PAPER_TRADE_ONLY"
        action = "主线和表达方式初步达标；继续模拟触发与复盘，不开真实仓位。"
    else:
        tier = "RESEARCH_OBSERVATION"
        action = "继续观察和样本积累，不讨论自动交易。"
    return {
        "tier": tier,
        "action": action,
        "blockers": blockers,
        "paper_sim_action": "NO_REAL_MONEY_AUTO",
    }


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    plan = read_json(args.plan_json)
    themes = read_csv(args.themes_csv)
    candidates = read_csv(args.candidates_csv)
    review = read_json(args.review_json)
    feedback = read_json(args.feedback_json)
    tracker = read_json(args.strict_tracker_json)

    theme_rows = [evaluate_theme(row.to_dict()) for _, row in themes.iterrows()] if not themes.empty else []
    candidate_rows = [evaluate_candidate(row.to_dict()) for _, row in candidates.iterrows()] if not candidates.empty else []
    sample = review_summary(review, feedback, tracker)
    decision = decide_system_tier(plan, theme_rows, candidate_rows, sample)

    return {
        "asof": args.asof,
        "diagnostic_only": True,
        "source_boundary": {
            "plan_json": str(args.plan_json),
            "themes_csv": str(args.themes_csv),
            "candidates_csv": str(args.candidates_csv),
            "review_json": str(args.review_json),
            "feedback_json": str(args.feedback_json),
            "strict_tracker_json": str(args.strict_tracker_json),
        },
        "v6ab_transfer_principles": [
            "PIT 可见性：只用当时可见的快照/计划/复盘，不用后验涨幅倒推买点。",
            "事实精度：真实政策/订单/成交/涨停结构权重大于概念噪音或数据缺口。",
            "主线与表达分离：题材对不等于买点对，龙头/中军/补涨需要分别评估。",
            "晋级 gate：只允许从观察到模拟，再到人工小额评审；不允许一步到自动真钱。",
        ],
        "data_boundary": {
            "plan_asof": plan.get("asof", ""),
            "next_trade_date": plan.get("next_trade_date", ""),
            "data_latest": plan.get("data_latest", ""),
            "live_snapshot_used": bool(plan.get("live_snapshot_used", False)),
        },
        "theme_rows": sorted(theme_rows, key=lambda row: row["theme_score"], reverse=True),
        "candidate_rows": sorted(candidate_rows, key=lambda row: (row["tier"] == "PAPER_TRADE_READY", row["score"]), reverse=True),
        "sample_summary": sample,
        "decision": decision,
    }


def render_md(payload: dict[str, Any]) -> str:
    decision = payload["decision"]
    boundary = payload["data_boundary"]
    sample = payload["sample_summary"]
    lines = [
        "# A股 Radar x V6AB 共性迁移评估",
        "",
        f"- 日期：`{payload['asof']}`",
        "- 模拟/实盘动作：`NO_REAL_MONEY_AUTO`。",
        "- 目的：把 V6AB 已验证的 PIT、事实精度、主线表达、晋级 gate 方法迁移到 A股 Radar。",
        f"- 当前层级：`{decision['tier']}` — {decision['action']}",
        "",
        "## Data Boundary",
        "",
        f"- plan asof：`{boundary.get('plan_asof', '')}`",
        f"- next trade date：`{boundary.get('next_trade_date', '')}`",
        f"- data latest：`{boundary.get('data_latest', '')}`",
        f"- live snapshot used：`{boundary.get('live_snapshot_used', False)}`",
        "",
        "## V6AB 共性原则迁移",
        "",
    ]
    lines.extend(f"- {item}" for item in payload["v6ab_transfer_principles"])
    lines += [
        "",
        "## Mainline Review",
        "",
        "| theme | score | phase | breadth | fact precision | tier | action |",
        "| --- | ---: | --- | ---: | ---: | --- | --- |",
    ]
    for row in payload["theme_rows"][:8]:
        lines.append(
            f"| {row['theme']} | {row['theme_score']:.1f} | {row['phase']} | {row['breadth']:.2f} | "
            f"{row['fact_precision_score']} | `{row['tier']}` | {row['action']} |"
        )
    lines += [
        "",
        "## Candidate Expression Review",
        "",
        "| symbol | theme | role | mode | fact | expression | tier | next action |",
        "| --- | --- | --- | --- | ---: | ---: | --- | --- |",
    ]
    for row in payload["candidate_rows"][:12]:
        lines.append(
            f"| `{row['symbol']}` {row['name']} | {row['theme']} | {row['role']} | {row['mode']} | "
            f"{row['fact_precision_score']} | {row['expression_score']} | `{row['tier']}` | {row['next_action']} |"
        )
    lines += [
        "",
        "## Sample / Gate Status",
        "",
        f"- review rows：`{sample.get('review_rows', 0)}`",
        f"- review classes：`{sample.get('review_class_counts', {})}`",
        f"- WATCH_ONLY_PLUS rows：`{sample.get('watch_only_plus_rows', 0)}`",
        f"- strict tracker evaluated rows：`{sample.get('strict_tracker_evaluated_rows', 0)}`",
        f"- blockers：`{', '.join(decision.get('blockers', [])) or 'none'}`",
        "",
        "## Interpretation",
        "",
        "- 当前适合继续作为 A股短线训练仓候选发现系统，不适合自动真钱。",
        "- V6AB 的共性已经能直接反哺：PIT 边界、噪音降权、表达方式审查、晋级 gate。",
        "- 下一步不是加复杂规则，而是积累可评价样本，并记录每次是否真的给出可参与买点。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Review which V6AB principles can be transferred into A-share Radar.")
    parser.add_argument("--asof", default=str(date.today()))
    parser.add_argument("--plan-json", type=Path, default=DEFAULT_PLAN_JSON)
    parser.add_argument("--themes-csv", type=Path, default=DEFAULT_THEMES_CSV)
    parser.add_argument("--candidates-csv", type=Path, default=DEFAULT_CANDIDATES_CSV)
    parser.add_argument("--review-json", type=Path, default=DEFAULT_REVIEW_JSON)
    parser.add_argument("--feedback-json", type=Path, default=DEFAULT_FEEDBACK_JSON)
    parser.add_argument("--strict-tracker-json", type=Path, default=DEFAULT_STRICT_TRACKER_JSON)
    parser.add_argument("--output-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    payload = build_payload(args)
    md = render_md(payload)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    json_text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    (args.output_dir / "latest.json").write_text(json_text, encoding="utf-8")
    (args.output_dir / "latest.md").write_text(md, encoding="utf-8")
    write_csv(args.output_dir / "latest_theme_rows.csv", payload["theme_rows"])
    write_csv(args.output_dir / "latest_candidate_rows.csv", payload["candidate_rows"])
    (REPORT_ROOT / "A股Radar_V6AB共性迁移评估_LATEST.json").write_text(json_text, encoding="utf-8")
    (REPORT_ROOT / "A股Radar_V6AB共性迁移评估_LATEST.md").write_text(md, encoding="utf-8")
    write_csv(REPORT_ROOT / "A股Radar_V6AB共性迁移评估_Themes_LATEST.csv", payload["theme_rows"])
    write_csv(REPORT_ROOT / "A股Radar_V6AB共性迁移评估_Candidates_LATEST.csv", payload["candidate_rows"])
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
