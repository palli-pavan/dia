"""Submission-critical coverage for arbitrary affected places and saved workflows."""
import numpy as np
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
import server
from core import store
from core.comparison import equal_share


@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "locations.sqlite3")


def location(**changes):
    return dict(location_id="loc_vijayawada", name="Vijayawada Ward 12", latitude=16.5062,
        longitude=80.648, population=2000, affected_population=750,
        children_population=300, elderly_population=200, population_density=3500,
        minor_damage=100, major_damage=60, destroyed_buildings=20, magnitude=6, **changes)


def analyze(**changes):
    config = {"area_populations": {}, "locations": [location()], "scenario_name": "Andhra flood response", "disaster_type": "Flood"}
    config.update(changes)
    return server.analyze_disaster(server.AnalyzeRequest(**config))


def test_custom_only_pipeline_uses_exact_observations_and_reported_count():
    result = analyze()
    assert len(result["areas"]) == 1
    area = result["areas"][0]
    assert area["area_id"] == "loc_vijayawada"
    assert area["area_name"] == "Vijayawada Ward 12"
    assert (area["latitude"], area["longitude"]) == (16.5062, 80.648)
    assert area["features"]["building_damage"] == 180
    assert area["features"]["magnitude"] == 6
    assert area["features"]["population_density"] == 3500
    assert area["estimated_affected"] == 750
    assert area["demand"]["Food"] == 4500
    assert area["input_source"] == "User observations"
    assert area["affected_source"] == "Entered count"
    assert len(result["actions"]) == 3
    assert server.explain_area(result["plan_id"], area["area_id"])["predicted_class"] == area["predicted_severity"]
    assert len(server.export_plan(result["plan_id"]).body.decode().splitlines()) == 4


def test_mixed_locations_and_missing_affected_estimate_are_supported():
    new = location()
    new["affected_population"] = None
    result = analyze(area_populations={"Area A": 1000}, locations=[new])
    assert len(result["areas"]) == 2
    assert result["overview"]["total_population"] == 3000
    assert next(a for a in result["areas"] if a["area_id"].startswith("loc_"))["affected_source"] == "Model-based estimate"


def test_saved_scenario_and_dispatch_lifecycle_survive_reload():
    base = analyze()
    action = base["actions"][0]["action_id"]
    with pytest.raises(server.HTTPException) as error:
        server.update_dispatch(base["plan_id"], server.DispatchUpdate(action_id=action, status="DELIVERED"))
    assert error.value.status_code == 409
    server.approve_dispatch(base["plan_id"], server.DispatchRequest(action_id=action))
    for status in ["DISPATCHED", "DELIVERED", "DELIVERED"]:
        assert server.update_dispatch(base["plan_id"], server.DispatchUpdate(action_id=action, status=status))["status"] == status
    loaded = server.get_plan(base["plan_id"])
    assert loaded["inputs"]["locations"][0]["name"] == "Vijayawada Ward 12"
    assert loaded["dispatch_statuses"][action] == "DELIVERED"
    assert server.list_plans()[0]["scenario_name"] == "Andhra flood response"
    assert len([event for event in store.events(base["plan_id"]) if event["kind"] == "DISPATCH_DELIVERED"]) == 1
    with pytest.raises(server.HTTPException):
        server.update_dispatch(base["plan_id"], server.DispatchUpdate(action_id=action, status="DISPATCHED"))


def test_custom_location_shock_and_zero_stock():
    base = analyze(water_supply=100, food_supply=0, med_supply=0)
    zero = server.simulate_shock(server.SimulateRequest(plan_id=base["plan_id"], shock_water_pct=0))
    assert zero["areas"] == base["areas"]
    changed = server.simulate_shock(server.SimulateRequest(plan_id=base["plan_id"], shock_water_pct=-100, shock_pop_pct=20))
    assert changed["affected_after"] == 900
    assert changed["areas"][0]["population"] == 2400
    assert changed["areas"][0]["allocation"]["Water"] == 0
    assert server.get_plan(base["plan_id"])["areas"][0]["estimated_affected"] == 750


def test_zero_reported_affected_is_not_replaced_by_model_estimate():
    new = location()
    new["affected_population"] = 0
    base = analyze(locations=[new], severity="Extreme")
    assert base["overview"]["total_affected"] == 0
    assert all(resource["demand"] == 0 for resource in base["resources"].values())


def test_comparisons_cap_demand_and_conserve_stock():
    base = analyze(area_populations={"Area A": 1800}, food_supply=123, water_supply=0, med_supply=50000)
    assert len(base["strategy_comparison"]) == 9
    for row in base["strategy_comparison"]:
        resource = base["resources"][row["resource"]]
        assert row["allocated"] == pytest.approx(min(resource["supply"], resource["demand"]), abs=0.01)
        assert 0 <= row["minimum_coverage_pct"] <= 100
        assert 0 <= row["priority_weighted_coverage_pct"] <= 100
    assert equal_share(np.array([1., 10., 100.]), 30).tolist() == pytest.approx([1, 10, 19])


def test_out_of_training_range_warning_names_actual_location():
    new = location()
    new["population_density"] = 900000
    base = analyze(locations=[new])
    assert base["input_warnings"][0]["area_name"] == new["name"]
    assert "population_density" in base["input_warnings"][0]["features"]


@pytest.mark.parametrize("changes", [
    {"latitude": 91}, {"longitude": -181}, {"name": "   "}, {"population": -1},
    {"affected_population": 2001}, {"children_population": 1801},
    {"minor_damage": -2}, {"population_density": float("nan")}, {"location_id": "../../bad"},
])
def test_invalid_custom_observations_are_rejected(changes):
    new = location()
    new.update(changes)
    with pytest.raises(ValidationError):
        server.AnalyzeRequest(area_populations={}, locations=[new])


def test_duplicate_location_identity_or_name_is_rejected():
    one = location()
    two = {**one, "location_id": "loc_other", "name": " vijayawada ward 12 "}
    with pytest.raises(ValidationError):
        server.AnalyzeRequest(locations=[one, two])
    with pytest.raises(ValidationError):
        server.AnalyzeRequest(locations=[one, {**one, "name": "Different name"}])


def test_http_validation_saved_list_and_status_routes():
    with TestClient(server.app) as client:
        response = client.post("/api/analyze", json={"area_populations": {}, "locations": [location()], "scenario_name": "HTTP custom place"})
        assert response.status_code == 200
        base = response.json()
        assert client.get("/api/plans").json()[0]["plan_id"] == base["plan_id"]
        assert client.get(f"/api/plans/{base['plan_id']}").json()["inputs"]["scenario_name"] == "HTTP custom place"
        assert client.post("/api/analyze", json={"area_populations": {}, "locations": []}).status_code == 422
        assert client.post(f"/api/plans/{base['plan_id']}/dispatch/status", json={"action_id": "unknown", "status": "DISPATCHED"}).status_code == 409


def test_many_custom_locations_are_not_dropped():
    locations = [{**location(), "location_id": f"loc_{i}", "name": f"Affected ward {i}", "latitude": 16.5 + i * .001} for i in range(30)]
    base = analyze(locations=locations, water_supply=12345)
    assert len(base["areas"]) == 30
    assert base["overview"]["total_affected"] == 30 * 750
    assert sum(area["allocation"]["Water"] for area in base["areas"]) == pytest.approx(12345, abs=0.01)


@pytest.mark.parametrize("name", ["", "   ", "\t\n"])
def test_blank_scenario_name_is_generated_and_persisted(name):
    result = analyze(scenario_name=name)
    assert result["inputs"]["scenario_name"] == "Flood response"
    assert server.get_plan(result["plan_id"])["inputs"]["scenario_name"] == "Flood response"
    assert server.list_plans()[0]["scenario_name"] == "Flood response"


def test_custom_scenario_name_is_trimmed_and_preserved():
    request = server.AnalyzeRequest(scenario_name="  Vijayawada emergency  ")
    assert request.scenario_name == "Vijayawada emergency"
