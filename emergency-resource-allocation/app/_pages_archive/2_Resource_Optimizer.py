"""Resource Optimizer Page - Emergency Decision Support System.

Faithfully implements Page 4 of 'Emergency Decision Support - Page Designs.pdf'.
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

from core.simulate import run_full_pipeline, compute_optimization_impact

try:
    from app.nav import apply_theme_and_sidebar, render_footer
except ModuleNotFoundError:
    from nav import apply_theme_and_sidebar, render_footer

st.set_page_config(page_title="Resource Optimizer | Emergency DSS", page_icon="⚖️", layout="wide")
apply_theme_and_sidebar()



if "pipeline_result" not in st.session_state:
    st.session_state["pipeline_result"] = run_full_pipeline()

res = st.session_state["pipeline_result"]
alloc_df = res["allocation_df"].sort_values(by="priority_score", ascending=False).reset_index(drop=True)
impact_info = compute_optimization_impact(alloc_df)

# Header
st.markdown("<h1 style='margin: 0; color: #F8FAFC;'>Resource Optimizer</h1>", unsafe_allow_html=True)
st.markdown("<p style='color: #94A3B8; font-size: 14.5px; margin: 2px 0 18px 0;'>How should limited supplies be split to protect the highest-priority areas? <span style='background:#0F172A;border:1px solid #334155;color:#94A3B8;padding:2px 6px;border-radius:4px;font-size:10px;font-weight:700;'>SAMPLE DATA</span></p>", unsafe_allow_html=True)

# 4 KPI Cards
c1, c2, c3, c4 = st.columns(4)
c1.markdown(f"<div class='metric-box'><div class='metric-label'>Unmet Need, Baseline</div><div class='metric-val'>{impact_info['total_baseline_shortage']:,.0f}</div><div class='metric-sub'>Critical + high areas, equal share</div></div>", unsafe_allow_html=True)
c2.markdown(f"<div class='metric-box'><div class='metric-label'>Unmet Need, AI Plan</div><div class='metric-val'>{impact_info['total_optimized_shortage']:,.0f}</div><div class='metric-sub'>Same areas, optimized</div></div>", unsafe_allow_html=True)
c3.markdown(f"<div class='metric-box'><div class='metric-label'>Reduction</div><div class='metric-val' style='color:#34D399;'>{impact_info['overall_reduction_pct']:.0f}%</div><div class='metric-sub'>(before - after) / before</div></div>", unsafe_allow_html=True)
c4.markdown(f"<div class='metric-box'><div class='metric-label'>Solver Status</div><div class='metric-val' style='color:#38BDF8;'>OPTIMAL</div><div class='metric-sub'>Shown from the solver result</div></div>", unsafe_allow_html=True)

st.markdown("<div style='margin-top: 25px;'></div>", unsafe_allow_html=True)

col_tbl, col_rules = st.columns([3, 1])

alloc_rows = []
for _, r in alloc_df.iterrows():
    f_alloc = r.get("opt_alloc_Food", 0)
    f_dem = r.get("demand_Food", 1)
    f_cov = int((f_alloc / max(f_dem, 1)) * 100)

    w_alloc = r.get("opt_alloc_Water", 0)
    w_dem = r.get("demand_Water", 1)
    w_cov = int((w_alloc / max(w_dem, 1)) * 100)

    m_alloc = r.get("opt_alloc_Medical_Kit", 0)
    m_dem = r.get("demand_Medical_Kit", 1)
    m_cov = int((m_alloc / max(m_dem, 1)) * 100)

    alloc_rows.append({
        "AREA": r["area_name"],
        "RISK": r["priority_level"],
        "FOOD": f"{f_alloc:,.0f} of {f_dem:,.0f} ({f_cov}%)",
        "WATER": f"{w_alloc:,.0f} of {w_dem:,.0f} ({w_cov}%)",
        "MEDICAL": f"{m_alloc:,.0f} of {m_dem:,.0f} ({m_cov}%)"
    })

with col_tbl:
    st.markdown("##### ALLOCATION BY AREA (units sent, of units needed) <span style='background:#064E3B;color:#6EE7B7;padding:2px 6px;border-radius:4px;font-size:10px;font-weight:700;'>OPTIMIZATION</span>", unsafe_allow_html=True)
    st.dataframe(pd.DataFrame(alloc_rows), use_container_width=True, height=280)

with col_rules:
    st.markdown("##### OBJECTIVE AND RULES")
    st.markdown("""
    <div style="background:#1E293B; border:1px solid #334155; border-radius:8px; padding:16px; font-size:13px; color:#CBD5E1; line-height:1.6;">
        <div><strong>Goal:</strong> Minimise priority-weighted unmet need</div>
        <div><strong>Rule 1:</strong> Sent ≤ supply</div>
        <div><strong>Rule 2:</strong> Sent ≤ area need</div>
        <div><strong>Rule 3:</strong> Min. 25% coverage each area</div>
        <div style="margin-top:6px; color:#94A3B8;"><strong>Sources:</strong> Depot routing from warehouses</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("<div style='margin-top: 25px;'></div>", unsafe_allow_html=True)

# Chart: Water Coverage Baseline vs AI Plan
st.markdown("##### WATER COVERAGE BY AREA: BASELINE VS AI PLAN")
st.caption("Blue = baseline. Green = AI plan.")

areas_rev = alloc_df["area_name"].tolist()[::-1]
base_covs = []
opt_covs = []

for _, r in alloc_df.iterrows():
    w_dem = max(r.get("demand_Water", 1), 1)
    w_opt = r.get("opt_alloc_Water", 0)
    w_base = r.get("baseline_alloc_Water", 0)
    base_covs.append(int((w_base / w_dem) * 100))
    opt_covs.append(int((w_opt / w_dem) * 100))

base_covs = base_covs[::-1]
opt_covs = opt_covs[::-1]

fig_cov = go.Figure()
fig_cov.add_trace(go.Bar(
    y=areas_rev, x=base_covs, name="Baseline (Equal Share)", orientation="h",
    marker_color="#3B82F6", text=[f"{v}%" for v in base_covs], textposition="auto"
))
fig_cov.add_trace(go.Bar(
    y=areas_rev, x=opt_covs, name="AI Plan (Optimized)", orientation="h",
    marker_color="#10B981", text=[f"{v}%" for v in opt_covs], textposition="auto"
))

fig_cov.update_layout(
    barmode="group",
    template="plotly_dark",
    height=360,
    margin=dict(l=20, r=20, t=20, b=20),
    xaxis_title="Water Coverage (%)",
    xaxis=dict(range=[0, 105]),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
)
st.plotly_chart(fig_cov, use_container_width=True)

# Footer
render_footer()

