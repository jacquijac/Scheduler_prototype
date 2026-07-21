"""CP-SAT-basierter Dienstplan-Solver.

Nimmt die drei Datentabellen (Ärzte, Skills, Tagesbedarf) plus fixe
Zuweisungen (Ferien) und eine Regel-Konfiguration entgegen und liefert einen
vollständigen Monatsplan zurück -- oder einen klaren Hinweis, welche
Constraints im Konflikt stehen, falls keine Lösung existiert.

Ärzt:innen werden direkt über ihren Namen identifiziert (Spalte "name" in
allen Tabellen) -- keine separaten IDs.
"""

from __future__ import annotations

import pandas as pd
import yaml
from ortools.sat.python import cp_model


def load_config(path: str = "rules_config.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _make_blocks(dates: list[str], block_length_days: int) -> list[list[str]]:
    """Teilt eine sortierte Liste von Datums-Strings in aufeinanderfolgende
    Blöcke fester Länge (letzter Block darf kürzer sein)."""
    blocks = []
    for i in range(0, len(dates), block_length_days):
        blocks.append(dates[i : i + block_length_days])
    return blocks


def solve_schedule(
    doctors_df: pd.DataFrame,
    skills_df: pd.DataFrame,
    daily_df: pd.DataFrame,
    fixed_df: pd.DataFrame,
    config: dict,
    time_limit_seconds: int = 30,
):
    """Löst den Monatsplan. Gibt (status_text, schedule_df, unfilled_df) zurück.

    schedule_df: eine Zeile pro (date, function, name) -- die finale Zuteilung
    unfilled_df: Slots, die NICHT besetzt werden konnten (leer, wenn alles klappt)
    """
    model = cp_model.CpModel()

    names = doctors_df["name"].tolist()
    on_call_eligible = set(doctors_df.loc[doctors_df["on_call_eligible"] == 1, "name"])
    dates = sorted(daily_df["date"].unique())

    qualified = {
        (row.name, row.function): bool(row.qualified) for row in skills_df.itertuples()
    }

    # Ferien: an diesem Tag komplett gesperrt.
    holidays = {(r.name, r.date) for r in fixed_df.itertuples() if r.type == "holiday"}
    # Optionale, bereits fix vorgegebene Rotationsblöcke aus fixed_assignments.csv
    # (type == "rotation") -- falls jemand von aussen vorgeben will, wer eine
    # Rotation übernimmt, statt den Solver frei wählen zu lassen.
    manual_rotation_days = {
        (r.name, r.date): r.function for r in fixed_df.itertuples() if r.type == "rotation"
    }

    oc_cfg = config["on_call"]
    ON_CALL_FN = oc_cfg["function_name"]
    weekend_dates = {d for d in dates if pd.Timestamp(d).weekday() >= 5}

    rot_cfg = config.get("rotations", {"block_functions": [], "block_length_days": 7})
    block_functions = set(rot_cfg.get("block_functions", []))
    block_length_days = int(rot_cfg.get("block_length_days", 7))
    date_blocks = _make_blocks(dates, block_length_days) if block_functions else []

    # --- Entscheidungsvariablen ---------------------------------------------
    # Normale Funktionen: assign[name, date, function, slot_type] , slot_type in {"main", "trainee"}
    # Block-Rotationsfunktionen: block_assign[name, function, block_index] -- eine Variable
    # pro Block statt pro Tag, damit dieselbe Person den ganzen Block übernimmt.
    assign = {}
    block_assign = {}
    slot_rows = list(daily_df.itertuples())

    daily_by_date_fn = {}
    for row in slot_rows:
        daily_by_date_fn.setdefault((row.date, row.function), row)

    for row in slot_rows:
        d, fn = row.date, row.function
        if fn in block_functions:
            continue  # wird unten blockweise behandelt
        for doc in names:
            if (doc, d) in holidays:
                continue
            if fn == ON_CALL_FN:
                is_q = doc in on_call_eligible
            else:
                is_q = qualified.get((doc, fn), False)
            if is_q:
                assign[(doc, d, fn, "main")] = model.NewBoolVar(f"a_{doc}_{d}_{fn}_main")
            if (
                config["training"]["allow_trainee_slots"]
                and getattr(row, "trainee_slot", 0) == 1
                and not is_q
            ):
                assign[(doc, d, fn, "trainee")] = model.NewBoolVar(f"a_{doc}_{d}_{fn}_train")

    # Block-Variablen für Rotationsfunktionen (z.B. Ward, Hepatology über je 1-2 Wochen)
    for fn in block_functions:
        for b_idx, block_dates in enumerate(date_blocks):
            relevant_dates = [d for d in block_dates if (d, fn) in daily_by_date_fn]
            if not relevant_dates:
                continue
            for doc in names:
                # Person muss an ALLEN Tagen des Blocks qualifiziert und verfügbar sein
                if any((doc, d) in holidays for d in relevant_dates):
                    continue
                if not qualified.get((doc, fn), False):
                    continue
                block_assign[(doc, fn, b_idx)] = model.NewBoolVar(f"blk_{doc}_{fn}_{b_idx}")

    # --- Harte Regel: jeder Haupt-Slot wird mit genau slots_needed besetzt -----
    unfilled_indicator = {}
    for (d, fn), row in daily_by_date_fn.items():
        needed = row.slots_needed
        if fn in block_functions:
            continue  # unten separat behandelt
        main_vars = [
            v for (doc, dd, ff, kind), v in assign.items() if dd == d and ff == fn and kind == "main"
        ]
        fixed_count = 1 if (d, fn) in {(dd, ff) for (doc, dd), ff in manual_rotation_days.items()} else 0
        remaining_needed = max(needed - fixed_count, 0)
        if main_vars:
            unfilled = model.NewIntVar(0, remaining_needed, f"unfilled_{d}_{fn}")
            model.Add(sum(main_vars) + unfilled == remaining_needed)
            unfilled_indicator[(d, fn)] = unfilled
        elif remaining_needed > 0:
            unfilled_indicator[(d, fn)] = remaining_needed

    # --- Block-Rotationen: pro Block genau 1 Person, über alle Tage des Blocks --
    for fn in block_functions:
        for b_idx, block_dates in enumerate(date_blocks):
            relevant_dates = [d for d in block_dates if (d, fn) in daily_by_date_fn]
            if not relevant_dates:
                continue
            block_vars = [v for (doc, ff, bi), v in block_assign.items() if ff == fn and bi == b_idx]
            unfilled = model.NewIntVar(0, 1, f"unfilled_blk_{fn}_{b_idx}")
            if block_vars:
                model.Add(sum(block_vars) + unfilled == 1)
            else:
                model.Add(unfilled == 1)
            for d in relevant_dates:
                unfilled_indicator[(d, fn)] = unfilled if d == relevant_dates[0] else 0

    # --- Harte Regel: höchstens eine Funktion pro Arzt pro Tag -----------------
    if config["hard_rules"]["max_one_function_per_doctor_per_day"]:
        for doc in names:
            for d in dates:
                vars_that_day = [
                    v for (dc, dd, ff, kind), v in assign.items() if dc == doc and dd == d
                ]
                for (dc, ff, bi), v in block_assign.items():
                    if dc != doc:
                        continue
                    if bi < len(date_blocks) and d in date_blocks[bi]:
                        vars_that_day.append(v)
                fixed_here = 1 if (doc, d) in manual_rotation_days else 0
                if vars_that_day:
                    model.Add(sum(vars_that_day) + fixed_here <= 1)

    # --- On-Call: HARTE OBERGRENZE pro Arzt/Monat (statt fixer Anzahl), --------
    # weiches Ziel für Wochenend-Verteilung und Fairness zwischen den Ärzt:innen
    oc_vars_by_doctor = {doc: [] for doc in on_call_eligible}
    for d in dates:
        for doc in on_call_eligible:
            key = (doc, d, ON_CALL_FN, "main")
            if key in assign:
                oc_vars_by_doctor[doc].append((d, assign[key]))

    weekend_penalty_terms = []
    oc_counts = []
    for doc, entries in oc_vars_by_doctor.items():
        total = [v for _, v in entries]
        if total:
            oc_count = model.NewIntVar(0, len(total), f"occ_{doc}")
            model.Add(oc_count == sum(total))
            model.Add(oc_count <= oc_cfg["max_days_per_month"])  # harte Obergrenze
            oc_counts.append(oc_count)
        weekend_vars = [v for d, v in entries if d in weekend_dates]
        if weekend_vars:
            wk_count = model.NewIntVar(0, len(weekend_vars), f"wk_{doc}")
            model.Add(wk_count == sum(weekend_vars))
            dev = model.NewIntVar(0, len(weekend_vars), f"wkdev_{doc}")
            target = oc_cfg["weekend_target_per_doctor"]
            model.AddAbsEquality(dev, wk_count - target)
            weekend_penalty_terms.append(dev)

    # Weiches Ziel: On-Call möglichst gleichmässig unter den on-call-fähigen
    # Ärzt:innen verteilen (innerhalb der harten Obergrenze)
    oc_spread_terms = []
    if oc_counts:
        max_oc = model.NewIntVar(0, len(dates), "max_oc")
        min_oc = model.NewIntVar(0, len(dates), "min_oc")
        model.AddMaxEquality(max_oc, oc_counts)
        model.AddMinEquality(min_oc, oc_counts)
        oc_spread = model.NewIntVar(0, len(dates), "oc_spread")
        model.Add(oc_spread == max_oc - min_oc)
        oc_spread_terms.append(oc_spread)

    # --- Weiche Regel: gleichmässige Verteilung der regulären Diensttage -------
    total_assigned = {doc: [] for doc in names}
    for (doc, d, fn, kind), v in assign.items():
        if fn != ON_CALL_FN:
            total_assigned[doc].append(v)
    for (doc, fn, bi), v in block_assign.items():
        n_days_in_block = len(date_blocks[bi]) if bi < len(date_blocks) else 1
        total_assigned[doc].extend([v] * n_days_in_block)  # gewichtet nach Blocklänge

    counts = []
    for doc in names:
        vs = total_assigned[doc]
        if vs:
            c = model.NewIntVar(0, len(dates), f"cnt_{doc}")
            model.Add(c == sum(vs))
            counts.append(c)
    balance_terms = []
    if counts:
        max_c = model.NewIntVar(0, len(dates), "max_c")
        min_c = model.NewIntVar(0, len(dates), "min_c")
        model.AddMaxEquality(max_c, counts)
        model.AddMinEquality(min_c, counts)
        spread = model.NewIntVar(0, len(dates), "spread")
        model.Add(spread == max_c - min_c)
        balance_terms.append(spread)

    # --- Zielfunktion: unbesetzte Slots zuerst minimieren, dann Fairness -------
    hard_unfilled = [v for v in unfilled_indicator.values() if not isinstance(v, int)]
    forced_unfilled_const = sum(v for v in unfilled_indicator.values() if isinstance(v, int))

    model.Minimize(
        1000 * (sum(hard_unfilled) + forced_unfilled_const)
        + 50 * sum(oc_spread_terms)
        + oc_cfg["weekend_deviation_penalty"] * sum(weekend_penalty_terms)
        + config["fairness"]["balance_workload_penalty"] * sum(balance_terms)
    )

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_seconds
    solver.parameters.num_search_workers = 8
    status = solver.Solve(model)
    status_name = solver.StatusName(status)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return status_name, pd.DataFrame(), pd.DataFrame()

    # --- Ergebnis auslesen ------------------------------------------------------
    result_rows = []
    for (doc, d, fn, kind), v in assign.items():
        if solver.Value(v) == 1:
            result_rows.append({"date": d, "function": fn, "name": doc, "slot_type": kind})
    for (doc, fn, bi), v in block_assign.items():
        if solver.Value(v) == 1:
            for d in date_blocks[bi]:
                if (d, fn) in daily_by_date_fn:
                    result_rows.append({"date": d, "function": fn, "name": doc, "slot_type": "rotation_block"})
    for (doc, d), fn in manual_rotation_days.items():
        result_rows.append({"date": d, "function": fn, "name": doc, "slot_type": "fixed_rotation"})

    schedule_df = pd.DataFrame(result_rows).sort_values(["date", "function"])

    unfilled_rows = []
    for (d, fn), v in unfilled_indicator.items():
        n = v if isinstance(v, int) else solver.Value(v)
        if n > 0:
            unfilled_rows.append({"date": d, "function": fn, "unfilled_slots": n})
    unfilled_df = pd.DataFrame(unfilled_rows)

    return status_name, schedule_df, unfilled_df
