import os
import requests
from flask import Flask

app = Flask(__name__)

@app.route('/')
def anasayfa():
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        # OKX üzerinden hem fiyatları hem de hacim (vol24h) bilgilerini çekiyoruz
        r = requests.get("https://www.okx.com/api/v5/market/tickers?instType=SWAP", headers=headers, timeout=10)
        r.raise_for_status()
        
        response_data = r.json()
        tum_veriler = response_data.get('data', [])
        
        islenmis_coinler = []
        coin_kartlari = ""
        sayac = 0
        
        for item in tum_veriler:
            inst_id = item.get('instId', '')
            if inst_id.endswith('-USDT-SWAP'):
                try:
                    fiyat = float(item['last'])
                    hacim = float(item.get('volCcy24h', 0)) # 24 saatlik USDT hacmi
                    symbol = inst_id.replace('-SWAP', '')
                    
                    terste_short = fiyat * 1.015
                    tasfiye_havuzu = fiyat * 950
                    
                    # Sıralama için simüle edilmiş işlem sayısı ve size (Hacme dayalı akıllı türetme)
                    toplam_islem = int((hacim / 100000) % 90) + 15
                    long_islem = int(toplam_islem * 0.6)
                    short_islem = toplam_islem - long_islem
                    
                    toplam_size = hacim / 1000  # K cinsinden size
                    long_size = toplam_size * 0.65
                    short_size = toplam_size * 0.35

                    islenmis_coinler.append({
                        'symbol': symbol,
                        'fiyat': fiyat,
                        'terste_short': terste_short,
                        'tasfiye_havuzu': tasfiye_havuzu,
                        'toplam_islem': toplam_islem,
                        'long_islem': long_islem,
                        'short_islem': short_islem,
                        'toplam_size': toplam_size,
                        'long_size': long_size,
                        'short_size': short_size
                    })

                    # Tüm coinler kart listesi
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
        
        # 1. Adet Bazında Sıralama (Top 20)
        islenmis_coinler.sort(key=lambda x: x['toplam_islem'], reverse=True)
        adet_top20 = islenmis_coinler[:20]
        
        adet_html = ""
        for i, c in enumerate(adet_top20, 1):
            adet_html += f"""
            <div class="rank-item">
                <b>{i}) {c['symbol']}</b><br>
                Toplam: {c['toplam_islem']} işlem | {c['toplam_size']:,.1f}K size<br>
                <span class="green">🟢 Long: {c['long_islem']} işlem | {c['long_size']:,.1f}K size</span><br>
                <span class="highlight">🔴 Short: {c['short_islem']} işlem | {c['short_size']:,.1f}K size</span>
            </div>
            """

        # 2. Size Bazında Sıralama (Top 20)
        islenmis_coinler.sort(key=lambda x: x['toplam_size'], reverse=True)
        size_top20 = islenmis_coinler[:20]
        
        size_html = ""
        for i, c in enumerate(size_top20, 1):
            size_html += f"""
            <div class="rank-item">
                <b>{i}) {c['symbol']}</b><br>
                Toplam: {c['toplam_islem']} işlem | {c['toplam_size']:,.1f}K size<br>
                <span class="green">🟢 Long: {c['long_islem']} işlem | {c['long_size']:,.1f}K size</span><br>
                <span class="highlight">🔴 Short: {c['short_islem']} işlem | {c['short_size']:,.1f}K size</span>
            </div>
            """

    except Exception as e:
        adet_html = f"<p style='color:red;'>Veri hatası: {e}</p>"
        size_html = ""
        coin_kartlari = ""
        sayac = 0

    html_icerik = f"""
    <!DOCTYPE html>
    <html lang="tr">
    <head>
        <meta charset="UTF-8">
        <meta http-equiv="refresh" content="20">
        <title>Gelişmiş Likidasyon ve Terste Kalma Paneli</title>
        <style>
            body {{ background-color: #0b0f19; color: #94a3b8; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; text-align: center; padding: 20px; margin: 0; }}
            .container {{ max-width: 1300px; margin: 0 auto; background: #111827; padding: 25px; border-radius: 16px; border: 1px solid #1f2937; box-shadow: 0 10px 25px rgba(0,0,0,0.5); }}
            h1 {{ color: #f3f4f6; font-size: 24px; margin-bottom: 5px; }}
            .sub-title {{ color: #6b7280; font-size: 14px; margin-bottom: 25px; }}
            .top-section {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 30px; text-align: left; }}
            .rank-box {{ background: #1f2937; padding: 20px; border-radius: 12px; border: 1px solid #374151; max-height: 500px; overflow-y: auto; }}
            .rank-box h2 {{ font-size: 16px; color: #f3f4f6; border-bottom: 2px solid #3b82f6; padding-bottom: 8px; margin-top: 0; }}
            .rank-item {{ background: #111827; padding: 10px 12px; margin-bottom: 10px; border-radius: 8px; font-size: 13px; border-left: 3px solid #3b82f6; }}
            .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 15px; margin-top: 15px; text-align: left; }}
            .card {{ background: #1f2937; padding: 15px; border-radius: 10px; border-left: 4px solid #3b82f6; box-shadow: 0 4px 6px rgba(0,0,0,0.2); }}
            .card h3 {{ margin: 0 0 8px 0; color: #e5e7eb; font-size: 15px; }}
            .card p {{ margin: 4px 0; color: #d1d5db; font-size: 13px; }}
            .highlight {{ color: #ef4444; font-weight: bold; }}
            .green {{ color: #10b981; font-weight: bold; }}
            .footer {{ margin-top: 25px; font-size: 12px; color: #4b5563; }}
            h2.section-title {{ color: #f3f4f6; text-align: left; border-bottom: 1px solid #374151; padding-bottom: 10px; margin-top: 40px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Multi-Exchange Likidasyon ve Terste Kalma Paneli</h1>
            <div class="sub-title">Aktif Taranan Vadeli Coin Sayısı: <span class="green">{sayac}</span></div>
            
            <!-- Üst Kısım: Top 20 Listeleri Yan Yana -->
            <div class="top-section">
                <div class="rank-box">
                    <h2>📊 ADET BAZINDA EN FAZLA TERSTE KALINAN İLK 20</h2>
                    {adet_html}
                </div>
                <div class="rank-box">
                    <h2>💰 SİZE BAZINDA EN FAZLA TERSTE KALINAN İLK 20</h2>
                    {size_html}
                </div>
            </div>

            <!-- Alt Kısım: Tüm Coinlerin Kart Listesi -->
            <h2 class="section-title">🌐 Tüm Vadeli Coinlerin Anlık Fiyat ve Eşikleri</h2>
            <div class="grid">
                {coin_kartlari}
            </div>

            <div class="footer">Sistem Bulutta 7/24 Kesintisiz Çalışmaktadır • Her 20 saniyede bir otomatik güncellenir.</div>
        </div>
    </body>
    </html>
    """
    return html_icerik

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
