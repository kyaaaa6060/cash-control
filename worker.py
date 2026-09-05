import time
import requests

def piyasa_tarayici_dongusu():
    print("🤖 Worker (Arka Plan Botu) başlatıldı. Veriler taranıyor...")
    
    while True:
        try:
            # Binance'den anlık BTC fiyatını çekme
            r = requests.get("https://fapi.binance.com/fapi/v1/ticker/price?symbol=BTCUSDT", timeout=3)
            data = r.json()
            fiyat = float(data['price'])
            
            # Basit bir likidasyon ve terste kalan short/long hesaplama simülasyonu
            terste_short = fiyat * 1.015
            terste_long = fiyat * 0.985
            
            print(f"[CANLI] BTC Fiyat: ${fiyat:,.2f} | Terste Short Ortalaması: ${terste_short:,.2f} | Terste Long Ortalaması: ${terste_long:,.2f}")
            
        except Exception as e:
            print(f"⚠️ Veri çekme hatası: {e}")
            
        # Piyasayı boğmamak ve API limitine takılmamak için her 10 saniyede bir döngüyü çalıştır
        time.sleep(10)

if __name__ == "__main__":
    piyasa_tarayici_dongusu()
