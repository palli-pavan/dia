"""Unified UI Styling and Sidebar for Single-Page Emergency Decision Support.
"""

import streamlit as st

GLOBAL_CSS = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
    }

    /* Hide default Streamlit multi-page sidebar list */
    [data-testid="stSidebarNav"] {
        display: none !important;
    }

    /* Sidebar Brand */
    .brand-container {
        padding: 4px 0 16px 0;
        border-bottom: 1px solid #1E293B;
        margin-bottom: 16px;
    }
    .brand-title {
        font-size: 19px;
        font-weight: 800;
        letter-spacing: -0.5px;
        color: #F8FAFC;
        margin: 0;
        line-height: 1.2;
    }
    .brand-subtitle {
        font-size: 12px;
        color: #94A3B8;
        font-weight: 500;
        margin-top: 3px;
    }

    /* Sidebar Category Section Titles */
    .nav-category {
        font-size: 11px;
        font-weight: 700;
        color: #64748B;
        text-transform: uppercase;
        letter-spacing: 1.3px;
        margin: 16px 0 8px 2px;
    }

    /* Badges */
    .badge-critical { background: #7F1D1D; color: #FCA5A5; padding: 2px 8px; border-radius: 4px; font-weight: 700; font-size: 11px; }
    .badge-high { background: #78350F; color: #FCD34D; padding: 2px 8px; border-radius: 4px; font-weight: 700; font-size: 11px; }
    .badge-medium { background: #713F12; color: #FEF08A; padding: 2px 8px; border-radius: 4px; font-weight: 700; font-size: 11px; }
    .badge-low { background: #064E3B; color: #6EE7B7; padding: 2px 8px; border-radius: 4px; font-weight: 700; font-size: 11px; }

    /* Footer */
    .disclaimer-footer {
        text-align: center;
        color: #64748B;
        font-size: 11.5px;
        line-height: 1.5;
        border-top: 1px solid #334155;
        padding-top: 22px;
        margin-top: 40px;
    }
</style>
"""

DISCLAIMER_TEXT = (
    "Decision-support tool; final decisions rest with emergency managers. "
    "Sample numbers are illustrative and are replaced by your data and model output."
)


def apply_theme_and_sidebar():
    """Injects styles and renders the clean Mission Control sidebar."""
    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)
    
    with st.sidebar:
        st.markdown("""
        <div class="brand-container">
            <div class="brand-title">EMERGENCY DSS</div>
            <div class="brand-subtitle">AI-assisted resource allocation</div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown('<div class="nav-category">MISSION WORKFLOW</div>', unsafe_allow_html=True)
        
        # Display the 4 steps clearly in the sidebar
        steps_map = {
            "1 Describe": "1️⃣ Describe Disaster",
            "2 AI analysis": "2️⃣ AI Risk Analysis",
            "3 Response plan": "3️⃣ Tactical Response Plan",
            "4 What-if": "4️⃣ What-If & Audit"
        }

        active = st.session_state.get("active_step", "1 Describe")
        for step_key, step_label in steps_map.items():
            is_active = (active == step_key)
            btn_type = "primary" if is_active else "secondary"
            if st.button(step_label, key=f"side_{step_key}", type=btn_type, use_container_width=True):
                st.session_state["active_step"] = step_key
                st.rerun()

        st.markdown('<div style="margin-top: 20px; border-top: 1px solid #1E293B;"></div>', unsafe_allow_html=True)
        st.markdown('<div class="nav-category">MISSION SUMMARY</div>', unsafe_allow_html=True)
        
        d_type = st.session_state.get("disaster_type", "Wildfire")
        d_sev = st.session_state.get("severity_level", "High")
        d_dur = st.session_state.get("duration_hours", 72)
        d_conv = len(st.session_state.get("dispatched_convoys", set()))

        st.markdown(f"""
        <div style="background:#0F172A; border:1px solid #1E293B; border-radius:8px; padding:12px; font-size:12.5px; color:#CBD5E1; line-height:1.7;">
            <div><strong>Disaster:</strong> {d_type} ({d_sev})</div>
            <div><strong>Duration:</strong> {d_dur} hours</div>
            <div><strong>Convoys Active:</strong> {d_conv} dispatched</div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown('<div style="margin-top: 15px;"></div>', unsafe_allow_html=True)
        if st.button("🔄 Reset to Default Scenario", use_container_width=True):
            st.session_state["active_step"] = "1 Describe"
            st.session_state["disaster_type"] = "Wildfire"
            st.session_state["severity_level"] = "High"
            st.session_state["duration_hours"] = 72
            st.session_state["food_supply"] = 40000
            st.session_state["water_supply"] = 40000
            st.session_state["med_supply"] = 2500
            st.session_state["dispatched_convoys"] = set()
            st.session_state.pop("pipeline_result", None)
            st.rerun()


def render_footer():
    """Renders the standard mandatory footer."""
    st.markdown(f"""
    <div class="disclaimer-footer">
        <strong>{DISCLAIMER_TEXT}</strong>
    </div>
    """, unsafe_allow_html=True)
