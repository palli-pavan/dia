import pandas as pd
import networkx as nx

def build_road_network(roads_df):
    """
    Builds a NetworkX graph from the roads dataframe.
    Adjusts travel cost based on road condition/status.
    """
    G = nx.Graph()
    
    for _, row in roads_df.iterrows():
        source = row['source']
        dest = row['destination']
        dist = row['distance_km']
        time = row['travel_time_min']
        status = row['road_status']
        condition = row['road_condition']
        
        # Adjust travel time based on status/condition
        if status == 'BLOCKED':
            continue # Cannot use this road
            
        multiplier = 1.0
        if status == 'DAMAGED':
            multiplier = 2.0
        elif condition == 'SEVERELY_DAMAGED':
            multiplier = 1.5
            
        G.add_edge(
            source, 
            dest, 
            distance=dist, 
            travel_time=time * multiplier,
            status=status
        )
        
    return G

def get_shortest_path(G, source, target, weight='travel_time'):
    """
    Calculates the shortest path between two nodes.
    """
    try:
        path = nx.shortest_path(G, source=source, target=target, weight=weight)
        cost = nx.shortest_path_length(G, source=source, target=target, weight=weight)
        
        # Calculate other metric
        other_weight = 'distance' if weight == 'travel_time' else 'travel_time'
        other_cost = sum(G[u][v][other_weight] for u, v in zip(path[:-1], path[1:]))
        
        return {
            'path': path,
            weight: cost,
            other_weight: other_cost,
            'accessible': True
        }
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return {
            'path': [],
            'travel_time': float('inf'),
            'distance': float('inf'),
            'accessible': False
        }
