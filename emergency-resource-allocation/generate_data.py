import pandas as pd
# pyrefly: ignore [missing-import]
import numpy as np

def generate_datasets():
    # 1. Disasters (EM-DAT style)
    disasters_data = {
        'disaster_id': ['D001', 'D002', 'D003'],
        'disaster_type': ['Flood', 'Earthquake', 'Cyclone'],
        'date': ['2023-05-10', '2023-08-15', '2023-09-20'],
        'country': ['USA', 'USA', 'USA'],
        'region': ['Texas', 'California', 'Florida'],
        'location': ['Houston', 'San Francisco', 'Miami'],
        'magnitude': [7.5, 6.8, 4.2], # Flood depth(ft), Richter, Category
        'total_affected': [15000, 8000, 25000],
        'total_deaths': [15, 45, 12],
        'economic_damage': [5000000, 12000000, 8000000]
    }
    pd.DataFrame(disasters_data).to_csv('data/disasters.csv', index=False)

    # Houston Study Area Nodes (A to J)
    nodes = {
        'A': (29.7604, -95.3698), 'B': (29.7700, -95.3800), 'C': (29.7500, -95.3500),
        'D': (29.7800, -95.3900), 'E': (29.7400, -95.3400), 'F': (29.7900, -95.4000),
        'G': (29.7300, -95.3300), 'H': (29.8000, -95.4100), 'I': (29.7200, -95.3200),
        'J': (29.8100, -95.4200)
    }

    # 2. Population (WorldPop style)
    population_data = []
    for node, coords in nodes.items():
        population_data.append({
            'area_id': node,
            'area_name': f'Area_{node}',
            'latitude': coords[0],
            'longitude': coords[1],
            'population': np.random.randint(500, 5000),
            'population_density': np.random.randint(1000, 8000),
            'children_population': np.random.randint(100, 1000),
            'elderly_population': np.random.randint(50, 800)
        })
    pd.DataFrame(population_data).to_csv('data/population.csv', index=False)

    # 3. Damage (xBD style)
    damage_data = []
    for node in nodes.keys():
        total_b = np.random.randint(100, 1000)
        minor = int(total_b * np.random.uniform(0.1, 0.4))
        major = int(total_b * np.random.uniform(0.05, 0.3))
        destroyed = int(total_b * np.random.uniform(0.0, 0.2))
        intact = total_b - minor - major - destroyed
        sev = 'LOW'
        if destroyed / total_b > 0.15: sev = 'CRITICAL'
        elif (major+destroyed) / total_b > 0.2: sev = 'HIGH'
        elif (minor+major+destroyed) / total_b > 0.3: sev = 'MEDIUM'
        
        damage_data.append({
            'area_id': node,
            'disaster_id': 'D001',
            'building_damage': minor + major + destroyed,
            'damaged_buildings': minor + major + destroyed,
            'minor_damage': minor,
            'major_damage': major,
            'destroyed_buildings': destroyed,
            'damage_severity': sev
        })
    pd.DataFrame(damage_data).to_csv('data/damage.csv', index=False)

    # 4. Roads (OSM style)
    roads_data = []
    node_list = list(nodes.keys())
    for i in range(len(node_list)):
        for j in range(i+1, len(node_list)):
            if np.random.rand() > 0.4: # 60% connectivity
                dist = np.random.uniform(1.0, 15.0)
                roads_data.append({
                    'source': node_list[i],
                    'destination': node_list[j],
                    'distance_km': round(dist, 2),
                    'travel_time_min': round(dist * 1.5, 2),
                    'road_type': np.random.choice(['highway', 'primary', 'secondary']),
                    'road_condition': np.random.choice(['GOOD', 'GOOD', 'DAMAGED', 'SEVERELY_DAMAGED']),
                    'road_status': np.random.choice(['OPEN', 'OPEN', 'OPEN', 'DAMAGED', 'BLOCKED'])
                })
    pd.DataFrame(roads_data).to_csv('data/roads.csv', index=False)

    # 5. Resources
    resources_data = [
        {'resource_id': 'R1', 'resource_type': 'Food', 'quantity': 10000, 'warehouse_id': 'W1'},
        {'resource_id': 'R2', 'resource_type': 'Water', 'quantity': 20000, 'warehouse_id': 'W1'},
        {'resource_id': 'R3', 'resource_type': 'Medical_Kit', 'quantity': 5000, 'warehouse_id': 'W2'},
        {'resource_id': 'R4', 'resource_type': 'Food', 'quantity': 5000, 'warehouse_id': 'W2'},
    ]
    pd.DataFrame(resources_data).to_csv('data/resources.csv', index=False)

    # 6. Warehouses
    warehouses_data = [
        {'warehouse_id': 'W1', 'warehouse_name': 'Central Depot', 'latitude': 29.7550, 'longitude': -95.3600},
        {'warehouse_id': 'W2', 'warehouse_name': 'North Depot', 'latitude': 29.7850, 'longitude': -95.3950},
    ]
    pd.DataFrame(warehouses_data).to_csv('data/warehouses.csv', index=False)

    # 7. Hospitals
    hospitals_data = [
        {'hospital_id': 'H1', 'hospital_name': 'General Hospital', 'latitude': 29.7650, 'longitude': -95.3700, 'total_capacity': 500, 'available_beds': 120, 'emergency_capacity': 50, 'medical_staff': 80},
        {'hospital_id': 'H2', 'hospital_name': 'City Medical', 'latitude': 29.7450, 'longitude': -95.3450, 'total_capacity': 300, 'available_beds': 45, 'emergency_capacity': 20, 'medical_staff': 40},
    ]
    pd.DataFrame(hospitals_data).to_csv('data/hospitals.csv', index=False)

    # 8. Shelters
    shelters_data = [
        {'shelter_id': 'S1', 'shelter_name': 'High School Shelter', 'latitude': 29.7750, 'longitude': -95.3850, 'capacity': 1000, 'occupied': 200, 'available_capacity': 800},
        {'shelter_id': 'S2', 'shelter_name': 'Community Center', 'latitude': 29.7350, 'longitude': -95.3350, 'capacity': 500, 'occupied': 450, 'available_capacity': 50},
    ]
    pd.DataFrame(shelters_data).to_csv('data/shelters.csv', index=False)

    # 9. Scenarios
    scenarios_data = [
        {'scenario_id': 'SC1', 'name': 'Flood', 'description': 'High water requirement, blocked roads'},
        {'scenario_id': 'SC2', 'name': 'Earthquake', 'description': 'High building damage, high medical demand'},
        {'scenario_id': 'SC3', 'name': 'Cyclone', 'description': 'Infrastructure damage, shelter requirement'},
    ]
    pd.DataFrame(scenarios_data).to_csv('data/scenarios.csv', index=False)
    
    print("All synthetic datasets generated successfully.")

if __name__ == '__main__':
    generate_datasets()
