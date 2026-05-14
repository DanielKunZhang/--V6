#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
DESKTOP_DIR = Path("/Users/zhangkun/Desktop/AI个人投资公司")
OUT_DIR = ROOT / "backtest_results" / "investment_company_dashboard"

SOURCES = {
    "central_risk": ROOT / "backtest_results" / "central_risk_board" / "latest.json",
    "performance": ROOT / "backtest_results" / "performance_attribution" / "latest.json",
    "overlay": ROOT / "backtest_results" / "overlay_trade_journal" / "latest.json",
    "monthly": ROOT / "backtest_results" / "monthly_research_review" / "latest.json",
    "v6_weekly": ROOT / "backtest_results" / "v6_weekly_review" / "latest.json",
    "v6_backlog": ROOT / "backtest_results" / "v6_research_backlog" / "latest.json",
}

DESKTOP_LINKS = {
    "central_risk": "中央风控看板_CENTRAL_RISK_BOARD_LATEST.html",
    "performance": "绩效归因看板_PERFORMANCE_ATTRIBUTION_LATEST.html",
    "overlay": "Radar_Overlay_Journal_LATEST.html",
    "monthly": "Monthly_Research_Review_LATEST.html",
    "v6a_cutover_card": "2026-05-26_V6A_balanced_cutover_执行检查卡_v1.md",
    "v6b_card": "6月1日_V6B_执行卡.md",
    "v6b_preflight": "2026-06-01_V6B_执行预检报告.md",
    "overview": "投资系统全景图_SYSTEM_OVERVIEW.html",
    "plan": "26年阶段性组合策略计划.html",
}


def read_json(path: Path) -> Any:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def fmt_usd(value: float | int | None) -> str:
    if value is None:
        return "—"
    if abs(float(value)) < 100:
        return f"${float(value):,.2f}"
    return f"${float(value):,.0f}"


def fmt_pct(value: float | int | None) -> str:
    if value is None:
        return "—"
    return f"{float(value):.1f}%"


def first_line_from_md(path: Path) -> str:
    if not path.exists():
        return ""
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if text.startswith("- ") and not text.startswith("- Generated") and not text.startswith("- Month Tag"):
            return text[2:]
    return ""


def build_payload() -> dict[str, Any]:
    central = read_json(SOURCES["central_risk"])
    performance = read_json(SOURCES["performance"])
    overlay = read_json(SOURCES["overlay"])
    monthly = read_json(SOURCES["monthly"])
    v6_weekly = read_json(SOURCES["v6_weekly"])
    v6_backlog = read_json(SOURCES["v6_backlog"])

    coverage = performance.get("coverage", {}) if isinstance(performance.get("coverage"), dict) else {}
    overlay_stats = overlay.get("stats", {}) if isinstance(overlay.get("stats"), dict) else {}
    monthly_missing = monthly.get("missing_summary", {}) if isinstance(monthly.get("missing_summary"), dict) else {}
    monthly_registry = monthly.get("registry_summary", {}) if isinstance(monthly.get("registry_summary"), dict) else {}

    backlog_items = v6_backlog if isinstance(v6_backlog, list) else monthly.get("backlog_items", [])
    top_backlog = backlog_items[:5] if isinstance(backlog_items, list) else []

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "central_risk": {
            "status": central.get("status", "UNKNOWN"),
            "reasons": central.get("status_reasons", []),
            "max_position": (central.get("firm_snapshot", {}) or {}).get("max_position"),
            "top2_sum": (central.get("firm_snapshot", {}) or {}).get("top2_sum"),
            "top_theme": (central.get("themes", [{}]) or [{}])[0].get("current_pct") if central.get("themes") else None,
            "one_line": first_line_from_md(ROOT / "backtest_results" / "central_risk_board" / "latest.md"),
        },
        "performance": {
            "coverage": coverage.get("covered_ratio_pct"),
            "broker_pl": coverage.get("unrealized_pl_usd"),
            "broker_pl_pct": coverage.get("unrealized_pl_pct_broker_equity"),
            "one_line": first_line_from_md(ROOT / "backtest_results" / "performance_attribution" / "latest.md"),
        },
        "v6": {
            "decision": v6_weekly.get("decision") or monthly.get("weekly_review", {}).get("decision") or "UNKNOWN",
            "pilot_decision": v6_weekly.get("pilot_review_decision") or monthly.get("weekly_review", {}).get("pilot_review_decision") or "UNKNOWN",
            "managed_pl_pct": v6_weekly.get("managed_unrealized_pl_pct_points"),
            "top3_weight": v6_weekly.get("top3_weight"),
        },
        "radar": {
            "registry_count": monthly_registry.get("entry_count"),
            "coverage_gaps": monthly_missing.get("coverage_gap_count"),
            "critical_misses": monthly_missing.get("critical_miss_count"),
            "priority_watch": monthly_registry.get("top_watch", []),
        },
        "overlay": {
            "closed_samples": overlay_stats.get("closed_sample_count"),
            "live_or_watch": overlay_stats.get("live_or_watch_count"),
            "realized_pnl": overlay_stats.get("total_realized_pnl_usd"),
            "one_line": first_line_from_md(ROOT / "backtest_results" / "overlay_trade_journal" / "latest.md"),
        },
        "monthly": {
            "one_line": first_line_from_md(ROOT / "backtest_results" / "monthly_research_review" / "latest.md"),
        },
        "top_backlog": top_backlog,
    }


def action_groups(payload: dict[str, Any]) -> dict[str, list[str]]:
    groups = {"必须处理": [], "可观察": [], "禁止动作": []}
    risk = payload["central_risk"]
    if risk["status"] == "RED":
        groups["必须处理"].append("继续把腾讯 / PDD / 中国平台互联网集中度视为第一风险源；低位不加，等待合适窗口去超配。")
    v6 = payload["v6"]
    if "CONTINUE" in str(v6["pilot_decision"]) or "Investigate" in str(v6["decision"]):
        groups["可观察"].append("V6 继续收集 pilot / review 证据；5月26日前只看执行质量和 cutover 证据包。")
    radar = payload["radar"]
    if int(radar.get("coverage_gaps") or 0) > 0:
        groups["可观察"].append("Radar / V6-B 等 6月1日数据窗口，按执行卡补 universe、漏网机会和 scorecard。")
    overlay = payload["overlay"]
    if int(overlay.get("closed_samples") or 0) == 0:
        groups["禁止动作"].append("Overlay 还没有真实关闭样本，不能用 watch 项目推断策略有效，也不能扩大预算。")
    groups["禁止动作"].append("未触发明确确认短语前，不允许 V6 自动下真实订单或扩容。")
    if not groups["必须处理"] and not groups["可观察"]:
        groups["可观察"].append("当前没有需要改变系统状态的动作，继续按既定节奏运行。")
    return groups


LANE_LABELS = {
    "execution_quality": "执行质量",
    "v6a_parameter_challenger": "V6-A 参数 challenger",
    "v6b_core_reaccel": "V6-B 核心再加速",
    "v6b_turnaround": "V6-B 反转动量",
    "v6b_bottleneck": "V6-B 瓶颈链",
    "radar_missing_opportunity": "Radar 漏网复盘",
}

TEXT_TRANSLATIONS = {
    "Keep V6-A in manual pilot and collect more execution evidence": "V6-A 继续手动 pilot，补足执行质量证据",
    "Continue manual pilot and reuse the same review board at the next weekly checkpoint.": "继续手动 pilot，在下一个周度检查点复用同一套 review board。",
    "Build formal side-by-side board for the balanced V6-A challenger": "为 balanced V6-A challenger 建立正式对比板",
    "Prepare baseline vs balanced challenger review board and implementation/replay plan.": "准备 baseline vs balanced challenger 对比板，以及 implementation / replay 计划。",
    "Promote core_reaccel to formal V6-B challenger lane": "把 core_reaccel 提升为正式 V6-B challenger 轨道",
    "Keep core_reaccel ahead of other V6-B tracks and build the next validation board around it.": "让 core_reaccel 保持在其他 V6-B 轨道之前，并围绕它建立下一张验证板。",
    "Keep turnaround as secondary research only": "turnaround 只保留为二级研究方向",
    "Do not give allocator weight; only continue if new sparse-track evidence improves quality.": "不给 allocator 权重；只有 sparse-track 证据质量改善时才继续。",
    "Freeze bottleneck as a live promotion candidate": "bottleneck 暂停作为 live 晋级候选",
    "Do not spend allocator attention here until universe quality or exits materially improve.": "在 universe 质量或退出规则明显改善前，不消耗 allocator 注意力。",
    "Review new missing-opportunity names before the next Radar universe refresh": "在下一次 Radar universe 刷新前复核新的漏网标的",
    "Decide whether to upgrade these names/themes into point-in-time research seed or explicitly document why they remain excluded.": "决定是否把这些标的 / 主题升级为 point-in-time research seed，或明确记录为什么继续排除。",
}


def zh_text(value: Any) -> str:
    text = str(value or "")
    return TEXT_TRANSLATIONS.get(text, text)


def zh_lane(value: Any) -> str:
    text = str(value or "")
    return LANE_LABELS.get(text, text)


def build_html(payload: dict[str, Any]) -> str:
    risk = payload["central_risk"]
    performance = payload["performance"]
    v6 = payload["v6"]
    radar = payload["radar"]
    overlay = payload["overlay"]

    backlog_rows = []
    for item in payload["top_backlog"]:
        backlog_rows.append(
            "<tr>"
            f"<td>{html.escape(str(item.get('priority', '')))}</td>"
            f"<td>{html.escape(zh_lane(item.get('lane', '')))}</td>"
            f"<td>{html.escape(zh_text(item.get('title', '')))}</td>"
            f"<td>{html.escape(zh_text(item.get('next_step', '')))}</td>"
            "</tr>"
        )
    backlog_body = "".join(backlog_rows) or "<tr><td colspan='4'>暂无 backlog 数据</td></tr>"

    groups = action_groups(payload)
    action_columns = "".join(
        f"<div class='action-card'><h3>{html.escape(title)}</h3><ul>{''.join(f'<li>{html.escape(item)}</li>' for item in items) if items else '<li>暂无</li>'}</ul></div>"
        for title, items in groups.items()
    )
    priority_watch = ", ".join(str(item) for item in radar.get("priority_watch", [])[:8]) or "none"

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>AI个人投资公司 每日驾驶舱</title>
  <style>
    :root {{
      --bg: #f6f7f9;
      --panel: #ffffff;
      --ink: #111827;
      --muted: #667085;
      --line: #d9dee7;
      --red: #b42318;
      --orange: #b54708;
      --green: #027a48;
      --blue: #175cd3;
    }}
    body {{
      margin: 0;
      padding: 24px;
      background: var(--bg);
      color: var(--ink);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      line-height: 1.55;
    }}
    .wrap {{ max-width: 1180px; margin: 0 auto; }}
    header {{
      border-bottom: 1px solid var(--line);
      padding-bottom: 18px;
      margin-bottom: 18px;
    }}
    h1 {{ margin: 0 0 8px; font-size: 28px; letter-spacing: 0; }}
    h2 {{ margin: 24px 0 10px; font-size: 18px; letter-spacing: 0; }}
    .muted {{ color: var(--muted); font-size: 13px; }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: 12px;
    }}
    .card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
      min-height: 112px;
    }}
    .k {{ color: var(--muted); font-size: 12px; font-weight: 700; }}
    .v {{ margin-top: 6px; font-size: 22px; font-weight: 800; }}
    .small {{ margin-top: 8px; color: var(--muted); font-size: 12px; }}
    .red {{ color: var(--red); }}
    .orange {{ color: var(--orange); }}
    .green {{ color: var(--green); }}
    .blue {{ color: var(--blue); }}
    .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
      margin-top: 12px;
    }}
    ul {{ margin: 8px 0 0; padding-left: 20px; }}
    table {{
      width: 100%;
      border-collapse: collapse;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
    }}
    th, td {{
      padding: 10px 12px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
      font-size: 13px;
    }}
    th {{ background: #eef1f5; font-size: 12px; }}
    .links {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }}
    .links a {{
      color: var(--blue);
      border: 1px solid var(--line);
      background: #fff;
      border-radius: 999px;
      padding: 6px 10px;
      font-size: 12px;
      text-decoration: none;
      font-weight: 700;
    }}
    .action-grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
    }}
    .action-card {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      background: #fff;
    }}
    .action-card h3 {{
      margin: 0;
      font-size: 14px;
      letter-spacing: 0;
    }}
    @media (max-width: 980px) {{
      .grid {{ grid-template-columns: 1fr 1fr; }}
      .action-grid {{ grid-template-columns: 1fr; }}
      table {{ display: block; overflow-x: auto; }}
    }}
    @media (max-width: 620px) {{
      body {{ padding: 16px; }}
      .grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <header>
      <h1>AI个人投资公司 每日驾驶舱</h1>
      <div class="muted">生成时间：{html.escape(payload['generated_at'])} · 这是唯一日常入口；其他文档退到证据层。</div>
      <div class="links">
        <a href="{DESKTOP_LINKS['overview']}">系统全景图</a>
        <a href="{DESKTOP_LINKS['plan']}">26年计划</a>
        <a href="{DESKTOP_LINKS['central_risk']}">中央风控</a>
        <a href="{DESKTOP_LINKS['performance']}">绩效归因</a>
        <a href="{DESKTOP_LINKS['monthly']}">月度复盘</a>
        <a href="{DESKTOP_LINKS['overlay']}">Overlay</a>
        <a href="{DESKTOP_LINKS['v6a_cutover_card']}">5月26日 V6-A 执行卡</a>
        <a href="{DESKTOP_LINKS['v6b_card']}">6月1日执行卡</a>
        <a href="{DESKTOP_LINKS['v6b_preflight']}">V6-B 预检</a>
      </div>
    </header>

    <div class="grid">
      <div class="card"><div class="k">中央风控</div><div class="v red">{html.escape(str(risk['status']))}</div><div class="small">前二合计 {html.escape(fmt_pct(risk['top2_sum']))} · 最大单仓 {html.escape(fmt_pct(risk['max_position']))}</div></div>
      <div class="card"><div class="k">富途浮盈亏</div><div class="v blue">{html.escape(fmt_usd(performance['broker_pl']))}</div><div class="small">覆盖率 {html.escape(fmt_pct(performance['coverage']))} · 占富途 {html.escape(fmt_pct(performance['broker_pl_pct']))}</div></div>
      <div class="card"><div class="k">V6</div><div class="v orange">{html.escape(str(v6['decision']))}</div><div class="small">试运行结论 {html.escape(str(v6['pilot_decision']))}</div></div>
      <div class="card"><div class="k">Radar 供给链</div><div class="v">{html.escape(str(radar['registry_count'] or '—'))}</div><div class="small">覆盖缺口 {html.escape(str(radar['coverage_gaps'] or 0))} · 严重漏网 {html.escape(str(radar['critical_misses'] or 0))}</div></div>
      <div class="card"><div class="k">Overlay 样本</div><div class="v">{html.escape(str(overlay['closed_samples'] or 0))}</div><div class="small">观察中 {html.escape(str(overlay['live_or_watch'] or 0))} · 已实现 {html.escape(fmt_usd(overlay['realized_pnl']))}</div></div>
    </div>

    <section class="panel">
      <h2>今日动作区</h2>
      <div class="action-grid">{action_columns}</div>
    </section>

    <section class="panel">
      <h2>一行读数</h2>
      <ul>
        <li>{html.escape(str(risk['one_line'] or 'Central risk data unavailable'))}</li>
        <li>{html.escape(str(performance['one_line'] or 'Performance data unavailable'))}</li>
        <li>{html.escape(str(payload['monthly']['one_line'] or 'Monthly review data unavailable'))}</li>
        <li>{html.escape(str(overlay['one_line'] or 'Overlay data unavailable'))}</li>
      </ul>
    </section>

    <h2>最高优先级待办</h2>
    <table>
      <thead><tr><th>优先级</th><th>方向</th><th>事项</th><th>下一步</th></tr></thead>
      <tbody>{backlog_body}</tbody>
    </table>

    <section class="panel">
      <h2>Radar 重点观察名单</h2>
      <div>{html.escape(priority_watch)}</div>
    </section>
  </div>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate one-page AI investment company dashboard.")
    parser.add_argument("--tag", default=datetime.now().strftime("%Y%m%dT%H%M%S"))
    parser.add_argument("--sync-desktop", action="store_true")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = build_payload()
    html_content = build_html(payload)

    json_path = OUT_DIR / f"investment_company_dashboard_{args.tag}.json"
    html_path = OUT_DIR / f"investment_company_dashboard_{args.tag}.html"
    latest_json = OUT_DIR / "latest.json"
    latest_html = OUT_DIR / "latest.html"

    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    html_path.write_text(html_content, encoding="utf-8")
    latest_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    latest_html.write_text(html_content, encoding="utf-8")

    if args.sync_desktop:
        shutil.copy2(latest_html, DESKTOP_DIR / "AI个人投资公司_每日驾驶舱.html")
        shutil.copy2(latest_json, DESKTOP_DIR / "AI个人投资公司_每日驾驶舱.json")

    print("== AI Investment Company Dashboard ==")
    print(f"HTML: {html_path}")
    print(f"JSON: {json_path}")
    print(f"Sync desktop: {args.sync_desktop}")


if __name__ == "__main__":
    main()
