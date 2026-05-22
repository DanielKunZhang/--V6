#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
DESKTOP_ROOT = Path("/Users/zhangkun/Desktop/AI个人投资公司")
REPORT_ROOT = DESKTOP_ROOT / "报表输出" / "LATEST"
OUT_DIR = ROOT / "backtest_results" / "v6ab_macro_regime_evidence"


def expiry(source_date: str, days: int) -> str:
    return str(date.fromisoformat(source_date) + timedelta(days=days))


def row(
    *,
    source_date: str,
    theme: str,
    ticker: str,
    evidence_type: str,
    confidence: float,
    direction: str,
    weight: float,
    summary: str,
    source_path: str,
    expiry_days: int = 270,
) -> dict[str, Any]:
    return {
        "asof": source_date,
        "theme": theme,
        "ticker": ticker,
        "source": "macro_regime_seed",
        "source_path": source_path,
        "source_date": source_date,
        "evidence_type": evidence_type,
        "confidence": confidence,
        "direction": direction,
        "freshness": 1.0,
        "expiry_date": expiry(source_date, expiry_days),
        "summary": summary,
        "weight": weight,
    }


def build_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    # 2020 liquidity shock response: broad policy support, zero-rate/QE regime,
    # fiscal stimulus and stay-at-home technology demand. These are public,
    # date-stamped regime facts, not hindsight performance labels.
    rows.extend(
        [
            row(
                source_date="2020-03-15",
                theme="liquidity_growth",
                ticker="US.QQQ",
                evidence_type="macro_policy_liquidity",
                confidence=0.78,
                direction="positive",
                weight=0.72,
                summary="Federal Reserve emergency policy response cut rates to near zero and restarted broad asset purchases; regime signal for liquidity-supported growth assets.",
                source_path="https://www.federalreserve.gov/newsevents/pressreleases/monetary20200315a.htm",
                expiry_days=360,
            ),
            row(
                source_date="2020-03-23",
                theme="liquidity_growth",
                ticker="US.QQQ",
                evidence_type="macro_policy_liquidity",
                confidence=0.80,
                direction="positive",
                weight=0.74,
                summary="Federal Reserve announced extensive measures to support market functioning and credit flow; confirms liquidity backstop regime.",
                source_path="https://www.federalreserve.gov/newsevents/pressreleases/monetary20200323b.htm",
                expiry_days=360,
            ),
            row(
                source_date="2020-03-27",
                theme="liquidity_growth",
                ticker="US.IWM",
                evidence_type="fiscal_stimulus",
                confidence=0.74,
                direction="positive",
                weight=0.68,
                summary="CARES Act signed into law; large fiscal support reinforced risk-asset/liquidity-growth regime after COVID shock.",
                source_path="https://www.congress.gov/bill/116th-congress/house-bill/748",
                expiry_days=300,
            ),
            row(
                source_date="2020-04-30",
                theme="technology",
                ticker="US.AMZN",
                evidence_type="earnings_regime_fact",
                confidence=0.72,
                direction="positive",
                weight=0.68,
                summary="Large-cap internet/cloud businesses reported COVID-period demand resilience; evidence for technology/software leadership rather than only narrow AI.",
                source_path="https://www.sec.gov/Archives/edgar/data/1018724/000101872420000008/amzn-20200331x8k.htm",
                expiry_days=240,
            ),
            row(
                source_date="2020-07-30",
                theme="technology",
                ticker="US.AAPL",
                evidence_type="earnings_regime_fact",
                confidence=0.70,
                direction="positive",
                weight=0.66,
                summary="Mega-cap technology earnings confirmed strong digital/device/software demand in 2020 recovery phase.",
                source_path="https://www.apple.com/newsroom/2020/07/apple-reports-third-quarter-results/",
                expiry_days=240,
            ),
            row(
                source_date="2020-03-15",
                theme="precious_metals",
                ticker="US.GLD",
                evidence_type="macro_real_rate_liquidity",
                confidence=0.70,
                direction="positive",
                weight=0.64,
                summary="Zero-rate/QE regime lowered real-rate pressure and supported precious metals as liquidity/hedge expression.",
                source_path="https://www.federalreserve.gov/newsevents/pressreleases/monetary20200315a.htm",
                expiry_days=330,
            ),
            row(
                source_date="2020-08-27",
                theme="liquidity_growth",
                ticker="US.ARKK",
                evidence_type="macro_policy_liquidity",
                confidence=0.70,
                direction="positive",
                weight=0.62,
                summary="Federal Reserve adopted flexible average inflation targeting, reinforcing longer-for-lower policy interpretation for growth/liquidity regime.",
                source_path="https://www.federalreserve.gov/newsevents/pressreleases/monetary20200827a.htm",
                expiry_days=300,
            ),
        ]
    )

    # 2022 inflation/rate shock: keep this symmetric so the ledger is not just
    # a 2020 bullish-growth patch.
    rows.extend(
        [
            row(
                source_date="2022-02-24",
                theme="energy_resources",
                ticker="US.XLE",
                evidence_type="geopolitical_supply_shock",
                confidence=0.76,
                direction="positive",
                weight=0.70,
                summary="Russia-Ukraine invasion created energy supply shock; evidence for energy/resources inflation leadership regime.",
                source_path="https://www.whitehouse.gov/briefing-room/statements-releases/2022/02/24/fact-sheet-joined-by-allies-and-partners-the-united-states-imposes-devastating-costs-on-russia/",
                expiry_days=360,
            ),
            row(
                source_date="2022-03-16",
                theme="liquidity_growth",
                ticker="US.ARKK",
                evidence_type="macro_policy_tightening",
                confidence=0.78,
                direction="negative",
                weight=0.72,
                summary="Federal Reserve began rate-hiking cycle; negative evidence for liquidity-growth regime.",
                source_path="https://www.federalreserve.gov/newsevents/pressreleases/monetary20220316a.htm",
                expiry_days=360,
            ),
            row(
                source_date="2022-03-16",
                theme="technology",
                ticker="US.XLK",
                evidence_type="macro_policy_tightening",
                confidence=0.66,
                direction="mixed",
                weight=0.60,
                summary="Rate-hiking cycle pressured long-duration technology valuations; technology leadership required stronger market confirmation.",
                source_path="https://www.federalreserve.gov/newsevents/pressreleases/monetary20220316a.htm",
                expiry_days=270,
            ),
        ]
    )

    # 2023 broad technology/AI transition: keep broad technology evidence alive
    # so narrower AI subthemes must compete with parent technology leadership.
    rows.extend(
        [
            row(
                source_date="2023-01-25",
                theme="technology",
                ticker="US.MSFT",
                evidence_type="cloud_ai_platform_update",
                confidence=0.70,
                direction="positive",
                weight=0.64,
                summary="Microsoft/OpenAI and cloud platform updates marked broad technology platform re-acceleration, not only narrow semiconductor exposure.",
                source_path="https://blogs.microsoft.com/blog/2023/01/23/microsoftandopenaiextendpartnership/",
                expiry_days=300,
            ),
            row(
                source_date="2023-03-22",
                theme="liquidity_growth",
                ticker="US.QQQ",
                evidence_type="financial_stability_liquidity",
                confidence=0.60,
                direction="mixed",
                weight=0.54,
                summary="Bank-stress liquidity support improved market functioning but occurred alongside rate pressure; mixed evidence for liquidity-growth regime.",
                source_path="https://www.federalreserve.gov/newsevents/pressreleases/monetary20230322a.htm",
                expiry_days=180,
            ),
            row(
                source_date="2023-05-24",
                theme="technology",
                ticker="US.QQQ",
                evidence_type="ai_platform_market_regime",
                confidence=0.74,
                direction="positive",
                weight=0.66,
                summary="AI platform/computing cycle became a broad technology leadership regime; child AI themes should compete against parent technology leadership.",
                source_path="https://investor.nvidia.com/news/press-release-details/2023/NVIDIA-Announces-Financial-Results-for-First-Quarter-Fiscal-2024/default.aspx",
                expiry_days=360,
            ),
        ]
    )
    return rows


def render_md(payload: dict[str, Any]) -> str:
    by_theme: dict[str, int] = {}
    for row in payload["rows"]:
        by_theme[row["theme"]] = by_theme.get(row["theme"], 0) + 1
    lines = [
        "# V6AB Macro Regime Evidence Seed",
        "",
        f"- 日期：`{payload['asof']}`",
        f"- rows：`{payload['row_count']}`",
        "- 边界：只记录 date-stamped macro/regime facts；不使用事后收益标签，不直接改交易规则。",
        "",
        "## Theme Counts",
        "",
    ]
    for theme, count in sorted(by_theme.items(), key=lambda item: item[0]):
        lines.append(f"- `{theme}`：{count}")
    lines += [
        "",
        "## Rows",
        "",
        "| date | theme | ticker | type | direction | summary |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in payload["rows"]:
        lines.append(
            f"| {row['source_date']} | `{row['theme']}` | `{row['ticker']}` | {row['evidence_type']} | "
            f"{row['direction']} | {row['summary']} |"
        )
    return "\n".join(lines)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "asof",
        "theme",
        "ticker",
        "source",
        "source_path",
        "source_date",
        "evidence_type",
        "confidence",
        "direction",
        "freshness",
        "expiry_date",
        "summary",
        "weight",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate conservative macro/regime PIT evidence seeds for V6AB.")
    parser.add_argument("--asof", default=str(date.today()))
    parser.add_argument("--output-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    rows = build_rows()
    payload = {
        "asof": args.asof,
        "source_boundary": "manual_date_stamped_macro_regime_seed",
        "row_count": len(rows),
        "rows": rows,
    }
    md = render_md(payload)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    json_text = json.dumps(payload, ensure_ascii=False, indent=2)
    (args.output_dir / "latest.json").write_text(json_text, encoding="utf-8")
    (args.output_dir / "latest.md").write_text(md, encoding="utf-8")
    write_csv(args.output_dir / "latest.csv", rows)
    (REPORT_ROOT / "V6AB_Macro_Regime_Evidence_LATEST.json").write_text(json_text, encoding="utf-8")
    (REPORT_ROOT / "V6AB_Macro_Regime_Evidence_LATEST.md").write_text(md, encoding="utf-8")
    write_csv(REPORT_ROOT / "V6AB_Macro_Regime_Evidence_LATEST.csv", rows)
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
