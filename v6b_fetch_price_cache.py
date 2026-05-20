#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parent
DEFAULT_CACHE_DIR = ROOT / "backtest_results" / "price_cache"


def load_tickers_from_universe(path: Path) -> list[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    tickers = set(payload.get("market_benchmarks", []))
    for theme in payload.get("themes", []):
        tickers.update(theme.get("benchmarks", []))
        for key in ["leader_layer", "first_order_beneficiaries", "second_order_infrastructure", "third_order_high_beta"]:
            tickers.update(theme.get(key, []))
    return sorted(ticker for ticker in tickers if ticker and ticker != "CASH")


def cache_path(cache_dir: Path, ticker: str) -> Path:
    return cache_dir / f"{ticker.replace('.', '_')}_daily.csv"


def cache_fresh_enough(cache_dir: Path, ticker: str, min_end: str) -> bool:
    path = cache_path(cache_dir, ticker)
    if not path.exists():
        return False
    try:
        df = pd.read_csv(path, usecols=["date"])
    except Exception:
        return False
    if df.empty:
        return False
    max_date = pd.to_datetime(df["date"]).max()
    return bool(max_date >= pd.Timestamp(min_end) - pd.Timedelta(days=10))


def collect_quota(host: str, port: int) -> dict[str, Any]:
    from futu import OpenQuoteContext, RET_OK

    ctx = OpenQuoteContext(host=host, port=port)
    try:
        ret, data = ctx.get_history_kl_quota(get_detail=False)
    finally:
        ctx.close()
    if ret != RET_OK:
        return {"available": False, "error": str(data)}
    if isinstance(data, tuple):
        used = int(data[0])
        remaining = int(data[1])
        total = used + remaining
    else:
        row = data.iloc[0]
        total = int(row.get("total_quota", 0))
        used = int(row.get("used_quota", 0))
        remaining = total - used
    return {"available": True, "used": used, "remaining": remaining, "total": total}


def collect_quota_worker(host: str, port: int, q: mp.Queue) -> None:
    try:
        q.put(collect_quota(host, port))
    except Exception as exc:
        q.put({"available": False, "error": repr(exc)})


def collect_quota_with_timeout(host: str, port: int, timeout_sec: int) -> dict[str, Any]:
    q: mp.Queue = mp.Queue()
    p = mp.Process(target=collect_quota_worker, args=(host, port, q))
    p.start()
    p.join(timeout_sec)
    if p.is_alive():
        p.terminate()
        p.join()
        return {"available": False, "error": "quota_check_timeout", "timeout_sec": timeout_sec}
    if q.empty():
        return {"available": False, "error": "quota_check_no_output"}
    return q.get()


def fetch_futu_kline(ticker: str, start: str, end: str, host: str, port: int) -> pd.DataFrame | None:
    from futu import AuType, KLType, KL_FIELD, OpenQuoteContext, RET_OK

    ctx = OpenQuoteContext(host=host, port=port)
    all_data = []
    page_key = None
    try:
        while True:
            ret, df, page_key = ctx.request_history_kline(
                code=ticker,
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
                ],
                max_count=1000,
                page_req_key=page_key,
            )
            if ret != RET_OK:
                return None
            all_data.append(df)
            if page_key is None:
                break
    finally:
        ctx.close()
    if not all_data:
        return None
    result = pd.concat(all_data, ignore_index=True)
    if result.empty:
        return None
    result = result.drop_duplicates(subset="time_key")
    result["date"] = pd.to_datetime(result["time_key"]).dt.date
    result = result.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"})
    return result[["date", "Open", "High", "Low", "Close", "Volume"]].sort_values("date").reset_index(drop=True)


def fetch_worker(ticker: str, start: str, end: str, host: str, port: int, cache_dir: str, q: mp.Queue) -> None:
    try:
        df = fetch_futu_kline(ticker, start, end, host, port)
        if df is None or df.empty:
            q.put({"ticker": ticker, "status": "empty_or_error"})
            return
        path = cache_path(Path(cache_dir), ticker)
        df.to_csv(path, index=False)
        q.put(
            {
                "ticker": ticker,
                "status": "ok",
                "rows": int(len(df)),
                "start": str(pd.to_datetime(df["date"]).min().date()),
                "end": str(pd.to_datetime(df["date"]).max().date()),
                "path": str(path),
            }
        )
    except Exception as exc:
        q.put({"ticker": ticker, "status": "error", "error": repr(exc)})


def fetch_with_timeout(ticker: str, start: str, end: str, host: str, port: int, cache_dir: Path, timeout_sec: int) -> dict[str, Any]:
    q: mp.Queue = mp.Queue()
    p = mp.Process(target=fetch_worker, args=(ticker, start, end, host, port, str(cache_dir), q))
    p.start()
    p.join(timeout_sec)
    if p.is_alive():
        p.terminate()
        p.join()
        return {"ticker": ticker, "status": "timeout", "timeout_sec": timeout_sec}
    if q.empty():
        return {"ticker": ticker, "status": "no_output"}
    return q.get()


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch selected US daily K-line history into backtest_results/price_cache.")
    parser.add_argument("--universe", default="")
    parser.add_argument("--tickers", default="")
    parser.add_argument("--start", default="2012-01-01")
    parser.add_argument("--end", default="2026-05-19")
    parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=11111)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-fetch", type=int, default=0)
    parser.add_argument("--timeout-sec", type=int, default=45)
    parser.add_argument("--quota-timeout-sec", type=int, default=8)
    parser.add_argument("--skip-quota-check", action="store_true")
    parser.add_argument("--report", default="")
    args = parser.parse_args()

    if args.tickers:
        tickers = sorted({ticker.strip() for ticker in args.tickers.split(",") if ticker.strip()})
    elif args.universe:
        tickers = load_tickers_from_universe(Path(args.universe))
    else:
        raise SystemExit("Provide --tickers or --universe")

    cache_dir = Path(args.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    missing = [ticker for ticker in tickers if args.force or not cache_fresh_enough(cache_dir, ticker, args.end)]
    if args.max_fetch > 0:
        missing = missing[: args.max_fetch]

    quota = {"available": False, "skipped": True} if args.skip_quota_check else collect_quota_with_timeout(args.host, args.port, args.quota_timeout_sec)
    rows: list[dict[str, Any]] = []
    preflight = {"quota": quota, "total_requested": len(tickers), "to_fetch": len(missing)}
    print(json.dumps({"preflight": preflight}, ensure_ascii=False))

    if args.dry_run:
        rows = [{"ticker": ticker, "status": "would_fetch"} for ticker in missing]
    else:
        for ticker in missing:
            row = fetch_with_timeout(ticker, args.start, args.end, args.host, args.port, cache_dir, args.timeout_sec)
            rows.append(row)
            print(json.dumps(row, ensure_ascii=False))

    report = Path(args.report) if args.report else ROOT / "backtest_results" / "v6b_radar_momentum" / "v6b_fetch_price_cache_latest.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps({"preflight": preflight, "rows": rows}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"report={report}")


if __name__ == "__main__":
    main()
