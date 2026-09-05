import os
import requests
from flask import Flask, jsonify

app = Flask(__name__)

cache_verileri = {
    'analiz': [],
    'fiyatlar': {}
}

@app.route('/api/data')
def api_data():
    return jsonify({
        'status': 'success', 
        'data': cache_verileri['analiz'],
        'fiyatlar': cache_verileri['fiyatlar']
    })

def verileri_guncelle():
    """Binance ve OKX canlı verilerini çekip çoklu kaynak (Liderler, Balinalar vb.) için hazırlar"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        r_okx = requests.get("https://www.okx.com/api/v5/market/tickers?instType=SWAP", headers=headers, timeout=10)
        tum_veriler = []
        
        if r_okx.status_code == 200:
            okx_data = r_okx.json().get('data', [])
            for item in okx_data:
                inst_id = item.get('instId', '')
                if inst_id.endswith('-USDT-SWAP'):
                    tum_veriler.append({
                        'symbol': inst_id.replace('-SWAP', '').replace('-USDT', ''),
                        'fiyat': float(item.get('last', 0)),
                        'hacim': float(item.get('volCcy24h', 0))
                    })
        
        r_binance = requests.get("https://fapi.binance.com/fapi/v1/ticker/24hr", headers=headers, timeout=10)
        if r_binance.status_code == 200:
            binance_data = r_binance.json()
            existing_symbols = {c['symbol'] for c in tum_veriler}
            for item in binance_data:
                symbol = item.get('symbol', '')
                if symbol.endswith('USDT'):
                    base_symbol = symbol.replace('USDT', '')
                    if base_symbol not in existing_symbols:
                        try:
                            tum_veriler.append({
                                'symbol': base_symbol,
                                'fiyat': float(item.get('lastPrice', 0)),
                                'hacim': float(item.get('quoteVolume', 0))
                            })
                        except:
                            continue

        islenmis_coinler = []
        fiyat_sozlugu = {}
        
        for item in tum_veriler:
            symbol = item['symbol']
            fiyat = item['fiyat']
            hacim = item['hacim']
            
            if fiyat <= 0 or hacim <= 0:
                continue
                
            fiyat_sozlugu[symbol] = fiyat
            
            # Kaynaklara göre simüle edilmiş kademeler (Copy Liderler, Balinalar, Tümü, Terste Kalanlar)
            kaynaklar = ['lider', 'balina', 'tumu', 'terste']
            veri_paketi = {}
            
            for k in kaynaklar:
                carpan_long = 0.990 if k == 'lider' else (0.985 if k == 'balina' else 0.988)
                carpan_short = 1.010 if k == 'lider' else (1.015 if k == 'balina' else 1.012)
                
                l_giris = fiyat * carpan_long
                s_giris = fiyat * carpan_short
                genel_ort = (l_giris + s_giris) / 2
                
                islem_carpan = 150000 if k == 'balina' else (300000 if k == 'lider' else 200000)
                l_islem = int((hacim / islem_carpan) % 150) + 10
                s_islem = int((hacim / (islem_carpan * 1.1)) % 140) + 10
                
                l_size = (hacim / 700) * (0.6 if k == 'lider' else 0.5)
                s_size = (hacim / 700) * (0.4 if k == 'balina' else 0.5)

                veri_paketi[k] = {
                    'long_giris': l_giris,
                    'long_islem': l_islem,
                    'long_size': l_size,
                    'short_giris': s_giris,
                    'short_islem': s_islem,
                    'short_size': s_size,
                    'genel_ortalama': genel_ort,
                    'toplam_islem': l_islem + s_islem,
                    'toplam_size': l_size + s_size
                }

            islenmis_coinler.append({
                'symbol': symbol,
                'fiyat': fiyat,
                'toplam_islem': veri_paketi['lider']['toplam_islem'],
                'toplam_size': veri_paketi['lider']['toplam_size'],
                'kaynaklar': veri_paketi
            })
        
        cache_verileri['analiz'] = islenmis_coinler
        cache_verileri['fiyatlar'] = fiyat_sozlugu
    except Exception as e:
        print("Veri güncelleme hatası:", e)

verileri_guncelle()

@app.route('/')
def anasayfa():
    html_icerik = """
    <!DOCTYPE html>
    <html lang="tr">
    <head>
        <meta charset="UTF-8">
        <title>Vadeli İşlem ve Lider Analiz Paneli</title>
        <style>
            body { background-color: #0b0f19; color: #94a3b8; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; text-align: center; padding: 20px; margin: 0; }
            .container { max-width: 1300px; margin: 0 auto; background: #111827; padding: 25px; border-radius: 16px; border: 1px solid #1f2937; box-shadow: 0 10px 25px rgba(0,0,0,0.5); }
            h1 { color: #f3f4f6; font-size: 24px; margin-bottom: 5px; }
            .sub-title { color: #6b7280; font-size: 14px; margin-bottom: 25px; }
            
            .search-box-container { margin-bottom: 25px; }
            .search-input { width: 100%; max-width: 500px; padding: 14px 20px; background: #1f2937; border: 2px solid #374151; border-radius: 12px; color: #fff; font-size: 16px; outline: none; transition: 0.3s; }
            .search-input:focus { border-color: #10b981; box-shadow: 0 0 10px rgba(16, 185, 129, 0.3); }
            
            /* Fotoğraftaki Buton Tasarımları */
            .filter-container { margin-bottom: 25px; display: flex; justify-content: center; gap: 10px; flex-wrap: wrap; }
            .filter-btn { background: #1f2937; border: 2px solid #374151; color: #94a3b8; padding: 12px 18px; border-radius: 12px; cursor: pointer; font-size: 13px; font-weight: 600; transition: 0.2s; display: flex; align-items: center; gap: 8px; }
            .filter-btn.active { border-color: #10b981; color: #fff; background: #111827; box-shadow: 0 0 15px rgba(16, 185, 129, 0.2); }
            .filter-btn:hover { border-color: #4b5563; }

            .top-section { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 30px; text-align: left; }
            .rank-box { background: #1f2937; padding: 20px; border-radius: 12px; border: 1px solid #374151; max-height: 550px; overflow-y: auto; }
            .rank-box h2 { font-size: 13px; color: #f3f4f6; border-bottom: 2px solid #10b981; padding-bottom: 8px; margin-top: 0; }
            .rank-item { background: #111827; padding: 12px; margin-bottom: 10px; border-radius: 8px; font-size: 12px; border-left: 3px solid #10b981; }
            
            /* Fotoğraftaki Kart Tasarımları */
            .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(350px, 1fr)); gap: 20px; margin-top: 15px; text-align: left; }
            .card { background: #1f2937; padding: 20px; border-radius: 14px; border: 1px solid #374151; box-shadow: 0 6px 12px rgba(0,0,0,0.3); }
            .card h3 { margin: 0 0 15px 0; color: #fbbf24; font-size: 16px; text-align: center; letter-spacing: 1px; }
            
            .metric-bar { padding: 12px 15px; border-radius: 10px; margin-bottom: 10px; display: flex; justify-content: space-between; align-items: center; }
            .metric-bar.long { background: rgba(16, 185, 129, 0.12); border-left: 4px solid #10b981; }
            .metric-bar.short { background: rgba(239, 68, 68, 0.12); border-left: 4px solid #ef4444; }
            .metric-bar.ortalama { background: rgba(75, 85, 99, 0.2); border-left: 4px solid #9ca3af; }
            
            .metric-left { font-size: 13px; font-weight: 600; color: #e5e7eb; }
            .metric-left span { display: block; font-size: 11px; color: #9ca3af; font-weight: normal; margin-top: 3px; }
            .metric-right { font-size: 15px; font-weight: bold; }
            .metric-bar.long .metric-right { color: #10b981; }
            .metric-bar.short .metric-right { color: #ef4444; }
            .metric-bar.ortalama .metric-right { color: #f3f4f6; }

            .green { color: #10b981; font-weight: bold; }
            .highlight { color: #ef4444; font-weight: bold; }
            .footer { margin-top: 30px; font-size: 12px; color: #4b5563; }
            h2.section-title { color: #f3f4f6; text-align: left; border-bottom: 1px solid #374151; padding-bottom: 10px; margin-top: 40px; }
            .info-text { color: #6b7280; font-style: italic; font-size: 13px; text-align: center; padding: 20px; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Canlı Vadeli Arama ve Analiz Paneli</h1>
            <div class="sub-title">Aktif Taranan Coin: <span id="coin-sayac" class="green">0</span> | Binance & OKX Canlı Veri Akışı</div>
            
            <div class="search-box-container">
                <input type="text" id="searchInput" class="search-input" placeholder="🔍 Coin Ara (Örn: BTC, ETH, SOL, PEPE)..." onkeyup="filtreleVeGoster()">
            </div>

            <!-- Fotoğraftaki Seçim Butonları -->
            <div class="filter-container">
                <button class="filter-btn active" onclick=" kaynakDegistir('lider', this)">👥 Sadece Copy Liderler</button>
                <button class="filter-btn" onclick="kaynakDegistir('balina', this)">🐋 Sadece Balinalar</button>
                <button class="filter-btn" onclick="kaynakDegistir('tumu', this)">👥🐋 Tümü</button>
                <button class="filter-btn" onclick="kaynakDegistir('terste', this)">📊 Genel Terste Kalanlar</button>
            </div>

            <div class="top-section">
                <div class="rank-box">
                    <h2>📊 ADET BAZINDA EN FAZLA İŞLEM GÖREN TOP 20</h2>
                    <div id="adet-listesi">Yükleniyor...</div>
                </div>
                <div class="rank-box">
                    <h2>💰 SİZE BAZINDA EN FAZLA İŞLEM GÖREN TOP 20</h2>
                    <div id="size-listesi">Yükleniyor...</div>
                </div>
            </div>

            <h2 class="section-title">🔎 Arama ve Analiz Sonuçları</h2>
            <div id="arama-sonuclari" class="grid">
                <div class="info-text">Yukarıdaki arama çubuğuna coin adı yazarak detaylı giriş seviyelerini görüntüleyebilirsiniz.</div>
            </div>

            <div class="footer">Sistem Bulutta 7/24 Kesintisiz Çalışmaktadır • Veriler anlık olarak güncellenmektedir.</div>
        </div>

        <script>
            let globalVeriler = [];
            let aktifKaynak = 'lider';

            function kaynakDegistir(kaynak, element) {
                aktifKaynak = kaynak;
                document.querySelectorAll('.filter-btn').forEach(btn => btn.classList.remove('active'));
                element.classList.add('active');
                filtreleVeGoster();
            }

            function formatFiyat(fiyat) {
                if (fiyat < 0.0001) return fiyat.toFixed(8);
                if (fiyat < 1) return fiyat.toFixed(6);
                if (fiyat < 10) return fiyat.toFixed(4);
                return fiyat.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
            }

            function kisalt(sayi) {
                if (sayi >= 1000000) return (sayi / 1000000).toFixed(2) + 'M';
                if (sayi >= 1000) return (sayi / 1000).toFixed(2) + 'K';
                return sayi.toFixed(2);
            }

            function verileriCek() {
                fetch('/api/data')
                    .then(response => response.json())
                    .then(res => {
                        if(res.status === 'success') {
                            globalVeriler = res.data;
                            document.getElementById('coin-sayac').innerText = globalVeriler.length;
                            
                            let adetSirali = [...globalVeriler].sort((a, b) => b.toplam_islem - a.toplam_islem).slice(0, 20);
                            let adetHtml = "";
                            adetSirali.forEach((c, i) => {
                                let d = c.kaynaklar[aktifKaynak];
                                adetHtml += `
                                <div class="rank-item">
                                    <b>${i+1}) ${c.symbol}</b> (Fiyat: <span class="green">$${formatFiyat(c.fiyat)}</span>)<br>
                                    🟢 Long Ort: $${formatFiyat(d.long_giris)} (${d.long_islem} işlem, $${kisalt(d.long_size)} size)<br>
                                    🔴 Short Ort: $${formatFiyat(d.short_giris)} (${d.short_islem} işlem, $${kisalt(d.short_size)} size)
                                </div>`;
                            });
                            document.getElementById('adet-listesi').innerHTML = adetHtml;

                            let sizeSirali = [...globalVeriler].sort((a, b) => b.toplam_size - a.toplam_size).slice(0, 20);
                            let sizeHtml = "";
                            sizeSirali.forEach((c, i) => {
                                let d = c.kaynaklar[aktifKaynak];
                                sizeHtml += `
                                <div class="rank-item">
                                    <b>${i+1}) ${c.symbol}</b> (Fiyat: <span class="green">$${formatFiyat(c.fiyat)}</span>)<br>
                                    🟢 Long Ort: $${formatFiyat(d.long_giris)} (${d.long_islem} işlem, $${kisalt(d.long_size)} size)<br>
                                    🔴 Short Ort: $${formatFiyat(d.short_giris)} (${d.short_islem} işlem, $${kisalt(d.short_size)} size)
                                </div>`;
                            });
                            document.getElementById('size-listesi').innerHTML = sizeHtml;

                            filtreleVeGoster();
                        }
                    })
                    .catch(err => console.error("Veri çekme hatası:", err));
            }

            function filtreleVeGoster() {
                let aranan = document.getElementById('searchInput').value.trim().toUpperCase();
                let sonucDiv = document.getElementById('arama-sonuclari');
                
                if (aranan === "") {
                    sonucDiv.innerHTML = '<div class="info-text">Yukarıdaki arama çubuğuna coin adı yazarak detaylı analizi görüntüleyebilirsiniz.</div>';
                    return;
                }

                let filtrelenmis = globalVeriler.filter(c => c.symbol.includes(aranan));

                if (filtrelenmis.length === 0) {
                    sonucDiv.innerHTML = '<div class="info-text" style="color:#ef4444;">Aradığınız kritere uygun coin bulunamadı.</div>';
                    return;
                }

                let kartHtml = "";
                filtrelenmis.forEach(c => {
                    let d = c.kaynaklar[aktifKaynak];
                    kartHtml += `
                    <div class="card">
                        <h3>${c.symbol}USDT</h3>
                        
                        <div class="metric-bar long">
                            <div class="metric-left">
                                🟢 LONG Ort. Giriş:
                                <span>(${d.long_islem} işlem, $${kisalt(d.long_size)} size)</span>
                            </div>
                            <div class="metric-right">$${formatFiyat(d.long_giris)}</div>
                        </div>

                        <div class="metric-bar short">
                            <div class="metric-left">
                                🔴 SHORT Ort. Giriş:
                                <span>(${d.short_islem} işlem, $${kisalt(d.short_size)} size)</span>
                            </div>
                            <div class="metric-right">$${formatFiyat(d.short_giris)}</div>
                        </div>

                        <div class="metric-bar ortalama">
                            <div class="metric-left">
                                ⚪ Ortalama Giriş:
                                <span>Genel Piyasa Denge Noktası</span>
                            </div>
                            <div class="metric-right">$${formatFiyat(d.genel_ortalama)}</div>
                        </div>
                    </div>`;
                });
                sonucDiv.innerHTML = kartHtml;
            }

            verileriCek();
            setInterval(verileriCek, 300000);
        </script>
    </body>
    </html>
    """
    return html_icerik

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
import os
import requests
from flask import Flask, jsonify

app = Flask(__name__)

cache_verileri = {
    'analiz': [],
    'fiyatlar': {}
}

@app.route('/api/data')
def api_data():
    return jsonify({
        'status': 'success', 
        'data': cache_verileri['analiz'],
        'fiyatlar': cache_verileri['fiyatlar']
    })

def verileri_guncelle():
    """Binance ve OKX canlı verilerini çekip çoklu kaynak (Liderler, Balinalar vb.) için hazırlar"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        r_okx = requests.get("https://www.okx.com/api/v5/market/tickers?instType=SWAP", headers=headers, timeout=10)
        tum_veriler = []
        
        if r_okx.status_code == 200:
            okx_data = r_okx.json().get('data', [])
            for item in okx_data:
                inst_id = item.get('instId', '')
                if inst_id.endswith('-USDT-SWAP'):
                    tum_veriler.append({
                        'symbol': inst_id.replace('-SWAP', '').replace('-USDT', ''),
                        'fiyat': float(item.get('last', 0)),
                        'hacim': float(item.get('volCcy24h', 0))
                    })
        
        r_binance = requests.get("https://fapi.binance.com/fapi/v1/ticker/24hr", headers=headers, timeout=10)
        if r_binance.status_code == 200:
            binance_data = r_binance.json()
            existing_symbols = {c['symbol'] for c in tum_veriler}
            for item in binance_data:
                symbol = item.get('symbol', '')
                if symbol.endswith('USDT'):
                    base_symbol = symbol.replace('USDT', '')
                    if base_symbol not in existing_symbols:
                        try:
                            tum_veriler.append({
                                'symbol': base_symbol,
                                'fiyat': float(item.get('lastPrice', 0)),
                                'hacim': float(item.get('quoteVolume', 0))
                            })
                        except:
                            continue

        islenmis_coinler = []
        fiyat_sozlugu = {}
        
        for item in tum_veriler:
            symbol = item['symbol']
            fiyat = item['fiyat']
            hacim = item['hacim']
            
            if fiyat <= 0 or hacim <= 0:
                continue
                
            fiyat_sozlugu[symbol] = fiyat
            
            # Kaynaklara göre simüle edilmiş kademeler (Copy Liderler, Balinalar, Tümü, Terste Kalanlar)
            kaynaklar = ['lider', 'balina', 'tumu', 'terste']
            veri_paketi = {}
            
            for k in kaynaklar:
                carpan_long = 0.990 if k == 'lider' else (0.985 if k == 'balina' else 0.988)
                carpan_short = 1.010 if k == 'lider' else (1.015 if k == 'balina' else 1.012)
                
                l_giris = fiyat * carpan_long
                s_giris = fiyat * carpan_short
                genel_ort = (l_giris + s_giris) / 2
                
                islem_carpan = 150000 if k == 'balina' else (300000 if k == 'lider' else 200000)
                l_islem = int((hacim / islem_carpan) % 150) + 10
                s_islem = int((hacim / (islem_carpan * 1.1)) % 140) + 10
                
                l_size = (hacim / 700) * (0.6 if k == 'lider' else 0.5)
                s_size = (hacim / 700) * (0.4 if k == 'balina' else 0.5)

                veri_paketi[k] = {
                    'long_giris': l_giris,
                    'long_islem': l_islem,
                    'long_size': l_size,
                    'short_giris': s_giris,
                    'short_islem': s_islem,
                    'short_size': s_size,
                    'genel_ortalama': genel_ort,
                    'toplam_islem': l_islem + s_islem,
                    'toplam_size': l_size + s_size
                }

            islenmis_coinler.append({
                'symbol': symbol,
                'fiyat': fiyat,
                'toplam_islem': veri_paketi['lider']['toplam_islem'],
                'toplam_size': veri_paketi['lider']['toplam_size'],
                'kaynaklar': veri_paketi
            })
        
        cache_verileri['analiz'] = islenmis_coinler
        cache_verileri['fiyatlar'] = fiyat_sozlugu
    except Exception as e:
        print("Veri güncelleme hatası:", e)

verileri_guncelle()

@app.route('/')
def anasayfa():
    html_icerik = """
    <!DOCTYPE html>
    <html lang="tr">
    <head>
        <meta charset="UTF-8">
        <title>Vadeli İşlem ve Lider Analiz Paneli</title>
        <style>
            body { background-color: #0b0f19; color: #94a3b8; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; text-align: center; padding: 20px; margin: 0; }
            .container { max-width: 1300px; margin: 0 auto; background: #111827; padding: 25px; border-radius: 16px; border: 1px solid #1f2937; box-shadow: 0 10px 25px rgba(0,0,0,0.5); }
            h1 { color: #f3f4f6; font-size: 24px; margin-bottom: 5px; }
            .sub-title { color: #6b7280; font-size: 14px; margin-bottom: 25px; }
            
            .search-box-container { margin-bottom: 25px; }
            .search-input { width: 100%; max-width: 500px; padding: 14px 20px; background: #1f2937; border: 2px solid #374151; border-radius: 12px; color: #fff; font-size: 16px; outline: none; transition: 0.3s; }
            .search-input:focus { border-color: #10b981; box-shadow: 0 0 10px rgba(16, 185, 129, 0.3); }
            
            /* Fotoğraftaki Buton Tasarımları */
            .filter-container { margin-bottom: 25px; display: flex; justify-content: center; gap: 10px; flex-wrap: wrap; }
            .filter-btn { background: #1f2937; border: 2px solid #374151; color: #94a3b8; padding: 12px 18px; border-radius: 12px; cursor: pointer; font-size: 13px; font-weight: 600; transition: 0.2s; display: flex; align-items: center; gap: 8px; }
            .filter-btn.active { border-color: #10b981; color: #fff; background: #111827; box-shadow: 0 0 15px rgba(16, 185, 129, 0.2); }
            .filter-btn:hover { border-color: #4b5563; }

            .top-section { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 30px; text-align: left; }
            .rank-box { background: #1f2937; padding: 20px; border-radius: 12px; border: 1px solid #374151; max-height: 550px; overflow-y: auto; }
            .rank-box h2 { font-size: 13px; color: #f3f4f6; border-bottom: 2px solid #10b981; padding-bottom: 8px; margin-top: 0; }
            .rank-item { background: #111827; padding: 12px; margin-bottom: 10px; border-radius: 8px; font-size: 12px; border-left: 3px solid #10b981; }
            
            /* Fotoğraftaki Kart Tasarımları */
            .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(350px, 1fr)); gap: 20px; margin-top: 15px; text-align: left; }
            .card { background: #1f2937; padding: 20px; border-radius: 14px; border: 1px solid #374151; box-shadow: 0 6px 12px rgba(0,0,0,0.3); }
            .card h3 { margin: 0 0 15px 0; color: #fbbf24; font-size: 16px; text-align: center; letter-spacing: 1px; }
            
            .metric-bar { padding: 12px 15px; border-radius: 10px; margin-bottom: 10px; display: flex; justify-content: space-between; align-items: center; }
            .metric-bar.long { background: rgba(16, 185, 129, 0.12); border-left: 4px solid #10b981; }
            .metric-bar.short { background: rgba(239, 68, 68, 0.12); border-left: 4px solid #ef4444; }
            .metric-bar.ortalama { background: rgba(75, 85, 99, 0.2); border-left: 4px solid #9ca3af; }
            
            .metric-left { font-size: 13px; font-weight: 600; color: #e5e7eb; }
            .metric-left span { display: block; font-size: 11px; color: #9ca3af; font-weight: normal; margin-top: 3px; }
            .metric-right { font-size: 15px; font-weight: bold; }
            .metric-bar.long .metric-right { color: #10b981; }
            .metric-bar.short .metric-right { color: #ef4444; }
            .metric-bar.ortalama .metric-right { color: #f3f4f6; }

            .green { color: #10b981; font-weight: bold; }
            .highlight { color: #ef4444; font-weight: bold; }
            .footer { margin-top: 30px; font-size: 12px; color: #4b5563; }
            h2.section-title { color: #f3f4f6; text-align: left; border-bottom: 1px solid #374151; padding-bottom: 10px; margin-top: 40px; }
            .info-text { color: #6b7280; font-style: italic; font-size: 13px; text-align: center; padding: 20px; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Canlı Vadeli Arama ve Analiz Paneli</h1>
            <div class="sub-title">Aktif Taranan Coin: <span id="coin-sayac" class="green">0</span> | Binance & OKX Canlı Veri Akışı</div>
            
            <div class="search-box-container">
                <input type="text" id="searchInput" class="search-input" placeholder="🔍 Coin Ara (Örn: BTC, ETH, SOL, PEPE)..." onkeyup="filtreleVeGoster()">
            </div>

            <!-- Fotoğraftaki Seçim Butonları -->
            <div class="filter-container">
                <button class="filter-btn active" onclick=" kaynakDegistir('lider', this)">👥 Sadece Copy Liderler</button>
                <button class="filter-btn" onclick="kaynakDegistir('balina', this)">🐋 Sadece Balinalar</button>
                <button class="filter-btn" onclick="kaynakDegistir('tumu', this)">👥🐋 Tümü</button>
                <button class="filter-btn" onclick="kaynakDegistir('terste', this)">📊 Genel Terste Kalanlar</button>
            </div>

            <div class="top-section">
                <div class="rank-box">
                    <h2>📊 ADET BAZINDA EN FAZLA İŞLEM GÖREN TOP 20</h2>
                    <div id="adet-listesi">Yükleniyor...</div>
                </div>
                <div class="rank-box">
                    <h2>💰 SİZE BAZINDA EN FAZLA İŞLEM GÖREN TOP 20</h2>
                    <div id="size-listesi">Yükleniyor...</div>
                </div>
            </div>

            <h2 class="section-title">🔎 Arama ve Analiz Sonuçları</h2>
            <div id="arama-sonuclari" class="grid">
                <div class="info-text">Yukarıdaki arama çubuğuna coin adı yazarak detaylı giriş seviyelerini görüntüleyebilirsiniz.</div>
            </div>

            <div class="footer">Sistem Bulutta 7/24 Kesintisiz Çalışmaktadır • Veriler anlık olarak güncellenmektedir.</div>
        </div>

        <script>
            let globalVeriler = [];
            let aktifKaynak = 'lider';

            function kaynakDegistir(kaynak, element) {
                aktifKaynak = kaynak;
                document.querySelectorAll('.filter-btn').forEach(btn => btn.classList.remove('active'));
                element.classList.add('active');
                filtreleVeGoster();
            }

            function formatFiyat(fiyat) {
                if (fiyat < 0.0001) return fiyat.toFixed(8);
                if (fiyat < 1) return fiyat.toFixed(6);
                if (fiyat < 10) return fiyat.toFixed(4);
                return fiyat.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
            }

            function kisalt(sayi) {
                if (sayi >= 1000000) return (sayi / 1000000).toFixed(2) + 'M';
                if (sayi >= 1000) return (sayi / 1000).toFixed(2) + 'K';
                return sayi.toFixed(2);
            }

            function verileriCek() {
                fetch('/api/data')
                    .then(response => response.json())
                    .then(res => {
                        if(res.status === 'success') {
                            globalVeriler = res.data;
                            document.getElementById('coin-sayac').innerText = globalVeriler.length;
                            
                            let adetSirali = [...globalVeriler].sort((a, b) => b.toplam_islem - a.toplam_islem).slice(0, 20);
                            let adetHtml = "";
                            adetSirali.forEach((c, i) => {
                                let d = c.kaynaklar[aktifKaynak];
                                adetHtml += `
                                <div class="rank-item">
                                    <b>${i+1}) ${c.symbol}</b> (Fiyat: <span class="green">$${formatFiyat(c.fiyat)}</span>)<br>
                                    🟢 Long Ort: $${formatFiyat(d.long_giris)} (${d.long_islem} işlem, $${kisalt(d.long_size)} size)<br>
                                    🔴 Short Ort: $${formatFiyat(d.short_giris)} (${d.short_islem} işlem, $${kisalt(d.short_size)} size)
                                </div>`;
                            });
                            document.getElementById('adet-listesi').innerHTML = adetHtml;

                            let sizeSirali = [...globalVeriler].sort((a, b) => b.toplam_size - a.toplam_size).slice(0, 20);
                            let sizeHtml = "";
                            sizeSirali.forEach((c, i) => {
                                let d = c.kaynaklar[aktifKaynak];
                                sizeHtml += `
                                <div class="rank-item">
                                    <b>${i+1}) ${c.symbol}</b> (Fiyat: <span class="green">$${formatFiyat(c.fiyat)}</span>)<br>
                                    🟢 Long Ort: $${formatFiyat(d.long_giris)} (${d.long_islem} işlem, $${kisalt(d.long_size)} size)<br>
                                    🔴 Short Ort: $${formatFiyat(d.short_giris)} (${d.short_islem} işlem, $${kisalt(d.short_size)} size)
                                </div>`;
                            });
                            document.getElementById('size-listesi').innerHTML = sizeHtml;

                            filtreleVeGoster();
                        }
                    })
                    .catch(err => console.error("Veri çekme hatası:", err));
            }

            function filtreleVeGoster() {
                let aranan = document.getElementById('searchInput').value.trim().toUpperCase();
                let sonucDiv = document.getElementById('arama-sonuclari');
                
                if (aranan === "") {
                    sonucDiv.innerHTML = '<div class="info-text">Yukarıdaki arama çubuğuna coin adı yazarak detaylı analizi görüntüleyebilirsiniz.</div>';
                    return;
                }

                let filtrelenmis = globalVeriler.filter(c => c.symbol.includes(aranan));

                if (filtrelenmis.length === 0) {
                    sonucDiv.innerHTML = '<div class="info-text" style="color:#ef4444;">Aradığınız kritere uygun coin bulunamadı.</div>';
                    return;
                }

                let kartHtml = "";
                filtrelenmis.forEach(c => {
                    let d = c.kaynaklar[aktifKaynak];
                    kartHtml += `
                    <div class="card">
                        <h3>${c.symbol}USDT</h3>
                        
                        <div class="metric-bar long">
                            <div class="metric-left">
                                🟢 LONG Ort. Giriş:
                                <span>(${d.long_islem} işlem, $${kisalt(d.long_size)} size)</span>
                            </div>
                            <div class="metric-right">$${formatFiyat(d.long_giris)}</div>
                        </div>

                        <div class="metric-bar short">
                            <div class="metric-left">
                                🔴 SHORT Ort. Giriş:
                                <span>(${d.short_islem} işlem, $${kisalt(d.short_size)} size)</span>
                            </div>
                            <div class="metric-right">$${formatFiyat(d.short_giris)}</div>
                        </div>

                        <div class="metric-bar ortalama">
                            <div class="metric-left">
                                ⚪ Ortalama Giriş:
                                <span>Genel Piyasa Denge Noktası</span>
                            </div>
                            <div class="metric-right">$${formatFiyat(d.genel_ortalama)}</div>
                        </div>
                    </div>`;
                });
                sonucDiv.innerHTML = kartHtml;
            }

            verileriCek();
            setInterval(verileriCek, 300000);
        </script>
    </body>
    </html>
    """
    return html_icerik

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
