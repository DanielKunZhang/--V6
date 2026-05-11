#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parent
DEFAULT_POLICY = ROOT / "v6_strategy_lab" / "configs" / "v6a_guarded_runner_policy_v1.json"


@dataclass(frozen=True)
class CommandResult:
    command: list[str]
    returncode: int
    stdout_tail: str
    stderr_tail: str


def now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def timestamp_tag(prefix: str) -> str:
    return f"{prefix}_{datetime.now().strftime('%Y%m%dT%H%M%S')}"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def resolve_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def tail(text: str, limit: int = 1800) -> str:
    return str(text or "")[-limit:]


def run_command(command: list[str]) -> CommandResult:
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
    return CommandResult(
        command=command,
        returncode=int(completed.returncode),
        stdout_tail=tail(completed.stdout),
        stderr_tail=tail(completed.stderr),
    )


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def output_dir(policy: dict[str, Any]) -> Path:
    return resolve_path(policy["audit"]["output_dir"])


def preview_paths(preview_tag: str) -> dict[str, Path]:
    base = ROOT / "backtest_results" / "attack_engine_live_preview"
    return {
        "orders": base / f"attack_live_order_preview_orders_{preview_tag}.csv",
        "account": base / f"attack_live_order_preview_account_{preview_tag}.json",
        "quotes": base / f"attack_live_order_preview_quotes_{preview_tag}.json",
        "report": base / f"attack_live_order_preview_report_{preview_tag}.md",
    }


def gate_paths(gate_tag: str) -> dict[str, Path]:
    base = ROOT / "backtest_results" / "attack_engine_release_gate"
    return {
        "json": base / f"attack_engine_release_gate_{gate_tag}.json",
        "report": base / f"attack_engine_release_gate_{gate_tag}.md",
    }


def executor_paths(exec_tag: str) -> dict[str, Path]:
    base = ROOT / "backtest_results" / "attack_engine_real_pilot_executor"
    return {
        "orders": base / f"v6a_real_pilot_orders_{exec_tag}.csv",
        "results": base / f"v6a_real_pilot_results_{exec_tag}.json",
        "report": base / f"v6a_real_pilot_report_{exec_tag}.md",
    }


def build_preview_command(policy: dict[str, Any], preview_tag: str) -> list[str]:
    cap = policy["capital"]
    data = policy["data"]
    futu = policy["futu"]
    command = [
        sys.executable,
        "attack_engine_live_order_preview.py",
        "--daily",
        data["daily_replay_csv"],
        "--strategy-capital",
        str(cap["strategy_capital_usd"]),
        "--max-gross",
        str(cap["max_gross"]),
        "--max-order-value",
        str(cap["max_order_value_usd"]),
        "--min-order-value",
        str(cap["min_order_value_usd"]),
        "--host",
        futu["host"],
        "--port",
        str(futu["port"]),
        "--acc-id",
        futu["real_acc_id"],
        "--trd-env",
        futu["trd_env"],
        "--tag",
        preview_tag,
    ]
    if policy["execution"].get("net_existing_positions", False):
        command.append("--net-existing-positions")
    return command


def build_gate_command(policy: dict[str, Any], preview_tag: str, gate_tag: str) -> list[str]:
    data = policy["data"]
    gate = policy["release_gate"]
    paths = preview_paths(preview_tag)
    return [
        sys.executable,
        "attack_engine_release_gate.py",
        "--replay-composite",
        data["replay_composite_csv"],
        "--replay-summary",
        data["replay_summary_csv"],
        "--live-preview-orders",
        str(paths["orders"]),
        "--live-preview-quotes",
        str(paths["quotes"]),
        "--live-preview-account",
        str(paths["account"]),
        "--asof-date",
        datetime.now().date().isoformat(),
        "--max-signal-age-days",
        str(data["max_signal_age_days"]),
        "--min-full-ann",
        str(gate["min_full_ann"]),
        "--min-oos-ann",
        str(gate["min_oos_ann"]),
        "--max-full-dd",
        str(gate["max_full_dd"]),
        "--min-oos-sharpe",
        str(gate["min_oos_sharpe"]),
        "--min-equity-pct",
        str(gate["min_equity_pct"]),
        "--min-rolling-3y-ann",
        str(gate["min_rolling_3y_ann"]),
        "--min-quote-count",
        str(gate["min_quote_count"]),
        "--tag",
        gate_tag,
    ]


def build_executor_command(policy: dict[str, Any], preview_tag: str, gate_tag: str, exec_tag: str, *, execute_real: bool, confirm: str) -> list[str]:
    cap = policy["capital"]
    futu = policy["futu"]
    command = [
        sys.executable,
        "attack_engine_real_pilot_executor.py",
        "--orders-csv",
        str(preview_paths(preview_tag)["orders"]),
        "--gate-json",
        str(gate_paths(gate_tag)["json"]),
        "--acc-id",
        futu["real_acc_id"],
        "--host",
        futu["host"],
        "--port",
        str(futu["port"]),
        "--max-total-notional",
        str(cap["max_total_notional_usd"]),
        "--max-order-value",
        str(cap["max_order_value_usd"]),
        "--tag",
        exec_tag,
    ]
    if execute_real:
        command.extend(["--armed", "--confirm", confirm])
    return command


def load_orders(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def load_gate(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return load_json(path)


def load_preview_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return load_json(path)


def order_summary(orders: pd.DataFrame) -> dict[str, Any]:
    if orders.empty:
        return {"count": 0, "buy_notional": 0.0, "sell_notional": 0.0, "total_notional": 0.0, "rows": []}
    executable = orders[orders["side"].isin(["BUY", "SELL"]) & (orders["preview_qty"].astype(float).abs() > 0)].copy()
    buy = executable.loc[executable["side"] == "BUY", "preview_order_value"].abs().sum()
    sell = executable.loc[executable["side"] == "SELL", "preview_order_value"].abs().sum()
    return {
        "count": int(len(executable)),
        "buy_notional": round(float(buy), 2),
        "sell_notional": round(float(sell), 2),
        "total_notional": round(float(buy + sell), 2),
        "rows": executable.to_dict("records"),
    }


def evaluate_blockers(policy: dict[str, Any], *, gate_payload: dict[str, Any], orders: pd.DataFrame, account: dict[str, Any], quotes: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    guards = policy["risk_guards"]
    cap = policy["capital"]
    summary = order_summary(orders)

    if guards.get("block_if_release_gate_fails", True) and gate_payload.get("gate_result") != "PASS":
        blockers.append("release_gate_not_pass")
    if guards.get("block_if_no_executable_orders", True) and summary["count"] <= 0:
        blockers.append("no_executable_orders")
    if guards.get("block_if_total_notional_exceeds_policy", True) and summary["total_notional"] > as_float(cap["max_total_notional_usd"]):
        blockers.append("total_notional_exceeds_policy")
    if guards.get("block_if_any_order_value_invalid", True) and not orders.empty:
        invalid_count = int((orders.get("order_value_ok", True).astype(bool) == False).sum())
        if invalid_count > 0:
            blockers.append(f"invalid_order_value_rows:{invalid_count}")
    if guards.get("block_if_account_has_warnings", True) and account.get("warnings"):
        blockers.append(f"account_warnings:{account.get('warnings')}")
    if guards.get("block_if_quote_has_warnings", True) and quotes.get("warnings"):
        blockers.append(f"quote_warnings:{quotes.get('warnings')}")
    return blockers


def write_markdown(path: Path, payload: dict[str, Any]) -> None:
    order_rows = payload["order_summary"].get("rows", [])
    lines = [
        "# V6-A Guarded Runner",
        "",
        f"- Generated: `{payload['generated_at']}`",
        f"- Mode: `{payload['mode']}`",
        f"- Decision: `{payload['decision']}`",
        f"- Release gate: `{payload['release_gate'].get('gate_result', 'MISSING')}`",
        f"- Blockers: `{payload['blockers']}`",
        f"- Total notional: `${payload['order_summary']['total_notional']:,.2f}`",
        f"- Buy notional: `${payload['order_summary']['buy_notional']:,.2f}`",
        f"- Sell notional: `${payload['order_summary']['sell_notional']:,.2f}`",
        "",
        "## Orders",
        "",
        "| ticker | side | qty | price | value | order ok |",
        "| --- | --- | ---: | ---: | ---: | --- |",
    ]
    for row in order_rows:
        lines.append(
            f"| {row.get('ticker', '')} | {row.get('side', '')} | {int(as_float(row.get('preview_qty'), 0))} | "
            f"${as_float(row.get('order_price'), 0):,.2f} | ${as_float(row.get('preview_order_value'), 0):,.2f} | {row.get('order_value_ok', '')} |"
        )
    lines.extend(
        [
            "",
            "## Artifacts",
            "",
            f"- Preview report: `{payload['artifacts']['preview_report']}`",
            f"- Release gate report: `{payload['artifacts']['gate_report']}`",
            f"- Executor report: `{payload['artifacts'].get('executor_report', '')}`",
            "",
            "## Boundaries",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in payload.get("boundaries", []))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def persist_latest(policy: dict[str, Any], payload: dict[str, Any], run_tag: str) -> dict[str, str]:
    out_dir = output_dir(policy)
    runs_dir = out_dir / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    run_json = runs_dir / f"v6a_guarded_runner_{run_tag}.json"
    run_md = runs_dir / f"v6a_guarded_runner_{run_tag}.md"
    latest_json = out_dir / policy["audit"]["latest_json"]
    latest_md = out_dir / policy["audit"]["latest_md"]
    write_json(run_json, payload)
    write_markdown(run_md, payload)
    write_json(latest_json, payload)
    write_markdown(latest_md, payload)
    return {
        "run_json": rel(run_json),
        "run_md": rel(run_md),
        "latest_json": rel(latest_json),
        "latest_md": rel(latest_md),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Guarded V6-A runner: preview -> release gate -> optional real execution.")
    parser.add_argument("--policy", default=str(DEFAULT_POLICY))
    parser.add_argument("--tag", default="")
    parser.add_argument("--execute-real", action="store_true")
    parser.add_argument("--confirm", default="")
    args = parser.parse_args()

    policy_path = resolve_path(args.policy)
    policy = load_json(policy_path)
    run_tag = args.tag or timestamp_tag("v6a_guarded")
    preview_tag = f"{run_tag}_preview"
    gate_tag = f"{run_tag}_gate"
    exec_tag = f"{run_tag}_executor"

    preview_result = run_command(build_preview_command(policy, preview_tag))
    if preview_result.returncode != 0:
        payload = {
            "generated_at": now_text(),
            "mode": "EXECUTE_REAL" if args.execute_real else "PLAN_ONLY",
            "decision": "BLOCKED",
            "blockers": ["preview_command_failed"],
            "commands": {"preview": asdict(preview_result)},
            "artifacts": {},
            "order_summary": {"count": 0, "buy_notional": 0.0, "sell_notional": 0.0, "total_notional": 0.0, "rows": []},
            "release_gate": {},
            "boundaries": policy.get("boundaries", []),
        }
        outputs = persist_latest(policy, payload, run_tag)
        print(json.dumps({"decision": payload["decision"], "blockers": payload["blockers"], "outputs": outputs}, ensure_ascii=False, indent=2))
        raise SystemExit(1)

    gate_result = run_command(build_gate_command(policy, preview_tag, gate_tag))
    paths = preview_paths(preview_tag)
    gpaths = gate_paths(gate_tag)
    orders = load_orders(paths["orders"])
    account = load_preview_json(paths["account"])
    quotes = load_preview_json(paths["quotes"])
    gate_payload = load_gate(gpaths["json"])
    blockers = evaluate_blockers(policy, gate_payload=gate_payload, orders=orders, account=account, quotes=quotes)

    execute_requested = bool(args.execute_real)
    confirm_ok = args.confirm == policy["execution"]["manual_confirm_phrase"]
    execution_allowed = execute_requested and confirm_ok and not blockers
    executor_result: CommandResult | None = None
    if execute_requested and not confirm_ok:
        blockers.append("manual_confirm_phrase_mismatch")
    if execution_allowed:
        executor_result = run_command(
            build_executor_command(policy, preview_tag, gate_tag, exec_tag, execute_real=True, confirm=args.confirm)
        )
        if executor_result.returncode != 0:
            blockers.append("executor_command_failed")

    decision = "EXECUTED_REAL" if execution_allowed and executor_result and executor_result.returncode == 0 else ("READY_FOR_MANUAL_CONFIRM" if not blockers else "BLOCKED")
    payload = {
        "generated_at": now_text(),
        "policy_path": rel(policy_path),
        "mode": "EXECUTE_REAL" if execute_requested else "PLAN_ONLY",
        "decision": decision,
        "blockers": blockers,
        "commands": {
            "preview": asdict(preview_result),
            "gate": asdict(gate_result),
            "executor": asdict(executor_result) if executor_result else {},
        },
        "release_gate": gate_payload,
        "order_summary": order_summary(orders),
        "account_summary": {
            "timestamp": account.get("timestamp", ""),
            "acc_id": account.get("acc_id", ""),
            "available_cash_usd": account.get("available_cash_usd", 0),
            "program_investable_capital_usd": account.get("program_investable_capital_usd", 0),
            "warnings": account.get("warnings", []),
        },
        "quote_summary": {
            "ok": quotes.get("ok", False),
            "snapshot_time": quotes.get("snapshot_time", ""),
            "warnings": quotes.get("warnings", []),
        },
        "artifacts": {
            "preview_orders": rel(paths["orders"]),
            "preview_account": rel(paths["account"]),
            "preview_quotes": rel(paths["quotes"]),
            "preview_report": rel(paths["report"]),
            "gate_json": rel(gpaths["json"]),
            "gate_report": rel(gpaths["report"]),
            "executor_report": rel(executor_paths(exec_tag)["report"]) if executor_result else "",
            "executor_results": rel(executor_paths(exec_tag)["results"]) if executor_result else "",
        },
        "boundaries": policy.get("boundaries", []),
    }
    outputs = persist_latest(policy, payload, run_tag)
    print(json.dumps({"decision": decision, "blockers": blockers, "outputs": outputs}, ensure_ascii=False, indent=2))
    if blockers:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
