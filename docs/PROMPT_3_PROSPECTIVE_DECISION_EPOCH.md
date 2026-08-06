# Prompt 3 — Prospective Decision Epoch

## Problem

The previous Stage 04 created each decision timestamp as the observed AIS departure minus a fixed lead. Although the observed departure was not inserted directly into the ETA formula, it determined whether and when a case existed. This is a retrospective oracle trigger and cannot be reproduced in live operation.

## Prospective trigger

Stage 04 now scans the corrected Stage 03 state table at a configured fixed interval. A case is emitted when all of the following are true:

1. the timestamp is inside the temporal holdout and operating window;
2. the vessel is currently `AT_ORIGIN_TERMINAL`;
3. a valid berth episode identifier is available;
4. the causal predicted berth release is available;
5. predicted release is within the configured decision horizon or is already overdue;
6. no decision has previously been emitted for that vessel–berth episode.

The default scan interval is five minutes and the default horizon is fifteen minutes. The first eligible scan is retained. Case generation does not accept an observed-departure table as an input.

## Prediction and validation separation

The prospective case is forecast first using information known at its decision timestamp:

- current corrected operational state;
- causal turnaround prior;
- predicted berth release;
- trip history whose destination arrival is earlier than the decision timestamp;
- queue state accumulated up to the decision timestamp;
- vessel capacity from the current state or vessel profile;
- contemporaneous destination-berth release estimates.

Observed AIS departures are detected afterwards. A departure is attached only when it belongs to the same vessel, origin terminal, and quality-gated berth episode, and lies within 15 minutes of that episode's observed release boundary. A later departure from a subsequent trip is rejected even when it falls within a broad future window. The retrospective timestamp `observed departure - horizon` is retained only in `04_epoch_comparison.csv`.

## Unmatched cases

A prospective system can issue a case even when the episode is excluded by the quality gate or no departure is detected near its observed release boundary. Such cases are retained as `UNMATCHED_RETAINED`. Deleting them would condition the decision sample on future outcomes.

Unmatched reasons are recorded as:

- `EPISODE_NOT_IN_QUALITY_GATED_HISTORY`;
- `EPISODE_RELEASE_UNAVAILABLE`;
- `NO_DEPARTURE_NEAR_SAME_EPISODE_RELEASE`.

## Primary outputs

- `04_prospective_decision_epochs.csv`
- `04_fuzzy_input.csv`
- `04_predeparture_forecast.csv`
- `04_epoch_comparison.csv`
- `04_unmatched_prospective_cases.csv`
- `04_prospective_epoch_audit.csv`
- `04_temporal_holdout_validation.csv`

## Audit requirements

A valid Prompt 3 run requires:

- one decision per vessel–berth episode;
- every decision on the configured scan grid;
- every decision generated while the vessel is at the origin terminal;
- no observed departure used for case generation or ETA prediction;
- no retrospective reference timestamp used for prediction;
- matched departures later than their decision timestamps;
- every matched departure anchored to the same berth episode;
- absolute departure-to-episode-release difference no greater than 15 minutes;
- no trip-history observation dated at or after the decision timestamp;
- no reuse of a matched departure across cases;
- full Stage 01–07 execution.

## Scientific boundary

This prompt corrects the temporal decision design and post-hoc validation identity. It does not recalibrate the confidence index, fuzzy memberships, rule coverage, action effects, or queue simulator. Those components must be evaluated in their respective prompts. All Stage 04–07 counts and performance metrics must be regenerated after this change.
