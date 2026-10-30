"""Unit tests for core/simulate.py and core/audit.py.

Verifies:
- Cutting water supply by 30% increases shortage and reduces coverage in the expected direction.
- Percentage reduction formula strictly equals (before - after) / before * 100.
- Scenario A vs Scenario B comparison correctly outputs metrics table, figures, and deltas.
- Optimization impact against baseline is properly computed.
- Every run appends a valid row to the audit log with timestamp, scenario, model, allocation, and solver status.
"""

import pytest
import pandas as pd
import numpy as np
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.simulate import (
    run_full_pipeline,
    compare_two_scenarios,
    compute_optimization_impact
)
from core.audit import log_decision_run, get_audit_history, clear_audit_log


TEST_AUDIT_CSV = "data/test_audit_log.csv"


@pytest.fixture(autouse=True)
def cleanup_test_audit():
    clear_audit_log(TEST_AUDIT_CSV)
    yield
    clear_audit_log(TEST_AUDIT_CSV)


def test_what_if_reduce_water_by_30_pct():
    """Verify cutting water by 30% increases water shortage and decreases water coverage."""
    # Run Baseline
    base_res = run_full_pipeline(
        resource_supply_deltas={"Water": 0.0}
    )
    # Run -30% Water Stress Test
    stress_res = run_full_pipeline(
        resource_supply_deltas={"Water": -30.0}
    )

    base_water_cov = base_res["coverages"]["Water"]
    stress_water_cov = stress_res["coverages"]["Water"]

    base_water_shortage = base_res["allocation_df"]["opt_shortage_Water"].sum()
    stress_water_shortage = stress_res["allocation_df"]["opt_shortage_Water"].sum()

    # Directional verification
    assert stress_water_cov <= base_water_cov, (
        f"Stress water coverage ({stress_water_cov}) must be <= base coverage ({base_water_cov})"
    )
    assert stress_water_shortage >= base_water_shortage, (
        f"Stress water shortage ({stress_water_shortage}) must be >= base shortage ({base_water_shortage})"
    )


def test_percentage_reduction_formula_math():
    """Verify formula: % reduction = (before - after) / before * 100."""
    res = run_full_pipeline()
    impact = compute_optimization_impact(res["allocation_df"])

    base_short = impact["total_baseline_shortage"]
    opt_short = impact["total_optimized_shortage"]
    reported_pct = impact["overall_reduction_pct"]

    if base_short > 0:
        expected_pct = round(((base_short - opt_short) / base_short) * 100.0, 2)
        assert pytest.approx(reported_pct, 0.01) == expected_pct
    else:
        assert reported_pct == 0.0


def test_scenario_comparison():
    res_a = run_full_pipeline(population_delta_pct=0.0)
    res_b = run_full_pipeline(population_delta_pct=25.0)

    comp = compare_two_scenarios(res_a, res_b, name_a="Base", name_b="Pop+25%")

    assert comp["comparison_table"] is not None
    assert comp["figure"] is not None
    assert comp["delta_shortage"] is not None
    # Increased population should increase total shortage
    assert comp["delta_shortage"] >= 0.0


def test_audit_log_persistence():
    pipeline_res = run_full_pipeline()
    record = log_decision_run(
        scenario_name="Automated_Test_Scenario",
        pipeline_result=pipeline_res,
        model_name="XGBoost",
        audit_file_path=TEST_AUDIT_CSV,
        additional_notes="Test runner verification"
    )

    assert os.path.exists(TEST_AUDIT_CSV)
    df_history = get_audit_history(TEST_AUDIT_CSV)

    assert len(df_history) == 1
    row = df_history.iloc[0]

    assert row["run_id"] == record["run_id"]
    assert row["scenario_name"] == "Automated_Test_Scenario"
    assert row["model_name"] == "XGBoost"
    assert row["solver_status"] in ["OPTIMAL", "SUB_OPTIMAL"]
    assert "UTC" in row["timestamp"]

    # Verify JSON deserialization of logged columns
    allocs = json.loads(row["dispatched_allocations"])
    assert "Water" in allocs or "Food" in allocs
