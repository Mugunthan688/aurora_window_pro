"""
Aurora Window Pro — backend/services/solar_wind_ingestion.py
=============================================================
Ingestion layer for live NOAA SWPC space weather data.

Handles:
    • IMF magnetic field vectors (Bx, By, Bz, Bt) from mag-1-day.json
    • Solar wind plasma (speed, density, temperature) from plasma-1-day.json
    • Real-time Kp index from noaa-planetary-k-index.json
    • 3-day Kp forecast from 3-day-forecast.json
    • Active geomagnetic alerts from alerts.json

⚠️  NOAA SWPC updated its JSON schema effective March 31, 2026.
    All parsers below use .get() with safe defaults and validate list
    length before indexing. Never assume key names or column positions.

DSCOVR → ACE Failover:
    In production, if DSCOVR data is stale (>5 min) the system would fall back
    to ACE real-time data from the same NOAA endpoints (the "source" field in
    each JSON row identifies the instrument). For the hackathon MVP, failover is
    handled by returning fallback mock data with source="fallback" when any
    NOAA request fails — downstream callers check this flag and display a
    degraded-mode banner.

All functions are async and use httpx for non-blocking HTTP calls.
"""

import httpx
import logging
from datetime import datetime, timezone
from typing import Any

from config import (
    NOAA_MAG_URL,
    NOAA_PLASMA_URL,
    NOAA_KP_URL,
    NOAA_FORECAST_URL,
    NOAA_ALERTS_URL,
    BZ_ALERT_THRESHOLD_NT,
    SOLAR_WIND_SPEED_THRESHOLD_KMS,
    ACE_FAILOVER_STALE_THRESHOLD_SEC,
    DATA_GAP_PLACEHOLDER,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared HTTP timeout — keep short so the API stays responsive in the field
# ---------------------------------------------------------------------------
_HTTP_TIMEOUT = 10.0   # seconds


# ===========================================================================
# Low-level fetch helper
# ===========================================================================

async def _fetch_noaa_json(url: str) -> tuple[Any, bool]:
    """
    Fetch a NOAA SWPC JSON endpoint and return (data, is_live).

    Returns:
        data    — parsed JSON (list or dict) if successful, else None
        is_live — False when the request failed; caller should use fallback data
    """
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.json(), True
    except httpx.TimeoutException:
        logger.warning("NOAA timeout: %s", url)
    except httpx.HTTPStatusError as e:
        logger.warning("NOAA HTTP %s: %s", e.response.status_code, url)
    except Exception as e:
        logger.warning("NOAA fetch error (%s): %s", url, e)
    return None, False


# ===========================================================================
# Column-index helpers
# (NOAA returns data as list-of-lists; row[0] is a header, rows[1:] are data)
# These helpers encapsulate the defensive index lookups in one place.
# ===========================================================================

def _safe_float(row: list, index: int) -> float | None:
    """Extract a float from a list row at `index`. Returns None on any error."""
    try:
        val = row[index]
        if val is None or str(val).strip().lower() in ("", "null", "nan", "-9999.0", "-9999"):
            return DATA_GAP_PLACEHOLDER
        return float(val)
    except (IndexError, TypeError, ValueError):
        return DATA_GAP_PLACEHOLDER


def _safe_str(row: list, index: int) -> str | None:
    """Extract a stripped string from a list row at `index`."""
    try:
        val = row[index]
        return str(val).strip() if val is not None else None
    except (IndexError, TypeError):
        return None


def _find_column(header_row: list, *names: str) -> int | None:
    """
    Find the index of a column by trying multiple possible header names.
    Handles schema variability between pre- and post-March-31-2026 formats.
    Returns None if none of the names are found.
    """
    lower_header = [str(h).lower().strip() for h in header_row]
    for name in names:
        try:
            return lower_header.index(name.lower())
        except ValueError:
            continue
    return None


# ===========================================================================
# 1. Magnetic Field Data — IMF Bx, By, Bz, Bt
# ===========================================================================

async def fetch_magnetic_field() -> dict:
    """
    Fetch and parse the latest IMF magnetic field reading from NOAA DSCOVR.

    Source: mag-1-day.json
    Returns the most recent non-null data row as a dict with keys:
        timestamp_utc, bx, by, bz, bt, source

    Falls back to mock data if the endpoint is unreachable or unparseable.
    """
    raw, is_live = await _fetch_noaa_json(NOAA_MAG_URL)

    if not is_live or not isinstance(raw, list) or len(raw) < 2:
        logger.warning("Magnetic field data unavailable — using fallback.")
        return _fallback_magnetic()

    # Row 0 is the header, rows 1..n are data newest-last
    header = raw[0]

    # Locate columns defensively — schema may vary across versions
    # Pre-2026: ["time_tag", "bx_gsm", "by_gsm", "bz_gsm", "lon_gsm", "lat_gsm", "bt"]
    # Post-2026: may use "bx", "by", "bz" or different casing
    idx_time = _find_column(header, "time_tag", "timestamp", "time")
    idx_bx   = _find_column(header, "bx_gsm", "bx")
    idx_by   = _find_column(header, "by_gsm", "by")
    idx_bz   = _find_column(header, "bz_gsm", "bz")
    idx_bt   = _find_column(header, "bt", "b_total", "btotal")

    if idx_bz is None:
        logger.warning("Bz column not found in mag JSON header: %s", header)
        return _fallback_magnetic()

    # Walk backward from the most recent row to find a non-null Bz reading
    for row in reversed(raw[1:]):
        if not isinstance(row, list):
            continue
        bz = _safe_float(row, idx_bz)
        if bz is None:
            continue   # Skip data gap rows

        return {
            "timestamp_utc": _safe_str(row, idx_time) if idx_time is not None else None,
            "bx":  _safe_float(row, idx_bx) if idx_bx is not None else None,
            "by":  _safe_float(row, idx_by) if idx_by is not None else None,
            "bz":  bz,
            "bt":  _safe_float(row, idx_bt) if idx_bt is not None else None,
            "source": "live",
        }

    logger.warning("All magnetic field rows contain data gaps — using fallback.")
    return _fallback_magnetic()


# ===========================================================================
# 2. Plasma Data — Solar Wind Speed, Density, Temperature
# ===========================================================================

async def fetch_plasma() -> dict:
    """
    Fetch and parse the latest solar wind plasma reading from NOAA DSCOVR.

    Source: plasma-1-day.json
    Returns the most recent non-null data row as a dict with keys:
        timestamp_utc, speed, density, temperature, source

    Falls back to mock data on failure.
    """
    raw, is_live = await _fetch_noaa_json(NOAA_PLASMA_URL)

    if not is_live or not isinstance(raw, list) or len(raw) < 2:
        logger.warning("Plasma data unavailable — using fallback.")
        return _fallback_plasma()

    header = raw[0]

    # Column names vary across schema versions — try multiple candidates
    idx_time  = _find_column(header, "time_tag", "timestamp", "time")
    idx_speed = _find_column(header, "speed", "proton_speed", "bulk_speed")
    idx_dens  = _find_column(header, "density", "proton_density", "np")
    idx_temp  = _find_column(header, "temperature", "proton_temp", "tp")

    if idx_speed is None:
        logger.warning("Speed column not found in plasma JSON header: %s", header)
        return _fallback_plasma()

    for row in reversed(raw[1:]):
        if not isinstance(row, list):
            continue
        speed = _safe_float(row, idx_speed)
        if speed is None:
            continue

        return {
            "timestamp_utc": _safe_str(row, idx_time) if idx_time is not None else None,
            "speed":       speed,
            "density":     _safe_float(row, idx_dens)  if idx_dens is not None else None,
            "temperature": _safe_float(row, idx_temp)  if idx_temp is not None else None,
            "source": "live",
        }

    logger.warning("All plasma rows contain data gaps — using fallback.")
    return _fallback_plasma()


# ===========================================================================
# 3. Kp Index — Latest Real-Time Value
# ===========================================================================

async def fetch_kp_index() -> dict:
    """
    Fetch the most recent Kp reading from NOAA.

    Source: noaa-planetary-k-index.json
    Returns:
        kp (float), timestamp_utc (str), kp_source (str), source (str)

    The Kp index is a 3-hour average — it will not reflect brief substorms.
    Use fetch_magnetic_field() Bz values for higher-cadence nowcasting.
    """
    raw, is_live = await _fetch_noaa_json(NOAA_KP_URL)

    if not is_live or not isinstance(raw, list) or len(raw) < 2:
        logger.warning("Kp data unavailable — using fallback.")
        return {"kp": None, "timestamp_utc": None, "source": "fallback"}

    header = raw[0]
    idx_time   = _find_column(header, "time_tag", "timestamp", "time")
    idx_kp     = _find_column(header, "kp", "kp_index", "planetary_k_index")
    idx_status = _find_column(header, "kp_index", "observed", "status")

    if idx_kp is None:
        # Post-2026 fallback: sometimes Kp is in column index 1 with no header
        idx_kp = 1

    for row in reversed(raw[1:]):
        if not isinstance(row, list):
            continue
        kp = _safe_float(row, idx_kp)
        if kp is None:
            continue

        return {
            "kp":            kp,
            "timestamp_utc": _safe_str(row, idx_time) if idx_time is not None else None,
            "source":        "live",
        }

    return {"kp": None, "timestamp_utc": None, "source": "fallback"}


# ===========================================================================
# 4. 3-Day Kp Forecast
# ===========================================================================

async def fetch_kp_forecast() -> dict:
    """
    Fetch the 3-day Kp forecast from NOAA SWPC.

    Source: 3-day-forecast.json — updated ~2x daily.
    Returns:
        forecast (list of {period, kp_predicted}), source (str)
    """
    raw, is_live = await _fetch_noaa_json(NOAA_FORECAST_URL)

    if not is_live or not isinstance(raw, list) or len(raw) < 2:
        logger.warning("Kp forecast unavailable — using fallback.")
        return {"forecast": [], "source": "fallback"}

    entries = []
    # Skip header row [0], parse data rows
    for row in raw[1:]:
        if not isinstance(row, list) or len(row) < 2:
            continue
        period   = _safe_str(row, 0)
        kp_pred  = _safe_float(row, 1)
        if period is None:
            continue
        entries.append({"period": period, "kp_predicted": kp_pred})

    return {"forecast": entries, "source": "live" if entries else "fallback"}


# ===========================================================================
# 5. Active NOAA Alerts
# ===========================================================================

async def fetch_noaa_alerts() -> dict:
    """
    Fetch active geomagnetic alerts from NOAA SWPC.

    Source: alerts.json — event-driven, updated when alerts are issued.
    Returns:
        alerts (list of {product_id, issued_at, message}), source (str)
    """
    raw, is_live = await _fetch_noaa_json(NOAA_ALERTS_URL)

    if not is_live or not isinstance(raw, list):
        logger.warning("NOAA alerts unavailable.")
        return {"alerts": [], "source": "fallback"}

    parsed = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        parsed.append({
            "product_id": item.get("product_id", "UNKNOWN"),
            "issued_at":  item.get("issue_datetime") or item.get("issued_at"),
            "message":    item.get("message", ""),
        })

    return {"alerts": parsed, "source": "live"}


# ===========================================================================
# 6. Combined Current Conditions — Primary service function
# ===========================================================================

async def get_latest_solar_wind() -> dict:
    """
    Combine the latest magnetic field + plasma + Kp readings into a single
    current-conditions snapshot.

    This is the primary function called by space_weather_api.py and alert_api.py.

    Returns a dict with:
        bx, by, bz, bt       — IMF components (nT)
        speed                — solar wind speed (km/s)
        density              — proton density (p/cm³)
        temperature          — proton temperature (K)
        kp                   — latest Kp index
        bz_alert             — True if Bz < –7 nT
        speed_alert          — True if speed > 500 km/s
        timestamp_utc        — timestamp of the magnetic field reading
        source               — "live", "partial", or "fallback"
    """

    # Fetch both streams concurrently using httpx (each is independent)
    # In a production system these would be awaited with asyncio.gather()
    # For hackathon clarity, sequential calls are used — still fast enough.
    mag_data    = await fetch_magnetic_field()
    plasma_data = await fetch_plasma()
    kp_data     = await fetch_kp_index()

    # Determine overall source quality
    live_count = sum(1 for d in [mag_data, plasma_data, kp_data] if d.get("source") == "live")
    if live_count == 3:
        source = "live"
    elif live_count > 0:
        source = "partial"   # Some streams live, some on fallback
    else:
        source = "fallback"

    bz    = mag_data.get("bz")
    speed = plasma_data.get("speed")

    # --- Threshold intelligence (PS Section 2.1) ---
    bz_alert    = (bz    is not None and bz    < BZ_ALERT_THRESHOLD_NT)
    speed_alert = (speed is not None and speed > SOLAR_WIND_SPEED_THRESHOLD_KMS)

    return {
        # Magnetic field
        "bx":  mag_data.get("bx"),
        "by":  mag_data.get("by"),
        "bz":  bz,
        "bt":  mag_data.get("bt"),

        # Plasma
        "speed":       speed,
        "density":     plasma_data.get("density"),
        "temperature": plasma_data.get("temperature"),

        # Kp
        "kp": kp_data.get("kp"),

        # Threshold flags
        "bz_alert":    bz_alert,
        "speed_alert": speed_alert,

        # Metadata
        "timestamp_utc": mag_data.get("timestamp_utc"),
        "source":        source,
    }


# ===========================================================================
# Fallback / mock data
# ===========================================================================

def _fallback_magnetic() -> dict:
    """
    Return realistic quiet-sun magnetic field values when NOAA is unreachable.
    Values represent a typical background solar wind Bz near zero (not alarming).
    Marked source="fallback" so downstream callers can display a degraded banner.
    """
    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "bx":    1.2,    # nT — typical quiet-sun value
        "by":   -0.8,
        "bz":    0.5,    # Slightly northward — no aurora expected
        "bt":    1.5,
        "source": "fallback",
    }


def _fallback_plasma() -> dict:
    """
    Return realistic quiet-sun solar wind plasma values when NOAA is unreachable.
    400 km/s is a typical background solar wind speed.
    """
    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "speed":       400.0,   # km/s — typical background speed
        "density":       5.0,   # p/cm³
        "temperature": 50000,   # K — rough background value
        "source": "fallback",
    }