# Prompt 4–10 Integrated Methodological Hardening

This branch is stacked on `method/prompt3-prospective-decision-epoch`. Prompt 3 prospective case generation and same-episode post-hoc validation remain unchanged. Prompts 4–10 change the interpretation, assessment, benchmarking, scenario simulation, and audit layers downstream of the prospective decision epoch.

## Prompt 4 — Forecast quality semantics

The previous confidence value multiplied two quantities that both inherited the AIS-gap penalty. It is replaced by a weighted data-quality index formed from four explicit components:

1. AIS continuity;
2. availability of completed trip history before the decision timestamp;
3. provenance of the turnaround prior;
4. completeness of the destination-berth projection.

The retained `forecast_confidence` column is a compatibility alias for `forecast_quality_index`. Its declared semantics are `DATA_QUALITY_INDEX_NOT_CALIBRATED_PROBABILITY`. It must not be described as a calibrated probability of forecast correctness.

## Prompt 5 — Fuzzy coverage and assessment status

Missing inputs are preserved as missing evidence. Membership coverage is audited on the observed domain and on a dense boundary grid. Four low-weight fallback rules cover the origin-queue partition while remaining below the operational recommendation threshold. Cases are explicitly classified as:

- `ASSESSED`;
- `UNASSESSED_INCOMPLETE_INPUT`;
- `UNASSESSED_NO_RULE_COVERAGE`.

`NO_INTERVENTION` is no longer used as a silent substitute for a case that could not be assessed.

## Prompt 6 — Berth gate and monotonic operational alert

Berth availability is a deterministic logical gate derived from the projected berth-slot ledger. Waiting time is the nonnegative difference between projected berth availability and ETA. A result of zero waiting time is reported as support observed in this dataset; positive variation is never manufactured.

The Mamdani centroid is retained as a diagnostic trace. Operational ordering uses a separately declared monotonic alert score whose adverse components are origin queue, berth unavailability, predicted wait, low forecast quality, service gap, and capacity shortfall. Fuzzy decisions are compared against a crisp threshold benchmark.

## Prompt 7 — ETA benchmark and uncertainty

ETA performance is compared against a fixed-duration baseline. A prospective online bias correction uses only completed arrivals known before each decision timestamp. Prediction intervals are formed from earlier absolute residuals after the configured minimum history is available. Outputs report MAE, skill against the fixed baseline, nominal interval coverage, and empirical interval coverage.

## Prompt 8 — Queue-conserving scenario simulator

The scenario simulator applies explicit service-capacity changes. Actual service equals the minimum of available service capacity and current demand. Every interval records arrivals, service capacity, actual service, unused capacity, queue state, and a mass-balance residual. Action costs are configured as normalized scenario units.

These are configured counterfactual scenarios. They are not field experiments and do not establish causal effects in observed operations.

## Prompt 9 — Sensitivity and robustness

The pipeline evaluates a 3 × 3 × 3 design across:

- recommendation-strength threshold;
- vehicle-arrival multiplier;
- action-effect multiplier.

Robustness outputs include action-set Jaccard similarity, queue-area changes, critical duration, and mass-balance residuals.

## Prompt 10 — Integrated audit and claim governance

The release bundle contains manuscript-ready metrics, claim-governance rules, blocking audits, disclosure-level limitations, and SHA-256 file hashes. Expert criterion validation is recorded as `NOT_AVAILABLE` until an expert-labeled decision dataset is supplied. No agreement-with-expert claim is admissible before that evidence exists.

## Methodological boundaries

Prompts 4–10 do not modify Stage 01 cleaning, Stage 02 interpolation, Stage 03 state/episode reconstruction, or Prompt 3 prospective case identity. All Stage 04–07 metrics are regenerated because confidence semantics, rule coverage, action selection, and scenario accounting have changed.
