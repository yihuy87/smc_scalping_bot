# smc_scoring.py
# =========================
# SMC AGGRESSIVE SCALPING SCORING (PREMIUM)
# =========================

def score_smc_signal(c: dict) -> int:
    """
    Scoring untuk setup Aggressive Scalping (0–125).
    A+ di-design lebih jarang.
    """
    score = 0

    # Bias 5m
    if c.get("bias_ok"):
        score += 20

    # Micro CHoCH
    if c.get("micro_choch"):
        score += 25
    if c.get("micro_choch_premium"):
        score += 10  # impulse candle bersih

    # Micro FVG
    if c.get("micro_fvg"):
        score += 15

    # Momentum
    if c.get("momentum_ok"):
        score += 20
    if c.get("momentum_premium"):
        score += 10  # sweet spot, tidak terlalu lemah/kuat

    # Market quality
    if c.get("not_choppy"):
        score += 15

    # Synergy bonus: bias + trigger + momentum
    if c.get("bias_ok") and c.get("micro_choch") and c.get("momentum_ok"):
        score += 10

    return score


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
