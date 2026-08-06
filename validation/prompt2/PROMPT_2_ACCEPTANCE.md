# Prompt 2 Acceptance Record

- Overall status: **PASS**
- State rows: 40,328
- State labels changed from Stage 02 instantaneous labels: 279
- Reconstructed berth episodes: 2,121
- Quality-gated service calls: 1,710
- Excluded or censored episodes: 411

| Check | Status | Actual | Expected |
|---|---:|---:|---:|
| `unchanged_rows::stage_output/stage_01/01_ais_clean.csv` | PASS | 32245 | 32245 |
| `unchanged_rows::stage_output/stage_01/01_ais_rejected.csv` | PASS | 113 | 113 |
| `unchanged_rows::stage_output/stage_02/02_vessel_interpolated_grid.csv` | PASS | 40328 | 40328 |
| `unchanged_rows::stage_output/stage_02/02_interpolation_rejected_grid.csv` | PASS | 61408 | 61408 |
| `stage3_preserves_stage2_row_domain` | PASS | 40328 | 40328 |
| `unique_vessel_grid_time` | PASS | 0 | 0 |
| `all_states_classified` | PASS | 0 | 0 |
| `direction_is_valid` | PASS | 0 | 0 |
| `raw_state_is_preserved` | PASS | None | None |
| `state_evidence_is_recorded` | PASS | None | None |
| `episode_internal_gap_limit` | PASS | 5.0 | <=7.5 |
| `one_berth_per_episode` | PASS | 0 | 0 |
| `one_port_per_episode` | PASS | 0 | 0 |
| `eligible_episodes_have_complete_boundaries` | PASS | 0 | 0 |
| `eligible_duration_lower_bound` | PASS | 10.0 | >=10 |
| `eligible_duration_upper_bound` | PASS | 145.0 | <=180 |
| `service_history_matches_quality_gate` | PASS | 1710 | 1710 |
| `service_history_nonempty` | PASS | 1710 | >0 |
| `blocking_stage3_audit` | PASS | 0 | 0 |
| `stage4_completed_with_corrected_service_calls` | PASS | 704 | >0 |
| `stage7_completed` | PASS | None | None |

## Episode classes

- `COMPLETE_SERVICE_CALL`: 1710
- `DATA_GAP_CENSORED`: 301
- `RIGHT_CENSORED`: 37
- `LEFT_CENSORED`: 36
- `SHORT_CONTACT`: 29
- `BOTH_CENSORED`: 5
- `EXTENDED_STAY`: 3

## Methodological boundary

Prompt 2 intentionally changes Stage 03 state labels and berth-episode membership. Stage 01–02 row domains remain fixed. Censored, short-contact, extended-stay, multi-berth, multi-port, and discontinuous episodes are prohibited from turnaround calibration and from the Stage 04 service-call history.

## Workflow evidence

- Workflow run: 31064694111
- Source commit: 29b4d17fea45ac16b5922d05b04dc9441c30962a
- Branch: method/prompt2-state-berth-episodes
- Unit tests and complete Stage 01-07 execution: PASS
