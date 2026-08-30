import os
import threading
import time
from datetime import datetime
from flask import Flask, jsonify, request

app = Flask(__name__)

# --- 7/24 ARKA PLAN TAKİP MOTORU (BACKGROUND WORKER THREAD) ---
COINS = ["BTC", "ETH", "SOL", "XRP", "AVAX"]
SOURCES = ["all", "whale", "copy", "pct6_20"]

# Sunucu belleğinde aktif işlemleri tuttuğumuz veritabanı sözlüğü
active_signals = {}

def get_market_price(coin):
    try:
        import requests
        url = f"https://api.binance.com/api/v3/ticker/price?symbol={coin}USDT"
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            return float(res.json()["price"])
    except Exception as e:
        print(f"Fiyat çekme hatası ({coin}): {e}")
    return None

def background_trading_worker():
    print("🤖 Cash Control 7/24 Arka Plan Takip Servisi (Thread) Aktif Edildi...")
    
    while True:
        try:
            for coin in COINS:
                mark_price = get_market_price(coin)
                if not mark_price:
                    continue
                
                for source in SOURCES:
                    key = f"{coin}_{source}"
                    
                    # 1. Aşama: Halihazırda açık bir işlem varsa TP / SL kontrolü yap
                    if key in active_signals:
                        plan = active_signals[key]
                        is_short = "SHORT" in plan["type"]
                        
                        hit_tp = mark_price <= plan["tp"] if is_short else mark_price >= plan["tp"]
                        hit_sl = mark_price >= plan["sl"] if is_short else mark_price <= plan["sl"]
                        
                        if hit_tp or hit_sl:
                            result_msg = "🎯 KÂR AL (TP) OLDU!" if hit_tp else "🛑 STOP (SL) OLDU!"
                            print(f"[ARKA PLAN İŞLEM KAPANDI] {key} -> {result_msg} | Fiyat: {mark_price}")
                            # İşlem bittiği için hafızadan sil (Yeni ivme kırılımı beklenir)
                            del active_signals[key]
                    
                    # 2. Aşama: Açık işlem yoksa hız/ivme ve formasyon tara
                    else:
                        simulated_velocity = 2.5 
                        
                        if simulated_velocity >= 2.2: # Hız eşiği aşıldıysa yeni sinyali mühürle
                            signal_type = "LONG İVME BASKISI" if coin in ["BTC", "ETH"] else "SHORT İVME BASKISI"
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
                            
                            print(f"[ARKA PLAN YENİ İŞLEM] {key} -> {signal_type} | Giriş: {entry} | TP: {tp} | SL: {sl}")

        except Exception as e:
            print(f"Arka plan döngü hatası: {e}")

        # Her 15 saniyede bir piyasayı arkada tara
        time.sleep(15)

# Uygulama başlarken arka plan döngüsünü bağımsız bir kol olarak başlatıyoruz
worker_thread = threading.Thread(target=background_trading_worker, daemon=True)
worker_thread.start()


# --- WEB SERVİS / API ROUTE'LARIN ---

@app.route("/")
def home():
    return "Cash Control Bot Çalışıyor ve Arka Planda Taramaya Devam Ediyor!"

@app.route("/api/coins")
def get_coins():
    return jsonify({"status": "success", "coins": COINS})

@app.route("/api/market-stats/<coin>")
def market_stats(coin):
    price = get_market_price(coin) or 60000.0
    return jsonify({
        "status": "success",
        "cache_remaining_seconds": 300,
        "data": {
            "symbol": coin + "USDT",
            "markPrice": price,
            "sources": {
                "all": {"long_avg": price * 0.99, "short_avg": price * 1.01, "general_avg": price, "long_count": 12, "long_size": 45000, "short_count": 8, "short_size": 32000},
                "whale": {"long_avg": price * 0.98, "short_avg": price * 1.02, "general_avg": price, "long_count": 5, "long_size": 150000, "short_count": 3, "short_size": 120000},
                "copy": {"long_avg": price * 0.995, "short_avg": price * 1.005, "general_avg": price, "long_count": 20, "long_size": 80000, "short_count": 15, "short_size": 60000},
                "pct6_20": {"long_avg": price * 0.985, "short_avg": price * 1.015, "general_avg": price, "long_count": 10, "long_size": 25000, "short_count": 9, "short_size": 22000}
            }
        }
    })

if __name__ == "__main__":
    # Render'ın verdiği dinamik portu otomatik yakalar
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
