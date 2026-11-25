"""Visa tracking website.

    .venv\\Scripts\\streamlit run website.py

Other office PCs open http://<this PC's name>:8501 . Tracking windows (CAPTCHAs)
always open on the PC running the website.
"""
import hmac

import streamlit as st

st.set_page_config(page_title="Visa tracking", page_icon=":material/travel_explore:",
                   layout="wide")


def signed_in() -> bool:
    """Office password from .streamlit/secrets.toml (shared by the staff)."""
    if st.session_state.get("signed_in"):
        return True
    expected = st.secrets.get("site_password", "")
    if not expected:
        st.error("Set site_password in .streamlit/secrets.toml first.", title="Website not set up")
        return False
    with st.form("sign_in", width=360):
        st.subheader("Visa tracking")
        typed = st.text_input("Office password", type="password")
        if st.form_submit_button("Sign in", type="primary", width="stretch"):
            if hmac.compare_digest(typed.encode(), expected.encode()):
                st.session_state.signed_in = True
                st.rerun()
            st.error("Wrong password.")
    return False


if not signed_in():
    st.stop()

page = st.navigation(
    [
        st.Page("app_pages/home.py", title="Home", icon=":material/home:", default=True),
        st.Page("app_pages/tracking.py", title="Tracking", icon=":material/travel_explore:",
                help="Check clients' application statuses and get the screenshots PDF."),
        st.Page("app_pages/data_entry.py", title="Data entry", icon=":material/edit_note:",
                help="Add, edit or remove clients for each tracking site."),
    ],
    position="top",
)
page.run()
