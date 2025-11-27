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


# ============================================================
#               LOGIC SMC AGGRESSIVE SCALPING (5m)
# ============================================================

def detect_bias_5m(df_5m: pd.DataFrame) -> bool:
    """
    Bias agresif 5m:
    - close > EMA20 > EMA50 (trend mikro naik)
    """
    close = df_5m["close"]
    ema20 = ema(close, 20)
    ema50 = ema(close, 50)

    last = close.iloc[-1]
    e20 = ema20.iloc[-1]
    e50 = ema50.iloc[-1]

    return bool(last > e20 > e50)


def detect_micro_choch(df_5m: pd.DataFrame):
    """
    Micro CHoCH:
    - high & low terakhir lebih tinggi dari swing kecil sebelumnya.
    Premium:
    - candle terakhir bullish
    - body > 1.3x rata-rata body
    - upper wick <= 25% dari total range
    """
    highs = df_5m["high"].values
    lows = df_5m["low"].values
    opens = df_5m["open"].values
    closes = df_5m["close"].values

    n = len(highs)
    if n < 10:
        return False, False

    # CHoCH dasar
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
    """
    highs = df_5m["high"].values
    lows = df_5m["low"].values

    n = len(highs)
    if n < 4:
        return False, 0.0, 0.0

    # cek di 4 candle terakhir
    start = max(0, n - 6)
    for i in range(start, n - 1):
        if lows[i + 1] > highs[i]:
            fvg_low = highs[i]
            fvg_high = lows[i + 1]
            return True, float(fvg_low), float(fvg_high)

    return False, 0.0, 0.0


def detect_momentum(df_5m: pd.DataFrame):
    """
    Momentum:
    - OK: RSI 45–75
    - Premium: RSI 50–68 (sweet spot tren sehat)
    """
    closes = df_5m["close"]
    if len(closes) < 30:
        return True, False

    rsi_val = rsi(closes, 14).iloc[-1]

    momentum_ok = bool(45 < rsi_val < 75)
    momentum_premium = bool(50 < rsi_val < 68)

    return momentum_ok, momentum_premium


def detect_not_choppy(df_5m: pd.DataFrame, window: int = 20) -> bool:
    """
    Filter choppy ringan:
    - range total > 1.5x rata-rata range candle.
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

    return bool(full_range > avg_range * 1.5)


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
    TP:
    - kelipatan jarak entry–SL (scalping RR 1:1.2 / 1:2 / 1:3)
    """
    closes = df_5m["close"].values
    lows = df_5m["low"].values

    last_close = closes[-1]

    if fvg_low and fvg_high and fvg_high > fvg_low:
        entry = (fvg_low + fvg_high) / 2.0
    else:
        entry = last_close

    recent_low = lows[-5:].min()
    buffer = abs(last_close) * 0.002  # ~0.2%
    sl = recent_low - buffer

    risk = abs(entry - sl)
    if risk <= 0:
        risk = abs(entry) * 0.003  # fallback kecil

    tp1 = entry + risk * 1.2
    tp2 = entry + risk * 2.0
    tp3 = entry + risk * 3.0

    return {
        "entry": float(entry),
        "sl": float(sl),
        "tp1": float(tp1),
        "tp2": float(tp2),
        "tp3": float(tp3),
    }


# ============================================================
#                    ANALYZE SYMBOL (AGGRESSIVE)
# ============================================================

def analyse_symbol(symbol: str):
    """
    Versi SMC Aggressive Scalping (LONG only):
    - Timeframe utama: 5m
    - Bias: close > EMA20 > EMA50
    - Trigger: micro CHoCH (premium = body kuat & wick bersih)
    - Confluence: micro FVG (jika ada)
    - Filter: momentum + tidak terlalu choppy
    """
    try:
        df_5m = get_klines(symbol, "5m", 220)
    except Exception as e:
        print(f"[{symbol}] ERROR fetching data:", e)
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

    conditions = {
        "bias_ok": bias_ok,
        "micro_choch": micro_choch,
        "micro_choch_premium": micro_choch_premium,
        "micro_fvg": micro_fvg,
        "momentum_ok": momentum_ok,
        "momentum_premium": momentum_premium,
        "not_choppy": not_choppy,
    }

    levels = build_entry_sl_tp_aggressive(df_5m, fvg_low, fvg_high)

    return conditions, levels
