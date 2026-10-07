#!/usr/bin/env python3
"""
Trading-Expert: 股票与加密合约量化诊断引擎 (A股 / 港股 / 美股 / OKX套B)
支持实时行情、套A游资量价分析、持仓移动止损追踪、OKX套B合约2.0风控。
"""

import sys
import os
import json
import urllib.request
from datetime import datetime, timezone
import re
from pathlib import Path

# 默认公开标的配置与策略参数模板 (用户可在 config/portfolio.json 自定义覆盖)
DEFAULT_WATCHLIST_CONFIG = {
    # 美股持仓与监控示例 (大盘指数基准)
    "US": {
        "SPY": {"name": "标普500 ETF", "cost": 500.00, "shares": 100},
        "QQQ": {"name": "纳斯达克100 ETF", "cost": 450.00, "shares": 100, "trailing_stop_pct": 0.08, "peak": 480.00, "stop_price": 441.60},
    },
    # A股短线量化关注池 (大盘核心基准: 平安银行 000001.SZ 权重基准，注: 上证综指代码为 sh000001)
    "A": {
        "000001": {"code": "sz000001", "name": "平安银行", "cost": 10.00, "shares": 1000, "stop_price": 9.50, "role": "金融权重基准 (上证综指为 sh000001)"},
        "600519": {"code": "sh600519", "name": "贵州茅台", "cost": 1600.00, "shares": 100, "stop_price": 1520.00, "role": "消费核心基准"},
    },
    # 港股关注池 (指数与核心权重)
    "HK": {
        "02800": {"code": "hk02800", "name": "盈富基金"},
        "00700": {"code": "hk00700", "name": "腾讯控股"},
    },
    # 套B 官方示例币种 (主流低波, 稳健 10x 逐仓)
    "CRYPTO": {
        "BTC": {"name": "BTC", "group": "主流基石组", "leverage": "10x", "sl_pct": 0.015, "tp_pct": 0.030, "be_pct": 0.015, "max_spread": 0.05, "digits": 2},
        "ETH": {"name": "ETH", "group": "主流基石组", "leverage": "10x", "sl_pct": 0.015, "tp_pct": 0.030, "be_pct": 0.015, "max_spread": 0.05, "digits": 2},
    }
}

def load_watchlist_config():
    local_cfg = Path("config/portfolio.json")
    cfg = DEFAULT_WATCHLIST_CONFIG
    if local_cfg.exists():
        try:
            with open(local_cfg, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            cfg = DEFAULT_WATCHLIST_CONFIG

    # 规范化 CRYPTO 键名: 同时建立短名 (BTC) 与全名 (BTC-USDT) 双向索引
    crypto_dict = {}
    for k, v in cfg.get("CRYPTO", {}).items():
        clean_k = k.upper().replace("-USDT-SWAP", "").replace("-USDT", "").replace("USDT", "").strip()
        crypto_dict[clean_k] = v
        crypto_dict[f"{clean_k}-USDT"] = v
    cfg["CRYPTO"] = crypto_dict
    return cfg

WATCHLIST_CONFIG = load_watchlist_config()

def resolve_symbol(query: str):
    q = query.strip().upper()

    # 显式带有 -USDT / -SWAP 后缀的一律判定为加密货币
    if q.endswith("-SWAP") or "-USDT" in q:
        clean = q.replace("-USDT-SWAP", "").replace("-USDT", "").replace("USDT", "").strip()
        return f"crypto:{clean}"

    # 显式带有前缀
    if q.startswith("CRYPTO:"):
        return f"crypto:{q.split(':')[1].strip()}"
    raw = query.strip()
    if raw.upper().startswith("US:"):
        return f"us{raw[3:].strip().upper()}"
    if raw.startswith("us") and len(raw) > 2 and raw[2:].isupper():
        return f"us{raw[2:]}"

    # 别名与大盘核心基准映射
    aliases = {
        "平安银行": "sz000001", "000001": "sz000001", "000001.SZ": "sz000001",
        "贵州茅台": "sh600519", "600519": "sh600519", "600519.SH": "sh600519", "茅台": "sh600519",
        "盈富基金": "hk02800", "02800": "hk02800", "02800.HK": "hk02800",
        "腾讯控股": "hk00700", "腾讯": "hk00700", "00700": "hk00700", "00700.HK": "hk00700",
        "SPY": "usSPY", "QQQ": "usQQQ",
    }
    if q in aliases:
        return aliases[q]

    # 无歧义的主流加密原生币种 (无美股代码冲突)
    PRIMARY_CRYPTO_SYMBOLS = {"BTC", "ETH", "DOGE", "PEPE", "SHIB", "OKB", "SOL", "XRP", "BNB", "ADA", "AVAX", "DOT"}
    if q in PRIMARY_CRYPTO_SYMBOLS:
        return f"crypto:{q}"

    # 美股持仓与监控匹配 (优先匹配 US 配置中的标的)
    if q in WATCHLIST_CONFIG.get("US", {}):
        return f"us{q}"

    if q.isdigit():
        if len(q) == 5:
            return f"hk{q}"
        elif len(q) == 6:
            if q.startswith(('60', '68')):
                return f"sh{q}"
            else:
                return f"sz{q}"

    # A股与港股显式带市场前缀 (如 sh600519, sz000001, hk00700)
    if q.startswith(('SH', 'SZ')) and len(q) > 2 and q[2:].isdigit():
        return f"{q[:2].lower()}{q[2:]}"
    if q.startswith('HK') and len(q) > 2 and q[2:].isdigit():
        return f"hk{q[2:]}"

    if q.endswith(('.SH', '.SZ', '.HK', '.US')):
        parts = q.split('.')
        return f"{parts[1].lower()}{parts[0]}"
    
    if re.match(r'^[A-Z]{1,5}$', q):
        return f"us{q}"
        
    return q

def fetch_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=6) as response:
        return json.loads(response.read().decode('utf-8'))

def get_crypto_digits(price: float, configured_digits: int = None) -> int:
    if price < 0.0001:
        return 8
    elif price < 0.01:
        return 6
    elif price < 1.0:
        return 4
    elif configured_digits is not None:
        return configured_digits
    return 2

def analyze_crypto(symbol: str):
    clean_sym = symbol.upper().replace("-USDT-SWAP", "").replace("-USDT", "").replace("USDT", "").strip()
    inst_id = f"{clean_sym}-USDT-SWAP"
    cfg = WATCHLIST_CONFIG.get("CRYPTO", {}).get(clean_sym, {
        "name": clean_sym, "group": "未预设标的", "leverage": "5x", "sl_pct": 0.02, "tp_pct": 0.04, "be_pct": 0.015, "max_spread": 0.08
    })

    try:
        t_data = fetch_json(f"https://www.okx.com/api/v5/market/ticker?instId={inst_id}")["data"][0]
        fr_data = fetch_json(f"https://www.okx.com/api/v5/public/funding-rate?instId={inst_id}")["data"][0]
        oi_data = fetch_json(f"https://www.okx.com/api/v5/public/open-interest?instType=SWAP&instId={inst_id}")["data"][0]
        c_data = fetch_json(f"https://www.okx.com/api/v5/market/candles?instId={inst_id}&bar=1H&limit=24")["data"]
    except Exception as e:
        print(f"抓取行情数据失败: {e}")
        return

    last_p = float(t_data["last"])
    digits = get_crypto_digits(last_p, cfg.get("digits"))
    high_24h = float(t_data["high24h"])
    low_24h = float(t_data["low24h"])
    open_24h = float(t_data["open24h"])
    chg_pct = (last_p - open_24h) / open_24h * 100 if open_24h else 0.0
    chg_amt = last_p - open_24h
    ask_px = float(t_data.get("askPx", last_p))
    bid_px = float(t_data.get("bidPx", last_p))
    spread_pct = (ask_px - bid_px) / last_p * 100 if last_p else 0.0
    vol_ccy = float(t_data.get("volCcy24h", 0))
    vol_24h_usd = vol_ccy * last_p if vol_ccy > 0 else 0.0

    funding_rate = float(fr_data.get("fundingRate", 0)) * 100
    funding_time_ms = int(fr_data.get("nextFundingTime", 0))
    funding_dt = datetime.fromtimestamp(funding_time_ms / 1000, tz=timezone.utc).strftime("%H:%M UTC") if funding_time_ms else "--"
    oi_usd = float(oi_data.get("oiUsd", 0))

    closes = [float(c[4]) for c in c_data]
    ma20 = sum(closes[:20]) / 20.0 if len(closes) >= 20 else last_p
    std20 = ((sum((x - ma20) ** 2 for x in closes[:20]) / 20.0) ** 0.5) if len(closes) >= 20 else 0
    upper_bb = ma20 + 2 * std20
    lower_bb = ma20 - 2 * std20

    pivot = (high_24h + low_24h + last_p) / 3
    r1 = 2 * pivot - low_24h
    s1 = 2 * pivot - high_24h

    now_utc = datetime.now(timezone.utc)
    in_funding_window = False
    if now_utc.hour in [23, 7, 15] and now_utc.minute >= 57:
        in_funding_window = True
    elif now_utc.hour in [0, 8, 16] and now_utc.minute <= 3:
        in_funding_window = True

    sl_long = last_p * (1 - cfg["sl_pct"])
    tp_long = last_p * (1 + cfg["tp_pct"])
    be_trigger = last_p * (1 + cfg["be_pct"])

    fmt = f"{{:.{digits}f}}"

    print(f"### 【OKX 套B 2.0 合约量化诊断：{symbol}（{inst_id}）】\n")
    print(f"- **体系归属**：套B加密合约实盘 | **策略分组**：{cfg['group']}（{cfg['leverage']} 逐仓 isolated）")
    print(f"- **实时现价**：`{fmt.format(last_p)}` USDT （24H涨跌幅: `{chg_pct:+.2f}%`，涨跌额: `{fmt.format(chg_amt)}`）")
    print(f"- **24H 极值**：最高 `{fmt.format(high_24h)}` | 最低 `{fmt.format(low_24h)}` | 今开 `{fmt.format(open_24h)}`")
    print(f"- **24H 成交货值**：`${vol_24h_usd / 1e6:.2f}M` USDT | **未平仓持仓量 (OI)**：`${oi_usd / 1e6:.2f}M` USDT")
    print(f"- **当前资金费率**：`{funding_rate:+.4f}%`（下次结算: `{funding_dt}` | 避震窗状态: {'⚠️ 处于结算避震窗' if in_funding_window else '✅ 正常交易窗'}）")
    print(f"- **盘口买卖价差**：`{spread_pct:.4f}%`（价差保护锁上限: `{cfg['max_spread']:.2f}%` -> {'✅ 盘口健康' if spread_pct <= cfg['max_spread'] else '⚠️ 价差超标，避让开仓'}）")

    print(f"\n#### 🎯 关键技术结构与多空订单块（SMC & 枢轴位）：")
    print(f"- **枢轴关键阻力 (R1)**：`{fmt.format(r1)}` USDT")
    print(f"- **布林上轨 (1H Upper BB)**：`{fmt.format(upper_bb)}` USDT")
    print(f"- **布林中轨 / MA20**：`{fmt.format(ma20)}` USDT")
    print(f"- **枢轴关键支撑 (S1)**：`{fmt.format(s1)}` USDT")
    print(f"- **布林下轨 (1H Lower BB)**：`{fmt.format(lower_bb)}` USDT")

    print(f"\n#### 🛡️ 工业级风控与交易纪律：")
    print(f"- **杠杆与仓位隔离**：严格物理锁定 `{cfg['leverage']} isolated`（严禁全仓）")
    print(f"- **止损保护位**：做多硬止损位 `{fmt.format(sl_long)}`（-{cfg['sl_pct']*100:.2f}%）")
    print(f"- **目标止盈位**：做多目标止盈位 `{fmt.format(tp_long)}`（+{cfg['tp_pct']*100:.2f}%）")
    print(f"- **动态保本损推升机制**：浮盈触及 `+{cfg['be_pct']*100:.1f}%`（触发价 `{fmt.format(be_trigger)}`）时，自动推升止损至开仓保本价。")

def fetch_quote(sec_code: str):
    url = f"http://qt.gtimg.cn/q={sec_code}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=5) as response:
        content = response.read().decode('gbk', errors='ignore')
    
    match = re.search(r'="([^"]+)"', content)
    if not match or not match.group(1):
        return None
    fields = match.group(1).split('~')
    return fields

def analyze_stock(query: str):
    sec_code = resolve_symbol(query)

    if sec_code.startswith("crypto:"):
        symbol = sec_code.split(":")[1]
        analyze_crypto(symbol)
        return

    fields = fetch_quote(sec_code)
    if not fields or len(fields) < 30:
        print(f"未能获取标的 [{query}] 的实时盘面数据，请核对代码。")
        return

    name = fields[1]
    code = fields[2]
    now_price = float(fields[3]) if fields[3] else 0.0
    pre_close = float(fields[4]) if fields[4] else 0.0
    open_price = float(fields[5]) if fields[5] else 0.0
    chg_amt = float(fields[31]) if len(fields) > 31 and fields[31] else (now_price - pre_close)
    chg_pct = float(fields[32]) if len(fields) > 32 and fields[32] else ((now_price - pre_close) / pre_close * 100 if pre_close else 0.0)
    high = float(fields[33]) if len(fields) > 33 and fields[33] else now_price
    low = float(fields[34]) if len(fields) > 34 and fields[34] else now_price
    turnover_rate = float(fields[38]) if len(fields) > 38 and fields[38] else 0.0
    
    market_type = "美股" if sec_code.startswith("us") else ("港股" if sec_code.startswith("hk") else "A股短线")
    currency = "USD" if market_type == "美股" else ("HKD" if market_type == "港股" else "CNY")

    print(f"### 【{name}（{code}）盘面量化与风控研判】\n")
    print(f"- **市场定位**：{market_type} | **当前货币**：{currency}")
    print(f"- **实时现价**：`{now_price:.2f}` {currency} （涨跌额: `{chg_amt:+.2f}`, 涨跌幅: `{chg_pct:+.2f}%`）")
    print(f"- **今日极值**：最高 `{high:.2f}` | 最低 `{low:.2f}` | 今开 `{open_price:.2f}` | 昨收 `{pre_close:.2f}`")
    if turnover_rate > 0:
        print(f"- **换手率**：`{turnover_rate:.2f}%`")

    clean_code = code.split('.')[0] if '.' in code else code
    if clean_code in WATCHLIST_CONFIG.get("US", {}):
        cfg = WATCHLIST_CONFIG["US"][clean_code]
        cost = cfg.get("cost", 0)
        shares = cfg.get("shares", 0)
        if cost > 0:
            pnl_pct = (now_price - cost) / cost * 100
            pnl_amt = (now_price - cost) * shares
            print(f"\n#### 🛡️ 持仓风控与止损监控：")
            print(f"- **持仓底仓**：{shares} 股 | **持仓成本**：${cost:.2f}")
            print(f"- **当前盈亏**：`{pnl_pct:+.2f}%`（浮动损益: `${pnl_amt:+.2f}`）")
        if "trailing_stop_pct" in cfg:
            stop_px = cfg["stop_price"]
            peak = cfg["peak"]
            dist_to_stop = (now_price - stop_px) / now_price * 100
            print(f"- **移动止损线（8%）**：止损触发位 `${stop_px:.2f}`（参考高点 `${peak:.2f}`）")
            if now_price < stop_px:
                print(f"- **⚠️ 风险警报**：现价已跌破移动止损位 `${stop_px:.2f}`，执行防守纪律！")
            else:
                print(f"- **止损安全垫**：距止损位有 `{dist_to_stop:.2f}%` 缓冲垫。")

    print(f"\n#### 🎯 短线量价结构与买卖点：")
    pivot = (high + low + now_price) / 3
    r1 = 2 * pivot - low
    s1 = 2 * pivot - high
    print(f"- **日内阻力位 (R1)**：`{r1:.2f}` {currency}")
    print(f"- **日内支撑位 (S1)**：`{s1:.2f}` {currency}")
    
    if chg_pct > 3.0:
        print(f"- **量价形态研判**：日内放量拉升。防诱多纪律：观察能否守住今开 `{open_price:.2f}` 及分时均线。")
    elif chg_pct < -3.0:
        print(f"- **量价形态研判**：空头破位下探。处于超卖弱势区，建议防守观望。")
    else:
        print(f"- **量价形态研判**：区间箱体震荡。严格按支撑位 `{s1:.2f}` 与阻力位 `{r1:.2f}` 设置止盈止损。")

    print(f"- **失效条件**：若跌破今日最低价 `{low:.2f}`，短线做多逻辑失效。")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 stock_doctor.py <股票或币种代码>")
        sys.exit(1)
    analyze_stock(sys.argv[1])
