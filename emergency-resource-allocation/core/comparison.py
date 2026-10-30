"""Transparent allocation baselines and synthetic training-range diagnostics."""
from functools import lru_cache
from pathlib import Path
import numpy as np
import pandas as pd
from core.data import ML_FEATURE_COLS


def equal_share(demand, stock):
    """Equal quantities with capped demand; redistribute unused shares."""
    allocation = np.zeros(len(demand), dtype=float)
    remaining = min(float(stock), float(demand.sum()))
    active = demand > 0
    while remaining > 1e-8 and active.any():
        share = remaining / int(active.sum())
        extra = np.where(active, np.minimum(demand - allocation, share), 0)
        allocation += extra
        remaining -= float(extra.sum())
        active = demand - allocation > 1e-8
    return allocation


def compare_strategies(frame, supplies):
    records = []
    # Match the optimizer's positive minimum objective weight.
    priority = np.maximum(frame["priority_score"].to_numpy(dtype=float), 0.05)
    for resource, stock in supplies.items():
        demand = frame[f"demand_{resource}"].to_numpy(dtype=float)
        proportional = demand * min(1, float(stock) / demand.sum()) if demand.sum() else demand.copy()
        for label, allocation in [
            ("Optimized", frame[f"opt_alloc_{resource}"].to_numpy(dtype=float)),
            ("Demand proportional", proportional),
            ("Equal quantities", equal_share(demand, stock)),
        ]:
            positive = demand > 0
            fractions = np.divide(allocation, demand, out=np.zeros_like(demand), where=positive)
            weight = priority[positive].sum()
            weighted = float((priority * fractions).sum() / weight) if weight else float(fractions[positive].mean()) if positive.any() else 1
            records.append({"resource": resource, "strategy": label,
                "allocated": round(float(allocation.sum()), 4),
                "shortage": round(max(0, float(demand.sum() - allocation.sum())), 4),
                "minimum_coverage_pct": round(float(fractions[positive].min()) * 100, 2) if positive.any() else 100,
                "priority_weighted_coverage_pct": round(weighted * 100, 2)})
    return records


@lru_cache(maxsize=1)
def training_ranges():
    path = Path(__file__).resolve().parents[1] / "data/historical_disaster_damage.csv"
    if not path.exists():
        return {}
    frame = pd.read_csv(path)
    return {key: (float(frame[key].min()), float(frame[key].max())) for key in ML_FEATURE_COLS if key in frame}


def input_range_warnings(frame):
    ranges = training_ranges()
    warnings = []
    for _, row in frame.iterrows():
        if not str(row["area_id"]).startswith("loc_"):
            continue
        outside = [key for key, (low, high) in ranges.items() if not low <= float(row[key]) <= high]
        if outside:
            warnings.append({"area_id": row["area_id"], "area_name": row["area_name"], "features": outside,
                "message": "Inputs outside the synthetic training-data range; interpret the prediction cautiously."})
    return warnings
