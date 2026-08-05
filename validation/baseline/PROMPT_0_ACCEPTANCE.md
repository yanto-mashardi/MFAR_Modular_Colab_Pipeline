# Prompt 0 Acceptance Record

## Frozen baseline

| Requirement | Status | Evidence |
|---|---|---|
| Create `revision/q1-logic-mfar` from `main` | PASS | Branch starts from baseline commit `125725c10081c4b3511ffc5aaf1b8e0836434bd8` |
| Identify baseline commit | PASS | Commit recorded in manifest and reproduction documentation |
| Snapshot active scientific configuration | PASS | Six CSV files in `config_snapshot/`; hashes are checked against `config/` |
| Provide manifest generator | PASS | `tools/create_baseline_manifest.py` |
| Record code, runtime, package, input, config, output, row-count, and metric evidence | PASS | Manifest schema `1.0` |
| Preserve separate Stage 01–07 notebooks | PASS | Existing notebooks are unchanged; reproduction controller executes them in order |
| Preserve Google Colab execution | PASS | `notebooks/00_Baseline_Reproduction.ipynb` |
| Prevent overwrite of existing outputs | PASS | Two isolated baseline run roots are used |
| Run repository unit tests | AUTOMATED | Executed in the Colab controller and GitHub Actions workflow |
| Execute complete pipeline twice | AUTOMATED | Run A and Run B in isolated roots |
| Compare row counts and key metrics | AUTOMATED | `repeatability_report.json` |
| Compare canonical CSV hashes | AUTOMATED | Comparison uses `--require-canonical-hashes` |
| Confirm no scientific code or parameter change | PASS | Branch diff is limited to reproducibility files and configuration copies |

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

## Principal frozen metrics

- ETA MAE: `16.8175074184` minutes.
- ETA RMSE: `20.1924163865` minutes.
- ETA bias: `12.9154302671` minutes.
- Zero-coverage cases: `247`.
- Median daily queue-area reduction: `1.2214200427%`.
- Critical-duration change: `+205` minutes.

The full precision values and SHA-256 hashes are stored in `baseline_manifest.json` and `baseline_metrics.csv`.
