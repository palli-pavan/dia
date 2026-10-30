"""AI Decision Audit Page - Emergency Decision Support System.

Faithfully implements Page 9 of 'Emergency Decision Support - Page Designs.pdf'.
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

from core.audit import get_audit_history

try:
    from app.nav import apply_theme_and_sidebar, render_footer
except ModuleNotFoundError:
    from nav import apply_theme_and_sidebar, render_footer

st.set_page_config(page_title="AI Decision Audit | Emergency DSS", page_icon="📋", layout="wide")
apply_theme_and_sidebar()



df_audit = get_audit_history(limit=50)

# Header
st.markdown("<h1 style='margin: 0; color: #F8FAFC;'>AI Decision Audit</h1>", unsafe_allow_html=True)
st.markdown("<p style='color: #94A3B8; font-size: 14.5px; margin: 2px 0 18px 0;'>Every analysis is recorded so decisions can be reviewed. <span style='background:#0F172A;border:1px solid #334155;color:#94A3B8;padding:2px 6px;border-radius:4px;font-size:10px;font-weight:700;'>SAMPLE DATA</span></p>", unsafe_allow_html=True)

st.markdown("##### DECISION LOG <small style='color:#94A3B8;'>(sample entries)</small> <span style='background:#1E3A8A;color:#93C5FD;padding:2px 6px;border-radius:4px;font-size:10px;font-weight:700;'>AUDIT</span>", unsafe_allow_html=True)

# Format entries matching PDF
log_rows = []
if not df_audit.empty:
    for _, r in df_audit.iterrows():
        t_str = str(r.get("timestamp", ""))[:16].replace("T", " ")
        scen = str(r.get("scenario_name", "Flood, High, base supply"))
        mod = str(r.get("model_name", "XGBoost"))
        solv = str(r.get("solver_status", "optimal")).lower()
        log_rows.append({
            "TIME": t_str,
            "SCENARIO": scen,
            "MODEL": mod,
            "TOP FEATURES": "Predicted pop., water shortage",
            "SOLVER": solv,
            "DETAILS": "OPEN"
        })
else:
    log_rows = [
        {"TIME": "2026-10-08 10:12", "SCENARIO": "Flood, High, base supply", "MODEL": "XGBoost", "TOP FEATURES": "Predicted pop., water shortage", "SOLVER": "optimal", "DETAILS": "OPEN"},
        {"TIME": "2026-10-08 10:20", "SCENARIO": "Water -30%", "MODEL": "XGBoost", "TOP FEATURES": "Water shortage, severity", "SOLVER": "optimal", "DETAILS": "OPEN"},
        {"TIME": "2026-10-08 10:31", "SCENARIO": "Population +20%", "MODEL": "XGBoost", "TOP FEATURES": "Predicted pop., medical demand", "SOLVER": "optimal", "DETAILS": "OPEN"},
    ]

st.dataframe(pd.DataFrame(log_rows), use_container_width=True, height=220)

col_dl, col_space = st.columns([1, 4])
with col_dl:
    csv_bytes = pd.DataFrame(log_rows).to_csv(index=False).encode("utf-8")
    st.download_button("DOWNLOAD CSV", data=csv_bytes, file_name="Decision_Audit_Log.csv", mime="text/csv", type="primary", use_container_width=True)

st.markdown("<div style='margin-top: 25px;'></div>", unsafe_allow_html=True)

st.markdown("##### EACH ENTRY RECORDS")
st.markdown("""
<div style="background:#1E293B; border:1px solid #334155; border-radius:8px; padding:16px; font-size:13.5px; color:#CBD5E1; line-height:1.6;">
    Scenario inputs, model used, predictions, priority scores, allocation, main influencing features, objective, solver status and timestamp.
</div>
""", unsafe_allow_html=True)

# Footer
render_footer()

