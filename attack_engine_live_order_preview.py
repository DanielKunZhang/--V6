#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import multiprocessing as mp
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List

import pandas as pd


ROOT = Path(__file__).parent
V3_REPO = ROOT / "cash_alpha_v3_repo"
OUT_DIR = ROOT / "backtest_results" / "attack_engine_live_preview"
DEFAULT_DAILY = ROOT / "backtest_results" / "attack_engine_replay" / "attack_replay_daily_20260506_v1.csv"
DEFAULT_FUTU_HOME_DIR = ROOT / ".tmp_futu_home"


def as_float(value: Any, default: float = math.nan) -> float:
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def fmt_usd(value: Any) -> str:
    value = as_float(value)
    if math.isnan(value):
        return ""
    return f"${value:,.2f}"


def fmt_pct(value: Any) -> str:
    value = as_float(value)
    if math.isnan(value):
        return ""
    return f"{value:.2f}%"


def load_module(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def normalize_code(value: Any) -> str:
    return str(value or "").strip().upper()


def parse_weights(value: str) -> Dict[str, float]:
    payload = json.loads(value)
    return {normalize_code(key): float(val) for key, val in payload.items()}


def latest_weights_by_candidate(daily_path: Path) -> pd.DataFrame:
    daily = pd.read_csv(daily_path)
    daily["date"] = pd.to_datetime(daily["date"])
    rows = []
    for cid, sub in daily.sort_values("date").groupby("candidate_id", sort=False):
        row = sub.iloc[-1]
        rows.append(
            {
                "candidate_id": str(cid),
                "signal_date": row["date"].date().isoformat(),
                "weights": parse_weights(row["weights_json"]),
            }
        )
    return pd.DataFrame(rows)


def composite_equal_weights(rows: pd.DataFrame) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for weights in rows["weights"]:
        for ticker, weight in weights.items():
            out[ticker] = out.get(ticker, 0.0) + float(weight) / len(rows)
    return out


def scale_weights(weights: Dict[str, float], max_gross: float) -> Dict[str, float]:
    noncash = {ticker: weight for ticker, weight in weights.items() if ticker != "CASH"}
    gross = sum(abs(weight) for weight in noncash.values())
    if gross > max_gross and gross > 0:
        scale = max_gross / gross
        noncash = {ticker: weight * scale for ticker, weight in noncash.items()}
    out = dict(noncash)
    out["CASH"] = 1.0 - sum(out.values())
    return out


def fetch_live_quotes(codes: Iterable[str], *, host: str, port: int, home_dir: Path) -> Dict[str, Any]:
    result = {"ok": False, "quotes": {}, "warnings": [], "snapshot_time": ""}
    tickers = sorted({normalize_code(code) for code in codes if normalize_code(code) and normalize_code(code) != "CASH"})
    if not tickers:
        result["ok"] = True
        return result
    try:
        account_mod = load_module("v6_futu_account_snapshot", V3_REPO / "futu_account_snapshot.py")
        account_mod.ensure_futu_home(home_dir)
        from futu import OpenQuoteContext, RET_OK

        ctx = OpenQuoteContext(host=host, port=port)
        try:
            ret, data = ctx.get_market_snapshot(tickers)
            if ret != RET_OK or data is None or data.empty:
                result["warnings"].append(f"get_market_snapshot_failed:{ret}:{data}")
                return result
            snapshot_time = ""
            for row in data.to_dict("records"):
                code = normalize_code(row.get("code"))
                last = positive_first(row.get("last_price"), row.get("close_price"), row.get("prev_close_price"))
                bid = as_float(row.get("bid_price"), 0.0)
                ask = as_float(row.get("ask_price"), 0.0)
                if bid <= 0:
                    bid = last
                if ask <= 0:
                    ask = last
                update_time = str(row.get("update_time") or row.get("data_time") or row.get("time") or "").strip()
                if update_time and not snapshot_time:
                    snapshot_time = update_time
                if last <= 0 and bid <= 0 and ask <= 0:
                    result["warnings"].append(f"bad_quote:{code}")
                    continue
                mid = (bid + ask) / 2.0 if bid > 0 and ask > 0 else positive_first(last, bid, ask)
                result["quotes"][code] = {
                    "last": round(float(positive_first(last, mid)), 6),
                    "bid": round(float(bid), 6),
                    "ask": round(float(ask), 6),
                    "mid": round(float(mid), 6),
                    "update_time": update_time,
                }
            result["snapshot_time"] = snapshot_time
        finally:
            ctx.close()
    except Exception as exc:
        result["warnings"].append(f"live_quote_exception:{exc}")
        return result
    missing = [ticker for ticker in tickers if ticker not in result["quotes"]]
    if missing:
        result["warnings"].append(f"quote_missing:{','.join(missing)}")
        return result
    result["ok"] = True
    return result


def positive_first(*values: Any) -> float:
    for value in values:
        number = as_float(value, 0.0)
        if number > 0:
            return number
    return 0.0


def fetch_account(*, host: str, port: int, acc_id: str, trd_env: str, home_dir: Path) -> Dict[str, Any]:
    try:
        account_mod = load_module("v6_futu_account_snapshot_account", V3_REPO / "futu_account_snapshot.py")
        return account_mod.fetch_account_snapshot(
            host=host,
            port=port,
            acc_id=acc_id,
            trd_env=trd_env,
            trd_market="US",
            security_firm="FUTUSECURITIES",
            home_dir=home_dir,
        )
    except Exception as exc:
        return {"ok": False, "warnings": [f"account_snapshot_exception:{exc}"], "positions": [], "capital": {}}


def _quote_worker(queue: mp.Queue, payload: Dict[str, Any]) -> None:
    try:
        result = fetch_live_quotes(
            payload["tickers"],
            host=payload["host"],
            port=payload["port"],
            home_dir=Path(payload["home_dir"]),
        )
    except Exception as exc:
        result = {"ok": False, "quotes": {}, "warnings": [f"quote_worker_exception:{exc}"], "snapshot_time": ""}
    queue.put(result)


def _account_worker(queue: mp.Queue, payload: Dict[str, Any]) -> None:
    try:
        result = fetch_account(
            host=payload["host"],
            port=payload["port"],
            acc_id=payload["acc_id"],
            trd_env=payload["trd_env"],
            home_dir=Path(payload["home_dir"]),
        )
    except Exception as exc:
        result = {"ok": False, "warnings": [f"account_worker_exception:{exc}"], "positions": [], "capital": {}}
    queue.put(result)


def run_worker_with_timeout(target, payload: Dict[str, Any], timeout_sec: float, fallback: Dict[str, Any]) -> Dict[str, Any]:
    queue: mp.Queue = mp.Queue()
    process = mp.Process(target=target, args=(queue, payload))
    process.start()
    process.join(timeout=max(float(timeout_sec), 1.0))
    if process.is_alive():
        process.terminate()
        process.join(2)
        return fallback
    if not queue.empty():
        return queue.get()
    return fallback


def current_position_qty(account_snapshot: Dict[str, Any], tickers: Iterable[str]) -> Dict[str, float]:
    wanted = {normalize_code(ticker) for ticker in tickers}
    out = {ticker: 0.0 for ticker in wanted}
    for row in account_snapshot.get("positions", []) or []:
        code = normalize_code(row.get("code"))
        if code in out:
            out[code] += as_float(row.get("qty"), 0.0)
    return out


def resolve_account_cash(account_snapshot: Dict[str, Any]) -> Dict[str, float]:
    capital = dict(account_snapshot.get("capital", {}) or {})
    account = dict(account_snapshot.get("account", {}) or {})
    return {
        "deployable_cash_usd": positive_first(
            account_snapshot.get("program_investable_capital_usd"),
            account_snapshot.get("available_cash_usd"),
            account_snapshot.get("buying_power_usd"),
            capital.get("deployable_cash_usd"),
            account.get("available_funds_usd"),
            account.get("cash_usd"),
            account.get("us_cash"),
        ),
        "total_assets_usd": positive_first(
            account_snapshot.get("net_liquidation_usd"),
            capital.get("total_assets_usd"),
            account.get("total_assets_usd"),
            account.get("net_assets_usd"),
        ),
    }


def build_order_preview(
    *,
    weights: Dict[str, float],
    quotes: Dict[str, Any],
    account_snapshot: Dict[str, Any],
    strategy_capital: float,
    max_gross: float,
    max_order_value: float,
    min_order_value: float,
    net_existing_positions: bool,
) -> pd.DataFrame:
    scaled = scale_weights(weights, max_gross)
    tickers = sorted(ticker for ticker in scaled if ticker != "CASH")
    current_qty = current_position_qty(account_snapshot, tickers) if net_existing_positions else {ticker: 0.0 for ticker in tickers}
    rows = []
    for ticker in tickers:
        quote = quotes.get(ticker, {})
        target_weight = float(scaled.get(ticker, 0.0))
        target_value = strategy_capital * target_weight
        reference_price = positive_first(quote.get("ask"), quote.get("last"), quote.get("mid"))
        target_qty = math.floor(target_value / reference_price) if reference_price > 0 and target_value > 0 else 0
        delta_qty = int(target_qty - current_qty.get(ticker, 0.0))
        side = "BUY" if delta_qty > 0 else ("SELL" if delta_qty < 0 else "HOLD")
        order_price = positive_first(quote.get("ask") if side == "BUY" else quote.get("bid"), quote.get("last"), quote.get("mid"))
        order_value = abs(delta_qty) * order_price
        capped_qty = delta_qty
        if max_order_value > 0 and order_value > max_order_value and order_price > 0:
            capped_qty = int(math.floor(max_order_value / order_price)) * (1 if delta_qty > 0 else -1)
            order_value = abs(capped_qty) * order_price
        rows.append(
            {
                "ticker": ticker,
                "side": "HOLD" if capped_qty == 0 else side,
                "target_weight": round(target_weight, 8),
                "target_value": round(target_value, 2),
                "current_qty_used_for_netting": round(float(current_qty.get(ticker, 0.0)), 6),
                "target_qty": int(target_qty),
                "preview_qty": int(capped_qty),
                "order_price": round(float(order_price), 4),
                "preview_order_value": round(float(order_value), 2),
                "bid": round(as_float(quote.get("bid"), 0.0), 4),
                "ask": round(as_float(quote.get("ask"), 0.0), 4),
                "last": round(as_float(quote.get("last"), 0.0), 4),
                "update_time": quote.get("update_time", ""),
                "order_value_ok": bool(order_value >= min_order_value) if capped_qty != 0 else True,
            }
        )
    return pd.DataFrame(rows)


def write_report(
    md_path: Path,
    *,
    orders: pd.DataFrame,
    weights: Dict[str, float],
    account_snapshot: Dict[str, Any],
    quote_result: Dict[str, Any],
    strategy_capital: float,
    max_gross: float,
    net_existing_positions: bool,
    signal_date: str,
) -> None:
    cash = resolve_account_cash(account_snapshot)
    warnings = list(account_snapshot.get("warnings", []) or []) + list(quote_result.get("warnings", []) or [])
    total_preview_buy = float(orders.loc[orders["side"] == "BUY", "preview_order_value"].sum()) if not orders.empty else 0.0
    lines = [
        "# V6 Attack Engine Live Order Preview",
        "",
        f"- Generated: `{datetime.now().isoformat(timespec='seconds')}`",
        f"- Signal date: `{signal_date}`",
        f"- Strategy capital: `{strategy_capital:,.2f}`",
        f"- Max gross exposure: `{max_gross:.2f}x`",
        f"- Net existing account positions: `{net_existing_positions}`",
        f"- Quote snapshot time: `{quote_result.get('snapshot_time', '')}`",
        f"- Account deployable cash estimate: `{fmt_usd(cash.get('deployable_cash_usd'))}`",
        f"- Total preview buy notional: `{fmt_usd(total_preview_buy)}`",
        f"- Warnings: `{warnings}`",
        "",
        "## Target Weights",
        "",
        "| ticker | weight |",
        "| --- | ---: |",
    ]
    for ticker, weight in sorted(scale_weights(weights, max_gross).items()):
        lines.append(f"| {ticker} | {fmt_pct(float(weight) * 100)} |")
    lines.extend(
        [
            "",
            "## Preview Orders",
            "",
            "| ticker | side | target weight | target value | target qty | preview qty | price | value | bid/ask |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for _, row in orders.iterrows():
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row["ticker"]),
                    str(row["side"]),
                    fmt_pct(as_float(row["target_weight"]) * 100),
                    fmt_usd(row["target_value"]),
                    str(int(row["target_qty"])),
                    str(int(row["preview_qty"])),
                    fmt_usd(row["order_price"]),
                    fmt_usd(row["preview_order_value"]),
                    f"{fmt_usd(row['bid'])}/{fmt_usd(row['ask'])}",
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- This is read-only preview. It does not call `place_order`.",
            "- Default mode does not net long-term account holdings, so V6 remains an independent small sleeve.",
            "- The current V6 signal still comes from replay cache. Production should refresh historical bars to today before using this preview for live trading.",
        ]
    )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only live order preview for V6 attack engine.")
    parser.add_argument("--daily", default=str(DEFAULT_DAILY))
    parser.add_argument("--strategy-capital", type=float, default=5000.0)
    parser.add_argument("--max-gross", type=float, default=1.0)
    parser.add_argument("--max-order-value", type=float, default=5000.0)
    parser.add_argument("--min-order-value", type=float, default=25.0)
    parser.add_argument("--net-existing-positions", action="store_true")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=11111)
    parser.add_argument("--acc-id", default="")
    parser.add_argument("--trd-env", default="REAL")
    parser.add_argument("--home-dir", default=str(DEFAULT_FUTU_HOME_DIR))
    parser.add_argument("--quote-timeout-sec", type=float, default=12.0)
    parser.add_argument("--account-timeout-sec", type=float, default=12.0)
    parser.add_argument("--tag", default="latest")
    args = parser.parse_args()

    latest = latest_weights_by_candidate(Path(args.daily))
    weights = composite_equal_weights(latest)
    signal_date = str(latest["signal_date"].max())
    tickers = sorted(ticker for ticker in weights if ticker != "CASH")

    quote_result = run_worker_with_timeout(
        _quote_worker,
        {"tickers": tickers, "host": args.host, "port": args.port, "home_dir": args.home_dir},
        args.quote_timeout_sec,
        {
            "ok": False,
            "quotes": {},
            "warnings": [f"quote_timeout:{args.quote_timeout_sec:.0f}s"],
            "snapshot_time": "",
        },
    )
    account_snapshot = run_worker_with_timeout(
        _account_worker,
        {
            "host": args.host,
            "port": args.port,
            "acc_id": args.acc_id,
            "trd_env": args.trd_env,
            "home_dir": args.home_dir,
        },
        args.account_timeout_sec,
        {
            "ok": False,
            "warnings": [f"account_timeout:{args.account_timeout_sec:.0f}s"],
            "positions": [],
            "capital": {},
            "account": {},
        },
    )
    orders = build_order_preview(
        weights=weights,
        quotes=quote_result.get("quotes", {}),
        account_snapshot=account_snapshot,
        strategy_capital=args.strategy_capital,
        max_gross=args.max_gross,
        max_order_value=args.max_order_value,
        min_order_value=args.min_order_value,
        net_existing_positions=args.net_existing_positions,
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    orders_path = OUT_DIR / f"attack_live_order_preview_orders_{args.tag}.csv"
    account_path = OUT_DIR / f"attack_live_order_preview_account_{args.tag}.json"
    quotes_path = OUT_DIR / f"attack_live_order_preview_quotes_{args.tag}.json"
    md_path = OUT_DIR / f"attack_live_order_preview_report_{args.tag}.md"
    orders.to_csv(orders_path, index=False)
    account_path.write_text(json.dumps(account_snapshot, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    quotes_path.write_text(json.dumps(quote_result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    write_report(
        md_path,
        orders=orders,
        weights=weights,
        account_snapshot=account_snapshot,
        quote_result=quote_result,
        strategy_capital=args.strategy_capital,
        max_gross=args.max_gross,
        net_existing_positions=args.net_existing_positions,
        signal_date=signal_date,
    )

    print("== V6 Live Order Preview ==")
    print(f"Orders:  {orders_path}")
    print(f"Account: {account_path}")
    print(f"Quotes:  {quotes_path}")
    print(f"Report:  {md_path}")


if __name__ == "__main__":
    main()
