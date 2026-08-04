"""Mechanical notebook rewrite for the audited MFAR pipeline."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOKS = ROOT / "notebooks"


def code(source: str) -> dict:
    return {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [],
            "source": source.splitlines(keepends=True)}


def markdown(source: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": source.splitlines(keepends=True)}


COMMON = '''# Shared paths and deterministic stage initialization
from pathlib import Path
from datetime import datetime, timezone
import os, sys
import pandas as pd

root = Path(os.environ.get("MFAR_CODE_ROOT", Path.cwd()))
if not (root / "src" / "mfar_paths.py").is_file():
    root = Path.cwd().parent
if not (root / "src" / "mfar_paths.py").is_file():
    raise FileNotFoundError("Run the notebook from the repository or set MFAR_CODE_ROOT")
sys.path.insert(0, str(root.resolve()))

from src.mfar_paths import *
from src.mfar_core import *
STARTED_AT = datetime.now(timezone.utc)
'''


STAGES = {
    3: ("03_Monitoring_State.ipynb", '''
state = validate_csv_input(STAGE_02_DIR / "02_vessel_interpolated_grid.csv",
    ["grid_time", "mmsi", "operational_status", "current_berth_id", "is_at_berth",
     "bracket_gap_min", "nearest_port_id"], NOTEBOOK_NAME, 3)
profiles = pd.read_csv(CONFIG_DIR / "vessel_profiles.csv")
state, episodes, empirical, audit, calibration_cutoff = run_stage3(
    state, profiles, STAGE_03_DIR, CONFIG_DIR)
display(audit)
print("Calibration cutoff:", calibration_cutoff)
'''),
    4: ("04_No_Intervention_Forecast.ipynb", '''
state = validate_csv_input(STAGE_03_DIR / "03_input_state_enhanced.csv",
    ["grid_time", "mmsi", "operational_status", "origin", "destination", "is_at_berth",
     "predicted_berth_release_time", "operational_phase"], NOTEBOOK_NAME, 4)
for col in ["grid_time", "predicted_berth_release_time"]:
    state[col] = pd.to_datetime(state[col], errors="coerce")
episodes = validate_csv_input(STAGE_03_DIR / "03_berth_episode_history.csv",
    ["mmsi", "berth_entry_time", "observed_end", "port_id"], NOTEBOOK_NAME, 4)
rates = validate_csv_input(VEHICLE_ARRIVAL_PATH,
    ["port_id", "time_start", "time_end", "car_arrival_rate_30min", "motorcycle_arrival_rate_30min"], NOTEBOOK_NAME, 4)
profiles = pd.read_csv(CONFIG_DIR / "vessel_profiles.csv")
berths = pd.read_csv(CONFIG_DIR / "terminal_berths.csv")
queue, event_log, forecast, summary, eta_audit, departure_audit = run_stage4(
    state, episodes, rates, profiles, berths, STAGE_04_DIR, CONFIG_DIR)
display(summary); display(eta_audit); display(departure_audit)
'''),
    5: ("05_Fuzzification.ipynb", '''
forecast = validate_csv_input(STAGE_04_DIR / "04_fuzzy_input.csv",
    ["simulation_time", "decision_time", "baseline_departure_time", "operational_phase",
     "origin_queue_ratio", "destination_queue_ratio", "berth_availability_at_eta",
     "predicted_wait_min", "forecast_confidence", "service_gap_min", "capacity_shortfall_ratio"],
    NOTEBOOK_NAME, 5)
memberships, definitions, audit = run_stage5(forecast, STAGE_05_DIR, CONFIG_DIR)
display(audit)
'''),
    6: ("06_Rule_Evaluation.ipynb", '''
memberships = validate_csv_input(STAGE_05_DIR / "05_fuzzy_memberships.csv",
    ["simulation_time", "origin", "operational_phase", "mu_origin_queue_low",
     "mu_berth_available", "mu_berth_unavailable"], NOTEBOOK_NAME, 6)
evaluated, catalog, rule_summary = run_stage6(memberships, STAGE_06_DIR, CONFIG_DIR)
display(evaluated["selected_action"].value_counts()); display(rule_summary)
'''),
    7: ("07_Candidate_Action.ipynb", '''
queue = validate_csv_input(STAGE_04_DIR / "04_daily_port_queue_forecast.csv",
    ["simulation_time", "port_id", "queue_ce", "queue_ratio"], NOTEBOOK_NAME, 7)
queue["simulation_time"] = pd.to_datetime(queue["simulation_time"], errors="coerce")
events = validate_csv_input(STAGE_04_DIR / "04_daily_event_log.csv",
    ["simulation_time", "origin", "served_ce", "mmsi"], NOTEBOOK_NAME, 7)
events["simulation_time"] = pd.to_datetime(events["simulation_time"], errors="coerce")
evaluated = validate_csv_input(STAGE_06_DIR / "06_rule_evaluation.csv",
    ["simulation_time", "origin", "mmsi", "operational_phase", "selected_action",
     "selected_rule_strength", "dominant_rule"], NOTEBOOK_NAME, 7)
evaluated["simulation_time"] = pd.to_datetime(evaluated["simulation_time"], errors="coerce")
rates = pd.read_csv(VEHICLE_ARRIVAL_PATH)
profiles = pd.read_csv(CONFIG_DIR / "vessel_profiles.csv")
sim, accepted, effects, daily, overall = run_stage7(
    queue, events, evaluated, rates, profiles, STAGE_07_DIR, CONFIG_DIR)
display(overall); display(daily.head(12))
print("Stage 07 is scenario evaluation, not empirical intervention validation.")
'''),
}


def write_stage(stage: int, filename: str, body: str) -> None:
    title = {
        3: "Empirical berth-state calibration",
        4: "Temporal-holdout pre-departure forecast",
        5: "Configuration-driven fuzzification",
        6: "Phase-constrained fuzzy rule evaluation",
        7: "Multi-day scenario evaluation",
    }[stage]
    final = f'''NOTEBOOK_NAME = "{filename}"
stage_dir = STAGE_DIRS[{stage}]
files = sorted(stage_dir.glob("{stage:02d}_*"))
write_execution_metadata({stage}, NOTEBOOK_NAME, STARTED_AT,
    [CONFIG_DIR / "pipeline_parameters.csv"], {{}}, {{"primary": len(locals().get("state", locals().get("forecast", locals().get("sim", []))))}}, files)
'''
    payload = {"cells": [markdown(f"# Stage {stage:02d} · {title}\n\nThis notebook delegates tested logic to `src/mfar_core.py` and writes auditable artifacts."),
                         code(COMMON), code(f'NOTEBOOK_NAME = "{filename}"\nvalidate_writable_directory(STAGE_DIRS[{stage}], NOTEBOOK_NAME, {stage})\n'),
                         code(body.strip() + "\n"), code(final)],
               "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                            "language_info": {"name": "python", "version": "3"}},
               "nbformat": 4, "nbformat_minor": 5}
    (NOTEBOOKS / filename).write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")


def replace_map_cells(filename: str, indices: list[int], replacement: str) -> None:
    path = NOTEBOOKS / filename
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["cells"][indices[0]] = code(replacement)
    for idx in indices[1:]:
        payload["cells"][idx] = code("# Map generation centralized in src/mfar_maps.py.\n")
    for cell in payload["cells"]:
        if cell.get("cell_type") == "code":
            cell["outputs"] = []; cell["execution_count"] = None
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")


for stage, (filename, body) in STAGES.items():
    write_stage(stage, filename, body)

replace_map_cells("01_AIS_Input_and_Cleaning.ipynb", [9, 10, 11, 12], '''# Audited Stage 01 spatial map
from src.mfar_maps import build_validation_map
berths = pd.read_csv(CONFIG / "terminal_berths.csv")
map_path, map_segments, map_audit = build_validation_map(
    clean, berths, STAGE / "01_ais_full_validation_map.html", "timestamp", max_points=2500)
map_segments.to_csv(STAGE / "01_map_segment_audit.csv", index=False)
print(map_path); display(pd.DataFrame([map_audit]))
''')

replace_map_cells("02_Time_Grid_and_State_Preparation.ipynb", [13, 14, 15, 16, 19], '''# Audited Stage 02 spatial maps
from src.mfar_maps import build_validation_map
berths = pd.read_csv(CONFIG / "terminal_berths.csv")
ais_compare = ais.copy()
full_path, full_segments, full_audit = build_validation_map(
    output_grid, berths, STAGE2 / "02_interpolated_full_validation_map.html", "grid_time",
    original=ais_compare, original_time_col="timestamp", max_points=1800, max_original_points=1000)
all_segment_audits = [full_segments.assign(map_file=full_path.name)]
for mmsi, vessel in output_grid.groupby("mmsi"):
    density = vessel.assign(map_date=vessel["grid_time"].dt.date).groupby("map_date").size()
    selected_date = density.idxmax()
    view = vessel[vessel["grid_time"].dt.date.eq(selected_date)]
    original_view = ais_compare[(ais_compare["mmsi"].astype(str) == str(mmsi)) & (ais_compare["timestamp"].dt.date.eq(selected_date))]
    name = f"02_validation_map_{int(mmsi)}_{selected_date}.html"
    path, segments, audit = build_validation_map(view, berths, STAGE2 / name, "grid_time",
        original=original_view, original_time_col="timestamp", max_points=2500, max_original_points=1200)
    all_segment_audits.append(segments.assign(map_file=path.name))
pd.concat(all_segment_audits, ignore_index=True).to_csv(STAGE2 / "02_map_segment_audit.csv", index=False)
print(full_path); display(pd.DataFrame([full_audit]))
''')
