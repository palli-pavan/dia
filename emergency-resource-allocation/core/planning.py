"""Shared, reproducible preparation for analysis and simulation."""
from pathlib import Path
import pandas as pd
from core.data import load_all_data
from core.simulate import run_full_pipeline

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POPULATIONS = dict(zip([f"Area {c}" for c in "ABCDEFG"], [1850, 2900, 3300, 4300, 3200, 3800, 2429]))
SEVERITY_MULTIPLIERS = {"Low": 0.65, "Moderate": 0.85, "High": 1.0, "Extreme": 1.2}


def prepare_scenario(config):
    data = load_all_data(str(ROOT / "data"))
    ids = [name.removeprefix("Area ") for name in config["area_populations"]]
    pop = data["population"].query("area_id in @ids").copy()
    pop["population_density"] = pop["population_density"].astype(float)
    for i, row in pop.iterrows():
        count = config["area_populations"][f"Area {row['area_id']}"]
        ratio = count / max(float(row["population"]), 1)
        vulnerable = float(row["children_population"] + row["elderly_population"]) * ratio
        scale = min(1, count / max(vulnerable, 1))
        for column in ["children_population", "elderly_population"]:
            pop.loc[i, column] = round(float(row[column]) * ratio * scale)
        pop.loc[i, "population_density"] = float(row["population_density"]) * ratio
        pop.loc[i, "population"] = count
    pop["area_name"] = pop["area_name"].str.replace("_", " ")
    data["population"] = pop
    data["damage"] = data["damage"].query("area_id in @ids").copy()
    data["roads"] = data["roads"][data["roads"]["source"].isin(ids) & data["roads"]["destination"].isin(ids)].copy()
    # A custom location supplies its own model features and coordinates. It does
    # not inherit damage, roads, or disaster magnitude from an example area.
    for location in config.get("locations", []):
        area_id = location["location_id"]
        disaster_id = f"custom_{area_id}"
        pop_row = {"area_id": area_id, "area_name": location["name"],
            **{key: location[key] for key in ["latitude", "longitude", "population", "population_density", "children_population", "elderly_population"]},
            "reported_affected": location.get("affected_population")}
        damage_row = {"area_id": area_id, "disaster_id": disaster_id,
            **{key: location[key] for key in ["minor_damage", "major_damage", "destroyed_buildings"]},
            "building_damage": sum(location[key] for key in ["minor_damage", "major_damage", "destroyed_buildings"]),
            "damage_severity": "UNKNOWN"}
        data["population"] = pd.concat([data["population"], pd.DataFrame([pop_row])], ignore_index=True)
        data["damage"] = pd.concat([data["damage"], pd.DataFrame([damage_row])], ignore_index=True)
        data["disasters"] = pd.concat([data["disasters"], pd.DataFrame([{
            "disaster_id": disaster_id, "disaster_type": config["disaster_type"], "magnitude": location["magnitude"]}])], ignore_index=True)
    resources = data["resources"].copy()
    resources["quantity"] = resources["quantity"].astype(float)
    for resource, field in [("Food", "food_supply"), ("Water", "water_supply"), ("Medical_Kit", "med_supply")]:
        mask = resources["resource_type"].eq(resource)
        original = resources.loc[mask, "quantity"]
        weights = original / original.sum() if original.sum() else original * 0 + 1 / len(original)
        resources.loc[mask, "quantity"] = weights * config[field]
    data["resources"] = resources
    rates = {"Food": 2.0, "Water": 2.0, "Medical_Kit": 0.12}
    if config["disaster_type"] == "Wildfire": rates.update(Water=2.5, Medical_Kit=0.18)
    if config["disaster_type"] == "Earthquake": rates["Medical_Kit"] = 0.25
    if config["disaster_type"] == "Cyclone": rates["Water"] = 2.5
    return data, rates


def execute_scenario(config, water_change=0.0, population_change=0.0):
    data, rates = prepare_scenario(config)
    result = run_full_pipeline(datasets=data, model_path=str(ROOT / "models/best_model.pkl"),
        encoder_path=str(ROOT / "models/label_encoder.pkl"), duration_days=config["duration_hours"] / 24,
        per_capita_needs=rates, affected_population_multiplier=SEVERITY_MULTIPLIERS[config["severity"]],
        minimum_service_fraction=config["minimum_service_fraction"],
        resource_supply_deltas={"Water": water_change}, population_delta_pct=population_change)
    result["parameters"].update(config)
    result["planning_rates"] = rates
    return result
