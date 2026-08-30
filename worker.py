import time
import requests
from datetime import datetime

# Takip edilecek coinler ve kaynaklar
COINS = ["BTC", "ETH", "SOL", "XRP", "AVAX"]
SOURCES = ["all", "whale", "copy", "pct6_20"]

# Aktif işlemlerin hafızada tutulduğu sözlük (Sunucu belleği)
active_signals = {}

def get_market_price(coin):
    try:
        url = f"https://api.binance.com/api/v3/ticker/price?symbol={coin}USDT"
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            return float(res.json()["price"])
    except Exception as e:
        print(f"Fiyat çekme hatası ({coin}): {e}")
    return None

def run_background_worker():
    print("🤖 Cash Control 7/24 Arka Plan Takip Servisi Başlatıldı...")
    
    while True:
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
                        print(f"[KAPANDI] {key} -> {result_msg} | Fiyat: {mark_price}")
                        # İşlem bittiği için hafızadan sil (Yeni formasyon/ivme beklenir)
                        del active_signals[key]
                
                # 2. Aşama: Açık işlem yoksa hız/ivme ve formasyon tara
                else:
                    # Simüle edilmiş anlık hız ivmesi (Normal eğrinin üzerindeki ani hareketler)
                    # Burada kendi hesaplama mantığını veya borsa verilerini tetikleyebilirsin
                    simulated_velocity = 2.5 
                    
                    if simulated_velocity >= 2.2: # Hız eşiği aşıldıysa sinyali mühürle
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
                        
                        print(f"[YENİ İŞLEM AÇILDI] {key} -> {signal_type} | Giriş: {entry} | TP: {tp} | SL: {sl}")
                        
                        # İsteğe bağlı: Telegram bot fonksiyonunu buraya ekleyerek 
                        # telefonuna anında bildirim düşmesini sağlayabilirsin.

        # Her 15 saniyede bir piyasayı arkada tara
        time.sleep(15)

if name == "main":
    run_background_worker()
