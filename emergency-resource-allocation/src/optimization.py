from ortools.linear_solver import pywraplp
import pandas as pd
from routing import get_shortest_path

def optimize_resources(affected_areas, resources_df, road_network):
    """
    Optimizes the allocation of resources from warehouses to affected areas.
    """
    solver = pywraplp.Solver.CreateSolver('SCIP')
    if not solver:
        raise Exception("SCIP solver not available")
        
    # Data extraction
    areas = affected_areas.to_dict('records')
    # Aggregate resources by warehouse and type
    warehouse_resources = {}
    for _, row in resources_df.iterrows():
        w_id = row['warehouse_id']
        r_type = row['resource_type']
        qty = row['quantity']
        if w_id not in warehouse_resources:
            warehouse_resources[w_id] = {}
        warehouse_resources[w_id][r_type] = warehouse_resources[w_id].get(r_type, 0) + qty
        
    warehouses = list(warehouse_resources.keys())
    resource_types = resources_df['resource_type'].unique()
    
    # Calculate routes from all warehouses to all areas
    # Mapping warehouses to nodes: W1->C, W2->H (for simulation)
    w_nodes = {'W1': 'C', 'W2': 'H'}
    routes = {}
    for w in warehouses:
        routes[w] = {}
        for a in areas:
            a_id = a['area_id']
            route = get_shortest_path(road_network, source=w_nodes.get(w, 'C'), target=a_id)
            routes[w][a_id] = route
            
    # Decision Variables: x[w, a, r] -> amount of resource r from warehouse w to area a
    x = {}
    for w in warehouses:
        for a in areas:
            a_id = a['area_id']
            for r in resource_types:
                # If no accessible route, we can't send resources, so max is 0
                max_val = solver.infinity() if routes[w][a_id]['accessible'] else 0
                x[(w, a_id, r)] = solver.IntVar(0, max_val, f'x_{w}_{a_id}_{r}')
                
    # Constraint 1: Resource allocation cannot exceed available inventory at warehouse
    for w in warehouses:
        for r in resource_types:
            avail = warehouse_resources[w].get(r, 0)
            solver.Add(sum(x[(w, a['area_id'], r)] for a in areas) <= avail)
            
    # Constraint 2: Allocation cannot exceed demand in each area
    for a in areas:
        a_id = a['area_id']
        demands = a.get('demand', {'Food': 0, 'Water': 0, 'Medical_Kit': 0})
        for r in resource_types:
            req = demands.get(r, 0)
            solver.Add(sum(x[(w, a_id, r)] for w in warehouses) <= req)
            
    # Objective Function
    # Minimize: Unmet Demand + Priority-Weighted Shortage + Transportation Cost
    objective = solver.Objective()
    
    for a in areas:
        a_id = a['area_id']
        priority = a.get('priority_score', 0.1)
        demands = a.get('demand', {'Food': 0, 'Water': 0, 'Medical_Kit': 0})
        
        for r in resource_types:
            req = demands.get(r, 0)
            allocated = sum(x[(w, a_id, r)] for w in warehouses)
            shortage = req - allocated
            
            # Shortage penalty (unmet demand) heavily weighted by priority
            # Add objective terms by creating a variable for shortage
            # Since solver.Minimize() takes a linear expression, we must substitute:
            # We want to minimize (req - allocated) * weight. 
            # Equivalently, maximize allocated * weight. 
            # We'll use solver.Maximize to make it simpler to frame.
            
            # Transportation cost penalty (minimize this, so subtract from maximize)
            transport_penalty = 0
            for w in warehouses:
                dist = routes[w][a_id].get('distance', float('inf'))
                if routes[w][a_id]['accessible']:
                    # Small penalty for distance
                    objective.SetCoefficient(x[(w, a_id, r)], priority * 1000 - dist * 0.1)
                
    objective.SetMaximization()
    status = solver.Solve()
    
    allocations = []
    if status == pywraplp.Solver.OPTIMAL or status == pywraplp.Solver.FEASIBLE:
        for w in warehouses:
            for a in areas:
                a_id = a['area_id']
                for r in resource_types:
                    val = x[(w, a_id, r)].solution_value()
                    if val > 0:
                        allocations.append({
                            'warehouse_id': w,
                            'area_id': a_id,
                            'resource_type': r,
                            'allocated': val,
                            'distance': routes[w][a_id]['distance'],
                            'travel_time': routes[w][a_id]['travel_time']
                        })
                        
    return pd.DataFrame(allocations)
