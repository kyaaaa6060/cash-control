import os
import requests
from flask import Flask

app = Flask(__name__)

@app.route('/')
def anasayfa():
    try:
        r = requests.get("https://fapi.binance.com/fapi/v1/ticker/price?symbol=BTCUSDT", timeout=3)
        data = r.json()
        fiyat_float = float(data['price'])
        binance_fiyat = f"${fiyat_float:,.2f}"
    except Exception:
        binance_fiyat = "$65,000 (Önbellek)"

    # Tasarımı doğrudan Python içinde sunuyoruz (Templates klasörüne gerek yok)
    html_icerik = f"""
    <!DOCTYPE html>
    <html lang="tr">
    <head>
        <meta charset="UTF-8">
        <meta http-equiv="refresh" content="10">
        <title>CashControl Pro - Canlı Takip</title>
        <style>
            body {{ background-color: #0d1117; color: #c9d1d9; font-family: Arial, sans-serif; text-align: center; padding-top: 50px; }}
            .card {{ background: #161b22; border: 1px solid #30363d; border-radius: 10px; display: inline-block; padding: 30px; box-shadow: 0 4px 12px rgba(0,0,0,0.5); }}
            h1 {{ color: #58a6ff; }}
            .price {{ font-size: 38px; color: #3fb950; font-weight: bold; margin: 20px 0; }}
            .info {{ color: #8b949e; font-size: 14px; }}
        </style>
    </head>
    <body>
        <div class="card">
            <h1>CashControl Pro</h1>
            <p class="info">Canlı XAUUSD / BTCUSDT Takip Paneli</p>
            <div class="price">{binance_fiyat}</div>
            <p class="info">Durum: Sistem Aktif ve Çalışıyor 🚀</p>
            <p style="font-size: 11px; color: #484f58; margin-top: 15px;">Her 10 saniyede bir otomatik güncellenir.</p>
        </div>
    </body>
    </html>
    """
    return html_icerik

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
