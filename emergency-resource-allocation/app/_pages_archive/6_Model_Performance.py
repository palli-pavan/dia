"""Model Performance Page - Emergency Decision Support System.

Faithfully implements Page 8 of 'Emergency Decision Support - Page Designs.pdf'.
"""

import os
import sys
import json
import streamlit as st
import pandas as pd

_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_app = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in [_root, _app]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    from app.nav import apply_theme_and_sidebar, render_footer
except ModuleNotFoundError:
    from nav import apply_theme_and_sidebar, render_footer

st.set_page_config(page_title="Model Performance | Emergency DSS", page_icon="📊", layout="wide")
apply_theme_and_sidebar()



# Load metrics.json
metrics_path = "models/metrics.json"
if os.path.exists(metrics_path):
    with open(metrics_path, "r", encoding="utf-8") as f:
        metrics_data = json.load(f)
else:
    metrics_data = {
        "models": {
            "Logistic_Regression_Baseline": {"precision_macro": 0.74, "recall_macro": 0.75, "f1_macro": 0.74, "pr_auc_ovr_macro": 0.79},
            "Random_Forest": {"precision_macro": 0.81, "recall_macro": 0.79, "f1_macro": 0.80, "pr_auc_ovr_macro": 0.85},
            "XGBoost": {"precision_macro": 0.84, "recall_macro": 0.81, "f1_macro": 0.83, "pr_auc_ovr_macro": 0.88}
        }
    }

models_dict = metrics_data["models"]
xgb_metrics = models_dict.get("XGBoost", list(models_dict.values())[-1])

# Header
st.markdown("<h1 style='margin: 0; color: #F8FAFC;'>Model Performance</h1>", unsafe_allow_html=True)
st.markdown("<p style='color: #94A3B8; font-size: 14.5px; margin: 2px 0 18px 0;'>Is the model reliable? Evidence from held-out test data (sample numbers). <span style='background:#0F172A;border:1px solid #334155;color:#94A3B8;padding:2px 6px;border-radius:4px;font-size:10px;font-weight:700;'>SAMPLE DATA</span></p>", unsafe_allow_html=True)

# 4 Metric Tiles
c1, c2, c3, c4 = st.columns(4)
c1.markdown(f"<div class='metric-tile'><div class='metric-tile-label'>Precision</div><div class='metric-tile-val'>{xgb_metrics.get('precision_macro', 0.84):.2f}</div><div class='metric-tile-sub'>Flagged areas that were truly high-risk</div></div>", unsafe_allow_html=True)
c2.markdown(f"<div class='metric-tile'><div class='metric-tile-label'>Recall</div><div class='metric-tile-val'>{xgb_metrics.get('recall_macro', 0.81):.2f}</div><div class='metric-tile-sub'>High-risk areas the model caught</div></div>", unsafe_allow_html=True)
c3.markdown(f"<div class='metric-tile'><div class='metric-tile-label'>F1</div><div class='metric-tile-val'>{xgb_metrics.get('f1_macro', 0.83):.2f}</div><div class='metric-tile-sub'>Balance of precision and recall</div></div>", unsafe_allow_html=True)
c4.markdown(f"<div class='metric-tile'><div class='metric-tile-label'>PR-AUC</div><div class='metric-tile-val'>{xgb_metrics.get('pr_auc_ovr_macro', 0.88):.2f}</div><div class='metric-tile-sub'>Preferred when classes are imbalanced</div></div>", unsafe_allow_html=True)

st.markdown("<div style='margin-top: 25px;'></div>", unsafe_allow_html=True)

col_comp, col_cm_box = st.columns([3, 2])

with col_comp:
    st.markdown("##### MODEL COMPARISON <small style='color:#94A3B8;'>(best chosen by F1)</small>", unsafe_allow_html=True)
    comp_rows = [
        {"MODEL": "Logistic Regression", "F1": f"{models_dict.get('Logistic_Regression_Baseline', {}).get('f1_macro', 0.74):.2f}", "PR-AUC": f"{models_dict.get('Logistic_Regression_Baseline', {}).get('pr_auc_ovr_macro', 0.79):.2f}", "RESULT": ""},
        {"MODEL": "Random Forest", "F1": f"{models_dict.get('Random_Forest', {}).get('f1_macro', 0.80):.2f}", "PR-AUC": f"{models_dict.get('Random_Forest', {}).get('pr_auc_ovr_macro', 0.85):.2f}", "RESULT": ""},
        {"MODEL": "XGBoost", "F1": f"{xgb_metrics.get('f1_macro', 0.83):.2f}", "PR-AUC": f"{xgb_metrics.get('pr_auc_ovr_macro', 0.88):.2f}", "RESULT": "BEST"},
    ]
    st.dataframe(pd.DataFrame(comp_rows), use_container_width=True, height=140)

with col_cm_box:
    st.markdown("##### CONFUSION MATRIX")
    cm_df = pd.DataFrame([
        {"": "Actual high", "Pred. high": "38", "Pred. low": "9"},
        {"": "Actual low", "Pred. high": "7", "Pred. low": "86"}
    ]).set_index("")
    st.dataframe(cm_df, use_container_width=True, height=140)

st.markdown("<div style='margin-top: 20px;'></div>", unsafe_allow_html=True)

# Training Setup
st.markdown("##### TRAINING SETUP <small style='color:#94A3B8;'>(sample)</small>", unsafe_allow_html=True)
st.markdown("""
<div style="background:#1E293B; border:1px solid #334155; border-radius:8px; padding:16px; font-size:13px; color:#CBD5E1; line-height:1.7;">
    <div><strong>Split:</strong> Stratified, 80/20</div>
    <div><strong>Validation:</strong> 5-fold cross-validation</div>
    <div><strong>Random seed:</strong> 42 (fixed)</div>
    <div style="color:#94A3B8; margin-top:4px;"><strong>Note:</strong> Accuracy alone is not used because emergency disaster datasets have class imbalance.</div>
</div>
""", unsafe_allow_html=True)

# Footer
render_footer()

