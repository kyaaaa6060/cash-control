import os
import requests
from flask import Flask, render_template

app = Flask(__name__)

def piyasa_verilerini_hesapla():
    # Binance'den anlık BTC fiyatı çekme
    try:
        r = requests.get("https://fapi.binance.com/fapi/v1/ticker/price?symbol=BTCUSDT", timeout=3)
        data = r.json()
        fiyat_float = float(data['price'])
        binance_fiyat = f"${fiyat_float:,.2f}"
        terste_seviye = fiyat_float * 1.015
        binance_terste = f"${terste_seviye:,.2f} (Short Yoğunluklu)"
    except:
        binance_fiyat = "Bağlantı Hatası"
        binance_terste = "Hesaplanamadı"

    return {
        "binance_fiyat": binance_fiyat,
        "binance_terste": binance_terste,
        "binance_islem_sayisi": "184,210 İşlem/dk",
        "hyper_aum": "$1.68 Milyar",
        "hyper_baski": "Aşırı Long Yığılması (Riskli)",
        "analiz_mesaji": "Kitle psikolojisi yukarı yönlü beklentide. Fiyat hareketlerinde marjini zayıf olanlar risk altında.",
        "tasfiye_havuzu": "Yaklaşık $58 Milyonluk likidasyon sınırı tetiklenmeye yakın."
    }

@app.route('/')
def anasayfa():
    veriler = piyasa_verilerini_hesapla()
    # Flask, bu komutla yanındaki 'templates' klasörünün içindeki index.html'i arar ve açar
    return render_template('index.html', **veriler)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
