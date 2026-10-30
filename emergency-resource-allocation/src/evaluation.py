import pandas as pd
import numpy as np

def calculate_baseline(affected_areas, resources_df):
    """
    Allocates resources proportionally to population as a baseline method.
    """
    areas = affected_areas.copy()
    total_pop = areas['population'].sum()
    
    # Calculate proportion
    areas['pop_proportion'] = areas['population'] / total_pop if total_pop > 0 else 0
    
    # Total available resources
    avail_resources = resources_df.groupby('resource_type')['quantity'].sum().to_dict()
    
    allocations = []
    for _, area in areas.iterrows():
        a_id = area['area_id']
        demands = area.get('demand', {'Food': 0, 'Water': 0, 'Medical_Kit': 0})
        
        for r_type, avail in avail_resources.items():
            req = demands.get(r_type, 0)
            if req > 0:
                # Proportional allocation
                allocated = int(avail * area['pop_proportion'])
                # Cannot exceed demand
                allocated = min(allocated, req)
                
                if allocated > 0:
                    allocations.append({
                        'area_id': a_id,
                        'resource_type': r_type,
                        'baseline_allocated': allocated
                    })
                    
    return pd.DataFrame(allocations)

def evaluate_performance(areas_df, optimal_df, baseline_df):
    """
    Compares Baseline vs Optimized.
    """
    results = {}
    
    # Demand data structure
    demand_flat = []
    for _, r in areas_df.iterrows():
        d = r['demand']
        for k, v in d.items():
            demand_flat.append({'area_id': r['area_id'], 'resource_type': k, 'demand': v, 'priority': r['priority_score']})
    d_df = pd.DataFrame(demand_flat)
    
    # Summarize optimized
    opt_sum = optimal_df.groupby(['area_id', 'resource_type'])['allocated'].sum().reset_index()
    # Summarize baseline
    if not baseline_df.empty:
        base_sum = baseline_df.groupby(['area_id', 'resource_type'])['baseline_allocated'].sum().reset_index()
    else:
        base_sum = pd.DataFrame(columns=['area_id', 'resource_type', 'baseline_allocated'])
        
    merge_df = d_df.merge(opt_sum, on=['area_id', 'resource_type'], how='left').fillna(0)
    merge_df = merge_df.merge(base_sum, on=['area_id', 'resource_type'], how='left').fillna(0)
    
    # Metrics calculation
    merge_df['opt_shortage'] = merge_df['demand'] - merge_df['allocated']
    merge_df['base_shortage'] = merge_df['demand'] - merge_df['baseline_allocated']
    
    # 1. Total Unmet Demand (Shortage)
    results['Total Shortage (Baseline)'] = merge_df['base_shortage'].sum()
    results['Total Shortage (Optimized)'] = merge_df['opt_shortage'].sum()
    
    # 2. Critical Demand Satisfaction
    crit_mask = merge_df['priority'] >= 0.8
    crit_demand = merge_df.loc[crit_mask, 'demand'].sum()
    if crit_demand > 0:
        opt_crit_alloc = merge_df.loc[crit_mask, 'allocated'].sum()
        base_crit_alloc = merge_df.loc[crit_mask, 'baseline_allocated'].sum()
        results['Critical Satisfaction (Baseline)'] = f"{(base_crit_alloc/crit_demand)*100:.1f}%"
        results['Critical Satisfaction (Optimized)'] = f"{(opt_crit_alloc/crit_demand)*100:.1f}%"
    else:
        results['Critical Satisfaction (Baseline)'] = "N/A"
        results['Critical Satisfaction (Optimized)'] = "N/A"
        
    # 3. Transportation Distance & Time
    results['Total Distance (Optimized)'] = optimal_df['distance'].sum() if not optimal_df.empty else 0
    results['Average Response Time (Optimized)'] = optimal_df['travel_time'].mean() if not optimal_df.empty else 0
    
    return results
