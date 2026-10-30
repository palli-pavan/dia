import pandas as pd
import numpy as np

# Configurable assumptions
DEMAND_CONFIG = {
    'food_units_per_person': 2.0,
    'water_units_per_person': 3.0,
    'medical_factor': 0.1 # 10% of affected population need medical kits
}

def calculate_demand(affected_population, injured_population=None):
    """
    Calculates resource demand based on configurable assumptions.
    """
    food_demand = affected_population * DEMAND_CONFIG['food_units_per_person']
    water_demand = affected_population * DEMAND_CONFIG['water_units_per_person']
    
    if injured_population is None:
        injured_population = affected_population * DEMAND_CONFIG['medical_factor']
        
    medical_demand = injured_population * 1.0 # 1 kit per injured person
    
    return {
        'Food': round(food_demand),
        'Water': round(water_demand),
        'Medical_Kit': round(medical_demand)
    }

def estimate_affected_population(population, damage_severity):
    """
    Estimates the affected population using disaster severity.
    """
    impact_factors = {
        'CRITICAL': 0.9,
        'HIGH': 0.7,
        'MEDIUM': 0.4,
        'LOW': 0.1
    }
    factor = impact_factors.get(damage_severity, 0.1)
    return int(population * factor)
