import os
import threading
import time
from datetime import datetime
from flask import Flask, jsonify, request, send_from_directory
import requests

app = Flask(__name__)

SOURCES = ["all", "whale", "copy", "pct6_20"]
active_signals = {}

def fetch_hyperliquid_universe():
    """
    Hyperliquid borsasındaki tüm vadeli işlem coinlerini (universe) dinamik olarak çeker.
    """
    try:
        res = requests.post("https://api.hyperliquid.xyz/info", json={"type": "meta"}, timeout=5)
        if res.status_code == 200:
            data = res.json()
            if "universe" in data:
                coins = [item["name"] for item in data["universe"]]
                if coins:
                    print(f"🚀 Hyperliquid'den {len(coins)} adet vadeli coin başarıyla yüklendi!")
                    return coins
    except Exception as e:
        print(f"Hyperliquid universe çekme hatası: {e}")
    
    # Bağlantı koparsa güvenli yedek liste
    return ["BTC", "ETH", "SOL", "XRP", "AVAX"]

# Başlangıçta tüm coin listesini Hyperliquid'den dinamik alıyoruz
COINS = fetch_hyperliquid_universe()

def get_multi_exchange_price(coin):
    """
    Binance, MEXC, Bybit, OKX ve Hyperliquid borsalarının anlık fiyatlarını 
    harmanlayarak (ortalama alarak) en doğru fiyatı üretir.
    """
    prices = []
    
    # 1. Binance API
    try:
        res = requests.get(f"https://api.binance.com/api/v3/ticker/price?symbol={coin}USDT", timeout=2)
        if res.status_code == 200:
            prices.append(float(res.json()["price"]))
    except Exception:
        pass

    # 2. MEXC API
    try:
        res = requests.get(f"https://www.mexc.com/open/api/v2/market/ticker?symbol={coin}_USDT", timeout=2)
        if res.status_code == 200:
            data = res.json()
            if "data" in data and len(data["data"]) > 0:
                prices.append(float(data["data"][0]["deal"]))
    except Exception:
        pass

    # 3. Bybit API
    try:
        res = requests.get(f"https://api.bybit.com/v5/market/tickers?category=linear&symbol={coin}USDT", timeout=2)
        if res.status_code == 200:
            data = res.json()
            if "result" in data and "list" in data["result"] and len(data["result"]["list"]) > 0:
                prices.append(float(data["result"]["list"][0]["lastPrice"]))
    except Exception:
        pass

    # 4. OKX API
    try:
        res = requests.get(f"https://www.okx.com/api/v5/market/ticker?instId={coin}-USDT", timeout=2)
        if res.status_code == 200:
            data = res.json()
            if "data" in data and len(data["data"]) > 0:
                prices.append(float(data["data"][0]["last"]))
    except Exception:
        pass

    # 5. Hyperliquid API (Tüm mid fiyatlar)
    try:
        res = requests.post("https://api.hyperliquid.xyz/info", json={"type": "allMids"}, timeout=2)
        if res.status_code == 200:
            mids = res.json()
            if coin in mids:
                prices.append(float(mids[coin]))
    except Exception:
        pass

    if prices:
        return sum(prices) / len(prices)
        
    return 1.0 # Fiyat bulunamazsa varsayılan

def background_trading_worker():
    print("🤖 Cash Control 7/24 Arka Plan Takip Servisi (Tüm Hyperliquid Vadeli Coinler) Aktif...")
    
    while True:
        try:
            for coin in COINS:
                mark_price = get_multi_exchange_price(coin)
                if not mark_price or mark_price <= 0:
                    continue
                
                for source in SOURCES:
                    key = f"{coin}_{source}"
                    
                    if key in active_signals:
                        plan = active_signals[key]
                        is_short = "SHORT" in plan["type"]
                        
                        hit_tp = mark_price <= plan["tp"] if is_short else mark_price >= plan["tp"]
                        hit_sl = mark_price >= plan["sl"] if is_short else mark_price <= plan["sl"]
                        
                        if hit_tp or hit_sl:
                            result_msg = "🎯 KÂR AL (TP) OLDU!" if hit_tp else "🛑 STOP (SL) OLDU!"
                            print(f"[ARKA PLAN İŞLEM KAPANDI] {key} -> {result_msg} | Fiyat: {mark_price}")
                            del active_signals[key]
                    
                    else:
                        simulated_velocity = 2.5 
                        
                        if simulated_velocity >= 2.2: 
                            signal_type = "LONG İVME BASKISI" if coin in ["BTC", "ETH", "SOL"] else "SHORT İVME BASKISI"
                            entry = mark_price
                            tp = entry * 1.025 if "LONG" in signal_type else entry * 0.975
                            sl = entry * 0.985 if "LONG" in signal_type else entry * 1.015
                            
                            active_signals[key] = {
                                "type": signal_type,
                                "entry": entry,
                                "tp": tp,
                                "sl": sl,
                                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            }

        except Exception as e:
            print(f"Arka plan döngü hatası: {e}")

        # 5 dakikada bir (300 saniye) döngü
        time.sleep(300)

worker_thread = threading.Thread(target=background_trading_worker, daemon=True)
worker_thread.start()


# --- WEB ARAYÜZÜ VE API ROUTE'LARIN ---

@app.route("/")
def home():
    return send_from_directory('.', 'index.html')

@app.route("/api/coins")
def get_coins():
    return jsonify({"status": "success", "coins": COINS})

@app.route("/api/market-stats/<coin>")
def market_stats(coin):
    price = get_multi_exchange_price(coin)
    
    return jsonify({
        "status": "success",
        "cache_remaining_seconds": 300,
        "data": {
            "symbol": coin + "USDT",
            "markPrice": price,
            "sources": {
                "all": {"long_avg": price * 0.99, "short_avg": price * 1.01, "general_avg": price, "long_count": 14, "long_size": 52000, "short_count": 9, "short_size": 38000},
                "whale": {"long_avg": price * 0.98, "short_avg": price * 1.02, "general_avg": price, "long_count": 6, "long_size": 180000, "short_count": 4, "short_size": 140000},
                "copy": {"long_avg": price * 0.995, "short_avg": price * 1.005, "general_avg": price, "long_count": 22, "long_size": 90000, "short_count": 16, "short_size": 65000},
                "pct6_20": {"long_avg": price * 0.985, "short_avg": price * 1.015, "general_avg": price, "long_count": 11, "long_size": 28000, "short_count": 10, "short_size": 24000}
            }
        }
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
