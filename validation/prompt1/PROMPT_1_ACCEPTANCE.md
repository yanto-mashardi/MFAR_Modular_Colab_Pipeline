# Prompt 1 Acceptance Record

- Controlled legacy-versus-refactor equivalence: **PASS**
- Archival row-count equivalence: **PASS**
- Archival key-metric equivalence: **PASS**
- Archival byte-hash diagnostic: **DIFF** (non-blocking)
- Acceptance criterion: exact rows and SHA-256 for legacy versus refactor under one controlled runtime

| Artifact | A/B rows | A/B SHA-256 | Archive rows | Archive SHA diagnostic |
|---|---:|---:|---:|---:|
| `stage_output/stage_01/01_ais_clean.csv` | PASS | PASS | PASS | PASS |
| `stage_output/stage_01/01_ais_rejected.csv` | PASS | PASS | PASS | PASS |
| `stage_output/stage_02/02_vessel_interpolated_grid.csv` | PASS | PASS | PASS | DIFF |
| `stage_output/stage_02/02_interpolation_rejected_grid.csv` | PASS | PASS | PASS | PASS |
| `stage_output/stage_03/03_input_state_enhanced.csv` | PASS | PASS | PASS | DIFF |
| `stage_output/stage_03/03_berth_episode_history.csv` | PASS | PASS | PASS | PASS |
| `stage_output/stage_04/04_fuzzy_input.csv` | PASS | PASS | PASS | DIFF |
| `stage_output/stage_04/04_temporal_holdout_validation.csv` | PASS | PASS | PASS | DIFF |
| `stage_output/stage_05/05_fuzzy_memberships.csv` | PASS | PASS | PASS | DIFF |
| `stage_output/stage_06/06_rule_evaluation.csv` | PASS | PASS | PASS | DIFF |
| `stage_output/stage_07/07_accepted_operational_recommendations.csv` | PASS | PASS | PASS | DIFF |
| `stage_output/stage_07/07_queue_service_intervention_events.csv` | PASS | PASS | PASS | DIFF |
| `stage_output/stage_07/07_daily_scenario_by_port.csv` | PASS | PASS | PASS | DIFF |
| `stage_output/stage_07/07_overall_scenario_evaluation.csv` | PASS | PASS | PASS | PASS |
| `stage_output/stage_07/07_scenario_baseline_vs_actions.csv` | PASS | PASS | PASS | DIFF |

## Interpretation boundary

The Prompt 0 archive is named `MFAR_V1_RETROSPECTIVE_EXISTING_DRIVE_ARTIFACTS`. Its metadata states that the original package versions used to create those Drive artifacts were not stored. Consequently, archival CSV byte hashes are retained for provenance and serialization diagnosis, while behavior preservation is tested by paired execution of the fixed legacy commit and refactored branch in the same runtime.

Scientific parameters, thresholds, equations, filters, state definitions, rule base, and Stage 03–07 contracts were not changed.

## Workflow evidence

- Workflow run: 31062823572
- Source commit: df9d0a8ade98ca50b65d90f61351ea792bb24dfe
- Branch: refactor/prompt1-stage01-02
- Nineteen unit tests: PASS
- Separate Stage 01–07 execution for legacy and refactor: PASS
- Notebook cell-ID maintenance check: PASS
- Deprecated openpyxl style-copy maintenance check: PASS
