#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import time
from datetime import date
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd


ROOT = Path(__file__).resolve().parent
DESKTOP_ROOT = Path("/Users/zhangkun/Desktop/AI个人投资公司")
REPORT_ROOT = DESKTOP_ROOT / "报表输出" / "LATEST"
DEFAULT_PLAN_JSON = REPORT_ROOT / "A股短线Radar下周一计划_LATEST.json"
DEFAULT_CANDIDATES_CSV = REPORT_ROOT / "A股短线Radar候选_LATEST.csv"
DEFAULT_OUTPUT_DIR = ROOT / "backtest_results" / "a_share_short_radar_review"


def fetch_snapshots(codes: List[str], host: str, port: int, home_dir: Path) -> pd.DataFrame:
    home_dir.mkdir(parents=True, exist_ok=True)
    os.environ["HOME"] = str(home_dir)
    from futu import OpenQuoteContext, RET_OK

    ctx = OpenQuoteContext(host=host, port=port)
    frames = []
    try:
        for start in range(0, len(codes), 300):
            batch = codes[start : start + 300]
            ret, data = ctx.get_market_snapshot(batch)
            if ret != RET_OK:
                raise RuntimeError(f"get_market_snapshot failed: {ret}, {data}")
            if data is not None and not data.empty:
                frames.append(data.copy())
            time.sleep(0.15)
    finally:
        ctx.close()
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def read_candidates(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(path)
    return pd.read_csv(path)


def classify_actual_trade(row: pd.Series, trades: pd.DataFrame) -> tuple[str, str, str]:
    """4-class classification when actual trade records exist for this symbol."""
    symbol = str(row.get("symbol", ""))
    match = trades[trades["symbol"].astype(str) == symbol]
    if match.empty:
        return classify(row)
    trade = match.iloc[0]
    entry = float(trade.get("entry_price", 0) or 0)
    exit_price = float(trade.get("exit_price", 0) or 0)
    if entry <= 0 or exit_price <= 0:
        return classify(row)
    pnl = (exit_price - entry) / entry
    stop = float(row.get("stop", 0) or 0)
    broke_stop = float(row.get("review_low", 0) or 0) <= stop if stop > 0 else False
    plan_valid = not broke_stop  # plan said OK to trade
    if pnl >= 0 and plan_valid:
        return "正确盈利", f"按计划入场，盈利{pnl*100:.1f}%", "维持规则，更新样本"
    if pnl < 0 and plan_valid:
        return "正确亏损", f"按计划入场，亏损{pnl*100:.1f}%，止损执行正确", "检查失效位设置是否偏宽"
    if pnl >= 0 and not plan_valid:
        return "错误盈利", f"计划失效但仍持有，盈利{pnl*100:.1f}%（运气成分）", "下次严格执行止损纪律"
    return "错误亏损", f"计划失效仍持有，亏损{pnl*100:.1f}%", "严格执行硬止损，减半仓位"


def classify(row: pd.Series) -> tuple[str, str, str]:
    action = str(row.get("action", ""))
    change = float(row.get("review_change_rate", 0.0) or 0.0) / 100.0
    high = float(row.get("review_high", 0.0) or 0.0)
    low = float(row.get("review_low", 0.0) or 0.0)
    close = float(row.get("review_close", 0.0) or 0.0)
    pullback = float(row.get("pullback_buy", 0.0) or 0.0)
    breakout = float(row.get("breakout_buy", 0.0) or 0.0)
    stop = float(row.get("stop", 0.0) or 0.0)

    touched_pullback = low <= pullback <= high if pullback > 0 and high > 0 else False
    touched_breakout = high >= breakout if breakout > 0 else False
    broke_stop = low <= stop if stop > 0 else False

    if "仅实时观察" in action or "只复盘" in action:
        if change > 0.05 and (touched_pullback or touched_breakout):
            return "规则过严", "候选明显走强且触及计划点，但原计划禁止交易", "补齐K线后评估是否允许更早低吸/半路"
        if change > 0.05:
            return "错过但规则正确", "上涨但未满足完整交易准入或缺少K线", "不追高，继续补数据"
        return "正确观察", "原计划观察，事后未证明必须交易", "维持规则"

    if "不追高" in action:
        if touched_pullback and close > pullback and not broke_stop:
            return "错过但规则正确", "出现分歧回踩并修复，计划方向正确但需人工确认是否可执行", "下次盘前写清更窄失效位"
        if change > 0.05 and not touched_pullback:
            return "错过但规则正确", "继续走强但没有给回踩买点", "不因后验上涨追责"
        if broke_stop:
            return "正确观察", "未追高避免潜在回撤", "维持不追高纪律"
        return "正确观察", "未出现清晰计划买点", "继续观察"

    if "可列入" in action:
        if broke_stop:
            return "规则错误", "计划允许交易但当日跌破失效位", "下一次候选仓位减半"
        if touched_pullback or touched_breakout:
            return "正确观察", "计划买点出现，需结合是否实际执行再归类盈利/亏损", "若交易需补成交记录"
        return "正确观察", "计划存在但买点未出现", "不交易"

    return "正确观察", "默认复盘分类", "维持规则"


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def render_md(plan: dict[str, Any], rows: List[Dict[str, Any]], asof: str) -> str:
    lines = [
        "# A股低频主线确认 Radar 观察复盘",
        "",
        f"- 复盘日期：`{asof}`",
        f"- 原计划交易日：`{plan.get('next_trade_date', '')}`",
        f"- 原计划生成：`{plan.get('asof', '')}`",
        "",
        "## 标的复盘",
        "",
        "| 标的 | 原主题 | 原身份 | 原动作 | 收盘 | 涨跌幅 | 盘中高低 | 复盘分类 | 判定理由 | 下一步 |",
        "| --- | --- | --- | --- | ---: | ---: | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            f"| `{row['symbol']}` {row['name']} | {row['theme']} | {row['role']} | {row['original_action']} | "
            f"{row['review_close']:.2f} | {row['review_change_rate']:.2f}% | "
            f"{row['review_low']:.2f}-{row['review_high']:.2f} | {row['review_class']} | "
            f"{row['review_reason']} | {row['next_action']} |"
        )
    counts = {}
    for row in rows:
        counts[row["review_class"]] = counts.get(row["review_class"], 0) + 1
    lines += [
        "",
        "## 复盘结论",
        "",
    ]
    for key, value in sorted(counts.items()):
        lines.append(f"- `{key}`：{value} 只")
    lines += [
        "",
        "## 下一次动作",
        "",
        "- 若没有实际交易：本次只作为观察样本，不计入交易胜负。",
        "- 若有实际交易：必须补成交价、仓位、卖出价，再归类为正确盈利/正确亏损/错误盈利/错误亏损。",
        "- 下一笔交易前必须先完成本复盘确认。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Review latest A-share short Radar plan.")
    parser.add_argument("--plan-json", type=Path, default=DEFAULT_PLAN_JSON)
    parser.add_argument("--candidates-csv", type=Path, default=DEFAULT_CANDIDATES_CSV)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--asof", default=str(date.today()))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=11111)
    parser.add_argument("--futu-home-dir", type=Path, default=ROOT / ".tmp_futu_home")
    parser.add_argument("--trades-csv", type=Path, default=None,
                        help="可选：实际成交记录 CSV，需含 symbol/entry_price/exit_price 列，启用4分类复盘")
    args = parser.parse_args()

    plan = json.loads(args.plan_json.read_text(encoding="utf-8"))
    candidates = read_candidates(args.candidates_csv)
    trades_df = pd.read_csv(args.trades_csv) if args.trades_csv and args.trades_csv.exists() else pd.DataFrame()
    codes = candidates["symbol"].astype(str).tolist()
    snapshots = fetch_snapshots(codes, args.host, args.port, args.futu_home_dir)
    snap = snapshots.rename(
        columns={
            "code": "symbol",
            "last_price": "review_close",
            "high_price": "review_high",
            "low_price": "review_low",
            "change_rate": "review_change_rate",
            "turnover": "review_turnover",
            "update_time": "review_update_time",
        }
    )
    if "review_change_rate" not in snap.columns and {"review_close", "prev_close_price"}.issubset(snap.columns):
        snap["review_change_rate"] = (snap["review_close"] / snap["prev_close_price"] - 1.0) * 100.0
    merged = candidates.merge(
        snap[["symbol", "review_close", "review_high", "review_low", "review_change_rate", "review_turnover", "review_update_time"]],
        on="symbol",
        how="left",
    )
    rows: List[Dict[str, Any]] = []
    for _, row in merged.iterrows():
        if not trades_df.empty:
            review_class, review_reason, next_action = classify_actual_trade(row, trades_df)
        else:
            review_class, review_reason, next_action = classify(row)
        rows.append(
            {
                "symbol": str(row["symbol"]),
                "name": str(row["name"]),
                "theme": str(row["theme"]),
                "role": str(row["role"]),
                "original_action": str(row["action"]),
                "review_close": float(row.get("review_close") or 0.0),
                "review_high": float(row.get("review_high") or 0.0),
                "review_low": float(row.get("review_low") or 0.0),
                "review_change_rate": float(row.get("review_change_rate") or 0.0),
                "review_turnover": float(row.get("review_turnover") or 0.0),
                "review_update_time": str(row.get("review_update_time") or ""),
                "review_class": review_class,
                "review_reason": review_reason,
                "next_action": next_action,
            }
        )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "latest_review.csv", rows)
    payload = {"asof": args.asof, "plan": plan, "rows": rows}
    (args.output_dir / "latest_review.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md = render_md(plan, rows, args.asof)
    (args.output_dir / "latest_review.md").write_text(md, encoding="utf-8")

    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    desktop_md = REPORT_ROOT / "A股短线Radar复盘_LATEST.md"
    desktop_json = REPORT_ROOT / "A股短线Radar复盘_LATEST.json"
    desktop_csv = REPORT_ROOT / "A股短线Radar复盘_LATEST.csv"
    desktop_md.write_text(md, encoding="utf-8")
    desktop_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(desktop_csv, rows)
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
