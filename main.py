from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
import requests

app = FastAPI()

def analyze_coin_tactics(mark_price, funding_rate, hl_funding, binance_funding, combined_avg, whale_data, all_data, oi_usd):
    signals = []

    # 1. BALİNA MALİYET SAVUNMASI
    if whale_data and "long_avg" in whale_data and "short_avg" in whale_data:
        whale_long_dist = abs(mark_price - whale_data["long_avg"]) / mark_price if whale_data["long_avg"] else 999
        whale_short_dist = abs(mark_price - whale_data["short_avg"]) / mark_price if whale_data["short_avg"] else 999

        if whale_long_dist <= 0.008 and mark_price >= whale_data["long_avg"]:
            signals.append({
                "badge": "🛡️ BALİNA LONG SAVUNMASI",
                "color": "#00c853",
                "desc": "Fiyat balina Long maliyetinde. Desteğe yakın."
            })
        elif whale_short_dist <= 0.008 and mark_price <= whale_data["short_avg"]:
            signals.append({
                "badge": "🛡️ BALİNA SHORT SAVUNMASI",
                "color": "#d50000",
                "desc": "Fiyat balina Short maliyetinde. Dirence yakın."
            })

    # 2. LİKİDASYON SÜPÜRME (SWEEP) BÖLGESİ
    if all_data and "long_avg" in all_data and all_data["long_avg"] > 0:
        all_long_dev = ((mark_price - all_data["long_avg"]) / all_data["long_avg"]) * 100
        if -2.5 <= all_long_dev <= -1.2:
            signals.append({
                "badge": "🎯 LİKİDASYON AV BÖLGESİ",
                "color": "#ff6d00",
                "desc": "Perakende maliyetinin %2 altı. Stop süpürme iğnesi gelebilir."
            })

    # 3. HACİMSEL DENGESİZLİK (SIZE RATIO)
    if combined_avg and "long_size" in combined_avg and "short_size" in combined_avg:
        total_l_size = combined_avg["long_size"]
        total_s_size = combined_avg["short_size"]
        size_ratio = total_l_size / total_s_size if total_s_size > 0 else 1.0

        if size_ratio >= 1.75:
            signals.append({
                "badge": "🐋 BÜYÜK PARA LONG",
                "color": "#00b0ff",
                "desc": "Long hacmi Short hacminin 1.75 katı üzerinde."
            })
        elif size_ratio <= 0.55:
            signals.append({
                "badge": "🐋 BÜYÜK PARA SHORT",
                "color": "#ff1744",
                "desc": "Short hacmi Long hacminin 1.8 katı üzerinde."
            })

    # 4. BORSALAR ARASI FONLAMA MAKASI
    funding_gap = abs(binance_funding - hl_funding)
    if funding_gap >= 0.04:
        signals.append({
            "badge": "⚡ FONLAMA MAKASI",
            "color": "#aa00ff",
            "desc": f"Binance vs HL arasında %{funding_gap:.3f} makas var."
        })

    # 5. SQUEEZE (PATLATMA) RİSKLERİ
    if funding_rate >= 0.05 and oi_usd > 8_000_000:
        signals.append({
            "badge": "🔴 LONG SQUEEZE",
            "color": "#f44336",
            "desc": "Aşırı Long birikimi + Yüksek OI."
        })
    elif funding_rate <= -0.04 and oi_usd > 8_000_000:
        signals.append({
            "badge": "🟢 SHORT SQUEEZE",
            "color": "#4caf50",
            "desc": "Aşırı Short birikimi + Negatif fonlama."
        })

    return signals

@app.get("/", response_class=HTMLResponse)
def read_index():
    try:
        with open("index.html", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "<h1>index.html dosyası bulunamadı!</h1>"

@app.get("/api/tactics-test")
def test_tactics():
    # Örnek test verisi simülasyonu
    sample_signals = analyze_coin_tactics(
        mark_price=65000.0,
        funding_rate=0.06,
        hl_funding=0.01,
        binance_funding=0.055,
        combined_avg={"long_size": 1500000, "short_size": 800000},
        whale_data={"long_avg": 64800.0, "short_avg": 65500.0},
        all_data={"long_avg": 66000.0},
        oi_usd=12000000
    )
    return {"status": "active", "sample_signals": sample_signals}
