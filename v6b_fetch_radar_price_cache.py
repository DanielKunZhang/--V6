#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

import alpha_cash_enhancement_search as alpha


ROOT = Path(__file__).parent
CACHE_DIR = ROOT / "backtest_results" / "price_cache"


def load_tickers(config_path: Path) -> List[str]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    tickers = set()
    for values in config["candidate_pool_variants"].values():
        tickers.update(values)
    tickers.update(t for t in config["defensive_pool"] if t != "CASH")
    tickers.update(["US.SPY", "US.QQQ"])
    return sorted(tickers)


def fetch_one_worker(ticker: str, start: str, end: str, home_dir: str, q: mp.Queue) -> None:
    try:
        if home_dir:
            os.environ["HOME"] = home_dir
        df = alpha.fetch_futu_kline(ticker, start, end)
        if df is None or df.empty:
            q.put({"ticker": ticker, "status": "empty"})
            return
        alpha.write_cache(ticker, CACHE_DIR, df)
        q.put(
            {
                "ticker": ticker,
                "status": "ok",
                "rows": int(len(df)),
                "start": str(pd.to_datetime(df["date"]).min().date()),
                "end": str(pd.to_datetime(df["date"]).max().date()),
            }
        )
    except Exception as exc:
        q.put({"ticker": ticker, "status": "error", "error": repr(exc)})


def fetch_one(ticker: str, start: str, end: str, home_dir: str, timeout_sec: int) -> Dict[str, Any]:
    q: mp.Queue = mp.Queue()
    p = mp.Process(target=fetch_one_worker, args=(ticker, start, end, home_dir, q))
    p.start()
    p.join(timeout_sec)
    if p.is_alive():
        p.terminate()
        p.join()
        return {"ticker": ticker, "status": "timeout", "timeout_sec": timeout_sec}
    if q.empty():
        return {"ticker": ticker, "status": "no_output"}
    return q.get()


def cache_exists(ticker: str, min_end: str) -> bool:
    cached = alpha.read_cache(ticker, CACHE_DIR, "1900-01-01", min_end)
    if cached is None or cached.empty:
        return False
    max_date = pd.to_datetime(cached["date"]).max()
    return max_date >= pd.Timestamp(min_end) - pd.Timedelta(days=10)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Radar tickers into local price_cache via Futu with per-ticker timeout.")
    parser.add_argument("--config", default="v6_strategy_lab/configs/v6b_radar_universe_20260510.json")
    parser.add_argument("--start", default="2012-01-01")
    parser.add_argument("--end", default="2026-05-08")
    parser.add_argument("--home-dir", default="/private/tmp/futu_v6b_home")
    parser.add_argument("--timeout-sec", type=int, default=20)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--only-missing", action="store_true", default=True)
    parser.add_argument("--tickers", default="", help="Optional comma-separated tickers override.")
    parser.add_argument("--report", default="")
    args = parser.parse_args()

    tickers = [t.strip() for t in args.tickers.split(",") if t.strip()] if args.tickers else load_tickers(Path(args.config))
    Path(args.home_dir).mkdir(parents=True, exist_ok=True)

    rows = []
    for ticker in tickers:
        if not args.force and args.only_missing and cache_exists(ticker, args.end):
            row = {"ticker": ticker, "status": "cached"}
        else:
            row = fetch_one(ticker, args.start, args.end, args.home_dir, args.timeout_sec)
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False))

    report = Path(args.report) if args.report else ROOT / "backtest_results" / "v6b_radar_momentum" / "v6b_fetch_price_cache_report.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"report={report}")


if __name__ == "__main__":
    main()
