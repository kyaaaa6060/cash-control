import time
import requests
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

app = FastAPI(title="Cash Control Engine - Multi-Exchange (Hyperliquid, Binance, MEXC, OKX)", version="6.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CACHE = {
    "last_update": 0,
    "data": {}
}
CACHE_DURATION = 5

def get_binance_futures_tickers():
    try:
        url = "https://fapi.binance.com/fapi/v1/premiumIndex"
        res = requests.get(url, timeout=3)
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
        print("Binance hatası:", e)
    return {}

def get_okx_futures_tickers():
    try:
        url = "https://www.okx.com/api/v5/public/mark-price?instType=SWAP"
        res = requests.get(url, timeout=3)
        if res.status_code == 200:
            result = res.json()
            if result.get("code") == "0":
                tickers = {}
                for item in result.get("data", []):
                    inst_id = item.get("instId", "")
                    if "-USDT-" in inst_id:
                        base_name = inst_id.split("-")[0]
                        tickers[base_name] = {
                            "markPrice": float(item.get("markPx", 0)),
                            "fundingRate": 0.0
                        }
                return tickers
    except Exception as e:
        print("OKX hatası:", e)
    return {}

def get_mexc_futures_tickers():
    try:
        url = "https://contract.mexc.com/api/v1/contract/ticker"
        res = requests.get(url, timeout=3)
        if res.status_code == 200:
            result = res.json()
            if result.get("success"):
                tickers = {}
                for item in result.get("data", []):
                    symbol = item.get("symbol", "").replace("_USDT", "USDT")
                    base_name = symbol.replace("USDT", "")
                    tickers[base_name] = {
                        "markPrice": float(item.get("fairPrice", 0) or item.get("lastPrice", 0)),
                        "fundingRate": float(item.get("fundingRate", 0)) * 100,
                    }
                return tickers
    except Exception as e:
        print("MEXC hatası:", e)
    return {}

def fetch_karma_market_data():
    processed_coins = {}
    total_open_interest_usd = 0
    all_prices = []
    
    binance_data = get_binance_futures_tickers()
    okx_data = get_okx_futures_tickers()
    mexc_data = get_mexc_futures_tickers()
    
    hl_url = "https://api.hyperliquid.xyz/info"
    payload = {"type": "metaAndAssetCtxs"}
    
    try:
        res = requests.post(hl_url, json=payload, headers={"Content-Type": "application/json"}, timeout=5)
        if res.status_code == 200:
            data = res.json()
            universe = data[0].get("universe", [])
            ctxs = data[1]
            
            sources = ["copy", "whale", "all", "pct6_20"]
            
            for i, asset in enumerate(universe):
                name = asset.get("name")
                ctx = ctxs[i]
                hl_mark_px = float(ctx.get("markPx", 0))
                open_interest = float(ctx.get("openInterest", 0))
                hl_funding = float(ctx.get("funding", 0)) * 100

prices = []
                fundings = []
                
                if hl_mark_px > 0:
                    prices.append(hl_mark_px)
                    fundings.append(hl_funding)
                
                if name in binance_data and binance_data[name]["markPrice"] > 0:
                    prices.append(binance_data[name]["markPrice"])
                    fundings.append(binance_data[name]["fundingRate"])
                    
                if name in okx_data and okx_data[name]["markPrice"] > 0:
                    prices.append(okx_data[name]["markPrice"])
                    
                if name in mexc_data and mexc_data[name]["markPrice"] > 0:
                    prices.append(mexc_data[name]["markPrice"])
                    fundings.append(mexc_data[name]["fundingRate"])
                
                if not prices:
                    continue
                
                mark_px = sum(prices) / len(prices)
                funding = sum(fundings) / len(fundings) if fundings else hl_funding
                
                all_prices.append(mark_px)
                oi_usd = open_interest * mark_px
                total_open_interest_usd += oi_usd
                
                coin_sources_data = {}
                for src in sources:
                    multiplier = 1.0 if src == "all" else (0.95 if src == "whale" else 1.02)
                    
                    long_avg = mark_px * 0.985 * multiplier
                    short_avg = mark_px * 1.015 * multiplier
                    general_avg = (long_avg + short_avg) / 2
                    
                    long_count = int(1500 + (hash(name + src) % 1500))
                    short_count = int(800 + (hash(src + name) % 800))
                    long_size = (long_count * mark_px * 0.05)
                    short_size = (short_count * mark_px * 0.04)
                    
                    if src == "pct6_20":
                        long_avg = mark_px * 1.08
                        short_avg = mark_px * 0.92
                    
                    coin_sources_data[src] = {
                        "long_avg": long_avg,
                        "long_count": long_count,
                        "long_size": long_size,
                        "short_avg": short_avg,
                        "short_count": short_count,
                        "short_size": short_size,
                        "general_avg": general_avg
                    }

                if coin_sources_data:
                    all_src_list = list(coin_sources_data.values())
                    n_src = len(all_src_list)
                    coin_sources_data["combined_avg"] = {
                        "long_avg": sum(s["long_avg"] for s in all_src_list) / n_src,
                        "long_count": int(sum(s["long_count"] for s in all_src_list) / n_src),
                        "long_size": sum(s["long_size"] for s in all_src_list) / n_src,
                        "short_avg": sum(s["short_avg"] for s in all_src_list) / n_src,
                        "short_count": int(sum(s["short_count"] for s in all_src_list) / n_src),
                        "short_size": sum(s["short_size"] for s in all_src_list) / n_src,
                        "general_avg": sum(s["general_avg"] for s in all_src_list) / n_src
                    }

                processed_coins[name] = {
                    "symbol": f"{name}USDT",
                    "markPrice": mark_px,
                    "fundingRate": funding,
                    "openInterestUSD": oi_usd,
                    "sources": coin_sources_data
                }
            
            global_data = {
                "totalActiveCoins": len(processed_coins),
                "totalAUM_OI": total_open_interest_usd,

"avgMarketPrice": sum(all_prices) / len(all_prices) if all_prices else 0
            }
            
            processed_coins["_GLOBAL_SUMMARY_"] = global_data
            return processed_coins
    except Exception as e:
        print("Karma veri hatası:", e)
        
    return {}

@app.get("/", response_class=HTMLResponse)
def read_index():
    try:
        with open("index.html", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "<h3>index.html dosyası bulunamadı!</h3>"

@app.get("/api/coins")
def get_all_coins():
    global CACHE
    current_time = time.time()
    if current_time - CACHE["last_update"] > CACHE_DURATION or not CACHE["data"]:
        CACHE["data"] = fetch_karma_market_data()
        CACHE["last_update"] = current_time
    
    coins = [k for k in CACHE["data"].keys() if not k.startswith("_")]
    return {"status": "success", "coins": sorted(coins)}

@app.get("/api/market-stats/{symbol}")
def get_coin_stats(symbol: str):
    global CACHE
    current_time = time.time()
    if current_time - CACHE["last_update"] > CACHE_DURATION or not CACHE["data"]:
        CACHE["data"] = fetch_karma_market_data()
        CACHE["last_update"] = current_time
        
    symbol = symbol.upper()
    coin_data = CACHE["data"].get(symbol)
    global_data = CACHE["data"].get("_GLOBAL_SUMMARY_", {})
    
    if not coin_data:
        return {"status": "error", "message": "Coin bulunamadı"}
        
    return {
        "status": "success",
        "cache_remaining_seconds": int(CACHE_DURATION - (current_time - CACHE["last_update"])),
        "data": coin_data,
        "global": global_data
    }

if name == "main":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
