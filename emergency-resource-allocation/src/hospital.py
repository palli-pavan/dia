import pandas as pd
from routing import get_shortest_path

def allocate_hospitals(affected_areas_df, hospitals_df, road_network):
    """
    Assigns injured patients from affected areas to the nearest available hospitals.
    """
    allocations = []
    
    # Sort areas by priority
    areas = affected_areas_df.sort_values(by='priority_score', ascending=False)
    
    # Track available beds
    available_beds = dict(zip(hospitals_df['hospital_id'], hospitals_df['available_beds']))
    
    for _, area in areas.iterrows():
        area_id = area['area_id']
        injured = int(area['population'] * 0.1) # Configurable injured fraction
        if injured <= 0:
            continue
            
        remaining_injured = injured
        
        # Find reachable hospitals
        reachable_hospitals = []
        for _, hospital in hospitals_df.iterrows():
            h_id = hospital['hospital_id']
            # We assume hospitals are located at the nearest road node. In our synthetic data, they don't have explicit node IDs.
            # We'll map them by proximity or just simulate node mapping.
            # For this MVP, we map W1 to node A, W2 to J, H1 to node A, H2 to node E, S1 to D, S2 to G
            h_node = 'A' if h_id == 'H1' else 'E' 
            
            route = get_shortest_path(road_network, source=area_id, target=h_node)
            if route['accessible']:
                reachable_hospitals.append({
                    'hospital_id': h_id,
                    'hospital_name': hospital['hospital_name'],
                    'travel_time': route['travel_time'],
                    'distance': route['distance']
                })
                
        # Sort by travel time
        reachable_hospitals.sort(key=lambda x: x['travel_time'])
        
        for h in reachable_hospitals:
            h_id = h['hospital_id']
            beds = available_beds[h_id]
            
            if beds > 0:
                assigned = min(remaining_injured, beds)
                available_beds[h_id] -= assigned
                remaining_injured -= assigned
                
                allocations.append({
                    'area_id': area_id,
                    'hospital_id': h_id,
                    'hospital_name': h['hospital_name'],
                    'patients_assigned': assigned,
                    'distance': h['distance'],
                    'travel_time': h['travel_time']
                })
                
            if remaining_injured <= 0:
                break
                
    return pd.DataFrame(allocations), available_beds
