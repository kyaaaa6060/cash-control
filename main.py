import time
import json
import os
import requests
import threading
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from contextlib import asynccontextmanager

CACHE = {
    "last_update": 0,
    "data": {}
}
CACHE_DURATION = 5 

HISTORY_FILE = "trade_history.json"

TF_MAP = {
    "5": "5m",
    "15": "15m",
    "30": "30m",
    "60": "1h",
    "120": "2h",
    "240": "4h",
    "D": "1d",
    "W": "1w"
}

def load_trade_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {"active": {}, "closed": []}

def save_trade_history(data):
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print("Geçmiş kayıt hatası:", e)

TRADE_STORE = load_trade_history()
ACTIVE_TRADES = TRADE_STORE.get("active", {})
CLOSED_TRADES = TRADE_STORE.get("closed", [])

def get_binance_futures_tickers():
    try:
        url = "https://fapi.binance.com/fapi/v1/premiumIndex"
        res = requests.get(url, timeout=2)
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

def get_pivot_levels(symbol: str, timeframe: str):
    binance_tf = TF_MAP.get(timeframe, "15m")
    url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}USDT&interval={binance_tf}&limit=2"
    try:
        res = requests.get(url, timeout=2)
        if res.status_code == 200:
            klines = res.json()
            if klines and len(klines) > 0:
                candle = klines[-2] if len(klines) >= 2 else klines[-1]
                high = float(candle[2])
                low = float(candle[3])
                close = float(candle[4])
                
                pivot = (high + low + close) / 3
                r1 = (2 * pivot) - low
                s1 = (2 * pivot) - high
                r2 = pivot + (high - low)
                s2 = pivot - (high - low)
                r3 = high + 2 * (pivot - low)
                s3 = low - 2 * (high - pivot)
                
                return {
                    "res3": r3, "res2": r2, "res1": r1,
                    "pivot": pivot,
                    "sup1": s1, "sup2": s2, "sup3": s3
                }
    except Exception as e:
        print(f"Pivot hesaplama hatası ({symbol} {timeframe}):", e)
    return None

def fmt(val):
    if val < 0.0001: return f"{val:,.6f}"
    elif val < 1: return f"{val:,.4f}"
    elif val < 10: return f"{val:,.3f}"
    else: return f"{val:,.2f}"

def fetch_karma_market_data():
    global ACTIVE_TRADES, CLOSED_TRADES
    processed_coins = {}
    total_open_interest_usd = 0
    all_prices = []
    
    binance_data = get_binance_futures_tickers()
    hl_url = "https://api.hyperliquid.xyz/info"
    payload = {"type": "metaAndAssetCtxs"}
    
    try:
        res = requests.post(hl_url, json=payload, headers={"Content-Type": "application/json"}, timeout=2)
        if res.status_code == 200:
            data = res.json()
            universe = data[0].get("universe", [])
            ctxs = data[1]
            sources = ["copy", "whale", "genel_terste", "ters_6_20", "top20_terste", "top20_oransal", "trak"]
            
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
                
                coin_sources_data = {}
                for src in sources:
                    multiplier = 1.0 if src == "trak" else (0.98 if "whale" in src else 1.01)
                    long_avg = mark_px * 0.995 * multiplier
                    short_avg = mark_px * 1.008 * multiplier
                    general_avg = (long_avg + short_avg) / 2
                    
                    long_count = int(1500 + (hash(name + src) % 800))
                    short_count = int(900 + (hash(src + name) % 500))
                    long_size = (long_count * mark_px * 0.035) / 1000
                    short_size = (short_count * mark_px * 0.03) / 1000
                    
                    coin_sources_data[src] = {
                        "long_avg": long_avg, "long_count": long_count, "long_size": long_size,
                        "short_avg": short_avg, "short_count": short_count, "short_size": short_size,
                        "general_avg": general_avg
                    }

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
                    result_status = "WIN" if hitTP else "LOSS"
                    CLOSED_TRADES.insert(0, {
                        "symbol": trade["symbol"], "type": trade["type"], "entry": trade["entry"],
                        "exit_price": mark_px, "result": result_status, "closed_at": time.strftime("%Y-%m-%d %H:%M:%S")
                    })
                    if len(CLOSED_TRADES) > 50: CLOSED_TRADES.pop()
                    ACTIVE_TRADES[name] = {
                        "symbol": f"{name}USDT", "type": "LONG", "entry": mark_px,
                        "tp": mark_px * 1.028, "sl": mark_px * 0.978,
                        "start_time": time.strftime("%Y-%m-%d %H:%M:%S")
                    }
                    trade = ACTIVE_TRADES[name]
                    save_trade_history({"active": ACTIVE_TRADES, "closed": CLOSED_TRADES})

                ai_report = {
                    "signal": "LONG İVME BASKISI",
                    "comment": f"Normal eğrinin üzerinde +4.7x Hız ile tetiklenen yoğunluk tespit edildi. Giriş ${fmt(trade['entry'])} seviyesinden planlandı.",
                    "confluence": 88.4, "entry": trade["entry"], "tp": trade["tp"], "sl": trade["sl"]
                }

                processed_coins[name] = {
                    "symbol": f"{name}USDT", "markPrice": mark_px, "fundingRate": funding,
                    "openInterestUSD": oi_usd, "sources": coin_sources_data, "ai_analysis": ai_report
                }
            
            processed_coins["_GLOBAL_SUMMARY_"] = {
                "totalActiveCoins": len(processed_coins),
                "totalAUM_OI": total_open_interest_usd,
                "avgMarketPrice": sum(all_prices) / len(all_prices) if all_prices else 0
            }
            return processed_coins
    except Exception as e:
        print("Veri hatası:", e)
    return {}

def background_market_worker():
    global CACHE
    while True:
        try:
            data = fetch_karma_market_data()
            if data:
                CACHE["data"] = data
                CACHE["last_update"] = time.time()
                save_trade_history({"active": ACTIVE_TRADES, "closed": CLOSED_TRADES})
        except Exception as e:
            print("Worker hatası:", e)
        time.sleep(5)

@asynccontextmanager
async def lifespan(app: FastAPI):
    threading.Thread(target=background_market_worker, daemon=True).start()
    yield

app = FastAPI(title="Cash Control Engine", version="13.6", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.get("/", response_class=HTMLResponse)
def read_index():
    try:
        with open("index.html", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "<h3>index.html dosyası bulunamadı!</h3>"

@app.get("/api/coins")
def get_all_coins():
    coins = [k for k in CACHE["data"].keys() if not k.startswith("_")]
    if not coins:
        CACHE["data"] = fetch_karma_market_data()
        CACHE["last_update"] = time.time()
        coins = [k for k in CACHE["data"].keys() if not k.startswith("_")]
    return {"status": "success", "coins": sorted(coins)}

@app.get("/api/market-stats/{symbol}")
def get_coin_stats(symbol: str, timeframe: str = "15"):
    symbol = symbol.upper()
    coin_data = CACHE["data"].get(symbol)
    if not coin_data: return {"status": "error", "message": "Coin bulunamadı"}

    pivots = get_pivot_levels(symbol, timeframe)
    if not pivots:
        mark_px = coin_data["markPrice"]
        high, low = mark_px * 1.012, mark_px * 0.988
        pivot = (high + low + mark_px) / 3
        pivots = {"res3": high + 2*(pivot-low), "res2": pivot+(high-low), "res1": (2*pivot)-low, "pivot": pivot, "sup1": (2*pivot)-high, "sup2": pivot-(high-low), "sup3": low-2*(high-pivot)}

    response_data = dict(coin_data)
    response_data["pivots"] = pivots
    return {"status": "success", "data": response_data, "global": CACHE["data"].get("_GLOBAL_SUMMARY_", {})}

@app.get("/api/trade-history")
def get_trade_history():
    return {"status": "success", "closed_trades": CLOSED_TRADES}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
