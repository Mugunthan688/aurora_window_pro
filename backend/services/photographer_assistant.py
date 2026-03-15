"""
AuroraWindow Pro — Photographer Assistant Service
Generates aurora photography recommendations based on current conditions.

Provides practical camera settings and shooting tips tailored to:
  - Current aurora intensity (driven by Kp index)
  - Sky darkness (moon phase + Bortle class)
  - Cloud cover conditions
  - Visibility score

Output is designed to be displayed directly in the frontend
photographer panel without any transformation needed.
"""

from config import (
    KP_QUIET,
    KP_ACTIVE,
    KP_MINOR_STORM,
    KP_MODERATE,
    KP_STRONG,
    KP_EXTREME,
    PHOTO_SETTINGS,
)

# ─── Kp to Activity Key ───────────────────────────────────────────────────────

def get_activity_key(kp: float) -> str:
    """
    Maps a Kp index value to a named activity level key.
    Used to look up the correct camera settings from PHOTO_SETTINGS config.

    Args:
        kp: Kp geomagnetic index (0–9)

    Returns:
        Activity key string: "quiet", "active", "minor",
        "moderate", "strong", or "extreme"
    """
    if kp >= KP_EXTREME:
        return "extreme"
    elif kp >= KP_STRONG:
        return "strong"
    elif kp >= KP_MODERATE:
        return "moderate"
    elif kp >= KP_MINOR_STORM:
        return "minor"
    elif kp >= KP_ACTIVE:
        return "active"
    else:
        return "quiet"

# ─── Camera Settings ──────────────────────────────────────────────────────────

def get_photo_settings(kp: float) -> dict:
    """
    Returns recommended camera settings based on the current Kp index.

    Higher Kp = faster aurora movement = shorter shutter speed needed
    to avoid motion blur in the aurora curtains.

    Settings are sourced from the PHOTO_SETTINGS config dict.

    Args:
        kp: Current Kp geomagnetic index (0–9)

    Returns:
        Dict with iso, aperture, shutter_speed keys.
    """
    activity_key = get_activity_key(kp)
    settings     = PHOTO_SETTINGS.get(activity_key, PHOTO_SETTINGS["active"])

    return {
        "iso":           settings["iso"],
        "aperture":      settings["aperture"],
        "shutter_speed": settings["shutter"],
        "activity_key":  activity_key,
    }

# ─── ISO Recommendation ───────────────────────────────────────────────────────

def get_iso_recommendation(
    kp:           float,
    moon_phase:   float = 0.0,
    cloud_cover:  float = 0.0,
) -> dict:
    """
    Refines ISO recommendation based on Kp, moon brightness,
    and cloud cover.

    Logic:
    - Higher Kp → higher base ISO (brighter aurora, faster shutter needed)
    - Full moon → reduce ISO slightly (extra ambient light)
    - Heavy cloud → increase ISO slightly (diffusion dims aurora)

    Args:
        kp:          Current Kp index (0–9)
        moon_phase:  Lunar illumination (0.0=new moon, 1.0=full moon)
        cloud_cover: Cloud cover percentage (0–100)

    Returns:
        Dict with recommended_iso (int), reason (str)
    """
    base_settings = get_photo_settings(kp)
    base_iso      = int(base_settings["iso"])

    adjustments = []
    adjusted_iso = base_iso

    # Full moon adds ambient light — reduce ISO to avoid overexposure
    if moon_phase >= 0.8:
        adjusted_iso = max(400, int(adjusted_iso * 0.6))
        adjustments.append("reduced for bright full moon")
    elif moon_phase >= 0.5:
        adjusted_iso = max(400, int(adjusted_iso * 0.8))
        adjustments.append("slightly reduced for half moon")

    # Heavy cloud diffuses aurora — bump ISO to compensate
    if cloud_cover >= 50:
        adjusted_iso = min(12800, int(adjusted_iso * 1.5))
        adjustments.append("boosted for thick cloud diffusion")
    elif cloud_cover >= 30:
        adjusted_iso = min(12800, int(adjusted_iso * 1.2))
        adjustments.append("slightly boosted for partial cloud")

    # Round ISO to nearest standard value
    standard_isos = [100, 200, 400, 800, 1600, 3200, 6400, 12800]
    adjusted_iso  = min(standard_isos, key=lambda x: abs(x - adjusted_iso))

    reason = (
        f"Base ISO {base_iso} for Kp {kp}"
        + (f" — {', '.join(adjustments)}" if adjustments else "")
    )

    return {
        "recommended_iso": adjusted_iso,
        "base_iso":        base_iso,
        "reason":          reason,
    }

# ─── Shutter Speed Recommendation ────────────────────────────────────────────

def get_shutter_recommendation(
    kp:            float,
    aurora_prob:   float = 50.0,
) -> dict:
    """
    Recommends a shutter speed range based on aurora activity.

    Fast aurora (high Kp) requires shorter exposures to freeze
    the curtain movement. Slow/weak aurora allows longer exposures
    to gather more light.

    Args:
        kp:          Current Kp index
        aurora_prob: Aurora probability % (from OVATION)

    Returns:
        Dict with shutter_speed, min_seconds, max_seconds, tip
    """
    base_settings = get_photo_settings(kp)
    shutter       = base_settings["shutter_speed"]

    # Shutter tip varies by activity level
    if kp >= KP_STRONG:
        tip = (
            "Aurora is moving fast. Keep exposures under 5s "
            "to freeze curtain structure. Use burst mode."
        )
        min_s, max_s = 2, 6
    elif kp >= KP_MINOR_STORM:
        tip = (
            "Active aurora. 6–10s exposures balance sharpness and light. "
            "Watch for rapid brightness changes."
        )
        min_s, max_s = 6, 10
    elif kp >= KP_ACTIVE:
        tip = (
            "Moderate activity. 10–20s exposures work well. "
            "Check focus on stars between shots."
        )
        min_s, max_s = 10, 20
    else:
        tip = (
            "Quiet conditions. Use 20–25s exposures to gather enough light. "
            "Consider stacking multiple frames in post."
        )
        min_s, max_s = 20, 25

    return {
        "shutter_speed":  shutter,
        "min_seconds":    min_s,
        "max_seconds":    max_s,
        "tip":            tip,
    }

# ─── Lens Recommendation ──────────────────────────────────────────────────────

def get_lens_recommendation(kp: float, aurora_prob: float = 50.0) -> dict:
    """
    Recommends lens choice and aperture for aurora photography.

    Aurora photography benefits from:
    - Wide angle (14–24mm) to capture the full oval
    - Fast aperture (f/1.4–f/2.8) to maximise light intake
    - Manual focus set to infinity

    Args:
        kp:          Current Kp index
        aurora_prob: Aurora probability %

    Returns:
        Dict with focal_length, aperture, focus_tip, lens_tip
    """
    settings = get_photo_settings(kp)

    if kp >= KP_STRONG:
        focal_length = "14–20mm"
        lens_note    = (
            "Wide angle essential — aurora may span the full sky. "
            "Include a foreground element for scale."
        )
    elif kp >= KP_MINOR_STORM:
        focal_length = "16–24mm"
        lens_note    = (
            "Standard wide angle works well. "
            "Capture horizon to overhead for full arc shots."
        )
    else:
        focal_length = "20–35mm"
        lens_note    = (
            "Slight telephoto acceptable for faint arc detail. "
            "Wider angle gives better star context."
        )

    return {
        "focal_length":   focal_length,
        "aperture":       settings["aperture"],
        "focus_tip":      "Set manual focus to infinity (∞). Verify on a bright star.",
        "lens_tip":       lens_note,
    }

# ─── Composition Tips ─────────────────────────────────────────────────────────

def get_composition_tips(kp: float, aurora_prob: float = 50.0) -> list:
    """
    Returns a list of shot composition tips based on conditions.

    Tips are ordered by priority — most important first.

    Args:
        kp:          Current Kp index
        aurora_prob: Aurora probability %

    Returns:
        List of tip strings (3–5 tips)
    """
    tips = []

    # Universal tips always included
    tips.append("Face the direction indicated by the azimuth compass in the app.")
    tips.append("Include a dark foreground — trees, water, or hills add depth.")
    tips.append("Set white balance to 3200K–4000K for natural aurora colours.")

    # Activity-specific tips
    if kp >= KP_STRONG:
        tips.append(
            "Aurora is very active. Shoot continuously — "
            "rapid changes make every frame unique."
        )
        tips.append(
            "Try portrait orientation to capture vertical aurora pillars "
            "from horizon to zenith."
        )
    elif kp >= KP_MINOR_STORM:
        tips.append(
            "Look for aurora arcs and rays. "
            "Position the horizon at the lower third of your frame."
        )
        tips.append(
            "If there is a lake or river nearby, reflections "
            "create stunning symmetry shots."
        )
    else:
        tips.append(
            "Faint aurora photographs best with longer exposures. "
            "Use a remote shutter release to avoid camera shake."
        )
        tips.append(
            "Include the Milky Way or bright star fields — "
            "they complement weak aurora beautifully."
        )

    return tips[:5]   # return max 5 tips

# ─── Tripod & Gear Advice ─────────────────────────────────────────────────────

def get_gear_advice(cloud_cover: float, visibility_score: float) -> dict:
    """
    Returns gear and preparation advice based on conditions.

    Args:
        cloud_cover:      Cloud cover percentage (0–100)
        visibility_score: Composite visibility score (0–100)

    Returns:
        Dict with tripod_required, extra_gear, preparation_tips
    """
    extra_gear = [
        "Spare batteries (cold drains them fast)",
        "Lens cloth for condensation",
        "Head torch with red light mode",
        "Warm gloves — camera controls are hard in thick gloves",
    ]

    preparation = []

    if cloud_cover > 40:
        preparation.append(
            "Clouds may clear — be patient and watch the forecast. "
            "Position yourself where you can see gaps forming."
        )
    else:
        preparation.append(
            "Clear sky detected. Arrive early to let your eyes dark-adapt "
            "and to set up your composition before aurora appears."
        )

    if visibility_score >= 75:
        preparation.append(
            "Excellent conditions expected. "
            "This could be a rare high-quality aurora event."
        )
    elif visibility_score >= 50:
        preparation.append(
            "Good conditions. Set your alert threshold and have your gear ready."
        )
    else:
        preparation.append(
            "Conditions are marginal. Keep your gear packed near the door "
            "in case conditions improve suddenly."
        )

    return {
        "tripod_required":  True,          # always required for aurora
        "remote_shutter":   True,          # strongly recommended
        "extra_gear":       extra_gear,
        "preparation_tips": preparation,
    }

# ─── Full Recommendation Package ──────────────────────────────────────────────

def get_full_recommendation(
    kp:               float = 4.0,
    moon_phase:       float = 0.2,
    cloud_cover:      float = 20.0,
    visibility_score: float = 70.0,
    aurora_prob:      float = 60.0,
    azimuth:          float = 347.0,
    elevation_angle:  float = 14.0,
) -> dict:
    """
    Returns a complete photographer recommendation package
    combining all settings, tips, and gear advice.

    This is the main function called by the routing API endpoint
    to build the full photographer route response.

    Args:
        kp:               Current Kp index (0–9)
        moon_phase:       Lunar illumination (0.0–1.0)
        cloud_cover:      Cloud cover % (0–100)
        visibility_score: Composite visibility score (0–100)
        aurora_prob:      Aurora probability % (0–100)
        azimuth:          Direction to face in degrees
        elevation_angle:  How high above horizon to look (degrees)

    Returns:
        Full recommendation dict ready for JSON API response
    """
    activity_key  = get_activity_key(kp)
    photo_settings = get_photo_settings(kp)
    iso_rec       = get_iso_recommendation(kp, moon_phase, cloud_cover)
    shutter_rec   = get_shutter_recommendation(kp, aurora_prob)
    lens_rec      = get_lens_recommendation(kp, aurora_prob)
    comp_tips     = get_composition_tips(kp, aurora_prob)
    gear_advice   = get_gear_advice(cloud_cover, visibility_score)

    # Direction label for azimuth
    direction_label = _azimuth_to_compass(azimuth)

    return {
        "activity_level":    activity_key,
        "kp":                kp,
        "camera_settings": {
            "iso":           iso_rec["recommended_iso"],
            "aperture":      photo_settings["aperture"],
            "shutter_speed": shutter_rec["shutter_speed"],
            "shutter_range": f"{shutter_rec['min_seconds']}–{shutter_rec['max_seconds']}s",
        },
        "direction": {
            "azimuth":         azimuth,
            "compass_label":   direction_label,
            "elevation_angle": elevation_angle,
            "instruction":     (
                f"Face {direction_label} ({azimuth}°) and look "
                f"{elevation_angle}° above the horizon."
            ),
        },
        "lens":              lens_rec,
        "composition_tips":  comp_tips,
        "gear_advice":       gear_advice,
        "iso_note":          iso_rec["reason"],
        "shutter_tip":       shutter_rec["tip"],
    }

# ─── Azimuth to Compass Label ─────────────────────────────────────────────────

def _azimuth_to_compass(azimuth: float) -> str:
    """
    Converts a bearing in degrees to a compass direction label.

    Args:
        azimuth: Direction in degrees (0 = North, 90 = East)

    Returns:
        Compass label string e.g. "NNW", "NE", "SSE"
    """
    directions = [
        "N", "NNE", "NE", "ENE",
        "E", "ESE", "SE", "SSE",
        "S", "SSW", "SW", "WSW",
        "W", "WNW", "NW", "NNW",
    ]
    index = round(azimuth / 22.5) % 16
    return directions[index]