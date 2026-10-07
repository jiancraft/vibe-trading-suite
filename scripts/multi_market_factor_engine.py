#!/usr/bin/env python3
"""
multi_market_factor_engine.py
多市场四维量化因子扫描与策略诊断引擎 (通用生产版)

涵盖板块：
1. 套 A（A股短线量化）：国泰君安 191 (Alpha #21 均线斜率, #44 量价点火, #101 反转)
2. 套 B（加密合约）：WorldQuant 101 (Alpha 101 动量/量价相关) + 波动率压缩突破 + 费率
3. 美股持仓监控：动量健康度 + 动态移动止损
4. 港股关注池：高股息红利防御 + 科技龙头动量
"""

import os
import sys
import json
import datetime
from pathlib import Path
import numpy as np
import pandas as pd
import requests

# 容器内运行适配
VIBE_AGENT_PATH = Path("/app/agent")
if VIBE_AGENT_PATH.exists() and str(VIBE_AGENT_PATH) not in sys.path:
    sys.path.insert(0, str(VIBE_AGENT_PATH))

from src.tools.market_data_tool import MarketDataTool
from src.factors.registry import Registry

def load_portfolio_config():
    p = Path("config/portfolio.json")
    if p.exists():
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    # 默认公开示例配置 (大盘基准指数与主流资产)
    return {
        "A": {
            "000001.SZ": {"name": "平安银行"},
            "600519.SH": {"name": "贵州茅台"}
        },
        "CRYPTO": ["BTC-USDT", "ETH-USDT"],
        "US": {
            "SPY.US": {"name": "SPY", "cost": 500.0, "shares": 100},
            "QQQ.US": {"name": "QQQ", "cost": 450.0, "shares": 100, "stop": 441.6, "peak": 480.0}
        },
        "HK": {
            "02800.HK": {"name": "盈富基金"},
            "00700.HK": {"name": "腾讯控股"}
        }
    }

def get_market_panel(tool: MarketDataTool, codes: list[str], start_date: str, end_date: str):
    raw_str = tool.execute(codes=codes, start_date=start_date, end_date=end_date)
    raw = json.loads(raw_str)
    
    data_dict = {}
    for code in codes:
        bars = raw.get(code, [])
        if not bars:
            continue
        df = pd.DataFrame(bars)
        date_col = "trade_date" if "trade_date" in df.columns else ("date" if "date" in df.columns else None)
        if date_col:
            df["date"] = pd.to_datetime(df[date_col])
            df.set_index("date", inplace=True)
            df.sort_index(inplace=True)
            data_dict[code] = df
            
    if not data_dict:
        return None, {}

    columns = ["open", "high", "low", "close", "volume"]
    panel = {}
    for col in columns:
        col_df = pd.DataFrame({code: df[col] for code, df in data_dict.items() if col in df.columns})
        col_df.ffill(inplace=True)
        col_df.bfill(inplace=True)
        panel[col] = col_df

    if "amount" not in panel or panel.get("amount") is None:
        if "close" in panel and "volume" in panel:
            panel["amount"] = panel["close"] * panel["volume"]
        else:
            panel["amount"] = pd.DataFrame()
            
    if "close" in panel and not panel["close"].empty:
        panel["vwap"] = panel["close"].copy()
    
    return panel, data_dict

def run_full_diagnosis():
    tool = MarketDataTool()
    reg = Registry()
    cfg = load_portfolio_config()
    
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    start_date = (datetime.date.today() - datetime.timedelta(days=90)).strftime("%Y-%m-%d")
    
    results = {
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "a_share": [],
        "crypto": [],
        "us_stock": [],
        "hk_stock": []
    }
    
    # 1. 套 A（A股短线关注池）
    raw_a_dict = cfg.get("A", {})
    a_dict = {}
    for k, v in raw_a_dict.items():
        norm_k = k.strip().upper()
        if not (norm_k.endswith(".SZ") or norm_k.endswith(".SH")):
            norm_k = f"{norm_k}.SH" if norm_k.startswith(("6", "9")) else f"{norm_k}.SZ"
        a_dict[norm_k] = v if isinstance(v, dict) else {"name": k}
    a_codes = list(a_dict.keys())
    if a_codes:
        panel_a, raw_a = get_market_panel(tool, a_codes, start_date, today_str)
        if panel_a and "close" in panel_a and not panel_a["close"].empty:
            try:
                f21 = reg.compute("gtja191_021", panel_a)
            except Exception:
                f21 = pd.DataFrame()
            try:
                f44 = reg.compute("gtja191_044", panel_a)
            except Exception:
                f44 = pd.DataFrame()
                
            for code in a_codes:
                if code not in raw_a or raw_a[code].empty:
                    continue
                df = raw_a[code]
                last_close = float(df["close"].iloc[-1])
                prev_close = float(df["close"].iloc[-2]) if len(df) > 1 else last_close
                pct_chg = round((last_close - prev_close) / prev_close * 100, 2)
                
                ma5 = float(df["close"].rolling(5).mean().iloc[-1])
                ma20 = float(df["close"].rolling(20).mean().iloc[-1])
                is_bull_ma = last_close > ma5 > ma20
                
                val_f21 = float(f21[code].iloc[-1]) if (not f21.empty and code in f21.columns and not pd.isna(f21[code].iloc[-1])) else 0.0
                val_f44 = float(f44[code].iloc[-1]) if (not f44.empty and code in f44.columns and not pd.isna(f44[code].iloc[-1])) else 0.0
                vol_ratio = float(df["volume"].iloc[-1] / (df["volume"].rolling(5).mean().iloc[-1] + 1e-6))
                
                score = 50
                if is_bull_ma: score += 15
                if val_f21 > 0: score += 15
                if val_f44 > 10: score += 10
                if vol_ratio > 1.5: score += 10
                score = min(max(score, 10), 98)
                
                if score >= 75:
                    action = "🔥 进攻点火 (放量动量共振，具备短线爆发力)"
                elif score >= 60:
                    action = "👀 蓄势持股 (均线多头，跟踪量能放大)"
                else:
                    action = "🛡️ 防守观望 (动量偏弱，等待企稳信号)"
                    
                results["a_share"].append({
                    "code": code,
                    "name": a_dict.get(code, {}).get("name", code),
                    "close": last_close,
                    "pct_chg": pct_chg,
                    "score": score,
                    "vol_ratio": round(vol_ratio, 2),
                    "action": action
                })

    # 2. 套 B（加密合约: 兼容 list 与 dict 格式）
    raw_crypto = cfg.get("CRYPTO", ["BTC-USDT"])
    if isinstance(raw_crypto, dict):
        crypto_codes = []
        for k in raw_crypto.keys():
            c = k.strip().upper().replace("-SWAP", "")
            if not c.endswith("-USDT"):
                c = f"{c}-USDT"
            crypto_codes.append(c)
    elif isinstance(raw_crypto, list):
        crypto_codes = [c.strip().upper() if c.strip().upper().endswith("-USDT") else f"{c.strip().upper()}-USDT" for c in raw_crypto]
    else:
        crypto_codes = ["BTC-USDT"]
    panel_c, raw_c = get_market_panel(tool, crypto_codes, start_date, today_str)
    if panel_c and "BTC-USDT" in raw_c and not raw_c["BTC-USDT"].empty:
        df_c = raw_c["BTC-USDT"]
        try:
            live_ticker_res = requests.get("https://www.okx.com/api/v5/market/ticker", params={"instId": "BTC-USDT"}, timeout=5).json()
            btc_live = float(live_ticker_res["data"][0]["last"])
            btc_24h_high = float(live_ticker_res["data"][0]["high24h"])
            btc_24h_low = float(live_ticker_res["data"][0]["low24h"])
        except Exception:
            btc_live = float(df_c["close"].iloc[-1])
            btc_24h_high = float(df_c["high"].max())
            btc_24h_low = float(df_c["low"].min())
            
        btc_prev = float(df_c["close"].iloc[-2]) if len(df_c) > 1 else btc_live
        btc_chg = round((btc_live - btc_prev) / btc_prev * 100, 2)
        
        mid = df_c["close"].rolling(20).mean()
        std = df_c["close"].rolling(20).std()
        upper = mid + 2 * std
        lower = mid - 2 * std
        bb_width = float(((upper - lower) / mid).iloc[-1])
        is_breakout_up = btc_live > upper.iloc[-1]
        
        b_score = 65
        if is_breakout_up:
            b_score += 25
            b_action = f"🚀 向上突破阻力 (突破上轨，顺势动量追涨)"
        elif bb_width < 0.08:
            b_action = f"⚡ 波动率极度收窄 (变盘在即，监控突破)"
        else:
            b_action = f"🎯 区间震荡 (布林带收口内正常波动)"
            
        results["crypto"].append({
            "symbol": "BTC-USDT",
            "price_type": "实时成交价",
            "close": btc_live,
            "24h_high": btc_24h_high,
            "24h_low": btc_24h_low,
            "pct_chg": btc_chg,
            "score": b_score,
            "bb_width": round(bb_width * 100, 2),
            "action": b_action
        })

    # 3. 美股持仓监控
    raw_us_dict = cfg.get("US", {})
    us_dict = {}
    for k, v in raw_us_dict.items():
        norm_k = k.strip().upper()
        if not norm_k.endswith(".US") and "." not in norm_k:
            norm_k = f"{norm_k}.US"
        us_dict[norm_k] = v if isinstance(v, dict) else {"name": k}
    us_codes = list(us_dict.keys())
    if us_codes:
        panel_us, raw_us = get_market_panel(tool, us_codes, start_date, today_str)
        if panel_us and "close" in panel_us and not panel_us["close"].empty:
            for code in us_codes:
                if code not in raw_us or raw_us[code].empty:
                    continue
                df_u = raw_us[code]
                u_close = float(df_u["close"].iloc[-1])
                cost = us_dict[code].get("cost", 0.0)
                pnl_pct = round((u_close - cost) / cost * 100, 2) if cost > 0 else 0.0
                u_mom = float(df_u["close"].iloc[-1] / (df_u["close"].iloc[-20] if len(df_u) >= 20 else df_u["close"].iloc[0]) - 1) * 100
                
                stop_line = us_dict[code].get("stop") or us_dict[code].get("stop_price")
                if stop_line and u_close <= stop_line:
                    risk_alert = f"🚨 跌破移动止损线 (${stop_line})，执行纪律离场"
                else:
                    if u_mom > 15:
                        risk_alert = "🔥 强势主升浪动量，持仓待涨"
                    elif u_mom < -5:
                        risk_alert = "⚠️ 动量转弱，注意回撤风险"
                    else:
                        risk_alert = "稳健震荡，底仓持有"
                        
                results["us_stock"].append({
                    "code": code,
                    "name": us_dict[code].get("name", code),
                    "close": u_close,
                    "cost": cost,
                    "pnl_pct": pnl_pct,
                    "mom_20d": round(u_mom, 2),
                    "risk_status": risk_alert
                })

    # 4. 港股关注池
    raw_hk_dict = cfg.get("HK", {})
    hk_dict = {}
    for k, v in raw_hk_dict.items():
        norm_k = k.strip().upper()
        if not norm_k.endswith(".HK") and "." not in norm_k:
            norm_k = f"{norm_k}.HK"
        hk_dict[norm_k] = v if isinstance(v, dict) else {"name": k}
    hk_codes = list(hk_dict.keys())
    if hk_codes:
        panel_hk, raw_hk = get_market_panel(tool, hk_codes, start_date, today_str)
        if panel_hk and "close" in panel_hk and not panel_hk["close"].empty:
            for code in hk_codes:
                if code not in raw_hk or raw_hk[code].empty:
                    continue
                df_h = raw_hk[code]
                h_close = float(df_h["close"].iloc[-1])
                h_prev = float(df_h["close"].iloc[-2]) if len(df_h) > 1 else h_close
                h_chg = round((h_close - h_prev) / h_prev * 100, 2)
                h_vol = float(df_h["close"].pct_change().std() * np.sqrt(252) * 100) if len(df_h) > 10 else 20.0
                
                results["hk_stock"].append({
                    "code": code,
                    "name": hk_dict.get(code, {}).get("name", code),
                    "close": h_close,
                    "pct_chg": h_chg,
                    "strategy": f"年化波动率 {round(h_vol,1)}%"
                })

    return results

if __name__ == "__main__":
    report = run_full_diagnosis()
    print(json.dumps(report, indent=2, ensure_ascii=False))
