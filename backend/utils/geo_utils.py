"""
AuroraWindow Pro — Geographic Utility Functions
Reusable helper functions for coordinate math, distance calculation,
travel time estimation, and location labelling.

No external GIS libraries needed — pure Python math only.
All functions are small, focused, and beginner-friendly.
"""

import math
from typing import Tuple, Optional

# ─── Constants ────────────────────────────────────────────────────────────────

EARTH_RADIUS_KM   = 6371.0    # mean radius of Earth in kilometres
AVERAGE_SPEED_KMH = 60.0      # assumed average driving speed in km/h
DRIVE_BUFFER_MIN  = 10        # extra minutes added for parking + walking

# ─── Coordinate Validation ────────────────────────────────────────────────────

def is_valid_coordinate(lat: float, lon: float) -> bool:
    """
    Checks whether a latitude/longitude pair is within valid ranges.

    Valid ranges:
      Latitude:  -90.0  to  90.0  degrees
      Longitude: -180.0 to 180.0  degrees

    Args:
        lat: Latitude in decimal degrees
        lon: Longitude in decimal degrees

    Returns:
        True if both values are within valid range, False otherwise.

    Example:
        >>> is_valid_coordinate(55.95, -3.19)
        True
        >>> is_valid_coordinate(999.0, 0.0)
        False
    """
    return -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0


def is_valid_latitude(lat: float) -> bool:
    """
    Checks whether a latitude value is valid.

    Args:
        lat: Latitude in decimal degrees

    Returns:
        True if -90.0 <= lat <= 90.0
    """
    return -90.0 <= lat <= 90.0


def is_valid_longitude(lon: float) -> bool:
    """
    Checks whether a longitude value is valid.

    Args:
        lon: Longitude in decimal degrees

    Returns:
        True if -180.0 <= lon <= 180.0
    """
    return -180.0 <= lon <= 180.0

# ─── Coordinate Normalisation ─────────────────────────────────────────────────

def normalize_latitude(lat: float) -> float:
    """
    Clamps a latitude value to the valid range [-90, 90].

    Useful when computed coordinates slightly exceed valid bounds
    due to floating point arithmetic in spherical geometry.

    Args:
        lat: Raw latitude value

    Returns:
        Clamped latitude in range [-90.0, 90.0]

    Example:
        >>> normalize_latitude(91.5)
        90.0
        >>> normalize_latitude(-95.0)
        -90.0
    """
    return max(-90.0, min(90.0, lat))


def normalize_longitude(lon: float) -> float:
    """
    Wraps a longitude value to the valid range [-180, 180].

    Handles wrap-around at the antimeridian (±180°).
    For example, 181° becomes -179°.

    Args:
        lon: Raw longitude value (may exceed ±180)

    Returns:
        Wrapped longitude in range [-180.0, 180.0]

    Example:
        >>> normalize_longitude(190.0)
        -170.0
        >>> normalize_longitude(-185.0)
        175.0
    """
    # Shift into [0, 360) range then subtract 180
    return ((lon + 180.0) % 360.0) - 180.0


def normalize_lat_lon(lat: float, lon: float) -> Tuple[float, float]:
    """
    Normalises both latitude and longitude in one call.

    Args:
        lat: Raw latitude (will be clamped)
        lon: Raw longitude (will be wrapped)

    Returns:
        Tuple of (normalised_lat, normalised_lon)

    Example:
        >>> normalize_lat_lon(91.0, 185.0)
        (90.0, -175.0)
    """
    return normalize_latitude(lat), normalize_longitude(lon)

# ─── Haversine Distance ───────────────────────────────────────────────────────

def haversine_distance(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    """
    Calculates the great-circle distance between two points on Earth
    using the Haversine formula.

    This gives the shortest distance over the Earth's surface —
    the straight-line "as the crow flies" distance, not road distance.
    Accurate to within ~0.3% for distances up to a few thousand km.

    Args:
        lat1: Latitude of point 1 in decimal degrees
        lon1: Longitude of point 1 in decimal degrees
        lat2: Latitude of point 2 in decimal degrees
        lon2: Longitude of point 2 in decimal degrees

    Returns:
        Distance in kilometres (float, rounded to 2 decimal places)

    Example:
        >>> haversine_distance(51.5, -0.1, 48.8, 2.3)   # London to Paris
        340.56
    """
    # Convert all angles from degrees to radians
    rlat1 = math.radians(lat1)
    rlat2 = math.radians(lat2)
    dlat  = math.radians(lat2 - lat1)
    dlon  = math.radians(lon2 - lon1)

    # Haversine formula
    a = (
        math.sin(dlat / 2) ** 2 +
        math.cos(rlat1) * math.cos(rlat2) *
        math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return round(EARTH_RADIUS_KM * c, 2)


def haversine_distance_m(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    """
    Same as haversine_distance() but returns the result in metres.
    Useful for terrain and elevation comparisons.

    Args:
        lat1, lon1: Origin coordinates
        lat2, lon2: Destination coordinates

    Returns:
        Distance in metres (float)
    """
    return haversine_distance(lat1, lon1, lat2, lon2) * 1000.0

# ─── Bearing / Azimuth ────────────────────────────────────────────────────────

def calculate_bearing(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    """
    Calculates the initial compass bearing (azimuth) from point 1
    to point 2 using the forward azimuth formula.

    A bearing of 0° points North, 90° East, 180° South, 270° West.

    Args:
        lat1, lon1: Origin coordinates in degrees
        lat2, lon2: Destination coordinates in degrees

    Returns:
        Bearing in degrees (0–360), rounded to 1 decimal place.

    Example:
        >>> calculate_bearing(51.5, -0.1, 48.8, 2.3)   # London to Paris
        156.2   # roughly south-southeast
    """
    rlat1 = math.radians(lat1)
    rlat2 = math.radians(lat2)
    dlon  = math.radians(lon2 - lon1)

    x       = math.sin(dlon) * math.cos(rlat2)
    y       = (
        math.cos(rlat1) * math.sin(rlat2) -
        math.sin(rlat1) * math.cos(rlat2) * math.cos(dlon)
    )
    bearing = (math.degrees(math.atan2(x, y)) + 360) % 360

    return round(bearing, 1)


def bearing_to_compass(bearing: float) -> str:
    """
    Converts a bearing in degrees to a 16-point compass label.

    Args:
        bearing: Direction in degrees (0 = North, 90 = East)

    Returns:
        Compass label string, e.g. "N", "NNE", "NW", "SSW"

    Example:
        >>> bearing_to_compass(347.0)
        'NNW'
    """
    directions = [
        "N",   "NNE", "NE",  "ENE",
        "E",   "ESE", "SE",  "SSE",
        "S",   "SSW", "SW",  "WSW",
        "W",   "WNW", "NW",  "NNW",
    ]
    index = round(bearing / 22.5) % 16
    return directions[index]

# ─── Destination Point ────────────────────────────────────────────────────────

def destination_point(
    lat:        float,
    lon:        float,
    bearing:    float,
    distance_km: float,
) -> Tuple[float, float]:
    """
    Calculates the destination point given a start location,
    bearing, and distance using spherical Earth geometry.

    Useful for generating candidate observation points around
    the user's location in a given direction.

    Args:
        lat:         Start latitude in degrees
        lon:         Start longitude in degrees
        bearing:     Direction of travel in degrees (0 = North)
        distance_km: Distance to travel in kilometres

    Returns:
        Tuple of (destination_lat, destination_lon) in degrees

    Example:
        >>> destination_point(55.95, -3.19, 0, 50)   # 50km north of Edinburgh
        (56.40, -3.19)
    """
    rlat     = math.radians(lat)
    rlon     = math.radians(lon)
    rbearing = math.radians(bearing)
    ang_dist = distance_km / EARTH_RADIUS_KM

    dest_lat = math.asin(
        math.sin(rlat) * math.cos(ang_dist) +
        math.cos(rlat) * math.sin(ang_dist) * math.cos(rbearing)
    )
    dest_lon = rlon + math.atan2(
        math.sin(rbearing) * math.sin(ang_dist) * math.cos(rlat),
        math.cos(ang_dist) - math.sin(rlat) * math.sin(dest_lat)
    )

    return (
        round(math.degrees(dest_lat), 6),
        round(normalize_longitude(math.degrees(dest_lon)), 6),
    )

# ─── Travel Time ──────────────────────────────────────────────────────────────

def estimate_travel_time(distance_km: float) -> int:
    """
    Estimates driving time in minutes from a straight-line distance.

    Assumes an average driving speed of 60 km/h on mixed roads,
    plus a 10-minute buffer for parking and walking to the spot.

    Args:
        distance_km: Straight-line distance in kilometres

    Returns:
        Estimated travel time in minutes (int, minimum 5 minutes)

    Example:
        >>> estimate_travel_time(30)
        40    # 30min drive + 10min buffer
    """
    drive_minutes = (distance_km / AVERAGE_SPEED_KMH) * 60.0
    total         = drive_minutes + DRIVE_BUFFER_MIN

    return max(5, round(total))


def format_travel_time(minutes: int) -> str:
    """
    Formats a travel time in minutes into a human-readable string.

    Args:
        minutes: Travel time in minutes

    Returns:
        Formatted string like "25 min" or "1 hr 10 min"

    Example:
        >>> format_travel_time(75)
        '1 hr 15 min'
    """
    if minutes < 60:
        return f"{minutes} min"

    hours   = minutes // 60
    mins    = minutes % 60

    if mins == 0:
        return f"{hours} hr"

    return f"{hours} hr {mins} min"

# ─── Location Label ───────────────────────────────────────────────────────────

def get_location_label(lat: float, lon: float) -> str:
    """
    Returns a simple human-readable location label from coordinates.

    For a full implementation this would reverse-geocode the coordinates.
    For MVP, we return a formatted coordinate string with hemisphere labels.

    Args:
        lat: Latitude in decimal degrees
        lon: Longitude in decimal degrees

    Returns:
        Formatted location string

    Example:
        >>> get_location_label(55.95, -3.19)
        '55.950°N, 3.190°W'
    """
    lat_dir = "N" if lat >= 0 else "S"
    lon_dir = "E" if lon >= 0 else "W"

    return f"{abs(round(lat, 3))}°{lat_dir}, {abs(round(lon, 3))}°{lon_dir}"


def get_hemisphere(lat: float) -> str:
    """
    Returns which hemisphere the latitude is in.

    Args:
        lat: Latitude in decimal degrees

    Returns:
        "northern" or "southern"
    """
    return "northern" if lat >= 0 else "southern"

# ─── Bounding Box ─────────────────────────────────────────────────────────────

def get_bounding_box(
    lat:       float,
    lon:       float,
    radius_km: float,
) -> dict:
    """
    Returns a lat/lon bounding box around a central point
    for a given radius in kilometres.

    Useful for pre-filtering candidate points before
    running the more expensive Haversine calculation.

    Args:
        lat:       Center latitude in degrees
        lon:       Center longitude in degrees
        radius_km: Radius of the bounding box in km

    Returns:
        Dict with min_lat, max_lat, min_lon, max_lon
    """
    # 1 degree of latitude ≈ 111.32 km
    lat_delta = radius_km / 111.32

    # 1 degree of longitude varies with latitude
    lon_delta = radius_km / (111.32 * math.cos(math.radians(lat)))

    return {
        "min_lat": normalize_latitude(lat  - lat_delta),
        "max_lat": normalize_latitude(lat  + lat_delta),
        "min_lon": normalize_longitude(lon - lon_delta),
        "max_lon": normalize_longitude(lon + lon_delta),
    }


def is_within_bounding_box(
    lat:  float,
    lon:  float,
    bbox: dict,
) -> bool:
    """
    Checks whether a point falls within a bounding box.

    Args:
        lat:  Point latitude
        lon:  Point longitude
        bbox: Dict with min_lat, max_lat, min_lon, max_lon

    Returns:
        True if the point is inside the bounding box
    """
    return (
        bbox["min_lat"] <= lat <= bbox["max_lat"] and
        bbox["min_lon"] <= lon <= bbox["max_lon"]
    )

# ─── Midpoint ─────────────────────────────────────────────────────────────────

def midpoint(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> Tuple[float, float]:
    """
    Calculates the geographic midpoint between two coordinates.

    Args:
        lat1, lon1: First point in degrees
        lat2, lon2: Second point in degrees

    Returns:
        Tuple of (mid_lat, mid_lon) in degrees
    """
    # Convert to radians
    rlat1 = math.radians(lat1)
    rlat2 = math.radians(lat2)
    dlon  = math.radians(lon2 - lon1)
    rlon1 = math.radians(lon1)

    bx = math.cos(rlat2) * math.cos(dlon)
    by = math.cos(rlat2) * math.sin(dlon)

    mid_lat = math.atan2(
        math.sin(rlat1) + math.sin(rlat2),
        math.sqrt((math.cos(rlat1) + bx) ** 2 + by ** 2)
    )
    mid_lon = rlon1 + math.atan2(by, math.cos(rlat1) + bx)

    return (
        round(math.degrees(mid_lat), 6),
        round(normalize_longitude(math.degrees(mid_lon)), 6),
    )