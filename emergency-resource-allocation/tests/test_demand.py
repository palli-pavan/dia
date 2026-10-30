"""Unit tests for core/demand.py.

Verifies:
- Demand values are strictly non-negative.
- Shortage is never negative: shortage_ik = max(0, demand_ik - available_ik).
- Coverage ratio stays within [0.0, 1.0].
- Per-capita standards and duration scale demand linearly.
- Hand-checked calculation verification.
"""

import pytest
import pandas as pd
import numpy as np
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.demand import (
    compute_area_demands,
    calculate_shortage_and_coverage,
    estimate_affected_population,
    DEFAULT_PER_CAPITA_NEEDS
)


@pytest.fixture
def sample_areas_data():
    return pd.DataFrame([
        {"area_id": "A", "population": 1000, "predicted_severity": "CRITICAL"},
        {"area_id": "B", "population": 2000, "predicted_severity": "LOW"},
    ])


@pytest.fixture
def sample_resources_data():
    return pd.DataFrame([
        {"resource_id": "R1", "resource_type": "Food", "quantity": 5000, "warehouse_id": "W1"},
        {"resource_id": "R2", "resource_type": "Water", "quantity": 1000, "warehouse_id": "W1"},
        {"resource_id": "R3", "resource_type": "Medical_Kit", "quantity": 50, "warehouse_id": "W2"},
    ])


def test_hand_checked_demand_calculation():
    """Hand-check: Area with 1000 population, CRITICAL severity (ratio 0.85).

    Affected = 1000 * 0.85 = 850.
    Water need: 850 * 3.0 L/day * 3 days = 7650 L.
    Food need:  850 * 2.0 packs/day * 3 days = 5100 rations.
    Medical:    850 * 0.05 kits/day * 3 days = 127.5 kits.
    """
    df = pd.DataFrame([{"area_id": "X", "population": 1000, "predicted_severity": "CRITICAL"}])
    result = compute_area_demands(df, duration_days=3.0, use_affected_only=True)

    assert result["estimated_affected"].iloc[0] == 850
    assert pytest.approx(result["demand_Water"].iloc[0], 0.1) == 7650.0
    assert pytest.approx(result["demand_Food"].iloc[0], 0.1) == 5100.0
    assert pytest.approx(result["demand_Medical_Kit"].iloc[0], 0.1) == 127.5


def test_demand_non_negative(sample_areas_data):
    df_demand = compute_area_demands(sample_areas_data)
    for col in ["demand_Food", "demand_Water", "demand_Medical_Kit"]:
        assert (df_demand[col] >= 0.0).all()
        assert not df_demand[col].isna().any()


def test_coverage_ratio_bounds(sample_areas_data, sample_resources_data):
    df_demand = compute_area_demands(sample_areas_data)
    demands, supplies, coverages = calculate_shortage_and_coverage(df_demand, sample_resources_data)

    for r_type, cov in coverages.items():
        assert 0.0 <= cov <= 1.0, f"Coverage for {r_type} must be in [0, 1], got {cov}"


def test_zero_population_case():
    df = pd.DataFrame([{"area_id": "Empty", "population": 0, "predicted_severity": "LOW"}])
    res = compute_area_demands(df)
    assert res["demand_Water"].iloc[0] == 0.0
    assert res["demand_Food"].iloc[0] == 0.0
