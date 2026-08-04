"""One-time mechanical migration of MFAR notebooks to shared path contracts."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
NOTEBOOK_DIR = ROOT / "notebooks"

BOOTSTRAP = '''#@title Shared MFAR paths and stage initialization
from pathlib import Path
from datetime import datetime, timezone
import os, sys, warnings
import pandas as pd
import numpy as np
warnings.filterwarnings("ignore")

# Locate the code repository only; all simulation I/O paths are resolved by
# src.mfar_paths through MFAR_GDRIVE_ROOT or the mounted/synchronized Drive.
_code_candidates = [Path.cwd(), Path.cwd().parent]
if os.environ.get("MFAR_CODE_ROOT"):
    _code_candidates.insert(0, Path(os.environ["MFAR_CODE_ROOT"]))
_code_candidates.extend([
    Path("/content/drive/MyDrive/MFAR_Modular_Colab_Pipeline"),
    Path("/content/drive/MyDrive/MFAR_Modular_Colab_Pipeline/MFAR_Modular_Colab_Pipeline"),
])
for _candidate in _code_candidates:
    if (_candidate / "src" / "mfar_paths.py").is_file():
        sys.path.insert(0, str(_candidate.resolve()))
        break
else:
    raise FileNotFoundError(
        "Modul src/mfar_paths.py tidak ditemukan. Jalankan notebook dari repository "
        "atau tetapkan MFAR_CODE_ROOT ke folder repository."
    )

from src.mfar_paths import (
    AIS_RAW_PATH, VEHICLE_ARRIVAL_PATH, DATA_RAW_DIR, CONFIG_DIR,
    STAGE_OUTPUT_DIR, STAGE_01_DIR, STAGE_02_DIR, STAGE_03_DIR,
    STAGE_04_DIR, STAGE_05_DIR, STAGE_06_DIR, STAGE_07_DIR,
    validate_csv_input, validate_raw_inputs, validate_writable_directory,
    write_execution_metadata,
)

_MFAR_STARTED_AT = datetime.now(timezone.utc)
'''

SETUPS = {
    1: '''
NOTEBOOK_NAME = "01_AIS_Input_and_Cleaning.ipynb"
RAW, CONFIG, STAGE = DATA_RAW_DIR, CONFIG_DIR, STAGE_01_DIR
AIS_FILE = AIS_RAW_PATH
validate_raw_inputs(NOTEBOOK_NAME)
validate_writable_directory(STAGE, NOTEBOOK_NAME, 1)
print("AIS source:", AIS_FILE)
print("Output folder:", STAGE)
''',
    2: '''
NOTEBOOK_NAME = "02_Time_Grid_and_State_Preparation.ipynb"
STAGE1, STAGE2, CONFIG = STAGE_01_DIR, STAGE_02_DIR, CONFIG_DIR
INPUT_AIS = STAGE1 / "01_ais_clean.csv"
PROFILE_FILE = CONFIG / "vessel_profiles.csv"
BERTH_FILE = CONFIG / "terminal_berths.csv"
GRID_INTERVAL_MIN = 5
MAX_BRACKET_GAP_MIN = 20
validate_writable_directory(STAGE2, NOTEBOOK_NAME, 2)
print("Input AIS:", INPUT_AIS)
print("Output folder:", STAGE2)
''',
    3: '''
NOTEBOOK_NAME = "03_Monitoring_State.ipynb"
RAW, CFG, STAGE = DATA_RAW_DIR, CONFIG_DIR, STAGE_OUTPUT_DIR
validate_writable_directory(STAGE_03_DIR, NOTEBOOK_NAME, 3)
print("Input stage:", STAGE_02_DIR)
print("Output folder:", STAGE_03_DIR)
''',
    4: '''
NOTEBOOK_NAME = "04_No_Intervention_Forecast.ipynb"
RAW, CFG, STAGE = DATA_RAW_DIR, CONFIG_DIR, STAGE_OUTPUT_DIR
validate_writable_directory(STAGE_04_DIR, NOTEBOOK_NAME, 4)
print("Input stage:", STAGE_03_DIR)
print("Vehicle arrivals:", VEHICLE_ARRIVAL_PATH)
print("Output folder:", STAGE_04_DIR)
''',
    5: '''
NOTEBOOK_NAME = "05_Fuzzification.ipynb"
RAW, CFG, STAGE = DATA_RAW_DIR, CONFIG_DIR, STAGE_OUTPUT_DIR
validate_writable_directory(STAGE_05_DIR, NOTEBOOK_NAME, 5)
print("Input stage:", STAGE_04_DIR)
print("Output folder:", STAGE_05_DIR)
''',
    6: '''
NOTEBOOK_NAME = "06_Rule_Evaluation.ipynb"
RAW, CFG, STAGE = DATA_RAW_DIR, CONFIG_DIR, STAGE_OUTPUT_DIR
validate_writable_directory(STAGE_06_DIR, NOTEBOOK_NAME, 6)
print("Input stage:", STAGE_05_DIR)
print("Output folder:", STAGE_06_DIR)
''',
    7: '''
NOTEBOOK_NAME = "07_Candidate_Action.ipynb"
RAW, CFG, STAGE = DATA_RAW_DIR, CONFIG_DIR, STAGE_OUTPUT_DIR
validate_writable_directory(STAGE_07_DIR, NOTEBOOK_NAME, 7)
print("Input stages:", STAGE_04_DIR, STAGE_06_DIR)
print("Output folder:", STAGE_07_DIR)
''',
}

INPUT_REPLACEMENTS = {
    1: {
        "raw = pd.read_csv(AIS_FILE)": "raw = validate_csv_input(AIS_FILE, required_source_columns if 'required_source_columns' in globals() else [\"created_at\",\"mmsi\",\"lat\",\"lon\",\"sog\",\"cog\",\"valid\",\"navstatus\"], NOTEBOOK_NAME, 1)",
    },
    2: {
        "ais = pd.read_csv(INPUT_AIS)": "ais = validate_csv_input(INPUT_AIS, [\"timestamp\",\"mmsi\",\"latitude\",\"longitude\",\"sog\",\"cog\"], NOTEBOOK_NAME, 2)",
    },
    3: {
        "state = pd.read_csv(INFILE)": "state = validate_csv_input(INFILE, [\"grid_time\",\"mmsi\",\"operational_status\",\"current_berth_id\",\"is_at_berth\"], NOTEBOOK_NAME, 3)",
    },
    4: {
        'state=pd.read_csv(STAGE/"stage_03"/"03_input_state_enhanced.csv")': 'state=validate_csv_input(STAGE_03_DIR/"03_input_state_enhanced.csv", ["grid_time","mmsi","operational_status","origin","destination","nearest_distance_nm","is_at_berth","berth_episode_id"], NOTEBOOK_NAME, 4)',
        'rates=pd.read_csv(RAW/"vehicle_arrival_rate_30min.csv")': 'rates=validate_csv_input(VEHICLE_ARRIVAL_PATH, ["port_id","time_start","time_end","car_arrival_rate_30min","motorcycle_arrival_rate_30min"], NOTEBOOK_NAME, 4)',
    },
    5: {
        'df=pd.read_csv(STAGE/"stage_04"/"04_fuzzy_input.csv")': 'df=validate_csv_input(STAGE_04_DIR/"04_fuzzy_input.csv", ["simulation_time","origin_queue_ratio","destination_queue_ratio","berth_availability_at_eta","predicted_wait_min","forecast_confidence","minutes_to_next_departure","capacity_shortfall_next_60min","operational_status"], NOTEBOOK_NAME, 5)',
    },
    6: {
        'df=pd.read_csv(STAGE/"stage_05"/"05_fuzzy_memberships.csv")': 'df=validate_csv_input(STAGE_05_DIR/"05_fuzzy_memberships.csv", ["simulation_time","origin","selected_action"] if False else ["simulation_time","origin","mu_origin_queue_low","mu_berth_available","mu_berth_unavailable"], NOTEBOOK_NAME, 6)',
    },
    7: {
        'queue=pd.read_csv(STAGE/"stage_04"/"04_daily_port_queue_forecast.csv")': 'queue=validate_csv_input(STAGE_04_DIR/"04_daily_port_queue_forecast.csv", ["simulation_time","port_id","queue_ce","queue_ratio"], NOTEBOOK_NAME, 7)',
        'events=pd.read_csv(STAGE/"stage_04"/"04_daily_event_log.csv")': 'events=validate_csv_input(STAGE_04_DIR/"04_daily_event_log.csv", ["simulation_time","origin","served_ce"], NOTEBOOK_NAME, 7)',
        'rules=pd.read_csv(STAGE/"stage_06"/"06_rule_evaluation.csv")': 'rules=validate_csv_input(STAGE_06_DIR/"06_rule_evaluation.csv", ["simulation_time","origin","selected_action","selected_rule_strength","dominant_rule"], NOTEBOOK_NAME, 7)',
    },
}

VARIABLES = {
    1: ("raw", "clean"), 2: ("ais", "output_grid"), 3: ("state", "state"),
    4: ("state", "forecast"), 5: ("df", "df"), 6: ("df", "out"),
    7: ("queue", "sim"),
}


def metadata_cell(stage: int) -> str:
    input_var, output_var = VARIABLES[stage]
    inputs = {
        1: "[AIS_RAW_PATH, VEHICLE_ARRIVAL_PATH]",
        2: "[INPUT_AIS, PROFILE_FILE, BERTH_FILE]",
        3: "[INFILE, CFG/'vessel_profiles.csv', CFG/'terminal_berths.csv']",
        4: "[STAGE_03_DIR/'03_input_state_enhanced.csv', VEHICLE_ARRIVAL_PATH, CFG/'vessel_profiles.csv', CFG/'terminal_berths.csv']",
        5: "[STAGE_04_DIR/'04_fuzzy_input.csv']",
        6: "[STAGE_05_DIR/'05_fuzzy_memberships.csv']",
        7: "[STAGE_04_DIR/'04_daily_port_queue_forecast.csv', STAGE_04_DIR/'04_daily_event_log.csv', STAGE_06_DIR/'06_rule_evaluation.csv', CFG/'vessel_profiles.csv']",
    }[stage]
    return f'''#@title Execution metadata and saved-artifact report
_stage_dir = STAGE_{stage:02d}_DIR
_saved_files = sorted(_stage_dir.glob("{stage:02d}_*"))
write_execution_metadata(
    stage={stage}, notebook=NOTEBOOK_NAME, started_at=_MFAR_STARTED_AT,
    input_paths={inputs},
    input_rows={{"{input_var}": len({input_var})}},
    output_rows={{"{output_var}": len({output_var})}},
    output_files=_saved_files,
)
'''


for stage, notebook_path in enumerate(sorted(NOTEBOOK_DIR.glob("*.ipynb")), start=1):
    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    notebook["cells"][1]["source"] = (BOOTSTRAP + SETUPS[stage]).splitlines(keepends=True)
    for cell in notebook["cells"]:
        if cell.get("cell_type") != "code":
            continue
        cell["execution_count"] = None
        cell["outputs"] = []
        source = "".join(cell.get("source", []))
        for old, new in INPUT_REPLACEMENTS[stage].items():
            source = source.replace(old, new)
        cell["source"] = source.splitlines(keepends=True)

    if not any(
        "Execution metadata and saved-artifact report" in "".join(cell.get("source", []))
        for cell in notebook["cells"]
    ):
        notebook["cells"].append(
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": metadata_cell(stage).splitlines(keepends=True),
            }
        )
    notebook_path.write_text(
        json.dumps(notebook, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )
    print(f"Updated {notebook_path}")
