import threading
import time
from flask import Flask, jsonify, render_template
import requests

app = Flask(__name__)

# Global değişkenler (Seviyeleri sabitlemek için)
cached_pivots = {
    "pivot": 0,
    "direnc_1": 0,
    "destek_1": 0,
    "direnc_2": 0,
    "destek_2": 0,
}


def calculate_pivot_points(high, low, close):
  """Klasik Pivot Noktaları Hesaplama (Sabit Mantık)"""
  pivot = (high + low + close) / 3
  r1 = (2 * pivot) - low
  s1 = (2 * pivot) - high
  r2 = pivot + (high - low)
  s2 = pivot - (high - low)

  return {
      "pivot": round(pivot, 4),
      "direnc_1": round(r1, 4),
      "destek_1": round(s1, 4),
      "direnc_2": round(r2, 4),
      "destek_2": round(s2, 4),
  }


def update_market_data():
  """Arka planda çalışıp son mum verilerini çeken döngü"""
  global cached_pivots
  while True:
    try:
      # Binance üzerinden ADAUSDT 1 saatlik son kapanmış mum verisini alıyoruz
      url = "https://api.binance.com/api/v3/klines?symbol=ADAUSDT&interval=1h&limit=2"
      response = requests.get(url, timeout=5)
      data = response.json()

      if len(data) >= 2:
        # data[-2] bir önceki (tamamlanmış) mumu verir, böylece değerler o mum boyunca sabit kalır
        last_closed_candle = data[-2]
        high = float(last_closed_candle[2])
        low = float(last_closed_candle[3])
        close = float(last_closed_candle[4])

        cached_pivots = calculate_pivot_points(high, low, close)
    except Exception as e:
      print(f"Veri güncelleme hatası: {e}")

    # Her 1 dakikada bir kontrol eder (mum açılana kadar seviyeler sabittir)
    time.sleep(60)


@app.route("/")
def home():
  # Ana sayfada veya API isteğinde sabit pivotları döndürür
  return jsonify(cached_pivots)


if __name__ == "__main__":
  # Arka plan veri güncelleme iş parçacığını (thread) başlat
  t = threading.Thread(target=update_market_data, daemon=True)
  t.start()

  # Flask uygulamasını başlat
  app.run(host="0.0.0.0", port=5000)
