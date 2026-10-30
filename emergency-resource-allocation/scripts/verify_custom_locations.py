"""Verify the actual running submission server without browser dependencies."""
import argparse
import csv
import io
import json
from pathlib import Path
import urllib.error
import urllib.request


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8008")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    checks = []

    def check(name, condition):
        assert condition, name
        checks.append(name)

    def call(path, body=None, expected=200, raw=False):
        request = urllib.request.Request(args.url + path, data=json.dumps(body).encode() if body is not None else None,
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                code, data = response.status, response.read().decode()
        except urllib.error.HTTPError as error:
            code, data = error.code, error.read().decode()
        assert code == expected, (path, code, data)
        return data if raw else json.loads(data)

    check("Updated model-ready server", call("/api/health")["version"] == "3.2.0")
    check("Production dashboard served", "ReliefPlan AI" in call("/", raw=True))
    location = dict(location_id="loc_http_vijayawada", name="Vijayawada verification", latitude=16.5062,
        longitude=80.648, population=2000, affected_population=750, children_population=300,
        elderly_population=200, population_density=3500, minor_damage=100, major_damage=60,
        destroyed_buildings=20, magnitude=6)
    second = {**location, "location_id": "loc_http_guntur", "name": "Guntur verification", "latitude": 16.3067,
        "longitude": 80.4365, "population": 1500, "affected_population": 500}
    config = dict(scenario_name="Synthetic HTTP verification", disaster_type="Flood", area_populations={},
        locations=[location, second], food_supply=1500, water_supply=1000, med_supply=100)
    plan = call("/api/analyze", config)
    plan_id = plan["plan_id"]
    check("Both custom places reach analysis", {a["area_name"] for a in plan["areas"]} == {location["name"], second["name"]})
    check("Entered affected counts preserved", plan["overview"]["total_affected"] == 1250)
    check("Resource budget enforced", plan["resources"]["Water"]["allocated"] <= 1000)
    check("Nine strategy comparisons", len(plan["strategy_comparison"]) == 9)
    check("Named scenario persisted", any(p["plan_id"] == plan_id and p["scenario_name"] == config["scenario_name"] for p in call("/api/plans")))
    check("Custom observations restored", call(f"/api/plans/{plan_id}")["inputs"]["locations"] == config["locations"])
    zero = call("/api/simulate", {"plan_id": plan_id, "shock_water_pct": 0})
    check("Zero-shock identity", zero["areas"] == plan["areas"])
    shock = call("/api/simulate", {"plan_id": plan_id, "shock_water_pct": -30, "shock_pop_pct": 20})
    check("Custom population shock", shock["affected_after"] == 1500)
    check("Supply shock reduces coverage", shock["water_coverage_after"] < shock["water_coverage_before"])
    check("Baseline unchanged by simulation", call(f"/api/plans/{plan_id}")["areas"] == plan["areas"])
    explanation = call(f"/api/explain/{plan_id}/{location['location_id']}")
    check("Custom SHAP explanation", len(explanation["contributions"]) == 6)
    action_id = plan["actions"][0]["action_id"]
    call(f"/api/plans/{plan_id}/dispatch/status", {"action_id": action_id, "status": "DELIVERED"}, expected=409)
    check("Cannot skip dispatch stages", True)
    approval = call(f"/api/plans/{plan_id}/dispatch", {"action_id": action_id})
    check("Approval idempotent", call(f"/api/plans/{plan_id}/dispatch", {"action_id": action_id})["event_id"] == approval["event_id"])
    for stage in ["DISPATCHED", "DELIVERED", "DELIVERED"]:
        call(f"/api/plans/{plan_id}/dispatch/status", {"action_id": action_id, "status": stage})
    check("Delivery status persisted", call(f"/api/plans/{plan_id}")["dispatch_statuses"][action_id] == "DELIVERED")
    rows = list(csv.DictReader(io.StringIO(call(f"/api/plans/{plan_id}/export.csv", raw=True))))
    check("CSV contains every custom area/resource", len(rows) == 6 and {r["area"] for r in rows} == {location["name"], second["name"]})
    call("/api/analyze", {**config, "locations": [{**location, "latitude": 95}]}, expected=422)
    check("Invalid coordinates rejected", True)
    call("/api/analyze", {**config, "locations": []}, expected=422)
    check("Empty scenario rejected", True)
    check("Lifecycle recorded in audit", {"DISPATCH_APPROVED", "DISPATCH_DISPATCHED", "DISPATCH_DELIVERED"}.issubset(
        {event["kind"] for event in call("/api/audit") if event["plan_id"] == plan_id}))
    output = {"server": args.url, "passed": len(checks), "checks": checks, "plan_id": plan_id,
        "analysis": plan, "shock": shock, "explanation": explanation}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(json.dumps({"passed": len(checks), "checks": checks}, indent=2))


if __name__ == "__main__":
    main()
