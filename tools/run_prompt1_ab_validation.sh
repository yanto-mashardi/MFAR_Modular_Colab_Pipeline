#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="${GITHUB_WORKSPACE:-$(cd "$(dirname "$0")/.." && pwd)}"
CURRENT_ROOT="/tmp/prompt1_current/${DRIVE_FOLDER_NAME}"
LEGACY_ROOT="/tmp/prompt1_legacy/${DRIVE_FOLDER_NAME}"
LEGACY_SHA="bcf3afe36e3edf9ca84047933316878ffa4b606a"
NOTEBOOKS=(
  01_AIS_Input_and_Cleaning.ipynb
  02_Time_Grid_and_State_Preparation.ipynb
  03_Monitoring_State.ipynb
  04_No_Intervention_Forecast.ipynb
  05_Fuzzification.ipynb
  06_Rule_Evaluation.ipynb
  07_Candidate_Action.ipynb
)

mkdir -p "$CURRENT_ROOT/data_raw" "$LEGACY_ROOT/data_raw"
python - <<'PY'
import os
from pathlib import Path
import gdown

roots = [
    Path('/tmp/prompt1_current') / os.environ['DRIVE_FOLDER_NAME'] / 'data_raw',
    Path('/tmp/prompt1_legacy') / os.environ['DRIVE_FOLDER_NAME'] / 'data_raw',
]
targets = {
    os.environ['AIS_FILE_ID']: 'ais_raw.csv',
    os.environ['ARRIVAL_FILE_ID']: 'vehicle_arrival_rate_30min.csv',
}
for file_id, filename in targets.items():
    primary = roots[0] / filename
    result = gdown.download(id=file_id, output=str(primary), quiet=False)
    if result is None or not primary.is_file() or primary.stat().st_size == 0:
        raise RuntimeError(f'Google Drive input could not be downloaded: {file_id}')
    (roots[1] / filename).write_bytes(primary.read_bytes())
PY

run_notebooks() {
  local notebook_root="$1"
  local drive_root="$2"
  mkdir -p "$drive_root/executed_notebooks"
  for notebook in "${NOTEBOOKS[@]}"; do
    echo "Executing ${notebook} with root ${drive_root}"
    MFAR_CODE_ROOT="$REPO_ROOT" \
    MFAR_GDRIVE_ROOT="$drive_root" \
    PYTHONPATH="$REPO_ROOT" \
      jupyter nbconvert --to notebook --execute \
        "$notebook_root/$notebook" \
        --output "$notebook" \
        --output-dir "$drive_root/executed_notebooks" \
        --ExecutePreprocessor.timeout=-1 \
        --ExecutePreprocessor.kernel_name=python3
  done
}

run_notebooks "$REPO_ROOT/notebooks" "$CURRENT_ROOT"

mkdir -p /tmp/prompt1_legacy/notebooks
for notebook in "${NOTEBOOKS[@]}"; do
  git -C "$REPO_ROOT" show "${LEGACY_SHA}:notebooks/${notebook}" \
    > "/tmp/prompt1_legacy/notebooks/${notebook}"
done
run_notebooks /tmp/prompt1_legacy/notebooks "$LEGACY_ROOT"

python "$REPO_ROOT/tools/create_baseline_manifest.py" snapshot \
  --repo-root "$REPO_ROOT" \
  --drive-root "$CURRENT_ROOT" \
  --output-dir /tmp/prompt1_current_manifest \
  --baseline-sha "$LEGACY_SHA" \
  --branch refactor/prompt1-stage01-02

set +e
python "$REPO_ROOT/tools/verify_prompt1_ab_equivalence.py" \
  --current-root "$CURRENT_ROOT" \
  --legacy-root "$LEGACY_ROOT" \
  --archival-baseline "$REPO_ROOT/validation/baseline/baseline_manifest.json" \
  --current-manifest /tmp/prompt1_current_manifest/baseline_manifest.json \
  --output /tmp/prompt1_ab_equivalence_report.json \
  --markdown "$REPO_ROOT/validation/prompt1/PROMPT_1_ACCEPTANCE.md" \
  --tolerance 1e-12
status=$?
set -e

cat /tmp/prompt1_ab_equivalence_report.json
exit "$status"
