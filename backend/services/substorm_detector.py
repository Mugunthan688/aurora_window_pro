"""
Aurora Window Pro — backend/services/substorm_detector.py
==========================================================
Rule-based substorm precursor detection engine.

PS Stretch Goal: "Real-time monitoring of the negative Bz deflection rate
to fire a 10-minute substorm precursor alert."

Logic overview:
    Substorms are triggered when:
    1. Bz is strongly negative (southward) — magnetic reconnection driver
    2. Solar wind speed is elevated — more particle energy input
    3. Bz is trending MORE negative — rapid loading of the magnetosphere

    We accumulate evidence points across these three factors and map the
    total to a risk level: low → moderate → high → imminent.
"""

import logging
from datetime import datetime, timezone
from services.solar_wind_ingestion import fetch_magnetic_field, fetch_plasma

logger = logging.getLogger(__name__)

# Risk thresholds (evidence point totals → risk level)
_RISK_LEVELS = [
    (8,  "imminent",  "⚡ Substorm likely within ~10 minutes. Aurora burst imminent."),
    (5,  "high",      "🔴 Strong substorm conditions. Head outside now."),
    (3,  "moderate",  "🟡 Substorm conditions building. Stay alert."),
    (0,  "low",       "🟢 Quiet. No substorm indicators at this time."),
]

# In-memory Bz history for trend analysis (up to 10 recent readings)
_bz_history: list[float] = []
_MAX_HISTORY = 10


async def get_substorm_risk() -> dict:
    """
    Primary service function called by space_weather_api.py.

    Fetches current solar wind conditions, runs rule-based substorm scoring,
    and returns a risk assessment dict.
    """
    mag_data    = await _safe_fetch_mag()
    plasma_data = await _safe_fetch_plasma()

    bz    = mag_data.get("bz")
    speed = plasma_data.get("speed")
    density = plasma_data.get("density")
    source = mag_data.get("source", "fallback")

    # Update rolling Bz history
    if bz is not None:
        _bz_history.append(bz)
        if len(_bz_history) > _MAX_HISTORY:
            _bz_history.pop(0)

    bz_rate = _compute_bz_rate(_bz_history)

    evidence, breakdown = _score_evidence(bz, speed, density, bz_rate)
    risk_level, message = _map_risk(evidence)
    precursor = risk_level in ("high", "imminent") and bz_rate is not None and bz_rate < -1.5

    return {
        "risk_level":          risk_level,
        "substorm_probability": _evidence_to_probability(evidence),
        "bz_now":              bz,
        "bz_rate":             round(bz_rate, 3) if bz_rate is not None else None,
        "solar_wind_speed":    speed,
        "density":             density,
        "evidence_score":      evidence,
        "evidence_breakdown":  breakdown,
        "precursor_flag":      precursor,
        "message":             message,
        "source":              source,
        "checked_at_utc":      datetime.now(timezone.utc).isoformat(),
    }


def _score_evidence(
    bz: float | None,
    speed: float | None,
    density: float | None,
    bz_rate: float | None,
) -> tuple[int, dict]:
    """
    Accumulate evidence points from three independent signals.
    Max possible score: 10 points.

    Returns (total_evidence, breakdown_dict).
    """
    evidence = 0
    breakdown = {}

    # --- Signal 1: Bz magnitude (0–5 pts) ---
    if bz is not None:
        if bz < -20:
            pts = 5
            note = f"Bz = {bz:.1f} nT — extreme southward field"
        elif bz < -15:
            pts = 4
            note = f"Bz = {bz:.1f} nT — very strong southward"
        elif bz < -10:
            pts = 3
            note = f"Bz = {bz:.1f} nT — strong southward"
        elif bz < -7:
            pts = 2
            note = f"Bz = {bz:.1f} nT — alert threshold crossed"
        elif bz < -4:
            pts = 1
            note = f"Bz = {bz:.1f} nT — mildly southward"
        else:
            pts = 0
            note = f"Bz = {bz:.1f} nT — northward or near zero, no concern"
        evidence += pts
        breakdown["bz_magnitude"] = {"points": pts, "max": 5, "note": note}
    else:
        breakdown["bz_magnitude"] = {"points": 0, "max": 5, "note": "Bz unavailable"}

    # --- Signal 2: Solar wind speed (0–3 pts) ---
    if speed is not None:
        if speed > 700:
            pts = 3
            note = f"Speed = {speed:.0f} km/s — very high, strong energy input"
        elif speed > 550:
            pts = 2
            note = f"Speed = {speed:.0f} km/s — elevated"
        elif speed > 450:
            pts = 1
            note = f"Speed = {speed:.0f} km/s — slightly elevated"
        else:
            pts = 0
            note = f"Speed = {speed:.0f} km/s — background level"
        evidence += pts
        breakdown["solar_wind_speed"] = {"points": pts, "max": 3, "note": note}
    else:
        breakdown["solar_wind_speed"] = {"points": 0, "max": 3, "note": "Speed unavailable"}

    # --- Signal 3: Bz trend / rate of change (0–2 pts) ---
    if bz_rate is not None:
        if bz_rate < -3.0:
            pts = 2
            note = f"Bz rate = {bz_rate:.2f} nT/min — rapid southward plunge"
        elif bz_rate < -1.5:
            pts = 1
            note = f"Bz rate = {bz_rate:.2f} nT/min — trending southward"
        else:
            pts = 0
            note = f"Bz rate = {bz_rate:.2f} nT/min — stable or recovering"
        evidence += pts
        breakdown["bz_trend"] = {"points": pts, "max": 2, "note": note}
    else:
        breakdown["bz_trend"] = {"points": 0, "max": 2, "note": "Insufficient Bz history for trend"}

    return evidence, breakdown


def _compute_bz_rate(history: list[float]) -> float | None:
    """
    Estimate Bz rate-of-change (nT/min) from recent history.
    Uses linear slope of the last 5 readings.
    Returns None if fewer than 2 readings are available.
    """
    if len(history) < 2:
        return None
    recent = history[-5:]   # Use up to 5 most recent readings
    n = len(recent)
    # Simple linear regression slope
    x_mean = (n - 1) / 2.0
    y_mean = sum(recent) / n
    numerator   = sum((i - x_mean) * (recent[i] - y_mean) for i in range(n))
    denominator = sum((i - x_mean) ** 2 for i in range(n))
    if denominator == 0:
        return 0.0
    return numerator / denominator   # nT per polling interval (~1 min)


def _map_risk(evidence: int) -> tuple[str, str]:
    """Map evidence score to a risk level label and message."""
    for threshold, level, message in _RISK_LEVELS:
        if evidence >= threshold:
            return level, message
    return "low", "Quiet conditions."


def _evidence_to_probability(evidence: int) -> float:
    """Convert evidence score (0–10) to a rough substorm probability (0–100%)."""
    return round(min(100.0, evidence * 10.0), 1)


async def _safe_fetch_mag() -> dict:
    try:
        return await fetch_magnetic_field()
    except Exception as e:
        logger.warning("Mag fetch failed in substorm detector: %s", e)
        return {"bz": None, "source": "fallback"}


async def _safe_fetch_plasma() -> dict:
    try:
        return await fetch_plasma()
    except Exception as e:
        logger.warning("Plasma fetch failed in substorm detector: %s", e)
        return {"speed": None, "density": None, "source": "fallback"}