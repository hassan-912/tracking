import streamlit as st

from tracker import clients_db

st.title("Visa tracking")
st.caption("Choose what you want to do.")

with st.container(horizontal=True, gap="large"):
    with st.container(border=True, width=360):
        st.subheader(":material/travel_explore: Tracking")
        st.write("Check application statuses and get the screenshots PDF.")
        if st.button("Open tracking", type="primary", width="stretch", key="go_tracking"):
            st.switch_page("app_pages/tracking.py")
    with st.container(border=True, width=360):
        st.subheader(":material/edit_note: Data entry")
        st.write("Add, edit or remove clients for each site.")
        if st.button("Open data entry", width="stretch", key="go_data"):
            st.switch_page("app_pages/data_entry.py")

st.space("medium")
st.caption("Clients in the website")
with st.container(horizontal=True):
    for cat in clients_db.CATEGORIES.values():
        st.metric(cat.title, clients_db.count(cat.key), border=True, width=150)
