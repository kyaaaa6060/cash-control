from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
import requests

app = FastAPI()

def get_sample_data():
    return {
        "BTC": {
            "symbol": "BTCUSDT",
            "markPrice": 65000.0,
            "fundingRate": 0.06,
            "openInterestUSD": 12000000,
            "signals": [
                {"badge": "🔴 LONG SQUEEZE", "color": "#f44336", "desc": "Aşırı Long birikimi + Yüksek OI."},
                {"badge": "⚡ FONLAMA MAKASI", "color": "#aa00ff", "desc": "Binance vs HL arasında fonlama farkı var."}
            ]
        },
        "ETH": {
            "symbol": "ETHUSDT",
            "markPrice": 3500.0,
            "fundingRate": -0.04,
            "openInterestUSD": 9000000,
            "signals": [
                {"badge": "🟢 SHORT SQUEEZE", "color": "#4caf50", "desc": "Aşırı Short birikimi + Negatif fonlama."}
            ]
        }
    }

@app.get("/", response_class=HTMLResponse)
def read_index():
    try:
        with open("index.html", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "<h1>index.html dosyası bulunamadı! Lütfen GitHub'a index.html dosyasını yükleyin.</h1>"

# Frontend hangi adresten veri istiyorsa hepsine cevap verelim:
@app.get("/api/data")
def api_data():
    return JSONResponse(content=get_sample_data())

@app.get("/api/market-data")
def api_market_data():
    return JSONResponse(content=get_sample_data())

@app.get("/data")
def data_route():
    return JSONResponse(content=get_sample_data())
