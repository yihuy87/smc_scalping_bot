# smc_logic.py
# =========================
# SMC AGGRESSIVE SCALPING (PREMIUM)
# =========================

import requests
import pandas as pd
import numpy as np
from config import BINANCE_REST_URL


# ================== DATA FETCHING & UTIL ==================

def get_klines(symbol: str, interval: str, limit: int = 200) -> pd.DataFrame:
    """Ambil data candlestick Binance (REST)."""
    url = f"{BINANCE_REST_URL}/api/v3/klines"
    params = {"symbol": symbol.upper(), "interval": interval, "limit": limit}

    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    data = r.json()

    cols = [
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_asset_volume", "number_of_trades",
        "taker_buy_base", "taker_buy_quote", "ignore"
    ]
    df = pd.DataFrame(data, columns=cols)

    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = df[c].astype(float)

    return df


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """RSI sederhana."""
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / (loss + 1e-9)
    rsi_val = 100 - (100 / (1 + rs))
    return rsi_val


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Average True Range (ATR) untuk volatilitas.
    Dipakai untuk buffer SL supaya lebih adaptif dengan market.
    """
    high = df["high"]
    low = df["low"]
    close = df["close"]

    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()

    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(window=period, min_periods=1).mean()


# ============================================================
#               LOGIC SMC AGGRESSIVE SCALPING (5m)
# ============================================================

def detect_bias_5m(df_5m: pd.DataFrame) -> bool:
    """
    Bias agresif 5m:
    - close > EMA20 > EMA50 (trend mikro naik)
    - tambahan: EMA20 & EMA50 tidak jelas-jelas downtrend (cek slope)
    """
    close = df_5m["close"]
    ema20 = ema(close, 20)
    ema50 = ema(close, 50)

    last = close.iloc[-1]
    e20 = ema20.iloc[-1]
    e50 = ema50.iloc[-1]

    # syarat utama
    bias_stack = last > e20 > e50

    # sedikit filter: ema jangan jelas-jelas downtrend tajam
    if len(ema20) > 5 and len(ema50) > 5:
        e20_prev = ema20.iloc[-5]
        e50_prev = ema50.iloc[-5]
        ema_slope_ok = (e20 >= e20_prev) and (e50 >= e50_prev)
    else:
        ema_slope_ok = True  # kalau data pendek, jangan terlalu strict

    return bool(bias_stack and ema_slope_ok)


def detect_micro_choch(df_5m: pd.DataFrame):
    """
    Micro CHoCH:
    - high & low terakhir lebih tinggi dari swing kecil sebelumnya.
    Premium:
    - candle terakhir bullish
    - body > 1.3x rata-rata body 8 candle sebelumnya
    - upper wick <= 25% dari total range
    """
    highs = df_5m["high"].values
    lows = df_5m["low"].values
    opens = df_5m["open"].values
    closes = df_5m["close"].values

    n = len(highs)
    if n < 10:
        return False, False

    # CHoCH dasar (pakai n-1 vs n-3 supaya "micro swing" sedikit lebih valid)
    micro_choch = bool(highs[-1] > highs[-3] and lows[-1] > lows[-3])

    # Premium detail
    last_open = opens[-1]
    last_close = closes[-1]
    last_high = highs[-1]
    last_low = lows[-1]

    # Harus bullish
    if last_close <= last_open:
        return micro_choch, False

    body = abs(last_close - last_open)
    past_bodies = np.abs(closes[-9:-1] - opens[-9:-1])
    avg_body = past_bodies.mean() if past_bodies.size > 0 else 0.0

    total_range = last_high - last_low
    if total_range <= 0 or avg_body <= 0:
        return micro_choch, False

    upper_wick = last_high - max(last_close, last_open)

    body_big_enough = body >= avg_body * 1.3
    wick_small_enough = (upper_wick / total_range) <= 0.25

    micro_choch_premium = bool(
        micro_choch and body_big_enough and wick_small_enough
    )

    return micro_choch, micro_choch_premium


def detect_micro_fvg(df_5m: pd.DataFrame):
    """
    Micro FVG bullish (imbalance kecil):
    - low candle n > high candle n-1 di beberapa candle terakhir.
    Di-upgrade:
    - scan beberapa candle dan ambil FVG yang paling dekat dengan harga sekarang.
    """
    highs = df_5m["high"].values
    lows = df_5m["low"].values
    closes = df_5m["close"].values

    n = len(highs)
    if n < 4:
        return False, 0.0, 0.0

    last_close = closes[-1]
    start = max(0, n - 12)  # scan lebih lebar tapi tetap "micro"
    best_diff = None
    best_low = 0.0
    best_high = 0.0

    for i in range(start, n - 1):
        # bullish FVG (imbalance ke atas)
        if lows[i + 1] > highs[i]:
            fvg_low = highs[i]
            fvg_high = lows[i + 1]

            # cari FVG yang paling dekat dengan harga sekarang
            mid = (fvg_low + fvg_high) / 2.0
            diff = abs(last_close - mid)
            if (best_diff is None) or (diff < best_diff):
                best_diff = diff
                best_low = fvg_low
                best_high = fvg_high

    if best_diff is None:
        return False, 0.0, 0.0

    return True, float(best_low), float(best_high)


def detect_momentum(df_5m: pd.DataFrame):
    """
    Momentum:
    - OK: RSI 45–75
    - Premium: RSI 50–68 (sweet spot tren sehat)
    """
    closes = df_5m["close"]
    if len(closes) < 30:
        # kalau data pendek, jangan terlalu ketat
        return True, False

    rsi_val = rsi(closes, 14).iloc[-1]

    momentum_ok = bool(45 < rsi_val < 75)
    momentum_premium = bool(50 < rsi_val < 68)

    return momentum_ok, momentum_premium


def detect_not_choppy(df_5m: pd.DataFrame, window: int = 20) -> bool:
    """
    Filter choppy:
    - range total > 1.5x rata-rata range candle.
    - kalau candle terlalu kecil semua (super pelan), dianggap choppy.
    """
    highs = df_5m["high"].values
    lows = df_5m["low"].values

    if len(highs) < window + 2:
        return True

    seg_high = highs[-window:]
    seg_low = lows[-window:]

    ranges = seg_high - seg_low
    full_range = seg_high.max() - seg_low.min()
    avg_range = ranges.mean()

    if avg_range <= 0:
        return False

    # kondisi utama
    trendiness_ok = full_range > avg_range * 1.5

    # kalau rata-rata range sangat kecil -> market lagi super pelan / choppy
    tiny_range = avg_range <= (seg_low.mean() * 0.001)  # ~0.1%
    if tiny_range:
        return False

    return bool(trendiness_ok)


# ============================================================
#                  ENTRY / SL / TP GENERATION
# ============================================================

def build_entry_sl_tp_aggressive(df_5m: pd.DataFrame,
                                 fvg_low: float,
                                 fvg_high: float) -> dict:
    """
    Entry:
    - kalau ada micro FVG → pakai mid FVG
    - kalau tidak → pakai close terakhir
    SL:
    - sedikit di bawah swing low pendek
    - ada buffer berbasis ATR (bukan hanya % fixed)
    TP:
    - kelipatan jarak entry–SL (scalping RR 1:1.2 / 1:2 / 1:3)
    """
    closes = df_5m["close"].values
    lows = df_5m["low"].values

    last_close = closes[-1]

    # Entry di mid FVG kalau tersedia
    if fvg_low and fvg_high and fvg_high > fvg_low:
        entry = (fvg_low + fvg_high) / 2.0
    else:
        entry = last_close

    # Swing low pendek sebagai acuan SL
    recent_low = lows[-5:].min()

    # ATR sebagai buffer utama
    atr_series = atr(df_5m, period=14)
    atr_val = float(atr_series.iloc[-1]) if not np.isnan(atr_series.iloc[-1]) else 0.0

    # Kalau ATR valid, pakai ATR; kalau tidak, fallback ke persentase
    if atr_val > 0:
        buffer = atr_val * 0.3  # 30% ATR buffer
    else:
        buffer = abs(last_close) * 0.002  # ~0.2% fallback

    sl = recent_low - buffer

    risk = abs(entry - sl)
    if risk <= 0:
        risk = max(abs(entry) * 0.003, 1e-8)  # fallback kecil tapi non-zero

    tp1 = entry + risk * 1.2
    tp2 = entry + risk * 2.0
    tp3 = entry + risk * 3.0

    return {
        "entry": float(entry),
        "sl": float(sl),
        "tp1": float(tp1),
        "tp2": float(tp2),
        "tp3": float(tp3),
        "risk_per_unit": float(risk),
    }


# ============================================================
#                    ANALYZE SYMBOL (AGGRESSIVE)
# ============================================================

def analyse_symbol(symbol: str):
    """
    Versi SMC Aggressive Scalping (LONG only):
    - Timeframe utama: 5m
    - Bias: close > EMA20 > EMA50 (+ ema tidak clearly downtrend)
    - Trigger: micro CHoCH (premium = body kuat & wick bersih)
    - Confluence: micro FVG (jika ada)
    - Filter: momentum + tidak terlalu choppy

    Return:
    - None, None  → tidak ada setup
    - conditions, levels → setup valid
    """
    try:
        df_5m = get_klines(symbol, "5m", 220)
    except Exception as e:
        print(f"[{symbol}] ERROR fetching data:", e)
        return None, None

    if df_5m is None or df_5m.empty:
        print(f"[{symbol}] Empty dataframe from get_klines")
        return None, None

    bias_ok = detect_bias_5m(df_5m)
    micro_choch, micro_choch_premium = detect_micro_choch(df_5m)
    micro_fvg, fvg_low, fvg_high = detect_micro_fvg(df_5m)
    momentum_ok, momentum_premium = detect_momentum(df_5m)
    not_choppy = detect_not_choppy(df_5m)

    # Syarat inti agresif:
    # - Wajib bias 5m OK
    # - Wajib momentum OK
    # - Wajib micro CHoCH (trigger)
    # - Market tidak terlalu choppy
    if not (bias_ok and momentum_ok and micro_choch and not_choppy):
        return None, None

    # simple scoring untuk kualitas setup internal (0–3)
    setup_score = 0
    if micro_choch_premium:
        setup_score += 1
    if micro_fvg:
        setup_score += 1
    if momentum_premium:
        setup_score += 1

    conditions = {
        "symbol": symbol.upper(),
        "timeframe": "5m",
        "bias_ok": bias_ok,
        "micro_choch": micro_choch,
        "micro_choch_premium": micro_choch_premium,
        "micro_fvg": micro_fvg,
        "momentum_ok": momentum_ok,
        "momentum_premium": momentum_premium,
        "not_choppy": not_choppy,
        "setup_score": setup_score,  # 0–3
    }

    levels = build_entry_sl_tp_aggressive(df_5m, fvg_low, fvg_high)

    return conditions, levels
