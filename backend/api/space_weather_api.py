"""
Aurora Window Pro — backend/api/space_weather_api.py
=====================================================
FastAPI router exposing live space weather endpoints.

All data is sourced from NOAA SWPC public JSON endpoints.

⚠️  NOAA SWPC updated its JSON schema effective March 31, 2026.
    All parsing below is written defensively using .get() with safe
    defaults. Never assume key existence or list length.

Endpoints:
    GET /space-weather/current    — Latest solar wind + Kp snapshot
    GET /space-weather/forecast   — 3-day Kp forecast (frontend-friendly)
    GET /space-weather/substorm   — Substorm precursor risk assessment
    GET /space-weather/alerts     — Active NOAA geomagnetic alerts
"""

from fastapi import APIRouter, HTTPException
from typing import Any

# ---------------------------------------------------------------------------
# Service layer imports
# Each service handles its own NOAA fetch + parsing logic.
# This router only orchestrates calls and shapes responses.
# ---------------------------------------------------------------------------
from services.solar_wind_ingestion import (
    get_latest_solar_wind,   # Returns parsed Bz, Bx, By, speed, density, temp + Kp
)
from services.ovation_parser import (
    get_aurora_activity_summary,  # Returns a short human-readable aurora status string
)
from services.substorm_detector import (
    get_substorm_risk,       # Returns substorm risk level + Bz rate-of-change
)

# ---------------------------------------------------------------------------
# Import NOAA URLs from central config so URLs stay in one place
# ---------------------------------------------------------------------------
from config import (
    NOAA_FORECAST_URL,
    NOAA_ALERTS_URL,
)

import httpx                 # Async HTTP client — non-blocking inside FastAPI
import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Router — mounted at /space-weather in main.py via app.include_router()
# ---------------------------------------------------------------------------
router = APIRouter(
    prefix="/space-weather",
    tags=["Space Weather"],
)


# ---------------------------------------------------------------------------
# Shared async helper: fetch JSON from a URL with graceful error handling
# ---------------------------------------------------------------------------
async def _fetch_json(url: str) -> tuple[Any, bool]:
    """
    Fetch JSON from `url` asynchronously.

    Returns:
        (data, is_live): data is the parsed JSON (or None on failure),
                         is_live is False when fallback/error occurred.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.json(), True
    except httpx.TimeoutException:
        logger.warning("Timeout fetching %s", url)
    except httpx.HTTPStatusError as e:
        logger.warning("HTTP %s from %s", e.response.status_code, url)
    except Exception as e:
        logger.warning("Unexpected error fetching %s: %s", url, e)
    return None, False


# ===========================================================================
# ENDPOINT 1 — GET /space-weather/current
# ===========================================================================
@router.get("/current", summary="Latest solar wind snapshot and Kp index")
async def get_current_space_weather():
    """
    Returns the most recent reading from NOAA DSCOVR/ACE instruments:

    - IMF Bz, Bx, By (nT)        — from mag-1-day.json
    - Solar wind speed (km/s)     — from plasma-1-day.json
    - Density (p/cm³)             — from plasma-1-day.json
    - Temperature (K)             — from plasma-1-day.json
    - Latest Kp index             — from noaa-planetary-k-index.json
    - Aurora activity summary     — derived from OVATION grid

    If NOAA data is unavailable, a fallback payload is returned with
    `"source": "fallback"` so the frontend can display a degraded-mode banner.
    """

    # --- Fetch from service layer ---
    solar_wind_data = await get_latest_solar_wind()
    aurora_summary  = await get_aurora_activity_summary()

    # solar_wind_data already includes a `source` flag ("live" or "fallback")
    # set by the service layer when DSCOVR→ACE failover or total failure occurs.

    return {
        "source": solar_wind_data.get("source", "unknown"),

        # --- IMF magnetic field components ---
        "imf": {
            "bz": solar_wind_data.get("bz"),          # Key driver of aurora (nT)
            "bx": solar_wind_data.get("bx"),          # East-west component (nT)
            "by": solar_wind_data.get("by"),          # North-south GSE component (nT)
            "bt": solar_wind_data.get("bt"),          # Total field magnitude (nT)
            "unit": "nT",
        },

        # --- Plasma / solar wind ---
        "solar_wind": {
            "speed":       solar_wind_data.get("speed"),       # km/s
            "density":     solar_wind_data.get("density"),     # protons/cm³
            "temperature": solar_wind_data.get("temperature"), # Kelvin
        },

        # --- Geomagnetic activity index ---
        "kp": {
            "value":       solar_wind_data.get("kp"),
            "description": _kp_description(solar_wind_data.get("kp")),
        },

        # --- Human-readable aurora activity ---
        "aurora_activity": aurora_summary,

        # --- Alert flags derived from thresholds in config.py ---
        "alerts": {
            # Bz < -7 nT fires nowcast alert (PS Section 2.1)
            "bz_alert":          _is_bz_alert(solar_wind_data.get("bz")),
            # Speed > 500 km/s fires velocity alert (PS Section 2.1)
            "speed_alert":       _is_speed_alert(solar_wind_data.get("speed")),
        },

        "timestamp_utc": solar_wind_data.get("timestamp_utc"),
    }


# ===========================================================================
# ENDPOINT 2 — GET /space-weather/forecast
# ===========================================================================
@router.get("/forecast", summary="3-day Kp forecast from NOAA SWPC")
async def get_kp_forecast():
    """
    Returns the NOAA 3-day Kp forecast in a simplified, frontend-friendly
    structure — one entry per forecast period with a human-readable label.

    Source: NOAA_FORECAST_URL (3-day-forecast.json) — updated 2× daily.

    Falls back to a placeholder forecast list if the endpoint is unavailable.
    """

    raw, is_live = await _fetch_json(NOAA_FORECAST_URL)

    if not is_live or raw is None:
        return {
            "source": "fallback",
            "forecast": _fallback_forecast(),
            "note": "NOAA forecast endpoint unavailable. Displaying placeholder data.",
        }

    # --- Defensive parsing ---
    # The 3-day-forecast.json returns a list of lists or a dict depending on schema version.
    # We normalise into a flat list of {period, kp_predicted, storm_level} objects.
    forecast_entries = []
    try:
        # Post-March-31-2026 schema: list of records, first item is header row
        if isinstance(raw, list) and len(raw) > 1:
            # Skip header row (index 0), parse data rows
            for row in raw[1:]:
                if not isinstance(row, list) or len(row) < 2:
                    continue
                period    = _safe_str(row, 0)
                kp_value  = _safe_float(row, 1)
                if period is None:
                    continue
                forecast_entries.append({
                    "period":       period,
                    "kp_predicted": kp_value,
                    "storm_level":  _kp_storm_level(kp_value),
                    "description":  _kp_description(kp_value),
                })
        else:
            # Unexpected schema — log and fall through to fallback
            logger.warning("3-day forecast JSON has unexpected structure: %s", type(raw))
            raise ValueError("Unrecognised schema")

    except Exception as e:
        logger.warning("Error parsing 3-day forecast: %s", e)
        return {
            "source": "fallback",
            "forecast": _fallback_forecast(),
            "note": "Forecast data could not be parsed. Schema may have changed.",
        }

    return {
        "source": "live",
        "forecast": forecast_entries,
        "note": "Kp forecast updated approximately twice daily by NOAA SWPC.",
    }


# ===========================================================================
# ENDPOINT 3 — GET /space-weather/substorm
# ===========================================================================
@router.get("/substorm", summary="Substorm precursor risk assessment")
async def get_substorm_status():
    """
    Evaluates real-time Bz trend data to assess substorm risk.

    A substorm (10–30 min intense auroral burst) can occur even when the
    3-hour Kp average looks quiet. This endpoint fires early warning signals
    based on the rate of Bz change — a stretch goal from the problem statement.

    Source: services.substorm_detector (consumes mag-1-day.json internally)

    Returns:
        risk_level   — "low" | "moderate" | "high" | "imminent"
        bz_now       — current Bz reading (nT)
        bz_rate      — Bz change rate over last 5 minutes (nT/min)
        message      — human-readable advice for the photographer
        source       — "live" or "fallback"
    """

    result = await get_substorm_risk()

    return {
        "source":     result.get("source", "unknown"),
        "risk_level": result.get("risk_level", "unknown"),
        "bz_now":     result.get("bz_now"),
        "bz_rate":    result.get("bz_rate"),        # nT/min — negative = rapidly southward
        "message":    result.get("message", ""),
        "advice": _substorm_photographer_advice(result.get("risk_level")),
    }


# ===========================================================================
# ENDPOINT 4 — GET /space-weather/alerts
# ===========================================================================
@router.get("/alerts", summary="Active NOAA geomagnetic alerts and watches")
async def get_active_alerts():
    """
    Returns currently active geomagnetic alerts, watches, and warnings
    issued by NOAA Space Weather Prediction Center.

    Source: NOAA_ALERTS_URL (alerts.json) — event-driven, updated as issued.

    Each alert includes:
        - product_id    — NOAA internal alert type identifier
        - issued_at     — UTC timestamp of issuance
        - message       — Full alert text
        - severity      — Extracted storm level if present (e.g. "G2", "G3")

    Returns an empty list (not an error) if no alerts are currently active.
    """

    raw, is_live = await _fetch_json(NOAA_ALERTS_URL)

    if not is_live or raw is None:
        return {
            "source": "fallback",
            "alerts": [],
            "count":  0,
            "note": "NOAA alerts endpoint unavailable. Check https://www.swpc.noaa.gov manually.",
        }

    # --- Defensive parsing ---
    # alerts.json returns a list of alert objects.
    # Each object should have: product_id, issue_datetime, message
    parsed_alerts = []
    try:
        if not isinstance(raw, list):
            raise ValueError("Expected a list of alert objects")

        for item in raw:
            if not isinstance(item, dict):
                continue

            product_id  = item.get("product_id", "UNKNOWN")
            issued_at   = item.get("issue_datetime") or item.get("issued_at")
            message     = item.get("message", "")

            parsed_alerts.append({
                "product_id": product_id,
                "issued_at":  issued_at,
                "message":    message,
                "severity":   _extract_storm_level(message),
            })

    except Exception as e:
        logger.warning("Error parsing NOAA alerts JSON: %s", e)
        return {
            "source": "fallback",
            "alerts": [],
            "count":  0,
            "note": f"Alert parsing failed: {e}",
        }

    return {
        "source": "live",
        "alerts": parsed_alerts,
        "count":  len(parsed_alerts),
    }


# ===========================================================================
# Private helper functions — keep all business logic out of endpoint bodies
# ===========================================================================

def _is_bz_alert(bz) -> bool:
    """True when Bz is below the -7 nT alert threshold (PS Section 2.1)."""
    if bz is None:
        return False
    try:
        return float(bz) < -7.0   # BZ_ALERT_THRESHOLD_NT from config
    except (TypeError, ValueError):
        return False


def _is_speed_alert(speed) -> bool:
    """True when solar wind speed exceeds 500 km/s (PS Section 2.1)."""
    if speed is None:
        return False
    try:
        return float(speed) > 500.0   # SOLAR_WIND_SPEED_THRESHOLD_KMS from config
    except (TypeError, ValueError):
        return False


def _kp_description(kp) -> str:
    """Map a Kp value to a human-readable storm level label."""
    if kp is None:
        return "Unknown"
    try:
        k = float(kp)
    except (TypeError, ValueError):
        return "Unknown"

    if k < 3:   return "Quiet"
    if k < 5:   return "Active"
    if k < 6:   return "G1 — Minor Storm"
    if k < 7:   return "G2 — Moderate Storm"
    if k < 8:   return "G3 — Strong Storm"
    if k < 9:   return "G4 — Severe Storm"
    return          "G5 — Extreme Storm"


def _kp_storm_level(kp) -> str | None:
    """Return NOAA G-scale storm level string, or None if below storm threshold."""
    if kp is None:
        return None
    try:
        k = float(kp)
    except (TypeError, ValueError):
        return None

    if k < 5:  return None
    if k < 6:  return "G1"
    if k < 7:  return "G2"
    if k < 8:  return "G3"
    if k < 9:  return "G4"
    return         "G5"


def _substorm_photographer_advice(risk_level: str | None) -> str:
    """Return field-ready advice based on substorm risk level."""
    advice_map = {
        "low":      "Conditions are quiet. Monitor passively — no immediate action needed.",
        "moderate": "Bz trending southward. Set up your camera and stay alert.",
        "high":     "Rapid Bz drop detected. Head outside now — display may start within minutes.",
        "imminent": "⚡ Substorm precursor signal! Aurora burst likely within 10 minutes. Shoot now.",
    }
    return advice_map.get(risk_level or "low", "Risk level unknown — check solar wind data.")


def _extract_storm_level(message: str) -> str | None:
    """
    Scan a NOAA alert message string for a G-scale storm level (G1–G5).
    Returns the first match found, or None.
    """
    if not message:
        return None
    import re
    match = re.search(r"G[1-5]", message)
    return match.group(0) if match else None


def _safe_str(row: list, index: int) -> str | None:
    """Safely extract a string from a list at `index`."""
    try:
        val = row[index]
        return str(val).strip() if val is not None else None
    except (IndexError, TypeError):
        return None


def _safe_float(row: list, index: int) -> float | None:
    """Safely extract a float from a list at `index`."""
    try:
        val = row[index]
        return float(val) if val is not None else None
    except (IndexError, TypeError, ValueError):
        return None


def _fallback_forecast() -> list[dict]:
    """
    Minimal placeholder forecast returned when NOAA is unreachable.
    The frontend should display these with a clear 'data unavailable' indicator.
    """
    return [
        {"period": "Today",    "kp_predicted": None, "storm_level": None, "description": "Data unavailable"},
        {"period": "Tomorrow", "kp_predicted": None, "storm_level": None, "description": "Data unavailable"},
        {"period": "Day 3",    "kp_predicted": None, "storm_level": None, "description": "Data unavailable"},
    ]