#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import subprocess
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DESKTOP_DIR = Path("/Users/zhangkun/Desktop/AI个人投资公司")
PYTHON = Path("/Library/Frameworks/Python.framework/Versions/3.12/bin/python3")

REPORT_SPECS = {
    "performance_attribution": {
        "script": ROOT / "performance_attribution.py",
        "out_dir": ROOT / "backtest_results" / "performance_attribution",
        "desktop_prefix": "绩效归因看板_PERFORMANCE_ATTRIBUTION_LATEST",
    },
    "overlay_trade_journal": {
        "script": ROOT / "overlay_trade_journal.py",
        "out_dir": ROOT / "backtest_results" / "overlay_trade_journal",
        "desktop_prefix": "Radar_Overlay_Journal_LATEST",
    },
    "monthly_research_review": {
        "script": ROOT / "monthly_research_review.py",
        "out_dir": ROOT / "backtest_results" / "monthly_research_review",
        "desktop_prefix": "Monthly_Research_Review_LATEST",
    },
}

SCOPE_REPORTS = {
    "daily": ["performance_attribution", "overlay_trade_journal"],
    "monthly": ["performance_attribution", "overlay_trade_journal", "monthly_research_review"],
}


def run_report(name: str, tag: str) -> None:
    spec = REPORT_SPECS[name]
    script = spec["script"]
    if not script.exists():
        raise FileNotFoundError(f"Missing report script: {script}")
    subprocess.run([str(PYTHON), str(script), "--tag", tag], cwd=ROOT, check=True)


def sync_report(name: str) -> None:
    spec = REPORT_SPECS[name]
    out_dir = spec["out_dir"]
    desktop_prefix = spec["desktop_prefix"]
    for ext in ("md", "html", "json"):
        src = out_dir / f"latest.{ext}"
        if not src.exists():
            raise FileNotFoundError(f"Missing latest report: {src}")
        dst = DESKTOP_DIR / f"{desktop_prefix}.{ext}"
        shutil.copy2(src, dst)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run and sync governance reporting outputs.")
    parser.add_argument("--scope", choices=sorted(SCOPE_REPORTS), required=True)
    parser.add_argument("--tag", default=None)
    args = parser.parse_args()

    tag = args.tag or f"auto_{args.scope}_{datetime.now().strftime('%Y%m%dT%H%M%S')}"
    reports = SCOPE_REPORTS[args.scope]

    for report in reports:
        print(f"== Running {report} ==", flush=True)
        run_report(report, tag)
        sync_report(report)

    print("== Governance reporting runner complete ==")
    print(f"Scope: {args.scope}")
    print(f"Tag:   {tag}")
    print(f"Synced desktop directory: {DESKTOP_DIR}")


if __name__ == "__main__":
    main()
