"""Unit tests for core/optimizer.py.

Verifies:
- Allocation never exceeds available supply: sum_i x_ik <= supply_k.
- Allocation never exceeds area demand: 0 <= x_ik <= demand_ik.
- Zero supply is handled gracefully with clear status.
- Optimization produces strictly non-negative shortage reduction.
- Determinism: identical inputs produce identical allocations.
- Solver status explicitly reports 'OPTIMAL' when verified.
"""

import pytest
import pandas as pd
import numpy as np
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.optimizer import (
    optimize_resource_allocation,
    compute_baseline_proportional_allocation,
    optimize_transportation_lp
)


@pytest.fixture
def sample_setup():
    areas = pd.DataFrame([
        {"area_id": "A", "population": 3000, "priority_score": 0.85, "latitude": 29.76, "longitude": -95.37,
         "demand_Food": 4000.0, "demand_Water": 8000.0, "demand_Medical_Kit": 150.0},
        {"area_id": "B", "population": 1500, "priority_score": 0.50, "latitude": 29.77, "longitude": -95.38,
         "demand_Food": 2000.0, "demand_Water": 4000.0, "demand_Medical_Kit": 75.0},
        {"area_id": "C", "population": 1000, "priority_score": 0.20, "latitude": 29.75, "longitude": -95.35,
         "demand_Food": 1000.0, "demand_Water": 2000.0, "demand_Medical_Kit": 30.0},
    ])
    resources = pd.DataFrame([
        {"resource_id": "R1", "resource_type": "Food", "quantity": 5000, "warehouse_id": "W1"},
        {"resource_id": "R2", "resource_type": "Water", "quantity": 10000, "warehouse_id": "W1"},
        {"resource_id": "R3", "resource_type": "Medical_Kit", "quantity": 100, "warehouse_id": "W2"},
    ])
    warehouses = pd.DataFrame([
        {"warehouse_id": "W1", "warehouse_name": "Central Depot", "latitude": 29.755, "longitude": -95.36},
        {"warehouse_id": "W2", "warehouse_name": "North Depot", "latitude": 29.785, "longitude": -95.395},
    ])
    return areas, resources, warehouses


def test_allocation_never_exceeds_supply(sample_setup):
    areas, resources, _ = sample_setup
    res = optimize_resource_allocation(areas, resources)
    df_alloc = res["allocation_df"]

    for _, row in resources.iterrows():
        r_type = row["resource_type"]
        supply = float(row["quantity"])
        total_allocated = float(df_alloc[f"opt_alloc_{r_type}"].sum())

        assert total_allocated <= supply + 1e-4, (
            f"Allocated {total_allocated} exceeds supply {supply} for {r_type}"
        )


def test_allocation_never_exceeds_demand(sample_setup):
    areas, resources, _ = sample_setup
    res = optimize_resource_allocation(areas, resources)
    df_alloc = res["allocation_df"]

    for r_type in ["Food", "Water", "Medical_Kit"]:
        for _, row in df_alloc.iterrows():
            alloc = float(row[f"opt_alloc_{r_type}"])
            dem = float(row[f"demand_{r_type}"])
            assert alloc <= dem + 1e-4, f"Allocated {alloc} exceeds demand {dem} for {r_type} in {row['area_id']}"
            assert alloc >= 0.0, f"Allocation must be non-negative"


def test_solver_status_is_optimal(sample_setup):
    areas, resources, _ = sample_setup
    res = optimize_resource_allocation(areas, resources)

    assert res["is_optimal"] is True
    for r_type, status in res["solver_statuses"].items():
        assert status == "OPTIMAL", f"Expected OPTIMAL status for {r_type}, got {status}"


def test_zero_supply_handling(sample_setup):
    areas, _, _ = sample_setup
    zero_resources = pd.DataFrame([
        {"resource_id": "R1", "resource_type": "Food", "quantity": 0, "warehouse_id": "W1"},
        {"resource_id": "R2", "resource_type": "Water", "quantity": 0, "warehouse_id": "W1"},
        {"resource_id": "R3", "resource_type": "Medical_Kit", "quantity": 0, "warehouse_id": "W2"},
    ])
    res = optimize_resource_allocation(areas, zero_resources)
    df_alloc = res["allocation_df"]

    for r_type in ["Food", "Water", "Medical_Kit"]:
        assert (df_alloc[f"opt_alloc_{r_type}"] == 0.0).all()
        assert "ZERO_SUPPLY" in res["solver_statuses"][r_type]


def test_optimizer_determinism(sample_setup):
    areas, resources, _ = sample_setup
    res1 = optimize_resource_allocation(areas, resources)
    res2 = optimize_resource_allocation(areas, resources)

    for r in ["Food", "Water", "Medical_Kit"]:
        np.testing.assert_allclose(
            res1["allocation_df"][f"opt_alloc_{r}"].values,
            res2["allocation_df"][f"opt_alloc_{r}"].values
        )


def test_transportation_lp(sample_setup):
    areas, resources, warehouses = sample_setup
    trans_res = optimize_transportation_lp(areas, warehouses, resources, resource_type="Water")

    assert trans_res["status"] == "OPTIMAL"
    assert len(trans_res["routes"]) > 0
    assert trans_res["total_shipped"] <= 10000.0


def test_shortage_reduction_non_negative(sample_setup):
    areas, resources, _ = sample_setup
    res = optimize_resource_allocation(areas, resources)
    summary = res["summary"]

    assert summary["shortage_reduction_units"] >= 0.0
    assert summary["shortage_reduction_pct"] >= 0.0
    assert summary["total_optimized_shortage"] <= summary["total_baseline_shortage"]
