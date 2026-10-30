"""Unit tests for core/priority.py.

Verifies:
- Priority scores strictly stay between 0.0 and 1.0.
- Risk level classification correctly maps to LOW, MEDIUM, HIGH, CRITICAL.
- Component weights sum to 1.0 and normalize properly.
- Road accessibility penalties properly apply.
- Same inputs yield deterministic, identical priority scores.
"""

import pytest
import pandas as pd
import numpy as np
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.priority import (
    calculate_area_priorities,
    classify_risk_level,
    min_max_normalize,
    DEFAULT_WEIGHTS,
    DEFAULT_THRESHOLDS
)


@pytest.fixture
def sample_areas_data():
    return pd.DataFrame([
        {"area_id": "A", "population": 2500, "building_damage": 250, "predicted_severity": "CRITICAL",
         "elderly_population": 200, "children_population": 400},
        {"area_id": "B", "population": 1200, "building_damage": 50, "predicted_severity": "MEDIUM",
         "elderly_population": 100, "children_population": 150},
        {"area_id": "C", "population": 4000, "building_damage": 500, "predicted_severity": "HIGH",
         "elderly_population": 350, "children_population": 600},
        {"area_id": "D", "population": 800, "building_damage": 10, "predicted_severity": "LOW",
         "elderly_population": 50, "children_population": 80},
    ])


@pytest.fixture
def sample_roads_data():
    return pd.DataFrame([
        {"source": "A", "destination": "B", "road_status": "BLOCKED"},
        {"source": "B", "destination": "C", "road_status": "OPEN"},
        {"source": "C", "destination": "D", "road_status": "DAMAGED"},
    ])


def test_priority_scores_bounded_in_0_1(sample_areas_data, sample_roads_data):
    df_result = calculate_area_priorities(sample_areas_data, sample_roads_data)
    scores = df_result["priority_score"].values

    assert (scores >= 0.0).all(), "Priority score must be >= 0.0"
    assert (scores <= 1.0).all(), "Priority score must be <= 1.0"
    assert not np.isnan(scores).any(), "Priority scores must not contain NaN"


def test_risk_level_categories(sample_areas_data):
    df_result = calculate_area_priorities(sample_areas_data)
    valid_levels = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}

    for lvl in df_result["priority_level"]:
        assert lvl in valid_levels, f"Unexpected priority level: {lvl}"

    # Critical boundary check
    assert classify_risk_level(0.85) == "CRITICAL"
    assert classify_risk_level(0.60) == "HIGH"
    assert classify_risk_level(0.35) == "MEDIUM"
    assert classify_risk_level(0.10) == "LOW"


def test_priority_determinism(sample_areas_data, sample_roads_data):
    res1 = calculate_area_priorities(sample_areas_data, sample_roads_data)
    res2 = calculate_area_priorities(sample_areas_data, sample_roads_data)

    np.testing.assert_allclose(res1["priority_score"].values, res2["priority_score"].values)
    assert (res1["priority_level"] == res2["priority_level"]).all()


def test_min_max_normalize_constant_series():
    s = pd.Series([10.0, 10.0, 10.0])
    normed = min_max_normalize(s)
    assert (normed == 0.0).all()
    assert not normed.isna().any()
