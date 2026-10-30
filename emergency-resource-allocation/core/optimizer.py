"""Linear programming resource allocation optimizer and baseline comparator.

Implements Module 4 of the Emergency Decision Support System:
Variables:
    x_ik >= 0 (amount of resource k allocated to area i)

Objective:
    Maximize   sum_i sum_k (priority_weight_i * x_ik / demand_ik)
    (Equivalently minimize priority-weighted unmet demand)

Subject to:
    sum_i x_ik <= supply_k           (Supply budget per resource)
    floor_k * demand_ik <= x_ik <= demand_ik
    floor_k = min(requested_floor, supply_k / total_demand_k)
    Optional: transportation distance penalties when warehouse coords exist.

Solver:
    Uses scipy.optimize.linprog with modern 'highs' simplex/interior-point solver.
    Strictly reports "OPTIMAL" only when verified by the solver status code.
    Gracefully handles zero-supply, surplus, and edge constraints.
"""

from __future__ import annotations

import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from scipy.optimize import linprog

_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

from core.demand import DEFAULT_PER_CAPITA_NEEDS


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculates great-circle distance between two GPS coordinates in kilometers."""
    r = 6371.0  # Earth radius in km
    dlat = np.radians(lat2 - lat1)
    dlon = np.radians(lon2 - lon1)
    a = (
        np.sin(dlat / 2.0) ** 2 +
        np.cos(np.radians(lat1)) * np.cos(np.radians(lat2)) * np.sin(dlon / 2.0) ** 2
    )
    c = 2.0 * np.arctan2(np.sqrt(a), np.sqrt(1.0 - a))
    return float(r * c)


def compute_baseline_proportional_allocation(
    areas_df: pd.DataFrame,
    resources_df: pd.DataFrame,
    resource_types: Optional[List[str]] = None
) -> pd.DataFrame:
    """Computes baseline heuristic allocation: equal share proportional to population.

    Formula:
        x_base_ik = min(demand_ik, supply_k * (pop_i / sum_pop))

    Args:
        areas_df: DataFrame with 'area_id', 'population', and 'demand_{resource}'.
        resources_df: DataFrame with 'resource_type' and 'quantity'.
        resource_types: List of resource keys.

    Returns:
        DataFrame with baseline allocated quantities 'baseline_alloc_{resource}'.
    """
    df = areas_df.copy()
    r_types = resource_types or list(DEFAULT_PER_CAPITA_NEEDS.keys())
    total_pop = float(df["population"].sum()) if "population" in df.columns and df["population"].sum() > 0 else 1.0

    for r_type in r_types:
        demand_col = f"demand_{r_type}"
        alloc_col = f"baseline_alloc_{r_type}"
        shortage_col = f"baseline_shortage_{r_type}"

        supply = float(resources_df[resources_df["resource_type"] == r_type]["quantity"].sum()) \
            if "resource_type" in resources_df.columns and "quantity" in resources_df.columns else 0.0

        if demand_col in df.columns:
            # Proportional share capped at demand
            prop_share = (df["population"] / total_pop) * supply
            df[alloc_col] = np.minimum(df[demand_col], prop_share).round(1)
            df[shortage_col] = np.maximum(0.0, df[demand_col] - df[alloc_col]).round(1)
        else:
            df[alloc_col] = 0.0
            df[shortage_col] = 0.0

    return df


def optimize_resource_allocation(
    areas_df: pd.DataFrame,
    resources_df: pd.DataFrame,
    resource_types: Optional[List[str]] = None,
    minimum_service_fraction: float = 0.25,
) -> Dict[str, Any]:
    """Solves the multi-resource priority-weighted Linear Program.

    Objective:
        Maximize sum_i (priority_i * x_ik / demand_ik)
        == Minimize sum_i (-priority_i / demand_ik * x_ik)

    Constraints:
        sum_i x_ik <= total_supply_k
        floor_k * demand_ik <= x_ik <= demand_ik for each area i

    Args:
        areas_df: DataFrame with 'area_id', 'priority_score', and 'demand_{resource}'.
        resources_df: DataFrame with 'resource_type' and 'quantity'.
        resource_types: Optional list of resource types to optimize.
        minimum_service_fraction: Requested demand share reserved for every area;
            reduced to the feasible common share if stock is insufficient.

    Returns:
        Dictionary containing:
            - 'allocation_df': enriched DataFrame with 'opt_alloc_{res}', 'opt_shortage_{res}'
            - 'solver_status': string summary per resource ('OPTIMAL', 'ZERO_SUPPLY', etc.)
            - 'metrics': objective values, runtime, shortage comparisons
    """
    start_time = time.perf_counter()
    df = areas_df.copy().reset_index(drop=True)
    n_areas = len(df)
    r_types = resource_types or list(DEFAULT_PER_CAPITA_NEEDS.keys())

    if not 0 <= minimum_service_fraction <= 1:
        raise ValueError("Minimum service fraction must be between zero and one.")
    # Positive objective weights do not themselves guarantee an allocation.
    if "priority_score" in df.columns:
        p_weights = np.maximum(df["priority_score"].values.astype(float), 0.05)
    else:
        p_weights = np.ones(n_areas, dtype=float)

    solver_statuses: Dict[str, str] = {}
    service_floors: Dict[str, float] = {}
    is_all_optimal = True
    total_opt_shortage: float = 0.0
    total_initial_demand: float = 0.0

    for r_type in r_types:
        demand_col = f"demand_{r_type}"
        alloc_col = f"opt_alloc_{r_type}"
        shortage_col = f"opt_shortage_{r_type}"

        # Get total available supply
        if "resource_type" in resources_df.columns and "quantity" in resources_df.columns:
            tot_supply = float(resources_df[resources_df["resource_type"] == r_type]["quantity"].sum())
        else:
            tot_supply = 0.0

        if demand_col not in df.columns:
            is_all_optimal = False
            df[alloc_col] = 0.0
            df[shortage_col] = 0.0
            solver_statuses[r_type] = "NO_DEMAND_DATA"
            continue

        demands = df[demand_col].values.astype(float)
        if not np.isfinite(demands).all() or (demands < 0).any() or not np.isfinite(tot_supply) or tot_supply < 0:
            raise ValueError("Demand and supply must be finite and non-negative.")
        total_initial_demand += float(demands.sum())

        # Handle zero supply case gracefully without solver failure
        if tot_supply <= 0:
            is_all_optimal = False
            service_floors[r_type] = 0.0
            df[alloc_col] = 0.0
            df[shortage_col] = demands
            total_opt_shortage += float(demands.sum())
            solver_statuses[r_type] = "ZERO_SUPPLY (No stockpile available)"
            continue

        # Handle zero total demand case
        if demands.sum() <= 0:
            service_floors[r_type] = 0.0
            df[alloc_col] = 0.0
            df[shortage_col] = 0.0
            solver_statuses[r_type] = "ZERO_DEMAND (All areas satisfied)"
            continue

        # Build LP
        # c vector: minimize - (p_i / D_i) * x_i
        c = np.zeros(n_areas, dtype=float)
        for i in range(n_areas):
            if demands[i] > 0:
                c[i] = - (p_weights[i] / demands[i])
            else:
                c[i] = 0.0

        # Inequality constraint: sum_i x_i <= tot_supply
        A_ub = np.ones((1, n_areas), dtype=float)
        b_ub = np.array([tot_supply], dtype=float)

        # Guarantee an equal fraction first. If stock cannot support the requested
        # floor, reduce it to the largest feasible shared fraction.
        floor = min(minimum_service_fraction, tot_supply / demands.sum())
        service_floors[r_type] = float(floor)
        bounds = [(float(floor * d), float(d)) for d in demands]

        # Solve with SciPy Highs LP solver
        res = linprog(c=c, A_ub=A_ub, b_ub=b_ub, bounds=bounds, method="highs")

        if res.success and res.status == 0:
            solver_statuses[r_type] = "OPTIMAL"
            allocations = np.clip(res.x, 0.0, demands)
        else:
            is_all_optimal = False
            solver_statuses[r_type] = f"INCOMPLETE ({res.message})"
            # Fallback to bounded proportional if LP failed
            prop = (demands / demands.sum()) * min(tot_supply, demands.sum())
            allocations = prop

        df[alloc_col] = allocations
        # Keep full precision internally: per-area rounding can exceed a scarce
        # stockpile or erase a feasible service floor. Round only for display.
        df[shortage_col] = np.maximum(0.0, demands - allocations)
        total_opt_shortage += float(df[shortage_col].sum())

    elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)

    # Compute baseline for comparison
    df = compute_baseline_proportional_allocation(df, resources_df, r_types)

    # Compute comparative performance
    baseline_shortage_cols = [f"baseline_shortage_{r}" for r in r_types if f"baseline_shortage_{r}" in df.columns]
    total_baseline_shortage = float(df[baseline_shortage_cols].sum().sum()) if baseline_shortage_cols else total_initial_demand

    shortage_reduction = max(0.0, total_baseline_shortage - total_opt_shortage)
    reduction_pct = round((shortage_reduction / total_baseline_shortage) * 100.0, 2) if total_baseline_shortage > 0 else 0.0

    return {
        "allocation_df": df,
        "is_optimal": is_all_optimal,
        "solver_statuses": solver_statuses,
        "service_floors": service_floors,
        "execution_time_ms": elapsed_ms,
        "summary": {
            "total_initial_demand": round(total_initial_demand, 1),
            "total_baseline_shortage": round(total_baseline_shortage, 1),
            "total_optimized_shortage": round(total_opt_shortage, 1),
            "shortage_reduction_units": round(shortage_reduction, 1),
            "shortage_reduction_pct": reduction_pct,
            "overall_status": "OPTIMAL" if is_all_optimal else "PARTIAL_OR_UNCONSTRAINED"
        }
    }


def optimize_transportation_lp(
    areas_df: pd.DataFrame,
    warehouses_df: pd.DataFrame,
    resources_df: pd.DataFrame,
    resource_type: str = "Water",
    distance_penalty_factor: float = 1e-7
) -> Dict[str, Any]:
    """Solves multi-source warehouse-to-area transportation LP when depot coordinates exist.

    Decision variables: x_ijk = amount of resource sent from warehouse j to area i.
    Objective:
        Maximize sum_i sum_j [ (p_i / D_i) * x_ij - lambda * dist_ij * x_ij ]

    Args:
        areas_df: Areas dataframe with coordinates and demands.
        warehouses_df: Warehouses dataframe with coordinates.
        resources_df: Resources dataframe with warehouse stockpiles.
        resource_type: Specific resource to route ('Food', 'Water', 'Medical_Kit').
        distance_penalty_factor: Small cost lambda penalizing excess transport mileage.

    Returns:
        Dictionary with route matrix, total distance km, and solver status.
    """
    if warehouses_df is None or warehouses_df.empty or "latitude" not in warehouses_df.columns:
        return {
            "status": "Source optimization unavailable - no warehouse data",
            "routes": []
        }

    n_areas = len(areas_df)
    n_warehouses = len(warehouses_df)
    demand_col = f"demand_{resource_type}"

    if demand_col not in areas_df.columns:
        return {"status": f"No demand data for {resource_type}", "routes": []}

    demands = areas_df[demand_col].values.astype(float)
    p_weights = areas_df.get("priority_score", pd.Series(1.0, index=areas_df.index)).values.astype(float)

    # Warehouse supplies
    wh_supplies = []
    for _, wh in warehouses_df.iterrows():
        w_id = wh["warehouse_id"]
        qty = resources_df[
            (resources_df["warehouse_id"] == w_id) & (resources_df["resource_type"] == resource_type)
        ]["quantity"].sum()
        wh_supplies.append(float(qty))

    # Distance matrix (km)
    distances = np.zeros((n_warehouses, n_areas))
    for j, (_, wh) in enumerate(warehouses_df.iterrows()):
        for i, (_, ar) in enumerate(areas_df.iterrows()):
            distances[j, i] = haversine_distance_km(wh["latitude"], wh["longitude"], ar["latitude"], ar["longitude"])

    # Decision variables flattened: x_ji where idx = j * n_areas + i
    n_vars = n_warehouses * n_areas
    c = np.zeros(n_vars)
    for j in range(n_warehouses):
        for i in range(n_areas):
            idx = j * n_areas + i
            # Objective: minimize - (p_i / D_i) * x_ji + lambda * dist_ji * x_ji
            benefit = (p_weights[i] / demands[i]) if demands[i] > 0 else 0.0
            cost = distance_penalty_factor * distances[j, i]
            c[idx] = - (benefit - cost)

    # Warehouse supply constraints: sum_i x_ji <= supply_j
    A_ub_wh = np.zeros((n_warehouses, n_vars))
    b_ub_wh = np.array(wh_supplies)
    for j in range(n_warehouses):
        for i in range(n_areas):
            A_ub_wh[j, j * n_areas + i] = 1.0

    # Area demand constraints: sum_j x_ji <= demand_i
    A_ub_ar = np.zeros((n_areas, n_vars))
    b_ub_ar = demands
    for i in range(n_areas):
        for j in range(n_warehouses):
            A_ub_ar[i, j * n_areas + i] = 1.0

    A_ub = np.vstack([A_ub_wh, A_ub_ar])
    b_ub = np.concatenate([b_ub_wh, b_ub_ar])
    bounds = [(0.0, None) for _ in range(n_vars)]

    res = linprog(c=c, A_ub=A_ub, b_ub=b_ub, bounds=bounds, method="highs")

    routes = []
    if res.success and res.status == 0:
        sol = res.x.reshape((n_warehouses, n_areas))
        for j, (_, wh) in enumerate(warehouses_df.iterrows()):
            for i, (_, ar) in enumerate(areas_df.iterrows()):
                qty = sol[j, i]
                if qty > 0.1:
                    routes.append({
                        "warehouse_id": wh["warehouse_id"],
                        "warehouse_name": wh.get("warehouse_name", wh["warehouse_id"]),
                        "area_id": ar["area_id"],
                        "resource_type": resource_type,
                        "quantity": round(float(qty), 1),
                        "distance_km": round(float(distances[j, i]), 2)
                    })
        return {
            "status": "OPTIMAL",
            "resource_type": resource_type,
            "routes": routes,
            "total_shipped": round(float(np.sum([r["quantity"] for r in routes])), 1)
        }
    else:
        return {"status": f"INCOMPLETE ({res.message})", "routes": []}
