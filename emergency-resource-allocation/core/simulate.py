"""What-If scenario simulation, multi-scenario comparison, and optimization impact.

Implements Module 7 & 8 of the Emergency Decision Support System:
- Re-runs the complete pipeline under dynamic parameter shifts:
  Supply shifts (+/-%), population shifts (+/-%), severity escalations, duration changes.
- Computes before vs after operational shifts: critical areas, shortages, coverages, dispatches.
- Generates side-by-side Scenario A vs Scenario B comparative analytics.
- Computes exact mathematical impact of LP Optimization vs Proportional Baseline.
"""

from __future__ import annotations

import os
import sys
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import joblib

_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

from core.data import load_all_data, prepare_ml_dataset
from core.model import predict_damage_severity
from core.demand import compute_area_demands, calculate_shortage_and_coverage, DEFAULT_PER_CAPITA_NEEDS
from core.priority import calculate_area_priorities
from core.optimizer import optimize_resource_allocation
from core.actions import generate_action_cards, generate_operational_warnings


def run_full_pipeline(
    datasets: Optional[Dict[str, pd.DataFrame]] = None,
    data_dir: str = "data",
    model_path: str = "models/best_model.pkl",
    encoder_path: str = "models/label_encoder.pkl",
    duration_days: float = 3.0,
    per_capita_needs: Optional[Dict[str, float]] = None,
    priority_weights: Optional[Dict[str, float]] = None,
    priority_thresholds: Optional[Dict[str, float]] = None,
    resource_supply_deltas: Optional[Dict[str, float]] = None,
    population_delta_pct: float = 0.0,
    severity_boost: bool = False,
    affected_population_multiplier: float = 1.0,
    minimum_service_fraction: float = 0.25,
) -> Dict[str, Any]:
    """Executes the complete decision support chain with optional parameter mutations.

    Chain:
        Data -> ML Prediction -> Demand & Shortage -> Area Priority -> LP Optimizer
             -> Recommended Action Cards -> Warnings -> Audit Metric Summary.

    Args:
        datasets: Preloaded dataset dictionary (if None, loaded from data_dir).
        data_dir: Path to CSV data directory.
        model_path: Path to serialized trained model.
        encoder_path: Path to label encoder.
        duration_days: Mission duration assumption in days.
        per_capita_needs: Resource demand rates per person per day.
        priority_weights: Normalization weighting vector.
        priority_thresholds: Risk classification cutoffs.
        resource_supply_deltas: Percentage deltas for supplies (e.g. {'Water': -30.0}).
        population_delta_pct: Population shift percentage (e.g. +15.0).
        severity_boost: Whether to escalate damage severity by one tier.

    Returns:
        Complete operational state dictionary with allocation, KPIs, and cards.
    """
    if datasets is None:
        datasets = load_all_data(data_dir)

    # 1. Feature Preparation
    df_ml = prepare_ml_dataset(datasets)
    if "reported_affected" in df_ml:
        df_ml["reported_affected"] = pd.to_numeric(df_ml["reported_affected"], errors="coerce")

    # Apply population shift
    if population_delta_pct != 0.0:
        pop_mult = max(0.1, 1.0 + (population_delta_pct / 100.0))
        df_ml["population"] = (df_ml["population"] * pop_mult).round().astype(int)
        for demographic in ["elderly_population", "children_population"]:
            if demographic in df_ml:
                df_ml[demographic] = (df_ml[demographic] * pop_mult).round().astype(int)
        df_ml["population_density"] = df_ml["population_density"] * pop_mult
        if "reported_affected" in df_ml:
            df_ml["reported_affected"] = (df_ml["reported_affected"] * pop_mult).round().clip(upper=df_ml["population"])

    # 2. ML Severity Prediction
    if not os.path.exists(model_path):
        model_path = "models/damage_model.pkl"
    model = joblib.load(model_path)
    encoder = joblib.load(encoder_path) if os.path.exists(encoder_path) else None

    preds, proba, classes = predict_damage_severity(model, df_ml, label_encoder=encoder, return_proba=True)
    df_ml["predicted_severity"] = preds
    if proba is not None:
        df_ml["prediction_confidence"] = np.max(proba, axis=1)

    # Optional severity boost for worst-case stress testing
    if severity_boost:
        tier_map = {"LOW": "MEDIUM", "MEDIUM": "HIGH", "HIGH": "CRITICAL", "CRITICAL": "CRITICAL"}
        df_ml["predicted_severity"] = df_ml["predicted_severity"].map(tier_map).fillna("HIGH")

    # 3. Demand & Shortage Computation
    df_demand = compute_area_demands(
        df_ml,
        per_capita_needs=per_capita_needs,
        duration_days=duration_days,
        use_affected_only=True
    )
    if affected_population_multiplier != 1.0:
        if not np.isfinite(affected_population_multiplier) or affected_population_multiplier < 0:
            raise ValueError("Affected population multiplier must be finite and non-negative.")
        df_demand["estimated_affected"] = np.minimum(
            df_demand["population"],
            (df_demand["estimated_affected"] * affected_population_multiplier).round(),
        ).astype(int)
        df_demand = compute_area_demands(df_demand, per_capita_needs, duration_days)

    # An entered affected count takes precedence over the model-derived planning
    # estimate and severity multiplier. Population shocks scale both counts.
    if "reported_affected" in df_demand:
        known = df_demand["reported_affected"].notna()
        df_demand.loc[known, "estimated_affected"] = df_demand.loc[known, "reported_affected"].astype(int)
        df_demand = compute_area_demands(df_demand, per_capita_needs, duration_days)

    # 4. Priority Scoring & Normalization
    roads_df = datasets.get("roads", None)
    df_priority = calculate_area_priorities(
        df_demand,
        roads_df=roads_df,
        weights=priority_weights,
        thresholds=priority_thresholds
    )

    # 5. Modify Supply Stockpiles if Deltas Specified
    resources_df = datasets["resources"].copy()
    if resource_supply_deltas:
        for r_type, delta_pct in resource_supply_deltas.items():
            mask = resources_df["resource_type"] == r_type
            if mask.any():
                mult = max(0.0, 1.0 + (delta_pct / 100.0))
                resources_df["quantity"] = resources_df["quantity"].astype(float)
                resources_df.loc[mask, "quantity"] = resources_df.loc[mask, "quantity"] * mult

    # 6. LP Resource Optimization
    opt_result = optimize_resource_allocation(df_priority, resources_df, minimum_service_fraction=minimum_service_fraction)
    alloc_df = opt_result["allocation_df"]

    # 7. Coverage Metrics
    r_types = list(per_capita_needs.keys()) if per_capita_needs else list(DEFAULT_PER_CAPITA_NEEDS.keys())
    tot_demands, tot_supplies, coverages = calculate_shortage_and_coverage(alloc_df, resources_df, r_types)

    # 8. Action Cards & Dynamic Warnings
    cards = generate_action_cards(alloc_df, resource_types=r_types)
    warnings = generate_operational_warnings(alloc_df, coverages, roads_df=roads_df)

    # 9. KPI Aggregates
    crit_count = int((alloc_df["priority_level"] == "CRITICAL").sum())
    high_count = int((alloc_df["priority_level"] == "HIGH").sum())
    total_affected = int(alloc_df["estimated_affected"].sum())

    total_shortage = sum(
        alloc_df[f"opt_shortage_{r}"].sum() for r in r_types if f"opt_shortage_{r}" in alloc_df.columns
    )
    total_allocated = sum(
        alloc_df[f"opt_alloc_{r}"].sum() for r in r_types if f"opt_alloc_{r}" in alloc_df.columns
    )

    return {
        "allocation_df": alloc_df,
        "resources_df": resources_df,
        "action_cards": cards,
        "warnings": warnings,
        "solver_statuses": opt_result["solver_statuses"],
        "is_optimal": opt_result["is_optimal"],
        "service_floors": opt_result["service_floors"],
        "coverages": coverages,
        "total_demands": tot_demands,
        "total_supplies": tot_supplies,
        "kpis": {
            "total_affected_population": total_affected,
            "critical_areas_count": crit_count,
            "high_risk_areas_count": high_count,
            "total_allocated_units": round(float(total_allocated), 1),
            "total_shortage_units": round(float(total_shortage), 1),
            "shortage_reduction_pct": opt_result["summary"]["shortage_reduction_pct"],
            "shortage_reduction_units": opt_result["summary"]["shortage_reduction_units"],
            "execution_time_ms": opt_result["execution_time_ms"]
        },
        "parameters": {
            "duration_days": duration_days,
            "population_delta_pct": population_delta_pct,
            "resource_supply_deltas": resource_supply_deltas or {},
            "severity_boost": severity_boost,
            "affected_population_multiplier": affected_population_multiplier,
            "minimum_service_fraction": minimum_service_fraction,
        }
    }


def compare_two_scenarios(
    res_a: Dict[str, Any],
    res_b: Dict[str, Any],
    name_a: str = "Scenario A (Baseline)",
    name_b: str = "Scenario B (Simulated)"
) -> Dict[str, Any]:
    """Generates quantitative comparison between two pipeline scenarios.

    Computes:
        - Delta shortage (before vs after)
        - Delta coverage %
        - Shifts in critical areas count
        - Area-by-area allocation changes
        - Plotly comparative bar chart
    """
    kpis_a = res_a["kpis"]
    kpis_b = res_b["kpis"]
    cov_a = res_a["coverages"]
    cov_b = res_b["coverages"]

    # Comparative KPI Table
    metrics_comp = [
        {
            "Metric": "Total Affected Population",
            name_a: f"{kpis_a['total_affected_population']:,}",
            name_b: f"{kpis_b['total_affected_population']:,}",
            "Delta": f"{kpis_b['total_affected_population'] - kpis_a['total_affected_population']:+d}"
        },
        {
            "Metric": "Critical Priority Areas",
            name_a: str(kpis_a["critical_areas_count"]),
            name_b: str(kpis_b["critical_areas_count"]),
            "Delta": f"{kpis_b['critical_areas_count'] - kpis_a['critical_areas_count']:+d}"
        },
        {
            "Metric": "Total Shortage (All Units)",
            name_a: f"{kpis_a['total_shortage_units']:,.1f}",
            name_b: f"{kpis_b['total_shortage_units']:,.1f}",
            "Delta": f"{kpis_b['total_shortage_units'] - kpis_a['total_shortage_units']:+,.1f}"
        },
        {
            "Metric": "Total Units Dispatched",
            name_a: f"{kpis_a['total_allocated_units']:,.1f}",
            name_b: f"{kpis_b['total_allocated_units']:,.1f}",
            "Delta": f"{kpis_b['total_allocated_units'] - kpis_a['total_allocated_units']:+,.1f}"
        }
    ]

    for r in cov_a.keys():
        cA = cov_a.get(r, 0.0) * 100.0
        cB = cov_b.get(r, 0.0) * 100.0
        metrics_comp.append({
            "Metric": f"{r} Regional Coverage %",
            name_a: f"{cA:.1f}%",
            name_b: f"{cB:.1f}%",
            "Delta": f"{cB - cA:+.1f}%"
        })

    df_comp = pd.DataFrame(metrics_comp)

    # Plotly Comparison Chart
    fig = go.Figure()
    resources = list(cov_a.keys())
    fig.add_trace(go.Bar(
        name=name_a,
        x=resources,
        y=[cov_a.get(r, 0.0) * 100.0 for r in resources],
        marker_color="#636EFA"
    ))
    fig.add_trace(go.Bar(
        name=name_b,
        x=resources,
        y=[cov_b.get(r, 0.0) * 100.0 for r in resources],
        marker_color="#EF553B"
    ))
    fig.update_layout(
        barmode="group",
        title=f"Regional Coverage Comparison: {name_a} vs {name_b}",
        yaxis_title="Coverage (%)",
        xaxis_title="Resource Type",
        template="plotly_dark",
        yaxis=dict(range=[0, 105]),
        margin=dict(l=40, r=40, t=60, b=40)
    )

    return {
        "comparison_table": df_comp,
        "figure": fig,
        "delta_shortage": round(kpis_b["total_shortage_units"] - kpis_a["total_shortage_units"], 1),
        "delta_critical_areas": kpis_b["critical_areas_count"] - kpis_a["critical_areas_count"]
    }


def compute_optimization_impact(
    allocation_df: pd.DataFrame,
    resource_types: Optional[List[str]] = None
) -> Dict[str, Any]:
    """Computes mathematical gains of LP Optimization versus Proportional Baseline.

    Formula:
        Reduction = Shortage_Base - Shortage_Opt
        Reduction % = (Reduction / Shortage_Base) * 100

    Args:
        allocation_df: DataFrame with opt_shortage_* and baseline_shortage_*.
        resource_types: Resource keys to evaluate.

    Returns:
        Structured breakdown of shortages, reductions, and percentage gains.
    """
    r_types = resource_types or list(DEFAULT_PER_CAPITA_NEEDS.keys())
    summary: Dict[str, Any] = {}

    total_base_shortage = 0.0
    total_opt_shortage = 0.0

    resource_rows = []
    for r in r_types:
        b_col = f"baseline_shortage_{r}"
        o_col = f"opt_shortage_{r}"

        b_short = float(allocation_df[b_col].sum()) if b_col in allocation_df.columns else 0.0
        o_short = float(allocation_df[o_col].sum()) if o_col in allocation_df.columns else 0.0

        diff = max(0.0, b_short - o_short)
        pct = round((diff / b_short) * 100.0, 2) if b_short > 0 else 0.0

        total_base_shortage += b_short
        total_opt_shortage += o_short

        resource_rows.append({
            "Resource": r,
            "Baseline_Shortage": round(b_short, 1),
            "Optimized_Shortage": round(o_short, 1),
            "Shortage_Reduction_Units": round(diff, 1),
            "Reduction_Percent": pct
        })

    total_reduction = max(0.0, total_base_shortage - total_opt_shortage)
    overall_pct = round((total_reduction / total_base_shortage) * 100.0, 2) if total_base_shortage > 0 else 0.0

    return {
        "table": pd.DataFrame(resource_rows),
        "total_baseline_shortage": round(total_base_shortage, 1),
        "total_optimized_shortage": round(total_opt_shortage, 1),
        "total_reduction_units": round(total_reduction, 1),
        "overall_reduction_pct": overall_pct
    }
