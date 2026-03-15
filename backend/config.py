"""
Aurora Window Pro — backend/config.py
======================================
Central configuration for the Aurora Window Pro hyper-local aurora forecasting platform.
Built for Orion Astrathon (48-hour hackathon).

NOTE: NOAA SWPC updated its JSON schema effective March 31, 2026.
All parsers consuming NOAA endpoints must be written defensively (use .get(), validate keys
before access, and fall back gracefully on unexpected schema). Legacy product endpoints
are deprecated — only the URLs listed below are valid as of the contest window.
"""

# ---------------------------------------------------------------------------
# App Identity
# ---------------------------------------------------------------------------

APP_NAME = "Aurora Window Pro"
APP_VERSION = "1.0.0"
DEBUG = True  # Set to False in production

# API prefix for all FastAPI routes (e.g. /api/v1/solar-wind)
API_PREFIX = "/api/v1"


# ---------------------------------------------------------------------------
# Primary Space Weather Data Sources — NOAA SWPC
# (PS Section 4.1 — all endpoints confirmed against post-March-31-2026 schema)
# ---------------------------------------------------------------------------

# IMF Bx, By, Bz, Bt vectors from DSCOVR — 1-minute cadence
# Used for: real-time Bz threshold nowcasting (D1 — Live Data Pipeline)
NOAA_MAG_URL = "https://services.swpc.noaa.gov/products/solar-wind/mag-1-day.json"

# Solar wind speed, density, temperature — 1-minute cadence
# Used for: solar wind velocity threshold alerts (D1 — Live Data Pipeline)
NOAA_PLASMA_URL = "https://services.swpc.noaa.gov/products/solar-wind/plasma-1-day.json"

# OVATION-Prime auroral probability grid (360×181 resolution) — ~30-minute cadence
# Used for: main interactive aurora map overlay (D2 — Interactive Aurora Map)
NOAA_OVATION_URL = "https://services.swpc.noaa.gov/json/ovation_aurora_latest.json"

# Real-time Kp index — 3-hour blocks
# Used for: context display, user alerts, and visibility score supplemental input (D3, D4)
NOAA_KP_URL = "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json"

# Predicted Kp for next 3 days — updated 2x daily
# Used for: advance planning features and scheduling alerts
NOAA_FORECAST_URL = "https://services.swpc.noaa.gov/products/3-day-forecast.json"

# Active NOAA geomagnetic alerts & watches — event-driven
# Used for: push notification source (D4 — Alert System)
NOAA_ALERTS_URL = "https://services.swpc.noaa.gov/products/alerts.json"


# ---------------------------------------------------------------------------
# Meteorological Data Source — Open-Meteo
# (PS Section 4.2 — free, no API key required)
# ---------------------------------------------------------------------------

# Cloud cover (low/mid/high), seeing index, transparency
# Used for: cloud cover component of Visibility Score (D3)
OPEN_METEO_BASE_URL = "https://api.open-meteo.com/v1/forecast"

# Open-Meteo query parameters appended at request time:
# hourly=cloudcover,cloudcover_low,cloudcover_mid,cloudcover_high
# No API key needed — rate limit is generous for hackathon use


# ---------------------------------------------------------------------------
# Polling / Refresh Cadences (in seconds)
# (PS Section 4.1 — matched to data source update frequencies)
# ---------------------------------------------------------------------------

# Solar wind mag & plasma — source updates every 1 minute; poll every 60s
SOLAR_WIND_POLL_INTERVAL_SEC = 60

# OVATION aurora probability grid — source updates every ~30 minutes
OVATION_POLL_INTERVAL_SEC = 1800

# Kp index — updated in 3-hour blocks; poll every 15 minutes to catch new blocks early
KP_POLL_INTERVAL_SEC = 900

# 3-day Kp forecast — updated 2x daily; poll every 6 hours
FORECAST_POLL_INTERVAL_SEC = 21600

# NOAA alerts — event-driven; poll every 2 minutes to stay responsive
ALERTS_POLL_INTERVAL_SEC = 120

# Cloud cover from Open-Meteo — hourly data; refresh every 30 minutes
CLOUD_COVER_POLL_INTERVAL_SEC = 1800


# ---------------------------------------------------------------------------
# Alert / Nowcast Threshold Constants
# (PS Section 2.1 — "Real-Time Solar Wind Ingestion & Threshold Intelligence")
# ---------------------------------------------------------------------------

# IMF Bz threshold: when Bz drops below this value (southward), magnetic reconnection
# occurs and auroral activity intensifies. Fire an alert immediately.
BZ_ALERT_THRESHOLD_NT = -7.0  # nT — from PS: "Bz < –7 nT"

# Solar wind speed threshold: speeds above this indicate enhanced particle flux.
# Alert even if Bz hasn't gone negative yet.
SOLAR_WIND_SPEED_THRESHOLD_KMS = 500.0  # km/s — from PS: "solar wind speed exceeds 500 km/s"

# Bz rate-of-change threshold for substorm early warning (stretch goal)
# If Bz deflects southward faster than this rate over a 5-minute window, fire precursor alert
BZ_SUBSTORM_RATE_THRESHOLD_NT_PER_MIN = -2.0  # nT/min (tune after testing)


# ---------------------------------------------------------------------------
# Visibility Score Routing Thresholds
# (PS Section 2.1 — "Logistical Routing" stretch goal; also used in D3 scoring)
# ---------------------------------------------------------------------------

# A candidate routing destination must satisfy ALL three simultaneously:

# Aurora probability from OVATION grid must exceed this to be "in the auroral zone"
ROUTING_MIN_AURORA_PROBABILITY_PCT = 50.0  # % — from PS: "aurora probability > 50%"

# Cloud cover must be below this for the sky to be usably clear
ROUTING_MAX_CLOUD_COVER_PCT = 30.0  # % — from PS: "below 30% cloud cover"

# Bortle scale: Class 4 = rural/suburban transition sky. Below this = genuinely dark.
# Routing must target locations with Bortle class strictly less than this value.
ROUTING_MAX_BORTLE_CLASS = 4  # — from PS: "below Bortle Class 4"


# ---------------------------------------------------------------------------
# Kp Index — Visibility Latitude Reference
# (PS Section 1.1 — Kp table for display and score context)
# ---------------------------------------------------------------------------

# Approximate minimum geomagnetic latitude (degrees) at which aurora is visible per Kp level.
# Used as a supplementary lookup for the visibility score engine.
KP_LATITUDE_REFERENCE = {
    0: 67.0,
    1: 66.5,
    2: 65.0,
    3: 63.0,
    4: 60.0,
    5: 56.0,   # G1 Minor Storm
    6: 54.0,   # G2 Moderate Storm
    7: 52.0,   # G3 Strong Storm
    8: 50.0,   # G4 Severe Storm
    9: 48.0,   # G5 Extreme Storm
}


# ---------------------------------------------------------------------------
# Visibility Score Weights
# (PS Section 2.1 — D3 Visibility Score Engine; weights must be documented & defensible)
# ---------------------------------------------------------------------------

# All three weights must sum to 1.0
VISIBILITY_WEIGHT_AURORA_PROBABILITY = 0.50   # Primary driver — OVATION probability
VISIBILITY_WEIGHT_CLOUD_COVER        = 0.30   # Clear sky is non-negotiable for photography
VISIBILITY_WEIGHT_DARKNESS           = 0.20   # Combines Bortle class + lunar illumination

assert abs(
    VISIBILITY_WEIGHT_AURORA_PROBABILITY +
    VISIBILITY_WEIGHT_CLOUD_COVER +
    VISIBILITY_WEIGHT_DARKNESS - 1.0
) < 1e-9, "Visibility score weights must sum to 1.0"


# ---------------------------------------------------------------------------
# Map Defaults
# (PS Section 2.2 — "web application or mobile-responsive interface")
# ---------------------------------------------------------------------------

# Default map center on load — set to northern Norway (prime aurora zone)
DEFAULT_MAP_LAT = 69.6489   # Tromsø, Norway
DEFAULT_MAP_LON = 18.9551
DEFAULT_MAP_ZOOM = 3        # Zoomed out to show full auroral oval

# Viewing geometry radius drawn around the user's pin (kilometres)
# Aurora visible up to ~500 km from the auroral oval edge on clear nights
VIEWER_RADIUS_KM = 500


# ---------------------------------------------------------------------------
# Astronomical & Darkness Constants
# ---------------------------------------------------------------------------

# Maximum lunar illumination fraction (0–1) before moon significantly degrades viewing
MAX_ACCEPTABLE_LUNAR_ILLUMINATION = 0.25  # 25% — quarter moon or brighter degrades score

# Solar zenith angle thresholds for twilight bands (degrees)
# Used for the day/night terminator layer (D2) and darkness scoring (D3)
CIVIL_TWILIGHT_ZENITH_DEG      = 96.0
NAUTICAL_TWILIGHT_ZENITH_DEG   = 102.0
ASTRONOMICAL_TWILIGHT_ZENITH_DEG = 108.0  # True darkness begins beyond this


# ---------------------------------------------------------------------------
# DSCOVR → ACE Failover
# (PS Section 5.1 — "DSCOVR→ACE failover" required for full marks on Technical Depth)
# ---------------------------------------------------------------------------

# If DSCOVR data is flagged as stale or missing, fall back to ACE real-time solar wind.
# ACE data is mirrored through NOAA SWPC at the same endpoints (instrument field in JSON).
# Parsers should check the "source" or "station" key in each record and log a warning
# when falling back. Mark any affected visibility scores as "degraded confidence".
ACE_FAILOVER_STALE_THRESHOLD_SEC = 300   # Flag DSCOVR data as stale if >5 min old
DATA_GAP_PLACEHOLDER = None              # Use None (not 0) for missing values to avoid false triggers


# ---------------------------------------------------------------------------
# CORS & Server (for FastAPI / Uvicorn)
# ---------------------------------------------------------------------------

ALLOWED_ORIGINS = [
    "http://localhost:3000",   # React dev server
    "http://localhost:5173",   # Vite dev server
    "http://127.0.0.1:3000",
    "*",                       # Loosen for hackathon judging — tighten in prod
]

HOST = "0.0.0.0"
PORT = 8000

# ================================
# ROUTING CONFIG
# ================================

# Average driving speed assumption for route estimation
AVG_DRIVING_SPEED_KMH = 60


# ================================
# VISIBILITY THRESHOLDS
# ================================

AURORA_PROBABILITY_THRESHOLD = 0.5
CLOUD_COVER_THRESHOLD = 30
BORTLE_THRESHOLD = 4


# ================================
# SPACE WEATHER ALERT THRESHOLDS
# ================================

BZ_ALERT_THRESHOLD = -7      # nT
SOLAR_WIND_ALERT_SPEED = 500 # km/s