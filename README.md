# Gastro-Klinik Dienstplan – Prototyp

Ein lauffähiger Prototyp: CP-SAT-Solver (Google OR-Tools) + Streamlit-Oberfläche.
Erzeugt einen Monatsplan aus drei Input-Tabellen und einer Regel-Konfiguration.

## Struktur

```
scheduler/
├── data/
│   ├── doctors.csv              # Ärzte-Stammdaten
│   ├── skills.csv               # Skill-Matrix: wer ist für welche Funktion qualifiziert
│   ├── daily_functions.csv      # welche Funktionen an welchem Tag besetzt werden müssen
│   └── fixed_assignments.csv    # fixe Rotationen / Ferien (unantastbar)
├── rules_config.yaml            # alle einstellbaren Regel-Parameter
├── solver.py                    # der eigentliche CP-SAT-Optimierer
├── generate_sample_data.py      # erzeugt die Beispieldaten oben (zum Testen)
└── app.py                       # Streamlit-Oberfläche (Upload → Lösen → Anzeigen → Export)
```

## Datenschema

**doctors.csv**
| Spalte | Bedeutung |
|---|---|
| doctor_id | eindeutige Kennung |
| name | Anzeigename |
| on_call_eligible | 1/0 – nimmt am Bereitschaftsdienst teil |

**skills.csv** (long format, eine Zeile pro Arzt×Funktion)
| Spalte | Bedeutung |
|---|---|
| doctor_id | |
| function | z.B. `Suite1`, `Suite2`, `Suite3`, `Outpatient`, `Ward`, `Hepatology` |
| qualified | 1 = hart qualifiziert, 0 = nicht qualifiziert (kann nur als **Trainingsplatz** zusätzlich eingeteilt werden, siehe unten) |

**daily_functions.csv** (was an jedem Tag besetzt werden muss)
| Spalte | Bedeutung |
|---|---|
| date | YYYY-MM-DD |
| function | Name der Funktion |
| slots_needed | wie viele qualifizierte Ärzte diese Funktion an diesem Tag braucht (meist 1) |
| trainee_slot | 1/0 – ob zusätzlich ein/e unqualifizierte:r Ärzt:in zu Ausbildungszwecken mitlaufen kann |

**fixed_assignments.csv** (fix vorgegeben, wird vom Solver nicht angetastet)
| Spalte | Bedeutung |
|---|---|
| doctor_id | |
| date | |
| type | `holiday` (nicht verfügbar) oder `rotation` (fix auf eine Funktion gebucht) |
| function | nur bei `type=rotation` relevant |

## Wichtige Annahmen, die ich getroffen habe (bitte prüfen/anpassen)

Diese Punkte sind als **Parameter in `rules_config.yaml`** hinterlegt, nicht im Code fest verdrahtet, damit sie leicht korrigierbar sind:

1. **On-Call** – `on_call.max_days_per_month` ist eine **harte Obergrenze** (niemand macht mehr Tage als dieser Wert), keine exakte Vorgabe. Der Solver verteilt die tatsächlich anfallenden On-Call-Tage so gleichmässig wie möglich unter den on-call-fähigen Ärzt:innen, bis zur Obergrenze.
2. **"Optimal 1 Wochenende pro Monat"** – als **weiches** Ziel umgesetzt: der Solver minimiert die Abweichung von `on_call.weekend_target_per_doctor` Wochenendtagen (Sa/So) On-Call pro Ärzt:in, verletzt es aber wenn nötig, statt komplett unlösbar zu werden.
3. **Trainingsplätze** – nicht-qualifizierte Ärzt:innen werden nie *anstelle* der geforderten qualifizierten Besetzung eingeteilt, sondern nur als **zusätzlicher** Platz, wenn `trainee_slot=1` für diese Funktion/diesen Tag gesetzt ist.
4. **Block-Rotationen** – Funktionen in `rotations.block_functions` (z.B. Ward, Hepatology) werden nicht täglich neu vergeben, sondern in Blöcken von `rotations.block_length_days` Tagen (Default: 7 = eine Woche) an **eine** Person vergeben, die für den ganzen Block qualifiziert und verfügbar sein muss. Beide Werte sind in der Oberfläche direkt einstellbar.
5. **Ärzt:innen-Identifikation** – alle Tabellen referenzieren Ärzt:innen über die Spalte `name` (muss eindeutig sein) statt über separate IDs, damit die Daten in der Oberfläche direkt lesbar sind.

## Ausführen

```bash
pip install ortools pandas streamlit
cd scheduler
python generate_sample_data.py      # erzeugt Beispieldaten in data/
streamlit run app.py                # öffnet die Oberfläche im Browser
```

Für den Praxiseinsatz: entweder `data/*.csv` durch eure echten Exporte ersetzen (gleiches Spaltenschema, jetzt mit `name` statt `doctor_id`), oder die Tabellen direkt in der Streamlit-Oberfläche bearbeiten (Zeilen hinzufügen/löschen per Klick) und am Ende als CSV herunterladen. `rules_config.yaml`-Werte sind ebenfalls direkt in der Oberfläche einstellbar.

## Nächste Schritte (nicht im Prototyp enthalten)

- Manuelles Überschreiben einzelner Zuweisungen in der Oberfläche + Re-Validierung
- Export als .ics / PDF
- Mehrmonats-Historie für echte Fairness (aktuell wird jeder Monat unabhängig optimiert)
- Nutzer-Login / Rechte, falls mehrere Personen den Plan pflegen
# Scheduler_prototype
