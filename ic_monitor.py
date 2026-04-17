#!/usr/bin/env python3
"""
铁鹰策略自动监控 & 调参建议引擎
每日盘后（美东 14:45）自动运行，功能：
  1. 持仓快照：每日记录 P&L、DTE、价格距行权价距离
  2. HV20 趋势：追踪三标的波动率变化，提前预警
  3. 保证金监控：实际占用 vs 名义资金 $30,000
  4. 滑点记录：开仓时实际成交价 vs 中间价
  5. 建议引擎：积累 3+ 笔交易后，自动分析并生成运营复盘建议
  6. 邮件报告：每日发送快照 + 阶段性发送建议报告
"""

import json
import logging
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from capacity_utils import build_capacity_snapshot

# ── 路径 ─────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
LOG_DIR = SCRIPT_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
HISTORY_FILE = LOG_DIR / "monitor_history.json"
IC_CODES_FILE = LOG_DIR / "ic_open_codes.json"
IC_OPEN_TRADE_FILE = LOG_DIR / "ic_open_trade.json"

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


def _load_live_strategy_context() -> Dict:
    from main_ic_us import (
        ASSETS as live_assets,
        CAPACITY_CONTROL,
        GROUPS_CAP_MULT,
        IC_MANUAL_CAPITAL,
        LEVERAGE,
        PRESSURE_MONITOR_CONFIG,
        _compute_live_pressure_summary,
        _compute_live_position_capacity_summary,
        _load_recent_execution_events,
        VIX_COOLDOWN_HV,
        VIX_DELEVERAGE_HV,
        VIX_HARD_STOP_HV,
    )

    return {
        "assets": [
            {
                "ticker": asset["ticker"],
                "name": asset["name"],
                "hv20_threshold": asset["hv20_threshold"],
                "hv20_warn": max(asset["hv20_threshold"] - 0.03, 0.0),
            }
            for asset in live_assets
        ],
        "live_assets": live_assets,
        "capacity_control": CAPACITY_CONTROL,
        "groups_cap_mult": GROUPS_CAP_MULT,
        "actual_capital": IC_MANUAL_CAPITAL,
        "leverage": LEVERAGE,
        "nominal_capital": IC_MANUAL_CAPITAL * LEVERAGE,
        "pressure_monitor_config": PRESSURE_MONITOR_CONFIG,
        "compute_live_pressure_summary": _compute_live_pressure_summary,
        "compute_live_position_capacity_summary": _compute_live_position_capacity_summary,
        "load_recent_execution_events": _load_recent_execution_events,
        "vix_deleverage_hv": VIX_DELEVERAGE_HV,
        "vix_hard_stop_hv": VIX_HARD_STOP_HV,
        "vix_cooldown_hv": VIX_COOLDOWN_HV,
    }


# ── 常量 ─────────────────────────────────────────────────
LIVE_CTX = _load_live_strategy_context()
ASSETS = LIVE_CTX["assets"]
ACTUAL_CAPITAL = LIVE_CTX["actual_capital"]
NOMINAL_CAPITAL = LIVE_CTX["nominal_capital"]
LEVERAGE = LIVE_CTX["leverage"]
PRESSURE_MONITOR_CONFIG = LIVE_CTX["pressure_monitor_config"]
VIX_DELEVERAGE_HV = LIVE_CTX["vix_deleverage_hv"]
VIX_HARD_STOP_HV = LIVE_CTX["vix_hard_stop_hv"]
VIX_COOLDOWN_HV = LIVE_CTX["vix_cooldown_hv"]
MIN_TRADES_FOR_SUGGESTION = 3  # 至少积累几笔交易才生成建议

ASSET_META = {asset["name"]: asset for asset in ASSETS}
ACCOUNT_DISPLAY_CURRENCY = "USD"
HKD_PER_USD = 7.80


def _hv_threshold(name: str) -> float:
    return ASSET_META.get(name, {}).get("hv20_threshold", 0.25)


def _hv_warn(name: str) -> float:
    return ASSET_META.get(name, {}).get("hv20_warn", 0.22)


def _safe_float(val) -> float:
    """Convert Futu API value to float; treats 'N/A', None, '' as 0.0"""
    try:
        return float(val) if val not in (None, "", "N/A") else 0.0
    except (TypeError, ValueError):
        return 0.0


def _to_display_usd(amount: float, base_currency: str) -> float:
    if (base_currency or "").upper() == "HKD":
        return amount / HKD_PER_USD
    return amount


def _load_ic_codes() -> Optional[set]:
    """读取 IC 持仓代码；文件缺失返回 None，存在但为空返回空集合。"""
    if not IC_CODES_FILE.exists():
        return None
    try:
        data = json.loads(IC_CODES_FILE.read_text(encoding="utf-8"))
        return set(data.get("codes", []))
    except Exception:
        return set()


def _load_open_trade_state() -> Dict:
    """读取 main_ic_us.py 记录的当前开仓元数据。"""
    if not IC_OPEN_TRADE_FILE.exists():
        return {}
    try:
        return json.loads(IC_OPEN_TRADE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _build_strategy_summary(positions: List[Dict], total_pl: float) -> Dict:
    """汇总 IC 策略自身风险，不使用账户级保证金字段。"""
    summary = {
        "active_legs": len(positions),
        "active_groups": 0,
        "max_risk_est": 0.0,
        "risk_ratio_nominal": 0.0,
        "unrealized_pl": total_pl,
        "imbalanced": bool(positions) and (len(positions) % 4 != 0),
        "by_asset": [],
    }

    open_trade_state = _load_open_trade_state()
    if open_trade_state:
        for asset_name, trade in open_trade_state.items():
            groups = int(trade.get("groups", 0) or 0)
            if groups <= 0:
                continue
            sell_put = _safe_float(trade.get("sell_put"))
            buy_put = _safe_float(trade.get("buy_put"))
            sell_call = _safe_float(trade.get("sell_call"))
            buy_call = _safe_float(trade.get("buy_call"))
            net_credit = _safe_float(trade.get("net_credit"))
            wing = max(sell_put - buy_put, buy_call - sell_call, 0.0)
            max_loss = max(wing * 100 * groups - net_credit, 0.0)

            summary["active_groups"] += groups
            summary["max_risk_est"] += max_loss
            summary["by_asset"].append({
                "asset": asset_name,
                "groups": groups,
                "max_risk_est": round(max_loss, 2),
            })
    elif positions:
        grouped: Dict[str, List[Dict]] = {}
        for pos in positions:
            key = f"{pos.get('asset', '?')}|{pos.get('expiry', '?')}"
            grouped.setdefault(key, []).append(pos)

        for key, legs in grouped.items():
            asset_name = key.split("|", 1)[0]
            groups = max(abs(int(leg.get("qty", 0) or 0)) for leg in legs)
            summary["active_groups"] += groups

            sell_put = buy_put = sell_call = buy_call = 0.0
            for leg in legs:
                strike = _safe_float(leg.get("strike"))
                qty = int(leg.get("qty", 0) or 0)
                option_type = leg.get("option_type", "")
                if option_type == "P":
                    if qty < 0:
                        sell_put = strike
                    elif qty > 0:
                        buy_put = strike
                elif option_type == "C":
                    if qty < 0:
                        sell_call = strike
                    elif qty > 0:
                        buy_call = strike

            wing = max(sell_put - buy_put, buy_call - sell_call, 0.0)
            if wing > 0 and groups > 0:
                max_loss = wing * 100 * groups
                summary["max_risk_est"] += max_loss
                summary["by_asset"].append({
                    "asset": asset_name,
                    "groups": groups,
                    "max_risk_est": round(max_loss, 2),
                })

    summary["risk_ratio_nominal"] = (
        summary["max_risk_est"] / NOMINAL_CAPITAL if NOMINAL_CAPITAL else 0.0
    )
    return summary


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
        """获取 IC 策略自身的美股期权持仓。"""
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

        ic_codes = _load_ic_codes()
        if ic_codes is not None:
            if not ic_codes:
                return []
            filtered = pos_data[pos_data["code"].isin(ic_codes)]
        else:
            logger.warning("⚠️ ic_open_codes.json 缺失，监控退化为按 QQQ/IWM/GLD 代码模糊匹配")
            filtered = pos_data[pos_data["code"].str.contains(r"(QQQ|IWM|GLD)", na=False, regex=True)]

        positions = []
        for _, row in filtered.iterrows():
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
                "cost_price": _safe_float(row.get("cost_price")),
                "unrealized_pl": _safe_float(row.get("unrealized_pl")),
                "market_val": _safe_float(row.get("market_val")),
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
        base_currency = str(row.get("currency") or ACCOUNT_DISPLAY_CURRENCY).upper()
        cash_raw = _safe_float(row.get("cash"))
        total_assets_raw = _safe_float(row.get("total_assets"))
        margin_used_raw = _safe_float(row.get("margin_call_margin") or row.get("initial_margin"))
        buying_power_raw = _safe_float(row.get("available_funds"))
        us_cash = _safe_float(row.get("us_cash"))
        usd_net_cash_power = _safe_float(row.get("usd_net_cash_power"))

        if usd_net_cash_power > 0:
            display_cash = usd_net_cash_power
            cash_display_label = "USD净购买力"
        elif us_cash > 0:
            display_cash = us_cash
            cash_display_label = "USD现金"
        else:
            display_cash = _to_display_usd(cash_raw, base_currency)
            cash_display_label = "账户现金折算"

        return {
            "cash": display_cash,
            "total_assets": _to_display_usd(total_assets_raw, base_currency),
            "margin_used": _to_display_usd(margin_used_raw, base_currency),
            "buying_power": _to_display_usd(buying_power_raw, base_currency),
            "display_currency": ACCOUNT_DISPLAY_CURRENCY,
            "base_currency": base_currency,
            "fx_hkd_per_usd": HKD_PER_USD,
            "cash_display_label": cash_display_label,
            "cash_raw": cash_raw,
            "total_assets_raw": total_assets_raw,
            "margin_used_raw": margin_used_raw,
            "buying_power_raw": buying_power_raw,
            "usd_assets": _safe_float(row.get("usd_assets")),
            "usd_net_cash_power": usd_net_cash_power,
            "us_cash": us_cash,
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
                    "建议优先复核：① 节前开仓是否被正确拦截；"
                    "② 开/平仓三轮报价与等待时间是否按设计执行；"
                    "③ 相关腿的盘口流动性是否持续偏弱。"
                ),
            })
        elif avg_slip > -5:  # 滑点极小，说明流动性好
            suggestions.append({
                "level": "INFO",
                "title": f"滑点良好（平均 ${avg_slip:.1f}/笔）",
                "detail": "三标的流动性整体正常，继续按当前实盘参数执行即可。",
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
                    "建议优先复核：① trade_history.csv 的开平仓原因分布；"
                    "② Holiday / VIX / cooldown 逻辑是否按预期触发；"
                    "③ 实际成交滑点是否显著偏离回测假设。"
                ),
            })
        elif win_rate > 0.80:
            suggestions.append({
                "level": "INFO",
                "title": f"胜率优秀（{win_rate*100:.0f}%）",
                "detail": (
                    f"已完成 {len(closed)} 笔，胜率 {win_rate*100:.0f}%，高于回测预期。"
                    "策略运行正常，继续按当前回测验证参数执行，不建议直接改实盘参数。"
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
                if v and v > _hv_threshold(name):
                    block_days[name] += 1

        suggestions = []
        for name, cnt in block_days.items():
            ratio = cnt / total
            if ratio > 0.50:  # 超过一半时间被过滤
                suggestions.append({
                    "level": "INFO",
                    "title": f"{name} HV20 过滤率过高（{ratio*100:.0f}% 的天数超阈值）",
                    "detail": (
                        f"{name} 有 {ratio*100:.0f}% 的观测日 HV20 超过当前阈值 "
                        f"({_hv_threshold(name):.0%})，策略大量空仓。"
                        "建议先复核：富途历史K线是否完整、HV20 计算口径是否与主程序一致、"
                        "以及这些空仓天数是否与回测假设一致；不直接建议改参数。"
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
                        f"{asset} 实盘表现弱于回测，建议对该标的做专项复盘："
                        "检查成交滑点、HV20 过滤、止损触发时点与回测是否一致。"
                        "若需要改参数，必须先在回测中验证。"
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
        capacity = snapshot.get("capacity") or build_capacity_snapshot(
            assets=LIVE_CTX["live_assets"],
            actual_capital=LIVE_CTX["actual_capital"],
            leverage=LEVERAGE,
            groups_cap_mult=LIVE_CTX["groups_cap_mult"],
            capacity_control=LIVE_CTX["capacity_control"],
        )

        # ── 颜色辅助 ────────────────────────────────────
        def pl_color(v):
            return "#2e7d32" if v >= 0 else "#c62828"

        def hv_color(v):
            if v is None:
                return "#888"
            current_name = hv_color.current_name
            if v >= _hv_threshold(current_name):
                return "#c62828"
            if v >= _hv_warn(current_name):
                return "#e65100"
            return "#2e7d32"

        def _expiry_to_date(value):
            if isinstance(value, date):
                return value
            if isinstance(value, str) and value:
                try:
                    return date.fromisoformat(value)
                except ValueError:
                    return None
            return None

        # ── HV20 表格 ────────────────────────────────────
        hv_rows = ""
        for name in ["QQQ", "IWM", "GLD"]:
            v = hv20.get(name)
            hv_color.current_name = name
            v_str = f"{v*100:.1f}%" if v else "N/A"
            status = ("🔴 禁止开仓" if v and v >= _hv_threshold(name)
                      else ("⚠️ 接近阈值" if v and v >= _hv_warn(name)
                            else "✅ 正常"))
            hv_rows += (
                f"<tr><td><b>{name}</b></td>"
                f"<td style='color:{hv_color(v)}'>{v_str}</td>"
                f"<td>{status}（阈值 {_hv_threshold(name):.0%}）</td></tr>"
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
                expiry_date = _expiry_to_date(legs[0].get("expiry"))
                dte = (expiry_date - date.today()).days if expiry_date else "?"
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

        # ── 账户级资金 + 策略级风险 ────────────────────────
        margin_used = account.get("margin_used", 0)
        cash = account.get("cash", 0)
        total_assets = account.get("total_assets", 0)
        display_currency = account.get("display_currency", ACCOUNT_DISPLAY_CURRENCY)
        cash_display_label = account.get("cash_display_label", "现金")
        account_margin_ratio = margin_used / total_assets * 100 if total_assets else 0
        margin_color = "#c62828" if account_margin_ratio > 50 else ("#e65100" if account_margin_ratio > 20 else "#2e7d32")
        currency_note = ""
        if account.get("base_currency") == "HKD" and display_currency == "USD":
            currency_note = (
                f"<p style='font-size:12px;color:#888'>"
                f"富途账户原始资金字段为 HKD，以上已按固定汇率 1 USD = {HKD_PER_USD:.2f} HKD 折算为 USD，"
                f"用于美股 IC 风控口径统一。</p>"
            )
        strategy = snapshot.get("strategy", {})
        execution_events = snapshot.get("execution_events", [])
        live_position_summary = snapshot.get("live_position_summary", [])
        pressure_summary = snapshot.get("pressure_summary", [])
        strategy_groups = int(strategy.get("active_groups", 0) or 0)
        strategy_legs = int(strategy.get("active_legs", 0) or 0)
        strategy_max_risk = _safe_float(strategy.get("max_risk_est"))
        strategy_risk_ratio = _safe_float(strategy.get("risk_ratio_nominal")) * 100
        strategy_imbalanced = bool(strategy.get("imbalanced"))
        capacity_rows = ""
        for asset in capacity["per_asset"]:
            capacity_rows += (
                f"<tr>"
                f"<td><b>{asset['name']}</b></td>"
                f"<td>{asset['estimated_groups']}组 / {asset['estimated_legs']}腿</td>"
                f"<td>≤{asset['batch_limit']}组/批</td>"
                f"<td>${asset['base_capital']:,.0f} ({asset['allocation_pct']:.0%})</td>"
                f"</tr>"
            )
        cap_label = (
            f"E={capacity['cap_mult']}x（自动降档）"
            if capacity["auto_downgraded"]
            else f"F={capacity['cap_mult']}x"
        )
        capacity_notice = ""
        if capacity["auto_downgraded"]:
            capacity_notice += (
                f"<p style='color:#e65100'><b>容量降档</b>: 实际本金达到 "
                f"${capacity['downgrade_threshold']:,.0f}，当前有效动态上限为 {cap_label}。</p>"
            )
        if capacity["needs_review"]:
            capacity_notice += (
                f"<p style='color:#c62828'><b>容量复核</b>: 实际本金达到 "
                f"${capacity['review_threshold']:,.0f}，建议优先升级执行架构后再继续放大。</p>"
            )
        live_position_html = ""
        if live_position_summary:
            rows = ""
            for item in live_position_summary:
                status = "✅ 可再开" if item.get("can_add") else "⛔ 不再开"
                color = "#2e7d32" if item.get("can_add") else "#c62828"
                rows += (
                    f"<tr>"
                    f"<td><b>{item.get('name', '-')}</b></td>"
                    f"<td>{item.get('existing_groups', 0)}组 / {item.get('existing_legs', 0)}腿</td>"
                    f"<td>{item.get('allowed_groups', 0)}组</td>"
                    f"<td style='color:{color}'>{status}</td>"
                    f"<td>{item.get('blocked_reason', '') or '-'}</td>"
                    f"</tr>"
                )
            live_position_html = f"""
<h3>🧮 实时持仓 vs 当前允许上限</h3>
<table border='1' cellpadding='6' style='border-collapse:collapse;width:100%'>
<tr style='background:#f2f2f2'><th>标的</th><th>真实持仓</th><th>当前允许上限</th><th>今晚是否可再开</th><th>备注</th></tr>
{rows}
</table>
"""
        pressure_html = ""
        if pressure_summary:
            rows = ""
            for item in pressure_summary:
                pressure_pl_color = "#2e7d32" if _safe_float(item.get("unrealized_pl")) >= 0 else "#c62828"
                rows += (
                    f"<tr>"
                    f"<td><b>{item.get('name', '-')}</b></td>"
                    f"<td>${_safe_float(item.get('current_price')):.2f}</td>"
                    f"<td>{item.get('groups', 0)}组 / {item.get('pressure_side', '-')}</td>"
                    f"<td>{item.get('dist_short_str', '-')}</td>"
                    f"<td>{item.get('dist_be_str', '-')}</td>"
                    f"<td>{item.get('dist_stop_str', '-')}</td>"
                    f"<td style='color:{pressure_pl_color}'>${_safe_float(item.get('unrealized_pl')):+,.0f} / {item.get('loss_ratio_str', '-')}</td>"
                    f"<td style='color:{item.get('level_color', '#555')}'><b>{item.get('level_label', '-')}</b></td>"
                    f"<td>{item.get('suggestion', '-')}</td>"
                    f"</tr>"
                )
            pressure_html = f"""
<h3>🚦 持仓压力监控</h3>
<table border='1' cellpadding='6' style='border-collapse:collapse;width:100%'>
<tr style='background:#f2f2f2'><th>标的</th><th>现价</th><th>持仓/受压侧</th><th>距短腿</th><th>距盈亏平衡</th><th>距价格止损</th><th>浮盈亏 / 最大亏损</th><th>等级</th><th>建议</th></tr>
{rows}
</table>
<p style='font-size:12px;color:#888'>分级口径：距 short strike ≤{PRESSURE_MONITOR_CONFIG['short_warn_pct']:.0%} 黄灯、≤{PRESSURE_MONITOR_CONFIG['short_alert_pct']:.1%} 橙灯；距价格止损 ≤{PRESSURE_MONITOR_CONFIG['stop_critical_pct']:.1%} 或浮亏达最大亏损 {PRESSURE_MONITOR_CONFIG['loss_critical_ratio']:.0%} 进入红灯。</p>
"""
        execution_html = ""
        if execution_events:
            event_rows = ""
            for event in reversed(execution_events):
                color = "#c62828" if event.get("level") == "CRITICAL" else "#e65100" if event.get("level") == "WARNING" else "#555555"
                event_rows += (
                    f"<tr>"
                    f"<td>{str(event.get('ts', '')).replace('T', ' ')}</td>"
                    f"<td><b>{event.get('asset', '-')}</b></td>"
                    f"<td style='color:{color}'>{event.get('message', '')}</td>"
                    f"<td>{event.get('details', '')}</td>"
                    f"</tr>"
                )
            execution_html = f"""
<h3>🛠️ 最近执行事件</h3>
<table border='1' cellpadding='6' style='border-collapse:collapse;width:100%'>
<tr style='background:#f2f2f2'><th>时间</th><th>标的</th><th>事件</th><th>详情</th></tr>
{event_rows}
</table>
"""

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

<h3>📈 HV20 波动率状态（三层风控口径）</h3>
<table border='1' cellpadding='6' style='border-collapse:collapse'>
<tr style='background:#f2f2f2'><th>标的</th><th>HV20</th><th>状态</th></tr>
{hv_rows}
</table>
<p style='font-size:12px;color:#888'>开仓阈值：QQQ/IWM 25%，GLD 18%（超过即禁止新开仓） ｜ 降杠杆阈值：22%（仅在允许开仓时 max_groups 减半） ｜ 硬止损阈值：39% ｜ 恢复阈值：28%</p>

<h3>📋 当前持仓</h3>
<table border='1' cellpadding='6' style='border-collapse:collapse;width:100%'>
<tr style='background:#f2f2f2'><th>代码</th><th>类型/行权价</th><th>数量/成本</th><th>浮盈亏</th></tr>
{pos_rows}
</table>
<p><b>总未实现盈亏：</b>
<span style='color:{pl_color(total_pl)};font-size:18px'><b>${total_pl:+.0f}</b></span></p>

<h3>💰 资金状态</h3>
<table border='1' cellpadding='6' style='border-collapse:collapse'>
<tr><td>总资产</td><td>${total_assets:,.0f} {display_currency}</td></tr>
<tr><td>{cash_display_label}</td><td>${cash:,.0f} {display_currency}</td></tr>
<tr><td>账户级融资占用</td>
    <td style='color:{margin_color}'>${margin_used:,.0f} {display_currency}
    （占账户总资产 {account_margin_ratio:.0f}%；该字段可能包含非 IC 仓位）</td></tr>
<tr><td>IC策略当前腿数</td><td>{strategy_legs} 腿 / {strategy_groups} 组</td></tr>
<tr><td>IC策略结构完整性</td><td style='color:{"#c62828" if strategy_imbalanced else "#2e7d32"}'>{'🚨 存在残腿/不平衡头寸' if strategy_imbalanced else '✅ 结构完整'}</td></tr>
<tr><td>IC策略理论最大风险</td><td>${strategy_max_risk:,.0f} USD（占名义资金 {strategy_risk_ratio:.0f}%）</td></tr>
<tr><td>策略分配</td><td>${ACTUAL_CAPITAL:,.0f} USD 实际本金 / ${NOMINAL_CAPITAL:,.0f} USD 名义资金（{LEVERAGE:.1f}x杠杆）</td></tr>
<tr><td>容量档位</td><td>{capacity['band_label']} / 成交难度{capacity['difficulty']}</td></tr>
<tr><td>动态上限</td><td>{cap_label}</td></tr>
<tr><td>预计组数</td><td>{capacity['total_groups']}组 / {capacity['total_legs']}腿</td></tr>
</table>
{currency_note}

<h3>📦 当前容量与预计组数</h3>
<table border='1' cellpadding='6' style='border-collapse:collapse;width:100%'>
<tr style='background:#f2f2f2'><th>标的</th><th>预计组数</th><th>单批建议</th><th>基准分配</th></tr>
{capacity_rows}
</table>
{capacity_notice}
{live_position_html}
{pressure_html}
{execution_html}

{suggestion_html}

<p style='color:#aaa;font-size:11px;margin-top:24px'>
自动发送 · 铁鹰量化监控系统 · {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
</p>
</div>
"""
        sent = self.notifier._send(subject, body)
        if sent:
            logger.info(f"📧 日报已发送: {subject}")
        else:
            logger.warning(f"📧 日报未发送: {subject}")

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
                status = "🔴 超阈值" if v >= _hv_threshold(name) else ("⚠️ 接近" if v >= _hv_warn(name) else "✅")
                logger.info(f"   {name}: {v*100:.1f}% {status}")

        # ── Step 2: 获取持仓 ─────────────────────────
        logger.info("📋 查询持仓...")
        positions = md.get_positions()
        total_pl = sum(p["unrealized_pl"] for p in positions)
        logger.info(f"   共 {len(positions)} 腿，总浮盈亏 ${total_pl:+.0f}")

        # ── Step 3: 账户资金 ─────────────────────────
        logger.info("💰 查询账户资金...")
        account = md.get_account_info()
        account_margin_pct = account.get("margin_used", 0) / account.get("total_assets", 0) * 100 if account.get("total_assets", 0) else 0
        logger.info(
            f"   {account.get('cash_display_label', '现金')}: "
            f"${account.get('cash', 0):,.0f} "
            f"{account.get('display_currency', ACCOUNT_DISPLAY_CURRENCY)}"
        )
        logger.info(
            f"   账户级融资占用: ${account.get('margin_used', 0):,.0f} "
            f"{account.get('display_currency', ACCOUNT_DISPLAY_CURRENCY)} "
            f"({account_margin_pct:.0f}% of total_assets)"
        )
        if account.get("base_currency") == "HKD":
            logger.info(
                f"   账户资金口径: 富途原始 HKD，监控已按 1 USD = {HKD_PER_USD:.2f} HKD 折算"
            )

        # ── Step 3.5: IC策略风险汇总 ───────────────────
        strategy = _build_strategy_summary(positions, total_pl)
        logger.info(
            f"   IC策略风险: {strategy['active_legs']}腿 / {strategy['active_groups']}组 / "
            f"理论最大风险 ${strategy['max_risk_est']:,.0f} "
            f"({strategy['risk_ratio_nominal']*100:.0f}% of nominal)"
        )
        capacity = build_capacity_snapshot(
            assets=LIVE_CTX["live_assets"],
            actual_capital=LIVE_CTX["actual_capital"],
            leverage=LEVERAGE,
            groups_cap_mult=LIVE_CTX["groups_cap_mult"],
            capacity_control=LIVE_CTX["capacity_control"],
        )
        logger.info(
            f"   容量档位: {capacity['band_label']} / 动态上限 "
            f"{'E' if capacity['auto_downgraded'] else 'F'}={capacity['cap_mult']}x / "
            f"预计 {capacity['total_groups']}组 {capacity['total_legs']}腿"
        )
        logger.info(
            "   预计组数: "
            + ", ".join(
                f"{asset['name']} {asset['estimated_groups']}组(单批≤{asset['batch_limit']})"
                for asset in capacity["per_asset"]
            )
        )
        execution_events = LIVE_CTX["load_recent_execution_events"](hours=36, limit=12)
        if execution_events:
            logger.info(f"   最近执行事件: {len(execution_events)} 条")
            for event in execution_events[-3:]:
                logger.info(
                    f"   [{event.get('level', 'INFO')}] {event.get('asset', '-')} "
                    f"{event.get('message', '')}"
                )
        live_position_summary = LIVE_CTX["compute_live_position_capacity_summary"](dry_run=False)
        pressure_summary = LIVE_CTX["compute_live_pressure_summary"](dry_run=False)
        logger.info(
            "   实时持仓/上限: "
            + ", ".join(
                f"{item['name']} {item['existing_groups']}/{item['allowed_groups']}组"
                for item in live_position_summary
            )
        )
        if pressure_summary:
            logger.info(
                "   压力分级: "
                + ", ".join(
                    f"{item['name']} {item['level_label']} "
                    f"(距短腿 {item['dist_short_str']}, 浮亏/MaxLoss {item['loss_ratio_str']})"
                    for item in pressure_summary
                )
            )

        # ── Step 4: 保存快照 ─────────────────────────
        snapshot = {
            "hv20": hv20_map,
            "positions": [
                {k: str(v) if isinstance(v, date) else v for k, v in p.items()}
                for p in positions
            ],
            "total_unrealized_pl": total_pl,
            "account": account,
            "strategy": strategy,
            "capacity": capacity,
            "execution_events": execution_events,
            "live_position_summary": live_position_summary,
            "pressure_summary": pressure_summary,
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
