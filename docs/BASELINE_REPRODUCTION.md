# MFAR V1 Baseline Reproduction

## Purpose

This package freezes the current **MFAR_V1_RETROSPECTIVE** implementation before any methodological revision. It records code, configuration, input, output, row-count, and metric evidence without changing the scientific algorithms or parameters.

- Repository: `yanto-mashardi/MFAR_Modular_Colab_Pipeline`
- Scientific baseline commit: `125725c10081c4b3511ffc5aaf1b8e0836434bd8`
- Revision branch: `revision/q1-logic-mfar`
- Scientific stages: separate notebooks `01` through `07`
- Primary runtime: Google Colab with the existing Google Drive input/output structure

## Clone the revision branch

```bash
git clone --branch revision/q1-logic-mfar --single-branch \
  https://github.com/yanto-mashardi/MFAR_Modular_Colab_Pipeline.git
cd MFAR_Modular_Colab_Pipeline
```

The original `main` branch remains unchanged. Methodological revisions must remain on the revision branch or its child branches until they pass the stated audits.

## Google Colab execution

Open `notebooks/00_Baseline_Reproduction.ipynb` in Google Colab and choose **Runtime → Run all**. The notebook performs the following actions:

1. mounts Google Drive;
2. clones or updates `revision/q1-logic-mfar`;
3. installs the repository requirements;
4. runs the existing unit tests;
5. copies the two raw input files into two isolated baseline run directories;
6. executes notebooks `01`–`07` in their existing order for Run A and Run B;
7. creates a manifest and metrics file for each run;
8. compares row counts, metrics, and canonical CSV hashes.

The seven scientific stages remain independently executable. The controller calls each notebook through `nbconvert`; it does not merge stage logic into one notebook.

## Isolated output structure

The path resolver requires the active I/O root to retain the exact folder name `In_Out_MFAR_Modular_Colab_Pipeline`. The reproduction controller therefore writes to the following structure and does not overwrite the current `stage_output` directory:

```text
In_Out_MFAR_Modular_Colab_Pipeline/
└── baseline_reproduction/
    └── 125725c10081c4b3511ffc5aaf1b8e0836434bd8/
        ├── run_a/
        │   └── In_Out_MFAR_Modular_Colab_Pipeline/
        │       ├── data_raw/
        │       ├── stage_output/stage_01 ... stage_07/
        │       ├── executed_notebooks/
        │       └── baseline_evidence/
        ├── run_b/
        │   └── In_Out_MFAR_Modular_Colab_Pipeline/
        │       └── ...
        └── repeatability_report.json
```

Each stage can also be run separately by setting `MFAR_CODE_ROOT` to the cloned repository and `MFAR_GDRIVE_ROOT` to the exact-name run root before opening the corresponding notebook.

## Baseline evidence in the repository

- `validation/baseline/baseline_manifest.json`: frozen evidence from the existing connected-Drive artifacts.
- `validation/baseline/baseline_metrics.csv`: row counts and principal Stage `01`–`07` metrics.
- `validation/baseline/config_snapshot/`: exact copy of all active scientific configuration files.
- `tools/create_baseline_manifest.py`: read-only manifest and repeatability utility.
- `validation/baseline/PROMPT_0_ACCEPTANCE.md`: acceptance checklist and evidence references.

The committed manifest records the environment used to inspect and hash existing artifacts. The original Colab package versions were not stored in the earlier stage metadata. Fresh Run A and Run B manifests record their own Python and package versions.

## Command-line use

Create a manifest after a complete run:

```bash
python tools/create_baseline_manifest.py snapshot \
  --repo-root . \
  --drive-root /path/to/run_a/In_Out_MFAR_Modular_Colab_Pipeline \
  --output-dir /path/to/run_a/In_Out_MFAR_Modular_Colab_Pipeline/baseline_evidence \
  --baseline-sha 125725c10081c4b3511ffc5aaf1b8e0836434bd8 \
  --branch revision/q1-logic-mfar
```

Compare two complete runs:

```bash
python tools/create_baseline_manifest.py compare \
  --first /path/to/run_a/In_Out_MFAR_Modular_Colab_Pipeline/baseline_evidence/baseline_manifest.json \
  --second /path/to/run_b/In_Out_MFAR_Modular_Colab_Pipeline/baseline_evidence/baseline_manifest.json \
  --output /path/to/repeatability_report.json \
  --require-canonical-hashes
```

A successful comparison requires identical commit SHA, input hashes, configuration hashes, canonical output row counts, canonical output hashes, and key metrics within the configured numeric tolerance.

## Scientific-change boundary

Prompt 0 adds reproducibility infrastructure only. It does not alter:

- AIS cleaning rules;
- interpolation equations;
- state and episode definitions;
- forecast equations;
- membership functions;
- fuzzy rules, weights, priorities, or phase constraints;
- policy threshold and cooldown;
- scenario equations or action effects.

Any later change to those elements must be identified as a methodological change and must generate a V1–V2 impact report.
