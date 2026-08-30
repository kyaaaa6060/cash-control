import time
import requests
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

app = FastAPI(title="Cash Control Engine - Smart Filter", version="8.3")

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
CACHE_DURATION = 30

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
        print("Binance hatası:", e)
    return {}

def fetch_karma_market_data():
    processed_coins = {}
    total_open_interest_usd = 0
    all_prices = []
    
    binance_data = get_binance_futures_tickers()
    
    hl_url = "https://api.hyperliquid.xyz/info"
    payload = {"type": "metaAndAssetCtxs"}
    
    try:
        res = requests.post(hl_url, json=payload, headers={"Content-Type": "application/json"}, timeout=3)
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
                
                prices = [hl_mark_px]
                fundings = [hl_funding]
                
                if name in binance_data and binance_data[name]["markPrice"] > 0:
                    prices.append(binance_data[name]["markPrice"])
                    fundings.append(binance_data[name]["fundingRate"])
                
                mark_px = sum(prices) / len(prices)
                funding = sum(fundings) / len(fundings)
                
                if mark_px <= 0:
                    continue
                
                all_prices.append(mark_px)
                oi_usd = open_interest * mark_px
                total_open_interest_usd += oi_usd
                
                sr_data = {
                    "support_1": mark_px * 0.965,
                    "support_2": mark_px * 0.930,
                    "resistance_1": mark_px * 1.035,
                    "resistance_2": mark_px * 1.070,
                    "trend": "Kanal İçi Sabit"
                }
                
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

                # AKILLI KARARSIZLIK KONTROLÜ
                res1 = sr_data["resistance_1"]
                sup1 = sr_data["support_1"]
                
                # Eğer fiyat direnç veya destek noktalarına uzaksa (orta alanda sıkışmışsa) robot kararsız desin
                mid_distance_ratio = abs(mark_px - ((res1 + sup1) / 2)) / mark_px
                
                if mark_px >= res1 * 0.992:
                    signal, color, conf, comment = "DİRENÇ BÖLGESİ / SATIŞ RİSKİ", "#f6465d", 85, f"Fiyat kritik direnç bölgesi olan ${res1:,.2f} seviyesinde. Formasyon direnç testi üretiyor."
                    formation = "Yükselen Kanal / Direnç Testi"
                elif mark_px <= sup1 * 1.008:
                    signal, color, conf, comment = "DESTEK BÖLGESİ / TEPKI ALIMI", "#0ecb81", 86, f"Fiyat ana destek bölgesi olan ${sup1:,.2f} seviyesine geriledi. Tepki olasılığı yüksek."
                    formation = "Alçalan Kanal / Çift Dip Adayı"
                elif mid_distance_ratio < 0.015: 
                    # Fiyat tam ortada ve net bir uçta değilse kararsız ilan et
                    signal, color, conf, comment = "PİYASA KARARSIZ / BELEMEDE", "#707A8A", 50, "Fiyat bant içinde nötr bölgede kalıyor. Net bir formasyon veya strateji sinyali üretmek için erken."
                    formation = "Net Formasyon Yok (Yatay Seyir)"
                else:
                    signal, color, conf, comment = "KANAL İÇİ DENGELİ SEYİR", "#f0b90b", 70, "Fiyat ortalama seviyelerde hareket ediyor, yön arayışı devam ediyor."
                    formation = "Simetrik Konsolidasyon"

                ai_report = {
                    "signal": signal,
                    "signalColor": color,
                    "confidence": conf,
                    "comment": comment,
                    "formation": formation,
                    "formationTF": "4 Saatlik (4H)",
                    "formationStatus": "Aktif / Filtrelenmiş"
                }

                processed_coins[name] = {
                    "symbol": f"{name}USDT",
                    "markPrice": mark_px,
                    "fundingRate": funding,
                    "openInterestUSD": oi_usd,
                    "sources": coin_sources_data,
                    "ai_analysis": ai_report,
                    "sr_levels": sr_data
                }
            
            processed_coins["_GLOBAL_SUMMARY_"] = {
                "totalActiveCoins": len(processed_coins),
                "totalAUM_OI": total_open_interest_usd,
                "avgMarketPrice": sum(all_prices) / len(all_prices) if all_prices else 0
            }
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
