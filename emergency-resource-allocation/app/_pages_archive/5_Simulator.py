"""What-If Simulator Page - Emergency Decision Support System.

Faithfully implements Page 7 of 'Emergency Decision Support - Page Designs.pdf'.
"""

import os
import sys
import streamlit as st
import pandas as pd

_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_app = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in [_root, _app]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from core.simulate import run_full_pipeline, compare_two_scenarios

try:
    from app.nav import apply_theme_and_sidebar, render_footer
except ModuleNotFoundError:
    from nav import apply_theme_and_sidebar, render_footer

st.set_page_config(page_title="What-If Simulator | Emergency DSS", page_icon="🧪", layout="wide")
apply_theme_and_sidebar()



if "pipeline_result" not in st.session_state:
    st.session_state["pipeline_result"] = run_full_pipeline()

res_current = st.session_state["pipeline_result"]

# Header
st.markdown("<h1 style='margin: 0; color: #F8FAFC;'>What-If Simulator</h1>", unsafe_allow_html=True)
st.markdown("<p style='color: #94A3B8; font-size: 14.5px; margin: 2px 0 18px 0;'>Change conditions, rerun the pipeline, and compare plans. <span style='background:#0F172A;border:1px solid #334155;color:#94A3B8;padding:2px 6px;border-radius:4px;font-size:10px;font-weight:700;'>SAMPLE DATA</span></p>", unsafe_allow_html=True)

col_ctrl, col_after = st.columns([1, 1])

with col_ctrl:
    st.markdown("##### CHANGE THE SCENARIO <span style='background:#581C87;color:#D8B4FE;padding:2px 6px;border-radius:4px;font-size:10px;font-weight:700;'>SIMULATION</span>", unsafe_allow_html=True)
    w_shock = st.slider("Water supply shift (%)", -80, 50, -30, step=5)
    f_shock = st.slider("Food supply shift (%)", -80, 50, 0, step=5)
    m_shock = st.slider("Medical supply shift (%)", -80, 50, 0, step=5)
    pop_shock = st.slider("Affected population shift (%)", -50, 100, 0, step=5)

    btn_sim = st.button("SIMULATE", type="primary", use_container_width=True)

if btn_sim or "sim_result" not in st.session_state:
    res_after = run_full_pipeline(
        resource_supply_deltas={"Water": float(w_shock), "Food": float(f_shock), "Medical_Kit": float(m_shock)},
        population_delta_pct=float(pop_shock)
    )
    st.session_state["sim_result"] = res_after

res_after = st.session_state["sim_result"]

with col_after:
    st.markdown(f"##### BEFORE VS AFTER: WATER {w_shock:+d}% <span style='background:#581C87;color:#D8B4FE;padding:2px 6px;border-radius:4px;font-size:10px;font-weight:700;'>SIMULATION</span>", unsafe_allow_html=True)

    w_cov_curr = res_current["coverages"].get("Water", 0.56) * 100
    w_cov_after = res_after["coverages"].get("Water", 0.39) * 100

    w_short_curr = res_current["allocation_df"]["opt_shortage_Water"].sum()
    w_short_after = res_after["allocation_df"]["opt_shortage_Water"].sum()

    tot_short_curr = res_current["kpis"]["total_shortage_units"]
    tot_short_after = res_after["kpis"]["total_shortage_units"]

    crit_short_curr = res_current["allocation_df"][res_current["allocation_df"]["priority_level"].isin(["CRITICAL", "HIGH"])]["opt_shortage_Water"].sum()
    crit_short_after = res_after["allocation_df"][res_after["allocation_df"]["priority_level"].isin(["CRITICAL", "HIGH"])]["opt_shortage_Water"].sum()

    area_e_curr = res_current["allocation_df"].iloc[0]["opt_alloc_Water"]
    area_e_after = res_after["allocation_df"].iloc[0]["opt_alloc_Water"]

    meas_table = [
        {"MEASURE": "Water coverage", "CURRENT": f"{w_cov_curr:.0f}%", "AFTER CHANGE": f"{w_cov_after:.0f}%", "DIFF": f"{w_cov_after - w_cov_curr:+.0f} pts"},
        {"MEASURE": "Water shortage", "CURRENT": f"{w_short_curr:,.0f}", "AFTER CHANGE": f"{w_short_after:,.0f}", "DIFF": f"{w_short_after - w_short_curr:+,.0f}"},
        {"MEASURE": "Total shortage", "CURRENT": f"{tot_short_curr:,.0f}", "AFTER CHANGE": f"{tot_short_after:,.0f}", "DIFF": f"{tot_short_after - tot_short_curr:+,.0f}"},
        {"MEASURE": "Unmet need, critical + high", "CURRENT": f"{crit_short_curr:,.0f}", "AFTER CHANGE": f"{crit_short_after:,.0f}", "DIFF": f"{crit_short_after - crit_short_curr:+,.0f}"},
        {"MEASURE": f"Water sent to {res_current['allocation_df'].iloc[0]['area_name']}", "CURRENT": f"{area_e_curr:,.0f}", "AFTER CHANGE": f"{area_e_after:,.0f}", "DIFF": f"{area_e_after - area_e_curr:+,.0f}"},
    ]
    st.dataframe(pd.DataFrame(meas_table), use_container_width=True, height=210)
    st.caption("Calculated by rerunning the same optimizer on the changed supply.")

st.markdown("<div style='margin-top: 25px;'></div>", unsafe_allow_html=True)

# Scenario A vs B Table
st.markdown("##### SCENARIO A VS SCENARIO B")
scenario_ab = [
    {"MEASURE": "Water available", "A: CURRENT": "40,000", "B: WATER -30%": "28,000", "DIFFERENCE": "-12,000"},
    {"MEASURE": "Water coverage", "A: CURRENT": f"{w_cov_curr:.0f}%", "B: WATER -30%": f"{w_cov_after:.0f}%", "DIFFERENCE": f"{w_cov_after - w_cov_curr:+.0f} pts"},
    {"MEASURE": "Total shortage", "A: CURRENT": f"{tot_short_curr:,.0f}", "B: WATER -30%": f"{tot_short_after:,.0f}", "DIFFERENCE": f"{tot_short_after - tot_short_curr:+,.0f}"},
]
st.dataframe(pd.DataFrame(scenario_ab), use_container_width=True)

# Footer
render_footer()

