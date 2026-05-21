#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

import v6ab_evidence_ledger as ledger_mod
import v6ab_mainline_classifier as clf_mod


ROOT = Path(__file__).resolve().parent
DESKTOP_ROOT = Path("/Users/zhangkun/Desktop/AI个人投资公司")
REPORT_ROOT = DESKTOP_ROOT / "报表输出" / "LATEST"
OUT_DIR = ROOT / "backtest_results" / "v6ab_daily_evolution" / "pit_replay"
DEFAULT_HISTORICAL_EVIDENCE = ROOT / "backtest_results" / "v6ab_historical_evidence" / "latest.json"
DEFAULT_EVENT_FACT_LEDGER = ROOT / "backtest_results" / "v6ab_event_facts" / "latest.json"


def _parse_date(value: Any) -> pd.Timestamp | None:
    try:
        if value in (None, ""):
            return None
        return pd.Timestamp(value).normalize()
    except Exception:
        return None


def build_full_seed(args: argparse.Namespace) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    rows.extend(ledger_mod.parse_x_radar(args.x_radar, args.end))
    rows.extend(ledger_mod.parse_13f(args.__dict__["13f"], args.end))
    rows.extend(ledger_mod.parse_valuation(args.valuation, args.end))
    extra_paths = [item.strip() for item in str(args.extra_evidence_json or "").split(",") if item.strip()]
    for extra in extra_paths:
        extra_path = Path(extra)
        if extra_path.exists():
            payload = json.loads(extra_path.read_text(encoding="utf-8"))
            rows.extend(payload.get("rows", []))
    return [row for row in rows if row.get("ticker")]


def visible_rows(seed_rows: list[dict[str, Any]], asof: str) -> list[dict[str, Any]]:
    asof_ts = pd.Timestamp(asof).normalize()
    rows: list[dict[str, Any]] = []
    for row in seed_rows:
        source_ts = _parse_date(row.get("source_date"))
        expiry_ts = _parse_date(row.get("expiry_date"))
        if source_ts is not None and source_ts > asof_ts:
            continue
        if expiry_ts is not None and expiry_ts < asof_ts:
            continue
        item = dict(row)
        item["asof"] = asof
        item["freshness"] = round(ledger_mod.freshness(asof, str(item.get("source_date", asof))), 4)
        rows.append(item)
    return rows


def replay_dates(start: str, end: str, freq: str) -> list[str]:
    if freq == "M":
        freq = "ME"
    dates = list(pd.date_range(start=start, end=end, freq=freq))
    end_ts = pd.Timestamp(end).normalize()
    if not dates or pd.Timestamp(dates[-1]).normalize() != end_ts:
        dates.append(end_ts)
    return [str(pd.Timestamp(dt).date()) for dt in dates]


def replay(args: argparse.Namespace) -> dict[str, Any]:
    seed_rows = build_full_seed(args)
    snapshots: list[dict[str, Any]] = []
    for asof in replay_dates(args.start, args.end, args.freq):
        rows = visible_rows(seed_rows, asof)
        ledger = {"asof": asof, "rows": rows}
        classifier = clf_mod.build_classifier(ledger, asof, taxonomy=args.taxonomy)
        snapshots.append(
            {
                "asof": asof,
                "evidence_count": len(rows),
                "theme_allowlist": classifier.get("theme_allowlist", []),
                "watchlist": classifier.get("watchlist", []),
                "boost_allowlist": classifier.get("boost_allowlist", []),
                "override_allowlist": classifier.get("override_allowlist", []),
                "b_sleeve_cap_hint": classifier.get("b_sleeve_cap_hint", 0.05),
                "fallback_to_v2": classifier.get("fallback_to_v2", True),
                "themes": classifier.get("themes", []),
                "ticker_priority": classifier.get("ticker_priority", []),
            }
        )
    return {
        "asof": args.asof,
        "start": args.start,
        "end": args.end,
        "freq": args.freq,
        "taxonomy": args.taxonomy,
        "source_boundary": "local_seed_visible_asof_only",
        "source_files": {
            "x_radar": str(args.x_radar),
            "13f": str(args.__dict__["13f"]),
            "valuation": str(args.valuation),
            "extra_evidence_json": str(args.extra_evidence_json),
        },
        "seed_evidence_count": len(seed_rows),
        "snapshots": snapshots,
    }


def render_md(payload: dict[str, Any]) -> str:
    snapshots = payload["snapshots"]
    active = [snap for snap in snapshots if snap.get("theme_allowlist")]
    latest = snapshots[-1] if snapshots else {}
    lines = [
        "# V6AB PIT Evidence + Classifier Replay v1",
        "",
        f"- 日期：`{payload['asof']}`",
        f"- replay 区间：`{payload['start']} -> {payload['end']}`",
        f"- replay 频率：`{payload['freq']}`",
        f"- seed evidence：`{payload['seed_evidence_count']}`",
        f"- 有 allowlist 的快照数：`{len(active)} / {len(snapshots)}`",
        "- 边界：只使用当前本地证据源的 source_date/as_of/last_updated 做 PIT 可见性过滤；不是完整历史新闻/财报证据库。",
        "- 价格边界：classifier 市场分数按每个 asof 截断本地价格缓存，避免未来价格泄漏。",
        "",
        "## Latest Snapshot",
        "",
        f"- asof：`{latest.get('asof', '')}`",
        f"- allowlist：`{', '.join(latest.get('theme_allowlist', [])) or 'none'}`",
        f"- boost：`{', '.join(latest.get('boost_allowlist', [])) or 'none'}`",
        f"- override：`{', '.join(latest.get('override_allowlist', [])) or 'none'}`",
        f"- B cap hint：`{float(latest.get('b_sleeve_cap_hint', 0.05)):.0%}`",
        "",
        "## Recent Snapshots",
        "",
        "| asof | evidence | allowlist | b_cap | fallback |",
        "| --- | ---: | --- | ---: | --- |",
    ]
    for snap in snapshots[-12:]:
        lines.append(
            f"| {snap['asof']} | {snap['evidence_count']} | `{', '.join(snap.get('theme_allowlist', [])) or 'none'}` | "
            f"{float(snap.get('b_sleeve_cap_hint', 0.05)):.0%} | `{snap.get('fallback_to_v2')}` |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay V6AB evidence ledger and mainline classifier point-in-time.")
    parser.add_argument("--asof", default=str(date.today()))
    parser.add_argument("--start", default="2012-05-21")
    parser.add_argument("--end", default="2026-05-19")
    parser.add_argument("--freq", default="ME")
    parser.add_argument("--x-radar", type=Path, default=ledger_mod.DEFAULT_X_RADAR)
    parser.add_argument("--13f", type=Path, default=ledger_mod.DEFAULT_13F)
    parser.add_argument("--valuation", type=Path, default=ledger_mod.DEFAULT_VALUATION)
    parser.add_argument("--extra-evidence-json", default=f"{DEFAULT_HISTORICAL_EVIDENCE},{DEFAULT_EVENT_FACT_LEDGER}")
    parser.add_argument("--taxonomy", choices=["ai", "historical"], default="historical")
    parser.add_argument("--output-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    payload = replay(args)
    md = render_md(payload)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "latest_pit_classifier_replay.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.output_dir / "latest_pit_classifier_replay.md").write_text(md, encoding="utf-8")
    (REPORT_ROOT / "V6AB_PIT_Classifier_Replay_LATEST.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (REPORT_ROOT / "V6AB_PIT_Classifier_Replay_LATEST.md").write_text(md, encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
