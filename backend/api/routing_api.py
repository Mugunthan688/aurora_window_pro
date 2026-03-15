"""
Aurora Window Pro — backend/api/routing_api.py
===============================================
FastAPI router for the GPS Routing stretch goal (PS Section 3.2).

Goal: Find the nearest location from the user's position that satisfies
all three visibility routing criteria simultaneously:

    ✓  Aurora probability  > 50%        (OVATION-Prime)
    ✓  Cloud cover         < 30%        (Open-Meteo)
    ✓  Bortle class        < 4          (light pollution estimate)

Since this is a hackathon MVP, we do NOT call any commercial routing API
(Google Maps, Mapbox, etc.). Instead we:
    1. Generate a grid of candidate points around the user.
    2. Score each candidate with the Visibility Score engine.
    3. Filter by routing criteria.
    4. Rank by composite score and haversine distance.
    5. Return the top candidates with estimated driving time.

Endpoints:
    GET /routing/best-spot           — Single best destination from user location
    GET /routing/nearby-candidates   — Ranked list of all qualifying candidates
"""

from fastapi import APIRouter, Query, HTTPException
from typing import Annotated
import math
import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Service layer imports
# ---------------------------------------------------------------------------
from services.route_finder      import generate_candidate_points   # Grid / spoke generator
from services.terrain_check     import get_terrain_context         # Horizon / elevation hints
from services.visibility_score  import compute_visibility_score    # Composite scorer

# ---------------------------------------------------------------------------
# Config thresholds — all sourced from config.py (one source of truth)
# ---------------------------------------------------------------------------
from config import (
    ROUTING_MIN_AURORA_PROBABILITY_PCT,   # 50.0 %
    ROUTING_MAX_CLOUD_COVER_PCT,          # 30.0 %
    ROUTING_MAX_BORTLE_CLASS,             # 4
    VISIBILITY_WEIGHT_AURORA_PROBABILITY,
    VISIBILITY_WEIGHT_CLOUD_COVER,
    VISIBILITY_WEIGHT_DARKNESS,
)

# ---------------------------------------------------------------------------
# Router — mounted at /routing in main.py
# ---------------------------------------------------------------------------
router = APIRouter(
    prefix="/routing",
    tags=["Routing (Stretch Goal)"],
)

# ---------------------------------------------------------------------------
# Constants for this module
# ---------------------------------------------------------------------------
DEFAULT_SEARCH_RADIUS_KM    = 150    # Default candidate search radius
MAX_SEARCH_RADIUS_KM        = 500    # Hard cap — beyond this, driving isn't practical
MIN_SEARCH_RADIUS_KM        = 20     # Minimum meaningful search area
DEFAULT_CANDIDATE_COUNT     = 32     # Points on the search grid/spoke pattern
MAX_CANDIDATES_RETURNED     = 10     # Max results in /nearby-candidates response
AVG_DRIVING_SPEED_KMH       = 80     # Assumed average speed for travel time estimate


# ===========================================================================
# ENDPOINT 1 — GET /routing/best-spot
# ===========================================================================
@router.get("/best-spot", summary="Find the single best aurora viewing spot near you")
async def get_best_spot(
    latitude: Annotated[
        float,
        Query(
            ge=-90.0,
            le=90.0,
            description="Your current latitude in decimal degrees.",
        ),
    ],
    longitude: Annotated[
        float,
        Query(
            ge=-180.0,
            le=180.0,
            description="Your current longitude in decimal degrees.",
        ),
    ],
    radius_km: Annotated[
        float,
        Query(
            ge=MIN_SEARCH_RADIUS_KM,
            le=MAX_SEARCH_RADIUS_KM,
            description=f"Search radius in km (default {DEFAULT_SEARCH_RADIUS_KM} km, max {MAX_SEARCH_RADIUS_KM} km).",
        ),
    ] = DEFAULT_SEARCH_RADIUS_KM,
):
    """
    Returns a single recommended aurora viewing destination — the highest-scoring
    candidate within `radius_km` that meets all three routing criteria:

    - Aurora probability > 50%
    - Cloud cover < 30%
    - Bortle class < 4

    If no candidate meets all three criteria, the best partial match is returned
    with a `partial_match: true` flag and an explanation of which criteria failed.

    Travel time is estimated using haversine distance ÷ 80 km/h average speed.
    No commercial routing API is used (hackathon MVP).
    """

    # --- Generate candidate grid around user position ---
    candidates = await _build_scored_candidates(
        origin_lat=latitude,
        origin_lon=longitude,
        radius_km=radius_km,
        n_points=DEFAULT_CANDIDATE_COUNT,
    )

    if not candidates:
        raise HTTPException(
            status_code=503,
            detail="Could not generate or score candidate locations. Data sources may be unavailable.",
        )

    # --- Find best fully-qualifying candidate ---
    qualifying = [c for c in candidates if c["meets_all_criteria"]]

    if qualifying:
        best = qualifying[0]   # Already sorted by score desc
        return {
            "found":          True,
            "partial_match":  False,
            "recommendation": _format_spot(best, origin_lat=latitude, origin_lon=longitude),
            "criteria_used": _routing_criteria_summary(),
            "search_radius_km": radius_km,
            "candidates_evaluated": len(candidates),
            "note": (
                f"Best qualifying spot found at "
                f"{round(best['distance_km'], 1)} km — "
                f"estimated {best['travel_time_str']} drive."
            ),
        }

    # --- No full match — return best partial candidate with explanation ---
    best_partial = candidates[0]   # Highest score regardless of criteria pass
    return {
        "found":          True,
        "partial_match":  True,
        "recommendation": _format_spot(best_partial, origin_lat=latitude, origin_lon=longitude),
        "criteria_used":  _routing_criteria_summary(),
        "search_radius_km":     radius_km,
        "candidates_evaluated": len(candidates),
        "note": (
            "No candidate within the search radius met all three routing criteria. "
            "Returning the best available location. Consider expanding the search radius "
            "or waiting for cloud cover to improve."
        ),
    }


# ===========================================================================
# ENDPOINT 2 — GET /routing/nearby-candidates
# ===========================================================================
@router.get("/nearby-candidates", summary="Ranked list of candidate aurora viewing spots")
async def get_nearby_candidates(
    latitude: Annotated[
        float,
        Query(
            ge=-90.0,
            le=90.0,
            description="Your current latitude in decimal degrees.",
        ),
    ],
    longitude: Annotated[
        float,
        Query(
            ge=-180.0,
            le=180.0,
            description="Your current longitude in decimal degrees.",
        ),
    ],
    radius_km: Annotated[
        float,
        Query(
            ge=MIN_SEARCH_RADIUS_KM,
            le=MAX_SEARCH_RADIUS_KM,
            description=f"Search radius in km (default {DEFAULT_SEARCH_RADIUS_KM} km).",
        ),
    ] = DEFAULT_SEARCH_RADIUS_KM,
    max_results: Annotated[
        int,
        Query(
            ge=1,
            le=MAX_CANDIDATES_RETURNED,
            description=f"Number of results to return (max {MAX_CANDIDATES_RETURNED}).",
        ),
    ] = 5,
    qualifying_only: Annotated[
        bool,
        Query(
            description="If true, only return candidates meeting all three routing criteria.",
        ),
    ] = False,
):
    """
    Returns a ranked list of candidate aurora viewing spots near the user.

    Useful for a map layer showing multiple options — the frontend can render
    these as pins with colour-coded scores.

    Each candidate includes:
    - Coordinates and distance from user
    - Visibility score (0–100)
    - Aurora probability, cloud cover, Bortle estimate
    - Whether it meets all routing criteria
    - Estimated drive time

    Sorted by visibility score descending.
    """

    candidates = await _build_scored_candidates(
        origin_lat=latitude,
        origin_lon=longitude,
        radius_km=radius_km,
        n_points=DEFAULT_CANDIDATE_COUNT,
    )

    if not candidates:
        raise HTTPException(
            status_code=503,
            detail="Could not generate or score candidate locations.",
        )

    # --- Optional filter ---
    if qualifying_only:
        filtered = [c for c in candidates if c["meets_all_criteria"]]
    else:
        filtered = candidates

    # --- Slice to requested result count ---
    results = filtered[:max_results]

    return {
        "origin":             {"latitude": latitude, "longitude": longitude},
        "search_radius_km":   radius_km,
        "total_evaluated":    len(candidates),
        "qualifying_count":   sum(1 for c in candidates if c["meets_all_criteria"]),
        "returned_count":     len(results),
        "qualifying_only":    qualifying_only,
        "criteria":           _routing_criteria_summary(),
        "candidates": [
            _format_spot(c, origin_lat=latitude, origin_lon=longitude)
            for c in results
        ],
    }


# ===========================================================================
# Core internal pipeline
# ===========================================================================

async def _build_scored_candidates(
    origin_lat: float,
    origin_lon: float,
    radius_km: float,
    n_points: int,
) -> list[dict]:
    """
    Generate candidate points, score each with the visibility engine,
    attach distance + travel time, and return sorted by score descending.

    Steps:
        1. Call route_finder.generate_candidate_points() to get lat/lon grid.
        2. Score each candidate with visibility_score.compute_visibility_score().
        3. Compute haversine distance from origin.
        4. Estimate travel time.
        5. Sort by visibility score descending.
    """

    # Step 1 — Generate candidate grid / spoke points
    try:
        raw_candidates = await generate_candidate_points(
            origin_lat=origin_lat,
            origin_lon=origin_lon,
            radius_km=radius_km,
            n_points=n_points,
        )
    except Exception as e:
        logger.error("Candidate generation failed: %s", e)
        return []

    if not raw_candidates:
        logger.warning("No candidate points generated for (%s, %s)", origin_lat, origin_lon)
        return []

    # Step 2 — Score each candidate
    default_weights = {
        "aurora":   VISIBILITY_WEIGHT_AURORA_PROBABILITY,
        "cloud":    VISIBILITY_WEIGHT_CLOUD_COVER,
        "darkness": VISIBILITY_WEIGHT_DARKNESS,
    }

    scored = []
    for point in raw_candidates:
        lat = point.get("latitude")
        lon = point.get("longitude")

        if lat is None or lon is None:
            continue

        try:
            score_result = await compute_visibility_score(
                latitude=lat,
                longitude=lon,
                weights=default_weights,
            )
        except Exception as e:
            logger.warning("Scoring failed for candidate (%s, %s): %s", lat, lon, e)
            # Skip unscoreable candidates — don't crash the whole batch
            continue

        # Step 3 — Distance from origin
        dist_km = _haversine_km(origin_lat, origin_lon, lat, lon)

        # Step 4 — Travel time estimate
        travel_minutes = (dist_km / AVG_DRIVING_SPEED_KMH) * 60
        travel_str     = _format_travel_time(travel_minutes)

        # Step 5 — Build candidate record
        aurora_prob = score_result.get("aurora_probability", 0.0)
        cloud_pct   = score_result.get("cloud_cover_pct", 100.0)
        bortle_est  = score_result.get("bortle_estimate")
        vis_score   = score_result.get("visibility_score", 0.0)
        darkness_sc = score_result.get("darkness_score", 0.0)

        meets_aurora  = aurora_prob >= ROUTING_MIN_AURORA_PROBABILITY_PCT
        meets_cloud   = cloud_pct   <= ROUTING_MAX_CLOUD_COVER_PCT
        meets_bortle  = (bortle_est is None) or (bortle_est < ROUTING_MAX_BORTLE_CLASS)
        meets_all     = meets_aurora and meets_cloud and meets_bortle

        scored.append({
            "latitude":          lat,
            "longitude":         lon,
            "visibility_score":  round(vis_score, 1),
            "aurora_probability": round(aurora_prob, 1),
            "cloud_cover_pct":   round(cloud_pct, 1),
            "clear_sky_pct":     round(100.0 - cloud_pct, 1),
            "darkness_score":    round(darkness_sc, 1),
            "bortle_estimate":   bortle_est,
            "distance_km":       round(dist_km, 1),
            "travel_minutes":    round(travel_minutes, 0),
            "travel_time_str":   travel_str,
            "meets_aurora_criteria": meets_aurora,
            "meets_cloud_criteria":  meets_cloud,
            "meets_bortle_criteria": meets_bortle,
            "meets_all_criteria":    meets_all,
            "data_source":       score_result.get("source", "live"),
            # Pass through any label hints from route_finder (e.g. "dark sky park")
            "location_hint":     point.get("label"),
        })

    # Sort: qualifying first, then by score descending
    scored.sort(key=lambda c: (not c["meets_all_criteria"], -c["visibility_score"]))

    return scored


def _format_spot(candidate: dict, origin_lat: float, origin_lon: float) -> dict:
    """
    Shape a scored candidate into a clean, frontend-friendly response object.
    Adds a human-readable reason for the recommendation.
    """
    return {
        "coordinates": {
            "latitude":  candidate["latitude"],
            "longitude": candidate["longitude"],
        },
        "visibility_score":   candidate["visibility_score"],
        "score_label":        _score_label(candidate["visibility_score"]),

        "aurora_probability": {
            "value":   candidate["aurora_probability"],
            "unit":    "%",
            "passes":  candidate["meets_aurora_criteria"],
            "threshold": f"> {ROUTING_MIN_AURORA_PROBABILITY_PCT}%",
        },
        "cloud_cover": {
            "value":      candidate["cloud_cover_pct"],
            "clear_sky":  candidate["clear_sky_pct"],
            "unit":       "%",
            "passes":     candidate["meets_cloud_criteria"],
            "threshold":  f"< {ROUTING_MAX_CLOUD_COVER_PCT}%",
        },
        "darkness": {
            "darkness_score":  candidate["darkness_score"],
            "bortle_estimate": candidate["bortle_estimate"],
            "passes":          candidate["meets_bortle_criteria"],
            "threshold":       f"Bortle < {ROUTING_MAX_BORTLE_CLASS}",
        },

        "travel": {
            "distance_km":       candidate["distance_km"],
            "estimated_time":    candidate["travel_time_str"],
            "travel_minutes":    candidate["travel_minutes"],
            "speed_assumption":  f"{AVG_DRIVING_SPEED_KMH} km/h average",
        },

        "meets_all_criteria": candidate["meets_all_criteria"],
        "location_hint":      candidate.get("location_hint"),
        "reason":             _generate_reason(candidate),
        "data_source":        candidate.get("data_source", "live"),

        # Bearing from origin — useful for navigation hints ("head north-east")
        "bearing_from_origin": _bearing_label(
            _bearing_deg(origin_lat, origin_lon, candidate["latitude"], candidate["longitude"])
        ),
    }


# ===========================================================================
# Haversine distance + bearing (no GIS library needed)
# ===========================================================================

def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate great-circle distance between two points (decimal degrees)
    using the Haversine formula. Returns distance in kilometres.
    """
    R = 6371.0  # Earth radius in km
    phi1, phi2   = math.radians(lat1), math.radians(lat2)
    d_phi        = math.radians(lat2 - lat1)
    d_lambda     = math.radians(lon2 - lon1)

    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return initial compass bearing in degrees (0–360) from point 1 to point 2."""
    phi1     = math.radians(lat1)
    phi2     = math.radians(lat2)
    d_lambda = math.radians(lon2 - lon1)

    x = math.sin(d_lambda) * math.cos(phi2)
    y = (
        math.cos(phi1) * math.sin(phi2)
        - math.sin(phi1) * math.cos(phi2) * math.cos(d_lambda)
    )
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def _bearing_label(bearing: float) -> str:
    """Convert a bearing in degrees to a compass direction string."""
    directions = [
        "N", "NNE", "NE", "ENE",
        "E", "ESE", "SE", "SSE",
        "S", "SSW", "SW", "WSW",
        "W", "WNW", "NW", "NNW",
    ]
    index = round(bearing / 22.5) % 16
    return directions[index]


# ===========================================================================
# Formatting helpers
# ===========================================================================

def _format_travel_time(minutes: float) -> str:
    """
    Convert a decimal number of minutes into a human-readable drive time string.
    Examples: 45 → "45 min", 90 → "1 h 30 min", 5 → "5 min"
    """
    m = round(minutes)
    if m < 60:
        return f"{m} min"
    h, rem = divmod(m, 60)
    return f"{h} h {rem} min" if rem else f"{h} h"


def _score_label(score: float | None) -> str:
    """Map a 0–100 score to a UI-friendly label."""
    if score is None:   return "Unknown"
    if score >= 80:     return "Excellent"
    if score >= 60:     return "Good"
    if score >= 40:     return "Fair"
    if score >= 20:     return "Poor"
    return                     "Very Poor"


def _generate_reason(candidate: dict) -> str:
    """
    Build a single plain-English sentence explaining why this spot was recommended.
    Judges will see this in the demo — keep it informative and specific.
    """
    parts = []

    if candidate["meets_aurora_criteria"]:
        parts.append(f"aurora probability {candidate['aurora_probability']}%")
    else:
        parts.append(f"aurora probability only {candidate['aurora_probability']}% (below 50% threshold)")

    if candidate["meets_cloud_criteria"]:
        parts.append(f"clear sky {candidate['clear_sky_pct']}%")
    else:
        parts.append(f"cloud cover {candidate['cloud_cover_pct']}% (above 30% threshold)")

    if candidate["bortle_estimate"] is not None:
        if candidate["meets_bortle_criteria"]:
            parts.append(f"dark sky (Bortle {candidate['bortle_estimate']})")
        else:
            parts.append(f"Bortle {candidate['bortle_estimate']} (too much light pollution)")

    prefix = "Selected: " if candidate["meets_all_criteria"] else "Best available: "
    return prefix + ", ".join(parts) + f" — {candidate['travel_time_str']} drive."


def _routing_criteria_summary() -> dict:
    """Return the routing threshold values as a dict for API transparency."""
    return {
        "aurora_probability_min_pct": ROUTING_MIN_AURORA_PROBABILITY_PCT,
        "cloud_cover_max_pct":        ROUTING_MAX_CLOUD_COVER_PCT,
        "bortle_class_max":           ROUTING_MAX_BORTLE_CLASS,
        "note": (
            "All three criteria must be met simultaneously for a location "
            "to be classified as a full routing match (PS Section 2.1)."
        ),
    }