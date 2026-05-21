#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parent
DESKTOP_ROOT = Path("/Users/zhangkun/Desktop/AI个人投资公司")
REPORT_ROOT = DESKTOP_ROOT / "报表输出" / "LATEST"
DEFAULT_FEEDBACK_JSON = REPORT_ROOT / "A股短线Radar复盘反哺_LATEST.json"
DEFAULT_CACHE_DIR = ROOT / "data" / "a_share_radar_kline_cache"
DEFAULT_OUTPUT_DIR = ROOT / "backtest_results" / "a_share_radar_backfill"


class RequestTimeoutError(RuntimeError):
    pass


@contextmanager
def time_limit(seconds: int):
    if seconds <= 0:
        yield
        return

    def _handle_timeout(signum, frame):
        raise RequestTimeoutError(f"request_timeout_{seconds}s")

    old_handler = signal.signal(signal.SIGALRM, _handle_timeout)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def cache_path(cache_dir: Path, symbol: str) -> Path:
    safe = symbol.replace(".", "_")
    return cache_dir / f"{safe}.csv"


def p0_symbols(feedback: dict[str, Any]) -> list[dict[str, Any]]:
    rows = feedback.get("rows", []) if isinstance(feedback, dict) else []
    selected = []
    seen = set()
    for row in rows:
        if row.get("feedback_action") != "DATA_BACKFILL_AND_WATCH_ONLY_PLUS":
            continue
        symbol = str(row.get("symbol", ""))
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        selected.append(row)
    return selected


def fetch_futu_kline(symbol: str, start: str, end: str, host: str, port: int) -> pd.DataFrame:
    from futu import AuType, KLType, KL_FIELD, OpenQuoteContext, RET_OK

    ctx = OpenQuoteContext(host=host, port=port)
    frames = []
    page_key = None
    try:
        while True:
            ret, df, page_key = ctx.request_history_kline(
                code=symbol,
                start=start,
                end=end,
                ktype=KLType.K_DAY,
                autype=AuType.QFQ,
                fields=[
                    KL_FIELD.DATE_TIME,
                    KL_FIELD.OPEN,
                    KL_FIELD.HIGH,
                    KL_FIELD.LOW,
                    KL_FIELD.CLOSE,
                    KL_FIELD.TRADE_VOL,
                    KL_FIELD.TRADE_VAL,
                ],
                max_count=1000,
                page_req_key=page_key,
            )
            if ret != RET_OK:
                raise RuntimeError(f"request_history_kline failed for {symbol}: {ret}, {df}")
            if df is not None and not df.empty:
                frames.append(df.copy())
            if page_key is None:
                break
            time.sleep(0.15)
    finally:
        ctx.close()

    if not frames:
        return pd.DataFrame()
    result = pd.concat(frames, ignore_index=True)
    result = result.drop_duplicates(subset="time_key")
    result["date"] = pd.to_datetime(result["time_key"]).dt.date
    rename = {
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "volume": "Volume",
        "turnover": "Turnover",
        "turnover_rate": "TurnoverRate",
        "trade_val": "Turnover",
    }
    result = result.rename(columns=rename)
    keep = [col for col in ["date", "Open", "High", "Low", "Close", "Volume", "Turnover"] if col in result.columns]
    return result[keep].sort_values("date").reset_index(drop=True)


def validate_kline(df: pd.DataFrame, min_rows: int) -> tuple[bool, str]:
    if df.empty:
        return False, "empty"
    if len(df) < min_rows:
        return False, f"rows_below_{min_rows}"
    required = {"Open", "High", "Low", "Close", "Volume"}
    missing = sorted(required.difference(df.columns))
    if missing:
        return False, "missing_" + "_".join(missing)
    if df[["Open", "High", "Low", "Close"]].isna().any().any():
        return False, "price_nan"
    return True, "ok"


def render_md(rows: list[dict[str, Any]], asof: str, dry_run: bool) -> str:
    lines = [
        "# A股 Radar P0 K线补齐结果",
        "",
        f"- 日期：`{asof}`",
        f"- 模式：`{'DRY_RUN' if dry_run else 'LIVE_BACKFILL'}`",
        "- 范围：仅处理复盘反哺清单中的 P0 / WATCH_ONLY_PLUS 标的。",
        "",
        "| 标的 | 状态 | 行数 | 起止日期 | 缓存文件 | 说明 |",
        "| --- | --- | ---: | --- | --- | --- |",
    ]
    if not rows:
        lines.append("| 无 | skip | 0 | - | - | 无 P0 标的 |")
    for row in rows:
        lines.append(
            f"| `{row['symbol']}` {row['name']} | {row['status']} | {row['rows']} | "
            f"{row['start_date']} -> {row['end_date']} | `{row['path']}` | {row['message']} |"
        )
    lines += [
        "",
        "## 后续使用",
        "",
        "- 状态为 `ok` 的标的，下一次计划生成时不得再因为“仅有 Level A 快照”降级为普通 `WATCH_ONLY`。",
        "- 状态不是 `ok` 的标的，继续保留观察，不得输出真实仓位。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill K-line data only for A-share Radar P0 feedback symbols.")
    parser.add_argument("--feedback-json", type=Path, default=DEFAULT_FEEDBACK_JSON)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--asof", default=str(date.today()))
    parser.add_argument("--lookback-days", type=int, default=120)
    parser.add_argument("--min-rows", type=int, default=50)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=11111)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--request-timeout-seconds", type=int, default=45)
    args = parser.parse_args()

    feedback = read_json(args.feedback_json)
    selected = p0_symbols(feedback)
    end = args.asof
    start = str(pd.to_datetime(args.asof).date() - timedelta(days=args.lookback_days))

    args.cache_dir.mkdir(parents=True, exist_ok=True)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)

    rows = []
    for item in selected:
        symbol = str(item.get("symbol", ""))
        name = str(item.get("name", ""))
        path = cache_path(args.cache_dir, symbol)
        if args.dry_run:
            rows.append(
                {
                    "symbol": symbol,
                    "name": name,
                    "status": "dry_run",
                    "rows": 0,
                    "start_date": start,
                    "end_date": end,
                    "path": str(path),
                    "message": "would_fetch_targeted_kline",
                }
            )
            continue
        try:
            with time_limit(args.request_timeout_seconds):
                df = fetch_futu_kline(symbol, start, end, args.host, args.port)
            ok, message = validate_kline(df, args.min_rows)
            if ok:
                df.to_csv(path, index=False)
            rows.append(
                {
                    "symbol": symbol,
                    "name": name,
                    "status": "ok" if ok else "invalid",
                    "rows": int(len(df)),
                    "start_date": str(df["date"].min()) if not df.empty and "date" in df else "",
                    "end_date": str(df["date"].max()) if not df.empty and "date" in df else "",
                    "path": str(path) if ok else "",
                    "message": message,
                }
            )
        except Exception as exc:
            rows.append(
                {
                    "symbol": symbol,
                    "name": name,
                    "status": "error",
                    "rows": 0,
                    "start_date": "",
                    "end_date": "",
                    "path": "",
                    "message": repr(exc),
                }
            )

    payload = {"asof": args.asof, "dry_run": args.dry_run, "source_feedback": str(args.feedback_json), "rows": rows}
    md = render_md(rows, args.asof, args.dry_run)
    (args.output_dir / "latest_backfill.md").write_text(md, encoding="utf-8")
    (args.output_dir / "latest_backfill.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (REPORT_ROOT / "A股短线Radar_K线补齐_LATEST.md").write_text(md, encoding="utf-8")
    (REPORT_ROOT / "A股短线Radar_K线补齐_LATEST.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(md, flush=True)
    return 0


if __name__ == "__main__":
    exit_code = main()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(exit_code)
