"""Priority scoring module for disaster-affected areas.

Implements Module 2 of the Emergency Decision Support System:
Formula:
    priority_i = w1*norm(impact_i) + w2*norm(predicted_demand_i)
               + w3*norm(shortage_i) + w4*norm(medical_need_i)
               + w5*accessibility_penalty_i

- Uses min-max normalization inside the scenario.
- Configurable weights and risk thresholds (LOW, MEDIUM, HIGH, CRITICAL).
- Full decomposition of priority scores for explainability and auditing.
"""

from __future__ import annotations

import os
import sys
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

# Default weights (labelled as ASSUMPTIONS, configurable via UI)
DEFAULT_WEIGHTS: Dict[str, float] = {
    "impact": 0.25,
    "demand": 0.25,
    "shortage": 0.20,
    "medical_need": 0.15,
    "accessibility_penalty": 0.15,
}

# Default risk thresholds (labelled as ASSUMPTIONS)
DEFAULT_THRESHOLDS: Dict[str, float] = {
    "LOW_MAX": 0.25,
    "MEDIUM_MAX": 0.50,
    "HIGH_MAX": 0.75,
}

SEVERITY_WEIGHT_MAP: Dict[str, float] = {
    "LOW": 0.15,
    "MEDIUM": 0.40,
    "HIGH": 0.70,
    "CRITICAL": 1.00,
}


def min_max_normalize(series: pd.Series) -> pd.Series:
    """Min-max normalizes a numeric series into [0, 1] safely.

    Args:
        series: Pandas numeric series.

    Returns:
        Series scaled between 0.0 and 1.0.
    """
    s_min = series.min()
    s_max = series.max()
    if pd.isna(s_min) or pd.isna(s_max) or s_max == s_min:
        return pd.Series(0.0, index=series.index)
    return (series - s_min) / (s_max - s_min)


def compute_accessibility_penalties(
    areas: List[str], roads_df: Optional[pd.DataFrame] = None
) -> Dict[str, float]:
    """Computes access obstruction penalty for each area based on connecting roads.

    BLOCKED = 1.0, DAMAGED = 0.5, OPEN = 0.0.

    Args:
        areas: List of area IDs.
        roads_df: DataFrame of roads connecting nodes.

    Returns:
        Dictionary mapping area_id to accessibility penalty in [0, 1].
    """
    penalties: Dict[str, float] = {a: 0.0 for a in areas}
    if roads_df is None or roads_df.empty:
        return penalties

    road_status_scores = {"BLOCKED": 1.0, "DAMAGED": 0.5, "OPEN": 0.0}

    for area in areas:
        connected = roads_df[(roads_df["source"] == area) | (roads_df["destination"] == area)]
        if not connected.empty:
            statuses = connected["road_status"].map(road_status_scores).fillna(0.0)
            penalties[area] = float(statuses.mean())
        else:
            penalties[area] = 0.0

    return penalties


def classify_risk_level(
    score: float, thresholds: Optional[Dict[str, float]] = None
) -> str:
    """Classifies a priority score into a standard risk category.

    Args:
        score: Priority score in [0, 1].
        thresholds: Dictionary of threshold boundaries.

    Returns:
        Risk level string: 'LOW', 'MEDIUM', 'HIGH', or 'CRITICAL'.
    """
    th = thresholds or DEFAULT_THRESHOLDS
    if score >= th.get("HIGH_MAX", 0.75):
        return "CRITICAL"
    if score >= th.get("MEDIUM_MAX", 0.50):
        return "HIGH"
    if score >= th.get("LOW_MAX", 0.25):
        return "MEDIUM"
    return "LOW"


def calculate_area_priorities(
    areas_df: pd.DataFrame,
    roads_df: Optional[pd.DataFrame] = None,
    weights: Optional[Dict[str, float]] = None,
    thresholds: Optional[Dict[str, float]] = None,
) -> pd.DataFrame:
    """Calculates normalized priority scores and risk tiers for all areas.

    Args:
        areas_df: DataFrame containing area data, damage metrics, population,
                  and predicted_severity.
        roads_df: Optional DataFrame of roads for accessibility analysis.
        weights: Dictionary of component weights.
        thresholds: Dictionary of risk classification thresholds.

    Returns:
        DataFrame enriched with 'priority_score', 'priority_level',
        and decomposition columns.
    """
    df = areas_df.copy()
    w = weights or DEFAULT_WEIGHTS
    th = thresholds or DEFAULT_THRESHOLDS

    # Normalize weights so they sum to 1.0
    w_sum = sum(w.values()) if sum(w.values()) > 0 else 1.0
    norm_w = {k: v / w_sum for k, v in w.items()}

    # 1. Impact: structural damage modulated by predicted severity
    sev_weights = df["predicted_severity"].map(SEVERITY_WEIGHT_MAP).fillna(0.3)
    bldg_dmg = df["building_damage"].fillna(0) if "building_damage" in df else pd.Series(0, index=df.index)
    impact_raw = bldg_dmg * sev_weights + sev_weights * 100.0

    # 2. Predicted Demand: proportional to affected population
    if "estimated_affected" in df.columns:
        demand_raw = df["estimated_affected"].fillna(0)
    elif "population" in df.columns:
        demand_raw = df["population"] * sev_weights
    else:
        demand_raw = pd.Series(100.0, index=df.index)

    # 3. Shortage: unmet need estimate (if available)
    if "total_shortage" in df.columns:
        shortage_raw = df["total_shortage"].fillna(0)
    else:
        shortage_raw = demand_raw * 0.5  # Initial baseline proxy

    # 4. Medical Need: vulnerable demographic groups + injured
    elderly = df["elderly_population"].fillna(0) if "elderly_population" in df.columns else 0
    children = df["children_population"].fillna(0) if "children_population" in df.columns else 0
    medical_raw = elderly * 1.5 + children * 1.2

    # 5. Accessibility Penalty
    areas_list = df["area_id"].astype(str).tolist()
    penalties_dict = compute_accessibility_penalties(areas_list, roads_df)
    access_raw = df["area_id"].astype(str).map(penalties_dict).fillna(0.0)

    # Normalization inside current scenario
    norm_impact = min_max_normalize(impact_raw)
    norm_demand = min_max_normalize(demand_raw)
    norm_shortage = min_max_normalize(shortage_raw)
    norm_medical = min_max_normalize(medical_raw)
    norm_access = access_raw.clip(0.0, 1.0)  # already bounded [0, 1]

    # Weighted Priority Score
    priority_score = (
        norm_w["impact"] * norm_impact +
        norm_w["demand"] * norm_demand +
        norm_w["shortage"] * norm_shortage +
        norm_w["medical_need"] * norm_medical +
        norm_w["accessibility_penalty"] * norm_access
    ).clip(0.0, 1.0)

    # Risk level classification
    priority_level = priority_score.apply(lambda s: classify_risk_level(s, th))

    # Add results and component breakdowns
    df["priority_score"] = priority_score.round(4)
    df["priority_level"] = priority_level
    df["norm_impact"] = norm_impact.round(4)
    df["norm_demand"] = norm_demand.round(4)
    df["norm_shortage"] = norm_shortage.round(4)
    df["norm_medical_need"] = norm_medical.round(4)
    df["norm_accessibility_penalty"] = norm_access.round(4)

    # Weighted contributions for SHAP-style breakdown
    df["comp_impact"] = (norm_w["impact"] * norm_impact).round(4)
    df["comp_demand"] = (norm_w["demand"] * norm_demand).round(4)
    df["comp_shortage"] = (norm_w["shortage"] * norm_shortage).round(4)
    df["comp_medical_need"] = (norm_w["medical_need"] * norm_medical).round(4)
    df["comp_accessibility"] = (norm_w["accessibility_penalty"] * norm_access).round(4)

    return df
