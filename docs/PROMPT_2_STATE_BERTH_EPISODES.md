# Prompt 2 — Corrected Operational States and Berth Episodes

## Scope

Prompt 2 is an intentional methodological revision of Stage 03 and its Stage 04 input contract. Stage 01–02 transformations remain unchanged. The revision addresses instantaneous state oscillation, episode bridging across AIS gaps, berth-overlap conflicts, censored berth stays, implausibly long turnaround observations, and missing turnaround priors in downstream decision states.

## Corrected state reconstruction

Stage 02 geometric classifications are retained in explicit audit columns. Stage 03 reconstructs operational states causally using:

- vessel-specific temporal sequences;
- a continuity limit of 7.5 minutes for the five-minute grid;
- entry evidence from berth radius and stopped speed;
- berth-exit hysteresis using a larger exit radius and speed threshold;
- approach and departure evidence from terminal-distance trends;
- trip-direction memory during sailing;
- a recorded evidence source and transition flag for each state.

The corrected state labels are:

- `AT_BERTH_<PORT>`;
- `DEPARTING_<PORT>`;
- `SAILING`;
- `APPROACHING_<PORT>`.

## Physical berth assignment

Each configured berth can be assigned to at most one vessel at a grid time. When berth-radius candidates overlap, Stage 03 maximizes the number of feasible assignments and then minimizes a continuity-aware distance cost. The original Stage 02 nearest-berth evidence is preserved.

Assignment audit fields are:

- `nearest_berth_id_stage2`;
- `nearest_distance_nm_stage2`;
- `nearest_berth_radius_nm_stage2`;
- `berth_assignment_selected`;
- `berth_assignment_conflict`;
- `berth_assignment_method`.

The methods are `STAGE2_NEAREST`, `UNIQUE_MATCH_NEAREST`, `UNIQUE_MATCH_REASSIGNED`, and `UNASSIGNED_CAPACITY_CONFLICT`.

## Berth-episode reconstruction

An episode starts when a vessel enters a berth state and is split when any of the following occurs:

- a temporal sequence break;
- a berth identifier change;
- a terminal change;
- a transition out of the berth state.

The reconstruction records observed entry and exit boundaries, start and end reasons, internal gaps, distinct berth and port counts, data partition, and turnaround-estimate provenance.

Episode classes are:

- `COMPLETE_SERVICE_CALL`;
- `DATA_GAP_CENSORED`;
- `LEFT_CENSORED`;
- `RIGHT_CENSORED`;
- `BOTH_CENSORED`;
- `SHORT_CONTACT`;
- `EXTENDED_STAY`;
- `INVALID_BOUNDARY` when a residual invalid condition is encountered.

## Turnaround calibration gate

An episode enters `03_service_call_history.csv` only when it has complete observed boundaries, one berth, one terminal, sufficient points, acceptable interpolation quality, no internal continuity violation, and an observed duration from 10 to 180 minutes. Holdout episodes do not update calibration distributions.

Turnaround estimates use a causal hierarchy. Calibration-period states use prior observations available at that time. Holdout states use calibration-only vessel-port, vessel, port, or global medians. Before the first available estimate, the configured fallback is used. The estimate is propagated forward within a vessel sequence; later observations are never backfilled into earlier states.

The 10–180 minute limits are current design gates. They require sensitivity analysis and operational validation before being treated as empirically established service limits.

## Outputs

Stage 03 now writes:

- `03_input_state_enhanced.csv`;
- `03_berth_episode_history.csv`;
- `03_service_call_history.csv`;
- `03_vessel_empirical_profiles.csv`;
- `03_berth_occupancy_timeline.csv`;
- `03_berth_episode_class_summary.csv`;
- `03_state_transition_summary.csv`;
- `03_predicted_berth_release_state.csv`;
- `03_berth_prediction_audit.csv`.

Stage 04 reads `03_service_call_history.csv`; censored, short-contact, extended-stay, discontinuous, multi-berth, and multi-port episodes cannot become trip-history or arrival targets.

## Verified results

Workflow `31065390306` executed Stage 01–07 independently and passed all unit, physical, and methodological checks.

- Stage 01–02 row domains remained fixed.
- Stage 03 retained 40,328 state rows.
- 294 instantaneous Stage 02 labels were revised by sequence-aware inference.
- 2,084 berth episodes were reconstructed.
- 1,734 complete service calls passed the calibration gate.
- 350 episodes were excluded or classified as censored.
- 511 rows were reassigned to a physically distinct configured berth.
- Two excess candidates were demoted by the two-berth capacity constraint.
- Duplicate vessel-time rows: 0.
- Duplicate physical berth-time occupancy: 0.
- Nonfinite or nonpositive turnaround priors: 0.
- Blocking Stage 03 audit failures: 0.
- Stage 04 completed with 696 corrected service-call decision cases.
- Stage 07 completed successfully.

The excluded set comprises 302 data-gap-censored episodes, 27 short contacts, nine right-censored episodes, eight left-censored episodes, three extended stays, and one both-censored episode.

## Interpretation boundary

The revision establishes computational and logical consistency for state and episode reconstruction. It does not establish field-valid berth identity for every reassigned row. The 511 reassigned rows, approximately 1.27% of the state grid, indicate that overlapping berth radii materially affected the previous nearest-berth logic. Map-based and operator-record validation should sample these rows, with priority given to the two capacity-conflict demotions.

All Stage 03–07 tables and manuscript results must be regenerated because Prompt 2 intentionally changes episode membership and downstream decision cases. The confidence-index double counting, fuzzy-rule coverage, nonmonotonic memberships, simulator calibration, and retrospective decision epoch remain outside Prompt 2.
