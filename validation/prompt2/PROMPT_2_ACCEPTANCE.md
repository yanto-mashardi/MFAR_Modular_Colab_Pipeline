# Prompt 2 Acceptance Record

- Overall status: **PASS**
- State rows: 40,328
- State labels changed from Stage 02 instantaneous labels: 294
- Reconstructed berth episodes: 2,084
- Quality-gated service calls: 1,734
- Excluded or censored episodes: 350

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
| `service_history_matches_quality_gate` | PASS | 1734 | 1734 |
| `service_history_nonempty` | PASS | 1734 | >0 |
| `blocking_stage3_audit` | PASS | 0 | 0 |
| `stage4_completed_with_corrected_service_calls` | PASS | 696 | >0 |
| `stage7_completed` | PASS | None | None |

## Episode classes

- `COMPLETE_SERVICE_CALL`: 1734
- `DATA_GAP_CENSORED`: 302
- `SHORT_CONTACT`: 27
- `RIGHT_CENSORED`: 9
- `LEFT_CENSORED`: 8
- `EXTENDED_STAY`: 3
- `BOTH_CENSORED`: 1

## Methodological boundary

Prompt 2 intentionally changes Stage 03 state labels and berth-episode membership. Stage 01–02 row domains remain fixed. Censored, short-contact, extended-stay, multi-berth, multi-port, and discontinuous episodes are prohibited from turnaround calibration and from the Stage 04 service-call history.

## Physical berth and causal-prior evidence

- Unique berth occupancy: **PASS**
- Reassigned berth rows: 511
- Capacity-conflict demotions: 2
- `unique_vessel_grid_time`: 0
- `unique_physical_berth_grid_time`: 0
- `audit_berth_overlap_conflict_rows`: 0
- `nonfinite_turnaround_prior_rows`: 0
- `nonpositive_turnaround_prior_rows`: 0

## Workflow evidence

- Workflow run: 31065123426
- Source commit: 0ad59761ab72cb3345ed527c6b16a533ce6833c0
- Branch: method/prompt2-state-berth-episodes
- Unit tests and complete Stage 01-07 execution: PASS
