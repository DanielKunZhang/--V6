#!/usr/bin/env python3
"""
价值投资期权策略生成器
基于 Futu API 的 Sell Put 和 Covered Call 策略扫描系统

系统设计理念：
1. Sell Put（"接飞刀"赚权利金）：在股价进入击球区但尚未买入时，卖出虚值 Put
2. Covered Call（"持币待沽"增强收益）：在持有优质公司股票后，在内在价值上方卖出虚值 Call

作者：OpenClaw 根据用户提供的系统设计文档生成
日期：2026-04-06
"""

import sys
import yaml
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import time
import csv
import warnings
from typing import Dict, List, Optional, Tuple, Any

# 第三方库
try:
    from futu import (
        OpenQuoteContext, RET_OK, KLType, OptionType,
        SecurityType, Market
    )
    from prettytable import PrettyTable
except ImportError as e:
    print(f"❌ 缺少必要的依赖库: {e}")
    print("请运行: pip install futu-api prettytable pyyaml pandas numpy")
    sys.exit(1)

# 忽略警告
warnings.filterwarnings('ignore')

class ValueInvestingOptionWriter:
    """价值投资期权策略生成器主类"""
    
    def __init__(self, config_path: str = 'config_option_writer.yaml', cmdline_args: Dict = None):
        self.config = self._load_config(config_path)
        self.cmdline_args = cmdline_args or {}
        self.quote_ctx = None
        self.stock_price_cache = {}
        self.historical_vol_cache = {}
        self.sell_put_results = []
        self.covered_call_results = []
    
    def _load_config(self, config_path: str) -> Dict:
        """加载YAML配置文件"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            print(f"✅ 配置文件加载成功: {config_path}")
            return config
        except FileNotFoundError:
            print(f"❌ 配置文件不存在: {config_path}")
            sys.exit(1)
        except yaml.YAMLError as e:
            print(f"❌ 配置文件格式错误: {e}")
            sys.exit(1)
    
    def _normalize_code(self, code: str) -> str:
        """将配置文件格式的代码转换为 Futu API 格式"""
        if '.' not in code:
            return code
        
        # 检查是否已经是 Futu 格式（市场.代码）
        futu_markets = ['US', 'HK', 'SH', 'SZ', 'SG']
        parts = code.split('.')
        if len(parts) == 2:
            market, symbol = parts[0].upper(), parts[1]
            # 如果市场是 Futu 已知市场，说明已经是正确格式
            if market in futu_markets:
                # 已经是 Futu 格式，直接返回
                if market == 'HK' and symbol.isdigit():
                    symbol = symbol.zfill(5)
                return f"{market}.{symbol}"
            else:
                # 假设是 symbol.market 格式，需要转换
                symbol, market_suffix = parts[0], parts[1].upper()
                if market_suffix == 'US':
                    return f"US.{symbol}"
                elif market_suffix == 'HK':
                    if symbol.isdigit():
                        symbol = symbol.zfill(5)
                    return f"HK.{symbol}"
                # 其他市场
                return f"{market_suffix}.{symbol}"
        return code

    def connect_api(self) -> bool:
        """连接 Futu API"""
        try:
            host = self.config['futu_api']['host']
            port = self.config['futu_api']['port']
            
            print(f"🔌 连接富途 OpenD ({host}:{port})...")
            self.quote_ctx = OpenQuoteContext(host=host, port=port)
            
            # 验证连接是否成功
            ret, data = self.quote_ctx.get_global_state()
            if ret != RET_OK:
                print(f"❌ 连接失败: ret={ret}")
                return False
            
            print("✅ 富途 API 连接成功")
            return True
            
        except Exception as e:
            print(f"❌ 连接异常: {e}")
            return False
    
    def disconnect_api(self):
        """断开 API 连接"""
        if self.quote_ctx:
            self.quote_ctx.close()
            print("🔌 已断开富途 API 连接")
    
    def get_stock_price(self, code: str) -> Optional[float]:
        """获取股票最新价格"""
        normalized_code = self._normalize_code(code)
        if normalized_code in self.stock_price_cache:
            return self.stock_price_cache[normalized_code]
        
        try:
            ret, data = self.quote_ctx.get_market_snapshot([normalized_code])
            if ret == RET_OK and not data.empty:
                price = float(data.iloc[0]['last_price'])
                self.stock_price_cache[normalized_code] = price
                return price
        except Exception as e:
            print(f"❌ 获取 {code} 价格异常: {e}")
        return None
    
    def get_option_chain(self, code: str, option_type: str, expiry_days_min: int, expiry_days_max: int) -> Optional[pd.DataFrame]:
        """获取期权链数据"""
        normalized_code = self._normalize_code(code)
        try:
            today = datetime.now().date()
            ret, expiry_data = self.quote_ctx.get_option_expiration_date(normalized_code)
            if ret != RET_OK or expiry_data.empty:
                print(f"⚠️ 无法获取 {code} 期权到期日")
                return None
            
            valid_expiries = []
            for _, row in expiry_data.iterrows():
                try:
                    # 注意：列名是 'strike_time'，不是 'expiry_date'
                    expiry_date_str = row['strike_time']
                    if pd.isna(expiry_date_str) or expiry_date_str is None:
                        continue
                    
                    if isinstance(expiry_date_str, str):
                        if expiry_date_str == '' or expiry_date_str == 'N/A':
                            continue
                        expiry_date = datetime.strptime(expiry_date_str, '%Y-%m-%d').date()
                    else:
                        # 如果已经是日期类型
                        expiry_date = expiry_date_str
                    
                    days_to_expiry = (expiry_date - today).days
                    if expiry_days_min <= days_to_expiry <= expiry_days_max:
                        valid_expiries.append(expiry_date)
                except (ValueError, TypeError, AttributeError) as e:
                    # 跳过无效的日期数据
                    continue
            
            if not valid_expiries:
                print(f"⚠️ {code} 没有符合到期日范围 ({expiry_days_min}-{expiry_days_max}天) 的期权")
                return None
            
            option_type_enum = OptionType.PUT if option_type == 'PUT' else OptionType.CALL
            all_chains = []
            
            for expiry in valid_expiries:
                expiry_str = expiry.strftime('%Y-%m-%d')
                ret, chain_data = self.quote_ctx.get_option_chain(
                    normalized_code, 
                    option_type=option_type_enum,
                    start=expiry_str,
                    end=expiry_str
                )
                if ret == RET_OK and not chain_data.empty:
                    chain_data['expiry_date'] = expiry  # 保持为 date 对象
                    chain_data['days_to_expiry'] = (expiry - today).days
                    all_chains.append(chain_data)
            
            if not all_chains:
                print(f"⚠️ {code} 获取到期权链但数据为空")
                return None
            
            combined_chain = pd.concat(all_chains, ignore_index=True)
            print(f"✅ {code} 获取到 {len(combined_chain)} 个 {option_type} 期权合约")
            return combined_chain
            
        except Exception as e:
            print(f"❌ 获取 {code} 期权链异常: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def get_option_market_data(self, codes: List[str]) -> Dict[str, Dict]:
        """批量获取期权市场数据"""
        if not codes:
            return {}
        
        try:
            self.quote_ctx.subscribe(codes, ['QUOTE'])
            time.sleep(0.5)
            
            market_data = {}
            for code in codes:
                # 获取期权报价数据
                ret, quote_data = self.quote_ctx.get_stock_quote([code])
                if ret == RET_OK and not quote_data.empty:
                    # 期权报价数据中没有 bid/ask，使用 last_price 作为参考价
                    last_price = float(quote_data.iloc[0]['last_price'])
                    premium = float(quote_data.iloc[0]['premium']) if 'premium' in quote_data.columns else last_price
                    
                    # 希腊值和市场数据
                    iv = float(quote_data.iloc[0]['implied_volatility']) if 'implied_volatility' in quote_data.columns else 0.0
                    delta = float(quote_data.iloc[0]['delta']) if 'delta' in quote_data.columns else 0.0
                    volume = int(quote_data.iloc[0]['volume']) if 'volume' in quote_data.columns else 0
                    open_interest = int(quote_data.iloc[0]['open_interest']) if 'open_interest' in quote_data.columns else 0
                else:
                    last_price = premium = 0.0
                    iv = delta = 0.0
                    volume = open_interest = 0
                
                # 对于期权，我们使用 last_price/premium 作为中间价
                # 如果没有买卖盘数据，使用 last_price 作为参考
                mid_price = premium if premium > 0 else last_price
                
                market_data[code] = {
                    'bid': mid_price,  # 使用中间价作为 bid 的近似值
                    'ask': mid_price,  # 使用中间价作为 ask 的近似值
                    'mid': mid_price,
                    'iv': iv,
                    'delta': delta,
                    'volume': volume,
                    'open_interest': open_interest,
                }
            
            return market_data
            
        except Exception as e:
            print(f"❌ 获取期权市场数据异常: {e}")
            import traceback
            traceback.print_exc()
            return {}
    
    def calculate_historical_volatility(self, code: str, window_days: int = 30) -> Optional[float]:
        """计算历史波动率（HV）"""
        normalized_code = self._normalize_code(code)
        cache_key = f"{normalized_code}_{window_days}"
        if cache_key in self.historical_vol_cache:
            return self.historical_vol_cache[cache_key]
        
        try:
            end_date = datetime.now().date()
            start_date = end_date - timedelta(days=window_days * 2)
            
            ret, data = self.quote_ctx.request_history_kline(
                code=normalized_code,
                start=start_date.strftime('%Y-%m-%d'),
                end=end_date.strftime('%Y-%m-%d'),
                ktype=KLType.K_DAY,
                max_count=window_days * 2
            )
            
            if ret != RET_OK or data.empty or len(data) < window_days:
                return None
            
            closes = data['close'].astype(float)
            log_returns = np.log(closes / closes.shift(1)).dropna()
            
            if len(log_returns) < window_days:
                return None
            
            hv = log_returns.tail(window_days).std() * np.sqrt(252)
            hv_value = float(hv)
            
            self.historical_vol_cache[cache_key] = hv_value
            return hv_value
            
        except Exception as e:
            print(f"❌ 计算 {code} 历史波动率异常: {e}")
            return None
    
    def calculate_iv_percentile(self, code: str, current_iv: float) -> Optional[float]:
        """计算 IV 历史百分位（简化版）"""
        try:
            hv = self.calculate_historical_volatility(code, 30)
            if hv is None:
                return None
            
            # 简化：使用HV作为基准
            hv_series = pd.Series([hv * 0.8, hv * 1.0, hv * 1.2])
            percentile = (hv_series <= current_iv).mean()
            return float(percentile)
            
        except Exception as e:
            print(f"❌ 计算 {code} IV 百分位异常: {e}")
            return None
    
    def calculate_sell_put_metrics(self, option_row: pd.Series, stock_price: float, buy_zone: Tuple[float, float]) -> Dict[str, Any]:
        """计算 Sell Put 策略的关键指标"""
        try:
            strike_price = float(option_row['strike_price'])
            bid_price = float(option_row.get('bid', 0))
            days_to_expiry = int(option_row['days_to_expiry'])
            delta = float(option_row.get('delta', 0))
            iv = float(option_row.get('iv', 0))
            
            premium = bid_price if bid_price > 0 else float(option_row.get('mid', 0))
            capital_at_risk = strike_price - premium
            buy_zone_low, buy_zone_high = buy_zone
            
            # 安全边际
            safety_margin = (buy_zone_low - capital_at_risk) / buy_zone_low * 100 if capital_at_risk < buy_zone_low else 0
            
            # 年化收益率
            if days_to_expiry > 0 and capital_at_risk > 0:
                holding_period_return = premium / capital_at_risk
                annual_yield = holding_period_return * (365 / days_to_expiry) * 100
            else:
                annual_yield = 0
            
            # 保证金估算
            otm_amount = max(0, strike_price - stock_price)
            margin_1 = premium + 0.2 * stock_price - otm_amount
            margin_2 = premium + 0.1 * stock_price
            margin_required = max(margin_1, margin_2)
            
            if margin_required > 0:
                margin_yield = premium / margin_required * (365 / days_to_expiry) * 100 if days_to_expiry > 0 else 0
            else:
                margin_yield = 0
            
            return {
                'strike_price': strike_price,
                'premium': premium,
                'days_to_expiry': days_to_expiry,
                'delta': delta,
                'iv': iv,
                'capital_at_risk': capital_at_risk,
                'safety_margin_pct': safety_margin,
                'annual_yield_pct': annual_yield,
                'margin_required': margin_required,
                'margin_yield_pct': margin_yield,
                'in_buy_zone': buy_zone_low <= capital_at_risk <= buy_zone_high,
            }
            
        except Exception as e:
            print(f"❌ 计算 Sell Put 指标异常: {e}")
            return {}
    
    def calculate_covered_call_metrics(self, option_row: pd.Series, stock_price: float, target_price: float, cost_basis: Optional[float] = None) -> Dict[str, Any]:
        """计算 Covered Call 策略的关键指标"""
        try:
            strike_price = float(option_row['strike_price'])
            bid_price = float(option_row.get('bid', 0))
            days_to_expiry = int(option_row['days_to_expiry'])
            delta = float(option_row.get('delta', 0))
            iv = float(option_row.get('iv', 0))
            
            premium = bid_price if bid_price > 0 else float(option_row.get('mid', 0))
            
            # 静态收益率
            if stock_price > 0 and days_to_expiry > 0:
                static_return = (premium / stock_price) * (365 / days_to_expiry) * 100
            else:
                static_return = 0
            
            # 被行权时的总收益率
            if cost_basis is not None and cost_basis > 0:
                total_return_if_assigned = (strike_price - cost_basis + premium) / cost_basis * 100
            else:
                total_return_if_assigned = 0
            
            # 上行保护
            upside_protection = (strike_price - stock_price) / stock_price * 100
            
            return {
                'strike_price': strike_price,
                'premium': premium,
                'days_to_expiry': days_to_expiry,
                'delta': delta,
                'iv': iv,
                'static_return_pct': static_return,
                'total_return_if_assigned_pct': total_return_if_assigned,
                'upside_protection_pct': upside_protection,
                'reaches_target': strike_price >= target_price,
            }
            
        except Exception as e:
            print(f"❌ 计算 Covered Call 指标异常: {e}")
            return {}
    
    def filter_sell_put_options(self, code: str, chain_data: pd.DataFrame, market_data: Dict[str, Dict]) -> List[Dict]:
        """筛选符合条件的 Sell Put 期权"""
        try:
            config = self.config['sell_put']
            stock_price = self.get_stock_price(code)
            if stock_price is None:
                return []
            
            buy_zone = config['buy_zone'].get(code)
            if not buy_zone:
                return []
            
            buy_zone_low, buy_zone_high = buy_zone
            delta_min, delta_max = config['delta_range']
            min_volume = config['min_volume']
            min_open_interest = config['min_open_interest']
            
            filtered_options = []
            
            for _, row in chain_data.iterrows():
                option_code = row['code']
                option_market = market_data.get(option_code)
                if not option_market:
                    continue
                
                row = row.copy()
                for key, value in option_market.items():
                    row[key] = value
                
                strike_price = float(row['strike_price'])
                delta = float(row.get('delta', 0))
                volume = int(row.get('volume', 0))
                open_interest = int(row.get('open_interest', 0))
                bid_price = float(row.get('bid', 0))
                
                # 流动性筛选
                if volume < min_volume or open_interest < min_open_interest:
                    continue
                
                # Delta 筛选
                if not (delta_min <= abs(delta) <= delta_max):
                    continue
                
                # 行权价筛选
                capital_at_risk = strike_price - bid_price
                if not (buy_zone_low * 0.9 <= capital_at_risk <= buy_zone_high):
                    continue
                
                # IV 筛选
                iv = float(row.get('iv', 0))
                iv_percentile = self.calculate_iv_percentile(code, iv)
                if iv_percentile is not None and iv_percentile > config['iv_percentile_max']:
                    continue
                
                # 计算指标
                metrics = self.calculate_sell_put_metrics(row, stock_price, buy_zone)
                if not metrics:
                    continue
                
                # 最低年化收益率要求（命令行参数优先）
                min_yield = self.cmdline_args.get('min_annual_yield', config['min_annual_yield'])
                if metrics['annual_yield_pct'] < min_yield:
                    continue
                
                result = {
                    'stock_code': code,
                    'option_code': option_code,
                    'stock_price': stock_price,
                    'expiry_date': row['expiry_date'].strftime('%Y-%m-%d') if hasattr(row['expiry_date'], 'strftime') else str(row['expiry_date']),
                    **metrics
                }
                filtered_options.append(result)
            
            return filtered_options
            
        except Exception as e:
            print(f"❌ 筛选 {code} Sell Put 期权异常: {e}")
            return []
    
    def filter_covered_call_options(self, code: str, chain_data: pd.DataFrame, market_data: Dict[str, Dict]) -> List[Dict]:
        """筛选符合条件的 Covered Call 期权"""
        try:
            config = self.config['covered_call']
            stock_price = self.get_stock_price(code)
            if stock_price is None:
                return []
            
            holding_info = config['holdings'].get(code)
            if not holding_info:
                return []
            
            target_price = holding_info['target_sell_price']
            cost_basis = holding_info.get('cost_basis')
            delta_min, delta_max = config['delta_range']
            min_volume = config['min_volume']
            min_open_interest = config['min_open_interest']
            
            filtered_options = []
            
            for _, row in chain_data.iterrows():
                option_code = row['code']
                option_market = market_data.get(option_code)
                if not option_market:
                    continue
                
                row = row.copy()
                for key, value in option_market.items():
                    row[key] = value
                
                strike_price = float(row['strike_price'])
                delta = float(row.get('delta', 0))
                volume = int(row.get('volume', 0))
                open_interest = int(row.get('open_interest', 0))
                
                # 流动性筛选
                if volume < min_volume or open_interest < min_open_interest:
                    continue
                
                # Delta 筛选
                if not (delta_min <= delta <= delta_max):
                    continue
                
                # 行权价筛选
                if strike_price < target_price:
                    continue
                
                # IV 筛选
                iv = float(row.get('iv', 0))
                iv_percentile = self.calculate_iv_percentile(code, iv)
                if iv_percentile is not None and iv_percentile < config['iv_percentile_min']:
                    continue
                
                # 计算指标
                metrics = self.calculate_covered_call_metrics(row, stock_price, target_price, cost_basis)
                if not metrics:
                    continue
                
                result = {
                    'stock_code': code,
                    'option_code': option_code,
                    'stock_price': stock_price,
                    'target_price': target_price,
                    'expiry_date': row['expiry_date'].strftime('%Y-%m-%d') if hasattr(row['expiry_date'], 'strftime') else str(row['expiry_date']),
                    **metrics
                }
                filtered_options.append(result)
            
            return filtered_options
            
        except Exception as e:
            print(f"❌ 筛选 {code} Covered Call 期权异常: {e}")
            return []
    
    def run_sell_put_scan(self):
        """运行 Sell Put 策略扫描"""
        print("\n" + "="*60)
        print("🔍 开始扫描 Sell Put 策略")
        print("="*60)
        
        config = self.config['sell_put']
        
        # 处理命令行参数
        if self.cmdline_args.get('stock') and self.cmdline_args.get('buy_zone'):
            # 快速扫描模式：使用命令行参数
            stock = self.cmdline_args['stock']
            buy_zone_str = self.cmdline_args['buy_zone']
            try:
                low, high = map(float, buy_zone_str.split('-'))
                # 动态更新配置中的 buy_zone
                if 'buy_zone' not in config:
                    config['buy_zone'] = {}
                config['buy_zone'][stock] = (low, high)
                target_stocks = [stock]
                print(f"🔧 快速扫描模式: {stock}, 击球区 {low}-{high}")
            except (ValueError, AttributeError):
                print(f"❌ 无效的击球区格式: {buy_zone_str}, 请使用 '最低-最高' 格式 (如 150-170)")
                return []
        else:
            # 批处理模式：使用配置文件
            target_stocks = config['target_stocks']
            print(f"🔧 批处理模式: 扫描 {len(target_stocks)} 只股票")
        
        # 使用命令行参数覆盖配置（如果提供且不为None）
        expiry_days_min = self.cmdline_args.get('expiry_days_min')
        if expiry_days_min is None:
            expiry_days_min = config['expiry_days_min']
            
        expiry_days_max = self.cmdline_args.get('expiry_days_max')
        if expiry_days_max is None:
            expiry_days_max = config['expiry_days_max']
            
        min_annual_yield = self.cmdline_args.get('min_annual_yield')
        if min_annual_yield is None:
            min_annual_yield = config['min_annual_yield']
        
        all_results = []
        
        for code in target_stocks:
            print(f"\n📊 扫描 {code} ...")
            
            chain_data = self.get_option_chain(code, 'PUT', expiry_days_min, expiry_days_max)
            if chain_data is None or chain_data.empty:
                continue
            
            option_codes = chain_data['code'].tolist()
            market_data = self.get_option_market_data(option_codes)
            
            filtered = self.filter_sell_put_options(code, chain_data, market_data)
            all_results.extend(filtered)
            
            if filtered:
                print(f"   ✅ 找到 {len(filtered)} 个符合条件的 Sell Put 合约")
            else:
                print(f"   ⚠️ 未找到符合条件的 Sell Put 合约")
        
        all_results.sort(key=lambda x: x.get('annual_yield_pct', 0), reverse=True)
        self.sell_put_results = all_results
        return all_results
    
    def run_covered_call_scan(self):
        """运行 Covered Call 策略扫描"""
        print("\n" + "="*60)
        print("🔍 开始扫描 Covered Call 策略")
        print("="*60)
        
        config = self.config['covered_call']
        
        # 处理命令行参数
        if self.cmdline_args.get('stock') and self.cmdline_args.get('target_price'):
            # 快速扫描模式：使用命令行参数
            stock = self.cmdline_args['stock']
            target_price = float(self.cmdline_args['target_price'])
            holding_qty = self.cmdline_args.get('holding_qty', 100)
            # 动态更新配置中的 holdings
            if 'holdings' not in config:
                config['holdings'] = {}
            config['holdings'][stock] = {
                'target_sell_price': target_price,
                'quantity': holding_qty
            }
            holdings = config['holdings']
            print(f"🔧 快速扫描模式: {stock}, 目标价 {target_price}, 持仓 {holding_qty}")
        else:
            # 批处理模式：使用配置文件
            holdings = config['holdings']
            print(f"🔧 批处理模式: 扫描 {len(holdings)} 只持仓股票")
        
        # 使用命令行参数覆盖配置（如果提供且不为None）
        expiry_days_min = self.cmdline_args.get('expiry_days_min')
        if expiry_days_min is None:
            expiry_days_min = config['expiry_days_min']
            
        expiry_days_max = self.cmdline_args.get('expiry_days_max')
        if expiry_days_max is None:
            expiry_days_max = config['expiry_days_max']
        
        all_results = []
        
        for code, holding_info in holdings.items():
            print(f"\n📊 扫描 {code} ...")
            
            chain_data = self.get_option_chain(code, 'CALL', expiry_days_min, expiry_days_max)
            if chain_data is None or chain_data.empty:
                continue
            
            option_codes = chain_data['code'].tolist()
            market_data = self.get_option_market_data(option_codes)
            
            filtered = self.filter_covered_call_options(code, chain_data, market_data)
            all_results.extend(filtered)
            
            if filtered:
                print(f"   ✅ 找到 {len(filtered)} 个符合条件的 Covered Call 合约")
            else:
                print(f"   ⚠️ 未找到符合条件的 Covered Call 合约")
        
        all_results.sort(key=lambda x: x.get('static_return_pct', 0), reverse=True)
        self.covered_call_results = all_results
        return all_results
    
    def print_results_table(self, results: List[Dict], strategy_type: str):
        """使用 PrettyTable 打印结果表格"""
        if not results:
            print(f"📭 未找到符合条件的 {strategy_type} 策略")
            return
        
        if strategy_type == 'Sell Put':
            table = PrettyTable()
            table.field_names = [
                "股票", "到期日", "行权价", "权利金", "Delta", "IV%",
                "买入成本", "年化%", "安全边际"
            ]
            
            for r in results[:15]:
                table.add_row([
                    r['stock_code'],
                    r['expiry_date'][5:],
                    f"${r['strike_price']:.2f}",
                    f"${r['premium']:.2f}",
                    f"{r['delta']:.3f}",
                    f"{r['iv']*100:.1f}%" if r['iv'] > 0 else "N/A",
                    f"${r['capital_at_risk']:.2f}",
                    f"{r['annual_yield_pct']:.1f}%",
                    f"{r['safety_margin_pct']:.1f}%" if r['safety_margin_pct'] > 0 else "N/A"
                ])
            
            print(f"\n📋 {strategy_type} 策略推荐（按年化收益率排序）:")
            print(table)
            
        elif strategy_type == 'Covered Call':
            table = PrettyTable()
            table.field_names = [
                "股票", "到期日", "行权价", "权利金", "Delta", "IV%",
                "静态年化%", "上行保护%", "达到目标"
            ]
            
            for r in results[:15]:
                table.add_row([
                    r['stock_code'],
                    r['expiry_date'][5:],
                    f"${r['strike_price']:.2f}",
                    f"${r['premium']:.2f}",
                    f"{r['delta']:.3f}",
                    f"{r['iv']*100:.1f}%" if r['iv'] > 0 else "N/A",
                    f"{r['static_return_pct']:.1f}%",
                    f"{r['upside_protection_pct']:.1f}%",
                    "✅" if r['reaches_target'] else "⚠️"
                ])
            
            print(f"\n📋 {strategy_type} 策略推荐（按静态收益率排序）:")
            print(table)
    
    def save_results_csv(self, results: List[Dict], strategy_type: str):
        """保存结果到 CSV 文件"""
        if not results:
            return
        
        output_config = self.config.get('output', {})
        if not output_config.get('save_csv', True):
            return
        
        csv_path = output_config.get('csv_path', f'./option_strategy_{strategy_type.lower().replace(" ", "_")}.csv')
        
        try:
            with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
                if results:
                    writer = csv.DictWriter(f, fieldnames=results[0].keys())
                    writer.writeheader()
                    writer.writerows(results)
            
            print(f"💾 结果已保存到: {csv_path}")
            
        except Exception as e:
            print(f"❌ 保存CSV文件失败: {e}")
    
    def print_risk_warnings(self):
        """打印风险警告"""
        print("\n" + "="*80)
        print("⚠️  价值投资者重要提醒  ⚠️")
        print("="*80)
        print("""
1. Sell Put 前提是你愿意以【行权价 - 权利金】的价格长期持有该公司。
   不要因为权利金而去卖垃圾公司的 Put，只卖你真心想拥有的好公司。

2. Covered Call 会让你在暴涨时踏空。
   请确保【行权价】是你真心愿意卖出的价格，不要因小失大。

3. 期权卖方是"赚小钱、担大风险"的策略。
   务必控制仓位，单策略不超过总资产的5%。

4. 本系统仅为策略生成工具，不构成投资建议。
   投资有风险，决策需谨慎。
        """)
        print("="*80)
    
    def run(self):
        """主运行函数"""
        self.print_risk_warnings()
        
        if not self.connect_api():
            return
        
        try:
            # 确定运行模式
            mode = self.cmdline_args.get('mode', 'both')
            sell_put_only = self.cmdline_args.get('sell_put_only', False)
            covered_call_only = self.cmdline_args.get('covered_call_only', False)
            
            # 根据模式决定运行哪些扫描
            sell_put_results = []
            covered_call_results = []
            
            run_sell_put = False
            run_covered_call = False
            
            if sell_put_only:
                run_sell_put = True
                run_covered_call = False
            elif covered_call_only:
                run_sell_put = False
                run_covered_call = True
            else:
                if mode == 'both':
                    run_sell_put = True
                    run_covered_call = True
                elif mode == 'sell-put':
                    run_sell_put = True
                    run_covered_call = False
                elif mode == 'covered-call':
                    run_sell_put = False
                    run_covered_call = True
            
            # 扫描 Sell Put 策略
            if run_sell_put:
                sell_put_results = self.run_sell_put_scan()
            
            # 扫描 Covered Call 策略
            if run_covered_call:
                covered_call_results = self.run_covered_call_scan()
            
            # 打印结果
            if self.config.get('output', {}).get('print_table', True):
                if run_sell_put:
                    self.print_results_table(sell_put_results, 'Sell Put')
                if run_covered_call:
                    self.print_results_table(covered_call_results, 'Covered Call')
            
            # 保存结果
            if run_sell_put:
                self.save_results_csv(sell_put_results, 'Sell Put')
            if run_covered_call:
                self.save_results_csv(covered_call_results, 'Covered Call')
            
            # 汇总统计
            print("\n" + "="*60)
            print("📊 扫描完成汇总")
            print("="*60)
            if run_sell_put:
                print(f"Sell Put 策略找到: {len(sell_put_results)} 个")
                if sell_put_results:
                    best_put = sell_put_results[0]
                    print(f"\n🎯 最佳 Sell Put: {best_put['stock_code']} @ ${best_put['strike_price']:.2f}")
                    print(f"   年化收益率: {best_put['annual_yield_pct']:.1f}%")
                    print(f"   实际买入成本: ${best_put['capital_at_risk']:.2f}")
            
            if run_covered_call:
                print(f"Covered Call 策略找到: {len(covered_call_results)} 个")
                if covered_call_results:
                    best_call = covered_call_results[0]
                    print(f"\n🎯 最佳 Covered Call: {best_call['stock_code']} @ ${best_call['strike_price']:.2f}")
                    print(f"   静态年化收益率: {best_call['static_return_pct']:.1f}%")
                    print(f"   上行保护: {best_call['upside_protection_pct']:.1f}%")
            
        except KeyboardInterrupt:
            print("\n\n⏹️ 用户中断扫描")
        except Exception as e:
            print(f"\n❌ 运行异常: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.disconnect_api()


def main():
    """主函数入口"""
    import argparse
    import os
    
    parser = argparse.ArgumentParser(description='价值投资期权策略生成器')
    parser.add_argument('--config', '-c', default='config_option_writer.yaml',
                       help='配置文件路径 (默认: config_option_writer.yaml)')
    
    # 快速扫描模式参数
    parser.add_argument('--stock', '-s', 
                       help='快速扫描单个股票代码 (如 US.AAPL, HK.00700)')
    parser.add_argument('--buy-zone', '-b',
                       help='击球区价格范围 (格式: 最低-最高，如 150-170)')
    parser.add_argument('--target-price', '-t', type=float,
                       help='目标卖出价 (用于 Covered Call 策略)')
    parser.add_argument('--holding-qty', type=int, default=100,
                       help='持仓数量 (用于 Covered Call，默认: 100)')
    parser.add_argument('--mode', choices=['sell-put', 'covered-call', 'both'],
                       default='both', help='扫描模式 (默认: both)')
    
    # 过滤选项
    parser.add_argument('--expiry-days-min', type=int, default=None,
                       help='最小到期日 (天)')
    parser.add_argument('--expiry-days-max', type=int, default=None,
                       help='最大到期日 (天)')
    parser.add_argument('--delta-min', type=float, default=None,
                       help='Delta 最小值 (默认: 0.15)')
    parser.add_argument('--delta-max', type=float, default=None,
                       help='Delta 最大值 (默认: 0.35)')
    parser.add_argument('--min-annual-yield', type=float, default=None,
                       help='最低年化收益率要求 (%%)')
    
    # 运行控制
    parser.add_argument('--sell-put-only', action='store_true',
                       help='仅运行 Sell Put 扫描')
    parser.add_argument('--covered-call-only', action='store_true',
                       help='仅运行 Covered Call 扫描')
    
    args = parser.parse_args()
    
    print("🚀 价值投资期权策略生成器 v1.0")
    print("基于 Futu API，服务于价值投资者的期权卖方策略扫描")
    
    # 检查配置文件是否存在
    if not os.path.exists(args.config):
        print(f"\n❌ 配置文件不存在: {args.config}")
        print("请先创建配置文件，或使用 --config 指定配置文件路径")
        print("可以使用 config_option_writer.yaml 作为模板")
        return
    
    # 创建生成器实例
    generator = ValueInvestingOptionWriter(
        config_path=args.config,
        cmdline_args=vars(args)  # 传递命令行参数
    )
    
    # 运行扫描
    generator.run()


if __name__ == "__main__":
    main()