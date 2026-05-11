#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "backtest_results" / "v6_daily_report_runner"


def run(command: list[str]) -> dict[str, Any]:
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
    return {
        "command": command,
        "returncode": completed.returncode,
        "stdout_tail": completed.stdout[-3000:],
        "stderr_tail": completed.stderr[-3000:],
    }


def main() -> None:
    tag = datetime.now().strftime("v6_daily_auto_%Y%m%dT%H%M%S")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    steps = [
        run([sys.executable, "v6a_real_reconciliation.py", "--tag", tag]),
        run([sys.executable, "v6_reporting.py", "--period", "daily", "--tag", tag, "--send-email"]),
    ]
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "tag": tag,
        "status": "PASS" if all(step["returncode"] == 0 for step in steps) else "FAIL",
        "steps": steps,
    }
    out = OUT_DIR / f"{tag}.json"
    latest = OUT_DIR / "latest.json"
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    out.write_text(text, encoding="utf-8")
    latest.write_text(text, encoding="utf-8")
    print(text)
    if payload["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
