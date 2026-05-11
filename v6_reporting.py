#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import html
import importlib
import json
import os
import smtplib
import sys
from datetime import date, datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
DEFAULT_POLICY = ROOT / "v6_strategy_lab" / "configs" / "v6_reporting_policy_v1.json"
DEFAULT_OUTPUT_DIR = ROOT / "backtest_results" / "v6_reporting"


def now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def today_text() -> str:
    return date.today().isoformat()


def read_json(path: Path) -> Any:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def read_text(path: Path, limit: int = 6000) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    return text[:limit]


def read_csv_rows(path: Path, limit: int = 20) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))[:limit]


def resolve_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def latest_file(directory: Path, pattern: str) -> Path | None:
    if not directory.exists():
        return None
    files = sorted(directory.glob(pattern), key=lambda item: item.stat().st_mtime)
    return files[-1] if files else None


def rel(path: Path | None) -> str:
    if path is None:
        return ""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def period_range(period: str) -> str:
    today = date.today()
    if period == "weekly":
        return f"{today - timedelta(days=6)} ~ {today}"
    if period == "monthly":
        return f"{today.replace(day=1)} ~ {today}"
    if period == "quarterly":
        quarter_month = ((today.month - 1) // 3) * 3 + 1
        return f"{today.replace(month=quarter_month, day=1)} ~ {today}"
    return today.isoformat()


def summarize_release_gate(path: Path) -> dict[str, Any]:
    payload = read_json(path)
    if not payload:
        return {"exists": False, "path": rel(path)}
    gate_result = str(payload.get("gate_result", "")).upper()
    failed_blockers = payload.get("failed_blockers", [])
    overall_passed = bool(payload.get("overall_passed", False)) or gate_result == "PASS"
    return {
        "exists": True,
        "path": rel(path),
        "overall_passed": overall_passed,
        "operational_passed": bool(payload.get("operational_passed", overall_passed)),
        "activation_passed": bool(payload.get("activation_passed", overall_passed)),
        "gate_result": gate_result or ("PASS" if overall_passed else "FAIL"),
        "generated_at": str(payload.get("generated_at", "")),
        "candidate_id": str(payload.get("candidate_id", "")),
        "blockers": payload.get("blockers", []) or payload.get("pre_live_blockers", []) or failed_blockers,
        "summary": payload.get("summary", {}),
    }


def summarize_preview(report_path: Path, orders_path: Path) -> dict[str, Any]:
    orders = read_csv_rows(orders_path, limit=50)
    buy_notional = 0.0
    symbols: list[str] = []
    for row in orders:
        symbol = row.get("symbol") or row.get("code") or row.get("ticker") or ""
        if symbol:
            symbols.append(symbol)
        side = str(row.get("side") or row.get("action") or "").upper()
        qty = as_float(row.get("qty") or row.get("quantity") or row.get("preview_qty") or row.get("target_qty"))
        price = as_float(row.get("limit_price") or row.get("price") or row.get("estimated_price") or row.get("order_price"))
        notional = as_float(row.get("estimated_notional_usd") or row.get("notional_usd") or row.get("preview_order_value") or row.get("target_value"))
        if notional <= 0 and qty > 0 and price > 0:
            notional = qty * price
        if "BUY" in side or side in {"", "LONG"}:
            buy_notional += max(notional, 0.0)
    return {
        "report_path": rel(report_path),
        "orders_path": rel(orders_path),
        "report_exists": report_path.exists(),
        "orders_exists": orders_path.exists(),
        "order_count": len(orders),
        "symbols": symbols,
        "estimated_buy_notional_usd": round(buy_notional, 2),
        "report_excerpt": read_text(report_path, limit=1800),
    }


def summarize_real_pilot(path: Path) -> dict[str, Any]:
    payload = read_json(path)
    if not payload:
        return {"exists": False, "path": rel(path)}
    results = payload.get("execution_results", [])
    return {
        "exists": True,
        "path": rel(path),
        "generated_at": str(payload.get("generated_at", "")),
        "status": str(payload.get("status", "") or payload.get("cycle", {}).get("cycle_status", "")),
        "armed": bool(payload.get("cycle", {}).get("armed", False)),
        "order_rows": len(results) if isinstance(results, list) else 0,
        "note": "plan_only_or_latest_executor_payload",
    }


def summarize_v6b(scorecard_path: Path, live_forward_path: Path) -> dict[str, Any]:
    scorecard = read_json(scorecard_path)
    live_forward = read_json(live_forward_path)
    scorecard_dict = scorecard if isinstance(scorecard, dict) else {}
    live_forward_dict = live_forward if isinstance(live_forward, dict) else {}
    candidates = scorecard_dict.get("candidates", []) or scorecard_dict.get("rows", [])
    top: list[dict[str, Any]] = []
    if isinstance(candidates, list):
        sorted_rows = sorted(candidates, key=lambda item: as_float(item.get("total_score") or item.get("score")), reverse=True)
        for row in sorted_rows[:8]:
            top.append(
                {
                    "ticker": str(row.get("ticker") or row.get("symbol") or ""),
                    "score": row.get("total_score") or row.get("score") or "",
                    "status": row.get("status") or row.get("eligibility") or "",
                    "theme": row.get("theme") or row.get("theme_chain") or "",
                }
            )
    return {
        "scorecard_path": rel(scorecard_path),
        "scorecard_exists": bool(scorecard),
        "live_forward_path": rel(live_forward_path),
        "live_forward_exists": bool(live_forward),
        "top_candidates": top,
        "live_forward_status": str(live_forward_dict.get("status", "list_payload" if isinstance(live_forward, list) else "")),
        "live_forward_mode": str(live_forward_dict.get("mode", "")),
        "live_forward_rows": len(live_forward) if isinstance(live_forward, list) else 0,
        "live_forward_note": "V6-B remains SIM/research only until point-in-time/OOS/replay evidence passes.",
    }


def run_allocator(policy_path: Path, metrics_path: Path) -> dict[str, Any]:
    try:
        from v6_allocator import allocate, load_metrics

        policy = read_json(policy_path)
        metrics = load_metrics(metrics_path)
        result = allocate(policy, metrics)
        return {"exists": True, "path": rel(metrics_path), **result}
    except Exception as exc:
        return {"exists": metrics_path.exists(), "path": rel(metrics_path), "allocation_case": "unavailable", "weights": {}, "notes": [str(exc)]}


def decide_action(payload: dict[str, Any]) -> str:
    gate = payload["v6a"]["release_gate"]
    real = payload["v6a"]["real_pilot"]
    allocator = payload["allocator"]
    if real.get("armed"):
        return "需要用户确认：检测到 armed 执行记录，复核订单和仓位。"
    if not gate.get("exists"):
        return "禁止实盘：缺少 V6-A release gate。"
    if not gate.get("overall_passed"):
        return "禁止实盘：V6-A release gate 未通过。"
    if allocator.get("weights", {}).get("V6-B", 0) not in {0, 0.0, "0", "0.0"}:
        return "需要用户确认：allocator 给 V6-B 非零权重，必须人工复核。"
    return "需要用户确认：V6-A 可继续小额 pilot 流程；V6-B 仅研究/模拟。"


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    policy = read_json(resolve_path(args.policy))
    launch_policy_path = resolve_path(policy["artifacts"]["v6_live_launch_policy"])
    launch_policy = read_json(launch_policy_path)
    evidence = launch_policy.get("latest_real_pilot_evidence", {})

    release_gate_path = resolve_path(evidence.get("release_gate") or policy["artifacts"]["release_gate"])
    preview_report_path = resolve_path(evidence.get("live_preview_report") or policy["artifacts"]["live_preview_report"])
    preview_orders_path = resolve_path(evidence.get("live_preview_orders") or policy["artifacts"]["live_preview_orders"])

    real_pilot_dir = resolve_path(policy["artifacts"]["real_pilot_dir"])
    real_pilot_latest = latest_file(real_pilot_dir, "v6a_real_pilot_results_*.json")

    scorecard_path = resolve_path(policy["artifacts"]["v6b_scorecard"])
    live_forward_path = resolve_path(policy["artifacts"]["v6b_live_forward_results"])
    allocator_metrics_path = resolve_path(policy["artifacts"]["allocator_metrics"])
    allocator_policy_path = resolve_path(policy["artifacts"]["allocator_policy"])

    payload: dict[str, Any] = {
        "generated_at": now_text(),
        "report_date": today_text(),
        "period": args.period,
        "period_range": period_range(args.period),
        "title": f"V6 Strategy {args.period.title()} Report",
        "email_subject": f"[V6 Strategy] {args.period.title()} Report - {period_range(args.period)}",
        "policy_path": rel(resolve_path(args.policy)),
        "v6a": {
            "status": launch_policy.get("status", ""),
            "strategy_name": launch_policy.get("strategy_name", ""),
            "capital_policy": launch_policy.get("capital_policy", {}),
            "execution_policy": launch_policy.get("execution_policy", {}),
            "latest_real_pilot_evidence": evidence,
            "release_gate": summarize_release_gate(release_gate_path),
            "preview": summarize_preview(preview_report_path, preview_orders_path),
            "real_pilot": summarize_real_pilot(real_pilot_latest) if real_pilot_latest else {"exists": False, "path": ""},
        },
        "v6b": summarize_v6b(scorecard_path, live_forward_path),
        "allocator": run_allocator(allocator_policy_path, allocator_metrics_path),
        "reminders": policy.get("reminders", {}),
        "boundaries": policy.get("boundaries", []),
    }
    payload["weekly_action"] = decide_action(payload)
    return payload


def md_table(headers: list[str], rows: list[list[Any]]) -> str:
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        out.append("| " + " | ".join(str(item) for item in row) + " |")
    return "\n".join(out)


def render_markdown(payload: dict[str, Any]) -> str:
    v6a = payload["v6a"]
    gate = v6a["release_gate"]
    preview = v6a["preview"]
    allocator = payload["allocator"]
    v6b = payload["v6b"]

    top_rows = [
        [row.get("ticker", ""), row.get("score", ""), row.get("status", ""), row.get("theme", "")]
        for row in v6b.get("top_candidates", [])
    ]
    if not top_rows:
        top_rows = [["-", "-", "-", "-"]]

    return "\n".join(
        [
            f"# {payload['title']}",
            "",
            f"- Generated: `{payload['generated_at']}`",
            f"- Period: `{payload['period_range']}`",
            f"- 本周动作：{payload['weekly_action']}",
            "",
            "## V6-A 状态",
            "",
            md_table(
                ["项目", "状态"],
                [
                    ["策略", v6a.get("strategy_name", "")],
                    ["Launch Status", v6a.get("status", "")],
                    ["Release Gate", "PASS" if gate.get("overall_passed") else "FAIL/MISSING"],
                    ["Gate Path", gate.get("path", "")],
                    ["Preview Orders", preview.get("order_count", 0)],
                    ["Preview Buy Notional", f"${preview.get('estimated_buy_notional_usd', 0):,.2f}"],
                    ["Preview Symbols", ", ".join(preview.get("symbols", []))],
                    ["Real Pilot Record", v6a.get("real_pilot", {}).get("status", "not_executed")],
                ],
            ),
            "",
            "## V6-B / Dynamic Universe",
            "",
            f"- Status: `research_or_sim_only`",
            f"- Scorecard: `{v6b.get('scorecard_path', '')}`",
            f"- Live-forward: `{v6b.get('live_forward_path', '')}`",
            f"- Note: {v6b.get('live_forward_note', '')}",
            "",
            md_table(["Ticker", "Score", "Status", "Theme"], top_rows),
            "",
            "## Allocator",
            "",
            md_table(
                ["项目", "值"],
                [
                    ["Case", allocator.get("allocation_case", "")],
                    ["Weights", json.dumps(allocator.get("weights", {}), ensure_ascii=False)],
                    ["Notes", "; ".join(str(item) for item in allocator.get("notes", []))],
                ],
            ),
            "",
            "## 边界",
            "",
            "\n".join(f"- {item}" for item in payload.get("boundaries", [])),
            "",
        ]
    )


def render_html(payload: dict[str, Any], markdown: str) -> str:
    escaped = html.escape(markdown)
    action = html.escape(payload.get("weekly_action", ""))
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(payload['title'])}</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 0; background: #f8fafc; color: #111827; }}
main {{ max-width: 980px; margin: 32px auto; padding: 0 20px 48px; }}
.hero {{ background: #0f172a; color: #fff; padding: 24px; border-radius: 18px; }}
.action {{ margin-top: 14px; display: inline-block; background: #f59e0b; color: #111827; padding: 8px 12px; border-radius: 999px; font-weight: 700; }}
pre {{ white-space: pre-wrap; word-break: break-word; background: #fff; border: 1px solid #e5e7eb; border-radius: 14px; padding: 18px; line-height: 1.55; }}
</style>
</head>
<body>
<main>
  <section class="hero">
    <h1>{html.escape(payload['title'])}</h1>
    <div>Generated: {html.escape(payload['generated_at'])}</div>
    <div class="action">本周动作：{action}</div>
  </section>
  <pre>{escaped}</pre>
</main>
</body>
</html>
"""


def send_email_via_v3_notifier(payload: dict[str, Any], html_content: str) -> dict[str, Any]:
    try:
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        env_utils = importlib.import_module("env_utils")
        env_utils.load_local_env()
        notifier_module = importlib.import_module("notifier")
        notifier = notifier_module.EmailNotifier()
        sent = bool(notifier.send(payload["email_subject"], html_content, is_html=True))
        return {
            "attempted": True,
            "sent": sent,
            "provider": "v3_notifier",
            "enabled": bool(getattr(notifier, "enabled", False)),
            "sender": str(getattr(notifier, "sender", "")),
            "recipient": str(getattr(notifier, "recipient", "")),
            "error": "",
        }
    except Exception as exc:
        return {
            "attempted": True,
            "sent": False,
            "provider": "v3_notifier",
            "enabled": False,
            "sender": "",
            "recipient": "",
            "error": str(exc),
        }


def send_email_via_v6_env(payload: dict[str, Any], html_content: str) -> dict[str, Any]:
    required = {
        "smtp_server": os.environ.get("V6_EMAIL_SMTP_SERVER", ""),
        "smtp_port": os.environ.get("V6_EMAIL_SMTP_PORT", "465"),
        "sender": os.environ.get("V6_EMAIL_SENDER", ""),
        "password": os.environ.get("V6_EMAIL_PASSWORD", ""),
        "recipient": os.environ.get("V6_EMAIL_RECIPIENT", ""),
    }
    missing = [key for key, value in required.items() if not str(value).strip()]
    if missing:
        return {
            "attempted": True,
            "sent": False,
            "provider": "v6_env",
            "enabled": False,
            "sender": str(required.get("sender", "")),
            "recipient": str(required.get("recipient", "")),
            "error": f"missing_env:{','.join(missing)}",
        }
    msg = MIMEMultipart("alternative")
    msg["Subject"] = payload["email_subject"]
    msg["From"] = required["sender"]
    msg["To"] = required["recipient"]
    msg.attach(MIMEText(html_content, "html", "utf-8"))
    try:
        with smtplib.SMTP_SSL(required["smtp_server"], int(required["smtp_port"])) as server:
            server.login(required["sender"], required["password"])
            server.sendmail(required["sender"], [required["recipient"]], msg.as_string())
        return {
            "attempted": True,
            "sent": True,
            "provider": "v6_env",
            "enabled": True,
            "sender": str(required["sender"]),
            "recipient": str(required["recipient"]),
            "error": "",
        }
    except Exception as exc:
        return {
            "attempted": True,
            "sent": False,
            "provider": "v6_env",
            "enabled": True,
            "sender": str(required["sender"]),
            "recipient": str(required["recipient"]),
            "error": str(exc),
        }


def send_email(payload: dict[str, Any], html_content: str) -> dict[str, Any]:
    """Send V6 report email.

    V6 reuses the existing V3 notifier first so the same local `.ic_env.local`
    password setup works. Dedicated V6_EMAIL_* variables remain as fallback.
    """
    v3_result = send_email_via_v3_notifier(payload, html_content)
    if v3_result.get("sent"):
        return v3_result
    v6_result = send_email_via_v6_env(payload, html_content)
    if v6_result.get("sent"):
        v6_result["fallback_from"] = v3_result
        return v6_result
    return {
        "attempted": True,
        "sent": False,
        "provider": "v3_notifier_then_v6_env",
        "enabled": bool(v3_result.get("enabled")) or bool(v6_result.get("enabled")),
        "sender": str(v3_result.get("sender") or v6_result.get("sender", "")),
        "recipient": str(v3_result.get("recipient") or v6_result.get("recipient", "")),
        "error": f"v3={v3_result.get('error') or 'not_sent'}; v6={v6_result.get('error') or 'not_sent'}",
        "attempts": [v3_result, v6_result],
    }


def write_outputs(payload: dict[str, Any], markdown: str, html_content: str, output_dir: Path, tag: str) -> dict[str, str]:
    runs_dir = output_dir / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    base = f"v6_report_{payload['period']}_{tag}"
    json_path = runs_dir / f"{base}.json"
    md_path = runs_dir / f"{base}.md"
    html_path = runs_dir / f"{base}.html"
    latest_json = output_dir / f"latest_{payload['period']}.json"
    latest_md = output_dir / f"latest_{payload['period']}.md"
    latest_html = output_dir / f"latest_{payload['period']}.html"
    for path, content in [
        (json_path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n"),
        (md_path, markdown),
        (html_path, html_content),
        (latest_json, json.dumps(payload, ensure_ascii=False, indent=2) + "\n"),
        (latest_md, markdown),
        (latest_html, html_content),
    ]:
        path.write_text(content, encoding="utf-8")
    return {
        "run_json": rel(json_path),
        "run_md": rel(md_path),
        "run_html": rel(html_path),
        "latest_json": rel(latest_json),
        "latest_md": rel(latest_md),
        "latest_html": rel(latest_html),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate read-only V6 strategy status report.")
    parser.add_argument("--period", choices=["daily", "weekly", "monthly", "quarterly"], default="weekly")
    parser.add_argument("--policy", default=str(DEFAULT_POLICY))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--tag", default=datetime.now().strftime("%Y%m%dT%H%M%S"))
    parser.add_argument("--send-email", action="store_true", help="Opt-in email sending. Never triggers trading.")
    parser.add_argument("--fail-on-email-error", action="store_true")
    args = parser.parse_args()

    payload = build_payload(args)
    markdown = render_markdown(payload)
    html_content = render_html(payload, markdown)
    email_result = {"attempted": False, "sent": False, "error": ""}
    if args.send_email:
        email_result = send_email(payload, html_content)
        if args.fail_on_email_error and not email_result.get("sent", False):
            raise SystemExit(f"email_failed:{email_result.get('error')}")
    payload["email"] = email_result
    outputs = write_outputs(payload, markdown, html_content, resolve_path(args.output_dir), args.tag)
    print(json.dumps({"outputs": outputs, "email": email_result, "weekly_action": payload["weekly_action"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
