"""
advisor.py - Explainable Rule-Based Smart Irrigation Recommendation Engine
===========================================================================
This module encapsulates the agronomic domain logic used by the Smart Irrigation
Advisor prototype for the DCDSL course project.

Design Principles:
1. Pure functions: Easy to unit test and decouple from UI or database state.
2. Explainability: Returns structured, step-by-step reasoning that explains
   WHY an irrigation recommendation was produced.
3. Realistic Agronomic Heuristics:
   - Crop-specific Management Allowed Depletion (MAD) thresholds.
   - Soil texture infiltration & retention adjustments (Sandy, Loamy, Clay).
   - High evapotranspiration multiplier for hot weather (>32°C).
   - Rainfall suppression logic: avoids wasting water when natural rain is imminent.
   - Waterlogging & hypoxia prevention safety check (>75% saturation).
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


# Crop-specific moisture thresholds (percentage of volumetric field capacity)
CROP_THRESHOLDS = {
    "Tomato": {"min_moisture": 35.0, "optimal_moisture": 50.0, "liters_per_pct_acre": 1200.0},
    "Rice": {"min_moisture": 55.0, "optimal_moisture": 75.0, "liters_per_pct_acre": 2200.0},
    "Wheat": {"min_moisture": 30.0, "optimal_moisture": 45.0, "liters_per_pct_acre": 1100.0},
    "Cotton": {"min_moisture": 25.0, "optimal_moisture": 40.0, "liters_per_pct_acre": 900.0},
    "Maize": {"min_moisture": 32.0, "optimal_moisture": 48.0, "liters_per_pct_acre": 1150.0},
}

DEFAULT_CROP_CONFIG = {"min_moisture": 30.0, "optimal_moisture": 45.0, "liters_per_pct_acre": 1100.0}

SOIL_FACTORS = {
    "Sandy": 1.15,  # High percolation, dries faster, requires 15% more frequent/light application
    "Loamy": 1.00,  # Balanced reference baseline
    "Clay": 0.85,   # High water retention, lower application rate to prevent pooling
    "Silt": 0.95,
    "Peaty": 0.90,
}


@dataclass
class RecommendationResult:
    """Structured result returned by the recommendation engine."""
    status_code: str             # 'IRRIGATE', 'POSTPONE_RAIN', 'OPTIMAL', 'WATERLOG_RISK'
    status_title: str            # Short human-readable headline
    urgency: str                 # 'CRITICAL', 'HIGH', 'MODERATE', 'LOW', 'NONE'
    recommended_liters: float    # Total recommended volume in Liters
    recommended_duration_min: int  # Estimated drip/sprinkler run time in minutes
    reasons: List[str] = field(default_factory=list)      # Step-by-step explainable reasons
    rules_fired: List[str] = field(default_factory=list)  # Formal rule codes for traceability
    metrics_snapshot: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status_code": self.status_code,
            "status_title": self.status_title,
            "urgency": self.urgency,
            "recommended_liters": round(self.recommended_liters, 2),
            "recommended_duration_min": self.recommended_duration_min,
            "reasons": self.reasons,
            "rules_fired": self.rules_fired,
            "metrics_snapshot": self.metrics_snapshot,
        }


def calculate_irrigation_recommendation(
    soil_moisture_pct: float,
    rainfall_forecast_24h_mm: float,
    rainfall_last_24h_mm: float = 0.0,
    soil_temperature_c: float = 25.0,
    crop_type: str = "Wheat",
    area_acres: float = 1.0,
    soil_type: str = "Loamy",
) -> RecommendationResult:
    """
    Evaluates telemetry data against explainable rule-based logic to yield
    an actionable irrigation decision.

    Input Validation:
    - soil_moisture_pct must be between 0.0 and 100.0.
    - area_acres must be strictly positive.
    - rainfall values must be non-negative.
    """
    # ------------------------------------------------------------------
    # Step 0: Input Sanitization & Validation
    # ------------------------------------------------------------------
    if not (0.0 <= soil_moisture_pct <= 100.0):
        raise ValueError(f"Soil moisture ({soil_moisture_pct}%) must be between 0.0 and 100.0.")
    if area_acres <= 0.0:
        raise ValueError(f"Farm area ({area_acres} acres) must be greater than 0.")
    if rainfall_forecast_24h_mm < 0.0 or rainfall_last_24h_mm < 0.0:
        raise ValueError("Rainfall values cannot be negative.")

    crop_conf = CROP_THRESHOLDS.get(crop_type, DEFAULT_CROP_CONFIG)
    min_moisture = crop_conf["min_moisture"]
    optimal_moisture = crop_conf["optimal_moisture"]
    soil_multiplier = SOIL_FACTORS.get(soil_type, 1.0)

    reasons: List[str] = []
    rules_fired: List[str] = []
    snapshot = {
        "soil_moisture_pct": soil_moisture_pct,
        "crop_min_threshold_pct": min_moisture,
        "crop_optimal_target_pct": optimal_moisture,
        "rainfall_forecast_mm": rainfall_forecast_24h_mm,
        "rainfall_last_24h_mm": rainfall_last_24h_mm,
        "temperature_c": soil_temperature_c,
        "crop_type": crop_type,
        "soil_type": soil_type,
        "area_acres": area_acres,
    }

    # ------------------------------------------------------------------
    # Step 1: Rule R1 - High Moisture / Waterlogging Protection
    # ------------------------------------------------------------------
    if soil_moisture_pct >= 75.0:
        rules_fired.append("R1_WATERLOG_PROTECTION")
        reasons.append(
            f"Soil moisture is at {soil_moisture_pct:.1f}%, exceeding the 75% saturation barrier."
        )
        reasons.append(
            "Excessive watering risks root asphyxiation, nutrient leaching, and fungal infections."
        )
        return RecommendationResult(
            status_code="WATERLOG_RISK",
            status_title="Warning: Soil Near Saturation",
            urgency="NONE",
            recommended_liters=0.0,
            recommended_duration_min=0,
            reasons=reasons,
            rules_fired=rules_fired,
            metrics_snapshot=snapshot,
        )

    # ------------------------------------------------------------------
    # Step 2: Rule R2 - Imminent Heavy Rain Postponement
    # ------------------------------------------------------------------
    # If substantial rain is expected (>= 12 mm) and soil is not in emergency drought (< 15%),
    # postpone irrigation to conserve water and prevent runoff.
    if rainfall_forecast_24h_mm >= 12.0 and soil_moisture_pct >= 15.0:
        rules_fired.append("R2_HEAVY_RAIN_SUPPRESSION")
        reasons.append(
            f"Forecast predicts {rainfall_forecast_24h_mm:.1f} mm of rainfall within the next 24 hours."
        )
        reasons.append(
            f"Current soil moisture ({soil_moisture_pct:.1f}%) is above critical emergency level (15%)."
        )
        reasons.append(
            "Water Conservation Principle: Natural precipitation will satisfy crop water demand; artificial irrigation is postponed."
        )
        return RecommendationResult(
            status_code="POSTPONE_RAIN",
            status_title="Postpone: Significant Rainfall Forecast",
            urgency="LOW",
            recommended_liters=0.0,
            recommended_duration_min=0,
            reasons=reasons,
            rules_fired=rules_fired,
            metrics_snapshot=snapshot,
        )

    # ------------------------------------------------------------------
    # Step 3: Rule R3 - Moisture Status Check (Deficit vs Adequate)
    # ------------------------------------------------------------------
    if soil_moisture_pct >= min_moisture:
        rules_fired.append("R3_MOISTURE_ADEQUATE")
        reasons.append(
            f"Current moisture ({soil_moisture_pct:.1f}%) satisfies the minimum threshold for {crop_type} ({min_moisture:.1f}%)."
        )
        reasons.append(
            f"Soil water content is currently adequate. Target optimal range is {min_moisture:.1f}% - {optimal_moisture:.1f}%."
        )
        if rainfall_forecast_24h_mm > 0:
            reasons.append(
                f"Additionally, {rainfall_forecast_24h_mm:.1f} mm of light rain is expected, providing natural top-up."
            )
        return RecommendationResult(
            status_code="OPTIMAL",
            status_title="Moisture Levels Optimal - No Water Needed",
            urgency="NONE",
            recommended_liters=0.0,
            recommended_duration_min=0,
            reasons=reasons,
            rules_fired=rules_fired,
            metrics_snapshot=snapshot,
        )

    # ------------------------------------------------------------------
    # Step 4: Rule R4 & R5 - Moisture Deficit Calculation & Dosing
    # ------------------------------------------------------------------
    rules_fired.append("R4_MOISTURE_DEFICIT_DETECTED")
    moisture_deficit_pct = optimal_moisture - soil_moisture_pct
    reasons.append(
        f"Soil moisture ({soil_moisture_pct:.1f}%) has dropped below the threshold ({min_moisture:.1f}%) for {crop_type}."
    )
    reasons.append(
        f"Calculated deficit to reach optimal target ({optimal_moisture:.1f}%): {moisture_deficit_pct:.1f}%."
    )

    # Base volumetric dose: (deficit %) * (liters required per % per acre for crop) * (area)
    base_liters = moisture_deficit_pct * crop_conf["liters_per_pct_acre"] * area_acres

    # Adjust for soil texture
    adjusted_liters = base_liters * soil_multiplier
    if soil_multiplier != 1.0:
        rules_fired.append("R5_SOIL_TEXTURE_ADJUSTED")
        direction = "increased" if soil_multiplier > 1.0 else "moderated"
        reasons.append(
            f"Soil texture '{soil_type}' adjustment factor ({soil_multiplier:.2f}x) {direction} baseline dosage."
        )

    # Evapotranspiration Temperature adjustment
    temp_factor = 1.0
    if soil_temperature_c >= 33.0:
        temp_factor = 1.15
        rules_fired.append("R6_HIGH_EVAPOTRANSPIRATION")
        reasons.append(
            f"Elevated temperature ({soil_temperature_c:.1f}°C) triggers a +15% dosage buffer against evaporation loss."
        )
    elif soil_temperature_c <= 18.0:
        temp_factor = 0.90
        rules_fired.append("R6_LOW_EVAPOTRANSPIRATION")
        reasons.append(
            f"Cool temperature ({soil_temperature_c:.1f}°C) reduces evapotranspiration; dosage lowered by -10%."
        )
    adjusted_liters *= temp_factor

    # Moderate rainfall deduction (if light/moderate rain is expected, e.g. 1mm - 11mm)
    if rainfall_forecast_24h_mm > 0.0:
        # 1 mm of rain over 1 acre = ~4046.86 Liters. With 60% effective soil penetration: ~2400 L/acre.
        rain_credit_liters = rainfall_forecast_24h_mm * 2400.0 * area_acres
        deduction = min(adjusted_liters * 0.70, rain_credit_liters)  # Cap deduction at 70% to ensure stability
        adjusted_liters = max(adjusted_liters - deduction, 500.0 * area_acres)
        rules_fired.append("R7_PARTIAL_RAIN_CREDIT")
        reasons.append(
            f"Credited anticipated rainfall ({rainfall_forecast_24h_mm:.1f} mm): reduced required artificial dosage by {deduction:.0f} L."
        )

    # Determine Urgency
    if soil_moisture_pct <= 20.0:
        urgency = "CRITICAL"
        status_title = "Critical Irrigation Required Immediately"
        reasons.append("Urgency is CRITICAL: Crop is approaching Permanent Wilting Point (PWP).")
    elif (min_moisture - soil_moisture_pct) > 8.0:
        urgency = "HIGH"
        status_title = "Irrigation Recommended (High Priority)"
    else:
        urgency = "MODERATE"
        status_title = "Routine Irrigation Recommended"

    # Runtime estimation (assuming standard drip/sprinkler flow rate ~100 Liters/min per acre)
    flow_rate_lpm = 100.0 * area_acres
    estimated_duration_min = max(int(adjusted_liters / flow_rate_lpm), 10)

    return RecommendationResult(
        status_code="IRRIGATE",
        status_title=status_title,
        urgency=urgency,
        recommended_liters=round(adjusted_liters, 1),
        recommended_duration_min=estimated_duration_min,
        reasons=reasons,
        rules_fired=rules_fired,
        metrics_snapshot=snapshot,
    )
