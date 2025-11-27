# smc_scoring.py
# =========================
# SMC AGGRESSIVE SCALPING SCORING
# =========================

def score_smc_signal(c: dict) -> int:
    """
    Scoring sederhana untuk setup Aggressive Scalping (0–100).
    """
    score = 0

    if c.get("bias_ok"):
        score += 25   # trend 5m searah

    if c.get("micro_choch"):
        score += 35   # trigger utama

    if c.get("micro_fvg"):
        score += 15   # confluence imbalance

    if c.get("momentum_ok"):
        score += 15   # tenaga harga

    if c.get("not_choppy"):
        score += 10   # market tidak terlalu noisy

    return score


def tier_from_score(score: int) -> str:
    """
    Mapping score → Tier untuk Aggressive Scalping:
    - A+ : >= 85
    - A  : 70–84
    - B  : 55–69
    - NONE : < 55
    """
    if score >= 85:
        return "A+"
    elif score >= 70:
        return "A"
    elif score >= 55:
        return "B"
    else:
        return "NONE"


def should_send_tier(tier: str, min_tier: str) -> bool:
    """
    Bandingkan tier terhadap min_tier:
    Urutan: NONE < B < A < A+
    """
    order = {"NONE": 0, "B": 1, "A": 2, "A+": 3}
    return order.get(tier, 0) >= order.get(min_tier, 2)
