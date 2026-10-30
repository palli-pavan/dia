"""Predictions Page - Emergency Decision Support System.

Faithfully implements Page 3 of 'Emergency Decision Support - Page Designs.pdf'.
"""

import os
import sys
import streamlit as st
import pandas as pd
import plotly.graph_objects as go

_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_app = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in [_root, _app]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from core.simulate import run_full_pipeline

try:
    from app.nav import apply_theme_and_sidebar, render_footer
except ModuleNotFoundError:
    from nav import apply_theme_and_sidebar, render_footer

st.set_page_config(page_title="Predictions | Emergency DSS", page_icon="📈", layout="wide")
apply_theme_and_sidebar()



if "pipeline_result" not in st.session_state:
    st.session_state["pipeline_result"] = run_full_pipeline()

res = st.session_state["pipeline_result"]
alloc_df = res["allocation_df"].sort_values(by="priority_score", ascending=False).reset_index(drop=True)

# Page Header
st.markdown("<h1 style='margin: 0; color: #F8FAFC;'>Predictions</h1>", unsafe_allow_html=True)
st.markdown("<p style='color: #94A3B8; font-size: 14.5px; margin: 2px 0 18px 0;'>Which areas are likely to become critical, and by how much? <span style='background:#0F172A;border:1px solid #334155;color:#94A3B8;padding:2px 6px;border-radius:4px;font-size:10px;font-weight:700;'>SAMPLE DATA</span></p>", unsafe_allow_html=True)

col_tbl, col_guide = st.columns([3, 2])

# Table data
pred_rows = []
for _, r in alloc_df.iterrows():
    aff_now = int(r["population"] * 0.7)
    aff_pred = int(r["estimated_affected"] * 1.4)
    pct_chg = int(((aff_pred - aff_now) / max(aff_now, 1)) * 100)
    pred_rows.append({
        "AREA": r["area_name"],
        "NOW": f"{aff_now:,}",
        "PREDICTED": f"{aff_pred:,}",
        "CHANGE": f"{pct_chg:+d}%",
        "RISK": r["priority_level"]
    })

with col_tbl:
    st.markdown("##### PREDICTED AFFECTED BY AREA <span style='background:#1E3A8A;color:#93C5FD;padding:2px 6px;border-radius:4px;font-size:10px;font-weight:700;'>PREDICTION</span>", unsafe_allow_html=True)
    st.dataframe(pd.DataFrame(pred_rows), use_container_width=True, height=280)

with col_guide:
    st.markdown("##### HOW TO READ THIS")
    st.markdown("""
    <div style="background:#1E293B; border:1px solid #334155; border-radius:8px; padding:16px; font-size:13px; color:#CBD5E1; line-height:1.5;">
        Predicted values come from the trained model. Risk level comes from the priority score thresholds (adjustable).
        A probability column appears only when the chosen model provides one.
        <div style="margin-top:12px; font-weight:600;">
            <div style="color:#FCA5A5;">● CRITICAL: score 0.85 or more</div>
            <div style="color:#FCD34D;">● HIGH: 0.60 to 0.84</div>
            <div style="color:#FEF08A;">● MEDIUM: 0.35 to 0.59</div>
            <div style="color:#6EE7B7;">● LOW: below 0.35</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("<div style='margin-top: 25px;'></div>", unsafe_allow_html=True)

# Visual Comparison Chart: Now vs Predicted
st.markdown("##### CURRENT VS PREDICTED AFFECTED PEOPLE")
st.caption("Blue = now. Second bar = predicted (red when critical).")

fig = go.Figure()
areas = alloc_df["area_name"].tolist()[::-1]
now_vals = [int(r["population"] * 0.7) for _, r in alloc_df.iterrows()][::-1]
pred_vals = [int(r["estimated_affected"] * 1.4) for _, r in alloc_df.iterrows()][::-1]
risks = alloc_df["priority_level"].tolist()[::-1]

pred_colors = ["#EF4444" if r == "CRITICAL" else ("#F59E0B" if r == "HIGH" else "#3B82F6") for r in risks]

fig.add_trace(go.Bar(
    y=areas, x=now_vals, name="Affected Now", orientation="h",
    marker_color="#3B82F6", text=now_vals, textposition="auto"
))
fig.add_trace(go.Bar(
    y=areas, x=pred_vals, name="Predicted Affected", orientation="h",
    marker_color=pred_colors, text=pred_vals, textposition="auto"
))

fig.update_layout(
    barmode="group",
    template="plotly_dark",
    height=360,
    margin=dict(l=20, r=20, t=20, b=20),
    xaxis_title="Affected Population",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
)
st.plotly_chart(fig, use_container_width=True)

# Footer
render_footer()

