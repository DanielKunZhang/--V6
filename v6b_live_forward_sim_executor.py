#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from attack_engine_live_order_preview import DEFAULT_FUTU_HOME_DIR, fetch_account, fetch_live_quotes, normalize_code, positive_first
from attack_engine_sim_executor import place_sim_orders


ROOT = Path(__file__).parent
OUT_DIR = ROOT / "backtest_results" / "v6b_live_forward_sim"
DEFAULT_SCORECARD = ROOT / "v6_strategy_lab" / "scorecards" / "v6b_scorecard_20260511_live_forward_seed.json"


def as_float(value: Any, default: float = math.nan) -> float:
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def current_us_positions(account_snapshot: Dict[str, Any]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for row in account_snapshot.get("positions", []) or []:
        code = normalize_code(row.get("code"))
        if not code.startswith("US."):
            continue
        qty = as_float(row.get("qty"), 0.0)
        if qty > 0 and abs(qty - round(qty)) < 1e-9:
            out[code] = out.get(code, 0) + int(round(qty))
    return out


def select_candidates(scorecard: Dict[str, Any], *, top_n: int, status: str, max_same_track: int) -> List[Dict[str, Any]]:
    rows = [row for row in scorecard.get("rows", []) if row.get("status") == status]
    rows.sort(key=lambda row: (as_float(row.get("score"), 0.0), str(row.get("ticker"))), reverse=True)
    selected: List[Dict[str, Any]] = []
    track_counts: Dict[str, int] = {}
    for row in rows:
        track = str(row.get("track", ""))
        if track_counts.get(track, 0) >= max_same_track:
            continue
        selected.append(row)
        track_counts[track] = track_counts.get(track, 0) + 1
        if len(selected) >= top_n:
            break
    return selected


def build_orders(
    selected: List[Dict[str, Any]],
    quotes: Dict[str, Any],
    account: Dict[str, Any],
    *,
    strategy_capital: float,
    max_order_value: float,
    liquidate_non_target_us_positions: bool,
) -> pd.DataFrame:
    current = current_us_positions(account)
    tickers = [str(row["ticker"]) for row in selected]
    codes = set(tickers)
    if liquidate_non_target_us_positions:
        codes.update(current)

    target_weight = 1.0 / len(tickers) if tickers else 0.0
    rows = []
    for code in sorted(codes):
        quote = quotes.get(code, {})
        ask = positive_first(quote.get("ask"), quote.get("last"), quote.get("mid"))
        bid = positive_first(quote.get("bid"), quote.get("last"), quote.get("mid"))
        price_for_target = ask
        target_qty = 0
        if code in tickers and price_for_target > 0:
            target_qty = int(math.floor(strategy_capital * target_weight / price_for_target))
        current_qty = int(current.get(code, 0))
        delta = target_qty - current_qty
        side = "HOLD" if delta == 0 else ("BUY" if delta > 0 else "SELL")
        order_price = positive_first(ask if side == "BUY" else bid, quote.get("last"), quote.get("mid"))
        preview_qty = abs(delta)
        preview_value = preview_qty * order_price
        if max_order_value > 0 and preview_value > max_order_value and order_price > 0:
            preview_qty = int(math.floor(max_order_value / order_price))
            preview_value = preview_qty * order_price
        score_row = next((row for row in selected if str(row.get("ticker")) == code), {})
        rows.append(
            {
                "code": code,
                "side": "HOLD" if preview_qty == 0 else side,
                "score": as_float(score_row.get("score"), 0.0),
                "track": str(score_row.get("track", "")),
                "current_qty": current_qty,
                "target_qty": target_qty,
                "delta_qty": delta,
                "preview_qty": int(preview_qty),
                "order_price": round(float(order_price), 4),
                "preview_order_value": round(float(preview_value), 2),
                "bid": round(as_float(quote.get("bid"), 0.0), 4),
                "ask": round(as_float(quote.get("ask"), 0.0), 4),
                "last": round(as_float(quote.get("last"), 0.0), 4),
                "update_time": quote.get("update_time", ""),
            }
        )
    out = pd.DataFrame(rows)
    if not out.empty:
        side_rank = {"SELL": 0, "BUY": 1, "HOLD": 2}
        out["_side_rank"] = out["side"].map(side_rank).fillna(9)
        out = out.sort_values(["_side_rank", "code"]).drop(columns=["_side_rank"]).reset_index(drop=True)
    return out


def write_report(
    path: Path,
    *,
    scorecard_path: Path,
    selected: List[Dict[str, Any]],
    orders: pd.DataFrame,
    results: List[Dict[str, Any]],
    execute: bool,
    strategy_capital: float,
) -> None:
    lines = [
        "# V6-B Live-Forward SIM Executor",
        "",
        f"- Generated: `{datetime.now().isoformat(timespec='seconds')}`",
        f"- Mode: `{'EXECUTE_SIMULATE' if execute else 'PLAN_ONLY'}`",
        "- Trade env: `SIMULATE`",
        f"- Strategy capital: `${strategy_capital:,.2f}`",
        f"- Scorecard: `{scorecard_path}`",
        "- Boundary: live-forward engineering / behavior test only; not historical validation.",
        "",
        "## Selected Candidates",
        "",
        "| rank | ticker | track | score |",
        "| ---: | --- | --- | ---: |",
    ]
    for idx, row in enumerate(selected, start=1):
        lines.append(f"| {idx} | `{row['ticker']}` | `{row['track']}` | {as_float(row['score'], 0.0):.2f} |")
    lines.extend(["", "## Orders", "", "| code | side | score | current | target | qty | price | value | bid/ask |", "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"])
    for _, row in orders.iterrows():
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row["code"]),
                    str(row["side"]),
                    f"{as_float(row['score'], 0.0):.2f}",
                    str(int(row["current_qty"])),
                    str(int(row["target_qty"])),
                    str(int(row["preview_qty"])),
                    f"${as_float(row['order_price'], 0.0):,.2f}",
                    f"${as_float(row['preview_order_value'], 0.0):,.2f}",
                    f"${as_float(row['bid'], 0.0):,.2f}/${as_float(row['ask'], 0.0):,.2f}",
                ]
            )
            + " |"
        )
    lines.extend(["", "## Results", "", "```json", json.dumps(results, ensure_ascii=False, indent=2, default=str), "```"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="V6-B live-forward simulator runner.")
    parser.add_argument("--scorecard", default=str(DEFAULT_SCORECARD))
    parser.add_argument("--strategy-capital", type=float, default=5000.0)
    parser.add_argument("--max-order-value", type=float, default=2500.0)
    parser.add_argument("--top-n", type=int, default=3)
    parser.add_argument("--status", default="eligible_research")
    parser.add_argument("--max-same-track", type=int, default=2)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=11111)
    parser.add_argument("--sim-acc-id", default="19005590")
    parser.add_argument("--home-dir", default=str(DEFAULT_FUTU_HOME_DIR))
    parser.add_argument("--liquidate-non-target-us-positions", action="store_true")
    parser.add_argument("--execute-sim", action="store_true")
    parser.add_argument("--tag", default=datetime.now().strftime("%Y%m%d_%H%M%S"))
    args = parser.parse_args()

    scorecard_path = Path(args.scorecard)
    scorecard = json.loads(scorecard_path.read_text(encoding="utf-8"))
    selected = select_candidates(scorecard, top_n=args.top_n, status=args.status, max_same_track=args.max_same_track)
    if not selected:
        raise SystemExit(f"no candidates selected for status={args.status}")

    codes = sorted(str(row["ticker"]) for row in selected)
    quotes = fetch_live_quotes(codes, host=args.host, port=args.port, home_dir=Path(args.home_dir))
    if not quotes.get("ok"):
        raise SystemExit(f"quote fetch failed: {quotes.get('warnings')}")
    account = fetch_account(
        host=args.host,
        port=args.port,
        acc_id=args.sim_acc_id,
        trd_env="SIMULATE",
        home_dir=Path(args.home_dir),
    )
    if account.get("warnings"):
        raise SystemExit(f"account warnings: {account.get('warnings')}")

    orders = build_orders(
        selected,
        quotes.get("quotes", {}),
        account,
        strategy_capital=args.strategy_capital,
        max_order_value=args.max_order_value,
        liquidate_non_target_us_positions=args.liquidate_non_target_us_positions,
    )
    results = (
        place_sim_orders(orders, host=args.host, port=args.port, acc_id=args.sim_acc_id, home_dir=Path(args.home_dir))
        if args.execute_sim
        else []
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    slug = args.tag
    orders_path = OUT_DIR / f"v6b_live_forward_orders_{slug}.csv"
    results_path = OUT_DIR / f"v6b_live_forward_results_{slug}.json"
    report_path = OUT_DIR / f"v6b_live_forward_report_{slug}.md"
    payload_path = OUT_DIR / f"v6b_live_forward_payload_{slug}.json"
    orders.to_csv(orders_path, index=False)
    results_path.write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    payload_path.write_text(
        json.dumps(
            {
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "mode": "EXECUTE_SIMULATE" if args.execute_sim else "PLAN_ONLY",
                "scorecard": str(scorecard_path),
                "selected": selected,
                "quote_warnings": quotes.get("warnings", []),
                "account_warnings": account.get("warnings", []),
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )
    write_report(
        report_path,
        scorecard_path=scorecard_path,
        selected=selected,
        orders=orders,
        results=results,
        execute=args.execute_sim,
        strategy_capital=args.strategy_capital,
    )
    print("== V6-B Live-Forward SIM Executor ==")
    print(f"Mode:    {'EXECUTE_SIMULATE' if args.execute_sim else 'PLAN_ONLY'}")
    print(f"Orders:  {orders_path}")
    print(f"Results: {results_path}")
    print(f"Payload: {payload_path}")
    print(f"Report:  {report_path}")


if __name__ == "__main__":
    sys.exit(main())
