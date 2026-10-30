"""Data ingestion, validation, preprocessing, and synthetic historical data generator.

This module handles:
1. Loading all tabular datasets from disk with error reporting.
2. Validating schemas, checking missing values, types, and value boundaries.
3. Feature preprocessing and cleaning (imputation, scaling, alignment).
4. Generating realistic, labelled synthetic historical disaster training data.
"""

from __future__ import annotations

import os
import sys
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)


REQUIRED_COLUMNS: Dict[str, List[str]] = {
    "damage": [
        "area_id", "disaster_id", "building_damage", "minor_damage",
        "major_damage", "destroyed_buildings", "damage_severity"
    ],
    "disasters": [
        "disaster_id", "disaster_type", "date", "country", "region",
        "location", "magnitude", "total_affected", "total_deaths"
    ],
    "population": [
        "area_id", "area_name", "latitude", "longitude",
        "population", "population_density", "children_population", "elderly_population"
    ],
    "resources": ["resource_id", "resource_type", "quantity", "warehouse_id"],
    "warehouses": ["warehouse_id", "warehouse_name", "latitude", "longitude"],
    "roads": ["source", "destination", "distance_km", "travel_time_min", "road_type", "road_condition", "road_status"],
    "hospitals": ["hospital_id", "hospital_name", "latitude", "longitude", "total_capacity", "available_beds"],
    "shelters": ["shelter_id", "shelter_name", "latitude", "longitude", "capacity", "occupied", "available_capacity"],
    "scenarios": ["scenario_id", "name", "description"]
}

ML_FEATURE_COLS: List[str] = [
    "building_damage",
    "minor_damage",
    "major_damage",
    "destroyed_buildings",
    "population_density",
    "magnitude"
]

TARGET_COL: str = "damage_severity"
SEVERITY_CLASSES: List[str] = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]


def load_all_data(data_dir: str = "data") -> Dict[str, pd.DataFrame]:
    """Loads all system CSV files from the specified directory.

    Args:
        data_dir: Path to directory containing the CSV files.

    Returns:
        Dictionary mapping table names to pandas DataFrames.

    Raises:
        FileNotFoundError: If the directory does not exist or essential files are absent.
    """
    if not os.path.isdir(data_dir):
        raise FileNotFoundError(f"Data directory '{data_dir}' does not exist.")

    datasets: Dict[str, pd.DataFrame] = {}
    for table_name, req_cols in REQUIRED_COLUMNS.items():
        file_path = os.path.join(data_dir, f"{table_name}.csv")
        if os.path.exists(file_path):
            df = pd.read_csv(file_path)
            validate_dataset(df, table_name, req_cols)
            datasets[table_name] = df
        else:
            print(f"[WARNING] Table '{table_name}.csv' not found at {file_path}")

    return datasets


def validate_dataset(df: pd.DataFrame, dataset_name: str, required_cols: List[str]) -> bool:
    """Validates presence of required columns and reports data anomalies.

    Args:
        df: DataFrame to validate.
        dataset_name: Name of the dataset for logging.
        required_cols: List of required column names.

    Returns:
        True if all required columns are present.

    Raises:
        ValueError: If required columns are missing.
    """
    missing_cols = [c for c in required_cols if c not in df.columns]
    if missing_cols:
        raise ValueError(
            f"Dataset '{dataset_name}' is missing required columns: {missing_cols}"
        )

    # Check for empty dataframe
    if df.empty:
        print(f"[WARNING] Dataset '{dataset_name}' is empty.")

    # Check for non-negative values in numeric columns where negative makes no sense
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    for col in numeric_cols:
        if (df[col] < 0).any() and col not in ["latitude", "longitude"]:
            print(f"[WARNING] Dataset '{dataset_name}' column '{col}' contains negative numbers.")

    return True


def prepare_ml_dataset(datasets: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Merges damage, population, and disaster tables for model training or inference.

    Args:
        datasets: Dictionary of DataFrames as returned by load_all_data.

    Returns:
        Consolidated DataFrame with engineered features ready for ML ingestion.
    """
    if "damage" not in datasets or "population" not in datasets or "disasters" not in datasets:
        raise ValueError("Cannot prepare ML dataset: 'damage', 'population', or 'disasters' missing.")

    # Start from damage table
    df = datasets["damage"].copy()

    # Join population attributes by area_id
    pop_df = datasets["population"]
    df = pd.merge(df, pop_df, on="area_id", how="left")

    # Join disaster magnitude and characteristics by disaster_id
    disaster_df = datasets["disasters"]
    df = pd.merge(df, disaster_df, on="disaster_id", how="left")

    # Missing value imputation with safe defaults
    df["minor_damage"] = df["minor_damage"].fillna(0)
    df["major_damage"] = df["major_damage"].fillna(0)
    df["destroyed_buildings"] = df["destroyed_buildings"].fillna(0)
    
    if "building_damage" not in df.columns or df["building_damage"].isnull().all():
        df["building_damage"] = df["minor_damage"] + df["major_damage"] + df["destroyed_buildings"]
    else:
        df["building_damage"] = df["building_damage"].fillna(
            df["minor_damage"] + df["major_damage"] + df["destroyed_buildings"]
        )

    median_density = df["population_density"].median() if not df["population_density"].dropna().empty else 3000.0
    df["population_density"] = df["population_density"].fillna(median_density)

    median_mag = df["magnitude"].median() if not df["magnitude"].dropna().empty else 6.0
    df["magnitude"] = df["magnitude"].fillna(median_mag)

    return df


def generate_historical_training_data(
    output_path: str = "data/historical_disaster_damage.csv",
    n_samples: int = 800,
    random_state: int = 42
) -> pd.DataFrame:
    """Generates a realistic, documented synthetic historical disaster dataset.

    This ensures stratified cross-validation and multiple model comparisons
    can be performed rigorously without overfitting to the 10 scenario rows.

    Labels are generated based on structural engineering ratios with realistic
    random variance so that the ML task is non-trivial and models reflect realistic
    generalization scores (avoiding artificial 100% data leakage).

    Args:
        output_path: File path to save the generated synthetic CSV.
        n_samples: Number of historical records to generate.
        random_state: Seed for reproducibility.

    Returns:
        DataFrame containing generated historical disaster damage data.
    """
    rng = np.random.default_rng(random_state)

    disaster_types = ["Flood", "Earthquake", "Cyclone", "Wildfire"]
    hazard_magnitudes = {
        "Flood": (3.0, 10.0),       # Depth in feet
        "Earthquake": (4.5, 8.5),   # Richter scale
        "Cyclone": (1.0, 5.0),      # Saffir-Simpson category
        "Wildfire": (2.0, 9.0)      # Fire danger index
    }

    records: List[Dict[str, Any]] = []

    for i in range(n_samples):
        d_type = rng.choice(disaster_types)
        mag_min, mag_max = hazard_magnitudes[d_type]
        magnitude = round(float(rng.uniform(mag_min, mag_max)), 2)

        # Total building stock in area
        total_buildings = int(rng.integers(200, 2500))
        pop_density = int(rng.integers(500, 12000))

        # Normalized hazard impact intensity
        intensity = (magnitude - mag_min) / (mag_max - mag_min)
        # Add random vulnerability shock
        vuln_factor = rng.uniform(0.6, 1.4)
        effective_impact = np.clip(intensity * vuln_factor, 0.05, 0.95)

        # Proportion breakdown
        minor_ratio = float(np.clip(rng.normal(0.20 * effective_impact, 0.05), 0.02, 0.40))
        major_ratio = float(np.clip(rng.normal(0.18 * effective_impact, 0.05), 0.01, 0.40))
        destroyed_ratio = float(np.clip(rng.normal(0.12 * effective_impact, 0.04), 0.0, 0.35))

        minor_damage = int(total_buildings * minor_ratio)
        major_damage = int(total_buildings * major_ratio)
        destroyed = int(total_buildings * destroyed_ratio)
        total_damage = minor_damage + major_damage + destroyed

        # Latent severity index based on destruction intensity and magnitude
        comp_destroyed = destroyed / max(total_damage, 1)
        comp_major = major_damage / max(total_damage, 1)
        mag_norm = (magnitude - mag_min) / max(mag_max - mag_min, 1e-3)

        severity_score = (
            0.55 * comp_destroyed +
            0.30 * comp_major +
            0.15 * mag_norm
        )
        # Add realistic survey assessment noise
        noisy_score = severity_score + rng.normal(0, 0.02)

        if noisy_score >= 0.42:
            severity = "CRITICAL"
        elif noisy_score >= 0.27:
            severity = "HIGH"
        elif noisy_score >= 0.14:
            severity = "MEDIUM"
        else:
            severity = "LOW"

        records.append({
            "record_id": f"HIST_{i+1:04d}",
            "disaster_type": d_type,
            "magnitude": magnitude,
            "total_buildings": total_buildings,
            "building_damage": total_damage,
            "minor_damage": minor_damage,
            "major_damage": major_damage,
            "destroyed_buildings": destroyed,
            "population_density": pop_density,
            "damage_severity": severity,
            "data_source": "SYNTHETIC_HISTORICAL"
        })

    df_hist = pd.DataFrame(records)

    # Ensure output directory exists and save
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    df_hist.to_csv(output_path, index=False)
    print(f"[DATA] Generated {len(df_hist)} synthetic historical training records -> {output_path}")
    print("[DATA] Severity distribution:")
    print(df_hist["damage_severity"].value_counts().to_string())

    return df_hist


if __name__ == "__main__":
    # Self-test data module
    hist_data = generate_historical_training_data()
    raw_data = load_all_data("data")
    ml_prepared = prepare_ml_dataset(raw_data)
    print(f"[TEST] Successfully loaded {len(raw_data)} tables. Prepared ML shape: {ml_prepared.shape}")
