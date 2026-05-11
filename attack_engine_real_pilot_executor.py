#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd


ROOT = Path(__file__).parent
OUT_DIR = ROOT / "backtest_results" / "attack_engine_real_pilot_executor"
CONFIRM_TEXT = "EXECUTE_V6A_REAL_5000"


def load_gate(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"missing gate json: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("gate_result") != "PASS":
        raise SystemExit(f"release gate is not PASS: {payload.get('gate_result')}")
    return payload


def load_orders(path: Path, *, max_total_notional: float, max_order_value: float) -> pd.DataFrame:
    if not path.exists():
        raise SystemExit(f"missing orders csv: {path}")
    orders = pd.read_csv(path)
    required = {"ticker", "side", "preview_qty", "order_price", "preview_order_value", "order_value_ok"}
    missing = required - set(orders.columns)
    if missing:
        raise SystemExit(f"orders csv missing columns: {sorted(missing)}")

    orders = orders[orders["side"].isin(["BUY", "SELL"]) & (orders["preview_qty"].astype(float) > 0)].copy()
    if orders.empty:
        raise SystemExit("no executable orders in csv")
    if not orders["order_value_ok"].astype(bool).all():
        raise SystemExit("one or more order_value_ok checks failed")
    if float(orders["preview_order_value"].abs().sum()) > max_total_notional:
        raise SystemExit("total order notional exceeds max_total_notional")
    if float(orders["preview_order_value"].abs().max()) > max_order_value:
        raise SystemExit("single order notional exceeds max_order_value")
    return orders


def normalize_code(value: Any) -> str:
    return str(value or "").strip().upper()


def load_managed_state(path: Path, *, strategy_name: str) -> Dict[str, Any]:
    if not path.exists():
        return {
            "strategy": strategy_name,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "updated_at": "",
            "positions": {},
            "pending_orders": [],
        }
    payload = json.loads(path.read_text(encoding="utf-8"))
    if str(payload.get("strategy", "")) != strategy_name:
        raise SystemExit(f"managed state strategy mismatch: {payload.get('strategy')} != {strategy_name}")
    payload.setdefault("positions", {})
    payload.setdefault("pending_orders", [])
    return payload


def write_managed_state(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload["updated_at"] = datetime.now().isoformat(timespec="seconds")
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def validate_sells_against_managed_state(orders: pd.DataFrame, state: Dict[str, Any]) -> None:
    positions = state.get("positions", {}) if isinstance(state.get("positions"), dict) else {}
    for _, row in orders.iterrows():
        if str(row["side"]).upper() != "SELL":
            continue
        ticker = normalize_code(row["ticker"])
        sell_qty = float(row["preview_qty"])
        managed_qty = float(positions.get(ticker, 0.0))
        if sell_qty > managed_qty + 1e-9:
            raise SystemExit(f"refuse to sell unmanaged V6 shares: {ticker} sell={sell_qty} managed={managed_qty}")


def order_id_from_detail(result: Dict[str, Any]) -> str:
    detail = result.get("detail", [])
    if isinstance(detail, list) and detail:
        return str(detail[0].get("order_id", ""))
    return ""


def update_managed_state_with_results(
    path: Path,
    *,
    strategy_name: str,
    orders: pd.DataFrame,
    results: List[Dict[str, Any]],
    execute: bool,
) -> Dict[str, Any]:
    state = load_managed_state(path, strategy_name=strategy_name)
    validate_sells_against_managed_state(orders, state)
    if not execute:
        return state

    pending = list(state.get("pending_orders", []) or [])
    for result in results:
        pending.append(
            {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "ticker": normalize_code(result.get("ticker")),
                "side": str(result.get("side", "")).upper(),
                "qty": int(float(result.get("qty", 0))),
                "limit_price": float(result.get("limit_price", 0.0)),
                "preview_order_value": float(result.get("preview_order_value", 0.0)),
                "ok": bool(result.get("ok", False)),
                "order_id": order_id_from_detail(result),
                "status": "SUBMITTED_NEEDS_RECONCILIATION" if result.get("ok") else "SUBMIT_FAILED",
            }
        )
    state["pending_orders"] = pending
    write_managed_state(path, state)
    return state


def execute_orders(orders: pd.DataFrame, *, host: str, port: int, acc_id: str) -> List[Dict[str, Any]]:
    from futu import OpenSecTradeContext, OrderType, RET_OK, TrdEnv, TrdSide

    ctx = OpenSecTradeContext(
        host=host,
        port=port,
        filter_trdmarket="US",
        security_firm="FUTUSECURITIES",
    )
    results: List[Dict[str, Any]] = []
    try:
        for _, row in orders.iterrows():
            side = str(row["side"]).upper()
            trd_side = TrdSide.BUY if side == "BUY" else TrdSide.SELL
            ret, data = ctx.place_order(
                code=str(row["ticker"]),
                price=float(row["order_price"]),
                qty=int(row["preview_qty"]),
                trd_side=trd_side,
                order_type=OrderType.NORMAL,
                adjust_limit=0,
                trd_env=TrdEnv.REAL,
                acc_id=int(acc_id),
            )
            ok = bool(ret == RET_OK)
            results.append(
                {
                    "ticker": str(row["ticker"]),
                    "side": side,
                    "qty": int(row["preview_qty"]),
                    "limit_price": float(row["order_price"]),
                    "preview_order_value": float(row["preview_order_value"]),
                    "ok": ok,
                    "detail": data.to_dict("records") if ok and hasattr(data, "to_dict") else str(data),
                }
            )
    finally:
        ctx.close()
    return results


def write_report(path: Path, orders: pd.DataFrame, results: List[Dict[str, Any]], *, execute: bool) -> None:
    total = float(orders["preview_order_value"].abs().sum()) if not orders.empty else 0.0
    lines = [
        "# V6-A Real Pilot Executor",
        "",
        f"- Generated: `{datetime.now().isoformat(timespec='seconds')}`",
        f"- Mode: `{'EXECUTE_REAL' if execute else 'PLAN_ONLY'}`",
        "- Trade env: `REAL`",
        f"- Total order notional: `${total:,.2f}`",
        "",
        "## Orders",
        "",
        "| ticker | side | qty | limit price | value |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    for _, row in orders.iterrows():
        lines.append(
            f"| {row['ticker']} | {row['side']} | {int(row['preview_qty'])} | "
            f"${float(row['order_price']):,.2f} | ${float(row['preview_order_value']):,.2f} |"
        )
    lines.extend(["", "## Results", "", "```json", json.dumps(results, ensure_ascii=False, indent=2, default=str), "```"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Guarded real-account executor for V6-A first pilot.")
    parser.add_argument("--orders-csv", required=True)
    parser.add_argument("--gate-json", required=True)
    parser.add_argument("--acc-id", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=11111)
    parser.add_argument("--max-total-notional", type=float, default=5000.0)
    parser.add_argument("--max-order-value", type=float, default=5000.0)
    parser.add_argument("--tag", default="latest")
    parser.add_argument("--strategy-name", default="V6-A ATTACK_EQUAL_REPLAY")
    parser.add_argument("--managed-positions-state", default="")
    parser.add_argument("--update-managed-state", action="store_true")
    parser.add_argument("--armed", action="store_true")
    parser.add_argument("--confirm", default="")
    args = parser.parse_args()

    load_gate(Path(args.gate_json))
    orders = load_orders(Path(args.orders_csv), max_total_notional=args.max_total_notional, max_order_value=args.max_order_value)
    managed_state_path = Path(args.managed_positions_state) if args.managed_positions_state else None
    if managed_state_path is not None:
        state = load_managed_state(managed_state_path, strategy_name=args.strategy_name)
        validate_sells_against_managed_state(orders, state)

    execute = bool(args.armed and args.confirm == CONFIRM_TEXT)
    results = execute_orders(orders, host=args.host, port=args.port, acc_id=args.acc_id) if execute else []
    if managed_state_path is not None and args.update_managed_state:
        update_managed_state_with_results(
            managed_state_path,
            strategy_name=args.strategy_name,
            orders=orders,
            results=results,
            execute=execute,
        )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    orders_out = OUT_DIR / f"v6a_real_pilot_orders_{args.tag}.csv"
    results_out = OUT_DIR / f"v6a_real_pilot_results_{args.tag}.json"
    report_out = OUT_DIR / f"v6a_real_pilot_report_{args.tag}.md"
    orders.to_csv(orders_out, index=False)
    results_out.write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    write_report(report_out, orders, results, execute=execute)

    print("== V6-A Real Pilot Executor ==")
    print(f"Mode:    {'EXECUTE_REAL' if execute else 'PLAN_ONLY'}")
    print(f"Orders:  {orders_out}")
    print(f"Results: {results_out}")
    print(f"Report:  {report_out}")
    if not execute:
        print(f"Not executed. To execute, pass --armed --confirm {CONFIRM_TEXT}")


if __name__ == "__main__":
    main()
