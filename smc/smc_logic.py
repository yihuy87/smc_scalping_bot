# smc/smc_logic.py
# =========================
# SMC AGGRESSIVE SCALPING (PREMIUM)
# =========================

import requests
import pandas as pd
import numpy as np
from config import BINANCE_REST_URL


# ================== DATA FETCHING & UTIL ==================

def get_klines(symbol: str, interval: str, limit: int = 200) -> pd.DataFrame:
    """Ambil data candlestick Binance Futures (REST)."""
    url = f"{BINANCE_REST_URL}/fapi/v1/klines"
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
    Dipakai untuk buffer SL & filter choppy.
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
#               LOGIC SMC AGGRESSIVE SCALPING
# ============================================================

def detect_bias_generic(df: pd.DataFrame) -> bool:
    """
    Bias generik:
    - close > EMA20 > EMA50
    - EMA20 & EMA50 benar-benar naik (cek slope 5 candle ke belakang).
    Bisa dipakai untuk 5m, 15m, 1H.
    """
    close = df["close"]
    ema20 = ema(close, 20)
    ema50 = ema(close, 50)

    last = close.iloc[-1]
    e20 = ema20.iloc[-1]
    e50 = ema50.iloc[-1]

    bias_stack = last > e20 > e50

    if len(ema20) > 5 and len(ema50) > 5:
        e20_prev = ema20.iloc[-5]
        e50_prev = ema50.iloc[-5]

        base20 = max(abs(e20_prev), 1e-9)
        base50 = max(abs(e50_prev), 1e-9)
        slope20 = (e20 - e20_prev) / base20
        slope50 = (e50 - e50_prev) / base50

        # butuh slope naik, bukan flat
        ema_slope_ok = (slope20 > 0.001) and (slope50 > 0.0005)
    else:
        ema_slope_ok = True

    return bool(bias_stack and ema_slope_ok)


def detect_bias_5m(df_5m: pd.DataFrame) -> bool:
    """Alias khusus 5m, pakai rule generik."""
    return detect_bias_generic(df_5m)


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

    # swing kecil: bandingkan ke 2 candle sebelumnya
    micro_choch = bool(highs[-1] > highs[-3] and lows[-1] > lows[-3])

    last_open = opens[-1]
    last_close = closes[-1]
    last_high = highs[-1]
    last_low = lows[-1]

    # harus bullish
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
    - ambil FVG yang paling dekat dengan harga sekarang.
    """
    highs = df_5m["high"].values
    lows = df_5m["low"].values
    closes = df_5m["close"].values

    n = len(highs)
    if n < 4:
        return False, 0.0, 0.0

    last_close = closes[-1]
    start = max(0, n - 12)
    best_diff = None
    best_low = 0.0
    best_high = 0.0

    for i in range(start, n - 1):
        if lows[i + 1] > highs[i]:
            fvg_low = highs[i]
            fvg_high = lows[i + 1]

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
    Momentum (LONG):
    - OK: RSI 50–72 (RSI < 50 → skip, market lemah)
    - Premium: RSI 52–65 (sweet spot tren sehat)
    """
    closes = df_5m["close"]
    if len(closes) < 30:
        return True, False

    rsi_val = rsi(closes, 14).iloc[-1]

    momentum_ok = bool(50 <= rsi_val < 72)
    momentum_premium = bool(52 <= rsi_val <= 65)

    return momentum_ok, momentum_premium


def detect_not_choppy(df_5m: pd.DataFrame, window: int = 20) -> bool:
    """
    Filter choppy agresif tapi ketat:
    - range total > 1.8x rata-rata range candle.
    - ATR relatif terhadap harga tidak terlalu kecil (market tidak 'tidur').
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

    trendiness_ok = full_range > avg_range * 1.8

    # ATR check
    atr_series = atr(df_5m, period=14)
    atr_val = float(atr_series.iloc[-1]) if not np.isnan(atr_series.iloc[-1]) else 0.0
    last_price = float(df_5m["close"].iloc[-1])

    if last_price > 0:
        atr_pct = atr_val / last_price
    else:
        atr_pct = 0.0

    # kalau ATR < 0.4% harga → dianggap terlalu kalem/choppy
    if atr_pct < 0.004:
        return False

    return bool(trendiness_ok)


def detect_not_overextended(df_5m: pd.DataFrame,
                            ema_period: int = 20,
                            max_distance_pct: float = 0.012) -> bool:
    """
    TRUE kalau harga TIDAK terlalu jauh dari EMA (tidak over-extended).
    Untuk long:
    - close tidak lebih dari max_distance_pct di atas EMA20.
    (lebih ketat: default 1.2%)
    """
    close = df_5m["close"]
    ema20 = ema(close, ema_period)

    last_close = close.iloc[-1]
    last_ema = ema20.iloc[-1]

    if last_ema <= 0:
        return True

    dist_pct = (last_close - last_ema) / last_ema
    if dist_pct > max_distance_pct:
        return False

    return True


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

    if fvg_low and fvg_high and fvg_high > fvg_low:
        raw_entry = (fvg_low + fvg_high) / 2.0
    else:
        raw_entry = last_close

    # Untuk long, kita mau buy on dip, bukan ngejar di atas harga sekarang.
    entry = min(raw_entry, last_close)

    recent_low = lows[-5:].min()

    atr_series = atr(df_5m, period=14)
    atr_val = float(atr_series.iloc[-1]) if not np.isnan(atr_series.iloc[-1]) else 0.0

    if atr_val > 0:
        buffer = atr_val * 0.3
    else:
        buffer = abs(last_close) * 0.002

    sl = recent_low - buffer

    risk = abs(entry - sl)
    if risk <= 0:
        risk = max(abs(entry) * 0.003, 1e-8)

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
    Versi SMC Aggressive Scalping (LONG only, FUTURES):
    - Timeframe entry: 5m
    - Konfirmasi trend: 15m (WAJIB)
    - Trend besar: 1H (WAJIB)
    - Bias 5m: close > EMA20 > EMA50 + EMA benar-benar naik
    - Trigger: micro CHoCH *PREMIUM WAJIB* (candle impuls kuat)
    - Confluence: micro FVG (jika ada)
    - Filter: momentum (RSI >= 50), tidak terlalu choppy, tidak overextended
    """
    try:
        df_5m = get_klines(symbol, "5m", 220)
        df_15m = get_klines(symbol, "15m", 220)
        df_1h = get_klines(symbol, "1h", 220)
    except Exception as e:
        print(f"[{symbol}] ERROR fetching data:", e)
        return None, None

    if any(df is None or df.empty for df in (df_5m, df_15m, df_1h)):
        print(f"[{symbol}] Empty dataframe on one of TF (5m/15m/1h)")
        return None, None

    bias_5m = detect_bias_5m(df_5m)
    bias_15m = detect_bias_generic(df_15m)
    bias_1h = detect_bias_generic(df_1h)

    micro_choch, micro_choch_premium = detect_micro_choch(df_5m)
    micro_fvg, fvg_low, fvg_high = detect_micro_fvg(df_5m)
    momentum_ok, momentum_premium = detect_momentum(df_5m)
    not_choppy = detect_not_choppy(df_5m)
    not_overextended = detect_not_overextended(df_5m)

    # Syarat inti agresif (lebih ketat):
    # - Bias 5m, 15m, 1H wajib OK
    # - Momentum OK (RSI >= 50)
    # - Micro CHoCH *PREMIUM WAJIB*
    # - Market tidak choppy
    # - Tidak over-extended
    if not (
        bias_5m
        and bias_15m
        and bias_1h
        and momentum_ok
        and micro_choch
        and micro_choch_premium
        and not_choppy
        and not_overextended
    ):
        return None, None

    htf_15m_trend_ok = bias_15m
    htf_1h_trend_ok = bias_1h

    last_high = df_5m["high"].iloc[-1]
    last_low = df_5m["low"].iloc[-1]
    last_range = last_high - last_low

    levels = build_entry_sl_tp_aggressive(df_5m, fvg_low, fvg_high)
    entry = levels["entry"]

    # Anti entry di pucuk: kalau entry terlalu dekat high candle terakhir, skip
    if last_range > 0 and (last_high - entry) < (0.3 * last_range):
        return None, None

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
        "bias_ok": bias_5m,
        "htf_15m_trend_ok": htf_15m_trend_ok,
        "htf_1h_trend_ok": htf_1h_trend_ok,
        "micro_choch": micro_choch,
        "micro_choch_premium": micro_choch_premium,
        "micro_fvg": micro_fvg,
        "momentum_ok": momentum_ok,
        "momentum_premium": momentum_premium,
        "not_choppy": not_choppy,
        "not_overextended": not_overextended,
        "setup_score": setup_score,  # 0–3
    }

    return conditions, levels
