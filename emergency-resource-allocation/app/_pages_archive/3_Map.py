"""Decision Map Page - Emergency Decision Support System.

Faithfully implements Page 5 of 'Emergency Decision Support - Page Designs.pdf'.
"""

import os
import sys
import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium

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

st.set_page_config(page_title="Decision Map | Emergency DSS", page_icon="🗺️", layout="wide")
apply_theme_and_sidebar()



if "pipeline_result" not in st.session_state:
    st.session_state["pipeline_result"] = run_full_pipeline()

res = st.session_state["pipeline_result"]
alloc_df = res["allocation_df"].sort_values(by="priority_score", ascending=False).reset_index(drop=True)

# Header
st.markdown("<h1 style='margin: 0; color: #F8FAFC;'>Decision Map</h1>", unsafe_allow_html=True)
st.markdown("<p style='color: #94A3B8; font-size: 14.5px; margin: 2px 0 18px 0;'>Click an area to see its risk, shortage and recommended action. <span style='background:#0F172A;border:1px solid #334155;color:#94A3B8;padding:2px 6px;border-radius:4px;font-size:10px;font-weight:700;'>SAMPLE DATA</span></p>", unsafe_allow_html=True)

col_map, col_inspector = st.columns([3, 2])

color_map = {"CRITICAL": "#EF4444", "HIGH": "#F59E0B", "MEDIUM": "#EAB308", "LOW": "#10B981"}

with col_map:
    st.markdown("##### RISK MAP <small style='color:#94A3B8;'>(real map uses coordinates from your data)</small>", unsafe_allow_html=True)
    try:
        center_lat = float(alloc_df["latitude"].mean())
        center_lon = float(alloc_df["longitude"].mean())
        m = folium.Map(location=[center_lat, center_lon], zoom_start=11, tiles="CartoDB dark_matter")

        for _, r in alloc_df.iterrows():
            c = color_map.get(r["priority_level"], "#EAB308")
            folium.CircleMarker(
                location=[r["latitude"], r["longitude"]],
                radius=14, color=c, fill=True, fill_color=c, fill_opacity=0.85,
                tooltip=f"{r['area_name']}: {r['priority_level']} | Pop: {int(r['population']):,}"
            ).add_to(m)

        # Depots
        wh_df = pd.read_csv("data/warehouses.csv") if os.path.exists("data/warehouses.csv") else pd.DataFrame()
        for _, wh in wh_df.iterrows():
            folium.Marker(location=[wh["latitude"], wh["longitude"]], icon=folium.Icon(color="blue", icon="home", prefix="fa"), tooltip=f"Depot: {wh['warehouse_name']}").add_to(m)

        st_folium(m, width=640, height=440)
    except Exception as e:
        st.error(f"Map error: {e}")

with col_inspector:
    st.markdown("##### AREA INSPECTOR")
    picked_name = st.selectbox("Select Area to Inspect", alloc_df["area_name"].tolist(), index=0)
    target = alloc_df[alloc_df["area_name"] == picked_name].iloc[0]

    tier = target["priority_level"]
    badge_span = f"<span class='badge-{tier.lower()}'>{tier}</span>"

    aff_now = int(target["population"] * 0.7)
    aff_pred = int(target["estimated_affected"] * 1.4)
    w_dem = target.get("demand_Water", 0)
    w_sent = target.get("opt_alloc_Water", 0)
    m_sent = target.get("opt_alloc_Medical_Kit", 0)

    st.markdown(f"""
    <div class="area-inspector-card">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
            <strong style="font-size:18px; color:#F8FAFC;">{target['area_name']}</strong>
            {badge_span}
        </div>
        <div style="font-size:13px; color:#CBD5E1; line-height:1.7;">
            <div><strong>Affected now:</strong> {aff_now:,}</div>
            <div><strong>Predicted:</strong> {aff_pred:,}</div>
            <div><strong>Water needed:</strong> {w_dem:,.0f} L</div>
            <div><strong>Water sent:</strong> {w_sent:,.0f} L</div>
            <div><strong>Medical sent:</strong> {m_sent:,.0f} kits</div>
            <div><strong>Priority score:</strong> {target['priority_score']:.2f}</div>
        </div>
        <div style="margin-top:10px; font-size:12px; color:#94A3B8;">
            <strong>Top reasons:</strong> rising population, water shortage, high building damage.
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)
    c_btn1, c_btn2, c_btn3 = st.columns(3)
    if c_btn1.button("WHY?", use_container_width=True):
        st.info(f"Why {target['area_name']}: Primary driver is structural building collapses ({target['destroyed_buildings']} destroyed) and acute population concentration.")
    if c_btn2.button("SIMULATE", use_container_width=True):
        st.info("Navigate to What-If Simulator to test supply shocks for this area.")
    if c_btn3.button("APPLY", type="primary", use_container_width=True):
        st.success(f"Dispatched {w_sent:,.0f} L water and {m_sent:,.0f} medical kits to {target['area_name']}.")

# Footer
render_footer()

