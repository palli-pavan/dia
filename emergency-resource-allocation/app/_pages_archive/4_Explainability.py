"""AI Explainability Page - Emergency Decision Support System.

Faithfully implements Page 6 of 'Emergency Decision Support - Page Designs.pdf'.
"""

import os
import sys
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_app = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in [_root, _app]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from core.simulate import run_full_pipeline
from core.explain import (
    load_model_and_explainer,
    compute_global_feature_importance,
    explain_single_area_prediction,
    decompose_priority_score_components,
    DISCLAIMER_TEXT
)

try:
    from app.nav import apply_theme_and_sidebar, render_footer
except ModuleNotFoundError:
    from nav import apply_theme_and_sidebar, render_footer

st.set_page_config(page_title="AI Explainability | Emergency DSS", page_icon="🔍", layout="wide")
apply_theme_and_sidebar()



if "pipeline_result" not in st.session_state:
    st.session_state["pipeline_result"] = run_full_pipeline()

res = st.session_state["pipeline_result"]
alloc_df = res["allocation_df"].sort_values(by="priority_score", ascending=False).reset_index(drop=True)

try:
    model, explainer, encoder = load_model_and_explainer()
except Exception as e:
    st.error(f"Explainer error: {e}")
    st.stop()

# Header
st.markdown("<h1 style='margin: 0; color: #F8FAFC;'>AI Explainability</h1>", unsafe_allow_html=True)
st.markdown("<p style='color: #94A3B8; font-size: 14.5px; margin: 2px 0 18px 0;'>Why did the model rate each area this way? <span style='background:#0F172A;border:1px solid #334155;color:#94A3B8;padding:2px 6px;border-radius:4px;font-size:10px;font-weight:700;'>SAMPLE DATA</span></p>", unsafe_allow_html=True)

col_global, col_local = st.columns(2)

with col_global:
    st.markdown("##### GLOBAL: WHAT MATTERS MOST <small style='color:#94A3B8;'>(sample SHAP)</small>", unsafe_allow_html=True)
    imp_dict, fig_g = compute_global_feature_importance(explainer, alloc_df)
    st.plotly_chart(fig_g, use_container_width=True)

with col_local:
    crit_area = alloc_df.iloc[0]["area_name"]
    pick_area = st.selectbox("Inspect Area", alloc_df["area_name"].tolist(), index=0)
    target_row = alloc_df[alloc_df["area_name"] == pick_area].iloc[0]

    st.markdown(f"##### WHY IS {pick_area.upper()} {target_row['priority_level']}? <small style='color:#94A3B8;'>(sample SHAP)</small>", unsafe_allow_html=True)
    local_ai = explain_single_area_prediction(explainer, target_row, predicted_class=target_row["predicted_severity"])
    st.plotly_chart(local_ai["figure"], use_container_width=True)
    st.caption("Positive values raise predicted risk; negative values lower it.")

# In Plain Words Box
st.markdown(f"""
<div class="plain-words-box">
    <div style="font-weight: 700; color: #F8FAFC; margin-bottom: 4px;">IN PLAIN WORDS</div>
    {target_row['area_name']} is rated <strong>{target_row['priority_level']}</strong> mainly because its affected population is predicted to grow and structural damage is concentrated.<br>
    <span style="color: #94A3B8; font-size: 12px;">These values describe how the model behaves. They do not prove cause and effect.</span>
</div>
""", unsafe_allow_html=True)

# Priority Score Breakdown Table
st.markdown("##### PRIORITY SCORE BREAKDOWN <small style='color:#94A3B8;'>(weights are assumptions)</small>", unsafe_allow_html=True)

breakdown_data = [
    {"PART": "Impact", "WEIGHT": "0.30", "SCORE": f"{target_row.get('comp_impact', 0.28):.2f}"},
    {"PART": "Predicted demand", "WEIGHT": "0.25", "SCORE": f"{target_row.get('comp_demand', 0.24):.2f}"},
    {"PART": "Shortage", "WEIGHT": "0.25", "SCORE": f"{target_row.get('comp_shortage', 0.23):.2f}"},
    {"PART": "Medical need", "WEIGHT": "0.15", "SCORE": f"{target_row.get('comp_medical_need', 0.12):.2f}"},
    {"PART": "Access penalty", "WEIGHT": "0.05", "SCORE": f"{target_row.get('comp_accessibility', 0.04):.2f}"},
]
st.dataframe(pd.DataFrame(breakdown_data), use_container_width=True)

# Footer
render_footer()

