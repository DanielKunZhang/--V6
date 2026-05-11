#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
DEFAULT_STATE = ROOT / "backtest_results" / "v6a_state" / "v6a_managed_positions_sim_19005590.json"
OUT_DIR = ROOT / "backtest_results" / "v6a_sim_reconciliation"
DEFAULT_STRATEGY = "V6-A ATTACK_EQUAL_REPLAY"


def normalize_code(value: Any) -> str:
    return str(value or "").strip().upper()


def load_json(path: Path, *, strategy: str) -> dict[str, Any]:
    if not path.exists():
        return {
            "strategy": strategy,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "updated_at": "",
            "positions": {},
            "pending_orders": [],
        }
    payload = json.loads(path.read_text(encoding="utf-8"))
    if str(payload.get("strategy", "")) != strategy:
        raise SystemExit(f"managed state strategy mismatch: {payload.get('strategy')} != {strategy}")
    payload.setdefault("positions", {})
    payload.setdefault("pending_orders", [])
    return payload


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def query_orders(*, host: str, port: int, acc_id: str) -> dict[str, dict[str, Any]]:
    from futu import OpenSecTradeContext, RET_OK, SecurityFirm, TrdEnv, TrdMarket

    ctx = OpenSecTradeContext(
        filter_trdmarket=TrdMarket.US,
        host=host,
        port=port,
        security_firm=SecurityFirm.FUTUSECURITIES,
    )
    try:
        ret, data = ctx.order_list_query(trd_env=TrdEnv.SIMULATE, acc_id=int(acc_id), refresh_cache=True)
        if ret != RET_OK:
            raise RuntimeError(f"order_list_query failed: {data}")
        rows = data.to_dict("records") if hasattr(data, "to_dict") else []
        return {str(row.get("order_id", "")): row for row in rows if str(row.get("order_id", ""))}
    finally:
        ctx.close()


def is_final_status(status: str) -> bool:
    text = str(status or "").upper()
    return text in {"FILLED_ALL", "CANCELLED_ALL", "FAILED", "DISABLED", "DELETED", "FILLED_PART"}


def reconcile_state(state: dict[str, Any], order_rows: dict[str, dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    positions = {normalize_code(code): float(qty) for code, qty in dict(state.get("positions", {}) or {}).items()}
    remaining = []
    events = []

    for item in list(state.get("pending_orders", []) or []):
        order_id = str(item.get("order_id", ""))
        row = order_rows.get(order_id, {})
        status = str(row.get("order_status", item.get("status", "")))
        dealt_qty = float(row.get("dealt_qty", 0.0) or 0.0)
        avg_price = float(row.get("dealt_avg_price", 0.0) or 0.0)
        code = normalize_code(item.get("code") or item.get("ticker"))
        side = str(item.get("side", "")).upper()

        event = {
            "order_id": order_id,
            "code": code,
            "side": side,
            "status": status,
            "dealt_qty": dealt_qty,
            "dealt_avg_price": avg_price,
        }
        events.append(event)

        if dealt_qty > 0:
            if side == "BUY":
                positions[code] = positions.get(code, 0.0) + dealt_qty
            elif side == "SELL":
                positions[code] = max(positions.get(code, 0.0) - dealt_qty, 0.0)

        if not is_final_status(status):
            updated = dict(item)
            updated["last_status"] = status
            updated["last_checked_at"] = datetime.now().isoformat(timespec="seconds")
            remaining.append(updated)

    state["positions"] = {code: qty for code, qty in sorted(positions.items()) if abs(qty) > 1e-9}
    state["pending_orders"] = remaining
    state["updated_at"] = datetime.now().isoformat(timespec="seconds")
    summary = {
        "status": "PASS" if not remaining else "PENDING",
        "events": events,
        "remaining_pending_count": len(remaining),
        "positions": state["positions"],
    }
    return state, summary


def write_report(path: Path, summary: dict[str, Any], state_path: Path, acc_id: str) -> None:
    lines = [
        "# V6-A Sim Reconciliation",
        "",
        f"- Generated: `{datetime.now().isoformat(timespec='seconds')}`",
        "- Trade env: `SIMULATE`",
        f"- Account: `{acc_id}`",
        f"- State file: `{state_path}`",
        f"- Status: `{summary['status']}`",
        f"- Remaining pending orders: `{summary['remaining_pending_count']}`",
        "",
        "## Events",
        "",
        "| order_id | code | side | status | dealt_qty | avg_price |",
        "| --- | --- | --- | --- | ---: | ---: |",
    ]
    for row in summary["events"]:
        lines.append(
            f"| {row['order_id']} | {row['code']} | {row['side']} | {row['status']} | "
            f"{row['dealt_qty']:.4f} | {row['dealt_avg_price']:.4f} |"
        )
    lines.extend(["", "## V6-A Managed Sim Positions", "", "| code | qty |", "| --- | ---: |"])
    for code, qty in summary["positions"].items():
        lines.append(f"| {code} | {float(qty):.4f} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Reconcile V6-A SIM pending orders into managed positions state.")
    parser.add_argument("--state", default=str(DEFAULT_STATE))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=11111)
    parser.add_argument("--acc-id", default="19005590")
    parser.add_argument("--strategy-name", default=DEFAULT_STRATEGY)
    parser.add_argument("--tag", default=datetime.now().strftime("%Y%m%dT%H%M%S"))
    args = parser.parse_args()

    state_path = Path(args.state)
    state = load_json(state_path, strategy=args.strategy_name)
    order_rows = query_orders(host=args.host, port=args.port, acc_id=args.acc_id)
    new_state, summary = reconcile_state(state, order_rows)
    write_json(state_path, new_state)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUT_DIR / f"v6a_sim_reconciliation_{args.tag}.json"
    md_path = OUT_DIR / f"v6a_sim_reconciliation_{args.tag}.md"
    write_json(json_path, summary)
    write_report(md_path, summary, state_path, args.acc_id)
    print(json.dumps({"summary": summary, "json": str(json_path), "report": str(md_path)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
