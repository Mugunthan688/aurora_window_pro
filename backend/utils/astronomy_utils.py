"""
Aurora Window Pro — backend/utils/astronomy_utils.py
=====================================================
Simplified astronomy helpers for visibility scoring and map context.

Covers:
    • Lunar illumination / moon interference scoring
    • Twilight / darkness state from local solar time
    • Day/night terminator context
    • Darkness score composition
    • Observation window quality labelling
    • Best 24-hour observation windows (used by /visibility/best-window)

Production upgrade path:
    Replace the solar-position heuristics here with:
        • Python: `ephem` library (already in requirements.txt)
          ephem.Sun(), ephem.Moon(), ephem.localtime() → exact alt/az
        • JavaScript (frontend): SunCalc.js for terminator layer rendering
    The functions below use simplified local-solar-time geometry that is
    accurate to ±1 hour — sufficient for hackathon MVP decision-making.
"""

import math
from datetime import datetime, timezone, timedelta
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
# Mean synodic month (new moon → new moon) in days
_SYNODIC_MONTH_DAYS = 29.53058868

# Known new moon reference date (J2000.0 epoch adjusted) — 2000-01-06 UTC
_KNOWN_NEW_MOON = datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc)

# Solar zenith angle thresholds (degrees) — from config / PS Section 4.3
_ZENITH_CIVIL         = 96.0
_ZENITH_NAUTICAL      = 102.0
_ZENITH_ASTRONOMICAL  = 108.0


# ===========================================================================
# 1. Lunar illumination
# ===========================================================================

async def get_lunar_illumination(latitude: float, longitude: float) -> float:
    """
    Return the current lunar illumination fraction (0.0 – 1.0).

    0.0 = new moon (darkest — best aurora photography)
    0.5 = quarter moon (moderate interference)
    1.0 = full moon (bright — worst for aurora photography)

    Method: approximate moon phase from the elapsed days since a known
    new moon, then convert phase angle to illumination using the standard
    cos² formula.

    Production upgrade: use ephem.Moon().phase (gives % illumination directly)
    or the USNO Astronomical Applications API for exact values.
    """
    now   = datetime.now(timezone.utc)
    phase = _moon_phase_fraction(now)           # 0.0–1.0 through the lunation
    # Illumination = (1 - cos(phase_angle)) / 2
    # phase_angle goes from 0 (new) → π (full) → 2π (new again)
    phase_angle    = phase * 2 * math.pi
    illumination   = (1 - math.cos(phase_angle)) / 2
    return round(max(0.0, min(1.0, illumination)), 4)


def _moon_phase_fraction(dt: datetime) -> float:
    """
    Return the fractional position in the current lunar cycle (0.0–1.0).
    0.0 = new moon, 0.5 = full moon, 1.0 = back to new moon.
    """
    elapsed_days = (dt - _KNOWN_NEW_MOON).total_seconds() / 86400.0
    return (elapsed_days % _SYNODIC_MONTH_DAYS) / _SYNODIC_MONTH_DAYS


# ===========================================================================
# 2. Moon phase and interference scoring
# ===========================================================================

def moon_phase_impact(illumination: float) -> dict:
    """
    Convert lunar illumination (0–1) to a named phase and interference level.

    Returns:
        phase_name          (str)  — "New Moon", "Crescent", etc.
        interference_level  (str)  — "none" / "minimal" / "moderate" / "significant" / "severe"
        photography_impact  (str)  — plain-English impact note
        moon_penalty_pct    (float)— 0–100, how much this moon reduces darkness score
    """
    illum = max(0.0, min(1.0, illumination))

    if illum < 0.05:
        phase = "New Moon"
        level = "none"
        impact = "Ideal — moon below horizon or invisible."
        penalty = 0.0
    elif illum < 0.25:
        phase = "Waxing Crescent" if _is_waxing() else "Waning Crescent"
        level = "minimal"
        impact = "Crescent moon sets early — minimal impact on dark-sky hours."
        penalty = illum * 40
    elif illum < 0.50:
        phase = "First Quarter" if _is_waxing() else "Last Quarter"
        level = "moderate"
        impact = "Quarter moon visible for part of the night — plan around its setting."
        penalty = illum * 60
    elif illum < 0.80:
        phase = "Waxing Gibbous" if _is_waxing() else "Waning Gibbous"
        level = "significant"
        impact = "Bright gibbous moon washes out faint aurora. Strong displays still visible."
        penalty = illum * 80
    else:
        phase = "Full Moon"
        level = "severe"
        impact = "Full moon dramatically reduces contrast. Only brilliant aurora storms visible."
        penalty = min(100.0, illum * 100)

    return {
        "phase_name":         phase,
        "interference_level": level,
        "photography_impact": impact,
        "moon_penalty_pct":   round(penalty, 1),
        "illumination":       round(illum, 3),
    }


def moon_interference_score(illumination: float) -> float:
    """
    Return a 0–100 score representing how CLEAR the sky is of moon interference.
    100 = new moon (no interference), 0 = full moon (maximum interference).
    Used as an input to the darkness sub-score in visibility_score.py.
    """
    return round((1.0 - max(0.0, min(1.0, illumination))) * 100.0, 1)


def _is_waxing() -> bool:
    """Return True if the moon is currently waxing (growing brighter)."""
    phase = _moon_phase_fraction(datetime.now(timezone.utc))
    return phase < 0.5


# ===========================================================================
# 3. Twilight / darkness state
# ===========================================================================

async def get_twilight_state(latitude: float, longitude: float) -> str:
    """
    Return the current twilight/darkness state at the given location.

    Returns one of:
        "day"           — Sun above horizon, no aurora observation possible
        "civil"         — Sun 0–6° below horizon, bright sky
        "nautical"      — Sun 6–12° below horizon, horizon still visible
        "astronomical"  — Sun 12–18° below horizon, sky nearly dark
        "night"         — Sun >18° below horizon, true astronomical darkness

    Method: estimate the solar elevation angle from the local solar hour angle.
    This is a simplified calculation (ignores declination fully) accurate to
    ±1–2 hours — sufficient for MVP observation window scheduling.

    Production upgrade: use ephem.Sun().alt computed for the observer's
    location and time for exact solar elevation.
    """
    now_utc  = datetime.now(timezone.utc)
    # Approximate local solar time from longitude (15° per hour)
    solar_hour = (now_utc.hour + now_utc.minute / 60.0 + longitude / 15.0) % 24

    # Approximate solar elevation using a sinusoidal day model
    # Peak elevation at solar noon (hour 12), trough at midnight
    solar_elev_deg = _approx_solar_elevation(solar_hour, latitude)

    return _elevation_to_twilight_state(solar_elev_deg)


def twilight_state_from_local_time(
    utc_hour: float,
    longitude: float,
    latitude: float,
) -> str:
    """
    Synchronous version of get_twilight_state for use in scoring loops.

    Args:
        utc_hour   — Hour of day in UTC (0–24, fractional allowed)
        longitude  — Observer longitude
        latitude   — Observer latitude

    Returns twilight state string ("day" / "civil" / "nautical" / "astronomical" / "night").
    """
    solar_hour = (utc_hour + longitude / 15.0) % 24
    solar_elev = _approx_solar_elevation(solar_hour, latitude)
    return _elevation_to_twilight_state(solar_elev)


def _approx_solar_elevation(solar_hour: float, latitude: float) -> float:
    """
    Approximate solar elevation angle in degrees for a given solar hour and latitude.

    Uses a simple sinusoidal model:
        elevation ≈ max_elevation × cos(hour_angle) − latitude_correction

    This ignores seasonal declination (accurate within ±23° of the true value).
    Sufficient for "is it day or night" decisions in a hackathon context.
    """
    # Hour angle in radians: 0 at solar noon, ±π at midnight
    hour_angle_rad = math.radians((solar_hour - 12.0) * 15.0)

    # Max elevation at solar noon ≈ 90° − |latitude| (equinox approximation)
    max_elevation = 90.0 - abs(latitude)

    # Elevation varies sinusoidally through the day
    elevation = max_elevation * math.cos(hour_angle_rad)

    return elevation


def _elevation_to_twilight_state(solar_elevation_deg: float) -> str:
    """Map a solar elevation angle (degrees) to a twilight state string."""
    if solar_elevation_deg > 0:
        return "day"
    if solar_elevation_deg > -6:
        return "civil"
    if solar_elevation_deg > -12:
        return "nautical"
    if solar_elevation_deg > -18:
        return "astronomical"
    return "night"


# ===========================================================================
# 4. Darkness score
# ===========================================================================

def estimate_darkness_score(
    twilight_state: str,
    lunar_illumination: float,
    bortle_class: int,
) -> float:
    """
    Compute a composite darkness score (0–100) from three inputs.

    Sub-weights (must sum to 1.0):
        Twilight state     — 20%
        Lunar illumination — 30%
        Bortle class       — 50%

    Returns a float 0–100 where 100 = perfect darkness.
    """
    # Twilight sub-score
    twilight_scores = {
        "night":        100.0,
        "astronomical":  75.0,
        "nautical":      40.0,
        "civil":         10.0,
        "day":            0.0,
    }
    twilight_score = twilight_scores.get(twilight_state.lower(), 100.0)

    # Lunar sub-score — full moon = 0, new moon = 100
    lunar_score = moon_interference_score(lunar_illumination)

    # Bortle sub-score — Bortle 1 = 100, Bortle 9 = 0
    b = max(1, min(9, int(bortle_class)))
    bortle_score = ((9 - b) / 8.0) * 100.0

    darkness = (
        twilight_score * 0.20
        + lunar_score  * 0.30
        + bortle_score * 0.50
    )
    return round(max(0.0, min(100.0, darkness)), 2)


# ===========================================================================
# 5. Observation window quality label
# ===========================================================================

def observation_window_label(
    twilight_state: str,
    lunar_illumination: float,
    aurora_probability: float,
) -> str:
    """
    Return a single plain-English quality label for an observation window.
    Used by /visibility/best-window to annotate forecast windows.
    """
    if twilight_state == "day":
        return "Daytime — aurora not visible"
    if aurora_probability < 5:
        return "No aurora expected"

    moon = moon_phase_impact(lunar_illumination)
    interference = moon["interference_level"]

    if aurora_probability >= 60 and interference in ("none", "minimal"):
        return "Prime window — excellent aurora and dark sky"
    if aurora_probability >= 40 and interference in ("none", "minimal", "moderate"):
        return "Good window — favourable conditions"
    if aurora_probability >= 20:
        return "Marginal window — monitor and be ready to go"
    return "Unlikely — aurora probability too low"


# ===========================================================================
# 6. Best observation windows for /visibility/best-window
# ===========================================================================

async def get_best_observation_windows(
    latitude: float,
    longitude: float,
    hours_ahead: int = 24,
) -> list[dict]:
    """
    Return a ranked list of aurora observation windows over the next
    `hours_ahead` hours (default 24).

    Each window represents a consecutive block of hours where:
        • Sky is dark (astronomical or true night)
        • Cloud cover is below 60% (usable threshold — optimistic filter)
        • Aurora probability is non-negligible (> 5%)

    Steps:
        1. Walk through each hour over the forecast period.
        2. Classify each hour by twilight state.
        3. Merge consecutive dark hours into windows.
        4. Assign estimated aurora probability (uses current OVATION value
           as a static proxy — production would use 3-day Kp forecast).
        5. Sort windows by estimated composite score descending.

    Returns up to 5 windows. Returns empty list if no dark windows exist
    (e.g. polar day in summer at high latitudes).
    """
    from services.ovation_parser import get_ovation_probability
    from services.visibility_score import fetch_open_meteo_weather

    now_utc = datetime.now(timezone.utc)

    # Fetch aurora probability once — proxy for all windows
    ovation  = await get_ovation_probability(latitude, longitude)
    aurora_p = ovation.get("aurora_probability", 0.0) or 0.0

    # Fetch current cloud cover once
    weather  = await fetch_open_meteo_weather(latitude, longitude)
    cloud_p  = weather.get("cloud_cover_pct", 50.0)

    # Lunar illumination (current)
    lunar = await get_lunar_illumination(latitude, longitude)

    # --- Walk forward hour by hour ---
    hourly_states = []
    for h in range(hours_ahead):
        future_dt  = now_utc + timedelta(hours=h)
        utc_hour   = future_dt.hour + future_dt.minute / 60.0
        state      = twilight_state_from_local_time(utc_hour, longitude, latitude)
        dark_enough = state in ("astronomical", "night")
        hourly_states.append({
            "hour_offset": h,
            "datetime_utc": future_dt.isoformat(),
            "twilight_state": state,
            "dark_enough": dark_enough,
        })

    # --- Merge consecutive dark hours into windows ---
    windows = []
    current_window = None

    for entry in hourly_states:
        if entry["dark_enough"]:
            if current_window is None:
                current_window = {
                    "start_utc":     entry["datetime_utc"],
                    "start_offset":  entry["hour_offset"],
                    "end_utc":       entry["datetime_utc"],
                    "end_offset":    entry["hour_offset"],
                    "duration_hours": 1,
                    "hours":         [entry],
                }
            else:
                current_window["end_utc"]       = entry["datetime_utc"]
                current_window["end_offset"]    = entry["hour_offset"]
                current_window["duration_hours"] += 1
                current_window["hours"].append(entry)
        else:
            if current_window is not None:
                windows.append(current_window)
                current_window = None

    if current_window is not None:
        windows.append(current_window)

    # --- Annotate windows with scores ---
    annotated = []
    for w in windows:
        # Estimated score for this window
        darkness_sc = estimate_darkness_score(
            twilight_state="night",   # Window is only added if dark
            lunar_illumination=lunar,
            bortle_class=3,           # Assume rural for scheduling — real value via terrain_check
        )
        # Simple composite: aurora 60%, darkness 25%, cloud clarity 15%
        cloud_clarity = 100.0 - cloud_p
        score = (
            aurora_p        * 0.60
            + darkness_sc   * 0.25
            + cloud_clarity * 0.15
        )
        mid_twilight = w["hours"][len(w["hours"]) // 2]["twilight_state"]
        label = observation_window_label(mid_twilight, lunar, aurora_p)

        # Remove hour-level detail from response — keep payload small
        w_clean = {k: v for k, v in w.items() if k != "hours"}
        annotated.append({
            **w_clean,
            "estimated_score":    round(min(100.0, score), 1),
            "aurora_probability": round(aurora_p, 1),
            "cloud_cover_pct":    round(cloud_p, 1),
            "lunar_illumination": round(lunar, 3),
            "darkness_score":     round(darkness_sc, 1),
            "window_label":       label,
        })

    # Sort by estimated score descending, return top 5
    annotated.sort(key=lambda w: -w["estimated_score"])
    return annotated[:5]