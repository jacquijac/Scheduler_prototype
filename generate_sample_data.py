"""Erzeugt Beispieldaten (14 Ärzte, ein Monat) im richtigen Schema, damit
solver.py und app.py sofort getestet werden können. Für den echten Einsatz
einfach die CSVs in data/ durch eure echten Exporte ersetzen.

Ärzt:innen werden ab jetzt direkt über ihren Namen identifiziert -- keine
separaten IDs mehr, um die Daten in der Oberfläche direkt lesbar zu halten.
"""

import calendar
from datetime import date

import pandas as pd

YEAR, MONTH = 2026, 8  # Beispielmonat: August 2026
FUNCTIONS = ["Suite1", "Suite2", "Suite3", "Outpatient", "Ward", "Hepatology"]

NAMES = [
    "Müller Anna", "Keller Tobias", "Baumann Sara", "Zimmermann Elias",
    "Frei Nina", "Meier Jonas", "Steiner Lea", "Weber Simon",
    "Huber Mia", "Schneider Noah", "Fischer Laura", "Graf David",
    "Brunner Julia", "Vogel Marco",
]

# --- doctors.csv -------------------------------------------------------------
doctors = [
    {"name": n, "on_call_eligible": 1 if i <= 5 else 0}
    for i, n in enumerate(NAMES, start=1)
]
doctors_df = pd.DataFrame(doctors)

# --- skills.csv ----------------------------------------------------------------
# Nicht jede:r Ärzt:in kann jede Funktion. Suite3 (z.B. ERCP) ist am
# exklusivsten, Ward/Outpatient können fast alle.
skill_rows = []
for d in doctors:
    for fn in FUNCTIONS:
        if fn == "Suite3":
            qualified = 1 if d["name"] in NAMES[:4] else 0
        elif fn == "Suite2":
            qualified = 1 if d["name"] not in NAMES[12:] else 0
        else:
            qualified = 1
        skill_rows.append({"name": d["name"], "function": fn, "qualified": qualified})
skills_df = pd.DataFrame(skill_rows)

# --- daily_functions.csv --------------------------------------------------------
n_days = calendar.monthrange(YEAR, MONTH)[1]
all_dates = [date(YEAR, MONTH, day) for day in range(1, n_days + 1)]

daily_rows = []
for d in all_dates:
    is_weekend = d.weekday() >= 5
    if not is_weekend:
        # Werktags: Suite1/Suite2/Outpatient normal; Ward + Hepatology sind
        # Rotationsfunktionen (siehe rotations-Block in rules_config.yaml) --
        # sie erscheinen trotzdem hier täglich, werden vom Solver aber
        # blockweise mit derselben Person besetzt.
        for fn in ["Suite1", "Suite2", "Outpatient", "Ward", "Hepatology"]:
            daily_rows.append({
                "date": d.isoformat(), "function": fn, "slots_needed": 1,
                "trainee_slot": 1 if fn in ("Suite1", "Ward") else 0,
            })
        if d.weekday() in (1, 3):  # Di/Do
            daily_rows.append({"date": d.isoformat(), "function": "Suite3", "slots_needed": 1, "trainee_slot": 0})
    # On-Call: jeden Tag, wird separat im Solver behandelt (siehe rules_config.yaml)
    daily_rows.append({"date": d.isoformat(), "function": "OnCall", "slots_needed": 1, "trainee_slot": 0})

daily_df = pd.DataFrame(daily_rows)

# --- fixed_assignments.csv --------------------------------------------------------
# Ferien -- weiterhin einzelne Tage. Rotationen werden jetzt vom Solver
# blockweise vergeben (siehe rules_config.yaml: rotations.block_functions),
# daher hier keine Beispiel-Rotation mehr nötig.
fixed_rows = [
    {"name": "Frei Nina", "date": date(YEAR, MONTH, 3).isoformat(), "type": "holiday", "function": ""},
    {"name": "Frei Nina", "date": date(YEAR, MONTH, 4).isoformat(), "type": "holiday", "function": ""},
    {"name": "Frei Nina", "date": date(YEAR, MONTH, 5).isoformat(), "type": "holiday", "function": ""},
    {"name": "Huber Mia", "date": date(YEAR, MONTH, 10).isoformat(), "type": "holiday", "function": ""},
    {"name": "Huber Mia", "date": date(YEAR, MONTH, 11).isoformat(), "type": "holiday", "function": ""},
]
fixed_df = pd.DataFrame(fixed_rows)

if __name__ == "__main__":
    import os

    os.makedirs("data", exist_ok=True)
    doctors_df.to_csv("data/doctors.csv", index=False)
    skills_df.to_csv("data/skills.csv", index=False)
    daily_df.to_csv("data/daily_functions.csv", index=False)
    fixed_df.to_csv("data/fixed_assignments.csv", index=False)
    print(f"Beispieldaten für {YEAR}-{MONTH:02d} erzeugt: {len(doctors_df)} Ärzte, {n_days} Tage.")
