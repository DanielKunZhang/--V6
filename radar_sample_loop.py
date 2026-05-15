#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
DESKTOP_DIR = Path("/Users/zhangkun/Desktop/AI个人投资公司")
OUT_DIR = ROOT / "backtest_results" / "radar_sample_loop"
THEME_SCAN = ROOT / "backtest_results" / "radar_theme_rotation_scanner" / "latest.json"
MISSING_REVIEW = ROOT / "backtest_results" / "v6b_missing_opportunity_review" / "latest.json"
PRICE_CACHE_DIRS = [
    ROOT / "backtest_results" / "price_cache",
    ROOT / "backtest_results" / "v6b_rough_test" / "price_cache",
]

FIELDS = [
    "sample_id",
    "as_of",
    "source_channel",
    "ticker",
    "theme_id",
    "theme_label",
    "theme_stage",
    "layer",
    "price_at_signal",
    "score",
    "mom20",
    "mom60",
    "chase_risk",
    "trade_posture",
    "entry_note",
    "fwd_5d",
    "fwd_10d",
    "fwd_20d",
    "fwd_60d",
    "max_drawdown_after_signal",
    "decision",
    "review_verdict",
    "last_reviewed_at",
]


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def normalize_ticker(ticker: str) -> str:
    ticker = str(ticker or "").strip().upper()
    if not ticker:
        return ""
    return ticker if "." in ticker else f"US.{ticker}"


def pct(value: Any) -> str:
    if value in (None, ""):
        return ""
    return f"{float(value):.6f}"


def sample_id(as_of: str, source_channel: str, ticker: str) -> str:
    clean_ticker = normalize_ticker(ticker).replace(".", "_")
    clean_source = str(source_channel or "unknown").lower()
    return f"{as_of}_{clean_source}_{clean_ticker}"


def default_decision(chase_risk: str, trade_posture: str) -> str:
    text = f"{chase_risk} {trade_posture}"
    if "禁止" in text or "高" in chase_risk:
        return "不直接交易，等待回撤/盘整/重新触发"
    if "小仓" in text:
        return "只允许小仓试错，必须预设亏损上限"
    if "复核" in text:
        return "进入正式复核"
    return "观察"


def price_cache_paths(ticker: str) -> list[Path]:
    normalized = normalize_ticker(ticker).replace(".", "_")
    plain = normalize_ticker(ticker).replace("US.", "").replace(".", "_")
    out: list[Path] = []
    for directory in PRICE_CACHE_DIRS:
        out.append(directory / f"{normalized}_daily.csv")
        out.append(directory / f"{plain}_daily.csv")
    return out


def read_price_rows(ticker: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in price_cache_paths(ticker):
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                date = row.get("date") or row.get("Date")
                close = row.get("Close") or row.get("close")
                if not date or not close:
                    continue
                try:
                    rows.append({"date": date[:10], "close": float(close)})
                except ValueError:
                    continue
    dedup = {row["date"]: row for row in rows}
    return [dedup[key] for key in sorted(dedup)]


def forward_return(ticker: str, as_of: str, horizon: int) -> str:
    rows = read_price_rows(ticker)
    if not rows:
        return ""
    dates = [row["date"] for row in rows]
    if as_of not in dates:
        eligible = [idx for idx, date in enumerate(dates) if date <= as_of]
        if not eligible:
            return ""
        start_idx = eligible[-1]
    else:
        start_idx = dates.index(as_of)
    end_idx = start_idx + horizon
    if end_idx >= len(rows):
        return ""
    start = rows[start_idx]["close"]
    end = rows[end_idx]["close"]
    if start <= 0:
        return ""
    return f"{end / start - 1.0:.6f}"


def max_drawdown_after_signal(ticker: str, as_of: str, horizon: int = 60) -> str:
    rows = read_price_rows(ticker)
    if not rows:
        return ""
    dates = [row["date"] for row in rows]
    eligible = [idx for idx, date in enumerate(dates) if date <= as_of]
    if not eligible:
        return ""
    start_idx = eligible[-1]
    end_idx = min(len(rows), start_idx + horizon + 1)
    window = rows[start_idx:end_idx]
    if len(window) <= 1:
        return ""
    peak = window[0]["close"]
    max_dd = 0.0
    for row in window:
        peak = max(peak, row["close"])
        if peak > 0:
            max_dd = min(max_dd, row["close"] / peak - 1.0)
    return f"{max_dd:.6f}"


def build_row(as_of: str, source_channel: str, row: dict[str, Any], stage: str = "") -> dict[str, Any]:
    ticker = normalize_ticker(str(row.get("ticker") or ""))
    chase_risk = str(row.get("chase_risk") or "待补")
    trade_posture = str(row.get("trade_posture") or row.get("action") or "待复核")
    out = {
        "sample_id": sample_id(as_of, source_channel, ticker),
        "as_of": as_of,
        "source_channel": source_channel,
        "ticker": ticker,
        "theme_id": row.get("theme_id") or "",
        "theme_label": row.get("theme_label") or row.get("theme") or "",
        "theme_stage": stage or row.get("theme_stage") or "",
        "layer": row.get("layer_label") or row.get("buckets") or row.get("bucket_id") or row.get("layer") or "",
        "price_at_signal": row.get("close") or "",
        "score": row.get("score") or "",
        "mom20": pct(row.get("mom20")),
        "mom60": pct(row.get("mom60")),
        "chase_risk": chase_risk,
        "trade_posture": trade_posture,
        "entry_note": row.get("entry_note") or row.get("gap_attribution") or "",
        "fwd_5d": forward_return(ticker, as_of, 5),
        "fwd_10d": forward_return(ticker, as_of, 10),
        "fwd_20d": forward_return(ticker, as_of, 20),
        "fwd_60d": forward_return(ticker, as_of, 60),
        "max_drawdown_after_signal": max_drawdown_after_signal(ticker, as_of),
        "decision": default_decision(chase_risk, trade_posture),
        "review_verdict": "PENDING_FORWARD_REVIEW",
        "last_reviewed_at": datetime.now().isoformat(timespec="seconds"),
    }
    return {field: out.get(field, "") for field in FIELDS}


def build_rows() -> list[dict[str, Any]]:
    theme_scan = read_json(THEME_SCAN)
    missing = read_json(MISSING_REVIEW)
    as_of = str(theme_scan.get("as_of") or missing.get("as_of") or datetime.now().date())
    stage = str((theme_scan.get("summary", {}) or {}).get("top_theme_stage") or "")
    rows: list[dict[str, Any]] = []
    for row in theme_scan.get("candidates", []) if isinstance(theme_scan.get("candidates"), list) else []:
        rows.append(build_row(as_of, "independent_discovery", row, stage))
    for row in theme_scan.get("external_sample_review", []) if isinstance(theme_scan.get("external_sample_review"), list) else []:
        rows.append(build_row(as_of, "external_sample_review", row, stage))
    for row in missing.get("critical_misses", []) if isinstance(missing.get("critical_misses"), list) else []:
        rows.append(build_row(as_of, "missing_opportunity_review", row, stage))
    dedup: dict[str, dict[str, Any]] = {}
    for row in rows:
        dedup[row["sample_id"]] = row
    return list(dedup.values())


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def write_md(path: Path, rows: list[dict[str, Any]], tag: str) -> None:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["source_channel"]] = counts.get(row["source_channel"], 0) + 1
    lines = [
        "# Radar 样本闭环表",
        "",
        f"- Tag: `{tag}`",
        f"- Generated: `{datetime.now().isoformat(timespec='seconds')}`",
        f"- Sample count: `{len(rows)}`",
        f"- Independent discovery: `{counts.get('independent_discovery', 0)}`",
        f"- External sample review: `{counts.get('external_sample_review', 0)}`",
        f"- Missing opportunity review: `{counts.get('missing_opportunity_review', 0)}`",
        "",
        "## 使用规则",
        "",
        "- 这张表不是买入清单，而是 Radar 供给链的审计账本。",
        "- `independent_discovery` 代表系统独立发现；`external_sample_review` 代表朋友/外部网络样本；`missing_opportunity_review` 代表系统漏网后补课。",
        "- `fwd_5d/10d/20d/60d` 为空代表当前价格缓存还没有足够未来数据，后续定期刷新后再归因。",
        "- 只有样本跑出足够历史表现，才允许进入 V6-B 或 Overlay 预算讨论。",
        "",
        "## 样本预览",
        "",
        "| 来源 | 标的 | 主线 | 层级 | 信号价 | 分数 | 追高风险 | 交易姿态 | 复盘结论 |",
        "| --- | --- | --- | --- | ---: | ---: | --- | --- | --- |",
    ]
    for row in rows[:30]:
        lines.append(
            f"| {row['source_channel']} | `{row['ticker']}` | {row['theme_label'] or row['theme_id']} | "
            f"{row['layer']} | {row['price_at_signal']} | {row['score']} | {row['chase_risk']} | "
            f"{row['trade_posture']} | {row['review_verdict']} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Radar sample loop register from latest scanner/review outputs.")
    parser.add_argument("--tag", default=datetime.now().strftime("%Y%m%dT%H%M%S"))
    parser.add_argument("--sync-desktop", action="store_true")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = build_rows()
    json_path = OUT_DIR / f"radar_sample_loop_{args.tag}.json"
    csv_path = OUT_DIR / f"radar_sample_loop_{args.tag}.csv"
    md_path = OUT_DIR / f"radar_sample_loop_{args.tag}.md"
    latest_json = OUT_DIR / "latest.json"
    latest_csv = OUT_DIR / "latest.csv"
    latest_md = OUT_DIR / "latest.md"

    payload = {"generated_at": datetime.now().isoformat(timespec="seconds"), "tag": args.tag, "sample_count": len(rows), "rows": rows}
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    latest_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(csv_path, rows)
    write_csv(latest_csv, rows)
    write_md(md_path, rows, args.tag)
    write_md(latest_md, rows, args.tag)

    if args.sync_desktop:
        shutil.copy2(latest_md, DESKTOP_DIR / "Radar_样本闭环表_LATEST.md")
        shutil.copy2(latest_csv, DESKTOP_DIR / "Radar_样本闭环表_LATEST.csv")
        shutil.copy2(latest_json, DESKTOP_DIR / "Radar_样本闭环表_LATEST.json")

    print("== Radar Sample Loop ==")
    print(f"Samples: {len(rows)}")
    print(f"Markdown: {md_path}")
    print(f"CSV: {csv_path}")
    print(f"JSON: {json_path}")
    print(f"Sync desktop: {args.sync_desktop}")


if __name__ == "__main__":
    main()

