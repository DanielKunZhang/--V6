#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
DEFAULT_STATE = ROOT / "backtest_results" / "v6a_state" / "v6a_managed_positions_real_281756481449956811.json"
OUT_DIR = ROOT / "backtest_results" / "v6a_reconciliation"


def normalize_code(value: Any) -> str:
    return str(value or "").strip().upper()


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "strategy": "V6-A ATTACK_EQUAL_REPLAY",
            "positions": {},
            "pending_orders": [],
        }
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def query_broker_snapshot(*, host: str, port: int, acc_id: str, start: str, end: str) -> dict[str, Any]:
    from futu import OpenSecTradeContext, RET_OK, TrdEnv

    ctx = OpenSecTradeContext(host=host, port=port, filter_trdmarket="US", security_firm="FUTUSECURITIES")
    try:
        rows: list[dict[str, Any]] = []
        ret, data = ctx.order_list_query(trd_env=TrdEnv.REAL, acc_id=int(acc_id), refresh_cache=True)
        if ret != RET_OK:
            raise RuntimeError(f"order_list_query failed: {data}")
        rows.extend(data.to_dict("records") if hasattr(data, "to_dict") else [])

        ret, data = ctx.history_order_list_query(trd_env=TrdEnv.REAL, acc_id=int(acc_id), start=start, end=end)
        if ret != RET_OK:
            raise RuntimeError(f"history_order_list_query failed: {data}")
        rows.extend(data.to_dict("records") if hasattr(data, "to_dict") else [])

        ret, pos_data = ctx.position_list_query(trd_env=TrdEnv.REAL, acc_id=int(acc_id), refresh_cache=True)
        if ret != RET_OK:
            raise RuntimeError(f"position_list_query failed: {pos_data}")
        positions = {}
        for row in pos_data.to_dict("records") if hasattr(pos_data, "to_dict") else []:
            code = normalize_code(row.get("code"))
            qty = float(row.get("qty", 0.0) or 0.0)
            if code and qty > 0:
                positions[code] = {
                    "qty": qty,
                    "market_val": float(row.get("market_val", 0.0) or 0.0),
                    "current_price": float(row.get("nominal_price", row.get("last_price", 0.0)) or 0.0),
                }
        return {
            "ok": True,
            "orders": {str(row.get("order_id", "")): row for row in rows if str(row.get("order_id", ""))},
            "account_positions": positions,
            "warnings": [],
        }
    finally:
        ctx.close()


def _broker_worker(queue: mp.Queue, payload: dict[str, Any]) -> None:
    try:
        queue.put(query_broker_snapshot(**payload))
    except Exception as exc:
        queue.put({"ok": False, "orders": {}, "account_positions": {}, "warnings": [str(exc)]})


def query_broker_snapshot_with_timeout(*, timeout_sec: float, **payload: Any) -> dict[str, Any]:
    queue: mp.Queue = mp.Queue()
    process = mp.Process(target=_broker_worker, args=(queue, payload))
    process.start()
    process.join(max(float(timeout_sec), 1.0))
    if process.is_alive():
        process.terminate()
        process.join(2)
        return {"ok": False, "orders": {}, "account_positions": {}, "warnings": [f"broker_query_timeout:{timeout_sec:.0f}s"]}
    if not queue.empty():
        return queue.get()
    return {"ok": False, "orders": {}, "account_positions": {}, "warnings": ["broker_query_empty_result"]}


def is_final_status(status: str) -> bool:
    text = str(status or "").upper()
    return text in {"FILLED_ALL", "CANCELLED_ALL", "FAILED", "DISABLED", "DELETED"}


def reconcile_state(state: dict[str, Any], order_rows: dict[str, dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    positions = {normalize_code(code): float(qty) for code, qty in dict(state.get("positions", {}) or {}).items()}
    pending = list(state.get("pending_orders", []) or [])
    remaining = []
    events = []

    for item in pending:
        order_id = str(item.get("order_id", ""))
        row = order_rows.get(order_id, {})
        status = str(row.get("order_status", item.get("last_status", item.get("status", ""))))
        if not row:
            status = "MISSING_FROM_BROKER_QUERY"
        dealt_qty = float(row.get("dealt_qty", 0.0) or 0.0)
        avg_price = float(row.get("dealt_avg_price", 0.0) or 0.0)
        applied_qty = float(item.get("applied_dealt_qty", 0.0) or 0.0)
        new_dealt_qty = max(dealt_qty - applied_qty, 0.0)
        ticker = normalize_code(item.get("ticker"))
        side = str(item.get("side", "")).upper()

        event = {
            "order_id": order_id,
            "ticker": ticker,
            "side": side,
            "status": status,
            "dealt_qty": dealt_qty,
            "new_dealt_qty": new_dealt_qty,
            "dealt_avg_price": avg_price,
        }
        events.append(event)

        if new_dealt_qty > 0:
            if side == "BUY":
                positions[ticker] = positions.get(ticker, 0.0) + new_dealt_qty
            elif side == "SELL":
                positions[ticker] = max(positions.get(ticker, 0.0) - new_dealt_qty, 0.0)

        if not is_final_status(status):
            updated = dict(item)
            updated["last_status"] = status
            updated["applied_dealt_qty"] = dealt_qty
            updated["last_checked_at"] = datetime.now().isoformat(timespec="seconds")
            remaining.append(updated)

    state["positions"] = {code: qty for code, qty in sorted(positions.items()) if abs(qty) > 1e-9}
    state["pending_orders"] = remaining
    state["updated_at"] = datetime.now().isoformat(timespec="seconds")
    summary = {
        "events": events,
        "remaining_pending_count": len(remaining),
        "positions": state["positions"],
    }
    return state, summary


def write_report(path: Path, summary: dict[str, Any], state_path: Path) -> None:
    lines = [
        "# V6-A Real Reconciliation",
        "",
        f"- Generated: `{datetime.now().isoformat(timespec='seconds')}`",
        f"- State file: `{state_path}`",
        f"- Broker query ok: `{summary.get('broker_query_ok')}`",
        f"- Broker warnings: `{'; '.join(summary.get('broker_warnings', [])) or 'none'}`",
        f"- Remaining pending orders: `{summary['remaining_pending_count']}`",
        "",
        "## Events",
        "",
        "| order_id | ticker | side | status | dealt_qty | new_dealt_qty | avg_price |",
        "| --- | --- | --- | --- | ---: | ---: | ---: |",
    ]
    for row in summary["events"]:
        lines.append(
            f"| {row['order_id']} | {row['ticker']} | {row['side']} | {row['status']} | "
            f"{row['dealt_qty']:.4f} | {row.get('new_dealt_qty', 0.0):.4f} | {row['dealt_avg_price']:.4f} |"
        )
    lines.extend(["", "## Managed Positions", "", "| ticker | qty |", "| --- | ---: |"])
    for code, qty in summary["positions"].items():
        lines.append(f"| {code} | {float(qty):.4f} |")
    lines.extend(["", "## Account Positions Snapshot", "", "| ticker | qty | market value | current price |", "| --- | ---: | ---: | ---: |"])
    for code, row in sorted((summary.get("account_positions") or {}).items()):
        lines.append(
            f"| {code} | {float(row.get('qty', 0.0)):.4f} | "
            f"{float(row.get('market_val', 0.0)):.2f} | {float(row.get('current_price', 0.0)):.4f} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def pending_date_range(state: dict[str, Any]) -> tuple[str, str]:
    dates = []
    for item in state.get("pending_orders", []) or []:
        raw = str(item.get("timestamp", ""))[:10]
        if raw:
            dates.append(raw)
    today = datetime.now().date().isoformat()
    return (min(dates) if dates else today), today


def main() -> None:
    parser = argparse.ArgumentParser(description="Reconcile V6-A REAL pending orders into managed positions state.")
    parser.add_argument("--state", default=str(DEFAULT_STATE))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=11111)
    parser.add_argument("--acc-id", default="281756481449956811")
    parser.add_argument("--tag", default=datetime.now().strftime("%Y%m%dT%H%M%S"))
    parser.add_argument("--timeout-sec", type=float, default=20.0)
    args = parser.parse_args()

    state_path = Path(args.state)
    state = load_json(state_path)
    start, end = pending_date_range(state)
    broker = query_broker_snapshot_with_timeout(
        host=args.host,
        port=args.port,
        acc_id=args.acc_id,
        start=start,
        end=end,
        timeout_sec=args.timeout_sec,
    )
    order_rows = broker.get("orders", {}) or {}
    new_state, summary = reconcile_state(state, order_rows)
    summary["broker_query_ok"] = bool(broker.get("ok"))
    summary["broker_warnings"] = list(broker.get("warnings", []))
    summary["account_positions"] = broker.get("account_positions", {}) or {}
    write_json(state_path, new_state)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUT_DIR / f"v6a_reconciliation_{args.tag}.json"
    md_path = OUT_DIR / f"v6a_reconciliation_{args.tag}.md"
    write_json(json_path, summary)
    write_report(md_path, summary, state_path)
    print(json.dumps({"summary": summary, "json": str(json_path), "report": str(md_path)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
