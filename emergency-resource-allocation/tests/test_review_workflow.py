"""Regression coverage for the formerly disconnected project workflow."""
import json
import pytest
from pydantic import ValidationError
import server
from core import store
from core.optimizer import optimize_resource_allocation
from core.planning import prepare_scenario
import pandas as pd


@pytest.fixture(autouse=True)
def isolated_database(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "review.sqlite3")


def plan(**changes):
    return server.analyze_disaster(server.AnalyzeRequest(**changes))


def test_supply_inputs_are_exact_totals_across_warehouses():
    config = server.AnalyzeRequest(food_supply=123.45, water_supply=0, med_supply=12).model_dump()
    data, _ = prepare_scenario(config)
    totals = data["resources"].groupby("resource_type")["quantity"].sum()
    assert totals["Food"] == pytest.approx(123.45)
    assert totals["Water"] == 0
    assert totals["Medical_Kit"] == 12


def test_analysis_uses_inputs_and_distinguishes_population():
    result = plan(water_supply=1000)
    assert result["resources"]["Water"]["supply"] == 1000
    assert result["resources"]["Water"]["allocated"] <= 1000
    assert result["overview"]["total_population"] == 21779
    assert result["overview"]["total_affected"] == sum(a["estimated_affected"] for a in result["areas"])
    assert result["overview"]["total_affected"] < 21779


def test_zero_population_is_preserved():
    result = plan(area_populations={"Area A": 0})
    assert result["overview"]["total_affected"] == 0
    assert all(r["demand"] == r["allocated"] == 0 for r in result["resources"].values())


def test_zero_stock_reports_shortage_not_no_action_needed():
    result = plan(food_supply=0, water_supply=0, med_supply=0)
    assert result["overview"]["solver_status"] == "SUPPLY_LIMITED"
    assert result["actions"] == []
    assert result["resources"]["Water"]["shortage"] > 0
    assert all(r["allocated"] == 0 for r in result["resources"].values())


def test_actual_service_floor_is_feasible_and_enforced():
    result = plan()
    for resource, summary in result["resources"].items():
        for area in result["areas"]:
            assert area["allocation"][resource] + 0.001 >= area["demand"][resource] * summary["service_floor_pct"] / 100
    scarce = plan(water_supply=10)
    assert scarce["resources"]["Water"]["service_floor_pct"] < 25
    assert all(a["allocation"]["Water"] > 0 for a in scarce["areas"])


def test_zero_shock_reproduces_saved_baseline_even_with_fractional_stock():
    base = plan(water_supply=12345.67, duration_hours=37)
    changed = server.simulate_shock(server.SimulateRequest(plan_id=base["plan_id"], shock_water_pct=0))
    assert changed["affected_before"] == changed["affected_after"]
    assert all(r["shortage_delta"] == 0 and r["coverage_after"] == r["coverage_before"] for r in changed["comparison"])
    assert changed["areas"] == base["areas"]


def test_water_and_population_shocks_use_same_plan():
    base = plan()
    changed = server.simulate_shock(server.SimulateRequest(plan_id=base["plan_id"], shock_water_pct=-30, shock_pop_pct=25))
    assert changed["water_coverage_after"] < changed["water_coverage_before"]
    assert changed["affected_after"] > changed["affected_before"]
    assert server.get_plan(base["plan_id"])["resources"] == base["resources"]


def test_severity_changes_estimated_need():
    low = plan(severity="Low")
    extreme = plan(severity="Extreme")
    assert extreme["overview"]["total_affected"] > low["overview"]["total_affected"]


def test_approvals_are_idempotent_persisted_and_plan_scoped():
    base = plan()
    req = server.DispatchRequest(action_id=base["actions"][0]["action_id"])
    a = server.approve_dispatch(base["plan_id"], req)
    b = server.approve_dispatch(base["plan_id"], req)
    assert a["event_id"] == b["event_id"]
    assert req.action_id in server.get_plan(base["plan_id"])["approved_actions"]
    with pytest.raises(server.HTTPException) as error:
        server.approve_dispatch(base["plan_id"], server.DispatchRequest(action_id="unknown"))
    assert error.value.status_code == 404


def test_bulletin_and_audit_are_real_persistent_records():
    assert server.get_audit_log() == []
    base = plan()
    saved = server.save_bulletin(base["plan_id"])
    assert saved["status"] == "SAVED_LOCALLY"
    assert server.latest_plan()["bulletin_saved"] is True
    assert {e["kind"] for e in server.get_audit_log()} == {"ANALYSIS", "BULLETIN_SAVED"}
    assert server.export_audit().media_type == "text/csv"


def test_plan_csv_has_every_area_resource_pair():
    base = plan()
    exported = server.export_plan(base["plan_id"])
    assert len(exported.body.decode().strip().splitlines()) == 22


def test_shap_explanation_matches_requested_area_and_class():
    base = plan()
    result = server.explain_area(base["plan_id"], "A")
    area = next(a for a in base["areas"] if a["area_id"] == "A")
    assert result["predicted_class"] == area["predicted_severity"]
    assert len(result["contributions"]) == 6
    assert "not causation" in result["disclaimer"]


@pytest.mark.parametrize("changes", [{"food_supply": -1}, {"water_supply": float("nan")}, {"duration_hours": 0},
    {"area_populations": {}}, {"area_populations": {"Area Z": 10}}, {"area_populations": {"Area A": -1}},
    {"disaster_type": "Unknown"}, {"minimum_service_fraction": 1.1}])
def test_invalid_input_is_rejected(changes):
    with pytest.raises(ValidationError):
        server.AnalyzeRequest(**changes)
