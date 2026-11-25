from datetime import date

import pandas as pd
import streamlit as st

from tracker import clients_db
from tracker.clients_db import CATEGORIES

st.title("Data entry")
st.caption("Click a cell to change it · press + (top right of the table) to add a client · "
           "tick rows and press the bin to remove them. Changes save straight away.")

if "editor_version" not in st.session_state:
    st.session_state.editor_version = {k: 0 for k in CATEGORIES}


def _to_date(text: str):
    try:
        return date.fromisoformat(text) if text else None
    except ValueError:
        return None


def table(category: str) -> pd.DataFrame:
    cat = CATEGORIES[category]
    rows = clients_db.load(category)
    df = pd.DataFrame(rows, columns=["id", "name", "ref", "secret", "notes"])
    df["check"] = [("✔ ready" if not (p := clients_db.problem_of(category, r["ref"], r["secret"]))
                    else f"✖ {p}") for r in rows]
    if cat.secret_is_date:
        df["secret"] = df["secret"].map(_to_date)
    return df


def save_edits(category: str, ids: list[int], key: str) -> None:
    """Write the editor's changes to the database as soon as they happen."""
    clients_db.apply_changes(category, ids, st.session_state[key])
    st.session_state.editor_version[category] += 1     # fresh editor showing the saved data
    st.toast("Saved", icon=":material/check:")


tabs = st.tabs([f"{c.title} ({clients_db.count(c.key)})" for c in CATEGORIES.values()])
for tab, cat in zip(tabs, CATEGORIES.values()):
    with tab:
        df = table(cat.key)
        key = f"editor_{cat.key}_{st.session_state.editor_version[cat.key]}"
        secret_column = (
            st.column_config.DateColumn(cat.secret_label, format="DD/MM/YYYY", width="medium")
            if cat.secret_is_date
            else st.column_config.TextColumn(cat.secret_label, width="medium"))
        st.data_editor(
            df,
            key=key,
            num_rows="dynamic",
            hide_index=True,
            width="stretch",
            column_order=["name", "ref", "secret", "notes", "check"],
            column_config={
                "id": None,
                "name": st.column_config.TextColumn("Client name", width="large"),
                "ref": st.column_config.TextColumn(cat.ref_label, width="medium",
                                                   help=f"Like {cat.ref_hint}"),
                "secret": secret_column,
                "notes": st.column_config.TextColumn("Notes", width="medium"),
                "check": st.column_config.TextColumn("Ready?", disabled=True, width="medium"),
            },
            on_change=save_edits,
            args=(cat.key, df["id"].tolist(), key),
            alt=f"{cat.title} clients",
        )
        if cat.secret_is_password:
            st.caption(":material/lock: Passwords are stored only on the office PC that runs "
                       "this website.")
