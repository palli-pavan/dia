"""Streamlit interface using the same validated services as the React dashboard."""
import pandas as pd
import streamlit as st
import server
from core.planning import DEFAULT_POPULATIONS


def main():
    st.set_page_config(page_title="ReliefPlan AI", page_icon="📦", layout="wide")
    st.title("ReliefPlan AI")
    st.caption("Synthetic disaster study data · Local decision support · Human review required")
    with st.sidebar.form("scenario"):
        st.subheader("Scenario")
        disaster = st.selectbox("Disaster type", ["Wildfire", "Flood", "Earthquake", "Cyclone"])
        severity = st.selectbox("Planning severity", ["Low", "Moderate", "High", "Extreme"], index=2)
        duration = st.number_input("Duration in hours", min_value=1, max_value=720, value=72)
        food = st.number_input("Food in rations", min_value=0.0, value=40000.0)
        water = st.number_input("Water in litres", min_value=0.0, value=40000.0)
        medical = st.number_input("Medical kits", min_value=0.0, value=2500.0)
        floor = st.slider("Requested minimum service percent", 0, 50, 25, step=5)
        pops = {name: st.number_input(name, min_value=0, max_value=10000000, value=value) for name, value in DEFAULT_POPULATIONS.items()}
        submitted = st.form_submit_button("Run AI analysis", type="primary")
    try:
        if submitted:
            with st.spinner("Predicting damage and optimizing resources"):
                req = server.AnalyzeRequest(disaster_type=disaster, severity=severity, duration_hours=duration,
                    food_supply=food, water_supply=water, med_supply=medical, area_populations=pops, minimum_service_fraction=floor / 100)
                st.session_state["review_plan"] = server.analyze_disaster(req)
        if st.sidebar.button("Restore latest saved plan"):
            st.session_state["review_plan"] = server.latest_plan()
        result = st.session_state.get("review_plan")
        if not result:
            st.info("Choose inputs and run AI analysis, or restore the latest saved plan.")
            return
        result = server.get_plan(result["plan_id"])
        overview, response, simulation, audit = st.tabs(["Analysis", "Response plan", "What-if", "Audit"])
        resources = pd.DataFrame.from_dict(result["resources"], orient="index")
        with overview:
            cols = st.columns(4)
            cols[0].metric("Estimated residents needing aid", f"{result['overview']['total_affected']:,}")
            cols[1].metric("Resident population", f"{result['overview']['total_population']:,}")
            cols[2].metric("Water coverage", f"{result['resources']['Water']['coverage_pct']}%")
            cols[3].metric("Allocation status", result["overview"]["solver_status"])
            st.dataframe(resources, width="stretch")
            st.map(pd.DataFrame([{k:a[k] for k in ['latitude','longitude']} for a in result['areas']]))
            area_id = st.selectbox("Area explanation", [a["area_id"] for a in result["areas"]])
            if st.button("Explain prediction"):
                explanation = server.explain_area(result["plan_id"], area_id)
                st.write("Predicted class", explanation["predicted_class"])
                st.dataframe(explanation["contributions"], width="stretch")
                st.caption(explanation["disclaimer"])
            st.subheader("Saved model evaluation")
            st.dataframe(pd.DataFrame.from_dict(server.get_metrics()["models"], orient="index")[["accuracy","f1_macro","cv_5fold_f1_macro_mean"]])
            exported = server.export_plan(result["plan_id"])
            st.download_button("Download plan CSV", exported.body, "reliefplan.csv", "text/csv")
        with response:
            st.caption("The feasible service floor is reduced when supply cannot support the requested minimum. Approvals are local records, not external convoy dispatches.")
            for action in result["actions"]:
                with st.container(border=True):
                    st.subheader(f"{action['area_name']} · {action['resource']}")
                    st.write(f"Allocate {action['quantity']:,.1f} {action['unit']}")
                    st.write(action["reason"])
                    st.write(action["expected_effect"])
                    approved = action["action_id"] in result["approved_actions"]
                    if st.button("Approval saved" if approved else "Approve locally", key=result["plan_id"]+action["action_id"], disabled=approved):
                        server.approve_dispatch(result["plan_id"], server.DispatchRequest(action_id=action["action_id"]))
                        st.rerun()
            if not result["actions"]:
                st.warning("No dispatchable stock. Review shortages and request supplies.")
            for warning in result["warnings"]:
                st.warning(warning["message"])
        with simulation:
            shock = st.slider("Water supply change percent", -100, 100, -30, step=5)
            population = st.slider("Population change percent", -50, 100, 0, step=5)
            if st.button("Run stress test"):
                compare = server.simulate_shock(server.SimulateRequest(plan_id=result["plan_id"], shock_water_pct=shock, shock_pop_pct=population))
                st.dataframe(compare["comparison"], width="stretch")
                st.write("Affected population", compare["affected_before"], "→", compare["affected_after"])
            if st.button("Save local planning bulletin", disabled=result["bulletin_saved"]):
                st.success(server.save_bulletin(result["plan_id"])["message"])
        with audit:
            st.dataframe(server.get_audit_log(), width="stretch")
            st.download_button("Download audit CSV", server.export_audit().body, "audit.csv", "text/csv")
    except Exception as exc:
        st.error(getattr(exc, "detail", str(exc)))


if __name__ == "__main__":
    main()
