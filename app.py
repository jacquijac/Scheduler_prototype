"""Streamlit-Oberfläche für den Dienstplan-Solver.
Start: streamlit run app.py
"""

import io

import pandas as pd
import streamlit as st
import yaml

from solver import solve_schedule

st.set_page_config(page_title="Dienstplan Gastroenterologie", layout="wide")
st.title("📅 Dienstplan-Generator – Gastroenterologie")

st.markdown(
    "Daten direkt unten bearbeiten (Zeilen hinzufügen/löschen per Tabelle), "
    "Regeln anpassen und auf **Dienstplan berechnen** klicken."
)

DATA_PATHS = {
    "doctors": "data/doctors.csv",
    "skills": "data/skills.csv",
    "daily": "data/daily_functions.csv",
    "fixed": "data/fixed_assignments.csv",
}


def load_default(key):
    df = pd.read_csv(DATA_PATHS[key], dtype=str)
    return _coerce_types(key, df)


def _coerce_types(key, df):
    """CSV-Spalten, die leer sein können (z.B. 'function' bei Ferien-Zeilen),
    werden sonst von pandas als float/NaN statt als Text erkannt, was den
    data_editor zum Absturz bringt. Deshalb hier immer explizit auf Text/Zahl
    zurückcasten."""
    df = df.copy()
    if key == "doctors":
        df["on_call_eligible"] = pd.to_numeric(df.get("on_call_eligible", 0), errors="coerce").fillna(0).astype(int).astype(bool)
    if key == "skills":
        df["qualified"] = pd.to_numeric(df.get("qualified", 0), errors="coerce").fillna(0).astype(int).astype(bool)
    if key == "daily":
        df["slots_needed"] = pd.to_numeric(df.get("slots_needed", 1), errors="coerce").fillna(1).astype(int)
        df["trainee_slot"] = pd.to_numeric(df.get("trainee_slot", 0), errors="coerce").fillna(0).astype(int).astype(bool)
    if key == "fixed":
        df["function"] = df.get("function", "").fillna("").astype(str)
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].fillna("").astype(str)
    return df


# ---------------------------------------------------------------------------
# 1. Daten -- direkt editierbar
# ---------------------------------------------------------------------------
st.header("1. Daten bearbeiten")

if "doctors_df" not in st.session_state:
    st.session_state["doctors_df"] = load_default("doctors")
if "skills_df" not in st.session_state:
    st.session_state["skills_df"] = load_default("skills")
if "daily_df" not in st.session_state:
    st.session_state["daily_df"] = load_default("daily")
if "fixed_df" not in st.session_state:
    st.session_state["fixed_df"] = load_default("fixed")

upload_col, reset_col = st.columns([3, 1])
with upload_col:
    with st.expander("Eigene CSV-Dateien hochladen (ersetzt die aktuelle Tabelle)"):
        u1, u2, u3, u4 = st.columns(4)
        up_doctors = u1.file_uploader("doctors.csv", type="csv", key="up_doc")
        up_skills = u2.file_uploader("skills.csv", type="csv", key="up_skill")
        up_daily = u3.file_uploader("daily_functions.csv", type="csv", key="up_daily")
        up_fixed = u4.file_uploader("fixed_assignments.csv", type="csv", key="up_fixed")
        if up_doctors is not None:
            st.session_state["doctors_df"] = _coerce_types("doctors", pd.read_csv(up_doctors, dtype=str))
        if up_skills is not None:
            st.session_state["skills_df"] = _coerce_types("skills", pd.read_csv(up_skills, dtype=str))
        if up_daily is not None:
            st.session_state["daily_df"] = _coerce_types("daily", pd.read_csv(up_daily, dtype=str))
        if up_fixed is not None:
            st.session_state["fixed_df"] = _coerce_types("fixed", pd.read_csv(up_fixed, dtype=str))
with reset_col:
    if st.button("↺ Auf Beispieldaten zurücksetzen"):
        st.session_state["doctors_df"] = load_default("doctors")
        st.session_state["skills_df"] = load_default("skills")
        st.session_state["daily_df"] = load_default("daily")
        st.session_state["fixed_df"] = load_default("fixed")
        st.rerun()

tab_doc, tab_skill, tab_daily, tab_fixed = st.tabs(
    ["👩‍⚕️ Ärzte", "🎓 Skill-Matrix", "🗓️ Tagesbedarf", "🏖️ Ferien / fixe Rotationen"]
)

with tab_doc:
    st.caption("Ärzt:innen werden über ihren Namen identifiziert (muss eindeutig sein).")
    st.session_state["doctors_df"] = st.data_editor(
        st.session_state["doctors_df"],
        num_rows="dynamic",
        use_container_width=True,
        key="editor_doctors",
        column_config={
            "name": st.column_config.TextColumn("Name", required=True),
            "on_call_eligible": st.column_config.CheckboxColumn("On-Call-fähig"),
        },
    )

doctor_names = st.session_state["doctors_df"]["name"].dropna().unique().tolist()
functions_in_use = sorted(st.session_state["daily_df"]["function"].dropna().unique().tolist())

with tab_skill:
    st.caption("Wer darf welche Funktion übernehmen (hart qualifiziert/nicht qualifiziert).")
    st.session_state["skills_df"] = st.data_editor(
        st.session_state["skills_df"],
        num_rows="dynamic",
        use_container_width=True,
        key="editor_skills",
        column_config={
            "name": st.column_config.SelectboxColumn("Name", options=doctor_names, required=True),
            "function": st.column_config.SelectboxColumn("Funktion", options=functions_in_use or None),
            "qualified": st.column_config.CheckboxColumn("Qualifiziert"),
        },
    )

with tab_daily:
    st.caption("Welche Funktionen an welchem Tag besetzt werden müssen.")
    st.session_state["daily_df"] = st.data_editor(
        st.session_state["daily_df"],
        num_rows="dynamic",
        use_container_width=True,
        key="editor_daily",
        column_config={
            "date": st.column_config.TextColumn("Datum (YYYY-MM-DD)", required=True),
            "function": st.column_config.TextColumn("Funktion", required=True),
            "slots_needed": st.column_config.NumberColumn("Benötigte Slots", min_value=0, step=1),
            "trainee_slot": st.column_config.CheckboxColumn("Trainingsplatz erlaubt"),
        },
    )

with tab_fixed:
    st.caption(
        "Ferien = Ärzt:in an diesem Tag komplett gesperrt. "
        "'rotation' = optional eine Rotation von aussen fix vorgeben, statt den Solver frei wählen zu lassen."
    )
    st.session_state["fixed_df"] = st.data_editor(
        st.session_state["fixed_df"],
        num_rows="dynamic",
        use_container_width=True,
        key="editor_fixed",
        column_config={
            "name": st.column_config.SelectboxColumn("Name", options=doctor_names, required=True),
            "date": st.column_config.TextColumn("Datum (YYYY-MM-DD)", required=True),
            "type": st.column_config.SelectboxColumn("Typ", options=["holiday", "rotation"]),
            "function": st.column_config.TextColumn("Funktion (nur bei rotation)"),
        },
    )

doctors_df = st.session_state["doctors_df"]
skills_df = st.session_state["skills_df"]
daily_df = st.session_state["daily_df"]
fixed_df = st.session_state["fixed_df"]

# ---------------------------------------------------------------------------
# 2. Regeln
# ---------------------------------------------------------------------------
st.header("2. Regeln")

with open("rules_config.yaml", "r", encoding="utf-8") as f:
    default_config = yaml.safe_load(f)

c1, c2, c3 = st.columns(3)
with c1:
    max_on_call = st.number_input(
        "Max. On-Call-Tage pro Ärzt:in / Monat",
        min_value=0, max_value=31,
        value=default_config["on_call"]["max_days_per_month"],
        help="Harte Obergrenze -- niemand macht mehr On-Call-Tage als dieser Wert.",
    )
with c2:
    weekend_target = st.number_input(
        "Ziel Wochenend-On-Calls pro Ärzt:in",
        min_value=0, max_value=10,
        value=default_config["on_call"]["weekend_target_per_doctor"],
    )
with c3:
    allow_trainee = st.checkbox(
        "Trainingsplätze erlauben", value=default_config["training"]["allow_trainee_slots"]
    )

c4, c5 = st.columns(2)
with c4:
    all_functions = functions_in_use
    default_block_fns = [f for f in default_config["rotations"]["block_functions"] if f in all_functions]
    block_functions = st.multiselect(
        "Funktionen mit Block-Rotation (gleiche Person über mehrere Wochen)",
        options=all_functions,
        default=default_block_fns,
    )
with c5:
    block_length = st.number_input(
        "Blocklänge (Tage)", min_value=1, max_value=31,
        value=default_config["rotations"]["block_length_days"],
        help="7 = wöchentliche Rotation, 14 = zwei Wochen am Stück, etc.",
    )

config = default_config.copy()
config["on_call"]["max_days_per_month"] = int(max_on_call)
config["on_call"]["weekend_target_per_doctor"] = int(weekend_target)
config["training"]["allow_trainee_slots"] = bool(allow_trainee)
config["rotations"]["block_functions"] = block_functions
config["rotations"]["block_length_days"] = int(block_length)

# ---------------------------------------------------------------------------
# 3. Lösen
# ---------------------------------------------------------------------------
st.header("3. Dienstplan berechnen")

if st.button("🚀 Dienstplan berechnen", type="primary"):
    with st.spinner("Löse Optimierungsproblem..."):
        status, schedule_df, unfilled_df = solve_schedule(
            doctors_df, skills_df, daily_df, fixed_df, config
        )
    st.session_state["status"] = status
    st.session_state["schedule_df"] = schedule_df
    st.session_state["unfilled_df"] = unfilled_df

if "schedule_df" in st.session_state:
    status = st.session_state["status"]
    schedule_df = st.session_state["schedule_df"]
    unfilled_df = st.session_state["unfilled_df"]

    if status not in ("OPTIMAL", "FEASIBLE"):
        st.error(f"Keine Lösung gefunden (Status: {status}). Regeln oder Daten prüfen.")
    else:
        st.success(f"Plan erstellt (Status: {status})")

        if not unfilled_df.empty:
            st.warning("Folgende Slots konnten nicht besetzt werden:")
            st.dataframe(unfilled_df, use_container_width=True)
        else:
            st.info("Alle Slots wurden erfolgreich besetzt.")

        st.subheader("Dienstplan – Agenda (Daten auf der x-Achse)")
        pivot = schedule_df.pivot_table(
            index="function", columns="date", values="name", aggfunc=lambda x: ", ".join(x)
        )
        # Spalten (Tage) chronologisch sortiert
        pivot = pivot.reindex(sorted(pivot.columns), axis=1)
        st.dataframe(pivot, use_container_width=True)

        st.subheader("On-Call-Verteilung")
        oc = schedule_df[schedule_df.function == config["on_call"]["function_name"]]
        oc_counts = oc["name"].value_counts()
        st.bar_chart(oc_counts)

        st.subheader("Export")
        csv_buf = io.StringIO()
        schedule_df.to_csv(csv_buf, index=False)
        st.download_button(
            "📥 Dienstplan als CSV herunterladen",
            data=csv_buf.getvalue(),
            file_name="dienstplan.csv",
            mime="text/csv",
        )

        excel_buf = io.BytesIO()
        with pd.ExcelWriter(excel_buf, engine="openpyxl") as writer:
            pivot.to_excel(writer, sheet_name="Agenda")
            schedule_df.to_excel(writer, sheet_name="Rohdaten", index=False)
        st.download_button(
            "📥 Dienstplan als Excel herunterladen",
            data=excel_buf.getvalue(),
            file_name="dienstplan.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

st.divider()
st.subheader("Bearbeitete Eingabedaten exportieren")
st.caption("Falls du die Tabellen oben verändert hast und sie dauerhaft speichern willst.")
e1, e2, e3, e4 = st.columns(4)
e1.download_button("💾 doctors.csv", doctors_df.to_csv(index=False), "doctors.csv", "text/csv")
e2.download_button("💾 skills.csv", skills_df.to_csv(index=False), "skills.csv", "text/csv")
e3.download_button("💾 daily_functions.csv", daily_df.to_csv(index=False), "daily_functions.csv", "text/csv")
e4.download_button("💾 fixed_assignments.csv", fixed_df.to_csv(index=False), "fixed_assignments.csv", "text/csv")
