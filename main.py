import os
import requests
from flask import Flask

app = Flask(__name__)

@app.route('/')
def anasayfa():
    try:
        # Binance Futures tüm ticker verilerini çekmeyi dene
        r = requests.get("https://fapi.binance.com/fapi/v1/ticker/price", timeout=10)
        
        # Eğer Binance engellerse HTTP hatası fırlatsın
        r.raise_for_status()
        
        tum_veriler = r.json()
        coin_kartlari = ""
        sayac = 0
        
        for item in tum_veriler:
            symbol = item['symbol']
            if symbol.endswith('USDT'):
                try:
                    fiyat = float(item['price'])
                    terste_short = fiyat * 1.015
                    tasfiye_havuzu = fiyat * 950
                    
                    coin_kartlari += f"""
                    <div class="card">
                        <h3>📊 {symbol}</h3>
                        <p>Anlık Fiyat: <span class="green">${fiyat:,.4f}</span></p>
                        <p>Terste Short: <span class="highlight">${terste_short:,.4f}</span></p>
                        <p>Tasfiye Eşiği: <span style="color: #f59e0b;">${tasfiye_havuzu:,.0f}</span></p>
                    </div>
                    """
                    sayac += 1
                except:
                    continue
                    
    except Exception as e:
        # Hatanın detayını doğrudan ekrana yazdıralım
        coin_kartlari = f"<p style='color: #ef4444; grid-column: 1 / -1; font-size: 16px; background: #1f2937; padding: 20px; border-radius: 8px;'><b>Binance API Hatası:</b> {e}</p>"
        sayac = 0

    html_icerik = f"""
    <!DOCTYPE html>
    <html lang="tr">
    <head>
        <meta charset="UTF-8">
        <meta http-equiv="refresh" content="15">
        <title>Binance Futures Paneli</title>
        <style>
            body {{ background-color: #0b0f19; color: #94a3b8; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; text-align: center; padding: 20px; margin: 0; }}
            .container {{ max-width: 1200px; margin: 0 auto; background: #111827; padding: 25px; border-radius: 16px; border: 1px solid #1f2937; box-shadow: 0 10px 25px rgba(0,0,0,0.5); }}
            h1 {{ color: #f3f4f6; font-size: 24px; margin-bottom: 5px; }}
            .sub-title {{ color: #6b7280; font-size: 14px; margin-bottom: 20px; }}
            .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 15px; margin-top: 15px; text-align: left; }}
            .card {{ background: #1f2937; padding: 15px; border-radius: 10px; border-left: 4px solid #3b82f6; box-shadow: 0 4px 6px rgba(0,0,0,0.2); }}
            .card h3 {{ margin: 0 0 8px 0; color: #e5e7eb; font-size: 16px; }}
            .card p {{ margin: 4px 0; color: #d1d5db; font-size: 13px; }}
            .highlight {{ color: #ef4444; font-weight: bold; }}
            .green {{ color: #10b981; font-weight: bold; }}
            .footer {{ margin-top: 25px; font-size: 12px; color: #4b5563; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Binance Futures - Tüm Vadeli Coinler Paneli</h1>
            <div class="sub-title">Aktif Taranan Vadeli Coin Sayısı: <span class="green">{sayac}</span></div>
            
            <div class="grid">
                {coin_kartlari}
            </div>

            <div class="footer">Sistem Bulutta 7/24 Kesintisiz Çalışmaktadır • Her 15 saniyede bir otomatik güncellenir.</div>
        </div>
    </body>
    </html>
    """
    return html_icerik

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
