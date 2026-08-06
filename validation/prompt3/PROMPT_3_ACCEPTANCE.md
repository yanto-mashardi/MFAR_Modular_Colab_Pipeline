# Prompt 3 Acceptance Record

- Overall status: **PASS**
- Prospective decision cases: 543
- Post-hoc matched departures: 523
- Unmatched cases retained: 20
- ETA validation cases: 480

| Check | Status | Actual | Expected |
|---|---:|---:|---:|
| `unchanged_rows::stage_output/stage_01/01_ais_clean.csv` | PASS | 32245 | 32245 |
| `unchanged_rows::stage_output/stage_01/01_ais_rejected.csv` | PASS | 113 | 113 |
| `unchanged_rows::stage_output/stage_02/02_vessel_interpolated_grid.csv` | PASS | 40328 | 40328 |
| `unchanged_rows::stage_output/stage_02/02_interpolation_rejected_grid.csv` | PASS | 61408 | 61408 |
| `unchanged_rows::stage_output/stage_03/03_input_state_enhanced.csv` | PASS | 40328 | 40328 |
| `prospective_cases_nonempty` | PASS | 543 | >0 |
| `raw_epoch_count_matches_forecast` | PASS | 543 | 543 |
| `all_epochs_are_prospective` | PASS | 0 | 0 |
| `one_decision_per_berth_episode` | PASS | 0 | 0 |
| `decision_epoch_on_five_minute_grid` | PASS | 0 | 0 |
| `decision_epoch_at_origin_berth` | PASS | 0 | 0 |
| `observed_departure_not_used_for_case_generation` | PASS | 0 | 0 |
| `observed_departure_not_used_in_eta` | PASS | 0 | 0 |
| `retrospective_reference_is_audit_only` | PASS | 0 | 0 |
| `matched_departure_occurs_after_decision` | PASS | 0 | 0 |
| `trip_history_is_known_at_decision` | PASS | 0 | 0 |
| `prospective_audit_has_no_failures` | PASS | 0 | 0 |
| `epoch_comparison_matches_posthoc_cases` | PASS | 543 | 543 |
| `stage5_completed` | PASS | None | None |
| `stage7_completed` | PASS | None | None |

## Epoch diagnostics

- Match rate: 96.32%
- Median decision-to-observed-departure lead: 20.0
- Median prospective-minus-retrospective epoch shift: -5.0
- Exact coincidences with `departure - horizon`: 76

## Methodological boundary

Decision cases are emitted by a fixed-grid scan of contemporaneous Stage 03 berth states. Observed departures and the retrospective reference timestamp are attached only after prediction. Unmatched prospective cases remain in the fuzzy-input population.

## Workflow evidence

- Workflow run: 31066520763
- Source commit: 43a61ff9e821066e9b6557d13785e9901197c133
- Branch: method/prompt3-prospective-decision-epoch
- Unit tests and complete Stage 01-07 execution: PASS
