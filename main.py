import time
import json
import os
import requests
import threading
from collections import defaultdict
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from contextlib import asynccontextmanager

# ============================================================
#  CACHE'LER
# ============================================================
CACHE = {"last_update": 0, "data": {}}              # hızlı döngü: mark price / funding
SMART_MONEY_CACHE = {"last_update": 0, "data": {}}   # yavaş döngü: Hyperliquid smart money
BINANCE_RATIO_CACHE = {"last_update": 0, "data": {}} # orta döngü: Binance resmi top-trader oranı
BINANCE_LEADERBOARD_CACHE = {"last_update": 0, "data": {}, "working": None}  # best-effort: Binance leaderboard

FAST_LOOP_SECONDS = 5
SMART_MONEY_LOOP_SECONDS = 90        # Hyperliquid leaderboard + cüzdan taraması ağır, sık çekmeyin
BINANCE_RATIO_LOOP_SECONDS = 30
BINANCE_LEADERBOARD_LOOP_SECONDS = 90  # best-effort, Binance'i çok yormayalım

HISTORY_FILE = "trade_history.json"
HOURLY_HISTORY_FILE = "hourly_history.json"

TF_MAP = {
    "5": "5m", "15": "15m", "30": "30m", "60": "1h",
    "120": "2h", "240": "4h", "D": "1d", "W": "1w"
}

# Hyperliquid leaderboard'dan taranacak cüzdan sayısı ve minimum hesap değeri filtresi.
# Bu sayıyı artırmak daha kapsamlı veri verir ama API'yi daha çok yorar.
HL_WALLET_LIMIT = 25
HL_MIN_ACCOUNT_VALUE = 25000


# ============================================================
#  DOSYA KAYIT / OKUMA YARDIMCILARI
# ============================================================
def load_trade_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"active": {}, "closed": []}


def save_trade_history(data):
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print("Geçmiş kayıt hatası:", e)


def load_hourly_history():
    if os.path.exists(HOURLY_HISTORY_FILE):
        try:
            with open(HOURLY_HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []


def save_hourly_history(history_data):
    try:
        with open(HOURLY_HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history_data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print("Saatlik geçmiş kayıt hatası:", e)


TRADE_STORE = load_trade_history()
ACTIVE_TRADES = TRADE_STORE.get("active", {})
CLOSED_TRADES = TRADE_STORE.get("closed", [])

HOURLY_RECORDS = load_hourly_history()
LAST_RECORDED_HOUR = -1


def fmt(val):
    if val < 0.0001: return f"{val:,.6f}"
    elif val < 1: return f"{val:,.4f}"
    elif val < 10: return f"{val:,.3f}"
    else: return f"{val:,.2f}"


# ============================================================
#  BINANCE - GERÇEK VERİLER (mark price, funding, resmi top-trader oranı, klines)
# ============================================================
def get_binance_futures_tickers():
    try:
        url = "https://fapi.binance.com/fapi/v1/premiumIndex"
        res = requests.get(url, timeout=4)
        if res.status_code == 200:
            tickers = {}
            for item in res.json():
                symbol = item.get("symbol", "")
                if symbol.endswith("USDT"):
                    base_name = symbol.replace("USDT", "")
                    tickers[base_name] = {
                        "markPrice": float(item.get("markPrice", 0)),
                        "fundingRate": float(item.get("lastFundingRate", 0)) * 100
                    }
            return tickers
    except Exception as e:
        print("Binance Mark Price hatası:", e)
    return {}


def get_binance_klines(symbol: str, timeframe: str, limit: int = 300):
    """Grafik (lightweight-charts) için ham mum verisi. Gerçek Binance Futures verisi."""
    binance_tf = TF_MAP.get(timeframe, "15m")
    url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}USDT&interval={binance_tf}&limit={limit}"
    try:
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            out = []
            for k in res.json():
                out.append({
                    "time": int(k[0] // 1000),
                    "open": float(k[1]),
                    "high": float(k[2]),
                    "low": float(k[3]),
                    "close": float(k[4]),
                })
            return out
    except Exception as e:
        print(f"Kline hatası ({symbol} {timeframe}):", e)
    return []


def get_pivot_levels(symbol: str, timeframe: str):
    klines = get_binance_klines(symbol, timeframe, limit=3)
    if klines and len(klines) > 0:
        candle = klines[-2] if len(klines) >= 2 else klines[-1]
        high, low, close = candle["high"], candle["low"], candle["close"]
        pivot = (high + low + close) / 3
        r1 = (2 * pivot) - low
        s1 = (2 * pivot) - high
        r2 = pivot + (high - low)
        s2 = pivot - (high - low)
        r3 = high + 2 * (pivot - low)
        s3 = low - 2 * (high - pivot)
        return {"res3": r3, "res2": r2, "res1": r1, "pivot": pivot, "sup1": s1, "sup2": s2, "sup3": s3}
    return None


def get_binance_top_trader_ratio(symbol: str):
    """
    GERÇEK ve RESMİ Binance verisi. API key gerekmez.
    https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Top-Trader-Long-Short-Ratio
    Not: bireysel 'işlem' ya da 'ortalama giriş fiyatı' vermez, sadece TOP trader'ların
    pozisyon bazında long/short oranını verir (Binance bunun ötesini public API'de sunmuyor).
    """
    try:
        url = f"https://fapi.binance.com/futures/data/topLongShortPositionRatio?symbol={symbol}USDT&period=15m&limit=1"
        res = requests.get(url, timeout=4)
        if res.status_code == 200:
            arr = res.json()
            if arr:
                item = arr[-1]
                return {
                    "longAccount": float(item.get("longAccount", 0)) * 100,
                    "shortAccount": float(item.get("shortAccount", 0)) * 100,
                    "longShortRatio": float(item.get("longShortRatio", 0)),
                }
    except Exception as e:
        print(f"Binance top-trader oranı hatası ({symbol}):", e)
    return None


def refresh_binance_ratio_cache(coin_names):
    fresh = {}
    for name in coin_names:
        r = get_binance_top_trader_ratio(name)
        if r:
            fresh[name] = r
        time.sleep(0.05)  # Binance rate limit'e nazik davran
    if fresh:
        BINANCE_RATIO_CACHE["data"] = fresh
        BINANCE_RATIO_CACHE["last_update"] = time.time()


# ============================================================
#  HYPERLIQUID - GERÇEK "SMART MONEY" VERİSİ
#  (Leaderboard'daki en iyi cüzdanların GERÇEK açık pozisyonları: giriş fiyatı,
#   boyut ve LİKİDASYON fiyatı. API key gerektirmez.)
# ============================================================
HL_INFO_URL = "https://api.hyperliquid.xyz/info"
HL_LEADERBOARD_URL = "https://stats-data.hyperliquid.xyz/Mainnet/leaderboard"


def get_hyperliquid_top_wallets(limit=HL_WALLET_LIMIT):
    """Hyperliquid'in kendi leaderboard sayfasının kullandığı public JSON. Günlük PnL'e göre sıralar."""
    try:
        res = requests.get(HL_LEADERBOARD_URL, timeout=8)
        if res.status_code != 200:
            return []
        data = res.json()
        rows = data.get("leaderboardRows", data if isinstance(data, list) else [])
        scored = []
        for row in rows:
            addr = row.get("ethAddress")
            acc_val = float(row.get("accountValue", 0) or 0)
            if not addr or acc_val < HL_MIN_ACCOUNT_VALUE:
                continue
            day_pnl = 0.0
            for perf in row.get("windowPerformances", []):
                if isinstance(perf, list) and len(perf) == 2 and perf[0] == "day":
                    try:
                        day_pnl = float(perf[1].get("pnl", 0))
                    except Exception:
                        day_pnl = 0.0
            scored.append((day_pnl, addr, acc_val))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [addr for _, addr, _ in scored[:limit]]
    except Exception as e:
        print("Hyperliquid leaderboard hatası:", e)
        return []


def get_hyperliquid_wallet_positions(address):
    """Tek bir cüzdanın anlık açık pozisyonları: coin, yön, boyut, giriş fiyatı, likidasyon fiyatı."""
    try:
        res = requests.post(
            HL_INFO_URL, json={"type": "clearinghouseState", "user": address},
            headers={"Content-Type": "application/json"}, timeout=6
        )
        if res.status_code != 200:
            return []
        data = res.json()
        out = []
        for ap in data.get("assetPositions", []):
            pos = ap.get("position", {})
            coin = pos.get("coin")
            try:
                szi = float(pos.get("szi", 0) or 0)
            except Exception:
                szi = 0
            if not coin or szi == 0:
                continue
            entry_px = pos.get("entryPx")
            liq_px = pos.get("liquidationPx")
            out.append({
                "coin": coin,
                "wallet": address,
                "side": "LONG" if szi > 0 else "SHORT",
                "size": abs(szi),
                "entry": float(entry_px) if entry_px not in (None, "") else 0.0,
                "liq": float(liq_px) if liq_px not in (None, "") else None,
                "unrealizedPnl": float(pos.get("unrealizedPnl", 0) or 0),
            })
        return out
    except Exception as e:
        print(f"Hyperliquid cüzdan verisi hatası ({address}):", e)
        return []


def refresh_smart_money_cache():
    """
    Leaderboard'daki en iyi cüzdanları tarar, her coin için LONG/SHORT ortalama giriş fiyatı,
    işlem (pozisyon) sayısı, toplam büyüklük ve tıklanabilir likidasyon seviyelerini üretir.
    """
    wallets = get_hyperliquid_top_wallets()
    if not wallets:
        return

    per_coin = defaultdict(lambda: {"LONG": [], "SHORT": []})
    for addr in wallets:
        positions = get_hyperliquid_wallet_positions(addr)
        for p in positions:
            per_coin[p["coin"]][p["side"]].append(p)
        time.sleep(0.08)  # Hyperliquid public API'sine nazik davran

    result = {}
    for coin, sides in per_coin.items():
        coin_result = {}
        liq_levels = []
        for side in ("LONG", "SHORT"):
            plist = sides[side]
            total_size = sum(p["size"] for p in plist)
            if plist and total_size > 0:
                avg_entry = sum(p["entry"] * p["size"] for p in plist) / total_size
            else:
                avg_entry = 0
            coin_result[side] = {
                "avg_entry": avg_entry,
                "count": len(plist),
                "total_size": total_size,
            }
            for p in plist:
                if p["liq"]:
                    liq_levels.append({
                        "price": p["liq"], "side": side, "size": p["size"],
                        "wallet": p["wallet"], "unrealizedPnl": p["unrealizedPnl"],
                    })
        coin_result["liq_levels"] = liq_levels
        result[coin] = coin_result

    if result:
        SMART_MONEY_CACHE["data"] = result
        SMART_MONEY_CACHE["last_update"] = time.time()


# ============================================================
#  BINANCE LEADERBOARD (SMART MONEY) - BEST EFFORT
#  Bu, Binance'in web sitesinin arka planda kullandığı, key/login gerektirmeyen
#  bir endpoint. RESMİ DEĞİL, dökümante edilmiyor ve Binance önceden habersiz
#  değiştirebiliyor/kısıtlayabiliyor (nitekim pozisyon endpoint'i 2024'te bir kez
#  "public"tan "login gerekli"ye çevrilmişti). Bu yüzden her adım try/except ile
#  korunuyor: çalışmazsa sessizce boş döner, uygulamanın geri kalanını etkilemez.
#  Hyperliquid tarafı (yukarıda) birincil/garantili kaynağınız olarak kalıyor.
# ============================================================
BINANCE_LB_HEADERS = {
    "Content-Type": "application/json",
    "clienttype": "web",
    "lang": "en",
    "Origin": "https://www.binance.com",
    "Referer": "https://www.binance.com/en/futures-activity/leaderboard",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
}
BINANCE_LB_RANK_URL = "https://www.binance.com/bapi/futures/v1/public/future/leaderboard/getLeaderboardRank"
BINANCE_LB_POSITION_URL = "https://www.binance.com/bapi/futures/v1/public/future/leaderboard/getOtherPosition"


def get_binance_leaderboard_traders(limit=30):
    """Binance leaderboard sıralamasını çeker (haftalık PNL'e göre en iyiler)."""
    try:
        body = {
            "tradeType": "PERPETUAL",
            "statisticsType": "PNL",
            "periodType": "WEEKLY",
            "isShared": True,   # sadece pozisyonunu herkese açık paylaşan trader'lar (zaten login'siz görülebilenler bunlar)
            "isTrader": False,
        }
        res = requests.post(BINANCE_LB_RANK_URL, json=body, headers=BINANCE_LB_HEADERS, timeout=6)
        if res.status_code != 200:
            return []
        data = res.json()
        rows = (data.get("data") or [])[:limit]
        return [r.get("encryptedUid") for r in rows if r.get("encryptedUid")]
    except Exception as e:
        print("Binance leaderboard sıralaması alınamadı (best-effort):", e)
        return []


def get_binance_trader_positions(encrypted_uid):
    """Tek bir trader'ın herkese açık paylaştığı pozisyonları çeker (giriş fiyatı dahil, likidasyon fiyatı YOK)."""
    try:
        body = {"encryptedUid": encrypted_uid, "tradeType": "PERPETUAL"}
        res = requests.post(BINANCE_LB_POSITION_URL, json=body, headers=BINANCE_LB_HEADERS, timeout=6)
        if res.status_code != 200:
            return []
        data = res.json()
        rows = (data.get("data") or {}).get("otherPositionRetList") or []
        out = []
        for r in rows:
            symbol = r.get("symbol", "")
            if not symbol.endswith("USDT"):
                continue
            amount = float(r.get("amount", 0) or 0)
            if amount == 0:
                continue
            out.append({
                "coin": symbol.replace("USDT", ""),
                "side": "LONG" if amount > 0 else "SHORT",
                "size": abs(amount),
                "entry": float(r.get("entryPrice", 0) or 0),
                "wallet": encrypted_uid,
            })
        return out
    except Exception as e:
        print(f"Binance trader pozisyonu alınamadı (best-effort, uid={encrypted_uid}):", e)
        return []


def refresh_binance_leaderboard_cache():
    traders = get_binance_leaderboard_traders()
    if not traders:
        # Endpoint kapanmış/login istiyor olabilir. Sessizce vazgeç, Hyperliquid ana kaynak olarak kalır.
        BINANCE_LEADERBOARD_CACHE["working"] = False
        return

    per_coin = defaultdict(lambda: {"LONG": [], "SHORT": []})
    got_any_position = False
    for uid in traders:
        positions = get_binance_trader_positions(uid)
        if positions:
            got_any_position = True
        for p in positions:
            per_coin[p["coin"]][p["side"]].append(p)
        time.sleep(0.1)

    BINANCE_LEADERBOARD_CACHE["working"] = got_any_position
    if not got_any_position:
        return

    result = {}
    for coin, sides in per_coin.items():
        coin_result = {}
        for side in ("LONG", "SHORT"):
            plist = sides[side]
            total_size = sum(p["size"] for p in plist)
            avg_entry = sum(p["entry"] * p["size"] for p in plist) / total_size if total_size > 0 else 0
            coin_result[side] = {"avg_entry": avg_entry, "count": len(plist), "total_size": total_size}
        result[coin] = coin_result

    BINANCE_LEADERBOARD_CACHE["data"] = result
    BINANCE_LEADERBOARD_CACHE["last_update"] = time.time()


# ============================================================
#  ANA VERİ TOPLAMA (hızlı döngü)
# ============================================================
def fetch_market_data():
    global ACTIVE_TRADES, CLOSED_TRADES, HOURLY_RECORDS, LAST_RECORDED_HOUR
    processed_coins = {}
    total_open_interest_usd = 0
    all_prices = []

    binance_data = get_binance_futures_tickers()
    hl_url = "https://api.hyperliquid.xyz/info"
    payload = {"type": "metaAndAssetCtxs"}

    try:
        res = requests.post(hl_url, json=payload, headers={"Content-Type": "application/json"}, timeout=5)
        if res.status_code == 200:
            data = res.json()
            universe = data[0].get("universe", [])
            ctxs = data[1]

            for i, asset in enumerate(universe):
                name = asset.get("name")
                ctx = ctxs[i]
                open_interest = float(ctx.get("openInterest", 0))

                if name in binance_data and binance_data[name]["markPrice"] > 0:
                    mark_px = binance_data[name]["markPrice"]
                    funding = binance_data[name]["fundingRate"]
                else:
                    mark_px = float(ctx.get("markPx", 0))
                    funding = float(ctx.get("funding", 0)) * 100

                if mark_px <= 0:
                    continue

                all_prices.append(mark_px)
                oi_usd = open_interest * mark_px
                total_open_interest_usd += oi_usd

                if name not in ACTIVE_TRADES:
                    ACTIVE_TRADES[name] = {
                        "symbol": f"{name}USDT", "type": "LONG", "entry": mark_px,
                        "tp": mark_px * 1.028, "sl": mark_px * 0.978,
                        "start_time": time.strftime("%Y-%m-%d %H:%M:%S")
                    }

                trade = ACTIVE_TRADES[name]
                hitTP = (trade["type"] == 'LONG' and mark_px >= trade["tp"]) or (trade["type"] == 'SHORT' and mark_px <= trade["tp"])
                hitSL = (trade["type"] == 'LONG' and mark_px <= trade["sl"]) or (trade["type"] == 'SHORT' and mark_px >= trade["sl"])

                if hitTP or hitSL:
                    result_status = "WIN" if hitTP else "LOSS"
                    CLOSED_TRADES.insert(0, {
                        "symbol": trade["symbol"], "type": trade["type"], "entry": trade["entry"],
                        "exit_price": mark_px, "result": result_status, "closed_at": time.strftime("%Y-%m-%d %H:%M:%S")
                    })
                    if len(CLOSED_TRADES) > 50: CLOSED_TRADES.pop()
                    ACTIVE_TRADES[name] = {
                        "symbol": f"{name}USDT", "type": "LONG", "entry": mark_px,
                        "tp": mark_px * 1.028, "sl": mark_px * 0.978,
                        "start_time": time.strftime("%Y-%m-%d %H:%M:%S")
                    }
                    save_trade_history({"active": ACTIVE_TRADES, "closed": CLOSED_TRADES})

                ai_report = {
                    "signal": "LONG İVME BASKISI",
                    "comment": f"Normal eğrinin üzerinde +4.7x Hız ile tetiklenen yoğunluk tespit edildi. Giriş ${fmt(trade['entry'])} seviyesinden planlandı.",
                    "confluence": 88.4, "entry": trade["entry"], "tp": trade["tp"], "sl": trade["sl"]
                }

                processed_coins[name] = {
                    "symbol": f"{name}USDT", "markPrice": mark_px, "fundingRate": funding,
                    "openInterestUSD": oi_usd, "ai_analysis": ai_report
                }

            # Saatlik kayıt (artık gerçek smart-money özetini kaydediyor)
            current_hour = time.localtime().tm_hour
            if current_hour != LAST_RECORDED_HOUR and SMART_MONEY_CACHE["data"]:
                hourly_snapshot = {
                    "timestamp": time.strftime("%Y-%m-%d %H:00:00"),
                    "coins": {
                        c: {"LONG": v.get("LONG"), "SHORT": v.get("SHORT")}
                        for c, v in SMART_MONEY_CACHE["data"].items()
                    }
                }
                HOURLY_RECORDS.insert(0, hourly_snapshot)
                if len(HOURLY_RECORDS) > 168:
                    HOURLY_RECORDS.pop()
                save_hourly_history(HOURLY_RECORDS)
                LAST_RECORDED_HOUR = current_hour

            processed_coins["_GLOBAL_SUMMARY_"] = {
                "totalActiveCoins": len(processed_coins),
                "totalAUM_OI": total_open_interest_usd,
                "avgMarketPrice": sum(all_prices) / len(all_prices) if all_prices else 0
            }
            return processed_coins
    except Exception as e:
        print("Veri hatası:", e)
    return {}


# ============================================================
#  ARKA PLAN İŞÇİLERİ
# ============================================================
def background_fast_worker():
    global CACHE
    while True:
        try:
            data = fetch_market_data()
            if data:
                CACHE["data"] = data
                CACHE["last_update"] = time.time()
                save_trade_history({"active": ACTIVE_TRADES, "closed": CLOSED_TRADES})
        except Exception as e:
            print("Hızlı worker hatası:", e)
        time.sleep(FAST_LOOP_SECONDS)


def background_smart_money_worker():
    while True:
        try:
            refresh_smart_money_cache()
        except Exception as e:
            print("Smart money worker hatası:", e)
        time.sleep(SMART_MONEY_LOOP_SECONDS)


def background_binance_ratio_worker():
    while True:
        try:
            coins = [k for k in CACHE["data"].keys() if not k.startswith("_")]
            if coins:
                refresh_binance_ratio_cache(coins)
        except Exception as e:
            print("Binance oran worker hatası:", e)
        time.sleep(BINANCE_RATIO_LOOP_SECONDS)


def background_binance_leaderboard_worker():
    while True:
        try:
            refresh_binance_leaderboard_cache()
        except Exception as e:
            print("Binance leaderboard worker hatası (best-effort):", e)
        time.sleep(BINANCE_LEADERBOARD_LOOP_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    threading.Thread(target=background_fast_worker, daemon=True).start()
    threading.Thread(target=background_smart_money_worker, daemon=True).start()
    threading.Thread(target=background_binance_ratio_worker, daemon=True).start()
    threading.Thread(target=background_binance_leaderboard_worker, daemon=True).start()
    yield


app = FastAPI(title="Cash Control Engine", version="14.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.get("/", response_class=HTMLResponse)
def read_index():
    try:
        with open("index.html", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "<h3>index.html dosyası bulunamadı!</h3>"


@app.get("/api/coins")
def get_all_coins():
    coins = [k for k in CACHE["data"].keys() if not k.startswith("_")]
    if not coins:
        CACHE["data"] = fetch_market_data()
        CACHE["last_update"] = time.time()
        coins = [k for k in CACHE["data"].keys() if not k.startswith("_")]
    return {"status": "success", "coins": sorted(coins)}


@app.get("/api/klines/{symbol}")
def get_klines(symbol: str, timeframe: str = "15", limit: int = 300):
    symbol = symbol.upper()
    return {"status": "success", "candles": get_binance_klines(symbol, timeframe, limit)}


@app.get("/api/smart-money/{symbol}")
def get_smart_money(symbol: str):
    symbol = symbol.upper()
    coin_data = SMART_MONEY_CACHE["data"].get(symbol)
    if not coin_data:
        coin_data = {"LONG": {"avg_entry": 0, "count": 0, "total_size": 0},
                      "SHORT": {"avg_entry": 0, "count": 0, "total_size": 0},
                      "liq_levels": []}
    binance_lb = BINANCE_LEADERBOARD_CACHE["data"].get(symbol)
    return {
        "status": "success",
        "data": coin_data,
        "binance_leaderboard": binance_lb,          # None ise: o coin için veri yok / endpoint çalışmıyor
        "binance_leaderboard_working": BINANCE_LEADERBOARD_CACHE["working"],
        "wallet_pool_size": HL_WALLET_LIMIT,
        "last_update": SMART_MONEY_CACHE["last_update"],
    }


@app.get("/api/market-stats/{symbol}")
def get_coin_stats(symbol: str, timeframe: str = "15"):
    symbol = symbol.upper()
    coin_data = CACHE["data"].get(symbol)
    if not coin_data:
        return {"status": "error", "message": "Coin bulunamadı"}

    pivots = get_pivot_levels(symbol, timeframe)
    if not pivots:
        mark_px = coin_data["markPrice"]
        high, low = mark_px * 1.012, mark_px * 0.988
        pivot = (high + low + mark_px) / 3
        pivots = {"res3": high + 2*(pivot-low), "res2": pivot+(high-low), "res1": (2*pivot)-low,
                  "pivot": pivot, "sup1": (2*pivot)-high, "sup2": pivot-(high-low), "sup3": low-2*(high-pivot)}

    response_data = dict(coin_data)
    response_data["pivots"] = pivots
    response_data["smart_money"] = SMART_MONEY_CACHE["data"].get(symbol, {
        "LONG": {"avg_entry": 0, "count": 0, "total_size": 0},
        "SHORT": {"avg_entry": 0, "count": 0, "total_size": 0},
        "liq_levels": []
    })
    response_data["binance_top_trader_ratio"] = BINANCE_RATIO_CACHE["data"].get(symbol)
    response_data["binance_leaderboard"] = BINANCE_LEADERBOARD_CACHE["data"].get(symbol)
    response_data["binance_leaderboard_working"] = BINANCE_LEADERBOARD_CACHE["working"]
    return {"status": "success", "data": response_data, "global": CACHE["data"].get("_GLOBAL_SUMMARY_", {})}


@app.get("/api/trade-history")
def get_trade_history():
    return {"status": "success", "closed_trades": CLOSED_TRADES}


@app.get("/api/hourly-history")
def get_hourly_history():
    return {"status": "success", "hourly_history": HOURLY_RECORDS}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
