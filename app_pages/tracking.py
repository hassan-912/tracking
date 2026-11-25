import socket

import pandas as pd
import streamlit as st

from tracker import clients_db
from tracker.clients_db import CATEGORIES
from tracker.web_job import Tracker, stamp

HOST = socket.gethostname()


@st.cache_resource
def tracker() -> Tracker:
    """One tracker for the whole office (only one run at a time)."""
    return Tracker()


st.title("Tracking")

choice = st.segmented_control(
    "Site", list(CATEGORIES), format_func=lambda k: CATEGORIES[k].title,
    default="wes", required=True, key="track_category")
cat = CATEGORIES[choice]
accounts = clients_db.to_accounts(choice)

if not accounts:
    st.info("No clients yet. Add them in Data entry.", icon=":material/info:")
    st.stop()

# ---------- choose who to check ----------
rows = pd.DataFrame([{"Client": a.name or "—", cat.ref_label: a.username,
                      "Ready?": "✔" if not a.problem else f"✖ {a.problem}"} for a in accounts])
st.caption("Tick clients to check only them, or check everyone.")
picked = st.dataframe(rows, on_select="rerun", selection_mode="multi-row", hide_index=True,
                      key=f"pick_{choice}", alt=f"{cat.title} clients to check")
chosen = [accounts[i].row for i in picked.selection.rows]
ready = sum(1 for a in accounts if not a.problem)

job = tracker().job
with st.container(horizontal=True, vertical_alignment="center"):
    start_all = st.button(f"Check all {ready} clients", type="primary",
                          icon=":material/play_arrow:", disabled=tracker().busy or not ready)
    start_some = st.button(f"Check {len(chosen)} selected", icon=":material/checklist:",
                           disabled=tracker().busy or not chosen)
if start_all or start_some:
    why_not = tracker().start(choice, chosen if start_some else None)
    if why_not:
        st.warning(why_not)
    else:
        st.rerun()

if cat.portal != "wes":
    st.caption(f":material/desktop_windows: CAPTCHA windows open on **{HOST}**, the PC "
               "running this website — someone needs to be at that PC.")


# ---------- live progress (refreshes by itself) ----------
@st.fragment(run_every=2)
def progress() -> None:
    job = tracker().job
    if job.state == "idle":
        return
    st.divider()
    st.subheader(f"{job.title} — {job.state}")

    if job.state == "waiting":
        st.warning(
            f"{job.windows} window(s) are open on **{HOST}**. In each one: type the CAPTCHA "
            "and submit (BLS: Verify → pictures → Submit · Brazil: hCaptcha → SEARCH). "
            "Wait until every window shows its result, then press the button.",
            title="Your turn: CAPTCHAs", icon=":material/touch_app:")
        if st.button("I've finished all the CAPTCHAs", type="primary",
                     icon=":material/done_all:", key="captchas_done"):
            tracker().captchas_done()
            st.rerun(scope="fragment")
    elif job.state == "running":
        st.info("Working… this page updates by itself.", icon=":material/hourglass_top:")
    elif job.state == "failed":
        st.error(job.error, title="Tracking stopped")

    if job.state == "finished":
        done = sum(1 for r in job.report if not r.get("problem"))
        changed = sum(1 for r in job.report if r.get("changed") == "YES")
        st.success(f"{done} checked · {changed} changed since last time · "
                   f"{len(job.report) - done} need a look. Finished at {stamp(job.finished_at)}.",
                   icon=":material/check_circle:")
        table = pd.DataFrame([{
            "Client": r.get("client") or "—",
            "Status": r.get("status", ""),
            "Changed?": r.get("changed", ""),
            "Problem": r.get("problem", ""),
        } for r in job.report])
        st.dataframe(table, hide_index=True, alt=f"{job.title} results")
        with st.container(horizontal=True):
            if job.pdf and job.pdf.exists():
                st.download_button("Screenshots PDF", job.pdf.read_bytes(), file_name=job.pdf.name,
                                   mime="application/pdf", icon=":material/picture_as_pdf:",
                                   type="primary")
            if job.results_file and job.results_file.exists():
                st.download_button("Results Excel", job.results_file.read_bytes(),
                                   file_name=job.results_file.name, icon=":material/table:",
                                   mime="application/vnd.openxmlformats-officedocument."
                                        "spreadsheetml.sheet")

    with st.expander("Details", expanded=job.state != "finished"):
        st.code("\n".join(job.log[-40:]) or "Starting…", language=None)


progress()
