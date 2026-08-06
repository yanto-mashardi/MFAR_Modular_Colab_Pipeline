# Prompt 0 Acceptance Record

## Final status

**PASS — Prompt 0 completed and independently verified through GitHub Actions.**

- Scientific baseline commit: `125725c10081c4b3511ffc5aaf1b8e0836434bd8`
- Revision branch: `revision/q1-logic-mfar`
- Verified revision commit: `b8e88cc0c36221d24464dbec35a7e1c8e2a4b25a`
- Successful workflow run: `31058246618`
- Successful workflow job: `92480368940`
- Workflow completion: `2026-08-06T00:04:59Z`
- Uploaded evidence artifact: `mfar-baseline-reproducibility`
- Artifact ID: `8951178953`
- Artifact ZIP SHA-256: `710351b7055fca5446477e005be94281651c99d9707b9ba5b268d2f2c97c79ec`

## Acceptance matrix

| Requirement | Status | Verification evidence |
|---|---|---|
| Create `revision/q1-logic-mfar` from `main` | PASS | Branch was created from scientific baseline commit `125725c10081c4b3511ffc5aaf1b8e0836434bd8` |
| Identify and freeze the scientific baseline commit | PASS | Commit is recorded in the manifest, documentation, Colab controller, and workflow |
| Preserve `main` | PASS | Prompt 0 changes were committed only to `revision/q1-logic-mfar` |
| Snapshot active scientific configuration | PASS | Six CSV files are stored under `validation/baseline/config_snapshot/` |
| Verify configuration snapshot equality | PASS | Manifest utility compares active and snapshot SHA-256 values and exits nonzero on mismatch |
| Provide a baseline manifest generator | PASS | `tools/create_baseline_manifest.py` |
| Record code revision and runtime | PASS | Commit SHA, branch, Python, platform, and package versions are stored in each run manifest |
| Record input/configuration/output checksums | PASS | SHA-256 evidence is stored for raw inputs, active configuration, snapshot configuration, and outputs |
| Record row counts and principal Stage 01–07 metrics | PASS | `baseline_manifest.json` and `baseline_metrics.csv` |
| Freeze a compatible baseline environment | PASS | `requirements-baseline.txt`; complete `pip freeze` is retained per run |
| Preserve separate Stage 01–07 notebooks | PASS | Existing scientific notebooks remain unchanged and are executed sequentially through `nbconvert` |
| Preserve independent stage execution in Google Colab | PASS | Each Stage 01–07 notebook remains directly runnable; `00_Baseline_Reproduction.ipynb` is an optional controller |
| Prevent overwriting existing Drive outputs | PASS | Run A and Run B use isolated roots beneath `baseline_reproduction/` |
| Run the repository test suite | PASS | 13 tests completed successfully |
| Download and verify the two raw inputs | PASS | Both connected-Drive files were downloaded successfully before execution |
| Execute complete Stage 01–07 pipeline twice | PASS | Run A and Run B both completed all seven stages |
| Compare row counts and key metrics | PASS | Repeatability comparison completed successfully with tolerance `1e-12` |
| Compare canonical output hashes | PASS | Comparison ran with `--require-canonical-hashes` and passed |
| Upload reproducibility evidence | PASS | GitHub Actions artifact uploaded successfully with 30-day retention |
| Confirm no scientific algorithm or active parameter change | PASS | Changes are restricted to reproducibility infrastructure, frozen dependency specification, tests, documentation, and exact configuration copies |

## Frozen existing-artifact funnel

| Object | Count |
|---|---:|
| Raw AIS rows | 32,358 |
| Accepted AIS rows | 32,245 |
| Rejected AIS rows | 113 |
| Accepted five-minute grid rows | 40,328 |
| Rejected candidate grid rows | 61,408 |
| Berth episodes | 1,986 |
| Decision cases | 703 |
| ETA validation pairs | 674 |
| Accepted recommendations | 252 |
| Queue-effect events | 165 |
| Day-terminal units | 62 |
| Scenario intervals | 12,648 |

## Principal frozen metrics

- ETA MAE: `16.817507418397625` minutes.
- ETA RMSE: `20.192416386485856` minutes.
- ETA bias: `12.915430267062314` minutes.
- Zero-coverage cases: `247`.
- Median daily queue-area reduction: `1.2214200426596555%`.
- Critical-duration change: `+205` minutes.

## Observed non-failing warnings

The completed run exposed two maintenance warnings that do not affect Prompt 0 acceptance:

1. Some existing notebook cells lack explicit `id` fields and trigger `MissingIDFieldWarning` in current `nbformat`.
2. `src/mfar_visuals.py` uses an `openpyxl` copy method that emits a deprecation warning.

These warnings are recorded for a later behavior-preserving refactor. Prompt 0 leaves the scientific notebooks and visualization logic unchanged.

The complete precision values, SHA-256 hashes, runtime records, and comparison result are stored in the baseline evidence files and the successful workflow artifact.
