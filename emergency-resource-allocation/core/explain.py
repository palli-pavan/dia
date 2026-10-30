"""Explainable AI (XAI) and priority score decomposition module.

Implements Module 6 of the Emergency Decision Support System:
- Uses SHAP TreeExplainer to interpret ML damage severity predictions.
- Computes Global Feature Importance (mean |SHAP| values).
- Generates Local Per-Area Explanations with feature contributions and waterfall charts.
- Produces plain-English natural language narratives quoting real values.
- Explicitly mandates: "Contributions describe model behaviour, not causation."
- Decomposes the mathematical Priority Score into its weighted components.
"""

from __future__ import annotations

import os
import sys
from typing import Any, Dict, List, Optional, Tuple, Union
import joblib
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import shap

_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

from core.data import ML_FEATURE_COLS, SEVERITY_CLASSES
from core.priority import DEFAULT_WEIGHTS

DISCLAIMER_TEXT: str = "Contributions describe model behaviour, not causation."


def load_model_and_explainer(
    model_path: str = "models/best_model.pkl",
    explainer_path: str = "models/shap_explainer.pkl",
    encoder_path: str = "models/label_encoder.pkl"
) -> Tuple[Any, Any, Optional[Any]]:
    """Loads saved model, SHAP TreeExplainer, and label encoder from disk."""
    if not os.path.exists(model_path):
        model_path = "models/damage_model.pkl"

    if not os.path.exists(model_path) or not os.path.exists(explainer_path):
        raise FileNotFoundError(
            f"Model or explainer file missing ({model_path}, {explainer_path}). Run Phase 2 training first."
        )

    model = joblib.load(model_path)
    explainer = joblib.load(explainer_path)
    encoder = joblib.load(encoder_path) if os.path.exists(encoder_path) else None

    return model, explainer, encoder


def compute_global_feature_importance(
    explainer: Any,
    X_samples: pd.DataFrame,
    feature_names: Optional[List[str]] = None
) -> Tuple[Dict[str, float], go.Figure]:
    """Computes global feature importance across samples using mean |SHAP|.

    Args:
        explainer: Fitted SHAP TreeExplainer.
        X_samples: Feature matrix.
        feature_names: List of feature names.

    Returns:
        Tuple of (importance_dict, plotly_bar_figure).
    """
    feats = feature_names or ML_FEATURE_COLS
    X_clean = X_samples[feats].copy().fillna(0)
    shap_vals = explainer.shap_values(X_clean)

    # Handle multi-class vs single output shape
    if isinstance(shap_vals, list):
        # List of arrays per class: average across classes
        mean_abs_per_class = [np.abs(sv).mean(axis=0) for sv in shap_vals]
        global_imp = np.mean(mean_abs_per_class, axis=0)
    elif isinstance(shap_vals, np.ndarray) and shap_vals.ndim == 3:
        # Array of shape (n_samples, n_features, n_classes)
        global_imp = np.abs(shap_vals).mean(axis=(0, 2))
    else:
        global_imp = np.abs(shap_vals).mean(axis=0)

    imp_dict = {feats[i]: round(float(global_imp[i]), 4) for i in range(len(feats))}
    sorted_items = sorted(imp_dict.items(), key=lambda x: x[1], reverse=True)

    # Build Plotly Figure
    df_plot = pd.DataFrame(sorted_items, columns=["Feature", "Mean_Abs_SHAP"])
    fig = px.bar(
        df_plot,
        x="Mean_Abs_SHAP",
        y="Feature",
        orientation="h",
        title="Global ML Feature Importance (Mean |SHAP Value|)",
        labels={"Mean_Abs_SHAP": "Mean |SHAP Value| (Impact on Severity)", "Feature": "Feature Name"},
        color="Mean_Abs_SHAP",
        color_continuous_scale="Viridis"
    )
    fig.update_layout(
        yaxis={"autorange": "reversed"},
        template="plotly_dark",
        margin=dict(l=40, r=40, t=60, b=40),
        annotations=[{
            "text": DISCLAIMER_TEXT,
            "xref": "paper",
            "yref": "paper",
            "x": 0.0,
            "y": -0.20,
            "showarrow": False,
            "font": {"size": 11, "color": "gray"}
        }]
    )

    return dict(sorted_items), fig


def explain_single_area_prediction(
    explainer: Any,
    area_row: pd.Series,
    predicted_class: str,
    class_names: Optional[List[str]] = None,
    feature_names: Optional[List[str]] = None
) -> Dict[str, Any]:
    """Provides local SHAP explanation for a specific area's damage prediction.

    Args:
        explainer: Fitted SHAP TreeExplainer.
        area_row: Row containing area feature attributes.
        predicted_class: The severity class predicted by the model.
        class_names: Ordered list of target classes.
        feature_names: List of input feature names.

    Returns:
        Dictionary containing feature values, SHAP contributions, narrative, and Plotly figure.
    """
    feats = feature_names or ML_FEATURE_COLS
    c_names = class_names or SEVERITY_CLASSES

    # Vector of single area features
    X_single = pd.DataFrame([pd.to_numeric(area_row[feats], errors="coerce").fillna(0).to_dict()])
    shap_vals = explainer.shap_values(X_single)

    # Class index determination
    pred_idx = 0
    if predicted_class in c_names:
        pred_idx = c_names.index(predicted_class)

    if isinstance(shap_vals, list):
        area_shap = shap_vals[pred_idx][0]
    elif isinstance(shap_vals, np.ndarray) and shap_vals.ndim == 3:
        area_shap = shap_vals[0, :, pred_idx]
    elif isinstance(shap_vals, np.ndarray) and shap_vals.ndim == 2:
        area_shap = shap_vals[0]
    else:
        area_shap = np.array(shap_vals).flatten()

    contributions = []
    for i, f in enumerate(feats):
        val = float(area_row.get(f, 0.0))
        c_val = float(area_shap[i]) if i < len(area_shap) else 0.0
        contributions.append({
            "feature": f,
            "feature_value": val,
            "shap_value": round(c_val, 4),
            "effect": "INCREASED RISK" if c_val > 0 else "DECREASED RISK"
        })

    # Sort contributions by absolute SHAP value
    contributions.sort(key=lambda x: abs(x["shap_value"]), reverse=True)

    # Natural Language Narrative
    top_push = [c for c in contributions if c["shap_value"] > 0]
    top_pull = [c for c in contributions if c["shap_value"] < 0]

    narrative_parts = [
        f"The ML model classified Area {area_row.get('area_id', 'Unknown')} as **{predicted_class}** severity."
    ]

    if top_push:
        lead = top_push[0]
        narrative_parts.append(
            f"The primary factor driving higher severity was **{lead['feature']} = {lead['feature_value']:,}** "
            f"(SHAP impact: +{lead['shap_value']:.4f})."
        )
    if len(top_push) > 1:
        second = top_push[1]
        narrative_parts.append(
            f"This was reinforced by **{second['feature']} = {second['feature_value']:,}** (+{second['shap_value']:.4f})."
        )
    if top_pull:
        mit = top_pull[0]
        narrative_parts.append(
            f"Conversely, **{mit['feature']} = {mit['feature_value']:,}** slightly mitigated the risk score ({mit['shap_value']:.4f})."
        )

    narrative_parts.append(f"\n*{DISCLAIMER_TEXT}*")
    plain_english = " ".join(narrative_parts)

    # Plotly Waterfall / Bar Chart
    df_contrib = pd.DataFrame(contributions)
    colors = ["#EF553B" if v > 0 else "#00CC96" for v in df_contrib["shap_value"]]

    fig = go.Figure(go.Bar(
        x=df_contrib["shap_value"],
        y=df_contrib["feature"],
        orientation="h",
        marker_color=colors,
        text=[f"{v:+.4f} (val: {r['feature_value']})" for v, r in zip(df_contrib["shap_value"], contributions)],
        textposition="auto"
    ))
    fig.update_layout(
        title=f"Local SHAP Feature Contributions for Area {area_row.get('area_id', '')} (Class: {predicted_class})",
        xaxis_title="SHAP Value (Contribution to Prediction)",
        yaxis_title="Feature",
        yaxis={"autorange": "reversed"},
        template="plotly_dark",
        margin=dict(l=40, r=40, t=60, b=50),
        annotations=[{
            "text": DISCLAIMER_TEXT,
            "xref": "paper",
            "yref": "paper",
            "x": 0.0,
            "y": -0.22,
            "showarrow": False,
            "font": {"size": 11, "color": "gray"}
        }]
    )

    return {
        "area_id": str(area_row.get("area_id", "")),
        "predicted_class": predicted_class,
        "contributions": contributions,
        "narrative": plain_english,
        "disclaimer": DISCLAIMER_TEXT,
        "figure": fig
    }


def decompose_priority_score_components(
    area_row: pd.Series,
    weights: Optional[Dict[str, float]] = None
) -> Tuple[Dict[str, float], go.Figure]:
    """Decomposes an area's total priority score into its transparent weighted factors.

    Formula:
        priority = comp_impact + comp_demand + comp_shortage + comp_medical + comp_accessibility

    Args:
        area_row: Enriched area row containing 'comp_*' and 'priority_score'.
        weights: Optional dictionary of active weights.

    Returns:
        Tuple of (breakdown_dict, plotly_horizontal_bar_figure).
    """
    w = weights or DEFAULT_WEIGHTS
    area_id = str(area_row.get("area_id", "Unknown"))
    tot_score = float(area_row.get("priority_score", 0.0))

    components = {
        "Structural Impact (w1)": float(area_row.get("comp_impact", 0.0)),
        "Estimated Demand (w2)": float(area_row.get("comp_demand", 0.0)),
        "Unmet Shortage (w3)": float(area_row.get("comp_shortage", 0.0)),
        "Medical / Vulnerable Need (w4)": float(area_row.get("comp_medical_need", 0.0)),
        "Accessibility Penalty (w5)": float(area_row.get("comp_accessibility", 0.0)),
    }

    df_comp = pd.DataFrame(list(components.items()), columns=["Factor", "Weighted_Score"])

    fig = px.bar(
        df_comp,
        x="Weighted_Score",
        y="Factor",
        orientation="h",
        title=f"Priority Score Decomposition for Area {area_id} (Total Score: {tot_score:.3f})",
        labels={"Weighted_Score": "Weighted Component Contribution", "Factor": "Factor"},
        color="Weighted_Score",
        color_continuous_scale="Sunset"
    )
    fig.update_layout(
        yaxis={"autorange": "reversed"},
        template="plotly_dark",
        margin=dict(l=40, r=40, t=60, b=40)
    )

    return components, fig
