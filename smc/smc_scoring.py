# smc/smc_scoring.py
# =========================
# SMC AGGRESSIVE SCALPING SCORING (PREMIUM)
# =========================

from typing import Dict


def score_smc_signal(c: Dict) -> int:
    """
    Scoring untuk setup Aggressive Scalping (0–150-an).
    Lebih sensitif ke:
    - Bias 5m + HTF (15m & 1H)
    - Kualitas micro (CHoCH premium, FVG)
    - Momentum (RSI)
    - Market quality (choppy / overextended)
    """

    score = 0

    bias_ok             = bool(c.get("bias_ok"))
    micro_choch         = bool(c.get("micro_choch"))
    micro_choch_premium = bool(c.get("micro_choch_premium"))
    micro_fvg           = bool(c.get("micro_fvg"))
    momentum_ok         = bool(c.get("momentum_ok"))
    momentum_premium    = bool(c.get("momentum_premium"))
    not_choppy          = bool(c.get("not_choppy"))
    not_overextended    = bool(c.get("not_overextended"))
    htf_15m_trend_ok    = bool(c.get("htf_15m_trend_ok"))
    htf_1h_trend_ok     = bool(c.get("htf_1h_trend_ok"))

    setup_score_internal = c.get("setup_score") or 0
    setup_score_internal = max(0, min(int(setup_score_internal), 3))

    # 1) Bias + HTF
    if bias_ok:
        score += 20

    if htf_15m_trend_ok:
        score += 15

    if htf_1h_trend_ok:
        score += 15

    # 2) Micro structure
    if micro_choch:
        score += 20

    if micro_choch_premium:
        score += 20   # candle impuls premium lebih dihargai

    if micro_fvg:
        score += 10

    # 3) Momentum (RSI)
    if momentum_ok:
        score += 20

    if momentum_premium:
        score += 15

    # 4) Market quality
    if not_choppy:
        score += 10

    if not_overextended:
        score += 10

    # 5) Synergy bonus
    if (
        bias_ok
        and htf_15m_trend_ok
        and htf_1h_trend_ok
        and micro_choch_premium
        and momentum_premium
    ):
        score += 10 + setup_score_internal * 2  # max +16

    return int(min(score, 150))


def tier_from_score(score: int) -> str:
    """
    Tier:
    - A+ : >= 125
    - A  : 100–124
    - B  : 80–99
    - NONE : < 80
    """
    if score >= 125:
        return "A+"
    elif score >= 100:
        return "A"
    elif score >= 80:
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
