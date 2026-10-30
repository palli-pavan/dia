import pandas as pd
from routing import get_shortest_path

def allocate_shelters(affected_areas_df, shelters_df, road_network):
    """
    Assigns displaced population from affected areas to the nearest available shelters.
    """
    allocations = []
    
    # Sort areas by priority
    areas = affected_areas_df.sort_values(by='priority_score', ascending=False)
    
    # Track available capacity
    available_capacity = dict(zip(shelters_df['shelter_id'], shelters_df['available_capacity']))
    
    for _, area in areas.iterrows():
        area_id = area['area_id']
        # Displaced population calculation (proxy: based on destroyed/major damaged buildings)
        b_total = area.get('building_damage', 1)
        b_severe = area.get('destroyed_buildings', 0) + area.get('major_damage', 0)
        displaced_ratio = min(b_severe / b_total, 1.0) if b_total > 0 else 0
        displaced = int(area['population'] * displaced_ratio)
        
        if displaced <= 0:
            continue
            
        remaining_displaced = displaced
        
        # Find reachable shelters
        reachable_shelters = []
        for _, shelter in shelters_df.iterrows():
            s_id = shelter['shelter_id']
            # Map shelters to nodes (S1 -> D, S2 -> G)
            s_node = 'D' if s_id == 'S1' else 'G'
            
            route = get_shortest_path(road_network, source=area_id, target=s_node)
            if route['accessible']:
                reachable_shelters.append({
                    'shelter_id': s_id,
                    'shelter_name': shelter['shelter_name'],
                    'travel_time': route['travel_time'],
                    'distance': route['distance']
                })
                
        # Sort by travel time
        reachable_shelters.sort(key=lambda x: x['travel_time'])
        
        for s in reachable_shelters:
            s_id = s['shelter_id']
            cap = available_capacity[s_id]
            
            if cap > 0:
                assigned = min(remaining_displaced, cap)
                available_capacity[s_id] -= assigned
                remaining_displaced -= assigned
                
                allocations.append({
                    'area_id': area_id,
                    'shelter_id': s_id,
                    'shelter_name': s['shelter_name'],
                    'people_assigned': assigned,
                    'distance': s['distance'],
                    'travel_time': s['travel_time']
                })
                
            if remaining_displaced <= 0:
                break
                
    return pd.DataFrame(allocations), available_capacity
