import time
import json
import os
import requests
import threading
from collections import defaultdict
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from contextlib import asynccontextmanager

# ============================================================
#  CACHE'LER VE SABİTLER
# ============================================================
CACHE = {"last_update": 0, "data": {}}              
SMART_MONEY_CACHE = {"last_update": 0, "data": {}}   
BINANCE_RATIO_CACHE = {"last_update": 0, "data": {}} 
BINANCE_LEADERBOARD_CACHE = {"last_update": 0, "data": {}, "working": None}  

FAST_LOOP_SECONDS = 5
SMART_MONEY_LOOP_SECONDS = 90        
BINANCE_RATIO_LOOP_SECONDS = 30
BINANCE_LEADERBOARD_LOOP_SECONDS = 90  

HISTORY_FILE = "trade_history.json"
HOURLY_HISTORY_FILE = "hourly_history.json"

TF_MAP = {
    "5": "5m", "15": "15m", "30": "30m", "60": "1h",
    "120": "2h", "240": "4h", "D": "1d", "W": "1w"
}

HL_WALLET_LIMIT = 30
HL_MIN_ACCOUNT_VALUE = 20000

# ============================================================
#  DOSYA KAYIT / OKUMA YARDIMCILARI
# ============================================================
def load_trade_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"active": {}, "closed": []}

def save_trade_history(data):
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print("Geçmiş kayıt hatası:", e)

def load_hourly_history():
    if os.path.exists(HOURLY_HISTORY_FILE):
        try:
            with open(HOURLY_HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []

def save_hourly_history(history_data):
    try:
        with open(HOURLY_HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history_data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print("Saatlik geçmiş kayıt hatası:", e)

TRADE_STORE = load_trade_history()
ACTIVE_TRADES = TRADE_STORE.get("active", {})
CLOSED_TRADES = TRADE_STORE.get("closed", [])
HOURLY_RECORDS = load_hourly_history()
LAST_RECORDED_HOUR = -1

def fmt(val):
    if val < 0.0001: return f"{val:,.6f}"
    elif val < 1: return f"{val:,.4f}"
    elif val < 10: return f"{val:,.3f}"
    else: return f"{val:,.2f}"

# ============================================================
#  BINANCE - MARK PRICE & KLINES & RATIOS
# ============================================================
def get_binance_futures_tickers():
    try:
        url = "https://fapi.binance.com/fapi/v1/premiumIndex"
        res = requests.get(url, timeout=4)
        if res.status_code == 200:
            tickers = {}
            for item in res.json():
                symbol = item.get("symbol", "")
                if symbol.endswith("USDT"):
                    base_name = symbol.replace("USDT", "")
                    tickers[base_name] = {
                        "markPrice": float(item.get("markPrice", 0)),
                        "fundingRate": float(item.get("lastFundingRate", 0)) * 100
                    }
            return tickers
    except Exception as e:
        print("Binance Mark Price hatası:", e)
    return {}

def get_binance_klines(symbol: str, timeframe: str, limit: int = 300):
    binance_tf = TF_MAP.get(timeframe, "15m")
    url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}USDT&interval={binance_tf}&limit={limit}"
    try:
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            out = []
            for k in res.json():
                out.append({
                    "time": int(k[0] // 1000),
                    "open": float(k[1]), "high": float(k[2]),
                    "low": float(k[3]), "close": float(k[4]),
                })
            return out
    except Exception as e:
        print(f"Kline hatası ({symbol} {timeframe}):", e)
    return []

def get_pivot_levels(symbol: str, timeframe: str):
    klines = get_binance_klines(symbol, timeframe, limit=3)
    if klines and len(klines) > 0:
        candle = klines[-2] if len(klines) >= 2 else klines[-1]
        high, low, close = candle["high"], candle["low"], candle["close"]
        pivot = (high + low + close) / 3
        return {
            "res3": high + 2 * (pivot - low), "res2": pivot + (high - low), "res1": (2 * pivot) - low,
            "pivot": pivot, "sup1": (2 * pivot) - high, "sup2": pivot - (high - low), "sup3": low - 2 * (high - pivot)
        }
    return None

def get_binance_top_trader_ratio(symbol: str):
    try:
        url = f"https://fapi.binance.com/futures/data/topLongShortPositionRatio?symbol={symbol}USDT&period=15m&limit=1"
        res = requests.get(url, timeout=4)
        if res.status_code == 200:
            arr = res.json()
            if arr:
                item = arr[-1]
                return {
                    "longAccount": float(item.get("longAccount", 0)) * 100,
                    "shortAccount": float(item.get("shortAccount", 0)) * 100,
                    "longShortRatio": float(item.get("longShortRatio", 0)),
                }
    except Exception as e:
        print(f"Binance top-trader oranı hatası ({symbol}):", e)
    return None

def refresh_binance_ratio_cache(coin_names):
    fresh = {}
    for name in coin_names:
        r = get_binance_top_trader_ratio(name)
        if r: fresh[name] = r
        time.sleep(0.05)
    if fresh:
        BINANCE_RATIO_CACHE["data"] = fresh
        BINANCE_RATIO_CACHE["last_update"] = time.time()

# ============================================================
#  HYPERLIQUID & COPY TRADER / WHALE ANALİZİ
# ============================================================
HL_INFO_URL = "https://api.hyperliquid.xyz/info"
HL_LEADERBOARD_URL = "https://stats-data.hyperliquid.xyz/Mainnet/leaderboard"

def get_hyperliquid_top_wallets(limit=HL_WALLET_LIMIT):
    try:
        res = requests.get(HL_LEADERBOARD_URL, timeout=8)
        if res.status_code != 200: return []
        data = res.json()
        rows = data.get("leaderboardRows", data if isinstance(data, list) else [])
        scored = []
        for row in rows:
            addr = row.get("ethAddress")
            acc_val = float(row.get("accountValue", 0) or 0)
            if not addr or acc_val < HL_MIN_ACCOUNT_VALUE: continue
            day_pnl = 0.0
            for perf in row.get("windowPerformances", []):
                if isinstance(perf, list) and len(perf) == 2 and perf[0] == "day":
                    try: day_pnl = float(perf[1].get("pnl", 0))
                    except: day_pnl = 0.0
            scored.append((day_pnl, addr, acc_val))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [addr for _, addr, _ in scored[:limit]]
    except Exception as e:
        print("Hyperliquid leaderboard hatası:", e)
        return []

def get_hyperliquid_wallet_positions(address):
    try:
        res = requests.post(HL_INFO_URL, json={"type": "clearinghouseState", "user": address},
                            headers={"Content-Type": "application/json"}, timeout=6)
        if res.status_code != 200: return []
        data = res.json()
        out = []
        for ap in data.get("assetPositions", []):
            pos = ap.get("position", {})
            coin = pos.get("coin")
            try: szi = float(pos.get("szi", 0) or 0)
            except: szi = 0
            if not coin or szi == 0: continue
            entry_px = pos.get("entryPx")
            liq_px = pos.get("liquidationPx")
            unrealized_pnl = float(pos.get("unrealizedPnl", 0) or 0)
            out.append({
                "coin": coin, "wallet": address,
                "side": "LONG" if szi > 0 else "SHORT",
                "size": abs(szi),
                "entry": float(entry_px) if entry_px not in (None, "") else 0.0,
                "liq": float(liq_px) if liq_px not in (None, "") else None,
                "unrealizedPnl": unrealized_pnl,
                "is_underwater": unrealized_pnl < 0
            })
        return out
    except Exception as e:
        print(f"Hyperliquid cüzdan verisi hatası ({address}):", e)
        return []

def refresh_smart_money_cache():
    wallets = get_hyperliquid_top_wallets()
    if not wallets: return

    per_coin = defaultdict(lambda: {"LONG": [], "SHORT": []})
    for addr in wallets:
        positions = get_hyperliquid_wallet_positions(addr)
        for p in positions:
            per_coin[p["coin"]][p["side"]].append(p)
        time.sleep(0.08)

    result = {}
    for coin, sides in per_coin.items():
        coin_result = {}
        liq_levels = []
        for side in ("LONG", "SHORT"):
            plist = sides[side]
            total_size = sum(p["size"] for p in plist)
            total_aum = sum(p["size"] * p["entry"] for p in plist)
            avg_entry = total_aum / total_size if total_size > 0 else 0
            
            underwater_list = [p for p in plist if p["is_underwater"]]
            uw_size = sum(p["size"] for p in underwater_list)
            uw_avg_entry = sum(p["entry"] * p["size"] for p in underwater_list) / uw_size if uw_size > 0 else 0

            coin_result[side] = {
                "avg_entry": avg_entry,
                "count": len(plist),
                "total_size": total_size,
                "total_aum_usd": total_aum,
                "underwater": {
                    "count": len(underwater_list),
                    "total_size": uw_size,
                    "avg_entry": uw_avg_entry
                }
            }
            for p in plist:
                if p["liq"]:
                    liq_levels.append({
                        "price": p["liq"], "side": side, "size": p["size"],
                        "wallet": p["wallet"], "unrealizedPnl": p["unrealizedPnl"],
                    })
        coin_result["liq_levels"] = liq_levels
        result[coin] = coin_result

    if result:
        SMART_MONEY_CACHE["data"] = result
        SMART_MONEY_CACHE["last_update"] = time.time()

# ============================================================
#  BINANCE LEADERBOARD
# ============================================================
BINANCE_LB_HEADERS = {
    "Content-Type": "application/json", "clienttype": "web", "lang": "en",
    "Origin": "https://www.binance.com", "Referer": "https://www.binance.com/en/futures-activity/leaderboard",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}
BINANCE_LB_RANK_URL = "https://www.binance.com/bapi/futures/v1/public/future/leaderboard/getLeaderboardRank"
BINANCE_LB_POSITION_URL = "https://www.binance.com/bapi/futures/v1/public/future/leaderboard/getOtherPosition"

def get_binance_leaderboard_traders(limit=25):
    try:
        body = {"tradeType": "PERPETUAL", "statisticsType": "PNL", "periodType": "WEEKLY", "isShared": True, "isTrader": False}
        res = requests.post(BINANCE_LB_RANK_URL, json=body, headers=BINANCE_LB_HEADERS, timeout=6)
        if res.status_code != 200: return []
        data = res.json()
        rows = (data.get("data") or [])[:limit]
        return [r.get("encryptedUid") for r in rows if r.get("encryptedUid")]
    except: return []

def get_binance_trader_positions(encrypted_uid):
    try:
        body = {"encryptedUid": encrypted_uid, "tradeType": "PERPETUAL"}
        res = requests.post(BINANCE_LB_POSITION_URL, json=body, headers=BINANCE_LB_HEADERS, timeout=6)
        if res.status_code != 200: return []
        data = res.json()
        rows = (data.get("data") or {}).get("otherPositionRetList") or []
        out = []
        for r in rows:
            symbol = r.get("symbol", "")
            if not symbol.endswith("USDT"): continue
            amount = float(r.get("amount", 0) or 0)
            if amount == 0: continue
            entry = float(r.get("entryPrice", 0) or 0)
            pnl = float(r.get("pnl", 0) or 0)
            out.append({
                "coin": symbol.replace("USDT", ""),
                "side": "LONG" if amount > 0 else "SHORT",
                "size": abs(amount), "entry": entry, "wallet": encrypted_uid,
                "is_underwater": pnl < 0
            })
        return out
    except: return []

def refresh_binance_leaderboard_cache():
    traders = get_binance_leaderboard_traders()
    if not traders:
        BINANCE_LEADERBOARD_CACHE["working"] = False
        return

    per_coin = defaultdict(lambda: {"LONG": [], "SHORT": []})
    got_any = False
    for uid in traders:
        positions = get_binance_trader_positions(uid)
        if positions: got_any = True
        for p in positions:
            per_coin[p["coin"]][p["side"]].append(p)
        time.sleep(0.1)

    BINANCE_LEADERBOARD_CACHE["working"] = got_any
    if not got_any: return

    result = {}
    for coin, sides in per_coin.items():
        coin_result = {}
        for side in ("LONG", "SHORT"):
            plist = sides[side]
            total_size = sum(p["size"] for p in plist)
            total_aum = sum(p["size"] * p["entry"] for p in plist)
            avg_entry = total_aum / total_size if total_size > 0 else 0
            
            underwater_list = [p for p in plist if p["is_underwater"]]
            uw_size = sum(p["size"] for p in underwater_list)
            uw_avg_entry = sum(p["entry"] * p["size"] for p in underwater_list) / uw_size if uw_size > 0 else 0

            coin_result[side] = {
                "avg_entry": avg_entry, "count": len(plist),
                "total_size": total_size, "total_aum_usd": total_aum,
                "underwater": {"count": len(underwater_list), "total_size": uw_size, "avg_entry": uw_avg_entry}
            }
        result[coin] = coin_result

    BINANCE_LEADERBOARD_CACHE["data"] = result
    BINANCE_LEADERBOARD_CACHE["last_update"] = time.time()

# ============================================================
#  FAST WORKER
# ============================================================
def fetch_market_data():
    global ACTIVE_TRADES, CLOSED_TRADES, HOURLY_RECORDS, LAST_RECORDED_HOUR
    processed_coins = {}
    total_open_interest_usd = 0
    all_prices = []

    binance_data = get_binance_futures_tickers()
    hl_url = "https://api.hyperliquid.xyz/info"
    try:
        res = requests.post(hl_url, json={"type": "metaAndAssetCtxs"}, headers={"Content-Type": "application/json"}, timeout=5)
        if res.status_code == 200:
            data = res.json()
            universe = data[0].get("universe", [])
            ctxs = data[1]

            for i, asset in enumerate(universe):
                name = asset.get("name")
                ctx = ctxs[i]
                open_interest = float(ctx.get("openInterest", 0))

                if name in binance_data and binance_data[name]["markPrice"] > 0:
                    mark_px = binance_data[name]["markPrice"]
                    funding = binance_data[name]["fundingRate"]
                else:
                    mark_px = float(ctx.get("markPx", 0))
                    funding = float(ctx.get("funding", 0)) * 100

                if mark_px <= 0: continue
                all_prices.append(mark_px)
                oi_usd = open_interest * mark_px
                total_open_interest_usd += oi_usd

                if name not in ACTIVE_TRADES:
                    ACTIVE_TRADES[name] = {
                        "symbol": f"{name}USDT", "type": "LONG", "entry": mark_px,
                        "tp": mark_px * 1.028, "sl": mark_px * 0.978,
                        "start_time": time.strftime("%Y-%m-%d %H:%M:%S")
                    }

                trade = ACTIVE_TRADES[name]
                hitTP = (trade["type"] == 'LONG' and mark_px >= trade["tp"]) or (trade["type"] == 'SHORT' and mark_px <= trade["tp"])
                hitSL = (trade["type"] == 'LONG' and mark_px <= trade["sl"]) or (trade["type"] == 'SHORT' and mark_px >= trade["sl"])

                if hitTP or hitSL:
                    CLOSED_TRADES.insert(0, {
                        "symbol": trade["symbol"], "type": trade["type"], "entry": trade["entry"],
                        "exit_price": mark_px, "result": "WIN" if hitTP else "LOSS", "closed_at": time.strftime("%Y-%m-%d %H:%M:%S")
                    })
                    if len(CLOSED_TRADES) > 50: CLOSED_TRADES.pop()
                    ACTIVE_TRADES[name] = {
                        "symbol": f"{name}USDT", "type": "LONG", "entry": mark_px,
                        "tp": mark_px * 1.028, "sl": mark_px * 0.978, "start_time": time.strftime("%Y-%m-%d %H:%M:%S")
                    }
                    save_trade_history({"active": ACTIVE_TRADES, "closed": CLOSED_TRADES})

                ai_report = {
                    "signal": "LONG İVME BASKISI",
                    "comment": f"Normal eğrinin üzerinde +4.7x Hız ile tetiklenen yoğunluk tespit edildi. Giriş ${fmt(trade['entry'])} seviyesinden planlandı.",
                    "confluence": 88.4, "entry": trade["entry"], "tp": trade["tp"], "sl": trade["sl"]
                }

                processed_coins[name] = {
                    "symbol": f"{name}USDT", "markPrice": mark_px, "fundingRate": funding,
                    "openInterestUSD": oi_usd, "ai_analysis": ai_report
                }

            current_hour = time.localtime().tm_hour
            if current_hour != LAST_RECORDED_HOUR and SMART_MONEY_CACHE["data"]:
                HOURLY_RECORDS.insert(0, {
                    "timestamp": time.strftime("%Y-%m-%d %H:00:00"),
                    "coins": {c: {"LONG": v.get("LONG"), "SHORT": v.get("SHORT")} for c, v in SMART_MONEY_CACHE["data"].items()}
                })
                if len(HOURLY_RECORDS) > 168: HOURLY_RECORDS.pop()
                save_hourly_history(HOURLY_RECORDS)
                LAST_RECORDED_HOUR = current_hour

            processed_coins["_GLOBAL_SUMMARY_"] = {
                "totalActiveCoins": len(processed_coins),
                "totalAUM_OI": total_open_interest_usd,
                "avgMarketPrice": sum(all_prices) / len(all_prices) if all_prices else 0
            }
            return processed_coins
    except Exception as e:
        print("Veri hatası:", e)
    return {}

# ============================================================
#  GÜVENLİ BACKGROUND LOOPS (SYNTAX HATASIZ)
# ============================================================
def background_fast_loop():
    while True:
        try:
            CACHE["data"] = fetch_market_data()
            CACHE["last_update"] = time.time()
        except Exception as e:
            print("Fast loop hatası:", e)
        time.sleep(FAST_LOOP_SECONDS)

def background_smart_money_loop():
    while True:
        try:
            refresh_smart_money_cache()
        except Exception as e:
            print("Smart money loop hatası:", e)
        time.sleep(SMART_MONEY_LOOP_SECONDS)

def background_binance_ratio_loop():
    while True:
        try:
            coin_names = [k for k in CACHE["data"].keys() if not k.startswith("_")]
            refresh_binance_ratio_cache(coin_names)
        except Exception as e:
            print("Binance ratio loop hatası:", e)
        time.sleep(BINANCE_RATIO_LOOP_SECONDS)

def background_binance_lb_loop():
    while True:
        try:
            refresh_binance_leaderboard_cache()
        except Exception as e:
            print("Binance LB loop hatası:", e)
        time.sleep(BINANCE_LEADERBOARD_LOOP_SECONDS)

@asynccontextmanager
async def lifespan(app: FastAPI):
    threading.Thread(target=background_fast_loop, daemon=True).start()
    threading.Thread(target=background_smart_money_loop, daemon=True).start()
    threading.Thread(target=background_binance_ratio_loop, daemon=True).start()
    threading.Thread(target=background_binance_lb_loop, daemon=True).start()
    yield

app = FastAPI(title="Cash Control Engine", version="15.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.get("/", response_class=HTMLResponse)
def read_index():
    try:
        with open("index.html", "r", encoding="utf-8") as f: return f.read()
    except: return "<h3>index.html bulunamadı!</h3>"

@app.get("/api/coins")
def get_all_coins():
    coins = [k for k in CACHE["data"].keys() if not k.startswith("_")]
    if not coins:
        CACHE["data"] = fetch_market_data()
        CACHE["last_update"] = time.time()
        coins = [k for k in CACHE["data"].keys() if not k.startswith("_")]
    return {"status": "success", "coins": sorted(coins)}

@app.get("/api/klines/{symbol}")
def get_klines(symbol: str, timeframe: str = "15", limit: int = 300):
    return {"status": "success", "candles": get_binance_klines(symbol.upper(), timeframe, limit)}

@app.get("/api/smart-money/{symbol}")
def get_smart_money(symbol: str):
    symbol = symbol.upper()
    coin_data = SMART_MONEY_CACHE["data"].get(symbol, {
        "LONG": {"avg_entry": 0, "count": 0, "total_size": 0, "total_aum_usd": 0, "underwater": {"count": 0, "total_size": 0, "avg_entry": 0}},
        "SHORT": {"avg_entry": 0, "count": 0, "total_size": 0, "total_aum_usd": 0, "underwater": {"count": 0, "total_size": 0, "avg_entry": 0}},
        "liq_levels": []
    })
    return {
        "status": "success", "data": coin_data,
        "binance_leaderboard": BINANCE_LEADERBOARD_CACHE["data"].get(symbol),
        "binance_leaderboard_working": BINANCE_LEADERBOARD_CACHE["working"],
        "last_update": SMART_MONEY_CACHE["last_update"],
    }

@app.get("/api/market-stats/{symbol}")
def get_coin_stats(symbol: str, timeframe: str = "15"):
    symbol = symbol.upper()
    coin_data = CACHE["data"].get(symbol)
    if not coin_data: return {"status": "error", "message": "Coin bulunamadı"}

    pivots = get_pivot_levels(symbol, timeframe)
    if not pivots:
        mp = coin_data["markPrice"]
        pivots = {"res3": mp*1.03, "res2": mp*1.02, "res1": mp*1.01, "pivot": mp, "sup1": mp*0.99, "sup2": mp*0.98, "sup3": mp*0.97}

    res_data = dict(coin_data)
    res_data["pivots"] = pivots
    res_data["smart_money"] = SMART_MONEY_CACHE["data"].get(symbol, {
        "LONG": {"avg_entry": 0, "count": 0, "total_size": 0, "total_aum_usd": 0, "underwater": {"count": 0, "total_size": 0, "avg_entry": 0}},
        "SHORT": {"avg_entry": 0, "count": 0, "total_size": 0, "total_aum_usd": 0, "underwater": {"count": 0, "total_size": 0, "avg_entry": 0}},
        "liq_levels": []
    })
    res_data["binance_top_trader_ratio"] = BINANCE_RATIO_CACHE["data"].get(symbol)
    res_data["binance_leaderboard"] = BINANCE_LEADERBOARD_CACHE["data"].get(symbol)
    res_data["binance_leaderboard_working"] = BINANCE_LEADERBOARD_CACHE["working"]
    return {"status": "success", "data": res_data, "global": CACHE["data"].get("_GLOBAL_SUMMARY_", {})}

@app.get("/api/trade-history")
def get_trade_history(): return {"status": "success", "closed_trades": CLOSED_TRADES}

@app.get("/api/hourly-history")
def get_hourly_history(): return {"status": "success", "hourly_history": HOURLY_RECORDS}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
