"""Demand, shortage, and resource coverage calculation module.

Implements Module 3 of the Emergency Decision Support System:
Formulas:
    demand_ik   = population_i * per_capita_need_k * duration
    shortage_ik = max(0, demand_ik - available_ik)
    coverage_k  = total_available_k / total_demand_k

Per-capita requirements, duration, and severity impact ratios are explicitly
tracked and labelled as "ASSUMPTIONS" in accordance with system design rules.
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

# Labelled ASSUMPTIONS (User-configurable via sidebar sliders)
DEFAULT_PER_CAPITA_NEEDS: Dict[str, float] = {
    "Food": 2.0,         # Rations / person / day [ASSUMPTION]
    "Water": 3.0,        # Litres / person / day [ASSUMPTION]
    "Medical_Kit": 0.05  # Kits / person / day [ASSUMPTION]
}

DEFAULT_DURATION_DAYS: float = 3.0  # Duration of emergency operation [ASSUMPTION]

SEVERITY_AFFECTED_RATIOS: Dict[str, float] = {
    "CRITICAL": 0.85,    # 85% of population in critical areas in acute need [ASSUMPTION]
    "HIGH": 0.55,        # 55% of population in high-risk areas in acute need [ASSUMPTION]
    "MEDIUM": 0.30,      # 30% of population in medium-risk areas in acute need [ASSUMPTION]
    "LOW": 0.10,         # 10% of population in low-risk areas in acute need [ASSUMPTION]
}


def estimate_affected_population(
    population: float,
    severity: str,
    custom_ratios: Optional[Dict[str, float]] = None
) -> int:
    """Estimates the acute affected population requiring aid in an area.

    Args:
        population: Total resident population in the area.
        severity: Assessed or predicted damage severity level.
        custom_ratios: Optional override for severity affected ratios.

    Returns:
        Integer count of affected residents.
    """
    ratios = custom_ratios or SEVERITY_AFFECTED_RATIOS
    ratio = ratios.get(str(severity).upper(), 0.30)
    return int(max(0, round(population * ratio)))


def compute_area_demands(
    areas_df: pd.DataFrame,
    per_capita_needs: Optional[Dict[str, float]] = None,
    duration_days: float = DEFAULT_DURATION_DAYS,
    use_affected_only: bool = True
) -> pd.DataFrame:
    """Computes exact demand for each resource type across all areas.

    Formula: demand_ik = population_i * per_capita_need_k * duration

    Args:
        areas_df: DataFrame containing area records with population and severity.
        per_capita_needs: Resource consumption standards per person per day.
        duration_days: Mission duration in days.
        use_affected_only: If True, uses affected population rather than total.

    Returns:
        DataFrame containing area identifier, population, and demand columns:
        'demand_Food', 'demand_Water', 'demand_Medical_Kit'.
    """
    df = areas_df.copy()
    needs = per_capita_needs or DEFAULT_PER_CAPITA_NEEDS
    duration = max(0.1, float(duration_days))

    # Ensure estimated affected population is computed
    if "estimated_affected" not in df.columns:
        sev_col = "predicted_severity" if "predicted_severity" in df.columns else "damage_severity"
        df["estimated_affected"] = df.apply(
            lambda r: estimate_affected_population(r.get("population", 1000), r.get(sev_col, "MEDIUM")),
            axis=1
        )

    base_pop = df["estimated_affected"] if use_affected_only else df["population"]

    for resource, rate in needs.items():
        col_name = f"demand_{resource}"
        df[col_name] = (base_pop * float(rate) * duration).round(1)

    return df


def calculate_shortage_and_coverage(
    demand_df: pd.DataFrame,
    resources_df: pd.DataFrame,
    resource_types: Optional[List[str]] = None
) -> Tuple[Dict[str, float], Dict[str, float], Dict[str, float]]:
    """Calculates aggregate total demand, available supply, and coverage ratio.

    Formula:
        coverage_k = total_available_k / total_demand_k

    Args:
        demand_df: DataFrame containing 'demand_{resource}' columns.
        resources_df: DataFrame containing stockpile quantities by resource_type.
        resource_types: List of resource keys to analyze.

    Returns:
        Tuple of (total_demands, total_supplies, coverage_ratios).
    """
    types = resource_types or list(DEFAULT_PER_CAPITA_NEEDS.keys())
    total_demands: Dict[str, float] = {}
    total_supplies: Dict[str, float] = {}
    coverage_ratios: Dict[str, float] = {}

    for r_type in types:
        demand_col = f"demand_{r_type}"
        tot_dem = float(demand_df[demand_col].sum()) if demand_col in demand_df.columns else 0.0
        
        # Aggregate supply from inventory
        avail = float(resources_df[resources_df["resource_type"] == r_type]["quantity"].sum()) \
            if "resource_type" in resources_df.columns and "quantity" in resources_df.columns else 0.0

        total_demands[r_type] = tot_dem
        total_supplies[r_type] = avail

        if tot_dem > 0:
            coverage = min(1.0, max(0.0, avail / tot_dem))
        else:
            coverage = 1.0  # 100% coverage if zero demand

        coverage_ratios[r_type] = round(coverage, 4)

    return total_demands, total_supplies, coverage_ratios


def get_assumptions_metadata() -> Dict[str, Any]:
    """Returns explicit dictionary of all system assumptions for UI labelling."""
    return {
        "per_capita_needs": {
            "values": DEFAULT_PER_CAPITA_NEEDS,
            "unit": "units/person/day",
            "is_assumption": True,
            "description": "Standard WHO/Sphere Project minimum daily emergency relief standards."
        },
        "duration_days": {
            "value": DEFAULT_DURATION_DAYS,
            "unit": "days",
            "is_assumption": True,
            "description": "Planning operational window for initial surge allocation."
        },
        "severity_affected_ratios": {
            "values": SEVERITY_AFFECTED_RATIOS,
            "unit": "fraction",
            "is_assumption": True,
            "description": "Assumed fraction of localized population in critical need per risk level."
        }
    }
