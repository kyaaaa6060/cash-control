import threading
import time
from flask import Flask, jsonify
import requests

app = Flask(__name__)

cached_pivots = {
    "pivot": 0,
    "direnc_1": 0,
    "destek_1": 0,
    "direnc_2": 0,
    "destek_2": 0,
}


def calculate_pivot_points(high, low, close):
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
  global cached_pivots
  while True:
    try:
      url = "https://api.binance.com/api/v3/klines?symbol=ADAUSDT&interval=1h&limit=2"
      response = requests.get(url, timeout=5)
      data = response.json()

      if len(data) >= 2:
        last_closed_candle = data[-2]
        high = float(last_closed_candle[2])
        low = float(last_closed_candle[3])
        close = float(last_closed_candle[4])

        cached_pivots = calculate_pivot_points(high, low, close)
    except Exception as e:
      print(f"Veri güncelleme hatası: {e}")

    # Döngü bittikten sonra 1 dakika bekler
    time.sleep(60)


@app.route("/")
def home():
  return jsonify(cached_pivots)


if __name__ == "__main__":
  # Uygulama ayağa kalkar kalkmaz BEKLEMEDEN ilk veriyi bir kez çekelim ki 0 görünmesin:
  try:
    initial_res = requests.get(
        "https://api.binance.com/api/v3/klines?symbol=ADAUSDT&interval=1h&limit=2",
        timeout=5,
    )
    init_data = initial_res.json()
    if len(init_data) >= 2:
      c = init_data[-2]
      cached_pivots = calculate_pivot_points(
          float(c[2]), float(c[3]), float(c[4])
      )
  except Exception as e:
    print(f"İlk veri çekme hatası: {e}")

  # Ardından arka plan döngüsünü başlat
  t = threading.Thread(target=update_market_data, daemon=True)
  t.start()

  app.run(host="0.0.0.0", port=5000)
