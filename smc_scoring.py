# smc_scoring.py
# =========================
# SMC AGGRESSIVE SCALPING SCORING (PREMIUM)
# =========================

from typing import Dict


def score_smc_signal(c: Dict) -> int:
    """
    Scoring untuk setup Aggressive Scalping (0–125).
    A+ di-design lebih jarang.

    Terintegrasi dengan logic baru:
    - Memanfaatkan c["setup_score"] (0–3) dari analyse_symbol
      sebagai bagian dari synergy bonus.
    """
    score = 0

    bias_ok = bool(c.get("bias_ok"))
    micro_choch = bool(c.get("micro_choch"))
    micro_choch_premium = bool(c.get("micro_choch_premium"))
    micro_fvg = bool(c.get("micro_fvg"))
    momentum_ok = bool(c.get("momentum_ok"))
    momentum_premium = bool(c.get("momentum_premium"))
    not_choppy = bool(c.get("not_choppy"))

    # default 0 kalau tidak ada di dict
    setup_score_internal = c.get("setup_score") or 0
    # clamp biar aman (0–3 sesuai logic analyse_symbol)
    setup_score_internal = max(0, min(int(setup_score_internal), 3))

    # ===== Komponen utama (maks 125) =====

    # Bias 5m
    if bias_ok:
        score += 20

    # Micro CHoCH
    if micro_choch:
        score += 25
    if micro_choch_premium:
        score += 10  # impulse candle bersih

    # Micro FVG
    if micro_fvg:
        score += 15

    # Momentum
    if momentum_ok:
        score += 20
    if momentum_premium:
        score += 10  # sweet spot, tidak terlalu lemah/kuat

    # Market quality
    if not_choppy:
        score += 15

    # Synergy bonus: bias + trigger + momentum
    # Di-upgrade agar nyambung dengan setup_score (0–3)
    # - Base synergy: 4 poin
    # - Tiap 1 poin setup_score → +2 poin synergy
    #   -> 4 + 3*2 = 10 (maksimal sama seperti versi lama)
    if bias_ok and micro_choch and momentum_ok:
        synergy = 4 + setup_score_internal * 2
        score += synergy

    return int(score)


def tier_from_score(score: int) -> str:
    """
    Tier lebih ketat:
    - A+ : >= 110
    - A  : 90–109
    - B  : 70–89
    - NONE : < 70
    """
    if score >= 110:
        return "A+"
    elif score >= 90:
        return "A"
    elif score >= 70:
        return "B"
    else:
        return "NONE"


def should_send_tier(tier: str, min_tier: str) -> bool:
    """
    Urutan: NONE < B < A < A+
    """
    order = {"NONE": 0, "B": 1, "A": 2, "A+": 3}
    return order.get(tier, 0) >= order.get(min_tier, 2)


def evaluate_smc_signal(conditions: Dict, min_tier: str = "A") -> Dict:
    """
    Helper kecil supaya enak dipakai di kode lain.

    Return dict:
    {
        "score": int,
        "tier": str,
        "should_send": bool
    }
    """
    score = score_smc_signal(conditions)
    tier = tier_from_score(score)
    send = should_send_tier(tier, min_tier)
    return {
        "score": score,
        "tier": tier,
        "should_send": send,
    }
