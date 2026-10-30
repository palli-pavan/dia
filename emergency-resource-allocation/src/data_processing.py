import pandas as pd
import os

def load_data(data_dir="data"):
    """Loads all CSV files from the data directory into a dictionary of DataFrames."""
    datasets = {}
    files = [
        "disasters.csv", "population.csv", "damage.csv", 
        "roads.csv", "resources.csv", "warehouses.csv", 
        "hospitals.csv", "shelters.csv", "scenarios.csv"
    ]
    for file in files:
        path = os.path.join(data_dir, file)
        if os.path.exists(path):
            name = file.split(".")[0]
            datasets[name] = pd.read_csv(path)
        else:
            print(f"Warning: {path} not found.")
    return datasets

def prepare_ml_dataset(datasets):
    """
    Merges population, damage, and disaster data to create a unified dataset
    for the Machine Learning severity prediction model.
    """
    if "damage" not in datasets or "population" not in datasets or "disasters" not in datasets:
        raise ValueError("Missing essential datasets for ML preparation.")
    
    # Base is damage assessment per area
    df = datasets["damage"].copy()
    
    # Merge with population
    pop_df = datasets["population"]
    df = pd.merge(df, pop_df, on="area_id", how="left")
    
    # Merge with disasters
    disaster_df = datasets["disasters"]
    df = pd.merge(df, disaster_df, on="disaster_id", how="left")
    
    # Basic cleaning / feature engineering
    # Fill missing values if any
    df.fillna({
        'minor_damage': 0, 'major_damage': 0, 'destroyed_buildings': 0,
        'population_density': df['population_density'].mean() if 'population_density' in df else 0
    }, inplace=True)
    
    return df

if __name__ == "__main__":
    # Quick test
    data = load_data("data")
    if data:
        ml_df = prepare_ml_dataset(data)
        print("ML Dataset Shape:", ml_df.shape)
        print(ml_df.head())
