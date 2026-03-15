"""
Aurora Window Pro — backend/api/alert_api.py
=============================================
FastAPI router for the Alert System (D4 — required deliverable).

PS Section 2.1 — "A notification mechanism that fires when visibility score
exceeds a user-configurable threshold at a saved location."

Additionally, threshold intelligence fires immediately when:
    • Bz < –7 nT          (magnetic reconnection trigger)
    • Solar wind > 500 km/s (enhanced particle flux trigger)
    • Active NOAA geomagnetic watch/warning is present

This module uses an in-memory alert store (Python dict) — no database needed
for the hackathon MVP. Alert preferences reset when the server restarts.

Endpoints:
    GET  /alerts/check         — Check if alert conditions are met right now
    POST /alerts/create        — Save a location + threshold preference
    GET  /alerts/sample        — Pre-built sample alerts for demo / judging
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Annotated
import uuid
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Service layer imports
# ---------------------------------------------------------------------------
from services.solar_wind_ingestion import get_latest_solar_wind   # Bz, speed, Kp
from services.visibility_score     import compute_visibility_score # Composite score

# ---------------------------------------------------------------------------
# Config thresholds (single source of truth)
# ---------------------------------------------------------------------------
from config import (
    BZ_ALERT_THRESHOLD_NT,              # -7.0 nT
    SOLAR_WIND_SPEED_THRESHOLD_KMS,     # 500.0 km/s
    VISIBILITY_WEIGHT_AURORA_PROBABILITY,
    VISIBILITY_WEIGHT_CLOUD_COVER,
    VISIBILITY_WEIGHT_DARKNESS,
    NOAA_ALERTS_URL,
)

import httpx

# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------
router = APIRouter(
    prefix="/alerts",
    tags=["Alerts"],
)

# ---------------------------------------------------------------------------
# In-memory alert store  { alert_id: AlertPreference dict }
# In production this would be a database table.
# ---------------------------------------------------------------------------
_alert_store: dict[str, dict] = {}

# Default visibility score threshold (user can override per alert)
DEFAULT_VISIBILITY_THRESHOLD = 50.0   # Fire when score ≥ this value


# ===========================================================================
# Pydantic models
# ===========================================================================

class AlertPreference(BaseModel):
    """
    Defines the parameters for a saved location alert.
    Sent by the client when creating a new alert via POST /alerts/create.
    """
    label: str = Field(
        default="My Location",
        description="Friendly name for this saved location (e.g. 'Backyard', 'Cabin').",
    )
    latitude: float = Field(
        ge=-90.0, le=90.0,
        description="Latitude of the saved observation location.",
    )
    longitude: float = Field(
        ge=-180.0, le=180.0,
        description="Longitude of the saved observation location.",
    )
    visibility_threshold: float = Field(
        default=DEFAULT_VISIBILITY_THRESHOLD,
        ge=0.0, le=100.0,
        description=(
            "Visibility score threshold (0–100). Alert fires when the score "
            "at this location meets or exceeds this value. Default: 50."
        ),
    )
    notify_on_bz_alert: bool = Field(
        default=True,
        description="Also fire alert when Bz < –7 nT, regardless of visibility score.",
    )
    notify_on_speed_alert: bool = Field(
        default=True,
        description="Also fire alert when solar wind speed > 500 km/s.",
    )
    notify_on_noaa_watch: bool = Field(
        default=True,
        description="Also fire alert when NOAA issues a geomagnetic watch or warning.",
    )


class AlertCheckResponse(BaseModel):
    """Returned by GET /alerts/check."""
    alert_id:     str | None
    label:        str
    triggered:    bool
    reasons:      list[str]
    visibility_score:     float | None
    threshold_used:       float
    bz_now:               float | None
    solar_wind_speed_now: float | None
    recommended_action:   str
    source:               str
    checked_at_utc:       str


# ===========================================================================
# ENDPOINT 1 — GET /alerts/check
# ===========================================================================
@router.get(
    "/check",
    summary="Check if alert conditions are currently met for a lat/lon",
    response_model=AlertCheckResponse,
)
async def check_alert(
    latitude: Annotated[
        float,
        Query(ge=-90.0, le=90.0, description="Observation latitude in decimal degrees."),
    ],
    longitude: Annotated[
        float,
        Query(ge=-180.0, le=180.0, description="Observation longitude in decimal degrees."),
    ],
    threshold: Annotated[
        float,
        Query(
            ge=0.0, le=100.0,
            description=(
                f"Visibility score threshold (0–100). "
                f"Alert fires when score ≥ this value. Default: {DEFAULT_VISIBILITY_THRESHOLD}."
            ),
        ),
    ] = DEFAULT_VISIBILITY_THRESHOLD,
    check_noaa_alerts: Annotated[
        bool,
        Query(description="Include active NOAA geomagnetic alerts in the check."),
    ] = True,
):
    """
    Evaluates current conditions at the given location and returns whether
    an alert should be fired.

    Checks (in priority order):
    1. **Bz threshold** — Bz < –7 nT fires immediately (PS Section 2.1)
    2. **Speed threshold** — Solar wind > 500 km/s fires immediately
    3. **Visibility score** — Score ≥ user threshold fires alert
    4. **NOAA watches** — Active geomagnetic watch/warning fires alert

    Returns `triggered: true` with a list of `reasons` and a recommended action.
    """

    now_utc = datetime.now(timezone.utc).isoformat()
    reasons: list[str] = []
    triggered = False

    # --- Fetch solar wind data (Bz + speed) ---
    solar_data = await _safe_get_solar_wind()
    bz_now    = solar_data.get("bz")
    speed_now = solar_data.get("speed")
    sw_source = solar_data.get("source", "unknown")

    # --- Check 1: Bz threshold ---
    if bz_now is not None and bz_now < BZ_ALERT_THRESHOLD_NT:
        triggered = True
        reasons.append(
            f"Bz = {bz_now:.1f} nT — below {BZ_ALERT_THRESHOLD_NT} nT threshold. "
            "Magnetic reconnection likely. Aurora may intensify within minutes."
        )

    # --- Check 2: Solar wind speed threshold ---
    if speed_now is not None and speed_now > SOLAR_WIND_SPEED_THRESHOLD_KMS:
        triggered = True
        reasons.append(
            f"Solar wind speed = {speed_now:.0f} km/s — exceeds {SOLAR_WIND_SPEED_THRESHOLD_KMS} km/s threshold. "
            "Enhanced particle flux incoming."
        )

    # --- Check 3: Visibility score threshold ---
    vis_score = await _safe_get_visibility_score(latitude, longitude)

    if vis_score is not None and vis_score >= threshold:
        triggered = True
        reasons.append(
            f"Visibility score = {vis_score:.1f}/100 — meets your threshold of {threshold:.0f}. "
            "Conditions at your location are favourable for aurora observation."
        )

    # --- Check 4: Active NOAA geomagnetic alerts ---
    noaa_alert_msg = None
    if check_noaa_alerts:
        noaa_alert_msg = await _check_noaa_alerts()
        if noaa_alert_msg:
            triggered = True
            reasons.append(f"NOAA issued: {noaa_alert_msg}")

    # --- Compose recommended action ---
    recommended_action = _recommended_action(triggered, reasons, vis_score, bz_now)

    return AlertCheckResponse(
        alert_id=None,   # Ad-hoc check — not tied to a saved preference
        label="Ad-hoc Check",
        triggered=triggered,
        reasons=reasons if reasons else ["No alert conditions detected at this time."],
        visibility_score=round(vis_score, 1) if vis_score is not None else None,
        threshold_used=threshold,
        bz_now=round(bz_now, 2) if bz_now is not None else None,
        solar_wind_speed_now=round(speed_now, 0) if speed_now is not None else None,
        recommended_action=recommended_action,
        source=sw_source,
        checked_at_utc=now_utc,
    )


# ===========================================================================
# ENDPOINT 2 — POST /alerts/create
# ===========================================================================
@router.post("/create", summary="Save an alert preference for a location")
async def create_alert(preference: AlertPreference):
    """
    Saves an alert preference (location + threshold) to the in-memory store.

    In a production system this would write to a database and hook into a
    push notification / email queue. For the hackathon MVP, preferences persist
    in memory for the session and can be checked via GET /alerts/check.

    Returns the generated `alert_id` — use this to retrieve or delete the alert later.

    Immediately runs a check against current conditions and returns whether
    the alert would currently be triggered.
    """

    alert_id = str(uuid.uuid4())[:8]   # Short ID for demo legibility

    # Persist preference
    _alert_store[alert_id] = {
        "alert_id":   alert_id,
        "label":      preference.label,
        "latitude":   preference.latitude,
        "longitude":  preference.longitude,
        "threshold":  preference.visibility_threshold,
        "notify_bz":       preference.notify_on_bz_alert,
        "notify_speed":    preference.notify_on_speed_alert,
        "notify_noaa":     preference.notify_on_noaa_watch,
        "created_at_utc":  datetime.now(timezone.utc).isoformat(),
    }

    logger.info("Alert created: %s for %s at (%s, %s)", alert_id, preference.label,
                preference.latitude, preference.longitude)

    # Run an immediate check so the user sees current status on creation
    current_check = await _evaluate_saved_alert(_alert_store[alert_id])

    return {
        "alert_id":       alert_id,
        "label":          preference.label,
        "saved":          True,
        "location":       {"latitude": preference.latitude, "longitude": preference.longitude},
        "threshold":      preference.visibility_threshold,
        "notify_on": {
            "bz_alert":    preference.notify_on_bz_alert,
            "speed_alert": preference.notify_on_speed_alert,
            "noaa_watch":  preference.notify_on_noaa_watch,
        },
        "current_status": current_check,
        "note": (
            "Alert preference saved. In a production system, notifications would be "
            "delivered via push/email. For this demo, use GET /alerts/check to poll "
            "conditions at any time."
        ),
    }


# ===========================================================================
# ENDPOINT 3 — GET /alerts/sample
# ===========================================================================
@router.get("/sample", summary="Pre-built sample alerts for demo and judging")
async def get_sample_alerts():
    """
    Returns a set of pre-built demonstration alerts covering different
    trigger scenarios. Useful for judges evaluating the alert system
    without having to manually set up locations.

    Also runs a live check against each sample location so judges see
    real current data in the response.
    """

    sample_locations = [
        {
            "label":     "Tromsø, Norway (prime aurora zone)",
            "latitude":  69.6489,
            "longitude": 18.9551,
            "threshold": 40.0,
        },
        {
            "label":     "Reykjavik, Iceland",
            "latitude":  64.1355,
            "longitude": -21.8954,
            "threshold": 50.0,
        },
        {
            "label":     "Fairbanks, Alaska, USA",
            "latitude":  64.8401,
            "longitude": -147.7200,
            "threshold": 45.0,
        },
        {
            "label":     "Inverness, Scotland (mid-latitude edge case)",
            "latitude":  57.4778,
            "longitude": -4.2247,
            "threshold": 60.0,   # Higher threshold needed at lower latitude
        },
        {
            "label":     "Helsinki, Finland",
            "latitude":  60.1699,
            "longitude": 24.9384,
            "threshold": 55.0,
        },
    ]

    # Fetch solar wind once — share across all sample checks
    solar_data = await _safe_get_solar_wind()

    results = []
    for loc in sample_locations:
        vis_score = await _safe_get_visibility_score(loc["latitude"], loc["longitude"])
        bz_now    = solar_data.get("bz")
        speed_now = solar_data.get("speed")

        reasons: list[str] = []
        triggered = False

        if bz_now is not None and bz_now < BZ_ALERT_THRESHOLD_NT:
            triggered = True
            reasons.append(f"Bz = {bz_now:.1f} nT (threshold: {BZ_ALERT_THRESHOLD_NT} nT)")

        if speed_now is not None and speed_now > SOLAR_WIND_SPEED_THRESHOLD_KMS:
            triggered = True
            reasons.append(f"Solar wind = {speed_now:.0f} km/s (threshold: {SOLAR_WIND_SPEED_THRESHOLD_KMS} km/s)")

        if vis_score is not None and vis_score >= loc["threshold"]:
            triggered = True
            reasons.append(f"Visibility score {vis_score:.1f} ≥ threshold {loc['threshold']}")

        results.append({
            "label":           loc["label"],
            "location":        {"latitude": loc["latitude"], "longitude": loc["longitude"]},
            "threshold":       loc["threshold"],
            "triggered":       triggered,
            "reasons":         reasons if reasons else ["Conditions quiet — no alert triggered."],
            "visibility_score": round(vis_score, 1) if vis_score is not None else None,
            "bz_now":          round(bz_now, 2) if bz_now is not None else None,
            "solar_wind_speed": round(speed_now, 0) if speed_now is not None else None,
            "recommended_action": _recommended_action(triggered, reasons, vis_score, bz_now),
            "source":          solar_data.get("source", "unknown"),
        })

    return {
        "description": (
            "Live alert checks for 5 aurora-chasing locations across the northern hemisphere. "
            "Use these to verify the alert system is working during judging."
        ),
        "solar_wind_summary": {
            "bz":    round(solar_data.get("bz", 0), 2) if solar_data.get("bz") is not None else None,
            "speed": round(solar_data.get("speed", 0), 0) if solar_data.get("speed") is not None else None,
            "source": solar_data.get("source", "unknown"),
        },
        "thresholds": {
            "bz_alert_nt":            BZ_ALERT_THRESHOLD_NT,
            "solar_wind_speed_kmh":   SOLAR_WIND_SPEED_THRESHOLD_KMS,
        },
        "samples": results,
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
    }


# ===========================================================================
# Internal helpers
# ===========================================================================

async def _evaluate_saved_alert(pref: dict) -> dict:
    """
    Run a full alert check against a saved preference dict.
    Used by /alerts/create to return immediate status after saving.
    """
    reasons: list[str] = []
    triggered = False

    solar_data = await _safe_get_solar_wind()
    bz_now     = solar_data.get("bz")
    speed_now  = solar_data.get("speed")

    if pref.get("notify_bz") and bz_now is not None and bz_now < BZ_ALERT_THRESHOLD_NT:
        triggered = True
        reasons.append(f"Bz = {bz_now:.1f} nT — below alert threshold ({BZ_ALERT_THRESHOLD_NT} nT).")

    if pref.get("notify_speed") and speed_now is not None and speed_now > SOLAR_WIND_SPEED_THRESHOLD_KMS:
        triggered = True
        reasons.append(f"Solar wind speed = {speed_now:.0f} km/s — above alert threshold ({SOLAR_WIND_SPEED_THRESHOLD_KMS} km/s).")

    vis_score = await _safe_get_visibility_score(pref["latitude"], pref["longitude"])
    if vis_score is not None and vis_score >= pref["threshold"]:
        triggered = True
        reasons.append(f"Visibility score {vis_score:.1f} ≥ your threshold {pref['threshold']}.")

    if pref.get("notify_noaa"):
        noaa_msg = await _check_noaa_alerts()
        if noaa_msg:
            triggered = True
            reasons.append(f"NOAA Alert: {noaa_msg}")

    return {
        "triggered":       triggered,
        "reasons":         reasons if reasons else ["No alert conditions currently active."],
        "visibility_score": round(vis_score, 1) if vis_score is not None else None,
        "bz_now":          round(bz_now, 2) if bz_now is not None else None,
        "solar_wind_speed": round(speed_now, 0) if speed_now is not None else None,
        "recommended_action": _recommended_action(triggered, reasons, vis_score, bz_now),
        "source":          solar_data.get("source", "unknown"),
    }


async def _safe_get_solar_wind() -> dict:
    """
    Fetch latest solar wind data from the service layer.
    Returns an empty dict (not an exception) on failure.
    """
    try:
        return await get_latest_solar_wind()
    except Exception as e:
        logger.warning("Solar wind fetch failed in alert check: %s", e)
        return {"source": "fallback"}


async def _safe_get_visibility_score(lat: float, lon: float) -> float | None:
    """
    Compute visibility score for a location.
    Returns None (not an exception) on failure.
    """
    try:
        result = await compute_visibility_score(
            latitude=lat,
            longitude=lon,
            weights={
                "aurora":   VISIBILITY_WEIGHT_AURORA_PROBABILITY,
                "cloud":    VISIBILITY_WEIGHT_CLOUD_COVER,
                "darkness": VISIBILITY_WEIGHT_DARKNESS,
            },
        )
        return result.get("visibility_score")
    except Exception as e:
        logger.warning("Visibility score failed in alert check for (%s, %s): %s", lat, lon, e)
        return None


async def _check_noaa_alerts() -> str | None:
    """
    Fetch active NOAA geomagnetic alerts and return the most severe message,
    or None if no active alerts are present.

    Defensively parsed — NOAA schema changed March 31, 2026.
    """
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(NOAA_ALERTS_URL)
            resp.raise_for_status()
            data = resp.json()

        if not isinstance(data, list) or not data:
            return None

        # Return the message from the first (most recent) alert
        first = data[0]
        if not isinstance(first, dict):
            return None

        msg = first.get("message", "")
        product_id = first.get("product_id", "")

        if msg:
            # Trim to first 120 chars for alert summary — full text via /space-weather/alerts
            summary = msg.strip()[:120].replace("\n", " ")
            return f"[{product_id}] {summary}..." if len(msg) > 120 else f"[{product_id}] {summary}"

    except Exception as e:
        logger.warning("NOAA alert fetch failed: %s", e)

    return None


def _recommended_action(
    triggered: bool,
    reasons: list[str],
    vis_score: float | None,
    bz_now: float | None,
) -> str:
    """
    Generate a concise, field-ready recommended action string.
    Tone is urgent and specific — designed for low-light field use.
    """
    if not triggered:
        return "Conditions are quiet. Set an alert and check back later."

    # Urgent physical triggers take priority over score threshold
    if bz_now is not None and bz_now < -10.0:
        return (
            "⚡ URGENT: Strong southward Bz detected. Get to a dark location immediately. "
            "Aurora may be visible right now."
        )

    if bz_now is not None and bz_now < BZ_ALERT_THRESHOLD_NT:
        return (
            "🔴 Bz is southward. Head outside or to your nearest dark site now. "
            "Display could start within minutes."
        )

    if vis_score is not None and vis_score >= 75:
        return (
            "🟢 Excellent conditions. Get to your observation spot and start shooting. "
            "Wide-angle, f/2.8, ISO 1600, 15–20s exposures recommended."
        )

    if vis_score is not None and vis_score >= 50:
        return (
            "🟡 Good conditions. Head out to a dark site within the next 30 minutes. "
            "Monitor cloud cover — gaps may open."
        )

    return (
        "🟠 Alert triggered on partial conditions. "
        "Monitor closely and be ready to move if conditions improve."
    )