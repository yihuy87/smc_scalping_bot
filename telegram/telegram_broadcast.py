# telegram/telegram_broadcast.py
# broadcast_signal + build_signal_message

import time

from config import TELEGRAM_ADMIN_ID
from core.bot_state import state, is_vip, cleanup_expired_vip
from telegram.telegram_common import send_telegram


def broadcast_signal(text: str):
    """Kirim sinyal:
    - SELALU ke admin (unlimited)
    - Juga ke semua subscribers (FREE:max 2 sinyal per hari / VIP: unlimited)
    """
    today = time.strftime("%Y-%m-%d")
    if state.daily_date != today:
        state.daily_date = today
        state.daily_counts = {}
        cleanup_expired_vip()
        print("Reset daily_counts & cleanup VIP untuk hari baru:", today)

    # admin
    if TELEGRAM_ADMIN_ID:
        try:
            send_telegram(text, chat_id=int(TELEGRAM_ADMIN_ID))
        except Exception as e:
            print("Gagal kirim ke admin:", e)
    else:
        print("⚠️ TELEGRAM_ADMIN_ID belum di-set. Admin tidak menerima sinyal.")

    # user
    if not state.subscribers:
        print("Belum ada subscriber. Hanya admin yang menerima sinyal.")
        return

    for cid in list(state.subscribers):
        if TELEGRAM_ADMIN_ID and str(cid) == str(TELEGRAM_ADMIN_ID):
            continue

        if is_vip(cid):
            send_telegram(text, chat_id=cid)
            continue

        count = state.daily_counts.get(cid, 0)
        if count >= 2:
            continue

        send_telegram(text, chat_id=cid)
        state.daily_counts[cid] = count + 1


def build_signal_message(
    symbol: str,
    levels: dict,
    conditions: dict,
    score: int,
    tier: str,
    side: str = "long"
) -> str:
    entry = levels["entry"]
    sl = levels["sl"]
    tp1 = levels["tp1"]
    tp2 = levels["tp2"]
    tp3 = levels["tp3"]

    # risk dari SL–entry (untuk hitung toleransi validasi)
    risk = abs(entry - sl)
    
    tol_up = entry + (0.30 * risk) # agresif tapi cukup ketat
    tol_down = entry - (0.15 * risk)

    def mark(flag: bool) -> str:
        return "✅" if flag else "❌"

    side_label = "LONG" if side == "long" else "SHORT"

    bias_ok             = conditions.get("bias_ok")
    htf_15m_trend_ok    = conditions.get("htf_15m_trend_ok")
    htf_1h_trend_ok     = conditions.get("htf_1h_trend_ok")
    micro_choch         = conditions.get("micro_choch")
    micro_choch_premium = conditions.get("micro_choch_premium")
    micro_fvg           = conditions.get("micro_fvg")
    momentum_ok         = conditions.get("momentum_ok")
    momentum_premium    = conditions.get("momentum_premium")
    not_choppy          = conditions.get("not_choppy")
    not_overextended    = conditions.get("not_overextended")
    setup_score         = conditions.get("setup_score", 0)

    text = f"""🟦 SMC AGGRESSIVE SCALPING — {symbol}

Score: {score}/150 — Tier {tier} — {side_label}
Setup internal (5m): {setup_score}/3

💰 Harga

• Entry : `{entry:.6f}`

• SL    : `{sl:.6f}`

• TP1   : `{tp1:.6f}`

• TP2   : `{tp2:.6f}`

• TP3   : `{tp3:.6f}`

📌 VALIDATION RULES (penting)

Harga dianggap *VALID* untuk entry jika:
• Harga TIDAK naik lebih dari `entry + 0.30 × risk`
  → Batas atas ≈ `{tol_up:.6f}`

• Harga TIDAK turun lebih dari `entry - 0.15 × risk`
  → Batas bawah ≈ `{tol_down:.6f}`

Jika harga:
• Naik di atas batas atas → *entry batal* (lewat/FOMO, jangan kejar)
• Turun di bawah batas bawah → *entry batal* (retracement terlalu dalam, momentum lemah)

📌 Checklist Multi-Timeframe

• Bias 5m (Close > EMA20 > EMA50 & naik)  : {mark(bias_ok)}
• Bias 15m searah                         : {mark(htf_15m_trend_ok)}
• Bias 1H searah                          : {mark(htf_1h_trend_ok)}

📌 Checklist Aggressive Scalping (5m)

• Micro CHoCH (trigger)                   : {mark(micro_choch)}
• Micro CHoCH premium candle              : {mark(micro_choch_premium)}
• Micro FVG (imbalance)                   : {mark(micro_fvg)}
• Momentum OK (RSI ≥ 50)                  : {mark(momentum_ok)}
• Momentum premium (RSI 52–65)            : {mark(momentum_premium)}
• Market tidak choppy (ATR & range)       : {mark(not_choppy)}
• Tidak over-extended dari EMA            : {mark(not_overextended)}

📝 Catatan

Strategi:
• Entry di 5m, tetapi wajib searah 15m dan 1H.
• Momentum minimal RSI 50 untuk long (hindari market lemah).
• Micro CHoCH premium: body kuat, wick bersih → mengurangi fake breakout.
• Filter tambahan: ATR & range untuk hindari market choppy/ terlalu tenang.
• Hindari entry di pucuk (over-extended dari EMA).
• Validation rules mencegah FOMO & deep retrace yang merusak R:R.
• Tier A+ diset ketat — hanya muncul saat confluence multi-timeframe & momentum kuat.

Free: maksimal 2 sinyal/hari. VIP: Unlimited sinyal.
"""
    return text
