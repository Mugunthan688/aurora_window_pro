"""
Aurora Window Pro — backend/services/route_finder.py
=====================================================
Stretch-goal routing service (PS Section 3.2).

Generates candidate viewing spots around the user, scores each against the
three routing criteria, and returns the best qualifying location.

Routing criteria (from config.py / PS Section 2.1):
    ✓ Aurora probability  > 50%  (OVATION-Prime)
    ✓ Cloud cover         < 30%  (Open-Meteo)
    ✓ Bortle class        < 4    (light pollution heuristic)

No commercial navigation API is used. Candidates are generated on a
spoke-and-ring grid around the user, scored, and ranked by a weighted
composite that balances visibility quality against driving distance.
"""

import math
import logging
from services.ovation_parser   import get_ovation_probability
from services.visibility_score import fetch_open_meteo_weather
from services.terrain_check    import estimate_bortle_class
from config import (
    ROUTING_MIN_AURORA_PROBABILITY_PCT,
    ROUTING_MAX_CLOUD_COVER_PCT,
    ROUTING_MAX_BORTLE_CLASS,
    AVG_DRIVING_SPEED_KMH,
)

logger = logging.getLogger(__name__)

# Composite score weights inside the route ranker
# Visibility quality matters more than distance for aurora chasing.
_WEIGHT_VISIBILITY = 0.70
_WEIGHT_PROXIMITY  = 0.30

AVG_DRIVING_SPEED_KMH = 80   # km/h — used for travel time estimate


# ===========================================================================
# Public function — called by routing_api.py
# ===========================================================================

async def generate_candidate_points(
    origin_lat: float,
    origin_lon: float,
    radius_km: float = 150.0,
    n_points:  int   = 32,
) -> list[dict]:
    """
    Generate a spoke-and-ring grid of candidate lat/lon points around the
    user's position, then score each against the routing criteria.

    Grid layout:
        • Inner ring  — radius/3,  n_points//2 evenly-spaced bearings
        • Outer ring  — radius,    n_points    evenly-spaced bearings
        + 8 cardinal/intercardinal compass points at full radius

    This gives ~50+ candidate points covering all directions at two ranges.

    Returns a list of candidate dicts (unsorted — routing_api.py sorts them).
    Each dict contains all data needed by routing_api.py to build a response.
    """
    raw_points = _generate_grid(origin_lat, origin_lon, radius_km, n_points)

    # Deduplicate by rounding to 1° — avoids scoring identical ocean/tundra cells
    seen   = set()
    unique = []
    for p in raw_points:
        key = (round(p["latitude"], 1), round(p["longitude"], 1))
        if key not in seen:
            seen.add(key)
            unique.append(p)

    # Score each candidate (IO-bound — each needs weather + OVATION lookup)
    scored = []
    for point in unique:
        candidate = await _score_candidate(
            origin_lat, origin_lon,
            point["latitude"], point["longitude"],
            point.get("label"),
            radius_km,
        )
        if candidate is not None:
            scored.append(candidate)

    return scored


# ===========================================================================
# Grid generation
# ===========================================================================

def _generate_grid(
    origin_lat: float,
    origin_lon: float,
    radius_km: float,
    n_points: int,
) -> list[dict]:
    """
    Return a list of raw {latitude, longitude, label} dicts on a
    spoke-and-ring pattern around the origin.
    """
    points = []

    # --- Inner ring (radius / 3) ---
    inner_radius = radius_km / 3.0
    inner_count  = max(8, n_points // 2)
    for i in range(inner_count):
        bearing = (360.0 / inner_count) * i
        lat, lon = _offset_point(origin_lat, origin_lon, inner_radius, bearing)
        points.append({"latitude": lat, "longitude": lon, "label": None})

    # --- Outer ring (full radius) ---
    for i in range(n_points):
        bearing = (360.0 / n_points) * i
        lat, lon = _offset_point(origin_lat, origin_lon, radius_km, bearing)
        points.append({"latitude": lat, "longitude": lon, "label": None})

    # --- 8 cardinal/intercardinal anchor points at full radius ---
    # These ensure we always probe N, NE, E, SE, S, SW, W, NW directions.
    for bearing, label in [
        (0,   "North"),   (45,  "Northeast"), (90,  "East"),  (135, "Southeast"),
        (180, "South"),   (225, "Southwest"), (270, "West"),  (315, "Northwest"),
    ]:
        lat, lon = _offset_point(origin_lat, origin_lon, radius_km, bearing)
        points.append({"latitude": lat, "longitude": lon, "label": label})

    return points


def _offset_point(
    lat: float, lon: float, distance_km: float, bearing_deg: float
) -> tuple[float, float]:
    """
    Return a new (lat, lon) reached by travelling `distance_km` km from
    (lat, lon) at `bearing_deg` degrees (0 = north, 90 = east).

    Uses the spherical-Earth direct-point formula.
    """
    R   = 6371.0
    lat1 = math.radians(lat)
    lon1 = math.radians(lon)
    brng = math.radians(bearing_deg)
    d_R  = distance_km / R

    lat2 = math.asin(
        math.sin(lat1) * math.cos(d_R)
        + math.cos(lat1) * math.sin(d_R) * math.cos(brng)
    )
    lon2 = lon1 + math.atan2(
        math.sin(brng) * math.sin(d_R) * math.cos(lat1),
        math.cos(d_R) - math.sin(lat1) * math.sin(lat2),
    )
    return round(math.degrees(lat2), 4), round(math.degrees(lon2), 4)


# ===========================================================================
# Candidate scoring
# ===========================================================================

async def _score_candidate(
    origin_lat: float,
    origin_lon: float,
    cand_lat:   float,
    cand_lon:   float,
    label:      str | None,
    max_radius_km: float,
) -> dict | None:
    """
    Fetch real-time data for a candidate point and compute a routing score.

    Returns None if data fetching fails entirely (candidate is skipped).
    """
    try:
        # --- Aurora probability from OVATION grid ---
        ovation  = await get_ovation_probability(cand_lat, cand_lon)
        aurora_p = ovation.get("aurora_probability", 0.0) or 0.0

        # --- Cloud cover from Open-Meteo ---
        weather  = await fetch_open_meteo_weather(cand_lat, cand_lon)
        cloud_p  = weather.get("cloud_cover_pct", 50.0)

        # --- Bortle estimate (heuristic) ---
        bortle   = estimate_bortle_class(cand_lat, cand_lon)

        # --- Routing criteria pass/fail ---
        passes_aurora  = aurora_p >= ROUTING_MIN_AURORA_PROBABILITY_PCT
        passes_cloud   = cloud_p  <= ROUTING_MAX_CLOUD_COVER_PCT
        passes_bortle  = bortle   <  ROUTING_MAX_BORTLE_CLASS
        meets_all      = passes_aurora and passes_cloud and passes_bortle

        # --- Distance and travel time ---
        dist_km        = _haversine_km(origin_lat, origin_lon, cand_lat, cand_lon)
        travel_min     = (dist_km / AVG_DRIVING_SPEED_KMH) * 60

        # --- Composite routing score (0–100) ---
        # Visibility quality (70%) + proximity bonus (30%)
        visibility_score = _compute_visibility_score(aurora_p, cloud_p, bortle)
        proximity_score  = _proximity_score(dist_km, max_radius_km)
        routing_score    = (
            visibility_score * _WEIGHT_VISIBILITY
            + proximity_score  * _WEIGHT_PROXIMITY
        )

        return {
            "latitude":          cand_lat,
            "longitude":         cand_lon,
            "label":             label,
            "aurora_probability": round(aurora_p, 1),
            "cloud_cover_pct":   round(cloud_p, 1),
            "clear_sky_pct":     round(100.0 - cloud_p, 1),
            "bortle_estimate":   bortle,
            "distance_km":       round(dist_km, 1),
            "travel_minutes":    round(travel_min, 0),
            "travel_time_str":   _format_travel_time(travel_min),
            "visibility_score":  round(visibility_score, 1),
            "proximity_score":   round(proximity_score, 1),
            "routing_score":     round(routing_score, 1),
            "meets_aurora_criteria": passes_aurora,
            "meets_cloud_criteria":  passes_cloud,
            "meets_bortle_criteria": passes_bortle,
            "meets_all_criteria":    meets_all,
            "data_source":       ovation.get("source", "live"),
        }

    except Exception as e:
        logger.warning("Candidate scoring failed for (%s, %s): %s", cand_lat, cand_lon, e)
        return None


# ===========================================================================
# Scoring helpers
# ===========================================================================

def _compute_visibility_score(
    aurora_prob: float, cloud_pct: float, bortle: int
) -> float:
    """
    Simplified 3-factor visibility score for routing purposes.
    Weights: aurora 50%, cloud clarity 30%, darkness 20%.
    """
    aurora_score   = math.sqrt(max(0.0, aurora_prob) / 100.0) * 100.0
    clarity_score  = 100.0 - max(0.0, min(100.0, cloud_pct))
    darkness_score = ((9 - max(1, min(9, bortle))) / 8.0) * 100.0

    return round(
        aurora_score   * 0.50
        + clarity_score  * 0.30
        + darkness_score * 0.20,
        2,
    )


def _proximity_score(dist_km: float, max_radius_km: float) -> float:
    """
    Convert distance from origin to a 0–100 proximity score.
    Closer candidates score higher — linearly scaled to the search radius.
    """
    if max_radius_km <= 0:
        return 100.0
    return round(max(0.0, (1.0 - dist_km / max_radius_km) * 100.0), 2)


# ===========================================================================
# Geometry + formatting helpers
# ===========================================================================

def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R    = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a    = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _format_travel_time(minutes: float) -> str:
    m = round(minutes)
    if m < 60:
        return f"{m} min"
    h, rem = divmod(m, 60)
    return f"{h} h {rem} min" if rem else f"{h} h"