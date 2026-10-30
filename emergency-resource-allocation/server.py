"""ReliefPlan API and packaged local dashboard."""
from typing import Annotated, Literal
import csv
import io
import json
import logging
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from core import store
from core.data import ML_FEATURE_COLS
from core.planning import ROOT, DEFAULT_POPULATIONS, SEVERITY_MULTIPLIERS, execute_scenario

app = FastAPI(title="ReliefPlan AI", version="3.2.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["GET", "POST"], allow_headers=["Content-Type"])
Quantity = Annotated[float, Field(ge=0, le=1_000_000_000, allow_inf_nan=False)]


class AffectedLocation(BaseModel):
    """User observations, never copied from an unrelated example location."""
    model_config = ConfigDict(extra="forbid")
    location_id: str = Field(pattern=r"^loc_[A-Za-z0-9_-]{1,64}$")
    name: str = Field(min_length=1, max_length=100)
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)
    population: int = Field(ge=0, le=10_000_000)
    affected_population: int | None = Field(default=None, ge=0, le=10_000_000)
    children_population: int = Field(default=0, ge=0, le=10_000_000)
    elderly_population: int = Field(default=0, ge=0, le=10_000_000)
    population_density: float = Field(ge=0, le=1_000_000, allow_inf_nan=False)
    minor_damage: int = Field(ge=0, le=10_000_000)
    major_damage: int = Field(ge=0, le=10_000_000)
    destroyed_buildings: int = Field(ge=0, le=10_000_000)
    magnitude: float = Field(ge=0, le=20, allow_inf_nan=False)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Enter a location name.")
        return value

    @model_validator(mode="after")
    def coherent_population(self):
        if self.affected_population is not None and self.affected_population > self.population:
            raise ValueError("Affected population cannot exceed resident population.")
        if self.children_population + self.elderly_population > self.population:
            raise ValueError("Children and elderly counts combined cannot exceed resident population.")
        return self


class AnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    disaster_type: Literal["Flood", "Earthquake", "Cyclone", "Wildfire"] = "Wildfire"
    severity: Literal["Low", "Moderate", "High", "Extreme"] = "High"
    duration_hours: int = Field(default=72, ge=1, le=720)
    food_supply: Quantity = 40000
    water_supply: Quantity = 40000
    med_supply: Quantity = 2500
    area_populations: dict[str, int] = Field(default_factory=lambda: DEFAULT_POPULATIONS.copy())
    locations: list[AffectedLocation] = Field(default_factory=list, max_length=100)
    scenario_name: str = Field(default="Disaster response", min_length=1, max_length=100)
    minimum_service_fraction: float = Field(default=0.25, ge=0, le=1, allow_inf_nan=False)

    @field_validator("scenario_name", mode="before")
    @classmethod
    def default_blank_scenario_name(cls, value, info):
        if isinstance(value, str):
            return value.strip() or f"{info.data.get('disaster_type', 'Disaster')} response"
        return value

    @field_validator("area_populations")
    @classmethod
    def validate_populations(cls, values):
        if any(name not in DEFAULT_POPULATIONS for name in values):
            raise ValueError("Unknown example area. Add a custom location using the locations field.")
        if any(pop < 0 or pop > 10_000_000 for pop in values.values()):
            raise ValueError("Population must be between 0 and 10000000.")
        return values

    @model_validator(mode="after")
    def valid_locations(self):
        if not self.area_populations and not self.locations:
            raise ValueError("Add at least one affected location or example area.")
        ids = [location.location_id for location in self.locations]
        names = [location.name.casefold() for location in self.locations] + [name.casefold() for name in self.area_populations]
        if len(ids) != len(set(ids)) or len(names) != len(set(names)):
            raise ValueError("Location IDs and names must be unique within a scenario.")
        return self


class SimulateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan_id: str
    shock_water_pct: float = Field(default=-30, ge=-100, le=200, allow_inf_nan=False)
    shock_pop_pct: float = Field(default=0, ge=-90, le=200, allow_inf_nan=False)


class DispatchRequest(BaseModel):
    action_id: str


class DispatchUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action_id: str
    status: Literal["DISPATCHED", "DELIVERED"]


def model_metrics():
    path = ROOT / "models/metrics.json"
    if not path.exists():
        raise HTTPException(503, "Model metrics missing. Run python core/model.py.")
    return json.loads(path.read_text(encoding="utf-8"))


def plan_or_404(plan_id):
    plan = store.get_plan(plan_id)
    if plan is None:
        raise HTTPException(404, "Plan not found. Run a new analysis.")
    return plan


def hydrated(plan):
    result = json.loads(plan["result"])
    history = store.events(plan["plan_id"])
    result["approved_actions"] = [e["item_id"] for e in history if e["kind"] == "DISPATCH_APPROVED"]
    result["dispatch_statuses"] = dispatch_statuses(history)
    result["bulletin_saved"] = any(e["kind"] == "BULLETIN_SAVED" for e in history)
    return result


def dispatch_statuses(history):
    states = {}
    for event in reversed(history):
        if event["kind"] in {"DISPATCH_APPROVED", "DISPATCH_DISPATCHED", "DISPATCH_DELIVERED"}:
            states[event["item_id"]] = event["kind"].removeprefix("DISPATCH_")
    return states


def serialize_result(result, config):
    frame = result["allocation_df"].sort_values("priority_score", ascending=False)
    resource_types = ["Food", "Water", "Medical_Kit"]
    areas = []
    for _, row in frame.iterrows():
        area = {"area_id": str(row["area_id"]), "area_name": str(row["area_name"]),
            "population": int(row["population"]), "estimated_affected": int(row["estimated_affected"]),
            "priority_score": round(float(row["priority_score"]), 4), "priority_level": str(row["priority_level"]),
            "predicted_severity": str(row["predicted_severity"]),
            "prediction_confidence": round(float(row.get("prediction_confidence", 0)), 4),
            "latitude": float(row["latitude"]), "longitude": float(row["longitude"]),
            "features": {f: float(row[f]) for f in ML_FEATURE_COLS},
            "input_source": "User observations" if str(row["area_id"]).startswith("loc_") else "Synthetic example",
            "affected_source": "Entered count" if pd.notna(row.get("reported_affected")) else "Model-based estimate",
            "priority_components": {c: float(row.get("comp_" + c, 0)) for c in ["impact", "demand", "shortage", "medical_need", "accessibility"]}}
        for key, prefix in [("demand", "demand_"), ("allocation", "opt_alloc_"), ("shortage", "opt_shortage_")]:
            area[key] = {r: round(float(row[prefix + r]), 4) for r in resource_types}
        areas.append(area)
    resources = {}
    for resource in resource_types:
        demand = float(frame["demand_" + resource].sum())
        allocated = float(frame["opt_alloc_" + resource].sum())
        resources[resource] = {"demand": round(demand, 4), "supply": round(result["total_supplies"][resource], 4),
            "allocated": round(allocated, 4), "shortage": round(max(0, demand - allocated), 4),
            "coverage_pct": round(100 * (allocated / demand if demand else 1), 2),
            "service_floor_pct": round(result["service_floors"].get(resource, 0) * 100, 2),
            "solver_status": result["solver_statuses"][resource]}
    actions = [dict(c, action_id=f"{c['area_id']}_{c['resource']}") for c in result["action_cards"] if c["card_type"] == "DISPATCH_ACTION"]
    status = "OPTIMAL" if result["is_optimal"] else "SUPPLY_LIMITED" if any("ZERO_SUPPLY" in s for s in result["solver_statuses"].values()) else "PARTIAL"
    from core.comparison import compare_strategies, input_range_warnings
    return {"status": "success", "inputs": config, "areas": areas, "actions": actions, "resources": resources,
        "strategy_comparison": compare_strategies(frame, result["total_supplies"]),
        "input_warnings": input_range_warnings(frame),
        "warnings": result["warnings"], "solver_statuses": result["solver_statuses"],
        "overview": {"total_population": int(frame["population"].sum()), "total_affected": int(frame["estimated_affected"].sum()),
            "critical_areas": int(frame["priority_level"].eq("CRITICAL").sum()), "high_areas": int(frame["priority_level"].eq("HIGH").sum()),
            "solver_status": status, "execution_time_ms": result["kpis"]["execution_time_ms"],
            "coverages": {r: resources[r]["coverage_pct"] for r in resource_types}},
        "assumptions": {"daily_rates": result["planning_rates"], "severity_multiplier": SEVERITY_MULTIPLIERS[config["severity"]],
            "minimum_service_fraction": config["minimum_service_fraction"], "data_source": "Synthetic examples and user-entered observations; model trained on synthetic data"}}


@app.get("/api/health")
def health_check():
    ready = all((ROOT / p).exists() for p in ["models/best_model.pkl", "models/label_encoder.pkl", "data/damage.csv"])
    return {"status": "ok" if ready else "setup_required", "system": "ReliefPlan AI", "version": "3.2.0", "model_ready": ready}


@app.post("/api/analyze")
def analyze_disaster(req: AnalyzeRequest):
    try:
        config = req.model_dump()
        result = serialize_result(execute_scenario(config), config)
        result["model_name"] = model_metrics()["metadata"]["best_model_name"]
        store.save_plan(config, result)
        store.record_event(result["plan_id"], "ANALYSIS", "analysis", {"scenario_name": req.scenario_name,
            "model_name": result["model_name"], "solver_status": result["overview"]["solver_status"], "inputs": config})
        return dict(result, approved_actions=[], dispatch_statuses={}, bulletin_saved=False)
    except HTTPException:
        raise
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(503, f"Project data or model unavailable: {exc}") from exc
    except Exception as exc:
        logging.exception("Analysis failed")
        raise HTTPException(500, "Analysis failed. See the local server log.") from exc


@app.get("/api/plans/latest")
def latest_plan():
    plan = store.latest_plan()
    return hydrated(plan) if plan else None


@app.get("/api/plans")
def list_plans():
    return store.list_plans()


@app.get("/api/plans/{plan_id}")
def get_plan(plan_id: str):
    return hydrated(plan_or_404(plan_id))


@app.post("/api/simulate")
def simulate_shock(req: SimulateRequest):
    plan = plan_or_404(req.plan_id)
    config, base = json.loads(plan["request"]), json.loads(plan["result"])
    changed = serialize_result(execute_scenario(config, req.shock_water_pct, req.shock_pop_pct), config)
    comparison = []
    for resource, before in base["resources"].items():
        after = changed["resources"][resource]
        comparison.append({"resource": resource, "coverage_before": before["coverage_pct"], "coverage_after": after["coverage_pct"],
            "shortage_before": before["shortage"], "shortage_after": after["shortage"],
            "shortage_delta": round(after["shortage"] - before["shortage"], 4)})
    result = {"plan_id": req.plan_id, "comparison": comparison, "areas": changed["areas"],
        "affected_before": base["overview"]["total_affected"], "affected_after": changed["overview"]["total_affected"],
        "water_coverage_before": base["resources"]["Water"]["coverage_pct"], "water_coverage_after": changed["resources"]["Water"]["coverage_pct"],
        "shock_water_pct": req.shock_water_pct, "shock_pop_pct": req.shock_pop_pct}
    store.record_event(req.plan_id, "SIMULATION", f"{req.shock_water_pct}:{req.shock_pop_pct}", result)
    return result


@app.post("/api/plans/{plan_id}/dispatch")
def approve_dispatch(plan_id: str, req: DispatchRequest):
    result = json.loads(plan_or_404(plan_id)["result"])
    action = next((a for a in result["actions"] if a["action_id"] == req.action_id), None)
    if not action:
        raise HTTPException(404, "Action does not belong to this plan.")
    event = store.record_event(plan_id, "DISPATCH_APPROVED", req.action_id, action)
    return {"status": "APPROVED_LOCALLY", "event_id": event["event_id"], "action": action,
        "message": "Approval recorded locally. No external convoy was dispatched."}


@app.post("/api/plans/{plan_id}/dispatch/status")
def update_dispatch(plan_id: str, req: DispatchUpdate):
    plan_or_404(plan_id)
    try:
        state = store.advance_dispatch(plan_id, req.action_id, req.status)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"action_id": req.action_id, "status": state,
            "message": f"{state.title()} status recorded locally from your confirmation."}


@app.post("/api/plans/{plan_id}/bulletin")
def save_bulletin(plan_id: str):
    result = json.loads(plan_or_404(plan_id)["result"])
    message = (f"Planning exercise: {result['inputs']['disaster_type']} response. "
        f"Estimated residents needing assistance: {result['overview']['total_affected']:,}. "
        f"Water demand coverage: {result['resources']['Water']['coverage_pct']}%. "
        "Locally saved project bulletin; not an official public alert.")
    event = store.record_event(plan_id, "BULLETIN_SAVED", "bulletin", {"message": message})
    return {"status": "SAVED_LOCALLY", "message": message, "event_id": event["event_id"]}


@app.get("/api/explain/{plan_id}/{area_id}")
def explain_area(plan_id: str, area_id: str):
    from core.explain import load_model_and_explainer, explain_single_area_prediction
    result = json.loads(plan_or_404(plan_id)["result"])
    area = next((a for a in result["areas"] if a["area_id"] == area_id), None)
    if area is None:
        raise HTTPException(404, "Area not found in this plan.")
    _, explainer, encoder = load_model_and_explainer(str(ROOT / "models/best_model.pkl"), str(ROOT / "models/shap_explainer.pkl"), str(ROOT / "models/label_encoder.pkl"))
    detail = explain_single_area_prediction(explainer, pd.Series(dict(area["features"], area_id=area_id)),
        area["predicted_severity"], class_names=list(encoder.classes_))
    return {"area_id": area_id, "predicted_class": detail["predicted_class"],
        "contributions": [{**c, "effect": "SUPPORTS CLASS" if c["shap_value"] > 0 else "OPPOSES CLASS"} for c in detail["contributions"]],
        "priority_components": area["priority_components"], "disclaimer": detail["disclaimer"]}


@app.get("/api/metrics")
def get_metrics():
    return model_metrics()


@app.get("/api/audit")
def get_audit_log():
    return [{**event, "payload": json.loads(event["payload"])} for event in store.events()]


def csv_response(records, filename):
    stream = io.StringIO()
    if records:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    return Response(stream.getvalue(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@app.get("/api/plans/{plan_id}/export.csv")
def export_plan(plan_id: str):
    result = json.loads(plan_or_404(plan_id)["result"])
    records = []
    for area in result["areas"]:
        for resource in result["resources"]:
            records.append({"area": area["area_name"], "population": area["population"], "estimated_affected": area["estimated_affected"],
                "predicted_severity": area["predicted_severity"], "priority_score": area["priority_score"], "priority_level": area["priority_level"],
                "resource": resource, "demand": area["demand"][resource], "allocated": area["allocation"][resource], "shortage": area["shortage"][resource]})
    return csv_response(records, f"reliefplan-{plan_id[:8]}.csv")


@app.get("/api/audit/export.csv")
def export_audit():
    return csv_response(store.events(), "reliefplan-audit.csv")


from funds_api import router as funds_router
app.include_router(funds_router)

if (ROOT / "frontend/dist").exists():
    app.mount("/", StaticFiles(directory=str(ROOT / "frontend/dist"), html=True), name="dashboard")
