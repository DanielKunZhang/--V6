#!/usr/bin/env python3
"""
季报追踪系统 v1.0
- 每日检查：未来 N 天内是否有持仓标的财报发布
- 触发邮件预警，提示关注重点指标
- 每周一汇总：本周/下周财报日历

用法：
  python3 earnings_tracker.py              # 检查未来7天，有财报则发邮件
  python3 earnings_tracker.py --days 14   # 扩展到14天预警窗口
  python3 earnings_tracker.py --summary   # 强制输出未来30天完整日历（无论是否临近）
  python3 earnings_tracker.py --update    # 尝试用yfinance自动更新下次财报日期
  python3 earnings_tracker.py --no-email  # 不发邮件，仅控制台输出
"""

import json
import logging
import argparse
import smtplib
import time
import os
from datetime import datetime, date, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from env_utils import load_local_env

load_local_env()

SCRIPT_DIR = Path(__file__).parent
CALENDAR_PATH = SCRIPT_DIR / "earnings_calendar.json"
CONFIG_PATH   = SCRIPT_DIR / "config.json"
LOG_PATH      = SCRIPT_DIR / "screener.log"

try:
    import yfinance as yf
    YFINANCE_OK = True
except ImportError:
    YFINANCE_OK = False


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(LOG_PATH, encoding="utf-8"),
            logging.StreamHandler()
        ]
    )


# ─────────────────────────────────────────────
# EARNINGS DATE FETCHING
# ─────────────────────────────────────────────

def try_fetch_next_earnings(symbol: str) -> str | None:
    """Try to get next earnings date from yfinance. Returns YYYY-MM-DD or None."""
    if not YFINANCE_OK:
        return None
    try:
        time.sleep(2)
        ticker = yf.Ticker(symbol)
        cal = ticker.calendar
        if cal is None:
            return None
        # calendar can be a dict or DataFrame depending on yfinance version
        if hasattr(cal, "columns"):
            # DataFrame format
            if "Earnings Date" in cal.columns:
                val = cal["Earnings Date"].iloc[0]
                return str(val.date()) if hasattr(val, "date") else str(val)[:10]
        elif isinstance(cal, dict):
            ed = cal.get("Earnings Date") or cal.get("earningsDate")
            if ed:
                if isinstance(ed, list):
                    ed = ed[0]
                if hasattr(ed, "date"):
                    return str(ed.date())
                return str(ed)[:10]
    except Exception as e:
        logging.debug(f"  {symbol} yfinance calendar 失败: {e}")
    return None


# ─────────────────────────────────────────────
# CORE LOGIC
# ─────────────────────────────────────────────

def get_upcoming_earnings(calendar: dict, days_ahead: int = 7) -> list[dict]:
    """Return list of earnings events within the next `days_ahead` days."""
    today = date.today()
    cutoff = today + timedelta(days=days_ahead)
    upcoming = []

    for symbol, info in calendar["holdings"].items():
        next_e = info.get("next_earnings")
        if not next_e:
            continue
        try:
            earnings_date = date.fromisoformat(next_e)
        except ValueError:
            continue

        days_until = (earnings_date - today).days
        if 0 <= days_until <= days_ahead:
            upcoming.append({
                "symbol": symbol,
                "company": info.get("company", symbol),
                "exchange": info.get("exchange", ""),
                "earnings_date": next_e,
                "days_until": days_until,
                "timing": info.get("timing", "TBD"),
                "confirmed": info.get("next_earnings_confirmed", False),
                "key_metrics": info.get("key_metrics_to_watch", []),
                "ir_url": info.get("ir_url", ""),
                "last_summary": info.get("last_result_summary", ""),
                "options_note": info.get("options_note", "")
            })

    upcoming.sort(key=lambda x: x["earnings_date"])
    return upcoming


def get_full_calendar(calendar: dict) -> list[dict]:
    """Return all upcoming earnings sorted by date."""
    today = date.today()
    all_events = []
    for symbol, info in calendar["holdings"].items():
        next_e = info.get("next_earnings")
        if not next_e:
            continue
        try:
            earnings_date = date.fromisoformat(next_e)
        except ValueError:
            continue
        days_until = (earnings_date - today).days
        all_events.append({
            "symbol": symbol,
            "company": info.get("company", symbol),
            "exchange": info.get("exchange", ""),
            "earnings_date": next_e,
            "days_until": days_until,
            "timing": info.get("timing", "TBD"),
            "confirmed": info.get("next_earnings_confirmed", False),
            "key_metrics": info.get("key_metrics_to_watch", []),
            "options_note": info.get("options_note", "")
        })
    all_events.sort(key=lambda x: x["earnings_date"])
    return all_events


# ─────────────────────────────────────────────
# HTML REPORT
# ─────────────────────────────────────────────

def urgency_color(days: int) -> str:
    if days <= 2:  return "#c62828"
    if days <= 5:  return "#e65100"
    if days <= 10: return "#f9a825"
    return "#1565c0"


def generate_html(upcoming: list[dict], full_calendar: list[dict], run_date: str) -> str:
    today = date.today()

    # Upcoming alert rows
    alert_rows = ""
    for e in upcoming:
        days = e["days_until"]
        color = urgency_color(days)
        day_label = "今天 🔔" if days == 0 else ("明天 ⚠️" if days == 1 else f"{days}天后")
        confirmed = "✅ 已确认" if e["confirmed"] else "〜 预估"
        metrics = "".join(f'<li>{m}</li>' for m in e["key_metrics"])
        opt_note = f'<div style="background:#fff3e0;border-left:3px solid #e65100;padding:6px 10px;margin-top:8px;font-size:12px;border-radius:4px">⚠️ 期权注意：{e["options_note"]}</div>' if e.get("options_note") else ""
        alert_rows += f"""
        <div style="border:1px solid #e0e0e0;border-left:5px solid {color};border-radius:10px;
                    padding:16px 20px;margin-bottom:14px;background:white;">
          <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:8px">
            <div>
              <span style="font-size:18px;font-weight:700;color:{color}">{e['symbol']}</span>
              <span style="color:#546e7a;font-size:14px;margin-left:8px">{e['company']}</span>
              <span style="background:#e3f2fd;color:#1565c0;border-radius:10px;
                           padding:2px 8px;font-size:11px;margin-left:6px">{e['exchange']}</span>
            </div>
            <div style="text-align:right">
              <div style="font-size:20px;font-weight:700;color:{color}">{day_label}</div>
              <div style="font-size:12px;color:#90a4ae">{e['earnings_date']} {e['timing']} &nbsp;{confirmed}</div>
            </div>
          </div>
          <div style="margin-top:12px;display:grid;grid-template-columns:1fr 1fr;gap:10px">
            <div>
              <div style="font-size:12px;font-weight:600;color:#1565c0;margin-bottom:4px">📋 重点关注指标</div>
              <ul style="font-size:13px;padding-left:16px;color:#333;margin:0">{metrics}</ul>
            </div>
            <div>
              <div style="font-size:12px;font-weight:600;color:#546e7a;margin-bottom:4px">📌 上季回顾</div>
              <div style="font-size:12.5px;color:#546e7a">{e['last_summary'] or '—'}</div>
              {f'<div style="margin-top:6px"><a href="{e["ir_url"]}" style="font-size:11.5px;color:#1565c0">📎 IR官网</a></div>' if e.get("ir_url") else ""}
            </div>
          </div>
          {opt_note}
        </div>"""

    # Full calendar table
    cal_rows = ""
    for e in full_calendar:
        days = e["days_until"]
        color = urgency_color(days)
        if days < 0:
            day_str = f'<span style="color:#90a4ae">已过期</span>'
        elif days == 0:
            day_str = '<span style="color:#c62828;font-weight:700">今天</span>'
        else:
            day_str = f'<span style="color:{color};font-weight:{"700" if days<=5 else "400"}">{days}天后</span>'
        confirmed = "✅" if e["confirmed"] else "〜"
        opt_icon = " ⚙️" if e.get("options_note") else ""
        cal_rows += f"""
        <tr>
          <td><strong>{e['symbol']}</strong>{opt_icon}</td>
          <td>{e['company'][:25]}</td>
          <td>{e['exchange']}</td>
          <td>{e['earnings_date']}</td>
          <td>{e['timing']}</td>
          <td>{day_str}</td>
          <td style="font-size:11px;color:#90a4ae">{confirmed}</td>
        </tr>"""

    count = len(upcoming)
    count_label = f"{count} 只标的" if count > 0 else "无"

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <title>季报追踪预警 {run_date}</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: -apple-system,'PingFang SC',sans-serif; background:#f4f6f9;
            padding:20px; max-width:900px; margin:0 auto; }}
    .header {{ background:linear-gradient(135deg,#0d47a1,#1565c0,#1976d2);
               color:white; padding:28px 36px; border-radius:16px; margin-bottom:20px; }}
    .header h1 {{ font-size:22px; margin-bottom:4px; }}
    .header .sub {{ opacity:.82; font-size:13px; }}
    .card {{ background:white; border-radius:12px; padding:22px;
             box-shadow:0 2px 8px rgba(0,0,0,.07); margin-bottom:18px; }}
    .section-title {{ font-size:14px; font-weight:700; color:#0d47a1;
                      border-bottom:2px solid #e3f2fd; padding-bottom:8px; margin-bottom:14px; }}
    table {{ width:100%; border-collapse:collapse; font-size:13px; }}
    th {{ background:#e3f2fd; color:#0d47a1; padding:8px 10px; text-align:left; font-weight:600; }}
    td {{ padding:8px 10px; border-bottom:1px solid #f0f0f0; }}
    tr:hover td {{ background:#f8faff; }}
    .footer {{ text-align:center; color:#90a4ae; font-size:11px; padding:16px 0; }}
  </style>
</head>
<body>

<div class="header">
  <h1>📅 季报追踪预警</h1>
  <div class="sub">{run_date} &nbsp;|&nbsp; 未来7天内财报：<strong>{count_label}</strong></div>
</div>

{'<div class="card"><div class="section-title">🔔 即将发布财报（7天内）</div>' + alert_rows + '</div>' if upcoming else
 '<div class="card" style="border-left:4px solid #43a047"><div class="section-title">✅ 未来7天无财报发布</div><p style="color:#546e7a;font-size:14px">所有持仓标的近期均无财报，无需特别关注。</p></div>'}

<div class="card">
  <div class="section-title">📆 完整季报日历（所有持仓）</div>
  <table>
    <thead><tr><th>代码</th><th>公司</th><th>市场</th><th>财报日期</th><th>时间</th><th>距今</th><th>确认</th></tr></thead>
    <tbody>{cal_rows}</tbody>
  </table>
  <p style="font-size:11.5px;color:#90a4ae;margin-top:10px">
    ✅=日期已官方确认 &nbsp;〜=预估日期（±7天）&nbsp; ⚙️=有期权持仓需关注 &nbsp;|&nbsp;
    日期更新：季报发布后手动更新 earnings_calendar.json
  </p>
</div>

<div class="card" style="background:#fff8e1;border:1px solid #f9a825">
  <div class="section-title" style="color:#e65100">💡 季报前后行动建议</div>
  <p style="font-size:13.5px;color:#5d4037">
    <strong>财报前3天：</strong>复习上季要点，确认期权是否需要调整（如有短期期权在财报前后到期）<br>
    <strong>财报当晚：</strong>快速核对关键指标是否与预期一致，重大偏差时发送 <code>/估值 [代码] [新股价]</code> 触发重新评估<br>
    <strong>财报后：</strong>更新 earnings_calendar.json 中的 next_earnings 日期和 last_result_summary
  </p>
</div>

<div class="footer">
  季报追踪系统 v1.0 · {run_date} · 日期来源：手动维护（预估）+ yfinance自动校正
</div>
</body>
</html>"""


# ─────────────────────────────────────────────
# EMAIL
# ─────────────────────────────────────────────

def send_email(html: str, subject: str, cfg: dict) -> bool:
    ec = cfg.get("email", {})
    if not ec.get("enabled"):
        return False
    sender = ec.get("sender", "")
    password = os.environ.get("IC_EMAIL_PASSWORD") or ec.get("password", "")
    recipients = ec.get("recipients", [])
    if not all([sender, password, recipients]) or "YOUR_" in password:
        logging.warning("邮件配置不完整，跳过")
        return False
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(html, "html", "utf-8"))
    try:
        if ec.get("use_ssl_direct", False):
            with smtplib.SMTP_SSL(ec["smtp_host"], ec["smtp_port"]) as srv:
                srv.login(sender, password)
                srv.sendmail(sender, recipients, msg.as_string())
        else:
            with smtplib.SMTP(ec["smtp_host"], ec["smtp_port"]) as srv:
                if ec.get("use_tls", True):
                    srv.starttls()
                srv.login(sender, password)
                srv.sendmail(sender, recipients, msg.as_string())
        logging.info(f"✅ 邮件已发送至 {recipients}")
        return True
    except Exception as e:
        logging.error(f"邮件发送失败: {e}")
        return False


# ─────────────────────────────────────────────
# AUTO-UPDATE
# ─────────────────────────────────────────────

def auto_update_dates(calendar: dict) -> int:
    """Try to update next_earnings dates from yfinance. Returns number updated."""
    updated = 0
    us_symbols = {
        sym: info for sym, info in calendar["holdings"].items()
        if info.get("exchange") == "US"
    }
    logging.info(f"尝试从 yfinance 自动更新 {len(us_symbols)} 只美股财报日期...")
    for symbol, info in us_symbols.items():
        new_date = try_fetch_next_earnings(symbol)
        if new_date and new_date != info.get("next_earnings"):
            logging.info(f"  {symbol}: {info.get('next_earnings')} → {new_date} (yfinance)")
            calendar["holdings"][symbol]["next_earnings"] = new_date
            calendar["holdings"][symbol]["next_earnings_confirmed"] = True
            updated += 1
        else:
            logging.info(f"  {symbol}: 保持 {info.get('next_earnings')}（yfinance无更新）")
    return updated


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="季报追踪系统")
    parser.add_argument("--days",     type=int, default=7, help="预警窗口天数（默认7）")
    parser.add_argument("--summary",  action="store_true", help="强制输出完整30天日历")
    parser.add_argument("--update",   action="store_true", help="尝试yfinance自动更新财报日期")
    parser.add_argument("--no-email", action="store_true", help="不发邮件")
    args = parser.parse_args()

    setup_logging()
    run_date = datetime.now().strftime("%Y-%m-%d %H:%M")

    if not CALENDAR_PATH.exists():
        logging.error(f"找不到 {CALENDAR_PATH}")
        return

    calendar = load_json(CALENDAR_PATH)
    cfg = load_json(CONFIG_PATH) if CONFIG_PATH.exists() else {}

    # Auto-update mode
    if args.update:
        n = auto_update_dates(calendar)
        if n > 0:
            calendar["_last_updated"] = date.today().isoformat()
            save_json(CALENDAR_PATH, calendar)
            logging.info(f"已更新 {n} 个财报日期并保存")
        else:
            logging.info("无新的财报日期更新")
        return

    days = 30 if args.summary else args.days
    upcoming = get_upcoming_earnings(calendar, days_ahead=args.days)
    full_calendar = get_full_calendar(calendar)

    # Console output
    logging.info(f"季报追踪：检查未来{args.days}天内财报")
    if upcoming:
        logging.info(f"发现 {len(upcoming)} 只标的即将发布财报：")
        for e in upcoming:
            logging.info(f"  📅 {e['symbol']} ({e['company'][:20]}) — {e['earnings_date']} ({e['days_until']}天后)")
    else:
        logging.info("未来7天无财报发布")

    # Always show full calendar
    logging.info("\n完整财报日历：")
    for e in full_calendar:
        logging.info(f"  {e['earnings_date']}  {e['symbol']:12s}  {e['company'][:25]:25s}  {e['days_until']}天后")

    # Generate HTML and send email if needed
    html = generate_html(upcoming, full_calendar, run_date)

    # Save local report
    reports_dir = SCRIPT_DIR / "reports"
    reports_dir.mkdir(exist_ok=True)
    report_file = reports_dir / f"earnings_{date.today().strftime('%Y%m%d')}.html"
    with open(report_file, "w", encoding="utf-8") as f:
        f.write(html)
    logging.info(f"报告已保存: {report_file}")

    # Send email: only if there are upcoming earnings within alert window
    alert_days = calendar.get("_alert_days_before", 5)
    should_alert = any(e["days_until"] <= alert_days for e in upcoming)

    if should_alert and not args.no_email:
        syms = ", ".join(e["symbol"] for e in upcoming if e["days_until"] <= alert_days)
        prefix = cfg.get("email", {}).get("subject_prefix", "[投资预警]")
        subject = f"{prefix} 📅 季报预警：{syms} 将于{alert_days}天内发布财报"
        send_email(html, subject, cfg)
    elif upcoming and not args.no_email:
        logging.info(f"有财报即将发布但超过{alert_days}天预警窗口，不发送邮件")
    elif args.summary:
        # Summary mode always sends
        prefix = cfg.get("email", {}).get("subject_prefix", "[投资预警]")
        send_email(html, f"{prefix} 📆 季报日历汇总 {date.today().isoformat()}", cfg)


if __name__ == "__main__":
    main()
