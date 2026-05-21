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
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parent
DEFAULT_POLICY = ROOT / "v6_strategy_lab" / "configs" / "v6a_auto_execution_policy_v1.json"


@dataclass(frozen=True)
class CommandResult:
    command: list[str]
    returncode: int
    stdout_tail: str
    stderr_tail: str


def now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def load_json(path: Path, default: Any | None = None) -> Any:
    if not path.exists():
        return {} if default is None else default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def resolve_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path.resolve())


def tail(text: str, limit: int = 2500) -> str:
    return str(text or "")[-limit:]


def run_command(command: list[str]) -> CommandResult:
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
    return CommandResult(
        command=command,
        returncode=int(completed.returncode),
        stdout_tail=tail(completed.stdout),
        stderr_tail=tail(completed.stderr),
    )


def parse_hhmm(value: str) -> tuple[int, int]:
    hour, minute = str(value).split(":", 1)
    return int(hour), int(minute)


def market_now(policy: dict[str, Any], *, override_time: str = "") -> dict[str, Any]:
    window = policy["market_window"]
    tz = ZoneInfo(window.get("timezone", "America/New_York"))
    now = datetime.now(tz)
    if override_time:
        hour, minute = parse_hhmm(override_time)
        now = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    start_h, start_m = parse_hhmm(window.get("start", "09:40"))
    end_h, end_m = parse_hhmm(window.get("end", "10:20"))
    start = now.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
    end = now.replace(hour=end_h, minute=end_m, second=0, microsecond=0)
    weekday_ok = (now.weekday() < 5) or not bool(window.get("weekdays_only", True))
    return {
        "now": now.isoformat(timespec="seconds"),
        "market_date": now.date().isoformat(),
        "timezone": str(window.get("timezone", "America/New_York")),
        "window": f"{window.get('start')}->{window.get('end')}",
        "weekday_ok": weekday_ok,
        "in_window": bool(weekday_ok and start <= now <= end),
    }


def load_managed_state(runner_policy: dict[str, Any]) -> dict[str, Any]:
    state_path = resolve_path(runner_policy["execution"]["managed_positions_state_file"])
    payload = load_json(state_path, {"positions": {}, "pending_orders": []})
    payload["_path"] = rel(state_path)
    return payload


def auto_state(policy: dict[str, Any]) -> dict[str, Any]:
    return load_json(resolve_path(policy["state_file"]), {"real_executions": []})


def executions_today(state: dict[str, Any], market_date: str) -> list[dict[str, Any]]:
    return [row for row in state.get("real_executions", []) if row.get("market_date") == market_date]


def parse_runner_stdout(stdout: str) -> dict[str, Any]:
    text = str(stdout or "").strip()
    if not text:
        return {}
    start = text.find("{")
    if start < 0:
        return {}
    try:
        return json.loads(text[start:])
    except json.JSONDecodeError:
        return {}


def load_runner_payload(runner_output: dict[str, Any]) -> dict[str, Any]:
    path = runner_output.get("outputs", {}).get("run_json")
    if not path:
        return {}
    return load_json(resolve_path(path), {})


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def preflight_blockers(
    *,
    policy: dict[str, Any],
    runner_policy: dict[str, Any],
    market: dict[str, Any],
    managed_state: dict[str, Any],
    state: dict[str, Any],
    force_window: bool,
) -> list[str]:
    blockers: list[str] = []
    if not bool(policy.get("auto_enabled", False)):
        blockers.append("auto_policy_disabled")
    if not bool(runner_policy.get("execution", {}).get("auto_real_orders_allowed", False)):
        blockers.append("runner_policy_auto_real_orders_not_allowed")
    if resolve_path(policy["kill_switch_file"]).exists():
        blockers.append("kill_switch_file_present")
    if not market["in_window"] and not force_window:
        blockers.append("outside_market_window")
    pending = managed_state.get("pending_orders", []) or []
    if policy.get("preflight", {}).get("require_pending_orders_zero", True) and pending:
        blockers.append(f"pending_orders_not_zero:{len(pending)}")
    today = executions_today(state, market["market_date"])
    limit = int(policy.get("daily_limits", {}).get("max_real_executions_per_day", 1))
    if len(today) >= limit:
        blockers.append(f"daily_real_execution_limit_reached:{len(today)}/{limit}")
    return blockers


def run_reconciliation(tag: str, timeout_sec: float) -> CommandResult:
    return run_command([sys.executable, "v6a_real_reconciliation.py", "--tag", tag, "--timeout-sec", str(timeout_sec)])


def run_guarded_runner(tag: str, *, execute_real: bool, confirm: str, runner_policy_path: Path) -> CommandResult:
    command = [sys.executable, "v6a_guarded_runner.py", "--policy", str(runner_policy_path), "--tag", tag]
    if execute_real:
        command.extend(["--execute-real", "--confirm", confirm])
    return run_command(command)


def runner_order_limits_ok(policy: dict[str, Any], runner_payload: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    summary = runner_payload.get("order_summary", {}) or {}
    max_notional = as_float(policy.get("daily_limits", {}).get("max_total_notional_usd"), 0.0)
    max_orders = int(policy.get("daily_limits", {}).get("max_order_count", 0))
    if max_notional > 0 and as_float(summary.get("total_notional")) > max_notional:
        blockers.append("auto_total_notional_exceeds_limit")
    if max_orders > 0 and int(summary.get("count", 0) or 0) > max_orders:
        blockers.append("auto_order_count_exceeds_limit")
    return blockers


def persist(policy: dict[str, Any], tag: str, payload: dict[str, Any]) -> dict[str, str]:
    out_dir = resolve_path(policy["output_dir"])
    runs_dir = out_dir / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    run_json = runs_dir / f"v6a_auto_guarded_executor_{tag}.json"
    latest_json = out_dir / "latest_run.json"
    write_json(run_json, payload)
    write_json(latest_json, payload)
    return {"run_json": rel(run_json), "latest_json": rel(latest_json)}


def record_execution(policy: dict[str, Any], state: dict[str, Any], market: dict[str, Any], exec_payload: dict[str, Any]) -> None:
    state.setdefault("real_executions", [])
    state["real_executions"].append(
        {
            "timestamp": now_text(),
            "market_date": market["market_date"],
            "decision": exec_payload.get("decision"),
            "order_summary": exec_payload.get("order_summary", {}),
            "artifacts": exec_payload.get("artifacts", {}),
        }
    )
    write_json(resolve_path(policy["state_file"]), state)


def main() -> int:
    parser = argparse.ArgumentParser(description="V6-A guarded auto-execution wrapper.")
    parser.add_argument("--policy", default=str(DEFAULT_POLICY))
    parser.add_argument("--tag", default="")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force-window", action="store_true")
    parser.add_argument("--override-market-time", default="")
    parser.add_argument("--reconciliation-timeout-sec", type=float, default=30.0)
    args = parser.parse_args()

    policy_path = resolve_path(args.policy)
    policy = load_json(policy_path)
    runner_policy_path = resolve_path(policy["runner_policy"])
    runner_policy = load_json(runner_policy_path)
    tag = args.tag or f"v6a_auto_{datetime.now().strftime('%Y%m%dT%H%M%S')}"
    market = market_now(policy, override_time=args.override_market_time)
    state = auto_state(policy)
    commands: dict[str, Any] = {}

    early_blockers = []
    if not bool(policy.get("auto_enabled", False)):
        early_blockers.append("auto_policy_disabled")
    if not bool(runner_policy.get("execution", {}).get("auto_real_orders_allowed", False)):
        early_blockers.append("runner_policy_auto_real_orders_not_allowed")
    if resolve_path(policy["kill_switch_file"]).exists():
        early_blockers.append("kill_switch_file_present")
    if early_blockers and not args.dry_run:
        payload = {
            "generated_at": now_text(),
            "tag": tag,
            "policy_path": rel(policy_path),
            "runner_policy_path": rel(runner_policy_path),
            "dry_run": bool(args.dry_run),
            "decision": "POLICY_DISABLED",
            "blockers": early_blockers,
            "market": market,
            "managed_state": load_managed_state(runner_policy),
            "plan": {},
            "execute": {},
            "commands": {},
            "boundaries": policy.get("boundaries", []),
        }
        outputs = persist(policy, tag, payload)
        print(json.dumps({"decision": payload["decision"], "blockers": early_blockers, "outputs": outputs}, ensure_ascii=False, indent=2))
        return 0

    pre_recon = run_reconciliation(f"{tag}_pre_reconcile", args.reconciliation_timeout_sec)
    commands["pre_reconciliation"] = asdict(pre_recon)
    managed_state = load_managed_state(runner_policy)
    blockers = preflight_blockers(
        policy=policy,
        runner_policy=runner_policy,
        market=market,
        managed_state=managed_state,
        state=state,
        force_window=bool(args.force_window),
    )
    if policy.get("preflight", {}).get("require_reconciliation_ok", True) and pre_recon.returncode != 0:
        blockers.append("pre_reconciliation_failed")

    plan = run_guarded_runner(f"{tag}_plan", execute_real=False, confirm="", runner_policy_path=runner_policy_path)
    commands["plan_runner"] = asdict(plan)
    plan_output = parse_runner_stdout(plan.stdout_tail)
    plan_payload = load_runner_payload(plan_output)
    plan_decision = plan_payload.get("decision", plan_output.get("decision", "UNKNOWN"))
    plan_blockers = list(plan_payload.get("blockers", plan_output.get("blockers", [])) or [])
    order_summary = plan_payload.get("order_summary", {}) or {}
    executable_count = int(order_summary.get("count", 0) or 0)

    no_orders = executable_count <= 0 and "no_executable_orders" in plan_blockers
    if no_orders and policy.get("preflight", {}).get("allow_no_executable_orders", True):
        decision = "NO_OP_AT_TARGET"
    elif plan.returncode != 0 or plan_decision not in {"READY_FOR_MANUAL_CONFIRM"}:
        blockers.append(f"plan_not_ready:{plan_decision}:{plan_blockers}")
        decision = "BLOCKED"
    else:
        blockers.extend(runner_order_limits_ok(policy, plan_payload))
        decision = "READY_TO_AUTO_EXECUTE"

    exec_payload: dict[str, Any] = {}
    if decision == "READY_TO_AUTO_EXECUTE" and not blockers and not args.dry_run:
        confirm = str(policy.get("execution", {}).get("confirm_phrase", ""))
        executed = run_guarded_runner(f"{tag}_execute", execute_real=True, confirm=confirm, runner_policy_path=runner_policy_path)
        commands["execute_runner"] = asdict(executed)
        exec_output = parse_runner_stdout(executed.stdout_tail)
        exec_payload = load_runner_payload(exec_output)
        if executed.returncode == 0 and exec_payload.get("decision") == "EXECUTED_REAL":
            decision = "EXECUTED_REAL"
            record_execution(policy, state, market, exec_payload)
            if policy.get("postflight", {}).get("run_reconciliation_after_execution", True):
                post_recon = run_reconciliation(f"{tag}_post_reconcile", args.reconciliation_timeout_sec)
                commands["post_reconciliation"] = asdict(post_recon)
                if post_recon.returncode != 0:
                    blockers.append("post_reconciliation_failed")
        else:
            blockers.append(f"execute_runner_failed:{exec_output.get('decision', 'UNKNOWN')}")
            decision = "BLOCKED"
    elif decision == "READY_TO_AUTO_EXECUTE" and args.dry_run:
        decision = "DRY_RUN_READY_TO_EXECUTE"

    if blockers:
        decision = "BLOCKED"

    payload = {
        "generated_at": now_text(),
        "tag": tag,
        "policy_path": rel(policy_path),
        "runner_policy_path": rel(runner_policy_path),
        "dry_run": bool(args.dry_run),
        "decision": decision,
        "blockers": blockers,
        "market": market,
        "managed_state": load_managed_state(runner_policy),
        "plan": {
            "decision": plan_decision,
            "blockers": plan_blockers,
            "order_summary": order_summary,
            "artifacts": plan_payload.get("artifacts", {}),
        },
        "execute": exec_payload,
        "commands": commands,
        "boundaries": policy.get("boundaries", []),
    }
    outputs = persist(policy, tag, payload)
    print(json.dumps({"decision": decision, "blockers": blockers, "outputs": outputs}, ensure_ascii=False, indent=2))
    return 0 if decision in {"NO_OP_AT_TARGET", "DRY_RUN_READY_TO_EXECUTE", "EXECUTED_REAL"} and not blockers else 2


if __name__ == "__main__":
    raise SystemExit(main())
