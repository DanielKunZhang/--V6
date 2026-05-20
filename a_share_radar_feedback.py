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

DEFAULT_REVIEW_JSON = REPORT_ROOT / "A股短线Radar复盘_LATEST.json"
DEFAULT_CANDIDATES_CSV = REPORT_ROOT / "A股短线Radar候选_LATEST.csv"
DEFAULT_OUTPUT_DIR = ROOT / "backtest_results" / "a_share_radar_feedback"


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


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


def theme_lookup(review: dict[str, Any]) -> dict[str, dict[str, Any]]:
    themes = review.get("plan", {}).get("themes", [])
    return {str(row.get("theme", "")): row for row in themes if row.get("theme")}


def candidate_lookup(candidates: pd.DataFrame) -> dict[str, dict[str, Any]]:
    if candidates.empty or "symbol" not in candidates.columns:
        return {}
    rows: dict[str, dict[str, Any]] = {}
    for _, row in candidates.iterrows():
        rows[str(row.get("symbol", ""))] = row.to_dict()
    return rows


def qualifies_for_watch_only_plus(
    review_row: dict[str, Any],
    candidate: dict[str, Any],
    theme: dict[str, Any],
) -> tuple[bool, str]:
    review_class = str(review_row.get("review_class", ""))
    original_action = str(review_row.get("original_action", ""))
    role = str(review_row.get("role", ""))
    theme_score = to_float(candidate.get("theme_score", theme.get("score", 0)))
    amount = to_float(review_row.get("review_turnover", candidate.get("amount_rmb", 0)))
    change = to_float(review_row.get("review_change_rate", 0))
    phase = str(theme.get("phase", ""))

    if review_class != "规则过严":
        return False, "not_strict_rule_sample"
    if "仅实时观察" not in original_action and "需补K线" not in original_action:
        return False, "not_data_gap_watch_only"
    if role not in {"龙头", "中军"}:
        return False, "role_not_leader_or_core"
    if theme_score < 25:
        return False, "theme_score_below_25"
    if amount < 2_000_000_000:
        return False, "turnover_below_2b"
    if change < 8:
        return False, "change_below_8pct"
    if "主升" not in phase:
        return False, "theme_not_main_uptrend"
    return True, "strict_rule_mainline_core_data_gap"


def build_feedback(review: dict[str, Any], candidates: pd.DataFrame, asof: str) -> list[dict[str, Any]]:
    themes = theme_lookup(review)
    candidates_by_symbol = candidate_lookup(candidates)
    rows = []
    for review_row in review.get("rows", []):
        symbol = str(review_row.get("symbol", ""))
        candidate = candidates_by_symbol.get(symbol, {})
        theme = themes.get(str(review_row.get("theme", "")), {})
        qualified, reason_code = qualifies_for_watch_only_plus(review_row, candidate, theme)
        if not qualified and str(review_row.get("review_class", "")) != "规则过严":
            continue

        action = "KEEP_OBSERVE"
        mode_after_feedback = str(candidate.get("mode", ""))
        priority = "P2"
        next_system_action = "记录样本，暂不改变候选模式。"
        if qualified:
            action = "DATA_BACKFILL_AND_WATCH_ONLY_PLUS"
            mode_after_feedback = "WATCH_ONLY_PLUS"
            priority = "P0"
            next_system_action = (
                "优先补齐最近60个交易日K线；若次日主题仍为主升且个股不高开加速，"
                "只记录模拟低吸/突破回踩触发，不给真实仓位。"
            )

        rows.append(
            {
                "asof": asof,
                "symbol": symbol,
                "name": str(review_row.get("name", "")),
                "theme": str(review_row.get("theme", "")),
                "role": str(review_row.get("role", "")),
                "review_class": str(review_row.get("review_class", "")),
                "review_change_rate": round(to_float(review_row.get("review_change_rate", 0)), 4),
                "review_turnover": round(to_float(review_row.get("review_turnover", 0)), 2),
                "old_mode": str(candidate.get("mode", "")),
                "mode_after_feedback": mode_after_feedback,
                "feedback_action": action,
                "priority": priority,
                "reason_code": reason_code,
                "position_size_rmb": "0",
                "next_system_action": next_system_action,
            }
        )
    return rows


def render_md(rows: list[dict[str, Any]], asof: str) -> str:
    lines = [
        "# A股 Radar 复盘反哺清单",
        "",
        f"- 日期：`{asof}`",
        "- 边界：当前仍为 20 个交易日观察期，所有反哺动作真实仓位仍为 `0`。",
        "- 目的：把收盘复盘中的规则过严/数据缺口样本转成下一次系统动作。",
        "",
    ]
    plus_rows = [row for row in rows if row["feedback_action"] == "DATA_BACKFILL_AND_WATCH_ONLY_PLUS"]
    if plus_rows:
        lines += [
            "## P0：补 K 线并升级为 WATCH_ONLY_PLUS",
            "",
            "| 标的 | 主线 | 身份 | 今日涨跌 | 成交额 | 原模式 | 新观察模式 | 下一步 |",
            "| --- | --- | --- | ---: | ---: | --- | --- | --- |",
        ]
        for row in plus_rows:
            turnover_yi = to_float(row["review_turnover"]) / 100_000_000
            lines.append(
                f"| `{row['symbol']}` {row['name']} | {row['theme']} | {row['role']} | "
                f"{row['review_change_rate']:.2f}% | {turnover_yi:.1f}亿 | {row['old_mode']} | "
                f"{row['mode_after_feedback']} | {row['next_system_action']} |"
            )
        lines.append("")
    else:
        lines += ["## P0：无", ""]

    other_rows = [row for row in rows if row["feedback_action"] != "DATA_BACKFILL_AND_WATCH_ONLY_PLUS"]
    if other_rows:
        lines += [
            "## 其他规则过严样本",
            "",
            "| 标的 | 主线 | 复盘分类 | 原因码 | 下一步 |",
            "| --- | --- | --- | --- | --- |",
        ]
        for row in other_rows:
            lines.append(
                f"| `{row['symbol']}` {row['name']} | {row['theme']} | "
                f"{row['review_class']} | `{row['reason_code']}` | {row['next_system_action']} |"
            )
        lines.append("")

    lines += [
        "## 规则说明",
        "",
        "- `WATCH_ONLY_PLUS` 不是买入模式；它只代表数据补齐和次日重点模拟确认优先级高于普通 WATCH_ONLY。",
        "- 晋级条件必须同时满足：复盘分类为 `规则过严`、原因为缺 K/仅观察、主题分不低于 25、角色为龙头/中军、成交额不低于 20 亿、涨幅不低于 8%、主题处于主升阶段。",
        "- 观察期结束前不得因为 `WATCH_ONLY_PLUS` 输出真实仓位。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert A-share Radar review lessons into next-system actions.")
    parser.add_argument("--review-json", type=Path, default=DEFAULT_REVIEW_JSON)
    parser.add_argument("--candidates-csv", type=Path, default=DEFAULT_CANDIDATES_CSV)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--asof", default=str(date.today()))
    args = parser.parse_args()

    review = read_json(args.review_json)
    candidates = read_csv(args.candidates_csv)
    rows = build_feedback(review, candidates, args.asof)
    payload = {
        "asof": args.asof,
        "source_review": str(args.review_json),
        "rows": rows,
    }
    md = render_md(rows, args.asof)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "latest_feedback.md").write_text(md, encoding="utf-8")
    (args.output_dir / "latest_feedback.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(args.output_dir / "latest_feedback.csv", rows)
    (REPORT_ROOT / "A股短线Radar复盘反哺_LATEST.md").write_text(md, encoding="utf-8")
    (REPORT_ROOT / "A股短线Radar复盘反哺_LATEST.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(REPORT_ROOT / "A股短线Radar复盘反哺_LATEST.csv", rows)
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
