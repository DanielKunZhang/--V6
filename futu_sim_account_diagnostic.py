#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import signal
from contextlib import contextmanager
from typing import Any, Iterator


class TimeoutError(RuntimeError):
    pass


@contextmanager
def deadline(seconds: int, label: str) -> Iterator[None]:
    def handler(_signum: int, _frame: Any) -> None:
        raise TimeoutError(f"{label}_timeout:{seconds}s")

    previous = signal.signal(signal.SIGALRM, handler)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


def frame_records(data: Any) -> Any:
    if hasattr(data, "to_dict"):
        return data.to_dict("records")
    return str(data)


def safe_call(label: str, seconds: int, fn: Any) -> dict[str, Any]:
    try:
        with deadline(seconds, label):
            ret, data = fn()
        return {"label": label, "ret": ret, "data": frame_records(data)}
    except Exception as exc:
        return {"label": label, "error": f"{type(exc).__name__}: {exc}"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only Futu SIMULATE account diagnostic.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=11111)
    parser.add_argument("--acc-id", type=int, default=19005590)
    parser.add_argument("--timeout-sec", type=int, default=8)
    args = parser.parse_args()

    from futu import OpenSecTradeContext, TrdEnv

    ctx = OpenSecTradeContext(
        host=args.host,
        port=args.port,
        filter_trdmarket="US",
        security_firm="FUTUSECURITIES",
    )
    try:
        result = {
            "host": args.host,
            "port": args.port,
            "acc_id": args.acc_id,
            "calls": [
                safe_call("get_acc_list", args.timeout_sec, lambda: ctx.get_acc_list()),
                safe_call(
                    "accinfo_query",
                    args.timeout_sec,
                    lambda: ctx.accinfo_query(
                        trd_env=TrdEnv.SIMULATE,
                        acc_id=args.acc_id,
                        refresh_cache=True,
                    ),
                ),
                safe_call(
                    "position_list_query",
                    args.timeout_sec,
                    lambda: ctx.position_list_query(
                        trd_env=TrdEnv.SIMULATE,
                        acc_id=args.acc_id,
                        refresh_cache=True,
                    ),
                ),
                safe_call(
                    "order_list_query",
                    args.timeout_sec,
                    lambda: ctx.order_list_query(
                        trd_env=TrdEnv.SIMULATE,
                        acc_id=args.acc_id,
                        refresh_cache=True,
                    ),
                ),
            ],
        }
    finally:
        ctx.close()
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
