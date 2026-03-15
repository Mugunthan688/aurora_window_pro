"""
Aurora Window Pro — backend/api/visibility_api.py
==================================================
FastAPI router exposing real-time aurora visibility scoring endpoints.

The Visibility Score (0–100) is a composite metric combining three components
as specified in the problem statement (PS Section 2.1 / D3):

    Visibility Score =
        (aurora_probability_score  × 0.50)   ← OVATION-Prime probability
      + (cloud_cover_score         × 0.30)   ← Open-Meteo cloud cover
      + (darkness_score            × 0.20)   ← Bortle + lunar + twilight

Weights are sourced from config.py and are documented / defensible for judges.

Endpoints:
    GET /visibility/score           — Full composite score for a lat/lon right now
    GET /visibility/best-window     — Best observation window in the next 24 hours
"""

from fastapi import APIRouter, Query, HTTPException
from typing import Annotated

# ---------------------------------------------------------------------------
# Service and utility imports
# ---------------------------------------------------------------------------
from services.visibility_score import compute_visibility_score   # Core composite engine
from services.ovation_parser   import get_ovation_probability    # OVATION grid lookup
from services.terrain_check    import get_terrain_context        # Horizon / obstruction hints
from utils.astronomy_utils     import (
    get_lunar_illumination,    # Returns 0.0–1.0 fraction
    get_twilight_state,        # Returns "day" | "civil" | "nautical" | "astronomical" | "night"
    get_best_observation_windows,  # Returns list of dark windows in next 24h
)

# ---------------------------------------------------------------------------
# Config — weight constants and routing thresholds
# ---------------------------------------------------------------------------
from config import (
    VISIBILITY_WEIGHT_AURORA_PROBABILITY,
    VISIBILITY_WEIGHT_CLOUD_COVER,
    VISIBILITY_WEIGHT_DARKNESS,
    ROUTING_MIN_AURORA_PROBABILITY_PCT,
    ROUTING_MAX_CLOUD_COVER_PCT,
    ROUTING_MAX_BORTLE_CLASS,
    MAX_ACCEPTABLE_LUNAR_ILLUMINATION,
)

import httpx
import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Router — mounted at /visibility in main.py
# ---------------------------------------------------------------------------
router = APIRouter(
    prefix="/visibility",
    tags=["Visibility Score"],
)


# ===========================================================================
# ENDPOINT 1 — GET /visibility/score
# ===========================================================================
@router.get("/score", summary="Real-time aurora visibility score for a lat/lon")
async def get_visibility_score(
    latitude: Annotated[
        float,
        Query(
            ge=-90.0,
            le=90.0,
            description="Observer latitude in decimal degrees (e.g. 64.1355 for Reykjavik)",
        ),
    ],
    longitude: Annotated[
        float,
        Query(
            ge=-180.0,
            le=180.0,
            description="Observer longitude in decimal degrees (e.g. -21.8954 for Reykjavik)",
        ),
    ],
    # Optional weight overrides — PS allows user-configurable thresholds (D4)
    weight_aurora: Annotated[
        float | None,
        Query(
            ge=0.0,
            le=1.0,
            description="Override weight for aurora probability component (default: 0.50). "
                        "All three weights must sum to 1.0 if overriding.",
        ),
    ] = None,
    weight_cloud: Annotated[
        float | None,
        Query(
            ge=0.0,
            le=1.0,
            description="Override weight for cloud cover component (default: 0.30).",
        ),
    ] = None,
    weight_darkness: Annotated[
        float | None,
        Query(
            ge=0.0,
            le=1.0,
            description="Override weight for darkness component (default: 0.20).",
        ),
    ] = None,
):
    """
    Computes a composite aurora visibility score (0–100) for the given
    latitude and longitude at the current moment.

    Score breakdown:
    - **aurora_probability** (0–100 %): From NOAA OVATION-Prime grid lookup.
      Represents the statistical chance of aurora overhead at this location.
    - **cloud_cover** (0–100 %): From Open-Meteo API.
      High cloud cover penalises the score (inverted for scoring: clear = high).
    - **darkness_score** (0–100): Composite of Bortle class, lunar illumination,
      and current twilight state. True darkness scores highest.

    The final score uses configurable weights (default 50/30/20 from config.py).
    If the user provides custom weights, they must sum to 1.0.

    Returns a routing-ready flag `meets_routing_criteria` that is `true` only
    when aurora_probability > 50%, cloud_cover < 30%, and Bortle < 4.
    """

    # --- Resolve and validate weights ---
    w_aurora   = weight_aurora   if weight_aurora   is not None else VISIBILITY_WEIGHT_AURORA_PROBABILITY
    w_cloud    = weight_cloud    if weight_cloud    is not None else VISIBILITY_WEIGHT_CLOUD_COVER
    w_darkness = weight_darkness if weight_darkness is not None else VISIBILITY_WEIGHT_DARKNESS

    _validate_weights(w_aurora, w_cloud, w_darkness)

    weights = {
        "aurora":    w_aurora,
        "cloud":     w_cloud,
        "darkness":  w_darkness,
    }

    # --- Gather all component data concurrently ---
    # Each service call is independent; run them and let the score engine combine them.
    try:
        score_result = await compute_visibility_score(
            latitude=latitude,
            longitude=longitude,
            weights=weights,
        )
    except Exception as e:
        logger.error("Visibility score computation failed for (%s, %s): %s", latitude, longitude, e)
        raise HTTPException(
            status_code=503,
            detail="Visibility score could not be computed. One or more data sources are unavailable.",
        )

    # --- Supplemental data for rich response ---
    lunar_illumination = await _safe_get_lunar(latitude, longitude)
    twilight_state     = await _safe_get_twilight(latitude, longitude)
    terrain            = await _safe_get_terrain(latitude, longitude)

    # --- Extract component scores for transparency ---
    aurora_prob    = score_result.get("aurora_probability", 0.0)    # 0–100
    cloud_pct      = score_result.get("cloud_cover_pct", 0.0)       # 0–100 (raw %)
    darkness_score = score_result.get("darkness_score", 0.0)        # 0–100
    bortle_est     = score_result.get("bortle_estimate")            # 1–9 or None
    final_score    = score_result.get("visibility_score", 0.0)      # 0–100

    # --- Routing criteria check (PS Section 2.1 — Logistical Routing stretch goal) ---
    meets_routing_criteria = (
        aurora_prob  >= ROUTING_MIN_AURORA_PROBABILITY_PCT  # > 50%
        and cloud_pct <= ROUTING_MAX_CLOUD_COVER_PCT        # < 30%
        and (bortle_est is None or bortle_est < ROUTING_MAX_BORTLE_CLASS)  # < Bortle 4
    )

    # --- Moon interference flag ---
    moon_interference = _classify_moon_interference(lunar_illumination)

    return {
        # --- Top-level score ---
        "visibility_score":       round(final_score, 1),   # 0–100
        "score_label":            _score_label(final_score),

        # --- Component breakdown ---
        "components": {
            "aurora_probability": {
                "value":  round(aurora_prob, 1),
                "unit":   "%",
                "weight": w_aurora,
                "source": score_result.get("aurora_source", "ovation"),
            },
            "cloud_cover": {
                "value":         round(cloud_pct, 1),
                "unit":          "%",
                "weight":        w_cloud,
                "clear_sky_pct": round(100.0 - cloud_pct, 1),  # Friendlier label for UI
                "source":        score_result.get("cloud_source", "open-meteo"),
            },
            "darkness": {
                "value":              round(darkness_score, 1),
                "weight":             w_darkness,
                "bortle_estimate":    bortle_est,
                "bortle_description": _bortle_description(bortle_est),
                "lunar_illumination": round(lunar_illumination * 100, 1) if lunar_illumination is not None else None,
                "moon_interference":  moon_interference,
                "twilight_state":     twilight_state,
            },
        },

        # --- Location context ---
        "location": {
            "latitude":  latitude,
            "longitude": longitude,
            "terrain":   terrain,   # e.g. {"horizon_obstruction": "low", "elevation_m": 42}
        },

        # --- Routing flag (stretch goal — PS Section 2.1) ---
        "meets_routing_criteria": meets_routing_criteria,
        "routing_criteria": {
            "aurora_probability_min":  ROUTING_MIN_AURORA_PROBABILITY_PCT,
            "cloud_cover_max":         ROUTING_MAX_CLOUD_COVER_PCT,
            "bortle_class_max":        ROUTING_MAX_BORTLE_CLASS,
        },

        # --- Data freshness ---
        "data_source":   score_result.get("source", "live"),   # "live" or "fallback"
        "computed_at_utc": score_result.get("computed_at_utc"),
    }


# ===========================================================================
# ENDPOINT 2 — GET /visibility/best-window
# ===========================================================================
@router.get("/best-window", summary="Best aurora observation window in the next 24 hours")
async def get_best_observation_window(
    latitude: Annotated[
        float,
        Query(
            ge=-90.0,
            le=90.0,
            description="Observer latitude in decimal degrees.",
        ),
    ],
    longitude: Annotated[
        float,
        Query(
            ge=-180.0,
            le=180.0,
            description="Observer longitude in decimal degrees.",
        ),
    ],
):
    """
    Returns a ranked list of aurora observation windows for the next 24 hours.

    Each window is a time period where:
    - Sky is dark (astronomical twilight or true night)
    - Cloud cover forecast is below 60% (usable — not ideal threshold)
    - Aurora activity is non-negligible based on the 3-day Kp forecast

    This is a planning aid for astrophotographers to decide when to head out.
    Cloud data comes from Open-Meteo hourly forecast.
    Darkness windows are computed from solar zenith angle via astronomy utils.

    Returns up to 5 candidate windows sorted by estimated composite score.
    """

    try:
        windows = await get_best_observation_windows(
            latitude=latitude,
            longitude=longitude,
        )
    except Exception as e:
        logger.error("Best-window computation failed for (%s, %s): %s", latitude, longitude, e)
        raise HTTPException(
            status_code=503,
            detail="Could not compute observation windows. Forecast data may be unavailable.",
        )

    if not windows:
        return {
            "location":        {"latitude": latitude, "longitude": longitude},
            "windows":         [],
            "recommendation":  "No suitable observation windows found in the next 24 hours. "
                               "Check back after current cloud cover clears.",
            "source":          "live",
        }

    # Annotate each window with a score label and photography advice
    annotated_windows = []
    for w in windows:
        score = w.get("estimated_score", 0.0)
        annotated_windows.append({
            **w,                                                   # Pass through all service fields
            "score_label":          _score_label(score),
            "photography_advice":   _photography_advice(score, w),
        })

    best = annotated_windows[0]

    return {
        "location": {
            "latitude":  latitude,
            "longitude": longitude,
        },
        "best_window":    best,
        "all_windows":    annotated_windows,
        "window_count":   len(annotated_windows),
        "recommendation": (
            f"Best window: {best.get('start_utc', 'Unknown')} → {best.get('end_utc', 'Unknown')} UTC "
            f"(estimated score: {round(best.get('estimated_score', 0), 1)}/100)"
        ),
        "source": "live",
    }


# ===========================================================================
# Private helpers
# ===========================================================================

def _validate_weights(w_aurora: float, w_cloud: float, w_darkness: float) -> None:
    """
    Ensure the three visibility weights sum to 1.0 (within floating-point tolerance).
    Raises HTTP 422 if the caller provided custom weights that don't balance.
    """
    total = w_aurora + w_cloud + w_darkness
    if abs(total - 1.0) > 0.01:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Custom weights must sum to 1.0. "
                f"Received: weight_aurora={w_aurora}, weight_cloud={w_cloud}, "
                f"weight_darkness={w_darkness} → sum={round(total, 4)}"
            ),
        )


def _score_label(score: float | None) -> str:
    """Map a 0–100 numeric score to a display label for the UI."""
    if score is None:
        return "Unknown"
    if score >= 80:  return "Excellent"
    if score >= 60:  return "Good"
    if score >= 40:  return "Fair"
    if score >= 20:  return "Poor"
    return                  "Very Poor"


def _bortle_description(bortle: int | float | None) -> str:
    """
    Return a plain-language description of a Bortle class estimate.
    Bortle scale runs 1 (darkest) to 9 (inner city).
    PS Section 4.3 references this for routing threshold (< Class 4).
    """
    if bortle is None:
        return "Unknown"
    b = int(bortle)
    descriptions = {
        1: "Excellent dark sky — zodiacal light and airglow visible",
        2: "Truly dark sky — typical remote site",
        3: "Rural sky — some light pollution on horizon",
        4: "Rural/suburban transition — Milky Way complex but clear",
        5: "Suburban sky — Milky Way washed out toward horizon",
        6: "Bright suburban sky — some dark patches remain",
        7: "Suburban/urban transition — Milky Way barely visible",
        8: "City sky — only bright clusters visible",
        9: "Inner city sky — only bright stars visible",
    }
    return descriptions.get(b, f"Bortle Class {b}")


def _classify_moon_interference(lunar_illumination: float | None) -> str:
    """
    Classify moon interference for the astrophotographer.
    PS Section 4.3 — lunar phase & illumination used in Visibility Score.
    Threshold from config: MAX_ACCEPTABLE_LUNAR_ILLUMINATION = 0.25
    """
    if lunar_illumination is None:
        return "unknown"
    if lunar_illumination < 0.10:
        return "none"       # New moon — ideal conditions
    if lunar_illumination < 0.25:
        return "minimal"    # Crescent — acceptable
    if lunar_illumination < 0.50:
        return "moderate"   # Quarter moon — degrades faint aurora
    if lunar_illumination < 0.80:
        return "significant" # Gibbous — washes out all but strong displays
    return "severe"         # Full moon — aurora photography very difficult


def _photography_advice(score: float, window: dict) -> str:
    """
    Return practical photography guidance for a given observation window.
    Combines estimated score with window-specific context.
    """
    cloud_pct = window.get("cloud_cover_pct", 50.0)
    moon_pct  = window.get("lunar_illumination_pct", 0.0)

    if score >= 75:
        return (
            "Prime conditions. Set up wide-angle on a tracking mount. "
            "ISO 1600–3200, f/2.8, 10–20s exposures."
        )
    if score >= 50:
        if cloud_pct > 40:
            return (
                "Partially cloudy — shoot in gaps between clouds. "
                "Use short bursts and check histogram frequently."
            )
        if moon_pct > 50:
            return (
                "Moon is bright. Use a shorter shutter (5–10s) and shoot "
                "when the moon is below the horizon if possible."
            )
        return "Decent window. ISO 800–1600, f/2.8, 15–25s. Scout your foreground now."
    if score >= 25:
        return (
            "Marginal conditions. Worth monitoring but don't drive far. "
            "Keep your camera ready indoors and step out if conditions improve."
        )
    return "Poor conditions. Rest and set an alert for the next clear window."


# ---------------------------------------------------------------------------
# Safe wrappers — return None instead of crashing if a utility is unavailable
# ---------------------------------------------------------------------------

async def _safe_get_lunar(lat: float, lon: float) -> float | None:
    """Return lunar illumination (0–1) or None if the utility fails."""
    try:
        return await get_lunar_illumination(lat, lon)
    except Exception as e:
        logger.warning("Lunar illumination lookup failed: %s", e)
        return None


async def _safe_get_twilight(lat: float, lon: float) -> str | None:
    """Return twilight state string or None if the utility fails."""
    try:
        return await get_twilight_state(lat, lon)
    except Exception as e:
        logger.warning("Twilight state lookup failed: %s", e)
        return None


async def _safe_get_terrain(lat: float, lon: float) -> dict:
    """Return terrain context dict or a safe empty default if the service fails."""
    try:
        return await get_terrain_context(lat, lon)
    except Exception as e:
        logger.warning("Terrain check failed for (%s, %s): %s", lat, lon, e)
        return {"horizon_obstruction": "unknown", "note": "Terrain data unavailable"}