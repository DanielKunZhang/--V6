#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parent
DESKTOP_ROOT = Path("/Users/zhangkun/Desktop/AI个人投资公司")
REPORT_ROOT = DESKTOP_ROOT / "报表输出" / "LATEST"
OUT_DIR = ROOT / "backtest_results" / "v6ab_historical_mainline_gap_review"
DEFAULT_ATTRIBUTION = ROOT / "backtest_results" / "v6ab_daily_evolution" / "latest_pit_vs_v2_attribution.json"


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"missing input: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def fmt_pct(value: float | None) -> str:
    if value is None or not np.isfinite(value):
        return "n/a"
    return f"{value:+.2%}"


def parse_theme_list(raw: str) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for part in str(raw or "").split(","):
        item = part.strip()
        if not item:
            continue
        if ":" in item:
            theme, proxy = item.split(":", 1)
        else:
            theme, proxy = item, ""
        out.append({"theme": theme.strip(), "proxy": proxy.strip()})
    return out


def themes(raw: str) -> set[str]:
    return {row["theme"] for row in parse_theme_list(raw)}


def period_label(raw_date: str) -> str:
    year = int(str(raw_date)[:4])
    if year == 2020:
        return "2020"
    if year == 2022:
        return "2022"
    if year >= 2024:
        return "2024_2026"
    return "pre_2024"


def summarize(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    grouped: dict[str, list[float]] = defaultdict(list)
    dates: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        values = row.get(key, [])
        if not isinstance(values, list):
            values = [values]
        for value in values:
            if not value:
                continue
            grouped[str(value)].append(float(row.get("guarded_minus_v2", 0.0) or 0.0))
            dates[str(value)].append(str(row.get("date", "")))
    out = []
    for name, deltas in grouped.items():
        out.append(
            {
                key: name,
                "count": len(deltas),
                "sum_delta": float(np.sum(deltas)),
                "avg_delta": float(np.mean(deltas)),
                "win_rate": float(np.mean([value > 0 for value in deltas])),
                "negative_months": int(np.sum([value < 0 for value in deltas])),
                "dates": dates[name],
            }
        )
    return sorted(out, key=lambda row: (row["sum_delta"], -row["count"]))


def classify_gap(row: dict[str, Any]) -> list[str]:
    labels: list[str] = []
    missed = set(row.get("missed_v2_themes", []))
    added = set(row.get("added_guarded_themes", []))
    boost = set(row.get("pit_boost_allowlist", []))
    if missed & {"technology", "liquidity_growth", "broad_beta"}:
        labels.append("missed_growth_beta_expression")
    if missed & {"precious_metals", "energy_resources", "utilities_power"}:
        labels.append("missed_defensive_or_commodity_expression")
    if boost & {"semis_ai", "ai_platform", "ai_optical", "ai_networking", "ai_infra", "ai_memory"}:
        labels.append("ai_boost_displaced_legacy_winner")
    if added & {"healthcare_biotech", "financials"}:
        labels.append("replacement_theme_underperformed")
    if float(row.get("guarded_turnover", 0.0) or 0.0) >= 1.0:
        labels.append("high_expression_turnover")
    if not labels:
        labels.append("generic_expression_gap")
    return labels


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    attribution = load_json(args.attribution_json)
    raw_rows = attribution.get("rows", [])
    rows: list[dict[str, Any]] = []
    for row in raw_rows:
        if not row.get("guarded_active"):
            continue
        delta = float(row.get("guarded_minus_v2", 0.0) or 0.0)
        v2_themes = themes(row.get("v2_selected", ""))
        guarded_themes = themes(row.get("guarded_selected", ""))
        item = {
            "date": row.get("date"),
            "period": period_label(str(row.get("date", ""))),
            "guarded_minus_v2": delta,
            "v2_next_ret": float(row.get("v2_next_ret", 0.0) or 0.0),
            "guarded_next_ret": float(row.get("guarded_next_ret", 0.0) or 0.0),
            "guarded_turnover": float(row.get("guarded_turnover", 0.0) or 0.0),
            "pit_boost_allowlist": list(row.get("pit_boost_allowlist", [])),
            "pit_override_allowlist": list(row.get("pit_override_allowlist", [])),
            "v2_selected": row.get("v2_selected", ""),
            "guarded_selected": row.get("guarded_selected", ""),
            "missed_v2_themes": sorted(v2_themes - guarded_themes),
            "added_guarded_themes": sorted(guarded_themes - v2_themes),
        }
        item["gap_labels"] = classify_gap(item)
        rows.append(item)

    negative_rows = [row for row in rows if float(row.get("guarded_minus_v2", 0.0)) < 0]
    positive_rows = [row for row in rows if float(row.get("guarded_minus_v2", 0.0)) > 0]
    by_period = []
    for period in ["2020", "2022", "2024_2026", "pre_2024"]:
        seg = [row for row in rows if row["period"] == period]
        if not seg:
            continue
        deltas = [float(row["guarded_minus_v2"]) for row in seg]
        by_period.append(
            {
                "period": period,
                "count": len(seg),
                "sum_delta": float(np.sum(deltas)),
                "avg_delta": float(np.mean(deltas)),
                "win_rate": float(np.mean([value > 0 for value in deltas])),
                "negative_months": int(np.sum([value < 0 for value in deltas])),
            }
        )

    label_counts = Counter(label for row in negative_rows for label in row.get("gap_labels", []))
    return {
        "asof": args.asof,
        "attribution_json": str(args.attribution_json),
        "active_months": len(rows),
        "negative_months": len(negative_rows),
        "positive_months": len(positive_rows),
        "sum_guarded_delta": float(np.sum([row["guarded_minus_v2"] for row in rows])) if rows else 0.0,
        "negative_sum_delta": float(np.sum([row["guarded_minus_v2"] for row in negative_rows])) if negative_rows else 0.0,
        "positive_sum_delta": float(np.sum([row["guarded_minus_v2"] for row in positive_rows])) if positive_rows else 0.0,
        "period_summary": by_period,
        "missed_v2_theme_summary": summarize(negative_rows, "missed_v2_themes"),
        "added_guarded_theme_summary": summarize(negative_rows, "added_guarded_themes"),
        "pit_boost_theme_summary": summarize(negative_rows, "pit_boost_allowlist"),
        "gap_label_summary": [
            {"label": label, "count": count}
            for label, count in label_counts.most_common()
        ],
        "worst_months": sorted(negative_rows, key=lambda row: row["guarded_minus_v2"])[:15],
        "best_months": sorted(positive_rows, key=lambda row: row["guarded_minus_v2"], reverse=True)[:10],
        "rows": rows,
        "interpretation": [
            "这是诊断层：用 PIT guarded vs V2 的月度差异定位 historical mainline / expression gap，不作为交易规则。",
            "若负贡献集中在 missed_v2_themes，下一步应补该主题当时可见的 date-stamped evidence 或改进主题映射。",
            "若负贡献来自高 turnover/替代主题，优先审计表达层和 theme taxonomy，而不是放宽 OVERRIDE。",
        ],
    }


def render_md(payload: dict[str, Any]) -> str:
    lines = [
        "# V6AB Historical Mainline Gap Review",
        "",
        f"- 日期：`{payload['asof']}`",
        f"- active months：`{payload['active_months']}`",
        f"- negative months：`{payload['negative_months']}`",
        f"- guarded sum delta：`{fmt_pct(payload['sum_guarded_delta'])}`",
        f"- negative sum delta：`{fmt_pct(payload['negative_sum_delta'])}`",
        "- 模拟盘动作：`NO_CHANGE`。",
        "",
        "## Period Summary",
        "",
        "| period | count | sum delta | avg | win rate | negative |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in payload["period_summary"]:
        lines.append(
            f"| `{row['period']}` | {row['count']} | {fmt_pct(row['sum_delta'])} | "
            f"{fmt_pct(row['avg_delta'])} | {fmt_pct(row['win_rate'])} | {row['negative_months']} |"
        )
    lines += [
        "",
        "## Missed V2 Themes In Negative Months",
        "",
        "| missed theme | count | sum delta | avg | win rate |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for row in payload["missed_v2_theme_summary"][:10]:
        lines.append(
            f"| `{row['missed_v2_themes']}` | {row['count']} | {fmt_pct(row['sum_delta'])} | "
            f"{fmt_pct(row['avg_delta'])} | {fmt_pct(row['win_rate'])} |"
        )
    lines += [
        "",
        "## Added Guarded Themes In Negative Months",
        "",
        "| added theme | count | sum delta | avg | win rate |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for row in payload["added_guarded_theme_summary"][:10]:
        lines.append(
            f"| `{row['added_guarded_themes']}` | {row['count']} | {fmt_pct(row['sum_delta'])} | "
            f"{fmt_pct(row['avg_delta'])} | {fmt_pct(row['win_rate'])} |"
        )
    lines += [
        "",
        "## Gap Labels",
        "",
        "| label | count |",
        "| --- | ---: |",
    ]
    for row in payload["gap_label_summary"]:
        lines.append(f"| `{row['label']}` | {row['count']} |")
    lines += [
        "",
        "## Worst Months",
        "",
        "| date | delta | missed V2 | added guarded | boost | labels |",
        "| --- | ---: | --- | --- | --- | --- |",
    ]
    for row in payload["worst_months"][:10]:
        lines.append(
            f"| `{row['date']}` | {fmt_pct(row['guarded_minus_v2'])} | "
            f"`{', '.join(row['missed_v2_themes'])}` | `{', '.join(row['added_guarded_themes'])}` | "
            f"`{', '.join(row['pit_boost_allowlist'])}` | `{', '.join(row['gap_labels'])}` |"
        )
    lines += ["", "## Interpretation", ""]
    lines.extend(f"- {item}" for item in payload.get("interpretation", []))
    return "\n".join(lines)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "date",
        "period",
        "guarded_minus_v2",
        "v2_next_ret",
        "guarded_next_ret",
        "guarded_turnover",
        "pit_boost_allowlist",
        "v2_selected",
        "guarded_selected",
        "missed_v2_themes",
        "added_guarded_themes",
        "gap_labels",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    field: ", ".join(row.get(field, [])) if isinstance(row.get(field), list) else row.get(field, "")
                    for field in fields
                }
            )


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnose historical mainline gaps between V2 and PIT guarded.")
    parser.add_argument("--asof", default=str(date.today()))
    parser.add_argument("--attribution-json", type=Path, default=DEFAULT_ATTRIBUTION)
    parser.add_argument("--output-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    payload = build_payload(args)
    md = render_md(payload)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "latest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.output_dir / "latest.md").write_text(md, encoding="utf-8")
    write_csv(args.output_dir / "latest.csv", payload["rows"])
    (REPORT_ROOT / "V6AB_Historical_Mainline_Gap_Review_LATEST.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (REPORT_ROOT / "V6AB_Historical_Mainline_Gap_Review_LATEST.md").write_text(md, encoding="utf-8")
    write_csv(REPORT_ROOT / "V6AB_Historical_Mainline_Gap_Review_LATEST.csv", payload["rows"])
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
