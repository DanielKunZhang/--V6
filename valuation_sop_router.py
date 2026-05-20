#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "valuation_sop_router_config.json"


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_ticker(ticker: str) -> str:
    ticker = str(ticker or "").strip().upper()
    return ticker.replace("US.", "")


def select_framework(ticker: str, attributes: list[str], config: dict[str, Any]) -> dict[str, Any]:
    ticker_key = normalize_ticker(ticker)
    frameworks = config.get("frameworks", {})
    overrides = config.get("ticker_overrides", {})
    default_key = config.get("default_framework", "SOP_v2.5")

    if ticker_key in overrides:
        override = overrides[ticker_key]
        framework_key = override.get("framework", default_key)
        framework = frameworks.get(framework_key, {})
        return {
            "ticker": ticker_key,
            "framework_key": framework_key,
            "framework_name": framework.get("name", framework_key),
            "framework_path": framework.get("path", ""),
            "selection_source": "ticker_override",
            "why_this_framework": override.get("reason", f"{ticker_key} has explicit framework override."),
            "system_feedback_targets": override.get("system_feedback_targets") or config.get("system_feedback_targets_default", []),
        }

    attr_set = {str(attr).strip() for attr in attributes if str(attr).strip()}
    for framework_key, framework in frameworks.items():
        use_for = set(framework.get("use_for", []))
        if attr_set & use_for:
            return {
                "ticker": ticker_key,
                "framework_key": framework_key,
                "framework_name": framework.get("name", framework_key),
                "framework_path": framework.get("path", ""),
                "selection_source": "attributes",
                "why_this_framework": f"Matched attributes: {', '.join(sorted(attr_set & use_for))}",
                "system_feedback_targets": config.get("system_feedback_targets_default", []),
            }

    framework = frameworks.get(default_key, {})
    return {
        "ticker": ticker_key,
        "framework_key": default_key,
        "framework_name": framework.get("name", default_key),
        "framework_path": framework.get("path", ""),
        "selection_source": "default",
        "why_this_framework": "No AI/Core/Infrastructure attributes matched; use conservative default.",
        "system_feedback_targets": config.get("system_feedback_targets_default", []),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Select valuation SOP based on ticker and attributes.")
    parser.add_argument("ticker")
    parser.add_argument("--attrs", nargs="*", default=[])
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    config = read_json(CONFIG)
    result = select_framework(args.ticker, args.attrs, config)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    print(f"VALUATION_FRAMEWORK_SELECTED = {result['framework_key']}")
    print(f"FRAMEWORK_NAME = {result['framework_name']}")
    print(f"FRAMEWORK_PATH = {result['framework_path']}")
    print(f"SELECTION_SOURCE = {result['selection_source']}")
    print(f"WHY_THIS_FRAMEWORK = {result['why_this_framework']}")
    print(f"SYSTEM_FEEDBACK_TARGET = {', '.join(result['system_feedback_targets'])}")


if __name__ == "__main__":
    main()
