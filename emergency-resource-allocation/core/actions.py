"""Recommended actions generator and dynamic operations warnings.

Implements Module 5 of the Emergency Decision Support System:
- Generates structured Action Cards quoting exact optimizer outputs.
- Formulates real-number-backed operational reasons and before->after impact.
- Produces 'No Action Needed' statuses for fully satisfied or low-risk areas.
- Evaluates dynamic risk warnings (critical deficits, low coverage, blocked transit).
"""

from __future__ import annotations

import os
import sys
from typing import Any, Dict, List, Optional
import pandas as pd

_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

from core.demand import DEFAULT_PER_CAPITA_NEEDS


def generate_action_cards(
    allocation_df: pd.DataFrame,
    resource_types: Optional[List[str]] = None,
    min_allocation_threshold: float = 0.1
) -> List[Dict[str, Any]]:
    """Generates clear, number-backed operational action cards for emergency teams.

    Args:
        allocation_df: Output DataFrame from optimizer containing demands,
                       opt_alloc_{res}, opt_shortage_{res}, and priority metadata.
        resource_types: List of resource types to evaluate.
        min_allocation_threshold: Minimum quantity to warrant a dispatch card.

    Returns:
        List of structured Action Card dictionaries.
    """
    cards: List[Dict[str, Any]] = []
    r_types = resource_types or list(DEFAULT_PER_CAPITA_NEEDS.keys())

    # Sort areas by priority score descending
    sorted_df = allocation_df.sort_values(
        by="priority_score", ascending=False
    ).copy()

    for _, row in sorted_df.iterrows():
        area_id = str(row["area_id"])
        area_name = str(row.get("area_name", f"Area {area_id}"))
        p_score = float(row.get("priority_score", 0.0))
        p_level = str(row.get("priority_level", "MEDIUM"))
        p_severity = str(row.get("predicted_severity", "MEDIUM"))
        affected_pop = int(row.get("estimated_affected", row.get("population", 0)))
        destroyed_bldg = int(row.get("destroyed_buildings", 0))

        area_dispatches = 0

        for r_type in r_types:
            demand = float(row.get(f"demand_{r_type}", 0.0))
            allocated = float(row.get(f"opt_alloc_{r_type}", 0.0))
            post_shortage = float(row.get(f"opt_shortage_{r_type}", max(0.0, demand - allocated)))
            pre_shortage = demand

            unit = "L" if r_type == "Water" else ("rations" if r_type == "Food" else "kits")

            if allocated >= min_allocation_threshold:
                area_dispatches += 1
                shortage_reduction = pre_shortage - post_shortage
                reduction_pct = round((shortage_reduction / pre_shortage) * 100.0, 1) if pre_shortage > 0 else 100.0

                reason = (
                    f"{area_name} holds {p_level} relative priority (score {p_score:.2f}) with {affected_pop:,} affected "
                    f"residents and {destroyed_bldg} destroyed structures. Predicted severity is {p_severity}."
                )

                expected_effect = (
                    f"Shortage reduced from {pre_shortage:,.1f} {unit} to {post_shortage:,.1f} {unit} "
                    f"({reduction_pct}% unmet need eliminated)."
                )

                cards.append({
                    "card_type": "DISPATCH_ACTION",
                    "priority_level": p_level,
                    "priority_score": round(p_score, 4),
                    "area_id": area_id,
                    "area_name": area_name,
                    "resource": r_type,
                    "quantity": allocated,
                    "unit": unit,
                    "initial_demand": round(demand, 1),
                    "shortage_before": round(pre_shortage, 1),
                    "shortage_after": round(post_shortage, 1),
                    "reduction_pct": reduction_pct,
                    "reason": reason,
                    "expected_effect": expected_effect,
                    "status": "RECOMMENDED"
                })

        # Zero allocation is not evidence that need has been met.
        if area_dispatches == 0:
            unmet = sum(float(row.get(f"opt_shortage_{r}", 0)) for r in r_types)
            cards.append({
                "card_type": "UNMET_NEED" if unmet > 0 else "NO_ACTION_NEEDED",
                "priority_level": p_level,
                "priority_score": round(p_score, 4),
                "area_id": area_id,
                "area_name": area_name,
                "resource": "ALL",
                "quantity": 0.0,
                "unit": "N/A",
                "initial_demand": unmet,
                "shortage_before": unmet,
                "shortage_after": unmet,
                "reduction_pct": 0.0 if unmet > 0 else 100.0,
                "reason": (
                    f"{area_name} ({p_level} priority, score {p_score:.2f}) has unmet demand and no available dispatch." if unmet > 0 else
                    f"{area_name} ({p_level} priority, score {p_score:.2f}) has sufficient local capacity "
                    f"or zero acute unmet demand in current planning window."
                ),
                "expected_effect": "Request additional supplies." if unmet > 0 else "No immediate supply dispatch required; maintain monitoring.",
                "status": "UNMET" if unmet > 0 else "SUFFICIENT"
            })

    return cards


def generate_operational_warnings(
    allocation_df: pd.DataFrame,
    coverage_ratios: Dict[str, float],
    roads_df: Optional[pd.DataFrame] = None
) -> List[Dict[str, Any]]:
    """Evaluates multi-domain operational safety warnings for command leadership.

    Args:
        allocation_df: Optimizer allocation results.
        coverage_ratios: Resource coverage fractions from demand calculation.
        roads_df: Road accessibility status table.

    Returns:
        List of warning alert dictionaries.
    """
    warnings: List[Dict[str, Any]] = []

    # 1. Macro Resource Coverage Bottleneck Warning
    for r_type, cov in coverage_ratios.items():
        if cov < 0.50:
            warnings.append({
                "severity": "CRITICAL",
                "category": "SUPPLY_DEFICIT",
                "title": f"Critical Regional Deficit: {r_type}",
                "message": (
                    f"Overall regional coverage for {r_type} is critically low at {cov * 100.0:.1f}%. "
                    f"Severe rationing is enforced. Immediate mutual-aid replenishment is required."
                )
            })
        elif cov < 0.75:
            warnings.append({
                "severity": "WARNING",
                "category": "SUPPLY_DEFICIT",
                "title": f"Moderate Supply Deficit: {r_type}",
                "message": (
                    f"Regional coverage for {r_type} is at {cov * 100.0:.1f}%. "
                    f"Non-critical sectors may experience partial shortages."
                )
            })

    # 2. Critical Area Unmet Need Warning
    crit_unmet = allocation_df[
        (allocation_df["priority_level"] == "CRITICAL")
    ]
    for _, row in crit_unmet.iterrows():
        area = row.get("area_name", row["area_id"])
        for r in DEFAULT_PER_CAPITA_NEEDS.keys():
            rem_short = float(row.get(f"opt_shortage_{r}", 0.0))
            dem = float(row.get(f"demand_{r}", 0.0))
            if dem > 0 and (rem_short / dem) > 0.25:
                warnings.append({
                    "severity": "CRITICAL",
                    "category": "UNMET_CRITICAL_NEED",
                    "title": f"Unmet Critical Demand in {area}",
                    "message": (
                        f"{area} is classified as CRITICAL (Priority {row['priority_score']:.2f}), "
                        f"yet {rem_short:,.1f} {r} ({rem_short/dem*100.0:.1f}%) remains unmet due to total inventory depletion."
                    )
                })

    # 3. Transport Obstruction Warnings
    if roads_df is not None and not roads_df.empty:
        blocked_roads = roads_df[roads_df["road_status"] == "BLOCKED"]
        for _, r_row in blocked_roads.iterrows():
            warnings.append({
                "severity": "HIGH",
                "category": "TRANSIT_OBSTRUCTION",
                "title": f"Transit Route Blocked: {r_row['source']} -> {r_row['destination']}",
                "message": (
                    f"Artery between {r_row['source']} and {r_row['destination']} is BLOCKED. "
                    f"Ground dispatch convoys must be rerouted or cleared by engineering teams."
                )
            })

    return warnings
