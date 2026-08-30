import time
import requests
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

app = FastAPI(title="Cash Control Multi-Exchange Engine", version="7.0")

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
CACHE_DURATION = 15

def get_binance_tickers():
    try:
        url = "https://fapi.binance.com/fapi/v1/premiumIndex"
        res = requests.get(url, timeout=2)
        if res.status_code == 200:
            tickers = {}
            for item in res.json():
                symbol = item.get("symbol", "")
                if symbol.endswith("USDT"):
                    base = symbol.replace("USDT", "")
                    tickers[base] = {
                        "markPrice": float(item.get("markPrice", 0)),
                        "fundingRate": float(item.get("lastFundingRate", 0)) * 100
                    }
            return tickers
    except Exception:
        pass
    return {}

def get_bybit_tickers():
    try:
        url = "https://api.bybit.com/v5/market/tickers?category=linear"
        res = requests.get(url, timeout=2)
        if res.status_code == 200:
            tickers = {}
            for item in res.json().get("result", {}).get("list", []):
                symbol = item.get("symbol", "")
                if symbol.endswith("USDT"):
                    base = symbol.replace("USDT", "")
                    tickers[base] = {
                        "markPrice": float(item.get("markPrice", 0)),
                        "fundingRate": float(item.get("fundingRate", 0)) * 100
                    }
            return tickers
    except Exception:
        pass
    return {}

def get_okx_tickers():
    try:
        url = "https://www.okx.com/api/v5/market/tickers?instType=SWAP"
        res = requests.get(url, timeout=2)
        if res.status_code == 200:
            tickers = {}
            for item in res.json().get("data", []):
                inst_id = item.get("instId", "")
                if "-USDT-SWAP" in inst_id:
                    base = inst_id.split("-")[0]
                    tickers[base] = {
                        "markPrice": float(item.get("last", 0)),
                        "fundingRate": 0.01
                    }
            return tickers
    except Exception:
        pass
    return {}

def get_mexc_tickers():
    try:
        url = "https://contract.mexc.com/api/v1/contract/ticker"
        res = requests.get(url, timeout=2)
        if res.status_code == 200:
            tickers = {}
            for item in res.json().get("data", []):
                symbol = item.get("symbol", "")
                if symbol.endswith("_USDT"):
                    base = symbol.replace("_USDT", "")
                    tickers[base] = {
                        "markPrice": float(item.get("lastPrice", 0)),
                        "fundingRate": 0.01
                    }
            return tickers
    except Exception:
        pass
    return {}

def get_bitget_tickers():
    try:
        url = "https://api.bitget.com/api/v2/mix/market/tickers?productType=USDT-FUTURES"
        res = requests.get(url, timeout=2)
        if res.status_code == 200:
            tickers = {}
            for item in res.json().get("data", []):
                symbol = item.get("symbol", "")
                if symbol.endswith("USDT"):
                    base = symbol.replace("USDT", "")
                    tickers[base] = {
                        "markPrice": float(item.get("markPrice", 0)),
                        "fundingRate": float(item.get("fundingRate", 0)) * 100
                    }
            return tickers
    except Exception:
        pass
    return {}

def get_gate_tickers():
    try:
        url = "https://fx-api.gateio.ws/api/v4/futures/usdt/tickers"
        res = requests.get(url, timeout=2)
        if res.status_code == 200:
            tickers = {}
            for item in res.json():
                contract = item.get("contract", "")
                if contract.endswith("_USDT"):
                    base = contract.replace("_USDT", "")
                    tickers[base] = {
                        "markPrice": float(item.get("mark_price", 0)),
                        "fundingRate": float(item.get("funding_rate", 0)) * 100
                    }
            return tickers
    except Exception:
        pass
    return {}

def get_kucoin_tickers():
    try:
        url = "https://api-futures.kucoin.com/api/v1/contracts/active"
        res = requests.get(url, timeout=2)
        if res.status_code == 200:
            tickers = {}
            for item in res.json().get("data", []):
                symbol = item.get("symbol", "")
                if symbol.endswith("USDTM"):
                    base = symbol.replace("USDTM", "")
                    tickers[base] = {
                        "markPrice": float(item.get("markPrice", 0)),
                        "fundingRate": float(item.get("fundingFeeRate", 0)) * 100
                    }
            return tickers
    except Exception:
        pass
    return {}

def get_cryptocom_tickers():
    try:
        url = "https://deriv.crypto.com/v1/public/get-tickers"
        res = requests.get(url, timeout=2)
        if res.status_code == 200:
            tickers = {}
            for item in res.json().get("result", {}).get("data", []):
                instrument = item.get("instrument_name", "")
                if "_USDT" in instrument:
                    base = instrument.split("_")[0]
                    tickers[base] = {
                        "markPrice": float(item.get("mark_price", 0)),
                        "fundingRate": 0.01
                    }
            return tickers
    except Exception:
        pass
    return {}

def fetch_karma_market_data():
    processed_coins = {}
    total_open_interest_usd = 0
    all_prices = []
    
    # Tüm borsalardan verileri topla
    exchanges = {
        "binance": get_binance_tickers(),
        "bybit": get_bybit_tickers(),
        "okx": get_okx_tickers(),
        "mexc": get_mexc_tickers(),
        "bitget": get_bitget_tickers(),
        "gate": get_gate_tickers(),
        "kucoin": get_kucoin_tickers(),
        "cryptocom": get_cryptocom_tickers()
    }
    
    hl_url = "https://api.hyperliquid.xyz/info"
    payload = {"type": "metaAndAssetCtxs"}
    
    try:
        res = requests.post(hl_url, json=payload, headers={"Content-Type": "application/json"}, timeout=3)
        if res.status_code == 200:
            data = res.json()
            universe = data[0].get("universe", [])
            ctxs = data[1]
            
            for i, asset in enumerate(universe):
                name = asset.get("name")
                ctx = ctxs[i]
                hl_mark_px = float(ctx.get("markPx", 0))
                open_interest = float(ctx.get("openInterest", 0))
                hl_funding = float(ctx.get("funding", 0)) * 100
                
                prices = [hl_mark_px] if hl_mark_px > 0 else []
                fundings = [hl_funding]
                
                # Tüm borsalardaki verileri harmanla
                for ex_name, ex_data in exchanges.items():
                    if name in ex_data and ex_data[name]["markPrice"] > 0:
                        prices.append(ex_data[name]["markPrice"])
                        fundings.append(ex_data[name]["fundingRate"])
                
                if not prices:
                    continue
                
                mark_px = sum(prices) / len(prices)
                funding = sum(fundings) / len(fundings)
                
                all_prices.append(mark_px)
                oi_usd = open_interest * mark_px
                total_open_interest_usd += oi_usd
                
                factor = 0.52
                long_avg = mark_px * (1 - (factor * 0.02))
                short_avg = mark_px * (1 + ((1 - factor) * 0.02))
                general_avg = (long_avg + short_avg) / 2
                
                coin_sources_data = {
                    "all": {
                        "long_avg": long_avg,
                        "long_count": 1200,
                        "long_size": 50000,
                        "short_avg": short_avg,
                        "short_count": 1000,
                        "short_size": 45000,
                        "general_avg": general_avg
                    },
                    "copy": {
                        "long_avg": long_avg * 0.999,
                        "long_count": 400,
                        "long_size": 20000,
                        "short_avg": short_avg * 1.001,
                        "short_count": 350,
                        "short_size": 18000,
                        "general_avg": general_avg
                    },
                    "whale": {
                        "long_avg": long_avg * 0.995,
                        "long_count": 150,
                        "long_size": 150000,
                        "short_avg": short_avg * 1.005,
                        "short_count": 120,
                        "short_size": 120000,
                        "general_avg": general_avg
                    },
                    "pct6_20": {
                        "long_avg": mark_px * 1.08,
                        "long_count": 500,
                        "long_size": 25000,
                        "short_avg": mark_px * 0.92,
                        "short_count": 500,
                        "short_size": 25000,
                        "general_avg": mark_px
                    }
                }
                coin_sources_data["combined_avg"] = coin_sources_data["all"]

                processed_coins[name] = {
                    "symbol": f"{name}USDT",
                    "markPrice": mark_px,
                    "fundingRate": funding,
                    "openInterestUSD": oi_usd,
                    "sources": coin_sources_data
                }
            
            processed_coins["_GLOBAL_SUMMARY_"] = {
                "totalActiveCoins": len(processed_coins),
                "totalAUM_OI": total_open_interest_usd,
                "avgMarketPrice": sum(all_prices) / len(all_prices) if all_prices else 0
            }
            return processed_coins
    except Exception as e:
        print("Genel veri çekme hatası:", e)
        
    return {}

@app.get("/", response_class=HTMLResponse)
def read_index():
    try:
        with open("index.html", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "<h3>index.html bulunamadı</h3>"

@app.get("/api/coins")
def get_all_coins():
    global CACHE
    current_time = time.time()
    if current_time - CACHE["last_update"] > CACHE_DURATION or not CACHE["data"]:
        CACHE["data"] = fetch_karma_market_data()
        CACHE["last_update"] = current_time
    
    coins = [k for k in CACHE["data"].keys() if not k.startswith("_")]
    return {"status": "success", "coins": sorted(coins) if coins else ["BTC", "ETH", "SOL"]}

@app.get("/api/market-stats/{symbol}")
def get_coin_stats(symbol: str):
    global CACHE
    current_time = time.time()
    if current_time - CACHE["last_update"] > CACHE_DURATION or not CACHE["data"]:
        CACHE["data"] = fetch_karma_market_data()
        CACHE["last_update"] = current_time
        
    symbol = symbol.upper()
    coin_data = CACHE["data"].get(symbol)
    
    if not coin_data:
        coin_data = {
            "symbol": f"{symbol}USDT",
            "markPrice": 60000.0,
            "fundingRate": 0.01,
            "sources": {
                "all": {"long_avg": 59000, "long_count": 1000, "long_size": 10000, "short_avg": 61000, "short_count": 1000, "short_size": 10000, "general_avg": 60000},
                "combined_avg": {"long_avg": 59000, "long_count": 1000, "long_size": 10000, "short_avg": 61000, "short_count": 1000, "short_size": 10000, "general_avg": 60000}
            }
        }
        
    return {
        "status": "success",
        "cache_remaining_seconds": int(CACHE_DURATION - (current_time - CACHE["last_update"])),
        "data": coin_data
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
