import pandas as pd

def calculate_priority(row, weights=None):
    """
    Calculates the emergency priority score for an affected area.
    Values should be normalized between 0 and 1.
    """
    if weights is None:
        weights = {
            'severity': 0.35,
            'population': 0.25,
            'vulnerability': 0.15,
            'medical_need': 0.15,
            'infrastructure': 0.10
        }
    
    # Severity mapping
    severity_map = {'CRITICAL': 1.0, 'HIGH': 0.75, 'MEDIUM': 0.5, 'LOW': 0.25}
    severity_score = severity_map.get(row.get('damage_severity', 'LOW'), 0.25)
    
    # Normalize population (assuming max population is around 10000 for this scale)
    pop_score = min(row.get('population', 0) / 10000, 1.0)
    
    # Vulnerability (children + elderly / total)
    vuln_pop = row.get('children_population', 0) + row.get('elderly_population', 0)
    total_pop = row.get('population', 1)
    vuln_score = min(vuln_pop / total_pop, 1.0) if total_pop > 0 else 0
    
    # Medical need (proxy: injured / total)
    medical_score = severity_score * 0.8 # Higher severity implies higher medical need
    
    # Infrastructure (destroyed buildings ratio)
    b_total = row.get('building_damage', 1)
    b_destroyed = row.get('destroyed_buildings', 0)
    infra_score = min(b_destroyed / b_total, 1.0) if b_total > 0 else 0
    
    priority = (
        weights['severity'] * severity_score +
        weights['population'] * pop_score +
        weights['vulnerability'] * vuln_score +
        weights['medical_need'] * medical_score +
        weights['infrastructure'] * infra_score
    )
    
    return priority

def get_priority_level(score):
    if score >= 0.80:
        return 'CRITICAL'
    elif score >= 0.60:
        return 'HIGH'
    elif score >= 0.40:
        return 'MEDIUM'
    else:
        return 'LOW'
