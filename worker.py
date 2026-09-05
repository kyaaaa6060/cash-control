import time
import requests
from datetime import datetime

COINS = ["BTC", "ETH", "SOL", "XRP", "AVAX"]
active_signals = {}

def get_market_data(coin):
    try:
        url = f"https://api.binance.com/api/v3/ticker/price?symbol={coin}USDT"
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            return float(res.json()["price"])
    except Exception as e:
        print(f"Fiyat çekme hatası ({coin}): {e}")
    return None

def run_background_worker():
    print("🤖 Cash Control 7/24 Detaylı Smart-Money Takip Servisi Başlatıldı...")
    
    while True:
        for coin in COINS:
            mark_price = get_market_data(coin)
            if not mark_price: continue
            
            key = f"{coin}_SMART"
            
            if key in active_signals:
                plan = active_signals[key]
                is_short = "SHORT" in plan["type"]
                hit_tp = mark_price <= plan["tp"] if is_short else mark_price >= plan["tp"]
                hit_sl = mark_price >= plan["sl"] if is_short else mark_price <= plan["sl"]
                
                if hit_tp or hit_sl:
                    result_msg = "🎯 KÂR AL (TP) OLDU!" if hit_tp else "🛑 STOP (SL) OLDU!"
                    print(f"[KAPANDI] {coin} -> {result_msg} | Fiyat: {mark_price}")
                    del active_signals[key]
            else:
                # Simüle edilmiş ya da Hyperliquid / Binance bot verisi bazlı kontrol
                signal_type = "LONG İVME BASKISI"
                entry = mark_price
                tp = entry * 1.025
                sl = entry * 0.985
                
                active_signals[key] = {
                    "type": signal_type, "entry": entry, "tp": tp, "sl": sl,
                    "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                print(f"[YENİ İŞLEM] {coin} -> {signal_type} | Giriş: {entry}")

        time.sleep(15)

if __name__ == "__main__":
    run_background_worker()
