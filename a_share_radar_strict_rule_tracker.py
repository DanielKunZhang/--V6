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

DEFAULT_FEEDBACK_JSON = REPORT_ROOT / "A股短线Radar复盘反哺_LATEST.json"
DEFAULT_REVIEW_JSON = REPORT_ROOT / "A股短线Radar复盘_LATEST.json"
DEFAULT_CANDIDATES_CSV = REPORT_ROOT / "A股短线Radar候选_LATEST.csv"
DEFAULT_BACKFILL_JSON = REPORT_ROOT / "A股短线Radar_K线补齐_LATEST.json"
DEFAULT_CACHE_DIR = ROOT / "data" / "a_share_radar_kline_cache"
DEFAULT_OUTPUT_DIR = ROOT / "backtest_results" / "a_share_radar_strict_rule_tracker"


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


def cache_path(cache_dir: Path, symbol: str) -> Path:
    return cache_dir / f"{symbol.replace('.', '_')}.csv"


def candidate_by_symbol(candidates: pd.DataFrame) -> dict[str, dict[str, Any]]:
    if candidates.empty or "symbol" not in candidates.columns:
        return {}
    return {str(row.get("symbol", "")): row.to_dict() for _, row in candidates.iterrows()}


def backfill_by_symbol(backfill: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = backfill.get("rows", []) if isinstance(backfill, dict) else []
    return {str(row.get("symbol", "")): row for row in rows}


def load_kline(cache_dir: Path, symbol: str) -> pd.DataFrame:
    path = cache_path(cache_dir, symbol)
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    if "date" not in df.columns:
        return pd.DataFrame()
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df.sort_values("date").reset_index(drop=True)


def horizon_result(
    df: pd.DataFrame,
    origin_date: date,
    origin_close: float,
    pullback: float,
    breakout: float,
    stop: float,
    horizon: int,
) -> dict[str, Any]:
    future = df[df["date"] > origin_date].head(horizon)
    if future.empty:
        return {
            f"d{horizon}_status": "pending_no_kline",
            f"d{horizon}_return_pct": "",
            f"d{horizon}_touched_plan_buy": False,
            f"d{horizon}_gap_accel_unbuyable": False,
            f"d{horizon}_broke_stop": False,
        }

    first = future.iloc[0]
    last = future.iloc[-1]
    ref_close = origin_close if origin_close > 0 else to_float(first.get("Open"))
    open_gap = (to_float(first.get("Open")) / ref_close - 1.0) if ref_close > 0 else 0.0
    touched_pullback = bool(pullback > 0 and (future["Low"] <= pullback).any() and (future["High"] >= pullback).any())
    touched_breakout = bool(breakout > 0 and (future["High"] >= breakout).any())
    broke_stop = bool(stop > 0 and (future["Low"] <= stop).any())
    ret = (to_float(last.get("Close")) / ref_close - 1.0) * 100.0 if ref_close > 0 else 0.0
    gap_accel_unbuyable = open_gap >= 0.04
    touched_plan_buy = (touched_pullback or touched_breakout) and not gap_accel_unbuyable and not broke_stop
    return {
        f"d{horizon}_status": "evaluated",
        f"d{horizon}_return_pct": round(ret, 2),
        f"d{horizon}_touched_plan_buy": touched_plan_buy,
        f"d{horizon}_gap_accel_unbuyable": gap_accel_unbuyable,
        f"d{horizon}_broke_stop": broke_stop,
    }


def build_rows(
    feedback: dict[str, Any],
    review: dict[str, Any],
    candidates: pd.DataFrame,
    backfill: dict[str, Any],
    cache_dir: Path,
) -> list[dict[str, Any]]:
    candidates_map = candidate_by_symbol(candidates)
    backfill_map = backfill_by_symbol(backfill)
    rows = []
    for item in feedback.get("rows", []):
        if item.get("feedback_action") != "DATA_BACKFILL_AND_WATCH_ONLY_PLUS":
            continue
        symbol = str(item.get("symbol", ""))
        candidate = candidates_map.get(symbol, {})
        origin_date = pd.to_datetime(review.get("asof") or item.get("asof") or feedback.get("asof")).date()
        origin_close = to_float(candidate.get("close"))
        pullback = to_float(candidate.get("pullback_buy"))
        breakout = to_float(candidate.get("breakout_buy"))
        stop = to_float(candidate.get("stop"))
        df = load_kline(cache_dir, symbol)
        row = {
            "origin_date": str(origin_date),
            "symbol": symbol,
            "name": str(item.get("name", "")),
            "theme": str(item.get("theme", "")),
            "role": str(item.get("role", "")),
            "review_class": str(item.get("review_class", "")),
            "feedback_mode": str(item.get("mode_after_feedback", "")),
            "origin_change_pct": to_float(item.get("review_change_rate")),
            "origin_turnover_yi": round(to_float(item.get("review_turnover")) / 100_000_000, 2),
            "pullback_buy": pullback,
            "breakout_buy": breakout,
            "stop": stop,
            "backfill_status": str(backfill_map.get(symbol, {}).get("status", "missing")),
            "cached_kline_rows": int(len(df)),
        }
        for horizon in (1, 3, 5):
            row.update(horizon_result(df, origin_date, origin_close, pullback, breakout, stop, horizon))
        rows.append(row)
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def render_md(rows: list[dict[str, Any]], asof: str) -> str:
    lines = [
        "# A股 Radar 规则过严样本追踪表",
        "",
        f"- 生成日期：`{asof}`",
        "- 边界：只追踪复盘反哺中的 `WATCH_ONLY_PLUS` 样本；真实仓位仍为 `0`。",
        "- 目的：验证规则过严样本后 1/3/5 日是否真的给出计划内买点，避免用后验涨幅倒推交易。",
        "",
        "| 样本日 | 标的 | 主线 | 身份 | 反哺模式 | 补K状态 | K线数 | D1 | D3 | D5 | 判断 |",
        "| --- | --- | --- | --- | --- | --- | ---: | --- | --- | --- | --- |",
    ]
    if not rows:
        lines.append("| - | 无 | - | - | - | - | 0 | - | - | - | 暂无规则过严 P0 样本 |")
    for row in rows:
        d1 = f"{row['d1_status']} / {row['d1_return_pct']}% / 买点={row['d1_touched_plan_buy']}"
        d3 = f"{row['d3_status']} / {row['d3_return_pct']}% / 买点={row['d3_touched_plan_buy']}"
        d5 = f"{row['d5_status']} / {row['d5_return_pct']}% / 买点={row['d5_touched_plan_buy']}"
        if row["d1_status"] != "evaluated":
            verdict = "等待后续K线"
        elif row["d1_gap_accel_unbuyable"]:
            verdict = "高开加速，不按可参与买点计分"
        elif row["d1_touched_plan_buy"]:
            verdict = "D1出现计划内模拟买点，进入后续验证"
        else:
            verdict = "D1未给计划内买点，继续只观察"
        lines.append(
            f"| {row['origin_date']} | `{row['symbol']}` {row['name']} | {row['theme']} | {row['role']} | "
            f"{row['feedback_mode']} | {row['backfill_status']} | {row['cached_kline_rows']} | "
            f"{d1} | {d3} | {d5} | {verdict} |"
        )
    lines += [
        "",
        "## 解释规则",
        "",
        "- `买点=True` 只表示触及原计划回踩/突破条件，且未出现高开加速不可参与、未先跌破失效位。",
        "- `高开加速不可参与=True` 时，即使后续继续上涨，也不按可复制买点计分。",
        "- D3/D5 用于验证错过后的机会质量，不作为追高理由。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Track strict-rule A-share Radar feedback samples over D1/D3/D5.")
    parser.add_argument("--feedback-json", type=Path, default=DEFAULT_FEEDBACK_JSON)
    parser.add_argument("--review-json", type=Path, default=DEFAULT_REVIEW_JSON)
    parser.add_argument("--candidates-csv", type=Path, default=DEFAULT_CANDIDATES_CSV)
    parser.add_argument("--backfill-json", type=Path, default=DEFAULT_BACKFILL_JSON)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--asof", default=str(date.today()))
    args = parser.parse_args()

    feedback = read_json(args.feedback_json)
    review = read_json(args.review_json)
    candidates = read_csv(args.candidates_csv)
    backfill = read_json(args.backfill_json)
    rows = build_rows(feedback, review, candidates, backfill, args.cache_dir)
    payload = {
        "asof": args.asof,
        "source_feedback": str(args.feedback_json),
        "source_review": str(args.review_json),
        "source_candidates": str(args.candidates_csv),
        "source_backfill": str(args.backfill_json),
        "rows": rows,
    }
    md = render_md(rows, args.asof)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "latest_strict_rule_tracker.md").write_text(md, encoding="utf-8")
    (args.output_dir / "latest_strict_rule_tracker.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(args.output_dir / "latest_strict_rule_tracker.csv", rows)
    (REPORT_ROOT / "A股短线Radar规则过严样本追踪_LATEST.md").write_text(md, encoding="utf-8")
    (REPORT_ROOT / "A股短线Radar规则过严样本追踪_LATEST.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(REPORT_ROOT / "A股短线Radar规则过严样本追踪_LATEST.csv", rows)
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
