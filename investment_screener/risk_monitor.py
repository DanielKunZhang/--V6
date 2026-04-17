#!/usr/bin/env python3
"""
组合风险监控 v1.0 — 浓度与相关性分析
- 按风险因子归因：中国地缘、AI芯片周期、USD/CNY、港股折价等
- 检测单一因子过度集中（>40%）或单一行业过度集中（>35%）
- 生成 HTML 报告 + 邮件预警

用法：
  python3 risk_monitor.py              # 分析当前持仓，生成报告
  python3 risk_monitor.py --no-email  # 仅控制台+本地报告，不发邮件
  python3 risk_monitor.py --summary   # 强制发送邮件（无论是否触发预警）
"""

import json
import logging
import argparse
import os
from datetime import date, datetime
from pathlib import Path

from env_utils import load_local_env

load_local_env()

SCRIPT_DIR   = Path(__file__).parent
HOLDINGS_PATH = SCRIPT_DIR / "holdings.json"
CONFIG_PATH   = SCRIPT_DIR / "config.json"
LOG_PATH      = SCRIPT_DIR / "screener.log"

# ─────────────────────────────────────────────────────────────
# 风险因子定义
# 每只持仓可同时归属多个风险因子（权重叠加）
# ─────────────────────────────────────────────────────────────

RISK_FACTORS = {
    "china_geopolitical": {
        "label": "中国地缘政治风险",
        "description": "中美关系恶化、台海、监管、CAC退市等系统性风险",
        "color": "#c62828",
        "threshold_pct": 40,   # 超过40%总市值触发高警戒
        "warn_pct": 30,
        "symbols": {
            # symbol_key: exposure_weight (0~1)
            "PDD": 0.9,            # 中概ADR，Temu受关税影响
            "TME": 1.0,            # 中概ADR
            "0700.HK_富途": 0.7,   # 港股腾讯，地缘折价
            "0700.HK_港股通": 0.7,
            "0700.HK_RSU": 0.7,
            "9992.HK_富途": 0.7,   # 泡泡玛特
            "9992.HK_港股通": 0.7,
            # 9999.HK 正股已平仓，仅剩 Short Put 期权（名义暴露小，不计入）
            "000333.SZ": 0.5,      # A股美的，美国关税风险
            "600036.SS": 0.3,      # A股招行，间接暴露
        }
    },
    "ai_semiconductor": {
        "label": "AI / 半导体周期风险",
        "description": "AI资本开支周期转向、芯片出口管制、估值泡沫破裂",
        "color": "#6a1b9a",
        "threshold_pct": 35,
        "warn_pct": 25,
        "symbols": {
            "NVDA": 1.0,    # 核心AI芯片
            "QCOM": 0.7,    # 半导体，AI端侧受益
            "TME": 0.1,     # 微小暴露（腾讯系AI应用）
            "0700.HK_富途": 0.2,
            "0700.HK_港股通": 0.2,
            "0700.HK_RSU": 0.2,
        }
    },
    "hkd_usd_fx": {
        "label": "港元/美元汇率风险",
        "description": "港元联系汇率制度、港股资产以HKD计价",
        "color": "#1565c0",
        "threshold_pct": 45,
        "warn_pct": 35,
        "symbols": {
            "0700.HK_富途": 1.0,
            "0700.HK_港股通": 1.0,
            "0700.HK_RSU": 1.0,
            "9992.HK_富途": 1.0,
            "9992.HK_港股通": 1.0,
            "9999.HK": 1.0,
            "hk_cash": 1.0,
        }
    },
    "cny_fx": {
        "label": "人民币汇率风险",
        "description": "CNY贬值影响A股持仓折算成USD/HKD后的实际价值",
        "color": "#2e7d32",
        "threshold_pct": 30,
        "warn_pct": 20,
        "symbols": {
            "000333.SZ": 1.0,
            "600036.SS": 1.0,
        }
    },
    "consumer_discretionary": {
        "label": "消费者可选消费集中度",
        "description": "PDD电商、泡泡玛特IP消费品——景气度与就业/消费意愿高度相关",
        "color": "#e65100",
        "threshold_pct": 30,
        "warn_pct": 20,
        "symbols": {
            "PDD": 1.0,
            "9992.HK_富途": 1.0,
            "9992.HK_港股通": 1.0,
        }
    },
    "tencent_ecosystem": {
        "label": "腾讯生态系集中度",
        "description": "腾讯直接持仓（0700.HK×3账户）+ TME（腾讯系子公司）+ 网易（腾讯业务竞争/生态关联）",
        "color": "#0277bd",
        "threshold_pct": 30,
        "warn_pct": 20,
        "symbols": {
            "0700.HK_富途": 1.0,
            "0700.HK_港股通": 1.0,
            "0700.HK_RSU": 1.0,
            "TME": 0.5,    # 腾讯控股34%股权
            # 9999.HK 正股已平仓
        }
    },
}

# ─────────────────────────────────────────────────────────────
# 近似市值（使用近期价格估算，定期手动更新）
# 单位统一为 USD（港币 /7.8，人民币 /7.3）
# ─────────────────────────────────────────────────────────────

APPROX_PRICES_USD = {
    "NVDA":            115.0,    # 约$115
    "PDD":             100.0,    # 约$100
    "QCOM":            145.0,    # 约$145
    "TME":              12.0,    # 约$12
    "0700.HK_富途":     46.0,    # 约400HKD / 7.8 ≈ $51，近期走弱用$46
    "0700.HK_港股通":   46.0,
    "0700.HK_RSU":      46.0,
    "9992.HK_富途":     16.0,    # 约125HKD / 7.8 ≈ $16
    "9992.HK_港股通":   16.0,
    # "9999.HK": 正股已平仓，Short Put 期权不计入股票市值
    "000333.SZ":        10.5,    # 约77CNY / 7.3 ≈ $10.5
    "600036.SS":         5.2,    # 约38CNY / 7.3 ≈ $5.2
    "hk_cash":           1.0,    # per HKD unit
}

# ─────────────────────────────────────────────────────────────
# 持仓规模 (shares / units)
# ─────────────────────────────────────────────────────────────

def load_position_sizes(holdings: dict) -> dict:
    """从 holdings.json 提取各 key 的持仓数量（股数/现金额）。"""
    sizes = {}
    for key, pos in holdings["positions"].items():
        if pos.get("_type") == "option":
            continue
        if pos.get("_type") == "cash":
            sizes[key] = pos.get("amount", 0)
        else:
            sizes[key] = pos.get("shares", 0)
    return sizes


def compute_market_values(sizes: dict) -> dict:
    """用近似价格计算各持仓 USD 市值。"""
    mv = {}
    for key, qty in sizes.items():
        price = APPROX_PRICES_USD.get(key, 0)
        mv[key] = qty * price
    return mv


# ─────────────────────────────────────────────────────────────
# 核心分析
# ─────────────────────────────────────────────────────────────

def analyze_concentration(mv: dict) -> dict:
    """
    返回：
      factor_results: {factor_id: {label, pct, status, positions_detail}}
      sector_results: {sector: {pct, status, symbols}}
      total_mv: float
      top_single: list of (key, pct)
    """
    total_mv = sum(mv.values())
    if total_mv == 0:
        return {}

    # --- 风险因子分析 ---
    factor_results = {}
    for fid, fdef in RISK_FACTORS.items():
        exposed_mv = 0.0
        detail = []
        for sym, weight in fdef["symbols"].items():
            val = mv.get(sym, 0) * weight
            if val > 0:
                exposed_mv += val
                detail.append({
                    "symbol": sym,
                    "weight": weight,
                    "mv_usd": mv.get(sym, 0),
                    "exposed_mv": val,
                })
        pct = exposed_mv / total_mv * 100
        if pct >= fdef["threshold_pct"]:
            status = "alert"
        elif pct >= fdef["warn_pct"]:
            status = "warn"
        else:
            status = "ok"
        detail.sort(key=lambda x: -x["exposed_mv"])
        factor_results[fid] = {
            "label": fdef["label"],
            "description": fdef["description"],
            "color": fdef["color"],
            "pct": pct,
            "exposed_mv": exposed_mv,
            "threshold_pct": fdef["threshold_pct"],
            "warn_pct": fdef["warn_pct"],
            "status": status,
            "detail": detail,
        }

    # --- 单一持仓集中度（top 3）---
    top_single = sorted(
        [(k, v / total_mv * 100) for k, v in mv.items() if v > 0],
        key=lambda x: -x[1]
    )

    return {
        "factor_results": factor_results,
        "total_mv": total_mv,
        "top_single": top_single[:6],
    }


# ─────────────────────────────────────────────────────────────
# HTML 报告
# ─────────────────────────────────────────────────────────────

STATUS_META = {
    "alert": {"icon": "🔴", "label": "高警戒", "bg": "#ffebee", "border": "#c62828"},
    "warn":  {"icon": "🟡", "label": "关注",   "bg": "#fff8e1", "border": "#f9a825"},
    "ok":    {"icon": "🟢", "label": "正常",   "bg": "#e8f5e9", "border": "#43a047"},
}


def bar_html(pct: float, threshold: float, warn: float, color: str) -> str:
    w = min(pct / threshold * 100, 100)
    return (
        f'<div style="background:#eceff1;border-radius:4px;height:10px;width:180px;display:inline-block;vertical-align:middle">'
        f'<div style="width:{w:.0f}%;height:10px;border-radius:4px;background:{color}"></div>'
        f'</div>'
        f'<span style="font-size:12px;margin-left:6px;color:#546e7a">{pct:.1f}% / 警戒{threshold:.0f}%</span>'
    )


def generate_html(result: dict, run_date: str) -> str:
    factor_results = result["factor_results"]
    total_mv = result["total_mv"]
    top_single = result["top_single"]

    alerts = [r for r in factor_results.values() if r["status"] == "alert"]
    warns  = [r for r in factor_results.values() if r["status"] == "warn"]

    # Overall status
    if alerts:
        overall_icon, overall_text, overall_bg = "🔴", f"发现 {len(alerts)} 项高警戒集中度", "#ffebee"
    elif warns:
        overall_icon, overall_text, overall_bg = "🟡", f"发现 {len(warns)} 项需关注集中度", "#fff8e1"
    else:
        overall_icon, overall_text, overall_bg = "🟢", "所有风险因子集中度正常", "#e8f5e9"

    # Factor rows
    factor_rows = ""
    for fid, r in sorted(factor_results.items(), key=lambda x: -x[1]["pct"]):
        sm = STATUS_META[r["status"]]
        detail_rows = "".join(
            f'<tr><td style="padding:3px 8px;font-size:12px">{d["symbol"]}</td>'
            f'<td style="padding:3px 8px;font-size:12px">${d["mv_usd"]:,.0f}</td>'
            f'<td style="padding:3px 8px;font-size:12px">{d["weight"]*100:.0f}%暴露</td>'
            f'<td style="padding:3px 8px;font-size:12px">${d["exposed_mv"]:,.0f}</td></tr>'
            for d in r["detail"]
        )
        factor_rows += f"""
        <div style="border:1px solid {sm['border']};border-left:5px solid {sm['border']};
                    border-radius:10px;padding:16px 20px;margin-bottom:12px;background:{sm['bg']}">
          <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:8px">
            <div>
              <span style="font-size:16px;font-weight:700;color:{r['color']}">{sm['icon']} {r['label']}</span>
              <span style="background:#eceff1;color:#546e7a;border-radius:10px;padding:2px 8px;
                           font-size:11px;margin-left:8px">{sm['label']}</span>
              <div style="font-size:12px;color:#546e7a;margin-top:4px">{r['description']}</div>
            </div>
            <div style="text-align:right">
              {bar_html(r['pct'], r['threshold_pct'], r['warn_pct'], r['color'])}
            </div>
          </div>
          <details style="margin-top:10px">
            <summary style="font-size:12px;color:#546e7a;cursor:pointer">
              显示明细（{len(r['detail'])}个持仓，加权暴露${r['exposed_mv']:,.0f}）
            </summary>
            <table style="margin-top:8px;font-size:12px;border-collapse:collapse">
              <thead><tr style="background:#f5f5f5">
                <th style="padding:3px 8px;text-align:left">持仓</th>
                <th style="padding:3px 8px;text-align:left">市值(USD)</th>
                <th style="padding:3px 8px;text-align:left">暴露权重</th>
                <th style="padding:3px 8px;text-align:left">加权暴露</th>
              </tr></thead>
              <tbody>{detail_rows}</tbody>
            </table>
          </details>
        </div>"""

    # Single position concentration
    single_rows = ""
    for key, pct in top_single:
        color = "#c62828" if pct > 30 else ("#e65100" if pct > 20 else "#2e7d32")
        single_rows += f"""
        <tr>
          <td><strong>{key}</strong></td>
          <td>${total_mv * pct / 100:,.0f}</td>
          <td>
            <div style="display:flex;align-items:center;gap:8px">
              <div style="background:#eceff1;border-radius:4px;height:8px;width:120px">
                <div style="width:{min(pct/40*100,100):.0f}%;height:8px;border-radius:4px;background:{color}"></div>
              </div>
              <span style="color:{color};font-weight:{'700' if pct>25 else '400'}">{pct:.1f}%</span>
            </div>
          </td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <title>组合风险监控 {run_date}</title>
  <style>
    * {{ box-sizing:border-box;margin:0;padding:0 }}
    body {{ font-family:-apple-system,'PingFang SC',sans-serif;background:#f4f6f9;
            padding:20px;max-width:900px;margin:0 auto }}
    .header {{ background:linear-gradient(135deg,#4a148c,#6a1b9a,#7b1fa2);
               color:white;padding:28px 36px;border-radius:16px;margin-bottom:20px }}
    .header h1 {{ font-size:22px;margin-bottom:4px }}
    .header .sub {{ opacity:.82;font-size:13px }}
    .card {{ background:white;border-radius:12px;padding:22px;
             box-shadow:0 2px 8px rgba(0,0,0,.07);margin-bottom:18px }}
    .section-title {{ font-size:14px;font-weight:700;color:#4a148c;
                      border-bottom:2px solid #f3e5f5;padding-bottom:8px;margin-bottom:14px }}
    table {{ width:100%;border-collapse:collapse;font-size:13px }}
    th {{ background:#f3e5f5;color:#4a148c;padding:8px 10px;text-align:left;font-weight:600 }}
    td {{ padding:8px 10px;border-bottom:1px solid #f0f0f0 }}
    tr:hover td {{ background:#fdf8ff }}
    .footer {{ text-align:center;color:#90a4ae;font-size:11px;padding:16px 0 }}
    .alert-banner {{ padding:14px 20px;border-radius:10px;margin-bottom:18px;
                     background:{overall_bg};border:1px solid #ddd }}
  </style>
</head>
<body>

<div class="header">
  <h1>🛡️ 组合风险监控</h1>
  <div class="sub">{run_date} &nbsp;|&nbsp; 组合总市值（估算）：${total_mv:,.0f} USD</div>
</div>

<div class="alert-banner">
  <strong style="font-size:16px">{overall_icon} {overall_text}</strong>
  <div style="font-size:12.5px;color:#546e7a;margin-top:4px">
    基于风险因子加权暴露分析。超过警戒线不代表需要立即行动，而是提示重新审视相关持仓的风险/回报平衡。
  </div>
</div>

<div class="card">
  <div class="section-title">🎯 风险因子集中度（按暴露占比排序）</div>
  {factor_rows}
</div>

<div class="card">
  <div class="section-title">📊 单一持仓集中度 TOP 6</div>
  <table>
    <thead><tr><th>持仓</th><th>估算市值(USD)</th><th>占比（警戒线40%）</th></tr></thead>
    <tbody>{single_rows}</tbody>
  </table>
</div>

<div class="card" style="background:#fff8e1;border:1px solid #f9a825">
  <div class="section-title" style="color:#e65100">💡 分散化行动建议</div>
  <p style="font-size:13.5px;color:#5d4037">
    <strong>地缘集中度高：</strong>考虑增加非中国资产比例（美股/欧洲/日本）作为对冲。中国地缘风险不代表卖出，
    但意味着任何新增仓位应优先考虑地缘中性标的，直到集中度回落至30%以下。<br><br>
    <strong>腾讯系过度集中：</strong>0700.HK（富途+港股通+RSU=2100股）+ TME同属腾讯生态，
    考虑RSU解锁后是否需要逐步减持降低单一生态系风险。<br><br>
    <strong>AI半导体：</strong>NVDA成本极低（$34），持仓价值巨大但已赚取主要收益。
    若AI资本开支出现转向信号，应优先评估是否需要锁定部分利润。
  </p>
</div>

<div class="footer">
  组合风险监控 v1.0 · {run_date} · 市值数据为近似估算，实际以券商账户为准<br>
  价格更新：修改 risk_monitor.py 中的 APPROX_PRICES_USD 字典
</div>

</body>
</html>"""


# ─────────────────────────────────────────────────────────────
# EMAIL
# ─────────────────────────────────────────────────────────────

def send_email(html: str, subject: str, cfg: dict) -> bool:
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

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
            import smtplib
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


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(LOG_PATH, encoding="utf-8"),
            logging.StreamHandler()
        ]
    )


def main():
    parser = argparse.ArgumentParser(description="组合风险监控")
    parser.add_argument("--no-email", action="store_true", help="不发邮件")
    parser.add_argument("--summary",  action="store_true", help="强制发送邮件（无论是否预警）")
    args = parser.parse_args()

    setup_logging()
    run_date = datetime.now().strftime("%Y-%m-%d %H:%M")

    holdings = json.loads(HOLDINGS_PATH.read_text(encoding="utf-8"))
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8")) if CONFIG_PATH.exists() else {}

    sizes = load_position_sizes(holdings)
    mv = compute_market_values(sizes)
    result = analyze_concentration(mv)

    factor_results = result["factor_results"]
    alerts = [r for r in factor_results.values() if r["status"] == "alert"]
    warns  = [r for r in factor_results.values() if r["status"] == "warn"]

    logging.info(f"\n====== 组合风险监控 {run_date} ======")
    logging.info(f"组合总市值（估算）: ${result['total_mv']:,.0f} USD")
    logging.info(f"\n风险因子集中度：")
    for fid, r in sorted(factor_results.items(), key=lambda x: -x[1]["pct"]):
        icon = "🔴" if r["status"]=="alert" else ("🟡" if r["status"]=="warn" else "🟢")
        logging.info(f"  {icon} {r['label']:20s}  {r['pct']:.1f}%（警戒{r['threshold_pct']}%）")

    logging.info(f"\n单一持仓集中度 TOP 6：")
    for key, pct in result["top_single"]:
        logging.info(f"  {key:25s}  {pct:.1f}%")

    # Save HTML report
    html = generate_html(result, run_date)
    reports_dir = SCRIPT_DIR / "reports"
    reports_dir.mkdir(exist_ok=True)
    report_file = reports_dir / f"risk_{date.today().strftime('%Y%m%d')}.html"
    report_file.write_text(html, encoding="utf-8")
    logging.info(f"\n报告已保存: {report_file}")

    # Send email
    prefix = cfg.get("email", {}).get("subject_prefix", "[投资预警]")
    should_send = args.summary or (not args.no_email and (alerts or warns))
    if should_send:
        if alerts:
            subject = f"{prefix} 🔴 组合风险预警：{len(alerts)}项因子超警戒线"
        elif warns:
            subject = f"{prefix} 🟡 组合风险提示：{len(warns)}项因子需关注"
        else:
            subject = f"{prefix} 🛡️ 组合风险月报 {date.today().isoformat()}"
        send_email(html, subject, cfg)
    else:
        logging.info("无预警或已禁用邮件，跳过发送")


if __name__ == "__main__":
    main()
