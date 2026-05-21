#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any


def ensure_futu_home(home_dir: str | Path) -> Path:
    path = Path(home_dir)
    path.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HOME", str(path))
    return path


def _records(data: Any) -> list[dict[str, Any]]:
    if data is None:
        return []
    if hasattr(data, "to_dict"):
        return data.to_dict("records")
    return []


def fetch_account_snapshot(
    *,
    host: str = "127.0.0.1",
    port: int = 11111,
    acc_id: str,
    trd_env: str = "REAL",
    trd_market: str = "US",
    security_firm: str = "FUTUSECURITIES",
    home_dir: str | Path | None = None,
) -> dict[str, Any]:
    if home_dir:
        ensure_futu_home(home_dir)

    from futu import OpenSecTradeContext, RET_OK, SecurityFirm, TrdEnv, TrdMarket

    env = TrdEnv.REAL if str(trd_env).upper() == "REAL" else TrdEnv.SIMULATE
    market = getattr(TrdMarket, str(trd_market).upper(), TrdMarket.NONE)
    firm = getattr(SecurityFirm, str(security_firm).upper(), SecurityFirm.FUTUSECURITIES)
    ctx = OpenSecTradeContext(filter_trdmarket=market, host=host, port=port, security_firm=firm)
    warnings: list[str] = []
    try:
        ret_pos, pos_df = ctx.position_list_query(trd_env=env, acc_id=int(acc_id), refresh_cache=True)
        if ret_pos != RET_OK:
            warnings.append(f"position_list_query_failed:{ret_pos}:{pos_df}")
            positions = []
        else:
            positions = _records(pos_df)

        ret_acc, acc_df = ctx.accinfo_query(trd_env=env, acc_id=int(acc_id), refresh_cache=True)
        if ret_acc != RET_OK:
            warnings.append(f"accinfo_query_failed:{ret_acc}:{acc_df}")
            capital_rows = []
        else:
            capital_rows = _records(acc_df)
    finally:
        ctx.close()

    capital = capital_rows[0] if capital_rows else {}
    payload = {
        "ok": not warnings,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "account": {"acc_id": str(acc_id), "trd_env": str(trd_env), "trd_market": str(trd_market)},
        "capital": capital,
        "positions": positions,
        "position_summary": {
            "positions_count": len([row for row in positions if float(row.get("qty", 0.0) or 0.0) > 0]),
            "long_positions_market_value_usd": sum(
                float(row.get("market_val", 0.0) or 0.0)
                for row in positions
                if str(row.get("code", "")).upper().startswith("US.") and float(row.get("qty", 0.0) or 0.0) > 0
            ),
        },
        "warnings": warnings,
    }
    return payload


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Fetch a read-only Futu account snapshot.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=11111)
    parser.add_argument("--acc-id", required=True)
    parser.add_argument("--trd-env", default="REAL")
    parser.add_argument("--trd-market", default="US")
    parser.add_argument("--security-firm", default="FUTUSECURITIES")
    parser.add_argument("--home-dir", default="")
    args = parser.parse_args()

    payload = fetch_account_snapshot(
        host=args.host,
        port=args.port,
        acc_id=args.acc_id,
        trd_env=args.trd_env,
        trd_market=args.trd_market,
        security_firm=args.security_firm,
        home_dir=args.home_dir or None,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
