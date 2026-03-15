"""
Aurora Window Pro — backend/services/terrain_check.py
======================================================
Terrain and light-pollution context service.

Provides Bortle class estimates, dark-sky suitability scores, and
nearest dark-sky site hints for routing decisions.

Production path: Replace heuristic Bortle estimator with a NOAA VIIRS DNB
GeoTIFF raster lookup (numpy/rasterio). Replace dark-sky sites with the
full IDA GeoJSON database. For MVP, rule-based approximations are used.
"""

import math
import logging
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Known dark-sky sites (IDA-certified subset — MVP placeholder list)
# Format: (name, latitude, longitude, bortle_class, notes)
# In production, load the full IDA GeoJSON from the filesystem or API.
# ---------------------------------------------------------------------------
_DARK_SKY_SITES = [
    ("Galloway Forest Dark Sky Park",          55.1167,  -4.3167,  2, "UK's largest dark sky park"),
    ("Brecon Beacons Dark Sky Reserve",        51.8833,  -3.4333,  3, "Wales — IDA Gold Tier"),
    ("Exmoor Dark Sky Reserve",                51.1500,  -3.7000,  3, "England — first IDA reserve"),
    ("Kerry Dark Sky Reserve",                 51.9500,  -9.8000,  2, "Ireland — Gold Tier"),
    ("NamibRand Nature Reserve",              -25.0000,  16.0000,  1, "Namibia — world-class southern site"),
    ("Aoraki Mackenzie Dark Sky Reserve",     -43.9167, 170.4500,  1, "New Zealand — largest reserve"),
    ("Cherry Springs State Park",              41.6597, -77.8258,  2, "Pennsylvania, USA"),
    ("Natural Bridges National Monument",      37.6069,-110.0001,  2, "Utah, USA — IDA certified"),
    ("Jasper National Park",                   52.8734,-117.9543,  2, "Alberta, Canada"),
    ("Abisko National Park",                   68.3500,  18.8333,  2, "Sweden — prime aurora location"),
    ("Þingvellir National Park",               64.2559, -20.9000,  3, "Iceland — near aurora belt"),
    ("Tromsø Dark Zone (approx)",              69.6489,  18.9551,  3, "Northern Norway — best aurora access"),
    ("Denali National Park",                   63.1148,-151.1926,  1, "Alaska, USA — remote dark skies"),
    ("Big Bend National Park",                 29.1275,-103.2425,  2, "Texas, USA — IDA sanctuary"),
    ("Pic du Midi Dark Sky Reserve",           42.9367,   0.1428,  2, "French Pyrenees"),
    ("Atacama Desert (La Serena area)",       -29.9027, -70.8742,  1, "Chile — driest, clearest skies"),
]


# ===========================================================================
# Primary public function
# ===========================================================================

async def get_terrain_context(latitude: float, longitude: float) -> dict:
    """
    Return a full terrain and light-pollution context dict for a given location.

    Called by visibility_api.py and routing_api.py to enrich responses
    with darkness quality and site suitability information.

    Returns:
        bortle_estimate     (int, 1–9)
        bortle_description  (str)
        terrain_score       (float, 0–100) — higher = better for aurora obs
        suitability_label   (str) — "Excellent" / "Good" / "Fair" / "Poor"
        horizon_obstruction (str) — "low" / "moderate" / "high" (heuristic)
        elevation_note      (str) — rough elevation tier from latitude proxy
        nearest_dark_site   (dict | None) — closest IDA-style dark sky site
        notes               (list of str) — human-readable context notes
    """
    bortle     = estimate_bortle_class(latitude, longitude)
    terrain_sc = _bortle_to_terrain_score(bortle)
    suitability = _suitability_label(terrain_sc)
    horizon    = _estimate_horizon_obstruction(latitude, longitude)
    elev_note  = _elevation_note(latitude)
    dark_site  = find_nearest_dark_sky_site(latitude, longitude)
    notes      = _generate_notes(latitude, longitude, bortle, horizon, dark_site)

    return {
        "bortle_estimate":    bortle,
        "bortle_description": _bortle_description(bortle),
        "terrain_score":      round(terrain_sc, 1),
        "suitability_label":  suitability,
        "horizon_obstruction": horizon,
        "elevation_note":     elev_note,
        "nearest_dark_site":  dark_site,
        "notes":              notes,
    }


# ===========================================================================
# Bortle class estimator
# ===========================================================================

def estimate_bortle_class(latitude: float, longitude: float) -> int:
    """
    Estimate Bortle sky darkness class (1–9) for a lat/lon.

    Method: two-factor heuristic combining:
        1. Latitude band — high latitudes are less populated, darker skies.
        2. Longitude proximity to known high-density population corridors.

    Production upgrade: replace with a NOAA VIIRS DNB GeoTIFF raster lookup
    using rasterio.open() + dataset.index() + dataset.read() at the queried
    coordinate. The raster encodes radiance values that map directly to Bortle.

    Bortle scale reference (PS Section 4.3):
        1 — Exceptional dark sky (zodiacal light, faint airglow visible)
        2 — Truly dark sky
        3 — Rural sky
        4 — Rural/suburban transition (routing threshold in config.py)
        5 — Suburban sky
        6 — Bright suburban
        7 — Suburban/urban transition
        8 — City sky
        9 — Inner city
    """
    abs_lat = abs(latitude)

    # --- Latitude band baseline ---
    if abs_lat >= 72:
        base = 2   # Arctic / Antarctic — very sparsely populated
    elif abs_lat >= 65:
        base = 3   # Sub-Arctic (Scandinavia, Alaska, northern Canada)
    elif abs_lat >= 58:
        base = 4   # Northern Europe, central Canada
    elif abs_lat >= 50:
        base = 5   # Central/Western Europe, northern US
    elif abs_lat >= 40:
        base = 6   # Southern Europe, central US, Japan corridor
    elif abs_lat >= 30:
        base = 7   # Mediterranean, southern US, China coastal
    elif abs_lat >= 15:
        base = 8   # Tropical belt — dense population in many regions
    else:
        base = 7   # Equatorial — varies widely; moderate default

    # --- Longitude penalty: proximity to high-density urban corridors ---
    # Northeast US corridor (Boston–NYC–DC): lon roughly –74 to –70, lat 40–42
    if 40 <= latitude <= 42 and -74 <= longitude <= -70:
        base = min(9, base + 2)

    # Western European core (Netherlands, Belgium, Germany): lon 4–15, lat 50–54
    elif 50 <= latitude <= 54 and 4 <= longitude <= 15:
        base = min(9, base + 1)

    # Eastern China coastal: lon 117–122, lat 30–40
    elif 30 <= latitude <= 40 and 117 <= longitude <= 122:
        base = min(9, base + 2)

    # Indian subcontinent densely populated belt: lon 72–88, lat 22–28
    elif 22 <= latitude <= 28 and 72 <= longitude <= 88:
        base = min(9, base + 2)

    # UK (England and Wales): mostly suburban
    elif 51 <= latitude <= 54 and -4 <= longitude <= 2:
        base = min(9, base + 1)

    # Clamp to valid Bortle range
    return max(1, min(9, base))


def _bortle_description(bortle: int) -> str:
    descriptions = {
        1: "Exceptional dark sky — zodiacal light and airglow visible to naked eye",
        2: "Truly dark sky — Milky Way structure is stunning, M33 visible",
        3: "Rural sky — some light domes on horizon, excellent aurora conditions",
        4: "Rural/suburban transition — Milky Way clear, slight horizon glow",
        5: "Suburban sky — Milky Way washed out toward horizon",
        6: "Bright suburban sky — only best parts of Milky Way visible",
        7: "Suburban/urban transition — Milky Way barely detectable",
        8: "City sky — only bright star clusters visible",
        9: "Inner city sky — only brightest stars visible, severe light pollution",
    }
    return descriptions.get(max(1, min(9, bortle)), f"Bortle Class {bortle}")


# ===========================================================================
# Terrain scoring
# ===========================================================================

def _bortle_to_terrain_score(bortle: int) -> float:
    """
    Convert Bortle class to a 0–100 terrain score.
    Linear inversion: Bortle 1 = 100 pts, Bortle 9 = 0 pts.
    Formula: score = (9 - bortle) / 8 × 100
    """
    b = max(1, min(9, bortle))
    return round(((9 - b) / 8.0) * 100.0, 1)


def _suitability_label(terrain_score: float) -> str:
    if terrain_score >= 80: return "Excellent"
    if terrain_score >= 60: return "Good"
    if terrain_score >= 40: return "Fair"
    if terrain_score >= 20: return "Poor"
    return                         "Unsuitable"


# ===========================================================================
# Horizon obstruction heuristic
# ===========================================================================

def _estimate_horizon_obstruction(latitude: float, longitude: float) -> str:
    """
    Estimate horizon obstruction level using a latitude-based heuristic.

    High latitudes → typically open tundra/fjord terrain → low obstruction.
    Mid latitudes → forests and hills are common → moderate.
    Lower latitudes → urban sprawl, vegetation density → moderate to high.

    Production upgrade: use a DEM (Digital Elevation Model) such as SRTM or
    Copernicus DEM to compute horizon angle profiles at 360° around the point.
    """
    abs_lat = abs(latitude)
    if abs_lat >= 65:
        return "low"         # Open Arctic/Antarctic terrain
    if abs_lat >= 50:
        return "moderate"    # Mixed — forests, gentle hills
    return "moderate"        # Conservative default for unknown terrain


def _elevation_note(latitude: float) -> str:
    """Rough elevation context based on latitude band."""
    abs_lat = abs(latitude)
    if abs_lat >= 70:
        return "High-latitude coastal or tundra — typically flat, excellent openness."
    if abs_lat >= 60:
        return "Sub-Arctic — mix of fjords, forests, and highlands."
    if abs_lat >= 45:
        return "Mid-latitude — terrain varies widely; mountains possible."
    return "Lower latitude — elevation and terrain vary significantly; local check recommended."


# ===========================================================================
# Nearest dark-sky site finder
# ===========================================================================

def find_nearest_dark_sky_site(
    latitude: float,
    longitude: float,
    max_radius_km: float = 500.0,
) -> dict | None:
    """
    Find the nearest IDA-certified (or equivalent) dark sky site.

    Uses the hardcoded _DARK_SKY_SITES list — a curated subset of globally
    significant dark sky locations. In production, load the full IDA GeoJSON
    dataset from disk or the IDA API and perform a spatial index query.

    Returns None if no site is within max_radius_km.

    Returns dict:
        name            (str)
        latitude        (float)
        longitude       (float)
        bortle_class    (int)
        distance_km     (float)
        bearing_label   (str)   — compass direction from observer
        notes           (str)
    """
    best_site  = None
    best_dist  = float("inf")
    best_bearing = 0.0

    for name, site_lat, site_lon, bortle, note in _DARK_SKY_SITES:
        dist = _haversine_km(latitude, longitude, site_lat, site_lon)
        if dist < best_dist:
            best_dist    = dist
            best_site    = (name, site_lat, site_lon, bortle, note)
            best_bearing = _bearing_deg(latitude, longitude, site_lat, site_lon)

    if best_site is None or best_dist > max_radius_km:
        return None

    name, site_lat, site_lon, bortle, note = best_site
    return {
        "name":          name,
        "latitude":      site_lat,
        "longitude":     site_lon,
        "bortle_class":  bortle,
        "distance_km":   round(best_dist, 1),
        "bearing_label": _bearing_label(best_bearing),
        "notes":         note,
    }


# ===========================================================================
# Human-readable notes generator
# ===========================================================================

def _generate_notes(
    latitude: float,
    longitude: float,
    bortle: int,
    horizon: str,
    dark_site: dict | None,
) -> list[str]:
    """Build a list of human-readable context notes for the location."""
    notes = []

    # Bortle context
    if bortle <= 2:
        notes.append("Outstanding dark sky — minimal light pollution. Ideal aurora photography conditions.")
    elif bortle <= 4:
        notes.append("Good dark sky. Aurora displays will be vivid with minimal light pollution interference.")
    elif bortle <= 6:
        notes.append("Moderate light pollution. Strong aurora displays will still be visible and photogenic.")
    else:
        notes.append(
            "Significant light pollution at this location. "
            "Consider driving to a darker site for aurora photography."
        )

    # Latitude aurora context
    abs_lat = abs(latitude)
    if abs_lat >= 65:
        notes.append("Location is within the primary auroral oval zone — excellent geographic position.")
    elif abs_lat >= 55:
        notes.append("Location is in the extended auroral viewing zone during moderate to strong storms (Kp ≥ 5).")
    elif abs_lat >= 48:
        notes.append("Aurora visible here only during severe geomagnetic storms (Kp ≥ 7–8).")
    else:
        notes.append("Location is far from the auroral oval. Only extreme events (Kp 9) may produce aurora here.")

    # Horizon note
    if horizon == "low":
        notes.append("Open horizon expected — good all-round sky access for wide-angle aurora photography.")
    else:
        notes.append("Moderate horizon obstruction possible. Scout your local site for best sky access.")

    # Nearest dark sky site
    if dark_site:
        notes.append(
            f"Nearest dark sky site: {dark_site['name']} "
            f"({dark_site['distance_km']} km {dark_site['bearing_label']}, "
            f"Bortle {dark_site['bortle_class']})."
        )

    return notes


# ===========================================================================
# Geometry helpers (no GIS library needed)
# ===========================================================================

def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres between two lat/lon points."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi       = math.radians(lat2 - lat1)
    dlambda    = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial compass bearing in degrees (0–360) from point 1 to point 2."""
    phi1     = math.radians(lat1)
    phi2     = math.radians(lat2)
    dlambda  = math.radians(lon2 - lon1)
    x = math.sin(dlambda) * math.cos(phi2)
    y = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlambda)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def _bearing_label(bearing: float) -> str:
    directions = ["N","NNE","NE","ENE","E","ESE","SE","SSE",
                  "S","SSW","SW","WSW","W","WNW","NW","NNW"]
    return directions[round(bearing / 22.5) % 16]