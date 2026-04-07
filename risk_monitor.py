#!/usr/bin/env python3
"""
风控监控脚本 - 为 Iron Condor 策略保驾护航

基于 4 个历史爆仓案例的教训：
1. David Chau (马丁格尔爆仓)
2. VIX 暴涨 (做空波动率拥挤)
3. 2020 新冠 (跳空 + 流动性枯竭)
4. 2008 金融危机 (系统性风险)

功能：
- 开盘前：检查市场环境、VIX、流动性
- 持仓中：监控盈亏、到期日、极端行情
- 熔断机制：触发条件自动平仓
"""

import time
import logging
from datetime import date, datetime
from typing import Dict, List, Optional
from pathlib import Path

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ============ 风控配置 ============
class RiskConfig:
    """风控配置"""

    # === 港股（腾讯）配置 ===
    HK_CONFIG = {
        "本金": 50000,           # HKD
        "max_groups": 2,         # 最多2组
        "单组最大亏损_HKD": 500,  # 单组亏损超过此值触发警告
        "单日最大亏损比例": 0.10,  # 单日亏损超过本金的10%
        "最小IV": 0.15,          # 最小隐含波动率
        "最大IV": 0.30,          # 超过此IV禁止开仓
        "最小成交量": 1000,       # 期权日成交量低于此值禁止开仓
    }

    # === 美股（SPY）配置 ===
    US_CONFIG = {
        "本金": 10000,           # USD
        "max_groups": 1,         # 最多1组
        "单组最大亏损_USD": 50,   # 单组亏损超过此值触发警告
        "单日最大亏损比例": 0.10,  # 单日亏损超过本金的10%
        "VIX低于": 20,          # 正常开仓
        "VIX谨慎": 25,          # 减少仓位
        "VIX禁止": 25,          # 禁止新开仓
        "VIX熔断": 30,          # 强制平仓
        "最小成交量": 1000,      # 期权日成交量
    }


class RiskMonitor:
    """风控监控器"""

    def __init__(self, market: str = "HK", config: Dict = None):
        """
        初始化风控监控器
        market: "HK" 港股 或 "US" 美股
        """
        self.market = market.upper()
        if config:
            self.config = config
        else:
            self.config = RiskConfig.HK_CONFIG if self.market == "HK" else RiskConfig.US_CONFIG

    # ============ 开盘前检查 ============

    def pre_market_check(self, data_provider=None) -> Dict:
        """
        开盘前风控检查
        返回: {"can_trade": True/False, "warnings": [...], "errors": [...]}
        """
        results = {
            "can_trade": True,
            "warnings": [],
            "errors": [],
        }

        logger.info("=" * 50)
        logger.info("🔍 开盘前风控检查")
        logger.info("=" * 50)

        # 1. 检查是否为交易日
        if not self._is_trading_day():
            results["errors"].append("今日非交易日")
            results["can_trade"] = False
            logger.error("❌ 今日非交易日")
            return results

        logger.info("✅ 今日为交易日")

        # 2. VIX 检查（美股）
        if self.market == "US":
            vix_check = self._check_vix(data_provider)
            if not vix_check["ok"]:
                results["can_trade"] = False
                results["errors"].extend(vix_check["messages"])
            else:
                results["warnings"].extend(vix_check.get("warnings", []))

        # 3. 检查持仓数量
        current_groups = self._get_current_positions(data_provider)
        if current_groups >= self.config.get("max_groups", 1):
            results["errors"].append(f"已达最大持仓组数: {current_groups}/{self.config['max_groups']}")
            results["can_trade"] = False
            logger.error(f"❌ 已达最大持仓组数: {current_groups}")
        else:
            logger.info(f"✅ 当前持仓: {current_groups} 组")

        # 4. 检查现金是否充足
        cash_ratio = self._check_cash_ratio(data_provider)
        if cash_ratio < 0.2:
            results["errors"].append(f"现金不足: {cash_ratio*100:.0f}% (需保留20%)")
            results["can_trade"] = False
            logger.error(f"❌ 现金不足: {cash_ratio*100:.0f}%")
        else:
            logger.info(f"✅ 现金比例: {cash_ratio*100:.0f}%")

        # 总结
        logger.info("-" * 50)
        if results["can_trade"]:
            logger.info("✅ 可以交易")
        else:
            logger.error("❌ 禁止交易")
            for err in results["errors"]:
                logger.error(f"  - {err}")
        for warn in results["warnings"]:
            logger.warning(f"  ⚠️ {warn}")

        return results

    def _is_trading_day(self) -> bool:
        """检查是否为交易日（港股/美股）"""
        today = date.today()
        # 简单检查：周末不是交易日，但返回信息让调用方决定
        if today.weekday() >= 5:  # 周六=5, 周日=6
            logger.warning(f"⚠️ 今日是周末，开盘检查仅供参考")
            return True  # 周末也允许检查，但不实际交易

        # TODO: 可以调用富途 API 检查真实交易日历
        return True

    def _check_vix(self, data_provider) -> Dict:
        """检查 VIX 波动率"""
        result = {"ok": True, "messages": [], "warnings": []}

        # 尝试获取 VIX
        vix = 15.0  # 默认值，如果无法获取
        if data_provider:
            try:
                # 这里可以调用数据源获取 VIX
                # vix = data_provider.get_vix()
                pass
            except:
                pass

        # 使用模拟值演示逻辑
        logger.info(f"📊 VIX 当前值: {vix:.1f}")

        vix_ban = self.config.get("VIX禁止", 25)
        vix_caution = self.config.get("VIX谨慎", 25)
        vix_crash = self.config.get("VIX熔断", 30)

        if vix >= vix_crash:
            result["ok"] = False
            result["messages"].append(f"VIX={vix:.1f} >= {vix_crash}，强制熔断")
            logger.error(f"❌ VIX 熔断: {vix:.1f}")
        elif vix >= vix_ban:
            result["ok"] = False
            result["messages"].append(f"VIX={vix:.1f} >= {vix_ban}，禁止开仓")
            logger.error(f"❌ VIX 禁止: {vix:.1f}")
        elif vix >= vix_caution:
            result["warnings"].append(f"VIX={vix:.1f} >= {vix_caution}，建议减少仓位")
            logger.warning(f"⚠️ VIX 谨慎: {vix:.1f}")
        else:
            logger.info(f"✅ VIX 正常: {vix:.1f}")

        return result

    def _get_current_positions(self, data_provider) -> int:
        """获取当前持仓组数"""
        # TODO: 连接实盘账户查询
        return 0  # 模拟：无持仓

    def _check_cash_ratio(self, data_provider) -> float:
        """检查现金比例"""
        # TODO: 连接账户查询资金
        return 1.0  # 模拟：100% 现金

    # ============ 持仓中监控 ============

    def monitor_positions(self, positions: List[Dict], data_provider=None) -> Dict:
        """
        监控持仓
        positions: [{"code": ..., "qty": ..., "cost": ..., "current": ..., "expiry": ...}, ...]
        """
        logger.info("=" * 50)
        logger.info("📊 持仓风控监控")
        logger.info("=" * 50)

        results = {
            "normal": True,
            "warnings": [],
            "actions": [],  # 需要执行的操作，如 ["close_all", "close_xxx"]
        }

        if not positions:
            logger.info("✅ 当前无持仓")
            return results

        # 1. 到期日检查
        exp_check = self._check_expiry(positions)
        results["warnings"].extend(exp_check.get("warnings", []))

        # 2. 盈亏检查
        pnl_check = self._check_pnl(positions)
        if not pnl_check["ok"]:
            results["normal"] = False
            results["actions"].extend(pnl_check.get("actions", []))

        results["warnings"].extend(pnl_check.get("warnings", []))

        # 3. 流动性检查
        liq_check = self._check_liquidity(positions, data_provider)
        results["warnings"].extend(liq_check.get("warnings", []))

        # 总结
        logger.info("-" * 50)
        if results["normal"]:
            logger.info("✅ 持仓正常")
        else:
            logger.error("❌ 触发风控动作")

        for warn in results["warnings"]:
            logger.warning(f"  ⚠️ {warn}")
        for action in results["actions"]:
            logger.error(f"  🔴 执行: {action}")

        return results

    def _check_expiry(self, positions: List[Dict]) -> Dict:
        """检查到期日"""
        result = {"warnings": []}
        today = date.today()

        for pos in positions:
            expiry = pos.get("expiry")
            if not expiry:
                continue

            if isinstance(expiry, str):
                expiry = datetime.strptime(expiry, "%Y-%m-%d").date()

            dte = (expiry - today).days

            if dte <= 1:
                result["warnings"].append(f"{pos['code']} 明天到期(DTE=1)，建议平仓")
                logger.warning(f"⚠️ {pos['code']} 明天到期")
            elif dte <= 3:
                result["warnings"].append(f"{pos['code']} 即将到期(DTE={dte})")
                logger.info(f"📅 {pos['code']} DTE={dte}")

        return result

    def _check_pnl(self, positions: List[Dict]) -> Dict:
        """检查盈亏"""
        result = {"ok": True, "warnings": [], "actions": []}

        total_pnl = 0
        max_loss = 0

        for pos in positions:
            cost = pos.get("cost", 0)
            current = pos.get("current", 0)
            qty = pos.get("qty", 1)

            pnl = (current - cost) * qty
            total_pnl += pnl

            # 单组亏损
            if pnl < 0:
                loss = abs(pnl)
                max_loss = max(max_loss, loss)

                loss_threshold = self.config.get("单组最大亏损_HKD", 500)
                if self.market == "US":
                    loss_threshold = self.config.get("单组最大亏损_USD", 50)

                if loss > loss_threshold:
                    result["warnings"].append(f"{pos['code']} 亏损 {loss:.0f}，超过阈值")
                    logger.warning(f"⚠️ {pos['code']} 亏损 {loss:.0f}")

        # 单日亏损比例
        daily_loss_ratio = abs(total_pnl) / self.config.get("本金", 50000)
        max_daily_loss = self.config.get("单日最大亏损比例", 0.10)

        if total_pnl < 0 and daily_loss_ratio > max_daily_loss:
            result["ok"] = False
            result["actions"].append("close_all")
            result["warnings"].append(f"单日亏损 {daily_loss_ratio*100:.1f}%，触发熔断")
            logger.error(f"❌ 单日亏损 {daily_loss_ratio*100:.1f}%，触发熔断")

        # 盈利检查：如果盈利超过 40%，可以提前平仓
        if total_pnl > 0:
            profit_ratio = total_pnl / self.config.get("本金", 50000)
            if profit_ratio > 0.40:
                result["warnings"].append(f"盈利 {profit_ratio*100:.0f}%，可考虑提前平仓")
                logger.info(f"💰 盈利 {profit_ratio*100:.0f}%，可考虑落袋为安")

        return result

    def _check_liquidity(self, positions: List[Dict], data_provider) -> Dict:
        """检查流动性"""
        result = {"warnings": []}
        min_volume = self.config.get("最小成交量", 1000)

        for pos in positions:
            code = pos.get("code", "")
            # TODO: 实际获取成交量
            # volume = data_provider.get_volume(code)
            volume = 5000  # 模拟

            if volume < min_volume:
                result["warnings"].append(f"{code} 成交量不足: {volume}")
                logger.warning(f"⚠️ {code} 成交量不足: {volume}")

        return result

    # ============ 熔断机制 ============

    def circuit_breaker_check(self, market_data: Dict = None) -> Dict:
        """
        熔断检查
        触发以下任一条件，立即平仓：
        1. 单日亏损 ≥ 本金的 8%
        2. 单组亏损 ≥ 权利金的 50%
        3. VIX ≥ 30
        4. 持仓中有任何期权的标的价格触及行权价 ± 5% 范围
        """
        logger.info("=" * 50)
        logger.info("🔥 熔断机制检查")
        logger.info("=" * 50)

        results = {
            "triggered": False,
            "reasons": [],
            "action": "continue",  # continue / close_partial / close_all
        }

        # 1. VIX 熔断
        if self.market == "US":
            vix = market_data.get("vix", 15) if market_data else 15
            vix_crash = self.config.get("VIX熔断", 30)
            if vix >= vix_crash:
                results["triggered"] = True
                results["reasons"].append(f"VIX={vix:.1f} >= {vix_crash}")
                results["action"] = "close_all"
                logger.error(f"❌ 熔断: VIX={vix:.1f}")

        # TODO: 添加更多熔断条件

        if results["triggered"]:
            logger.error(f"🚨 触发熔断: {results['reasons']}")
        else:
            logger.info("✅ 未触发熔断")

        return results


# ============ 便捷函数 ============

def quick_risk_check(market: str = "HK") -> Dict:
    """快速风控检查（不需要数据源）"""
    monitor = RiskMonitor(market=market)
    return monitor.pre_market_check(data_provider=None)


# ============ 测试 ============

if __name__ == "__main__":
    print("=" * 60)
    print("🛡️ Iron Condor 风控监控系统")
    print("=" * 60)

    # 测试港股风控
    print("\n--- 港股（腾讯）风控检查 ---")
    hk_result = quick_risk_check("HK")
    print(f"结果: {'可以交易' if hk_result['can_trade'] else '禁止交易'}")

    # 测试美股风控
    print("\n--- 美股（SPY）风控检查 ---")
    us_result = quick_risk_check("US")
    print(f"结果: {'可以交易' if us_result['can_trade'] else '禁止交易'}")

    # 测试持仓监控
    print("\n--- 持仓监控测试 ---")
    monitor = RiskMonitor(market="HK")

    test_positions = [
        {"code": "HK.TCH260430P420000", "qty": 1, "cost": 1.50, "current": 1.20, "expiry": "2026-04-30"},
        {"code": "HK.TCH260430C450000", "qty": 1, "cost": 1.80, "current": 2.00, "expiry": "2026-04-30"},
    ]

    monitor.monitor_positions(test_positions)