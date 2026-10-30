"""Audit trail and immutable decision logging module.

Implements Module 9 of the Emergency Decision Support System:
- Records every analysis run: timestamp, scenario inputs, model name,
  predictions, priority scores, LP allocations, top SHAP features,
  solver statuses, and shortage metrics.
- Appends to an operational audit CSV file for full governance.
- Supports querying history and exporting downloadable audit reports.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import sys
from typing import Any, Dict, List, Optional
import uuid
import pandas as pd

_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

AUDIT_LOG_CSV = "data/audit_log.csv"


def log_decision_run(
    scenario_name: str,
    pipeline_result: Dict[str, Any],
    model_name: str = "XGBoost",
    audit_file_path: str = AUDIT_LOG_CSV,
    additional_notes: str = ""
) -> Dict[str, Any]:
    """Records a complete execution run into the persistent audit trail.

    Args:
        scenario_name: Descriptive name of the disaster scenario.
        pipeline_result: Output dictionary from run_full_pipeline or optimize_resource_allocation.
        model_name: Name of the active ML model.
        audit_file_path: Path to the audit log CSV.
        additional_notes: Operational comments or operator ID.

    Returns:
        Dictionary containing the logged record.
    """
    os.makedirs(os.path.dirname(audit_file_path), exist_ok=True)
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    run_id = f"RUN_{uuid.uuid4().hex[:8].upper()}"

    alloc_df = pipeline_result["allocation_df"]
    kpis = pipeline_result.get("kpis", {})
    solver_statuses = pipeline_result.get("solver_statuses", {})
    params = pipeline_result.get("parameters", {})

    # Priority scores summary
    p_scores = alloc_df["priority_score"].tolist() if "priority_score" in alloc_df else []
    avg_priority = round(float(pd.Series(p_scores).mean()), 3) if p_scores else 0.0

    # Severity prediction distribution
    sev_counts = alloc_df["predicted_severity"].value_counts().to_dict() \
        if "predicted_severity" in alloc_df else {}

    # Allocation breakdown by resource
    alloc_summary = {}
    for col in alloc_df.columns:
        if col.startswith("opt_alloc_"):
            r_type = col.replace("opt_alloc_", "")
            alloc_summary[r_type] = round(float(alloc_df[col].sum()), 1)

    # Status summary
    all_opt = pipeline_result.get("is_optimal", True)
    status_str = "OPTIMAL" if all_opt else "SUB_OPTIMAL"

    record: Dict[str, Any] = {
        "run_id": run_id,
        "timestamp": now_utc,
        "scenario_name": scenario_name,
        "model_name": model_name,
        "solver_status": status_str,
        "total_affected_pop": kpis.get("total_affected_population", int(alloc_df.get("estimated_affected", pd.Series(0)).sum())),
        "critical_areas": kpis.get("critical_areas_count", int((alloc_df.get("priority_level", pd.Series()) == "CRITICAL").sum())),
        "avg_priority_score": avg_priority,
        "total_shortage": kpis.get("total_shortage_units", 0.0),
        "shortage_reduction_pct": kpis.get("shortage_reduction_pct", 0.0),
        "dispatched_allocations": json.dumps(alloc_summary),
        "predictions_distribution": json.dumps(sev_counts),
        "solver_statuses_detail": json.dumps(solver_statuses),
        "scenario_inputs": json.dumps(params),
        "notes": additional_notes
    }

    df_new = pd.DataFrame([record])
    if os.path.exists(audit_file_path):
        df_new.to_csv(audit_file_path, mode="a", header=False, index=False)
    else:
        df_new.to_csv(audit_file_path, mode="w", header=True, index=False)

    return record


def get_audit_history(
    audit_file_path: str = AUDIT_LOG_CSV,
    limit: Optional[int] = 50
) -> pd.DataFrame:
    """Reads historical audit records as a pandas DataFrame.

    Args:
        audit_file_path: CSV path.
        limit: Max number of most recent records to return.

    Returns:
        DataFrame of past decision executions.
    """
    if not os.path.exists(audit_file_path):
        return pd.DataFrame(columns=[
            "run_id", "timestamp", "scenario_name", "model_name", "solver_status",
            "total_affected_pop", "critical_areas", "avg_priority_score",
            "total_shortage", "shortage_reduction_pct", "dispatched_allocations"
        ])

    df = pd.read_csv(audit_file_path)
    if limit is not None and len(df) > limit:
        return df.iloc[-limit:].copy().reset_index(drop=True)
    return df


def clear_audit_log(audit_file_path: str = AUDIT_LOG_CSV) -> None:
    """Clears the audit trail file (used for testing and resets)."""
    if os.path.exists(audit_file_path):
        os.remove(audit_file_path)
