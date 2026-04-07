#!/usr/bin/env python3
"""
铁鹰策略自动监控 & 调参建议引擎
每日盘后（美东 14:45）自动运行，功能：
  1. 持仓快照：每日记录 P&L、DTE、价格距行权价距离
  2. HV20 趋势：追踪三标的波动率变化，提前预警
  3. 保证金监控：实际占用 vs $20,000 总资金
  4. 滑点记录：开仓时实际成交价 vs 中间价
  5. 建议引擎：积累 3+ 笔交易后，自动分析并生成调参建议
  6. 邮件报告：每日发送快照 + 阶段性发送建议报告
"""

import json
import logging
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

# ── 路径 ─────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
LOG_DIR = SCRIPT_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
HISTORY_FILE = LOG_DIR / "monitor_history.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_DIR / "monitor.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# ── 常量 ─────────────────────────────────────────────────
ASSETS = [
    {"ticker": "US.QQQ", "name": "QQQ"},
    {"ticker": "US.IWM", "name": "IWM"},
    {"ticker": "US.GLD", "name": "GLD"},
]
TOTAL_CAPITAL    = 20_000   # 实际总资金（含 $5k buffer）
ALLOCATED_CAPITAL = 15_000  # 策略分配资金
HV20_WARN_LEVEL  = 0.22     # HV20 接近阈值时预警（低于 25% 阈值 3%）
HV20_BLOCK_LEVEL = 0.25     # 策略禁止开仓阈值
MIN_TRADES_FOR_SUGGESTION = 3  # 至少积累几笔交易才生成建议


# ═══════════════════════════════════════════════════════════
# 1. 历史数据存储
# ═══════════════════════════════════════════════════════════

class TradeHistory:
    """本地 JSON 存储：持仓快照 + 交易记录"""

    def __init__(self, path: Path = HISTORY_FILE):
        self.path = path
        self._data = self._load()

    def _load(self) -> Dict:
        if self.path.exists():
            try:
                return json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"snapshots": [], "trades": []}

    def save(self):
        self.path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

    # ── 快照 ─────────────────────────────────────────────
    def add_snapshot(self, snapshot: Dict):
        """追加每日持仓快照（去重：同一天只保留最新一条）"""
        today = str(date.today())
        self._data["snapshots"] = [
            s for s in self._data["snapshots"] if s.get("date") != today
        ]
        snapshot["date"] = today
        self._data["snapshots"].append(snapshot)
        # 只保留最近 90 天
        self._data["snapshots"] = self._data["snapshots"][-90:]
        self.save()

    def snapshots(self) -> List[Dict]:
        return self._data.get("snapshots", [])

    # ── 交易记录 ─────────────────────────────────────────
    def add_trade(self, trade: Dict):
        """记录一笔开仓/平仓（由 main_ic_us 调用或监控器解析）"""
        trade["recorded_at"] = datetime.now().isoformat()
        self._data["trades"].append(trade)
        self.save()

    def trades(self) -> List[Dict]:
        return self._data.get("trades", [])

    def open_trades(self) -> List[Dict]:
        return [t for t in self.trades() if t.get("action") == "open"]


# ═══════════════════════════════════════════════════════════
# 2. 市场数据获取
# ═══════════════════════════════════════════════════════════

class MarketData:
    """通过富途 API 获取行情数据"""

    def __init__(self, host="127.0.0.1", port=11111):
        from futu import OpenQuoteContext
        self.ctx = OpenQuoteContext(host=host, port=port)

    def close(self):
        self.ctx.close()

    def get_hv20(self, ticker: str) -> Optional[float]:
        """计算标的 20 日历史波动率"""
        import numpy as np
        from futu import RET_OK, KLType
        today = date.today()
        start = (today - timedelta(days=60)).isoformat()
        ret, data, _ = self.ctx.request_history_kline(
            code=ticker, start=start, end=today.isoformat(),
            ktype=KLType.K_DAY, max_count=100,
        )
        if ret != RET_OK or data is None or data.empty or len(data) < 21:
            return None
        closes = data["close"].astype(float)
        log_returns = np.log(closes / closes.shift(1)).dropna()
        hv20 = float(log_returns.tail(20).std() * (252 ** 0.5))
        return hv20

    def get_hv20_all(self) -> Dict[str, Optional[float]]:
        result = {}
        for a in ASSETS:
            result[a["name"]] = self.get_hv20(a["ticker"])
        return result

    def get_price(self, ticker: str) -> Optional[float]:
        from futu import RET_OK
        self.ctx.subscribe([ticker], ["QUOTE"])
        ret, data = self.ctx.get_stock_quote([ticker])
        if ret == RET_OK and not data.empty:
            return float(data.iloc[0]["last_price"])
        return None

    def get_positions(self) -> List[Dict]:
        """获取所有美股期权持仓"""
        from futu import OpenSecTradeContext, TrdEnv
        from config import FUTU_CONFIG

        acc_id = int(FUTU_CONFIG.get("real_acc_id", "0"))
        trade_ctx = OpenSecTradeContext(
            host=FUTU_CONFIG["host"],
            port=FUTU_CONFIG["port"],
            filter_trdmarket="US",
            security_firm="FUTUSECURITIES",
        )
        ret, pos_data = trade_ctx.position_list_query(
            trd_env=TrdEnv.REAL,
            acc_id=acc_id,
            refresh_cache=True,
        )
        trade_ctx.close()

        if ret != 0 or pos_data is None or pos_data.empty:
            return []

        positions = []
        for _, row in pos_data.iterrows():
            code = str(row["code"])
            # 只关心三标的期权
            if not any(a["name"] in code for a in ASSETS):
                continue
            m = re.search(r"([A-Z]+)(\d{6})([CP])(\d+)", code)
            expiry = None
            if m:
                try:
                    expiry = datetime.strptime(m.group(2), "%y%m%d").date()
                except ValueError:
                    pass
            qty = int(row.get("qty", 0))
            if qty == 0:
                continue  # 跳过已平仓持仓（Futu API 会保留 qty=0 的记录）
            # strike: 富途代码末尾数字为行权价×1000，如 C615000 = $615
            strike_raw = float(m.group(4)) if m else 0.0
            strike = strike_raw / 1000.0 if strike_raw >= 1000 else strike_raw
            positions.append({
                "code": code,
                "asset": m.group(1) if m else "?",
                "expiry": expiry,
                "option_type": m.group(3) if m else "?",  # C/P
                "strike": strike,
                "qty": qty,
                "cost_price": float(row.get("cost_price", 0) or 0),
                "unrealized_pl": float(row.get("unrealized_pl", 0) or 0),
                "market_val": float(row.get("market_val", 0) or 0),
            })
        return positions

    def get_account_info(self) -> Dict:
        """获取账户资金信息（现金、保证金占用）"""
        from futu import OpenSecTradeContext, TrdEnv
        from config import FUTU_CONFIG

        acc_id = int(FUTU_CONFIG.get("real_acc_id", "0"))
        trade_ctx = OpenSecTradeContext(
            host=FUTU_CONFIG["host"],
            port=FUTU_CONFIG["port"],
            filter_trdmarket="US",
            security_firm="FUTUSECURITIES",
        )
        ret, data = trade_ctx.accinfo_query(
            trd_env=TrdEnv.REAL,
            acc_id=acc_id,
            refresh_cache=True,
        )
        trade_ctx.close()

        if ret != 0 or data is None or data.empty:
            return {}
        row = data.iloc[0]
        return {
            "cash": float(row.get("cash", 0) or 0),
            "total_assets": float(row.get("total_assets", 0) or 0),
            "margin_used": float(row.get("margin_call_margin", 0)
                                  or row.get("initial_margin", 0) or 0),
            "buying_power": float(row.get("available_funds", 0) or 0),
        }


# ═══════════════════════════════════════════════════════════
# 3. 建议引擎
# ═══════════════════════════════════════════════════════════

class SuggestionEngine:
    """
    积累交易数据后，自动生成调参建议。
    逻辑：量化→定性→文字建议，不自动改代码，只发邮件给你决策。
    """

    def __init__(self, history: TradeHistory):
        self.history = history

    def analyze(self) -> List[Dict]:
        """返回建议列表，每条: {level, title, detail}"""
        suggestions = []
        open_trades = self.history.open_trades()
        n = len(open_trades)

        if n < MIN_TRADES_FOR_SUGGESTION:
            return []  # 数据不足，暂不建议

        suggestions += self._analyze_slippage(open_trades)
        suggestions += self._analyze_win_rate(open_trades)
        suggestions += self._analyze_hv20_filter(open_trades)
        suggestions += self._analyze_asset_performance(open_trades)
        return suggestions

    # ── 滑点分析 ─────────────────────────────────────────
    def _analyze_slippage(self, trades: List[Dict]) -> List[Dict]:
        slippages = [
            t["slippage_usd"]
            for t in trades
            if "slippage_usd" in t
        ]
        if len(slippages) < 2:
            return []

        avg_slip = sum(slippages) / len(slippages)
        suggestions = []

        if avg_slip < -20:  # 平均每笔滑点损失 > $20
            suggestions.append({
                "level": "WARNING",
                "title": f"滑点偏大（平均 ${avg_slip:.1f}/笔）",
                "detail": (
                    f"已记录 {len(slippages)} 笔开仓，平均滑点 ${avg_slip:.1f}。"
                    f"建议：① 将 min_premium 从 $30 提高到 $50，过滤流动性差的情况；"
                    f"② 对 GLD 单独设更高的 min_premium（如 $40）。"
                ),
            })
        elif avg_slip > -5:  # 滑点极小，说明流动性好
            suggestions.append({
                "level": "INFO",
                "title": f"滑点良好（平均 ${avg_slip:.1f}/笔）",
                "detail": "三标的流动性均不错，当前 min_premium=$30 设置合理，无需调整。",
            })
        return suggestions

    # ── 胜率分析 ─────────────────────────────────────────
    def _analyze_win_rate(self, trades: List[Dict]) -> List[Dict]:
        closed = [t for t in self.history.trades() if t.get("action") == "close"]
        if len(closed) < 3:
            return []

        wins = [t for t in closed if t.get("pnl", 0) > 0]
        win_rate = len(wins) / len(closed)
        suggestions = []

        if win_rate < 0.55:
            suggestions.append({
                "level": "WARNING",
                "title": f"胜率偏低（{win_rate*100:.0f}%，回测目标 70%+）",
                "detail": (
                    f"已完成 {len(closed)} 笔，胜率 {win_rate*100:.0f}%。"
                    "可能原因：① HV20 过滤失灵，建议临时将阈值从 25% 下调至 22%；"
                    "② 考虑将 Wing 从 8% 扩大到 10%（降低被击穿概率，代价是权利金减少约 20%）。"
                ),
            })
        elif win_rate > 0.80:
            suggestions.append({
                "level": "INFO",
                "title": f"胜率优秀（{win_rate*100:.0f}%）",
                "detail": (
                    f"已完成 {len(closed)} 笔，胜率 {win_rate*100:.0f}%，高于回测预期。"
                    "策略运行正常，可考虑在 HV20 < 15% 时适当缩小 OTM 至 4%，提高权利金收入。"
                ),
            })
        return suggestions

    # ── HV20 过滤频率 ────────────────────────────────────
    def _analyze_hv20_filter(self, trades: List[Dict]) -> List[Dict]:
        """如果空仓天数过多（HV20 一直高），提示考虑百分位方案"""
        snapshots = self.history.snapshots()
        if len(snapshots) < 10:
            return []

        # 计算各标的 HV20 超过阈值的天数比例
        block_days = {a["name"]: 0 for a in ASSETS}
        total = len(snapshots)
        for s in snapshots:
            hv20_map = s.get("hv20", {})
            for name in block_days:
                v = hv20_map.get(name)
                if v and v > HV20_BLOCK_LEVEL:
                    block_days[name] += 1

        suggestions = []
        for name, cnt in block_days.items():
            ratio = cnt / total
            if ratio > 0.50:  # 超过一半时间被过滤
                suggestions.append({
                    "level": "INFO",
                    "title": f"{name} HV20 过滤率过高（{ratio*100:.0f}% 的天数超阈值）",
                    "detail": (
                        f"{name} 有 {ratio*100:.0f}% 的观测日 HV20 > 25%，策略大量空仓。"
                        "建议：对 GLD 单独设置更高的 HV20 阈值（如 40%），"
                        "或改用「HV20 处于过去1年 60% 分位以下」作为开仓条件，"
                        "提高 GLD 的资金利用率。"
                    ),
                })
        return suggestions

    # ── 各标的盈亏对比 ───────────────────────────────────
    def _analyze_asset_performance(self, trades: List[Dict]) -> List[Dict]:
        closed = [t for t in self.history.trades() if t.get("action") == "close" and "pnl" in t]
        if len(closed) < 6:
            return []

        pnl_by_asset: Dict[str, List[float]] = {}
        for t in closed:
            asset = t.get("asset", "?")
            pnl_by_asset.setdefault(asset, []).append(t["pnl"])

        suggestions = []
        for asset, pnls in pnl_by_asset.items():
            avg = sum(pnls) / len(pnls)
            if avg < 0:
                suggestions.append({
                    "level": "WARNING",
                    "title": f"{asset} 平均亏损（${avg:.0f}/笔，共 {len(pnls)} 笔）",
                    "detail": (
                        f"{asset} 实盘表现弱于回测，建议：① 暂停 {asset} 开仓 1 个月观察；"
                        "② 检查 HV20 过滤是否对该标的有效。"
                    ),
                })
        return suggestions


# ═══════════════════════════════════════════════════════════
# 4. 邮件报告
# ═══════════════════════════════════════════════════════════

class MonitorReporter:
    """生成并发送监控日报"""

    def __init__(self):
        from main_ic_us import EmailNotifier
        self.notifier = EmailNotifier()

    def send_daily_report(
        self,
        snapshot: Dict,
        suggestions: List[Dict],
    ):
        today = str(date.today())
        hv20 = snapshot.get("hv20", {})
        positions = snapshot.get("positions", [])
        account = snapshot.get("account", {})
        total_pl = snapshot.get("total_unrealized_pl", 0.0)

        # ── 颜色辅助 ────────────────────────────────────
        def pl_color(v):
            return "#2e7d32" if v >= 0 else "#c62828"

        def hv_color(v):
            if v is None:
                return "#888"
            if v >= HV20_BLOCK_LEVEL:
                return "#c62828"
            if v >= HV20_WARN_LEVEL:
                return "#e65100"
            return "#2e7d32"

        # ── HV20 表格 ────────────────────────────────────
        hv_rows = ""
        for name in ["QQQ", "IWM", "GLD"]:
            v = hv20.get(name)
            v_str = f"{v*100:.1f}%" if v else "N/A"
            status = ("🔴 禁止开仓" if v and v >= HV20_BLOCK_LEVEL
                      else ("⚠️ 接近阈值" if v and v >= HV20_WARN_LEVEL
                            else "✅ 正常"))
            hv_rows += (
                f"<tr><td><b>{name}</b></td>"
                f"<td style='color:{hv_color(v)}'>{v_str}</td>"
                f"<td>{status}</td></tr>"
            )

        # ── 持仓表格 ────────────────────────────────────
        pos_rows = ""
        if positions:
            # 按标的 + 到期日分组
            groups: Dict[str, List] = {}
            for p in positions:
                key = f"{p['asset']} 到期 {p['expiry']}"
                groups.setdefault(key, []).append(p)

            for group_key, legs in groups.items():
                group_pl = sum(l["unrealized_pl"] for l in legs)
                dte = (legs[0]["expiry"] - date.today()).days if legs[0]["expiry"] else "?"
                pos_rows += (
                    f"<tr style='background:#f9f9f9'>"
                    f"<td colspan='4'><b>{group_key}（DTE={dte}）</b> "
                    f"未实现盈亏: <span style='color:{pl_color(group_pl)}'>${group_pl:+.0f}</span></td></tr>"
                )
                for leg in legs:
                    leg_pl = leg["unrealized_pl"]
                    leg_pl_color = pl_color(leg_pl)
                    pos_rows += (
                        f"<tr><td style='padding-left:20px'>{leg['code']}</td>"
                        f"<td>{leg['option_type']} K={leg['strike']:.0f}</td>"
                        f"<td>{leg['qty']}张 成本${leg['cost_price']:.2f}</td>"
                        f"<td style='color:{leg_pl_color}'>${leg_pl:+.2f}</td></tr>"
                    )
        else:
            pos_rows = "<tr><td colspan='4' style='color:#888'>当前无持仓</td></tr>"

        # ── 保证金 / 资金 ────────────────────────────────
        margin_used = account.get("margin_used", 0)
        cash = account.get("cash", 0)
        total_assets = account.get("total_assets", 0)
        margin_ratio = margin_used / TOTAL_CAPITAL * 100 if TOTAL_CAPITAL else 0
        margin_color = "#c62828" if margin_ratio > 75 else ("#e65100" if margin_ratio > 55 else "#2e7d32")

        # ── 建议区块 ────────────────────────────────────
        suggestion_html = ""
        if suggestions:
            rows = ""
            for s in suggestions:
                icon = "🔴" if s["level"] == "WARNING" else "🟡" if s["level"] == "INFO" else "ℹ️"
                rows += (
                    f"<tr><td style='vertical-align:top;padding:4px'>{icon}</td>"
                    f"<td><b>{s['title']}</b><br>"
                    f"<span style='color:#555;font-size:13px'>{s['detail']}</span></td></tr>"
                )
            suggestion_html = f"""
<h3>💡 调参建议</h3>
<table border='0' cellpadding='6' style='font-family:sans-serif;width:100%'>
{rows}
</table>
"""
        else:
            open_count = len(self.history.open_trades()) if hasattr(self, 'history') else 0
            if open_count < MIN_TRADES_FOR_SUGGESTION:
                suggestion_html = (
                    f"<p style='color:#888;font-size:13px'>"
                    f"💡 已积累 {open_count} / {MIN_TRADES_FOR_SUGGESTION} 笔开仓，"
                    f"达到 {MIN_TRADES_FOR_SUGGESTION} 笔后将自动生成调参建议。</p>"
                )

        # ── 组装邮件 ────────────────────────────────────
        subject = (
            f"📊 铁鹰监控日报 {today} | "
            f"总P&L ${total_pl:+.0f} | "
            f"{'有建议' if suggestions else '正常'}"
        )
        body = f"""
<div style="font-family:sans-serif;max-width:700px">
<h2>📊 铁鹰策略监控日报 — {today}</h2>

<h3>📈 HV20 波动率状态（开仓过滤器）</h3>
<table border='1' cellpadding='6' style='border-collapse:collapse'>
<tr style='background:#f2f2f2'><th>标的</th><th>HV20</th><th>状态</th></tr>
{hv_rows}
</table>
<p style='font-size:12px;color:#888'>阈值：≥25% 禁止开仓 | ≥22% 预警</p>

<h3>📋 当前持仓</h3>
<table border='1' cellpadding='6' style='border-collapse:collapse;width:100%'>
<tr style='background:#f2f2f2'><th>代码</th><th>类型/行权价</th><th>数量/成本</th><th>浮盈亏</th></tr>
{pos_rows}
</table>
<p><b>总未实现盈亏：</b>
<span style='color:{pl_color(total_pl)};font-size:18px'><b>${total_pl:+.0f}</b></span></p>

<h3>💰 资金状态</h3>
<table border='1' cellpadding='6' style='border-collapse:collapse'>
<tr><td>总资产</td><td>${total_assets:,.0f}</td></tr>
<tr><td>现金</td><td>${cash:,.0f}</td></tr>
<tr><td>保证金占用</td>
    <td style='color:{margin_color}'>${margin_used:,.0f}
    （占总资金 {margin_ratio:.0f}%，预算上限 75%）</td></tr>
<tr><td>策略分配</td><td>${ALLOCATED_CAPITAL:,} / 总资金 ${TOTAL_CAPITAL:,}（$5k buffer 保留）</td></tr>
</table>

{suggestion_html}

<p style='color:#aaa;font-size:11px;margin-top:24px'>
自动发送 · 铁鹰量化监控系统 · {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
</p>
</div>
"""
        self.notifier._send(subject, body)
        logger.info(f"📧 日报已发送: {subject}")

    def set_history(self, h: TradeHistory):
        self.history = h


# ═══════════════════════════════════════════════════════════
# 5. 滑点记录工具（供 main_ic_us.py 在开仓后调用）
# ═══════════════════════════════════════════════════════════

def record_open_trade(
    asset: str,
    expiry: str,
    strikes: Dict,
    expected_premium: float,
    actual_premium: float,
    hv20: float,
):
    """
    开仓后调用，记录滑点数据。
    expected_premium: 下单前四腿中间价估算的净权利金
    actual_premium:   实际成交净权利金
    """
    history = TradeHistory()
    slippage = actual_premium - expected_premium
    history.add_trade({
        "action": "open",
        "asset": asset,
        "expiry": expiry,
        "strikes": strikes,
        "expected_premium": round(expected_premium, 2),
        "actual_premium": round(actual_premium, 2),
        "slippage_usd": round(slippage, 2),
        "hv20_at_open": round(hv20, 4),
        "date": str(date.today()),
    })
    logger.info(
        f"📝 开仓记录: {asset} 到期{expiry} "
        f"预期权利金${expected_premium:.0f} 实际${actual_premium:.0f} "
        f"滑点${slippage:+.0f}"
    )


def record_close_trade(
    asset: str,
    expiry: str,
    pnl: float,
    reason: str,
):
    """平仓后调用，记录盈亏"""
    history = TradeHistory()
    history.add_trade({
        "action": "close",
        "asset": asset,
        "expiry": expiry,
        "pnl": round(pnl, 2),
        "reason": reason,
        "date": str(date.today()),
    })
    logger.info(f"📝 平仓记录: {asset} 到期{expiry} 盈亏${pnl:+.0f} 原因:{reason}")


# ═══════════════════════════════════════════════════════════
# 6. 主入口
# ═══════════════════════════════════════════════════════════

def run_monitor():
    """每日盘后执行一次完整监控"""
    logger.info("=" * 55)
    logger.info("🔍 铁鹰监控启动")
    logger.info("=" * 55)

    history = TradeHistory()
    md = MarketData()

    try:
        # ── Step 1: 获取 HV20 ────────────────────────
        logger.info("📊 计算 HV20...")
        hv20_map = md.get_hv20_all()
        for name, v in hv20_map.items():
            if v:
                status = "🔴 超阈值" if v >= HV20_BLOCK_LEVEL else ("⚠️ 接近" if v >= HV20_WARN_LEVEL else "✅")
                logger.info(f"   {name}: {v*100:.1f}% {status}")

        # ── Step 2: 获取持仓 ─────────────────────────
        logger.info("📋 查询持仓...")
        positions = md.get_positions()
        total_pl = sum(p["unrealized_pl"] for p in positions)
        logger.info(f"   共 {len(positions)} 腿，总浮盈亏 ${total_pl:+.0f}")

        # ── Step 3: 账户资金 ─────────────────────────
        logger.info("💰 查询账户资金...")
        account = md.get_account_info()
        margin_pct = account.get("margin_used", 0) / TOTAL_CAPITAL * 100
        logger.info(f"   保证金占用: ${account.get('margin_used', 0):,.0f} ({margin_pct:.0f}%)")

        # ── Step 4: 保存快照 ─────────────────────────
        snapshot = {
            "hv20": hv20_map,
            "positions": [
                {k: str(v) if isinstance(v, date) else v for k, v in p.items()}
                for p in positions
            ],
            "total_unrealized_pl": total_pl,
            "account": account,
        }
        history.add_snapshot(snapshot)

        # ── Step 5: 生成建议 ─────────────────────────
        engine = SuggestionEngine(history)
        suggestions = engine.analyze()
        if suggestions:
            logger.info(f"💡 生成 {len(suggestions)} 条调参建议")
            for s in suggestions:
                logger.info(f"   [{s['level']}] {s['title']}")
        else:
            logger.info("💡 暂无建议（数据积累中）")

        # ── Step 6: 发送日报 ─────────────────────────
        reporter = MonitorReporter()
        reporter.set_history(history)
        reporter.send_daily_report(snapshot, suggestions)

    except Exception as e:
        logger.error(f"监控执行异常: {e}", exc_info=True)
        # 异常时也尝试发邮件告警
        try:
            from main_ic_us import EmailNotifier
            EmailNotifier().send_alert("CRITICAL", f"监控程序异常: {e}", "请检查 logs/monitor.log")
        except Exception:
            pass
    finally:
        md.close()

    logger.info("✅ 监控执行完成")


if __name__ == "__main__":
    run_monitor()
