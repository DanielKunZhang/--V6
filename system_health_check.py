#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import socket
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent
HOME = Path.home()
EXPECTED_USER = "zhangkun"
DESKTOP_ROOT = HOME / "Desktop" / "AI个人投资公司"
OFFICIAL_EVENTS = ROOT / "events_calendar.json"
CLAUDE_X_CMD = HOME / ".claude" / "commands" / "X扫描.md"
LOCAL_ENV = ROOT / ".ic_env.local"


@dataclass
class Check:
    status: str
    name: str
    detail: str = ""


class Reporter:
    def __init__(self) -> None:
        self.rows: list[Check] = []

    def ok(self, name: str, detail: str = "") -> None:
        self.rows.append(Check("PASS", name, detail))

    def warn(self, name: str, detail: str = "") -> None:
        self.rows.append(Check("WARN", name, detail))

    def fail(self, name: str, detail: str = "") -> None:
        self.rows.append(Check("FAIL", name, detail))

    def print(self) -> int:
        for row in self.rows:
            icon = {"PASS": "✅", "WARN": "⚠️", "FAIL": "❌"}[row.status]
            suffix = f" — {row.detail}" if row.detail else ""
            print(f"{icon} {row.status:4} {row.name}{suffix}")
        fails = sum(1 for row in self.rows if row.status == "FAIL")
        warns = sum(1 for row in self.rows if row.status == "WARN")
        print("")
        print(f"Summary: {fails} fail(s), {warns} warning(s), {len(self.rows)} check(s)")
        return 2 if fails else 0


def read_local_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if key:
            values[key] = value
    return values


def check_file(rep: Reporter, path: Path, name: str, required: bool = True) -> None:
    if path.exists():
        rep.ok(name, str(path))
    elif required:
        rep.fail(name, f"missing: {path}")
    else:
        rep.warn(name, f"missing: {path}")


def check_json(rep: Reporter, path: Path, name: str) -> None:
    if not path.exists():
        rep.fail(name, f"missing: {path}")
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        rep.fail(name, f"invalid JSON: {exc}")
        return
    count = len(data) if isinstance(data, list) else 1
    rep.ok(name, f"{path} ({count} item(s))")


def check_module(rep: Reporter, module: str, required: bool = True) -> None:
    if importlib.util.find_spec(module) is not None:
        rep.ok(f"Python module: {module}")
    elif required:
        rep.fail(f"Python module: {module}", "install dependencies")
    else:
        rep.warn(f"Python module: {module}", "optional dependency missing")


def check_port(rep: Reporter, host: str, port: int, name: str, required: bool = False) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1.0)
    try:
        sock.connect((host, port))
    except OSError as exc:
        if required:
            rep.fail(name, f"{host}:{port} unavailable: {exc}")
        else:
            rep.warn(name, f"{host}:{port} unavailable; ok if OpenD is intentionally closed")
    else:
        rep.ok(name, f"{host}:{port}")
    finally:
        sock.close()


def run_deep_command(rep: Reporter, cmd: list[str], name: str) -> None:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(ROOT),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=60,
            check=False,
        )
    except Exception as exc:
        rep.fail(name, str(exc))
        return
    if proc.returncode == 0:
        rep.ok(name)
    else:
        tail = "\n".join(proc.stdout.splitlines()[-8:])
        rep.fail(name, tail)


def main() -> int:
    parser = argparse.ArgumentParser(description="Investment system migration health check.")
    parser.add_argument("--deep", action="store_true", help="Run read-only workflow smoke tests.")
    parser.add_argument("--require-futu", action="store_true", help="Treat Futu OpenD port failure as FAIL.")
    args = parser.parse_args()

    rep = Reporter()

    rep.ok("Current machine", f"user={HOME.name}, macOS={platform.mac_ver()[0] or 'unknown'}, python={sys.version.split()[0]}")
    if HOME.name != EXPECTED_USER:
        rep.warn("macOS username differs from historical absolute paths", f"current={HOME.name}, expected={EXPECTED_USER}")

    check_file(rep, ROOT / "morning_brief.py", "Daily Board script")
    check_file(rep, ROOT / "central_risk_board.py", "Central Risk Board script")
    check_json(rep, OFFICIAL_EVENTS, "Official events_calendar.json")
    check_file(rep, ROOT / "requirements.txt", "Root requirements.txt")
    check_file(rep, ROOT / "REVIEW_CADENCE_POLICY.md", "Review cadence policy")
    check_json(rep, ROOT / "investment_screener" / "radar_astock.json", "A-share Radar tracking JSON")
    check_file(rep, ROOT / "investment_screener" / "A_SHARE_RADAR_REVIEW_SOP.md", "A-share Radar review SOP")
    check_file(rep, ROOT / "investment_screener" / "A_SHARE_RADAR_AUTOMATION_ROADMAP.md", "A-share Radar automation roadmap")

    duplicate_calendar = DESKTOP_ROOT / "events_calendar.json"
    if duplicate_calendar.exists():
        rep.fail("Duplicate Desktop events_calendar.json", f"should not exist: {duplicate_calendar}")
    else:
        rep.ok("No duplicate Desktop events_calendar.json")

    check_file(rep, DESKTOP_ROOT, "Desktop investment data root")
    check_file(rep, DESKTOP_ROOT / "交易决策日志" / "decision_log.csv", "Decision log CSV")
    check_file(rep, DESKTOP_ROOT / "朋友Alpha影子跟踪" / "friend_alpha_shadow_log.csv", "Friend Alpha shadow log")
    check_file(rep, DESKTOP_ROOT / "信息源扫描" / "X_Radar" / "daily", "X Radar daily directory")
    check_file(rep, DESKTOP_ROOT / "信息源扫描" / "X_Radar" / "daily" / "summaries", "X Radar summary directory")
    check_file(rep, DESKTOP_ROOT / "26年阶段性组合策略计划.html", "Portfolio HTML source")

    check_file(rep, CLAUDE_X_CMD, "Claude /X扫描 command", required=False)
    if CLAUDE_X_CMD.exists():
        text = CLAUDE_X_CMD.read_text(encoding="utf-8", errors="ignore")
        if str(OFFICIAL_EVENTS) in text:
            rep.ok("/X扫描 points to official events_calendar.json")
        else:
            rep.warn("/X扫描 event source", "command does not explicitly reference official WorkBuddy events_calendar.json")
        obsolete_calendar = str(DESKTOP_ROOT / "events_calendar.json")
        bad_lines: list[str] = []
        for line in text.splitlines():
            if obsolete_calendar not in line:
                continue
            if any(marker in line for marker in ["不是", "不要", "not ", "NOT ", "obsolete", "非正式"]):
                continue
            bad_lines.append(line.strip())
        if bad_lines:
            rep.fail("/X扫描 references obsolete Desktop calendar", " | ".join(bad_lines[:2]))
        elif obsolete_calendar in text:
            rep.ok("/X扫描 obsolete Desktop calendar guardrail", "mentioned only as a do-not-use path")

    env_values = read_local_env(LOCAL_ENV)
    if LOCAL_ENV.exists():
        rep.ok("Local env file", str(LOCAL_ENV))
    else:
        rep.warn("Local env file", f"missing: {LOCAL_ENV}")
    if env_values.get("IC_EMAIL_PASSWORD") or os.environ.get("IC_EMAIL_PASSWORD"):
        rep.ok("IC email password configured")
    else:
        rep.warn("IC email password configured", "IC_EMAIL_PASSWORD missing")
    v6_email_keys = ["V6_EMAIL_SMTP_SERVER", "V6_EMAIL_SENDER", "V6_EMAIL_PASSWORD", "V6_EMAIL_RECIPIENT"]
    present_v6 = [key for key in v6_email_keys if env_values.get(key) or os.environ.get(key)]
    if present_v6:
        rep.ok("V6 email env configured", ",".join(present_v6))
    else:
        rep.warn("V6 email env configured", "V6_EMAIL_* missing; ok if using IC email fallback")

    for module in ["pandas", "numpy", "yaml", "requests", "futu"]:
        check_module(rep, module, required=True)
    for module in ["scipy", "yfinance", "prettytable", "apscheduler", "pytz"]:
        check_module(rep, module, required=False)

    check_port(rep, "127.0.0.1", 11111, "Futu OpenD port", required=args.require_futu)

    launch_repo_files = list((ROOT / "launchd").glob("*.plist")) + list((ROOT / "launch_agents").glob("*.plist"))
    if launch_repo_files:
        rep.ok("Repo launchd plist files", f"{len(launch_repo_files)} file(s)")
    else:
        rep.warn("Repo launchd plist files", "none found")

    user_launch_agents = HOME / "Library" / "LaunchAgents"
    if user_launch_agents.exists():
        matching = list(user_launch_agents.glob("com.dingcle*.plist")) + list(user_launch_agents.glob("com.cashalpha*.plist")) + list(user_launch_agents.glob("com.irontrade*.plist"))
        if matching:
            rep.ok("Installed LaunchAgents", f"{len(matching)} likely related file(s)")
        else:
            rep.warn("Installed LaunchAgents", "no known investment-system plist found")
    else:
        rep.warn("Installed LaunchAgents", f"missing directory: {user_launch_agents}")

    if args.deep:
        run_deep_command(rep, [sys.executable, "morning_brief.py", "--no-email"], "Deep smoke: morning_brief.py --no-email")
        run_deep_command(rep, [sys.executable, "central_risk_board.py", "--cadence", "daily", "--tag", "migration_health_check"], "Deep smoke: central_risk_board.py daily")

    return rep.print()


if __name__ == "__main__":
    raise SystemExit(main())
