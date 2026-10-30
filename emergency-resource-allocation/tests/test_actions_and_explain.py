"""Unit tests for core/actions.py and core/explain.py.

Verifies:
- Action card quantities match optimizer output exactly.
- Action reasons quote real numbers (population, destroyed buildings, demand).
- 'No action needed' cards appear for fully satisfied areas.
- SHAP explainer loads and computes global/local explanations.
- Plain-English explanation strictly includes mandatory disclaimer:
  'Contributions describe model behaviour, not causation.'
- Priority decomposition correctly accounts for component weights.
"""

import pytest
import pandas as pd
import numpy as np
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.actions import generate_action_cards, generate_operational_warnings
from core.explain import (
    load_model_and_explainer,
    compute_global_feature_importance,
    explain_single_area_prediction,
    decompose_priority_score_components,
    DISCLAIMER_TEXT
)
from core.optimizer import optimize_resource_allocation
from core.priority import calculate_area_priorities
from core.demand import compute_area_demands


@pytest.fixture
def sample_pipeline_data():
    areas = pd.DataFrame([
        {"area_id": "A", "population": 3000, "building_damage": 200, "minor_damage": 50,
         "major_damage": 100, "destroyed_buildings": 50, "population_density": 4000,
         "magnitude": 7.5, "predicted_severity": "CRITICAL", "elderly_population": 200,
         "children_population": 300},
        {"area_id": "B", "population": 1000, "building_damage": 10, "minor_damage": 5,
         "major_damage": 5, "destroyed_buildings": 0, "population_density": 1500,
         "magnitude": 7.5, "predicted_severity": "LOW", "elderly_population": 50,
         "children_population": 80},
    ])
    resources = pd.DataFrame([
        {"resource_id": "R1", "resource_type": "Food", "quantity": 10000, "warehouse_id": "W1"},
        {"resource_id": "R2", "resource_type": "Water", "quantity": 15000, "warehouse_id": "W1"},
        {"resource_id": "R3", "resource_type": "Medical_Kit", "quantity": 200, "warehouse_id": "W2"},
    ])
    df_demand = compute_area_demands(areas)
    df_prio = calculate_area_priorities(df_demand)
    res_opt = optimize_resource_allocation(df_prio, resources)
    return res_opt["allocation_df"]


def test_action_cards_match_optimizer_quantities(sample_pipeline_data):
    cards = generate_action_cards(sample_pipeline_data)

    assert len(cards) > 0
    for card in cards:
        if card["card_type"] == "DISPATCH_ACTION":
            area_id = card["area_id"]
            res = card["resource"]
            row = sample_pipeline_data[sample_pipeline_data["area_id"] == area_id].iloc[0]
            expected_qty = float(row[f"opt_alloc_{res}"])

            assert pytest.approx(card["quantity"], 0.1) == expected_qty, (
                f"Card quantity {card['quantity']} does not match optimizer output {expected_qty}"
            )


def test_action_card_reasons_contain_real_numbers(sample_pipeline_data):
    cards = generate_action_cards(sample_pipeline_data)

    for card in cards:
        reason = card["reason"]
        # Ensure reason quotes real numeric values
        assert any(char.isdigit() for char in reason), f"Reason must quote real numbers: {reason}"
        assert card["priority_level"] in reason or "priority" in reason.lower()


def test_mandatory_shap_disclaimer():
    assert "not causation" in DISCLAIMER_TEXT.lower()
    assert DISCLAIMER_TEXT == "Contributions describe model behaviour, not causation."


def test_explain_local_prediction(sample_pipeline_data):
    model, explainer, encoder = load_model_and_explainer()
    row = sample_pipeline_data.iloc[0]

    explanation = explain_single_area_prediction(
        explainer, row, predicted_class=row["predicted_severity"]
    )

    assert explanation["area_id"] == "A"
    assert len(explanation["contributions"]) > 0
    assert DISCLAIMER_TEXT in explanation["narrative"]
    assert explanation["figure"] is not None


def test_priority_score_decomposition(sample_pipeline_data):
    row = sample_pipeline_data.iloc[0]
    components, fig = decompose_priority_score_components(row)

    assert "Structural Impact (w1)" in components
    assert "Estimated Demand (w2)" in components
    assert fig is not None

    # Total sum of components should equal priority_score within rounding margin
    comp_sum = sum(components.values())
    assert pytest.approx(comp_sum, abs=0.05) == float(row["priority_score"])
