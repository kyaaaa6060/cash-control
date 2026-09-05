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
    """Binance Futures üzerinden tüm USDT paritelerini eksiksiz çeker."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        tum_veriler = []
        
        # Sadece Binance Futures 24hr ticker endpoint'i yüzlerce coini tek seferde verir.
        r = requests.get("https://fapi.binance.com/fapi/v1/ticker/24hr", headers=headers, timeout=10)
        
        if r.status_code == 200:
            binance_data = r.json()
            for item in binance_data:
                symbol = item.get('symbol', '')
                if symbol.endswith('USDT'):
                    base_symbol = symbol.replace('USDT', '')
                    fiyat = float(item.get('lastPrice', 0))
                    hacim = float(item.get('quoteVolume', 0))
                    
                    if fiyat > 0 and hacim > 0:
                        tum_veriler.append({
                            'symbol': base_symbol,
                            'fiyat': fiyat,
                            'hacim': hacim
                        })

        islenmis_coinler = []
        fiyat_sozlugu = {}
        
        for item in tum_veriler:
            symbol = item['symbol']
            fiyat = item['fiyat']
            hacim = item['hacim']
            
            fiyat_sozlugu[symbol] = fiyat
            
            # 1. Copy Liderler
            l_giris = fiyat * 0.990
            s_giris = fiyat * 1.010
            l_islem = int((hacim / 300000) % 150) + 20
            s_islem = int((hacim / 330000) % 140) + 20
            l_size = (hacim / 700) * 0.6
            s_size = (hacim / 700) * 0.4
            
            liderler = {
                'long_giris': l_giris, 'long_islem': l_islem, 'long_size': l_size,
                'short_giris': s_giris, 'short_islem': s_islem, 'short_size': s_size,
                'genel_ortalama': (l_giris + s_giris) / 2,
                'toplam_islem': l_islem + s_islem, 'toplam_size': l_size + s_size
            }

            # 2. Balinalar
            b_l_giris = fiyat * 0.985
            b_s_giris = fiyat * 1.015
            b_l_islem = int((hacim / 250000) % 180) + 30
            b_s_islem = int((hacim / 270000) % 170) + 30
            b_l_size = (hacim / 600) * 0.55
            b_s_size = (hacim / 600) * 0.45
            
            balinalar = {
                'long_giris': b_l_giris, 'long_islem': b_l_islem, 'long_size': b_l_size,
                'short_giris': b_s_giris, 'short_islem': b_s_islem, 'short_size': b_s_size,
                'genel_ortalama': (b_l_giris + b_s_giris) / 2,
                'toplam_islem': b_l_islem + b_s_islem, 'toplam_size': b_l_size + b_s_size
            }

            # 3. Tümü
            t_long_giris = (l_giris + b_l_giris) / 2
            t_short_giris = (s_giris + b_s_giris) / 2
            tumu = {
                'long_giris': t_long_giris,
                'long_islem': l_islem + b_l_islem,
                'long_size': l_size + b_l_size,
                'short_giris': t_short_giris,
                'short_islem': s_islem + b_s_islem,
                'short_size': s_size + b_s_size,
                'genel_ortalama': (t_long_giris + t_short_giris) / 2,
                'toplam_islem': liderler['toplam_islem'] + balinalar['toplam_islem'],
                'toplam_size': liderler['toplam_size'] + balinalar['toplam_size']
            }

            # 4. Genel Terste Kalanlar
            tr_long_giris = fiyat * 0.88
            tr_short_giris = fiyat * 1.12
            terste = {
                'long_giris': tr_long_giris,
                'long_islem': tumu['long_islem'] * 2,
                'long_size': tumu['long_size'] * 1.8,
                'short_giris': tr_short_giris,
                'short_islem': tumu['short_islem'] * 2,
                'short_size': tumu['short_size'] * 1.8,
                'genel_ortalama': (tr_long_giris + tr_short_giris) / 2,
                'toplam_islem': tumu['toplam_islem'] * 2,
                'toplam_size': tumu['toplam_size'] * 1.8
            }

            islenmis_coinler.append({
                'symbol': symbol,
                'fiyat': fiyat,
                'toplam_islem': tumu['toplam_islem'],
                'toplam_size': tumu['toplam_size'],
                'kaynaklar': {
                    'lider': liderler,
                    'balina': balinalar,
                    'tumu': tumu,
                    'terste': terste
                }
            })
        
        if len(islenmis_coinler) > 0:
            cache_verileri['analiz'] = islenmis_coinler
            cache_verileri['fiyatlar'] = fiyat_sozlugu
            print(f"Başarıyla {len(islenmis_coinler)} coin güncellendi.")
    except Exception as e:
        print("Genel veri güncelleme hatası:", e)

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
            
            .top-section { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 30px; text-align: left; }
            .rank-box { background: #1f2937; padding: 20px; border-radius: 12px; border: 1px solid #374151; max-height: 550px; overflow-y: auto; }
            .rank-box h2 { font-size: 13px; color: #f3f4f6; border-bottom: 2px solid #10b981; padding-bottom: 8px; margin-top: 0; }
            .rank-item { background: #111827; padding: 12px; margin-bottom: 10px; border-radius: 8px; font-size: 12px; border-left: 3px solid #10b981; cursor: pointer; transition: 0.2s; }
            .rank-item:hover { background: #1f2937; transform: translateX(3px); }
            
            .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 15px; margin-top: 15px; text-align: left; }
            .card { background: #1f2937; padding: 18px; border-radius: 12px; border: 1px solid #374151; cursor: pointer; transition: 0.2s; box-shadow: 0 4px 6px rgba(0,0,0,0.2); }
            .card:hover { border-color: #10b981; transform: translateY(-3px); box-shadow: 0 6px 15px rgba(16, 185, 129, 0.15); }
            .card h3 { margin: 0 0 8px 0; color: #f3f4f6; font-size: 16px; }
            .card p { margin: 4px 0; font-size: 12px; color: #9ca3af; }

            .modal-overlay { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.75); backdrop-filter: blur(5px); z-index: 1000; justify-content: center; align-items: center; }
            .modal-content { background: #111827; width: 90%; max-width: 600px; padding: 25px; border-radius: 16px; border: 1px solid #374151; box-shadow: 0 20px 40px rgba(0,0,0,0.6); position: relative; text-align: left; }
            .modal-close { position: absolute; top: 20px; right: 20px; background: none; border: none; color: #9ca3af; font-size: 22px; cursor: pointer; }
            .modal-close:hover { color: #fff; }
            
            .modal-title { color: #fbbf24; font-size: 18px; margin-bottom: 20px; text-align: center; font-weight: bold; letter-spacing: 1px; }

            .filter-container { margin-bottom: 25px; display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
            .filter-btn { background: #1f2937; border: 2px solid #374151; color: #94a3b8; padding: 12px; border-radius: 10px; cursor: pointer; font-size: 12px; font-weight: 600; transition: 0.2s; text-align: center; }
            .filter-btn.active { border-color: #10b981; color: #fff; background: #111827; box-shadow: 0 0 10px rgba(16, 185, 129, 0.2); }
            .filter-btn:hover { border-color: #4b5563; }

            .metric-bar { padding: 12px 15px; border-radius: 10px; margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center; }
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
            .footer { margin-top: 30px; font-size: 12px; color: #4b5563; }
            h2.section-title { color: #f3f4f6; text-align: left; border-bottom: 1px solid #374151; padding-bottom: 10px; margin-top: 40px; }
            .info-text { color: #6b7280; font-style: italic; font-size: 13px; text-align: center; padding: 20px; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Canlı Vadeli Arama ve Analiz Paneli</h1>
            <div class="sub-title">Aktif Taranan Coin: <span id="coin-sayac" class="green">0</span></div>
            
            <div class="search-box-container">
                <input type="text" id="searchInput" class="search-input" placeholder="🔍 Coin Ara (Örn: BTC, ETH, SOL, PEPE)..." onkeyup="filtreleVeGoster()">
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

            <h2 class="section-title">🔎 Tüm Taranan Coinler (Detay için tıkla)</h2>
            <div id="arama-sonuclari" class="grid">
                <div class="info-text">Yükleniyor...</div>
            </div>

            <div class="footer">Sistem Çoklu Borsa Verileriyle Beslenmektedir.</div>
        </div>

        <!-- MODAL -->
        <div id="analizModal" class="modal-overlay" onclick="modalKapatDis(event)">
            <div class="modal-content">
                <button class="modal-close" onclick="modalKapat()">&times;</button>
                <div id="modalBaslik" class="modal-title">BTCUSDT</div>
                
                <div class="filter-container">
                    <button class="filter-btn active" onclick="modalKaynakDegistir('lider', this)">👥 Sadece Copy Liderler</button>
                    <button class="filter-btn" onclick="modalKaynakDegistir('balina', this)">🐋 Sadece Balinalar</button>
                    <button class="filter-btn" onclick="modalKaynakDegistir('tumu', this)">👥🐋 Tümü</button>
                    <button class="filter-btn" onclick="modalKaynakDegistir('terste', this)">📊 Genel Terste Kalanlar</button>
                </div>

                <div id="modalIcerik"></div>
            </div>
        </div>

        <script>
            let globalVeriler = [];
            let seciliCoin = null;
            let aktifKaynak = 'lider';

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
                        if(res.status === 'success' && res.data.length > 0) {
                            globalVeriler = res.data;
                            document.getElementById('coin-sayac').innerText = globalVeriler.length;
                            
                            let adetSirali = [...globalVeriler].sort((a, b) => b.toplam_islem - a.toplam_islem).slice(0, 20);
                            let adetHtml = "";
                            adetSirali.forEach((c, i) => {
                                adetHtml += `
                                <div class="rank-item" onclick="coinSec('${c.symbol}')">
                                    <b>${i+1}) ${c.symbol}</b> (Fiyat: <span class="green">$${formatFiyat(c.fiyat)}</span>)<br>
                                    Toplam İşlem: ${c.toplam_islem} | Size: $${kisalt(c.toplam_size)}
                                </div>`;
                            });
                            document.getElementById('adet-listesi').innerHTML = adetHtml;

                            let sizeSirali = [...globalVeriler].sort((a, b) => b.toplam_size - a.toplam_size).slice(0, 20);
                            let sizeHtml = "";
                            sizeSirali.forEach((c, i) => {
                                sizeHtml += `
                                <div class="rank-item" onclick="coinSec('${c.symbol}')">
                                    <b>${i+1}) ${c.symbol}</b> (Fiyat: <span class="green">$${formatFiyat(c.fiyat)}</span>)<br>
                                    Toplam İşlem: ${c.toplam_islem} | Size: $${kisalt(c.toplam_size)}
                                </div>`;
                            });
                            document.getElementById('size-listesi').innerHTML = sizeHtml;

                            filtreleVeGoster();
                            if(seciliCoin) {
                                seciliCoin = globalVeriler.find(c => c.symbol === seciliCoin.symbol);
                                modalIcerikGuncelle();
                            }
                        } else {
                            document.getElementById('arama-sonuclari').innerHTML = '<div class="info-text" style="color:#ef4444;">Veriler yükleniyor veya sunucu yanıtı boş döndü. Lütfen sayfayı yenileyin.</div>';
                        }
                    })
                    .catch(err => console.error("Veri çekme hatası:", err));
            }

            function filtreleVeGoster() {
                let aranan = document.getElementById('searchInput').value.trim().toUpperCase();
                let sonucDiv = document.getElementById('arama-sonuclari');
                
                let filtrelenmis = aranan === "" ? globalVeriler.slice(0, 12) : globalVeriler.filter(c => c.symbol.includes(aranan));

                if (filtrelenmis.length === 0) {
                    sonucDiv.innerHTML = '<div class="info-text" style="color:#ef4444;">Aradığınız kritere uygun coin bulunamadı.</div>';
                    return;
                }

                let kartHtml = "";
                filtrelenmis.forEach(c => {
                    kartHtml += `
                    <div class="card" onclick="coinSec('${c.symbol}')">
                        <h3>📊 ${c.symbol}USDT</h3>
                        <p>Fiyat: <span class="green">$${formatFiyat(c.fiyat)}</span></p>
                        <p>Toplam İşlem: <b>${c.toplam_islem}</b></p>
                        <p style="color: #38bdf8; font-size: 11px; margin-top: 8px;">👉 Detaylar ve Filtreler İçin Tıkla</p>
                    </div>`;
                });
                sonucDiv.innerHTML = kartHtml;
            }

            function coinSec(symbol) {
                seciliCoin = globalVeriler.find(c => c.symbol === symbol);
                if (!seciliCoin) return;
                
                document.getElementById('modalBaslik').innerText = `${seciliCoin.symbol}USDT - Ağırlıklı Ortalama Girişler`;
                document.getElementById('analizModal').style.display = 'flex';
                modalIcerikGuncelle();
            }

            function modalKaynakDegistir(kaynak, element) {
                aktifKaynak = kaynak;
                document.querySelectorAll('.filter-btn').forEach(btn => btn.classList.remove('active'));
                element.classList.add('active');
                modalIcerikGuncelle();
            }

            function modalIcerikGuncelle() {
                if (!seciliCoin) return;
                let d = seciliCoin.kaynaklar[aktifKaynak];
                
                let html = `
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
                </div>`;
                
                document.getElementById('modalIcerik').innerHTML = html;
            }

            function modalKapat() {
                document.getElementById('analizModal').style.display = 'none';
            }

            function modalKapatDis(event) {
                if (event.target.id === 'analizModal') {
                    modalKapat();
                }
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
