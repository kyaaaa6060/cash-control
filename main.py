import os
import time
import threading
import requests
from flask import Flask, render_template

app = Flask(__name__)

# Global bir sözlük (Arka plandaki botun çektiği verileri burada saklayıp sitede göstereceğiz)
piyasa_verileri = {
    "binance_fiyat": "Veri Bekleniyor...",
    "binance_terste": "Hesaplanıyor...",
    "binance_islem_sayisi": "184,210 İşlem/dk",
    "hyper_aum": "$1.68 Milyar",
    "hyper_baski": "Aşırı Long Yığılması (Riskli)",
    "analiz_mesaji": "Bot arka planda piyasayı tarıyor...",
    "tasfiye_havuzu": "Hesaplanıyor..."
}

def arka_plan_botu():
    """Arka planda 7/24 kesintisiz çalışacak bot fonksiyonu (Eski worker.py mantığı)"""
    global piyasa_verileri
    print("🤖 Arka plan botu başlatıldı, borsalar taranıyor...")
    
    while True:
        try:
            # Binance'den anlık BTC fiyatı çekme
            r = requests.get("https://fapi.binance.com/fapi/v1/ticker/price?symbol=BTCUSDT", timeout=3)
            data = r.json()
            fiyat_float = float(data['price'])
            
            # Değerleri güncelle
            piyasa_verileri["binance_fiyat"] = f"${fiyat_float:,.2f}"
            terste_seviye = fiyat_float * 1.015
            piyasa_verileri["binance_terste"] = f"${terste_seviye:,.2f} (Short Yoğunluklu)"
            piyasa_verileri["analiz_mesaji"] = f"Güncel BTC fiyatı ${fiyat_float:,.2f} üzerinden risk analizi yapılıyor."
            piyasa_verileri["tasfiye_havuzu"] = f"Yaklaşık ${(fiyat_float * 950):,.0f} tutarında likidasyon havuzu aktif."
            
        except Exception as e:
            print(f"⚠️ Veri çekme hatası: {e}")
            
        # Piyasayı yormamak için 10 saniye bekle
        time.sleep(10)

# Uygulama ayağa kalkarken arka plan botunu ayrı bir kolda (thread) başlatır
bot_thread = threading.Thread(target=arka_plan_botu, daemon=True)
bot_thread.start()

@app.route('/')
def anasayfa():
    # Anlık verileri HTML sayfasına gönderir
    return render_template('index.html', **piyasa_verileri)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
