#!/usr/bin/env python3
"""Verify Prompt 3 prospective decision-epoch contracts."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

CANONICAL_ROWS = {
    "stage_output/stage_01/01_ais_clean.csv": 32245,
    "stage_output/stage_01/01_ais_rejected.csv": 113,
    "stage_output/stage_02/02_vessel_interpolated_grid.csv": 40328,
    "stage_output/stage_02/02_interpolation_rejected_grid.csv": 61408,
    "stage_output/stage_03/03_input_state_enhanced.csv": 40328,
}
FUTURE_EPISODE_OUTCOMES = {
    "episode_class",
    "eligible_for_turnaround_calibration",
    "entry_observed",
    "exit_observed",
}


def _bool(series: pd.Series) -> pd.Series:
    return series.astype(str).str.lower().isin(["true", "1"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--drive-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown", type=Path, required=True)
    args = parser.parse_args()
    root = args.drive_root
    checks: list[dict] = []

    def check(name: str, passed: bool, actual=None, expected=None) -> None:
        checks.append({"check": name, "status": "PASS" if bool(passed) else "FAIL",
                       "actual": actual, "expected": expected})

    for relative, expected in CANONICAL_ROWS.items():
        path = root / relative
        actual = len(pd.read_csv(path, low_memory=False)) if path.is_file() else None
        check(f"unchanged_rows::{relative}", actual == expected, actual, expected)

    stage4 = root / "stage_output/stage_04"
    forecast = pd.read_csv(stage4 / "04_fuzzy_input.csv", low_memory=False)
    epochs = pd.read_csv(stage4 / "04_prospective_decision_epochs.csv", low_memory=False)
    comparison = pd.read_csv(stage4 / "04_epoch_comparison.csv", low_memory=False)
    audit = pd.read_csv(stage4 / "04_prospective_epoch_audit.csv", low_memory=False)
    summary = pd.read_csv(stage4 / "04_forecast_summary.csv", low_memory=False)
    for frame in [forecast, epochs, comparison]:
        for column in [
            "decision_time", "observed_departure_time",
            "retrospective_reference_decision_time", "episode_observed_release_time",
        ]:
            if column in frame:
                frame[column] = pd.to_datetime(frame[column], errors="coerce")

    check("prospective_cases_nonempty", len(forecast) > 0, len(forecast), ">0")
    check("raw_epoch_count_matches_forecast", len(epochs) == len(forecast), len(epochs), len(forecast))
    check("all_epochs_are_prospective",
          forecast["decision_epoch_mode"].eq("PROSPECTIVE_FIXED_GRID").all(),
          int(forecast["decision_epoch_mode"].ne("PROSPECTIVE_FIXED_GRID").sum()), 0)
    forbidden_epochs = sorted(FUTURE_EPISODE_OUTCOMES.intersection(epochs.columns))
    forbidden_forecast = sorted(FUTURE_EPISODE_OUTCOMES.intersection(forecast.columns))
    check("future_episode_outcomes_absent_from_raw_epochs",
          len(forbidden_epochs) == 0, ",".join(forbidden_epochs), "none")
    check("future_episode_outcomes_absent_from_fuzzy_input",
          len(forbidden_forecast) == 0, ",".join(forbidden_forecast), "none")
    bad_contract = int(
        forecast["prospective_feature_contract"].ne("CURRENT_STATE_ONLY").sum()
    )
    check("prospective_feature_contract_current_state_only", bad_contract == 0,
          bad_contract, 0)
    check("one_decision_per_berth_episode",
          not forecast.duplicated(["mmsi", "berth_episode_id"]).any(),
          int(forecast.duplicated(["mmsi", "berth_episode_id"]).sum()), 0)
    aligned = (forecast["decision_time"].notna()
               & forecast["decision_time"].dt.second.eq(0)
               & forecast["decision_time"].dt.minute.mod(5).eq(0))
    check("decision_epoch_on_five_minute_grid", aligned.all(), int((~aligned).sum()), 0)
    berth_fail = int((~_bool(forecast["is_at_berth"])).sum()) + int(
        forecast["operational_phase"].ne("AT_ORIGIN_TERMINAL").sum())
    check("decision_epoch_at_origin_berth", berth_fail == 0, berth_fail, 0)
    check("observed_departure_not_used_for_case_generation",
          not _bool(forecast["observed_departure_used_to_generate_case"]).any(),
          int(_bool(forecast["observed_departure_used_to_generate_case"]).sum()), 0)
    check("observed_departure_not_used_in_eta",
          not _bool(forecast["observed_departure_used_in_eta"]).any(),
          int(_bool(forecast["observed_departure_used_in_eta"]).sum()), 0)
    check("retrospective_reference_is_audit_only",
          not _bool(forecast["retrospective_reference_used_for_prediction"]).any(),
          int(_bool(forecast["retrospective_reference_used_for_prediction"]).sum()), 0)

    matched = forecast["observed_departure_time"].notna()
    bad_order = int((forecast.loc[matched, "observed_departure_time"]
                     <= forecast.loc[matched, "decision_time"]).sum())
    check("matched_departure_occurs_after_decision", bad_order == 0, bad_order, 0)
    bad_match_label = int(
        forecast.loc[matched, "departure_match_status"]
        .ne("MATCHED_SAME_EPISODE_POSTHOC").sum()
    )
    check("matched_departure_is_same_episode_posthoc", bad_match_label == 0, bad_match_label, 0)
    missing_release = int(forecast.loc[matched, "episode_observed_release_time"].isna().sum())
    check("matched_case_has_episode_release_anchor", missing_release == 0, missing_release, 0)
    release_delta = pd.to_numeric(
        forecast.loc[matched, "departure_to_episode_release_min"], errors="coerce"
    )
    over_tolerance = int(release_delta.abs().gt(15.0 + 1e-9).sum())
    check("matched_departure_within_episode_release_tolerance", over_tolerance == 0,
          over_tolerance, 0)
    reused = int(forecast.loc[matched, "matched_departure_index"].duplicated().sum())
    check("matched_departure_not_reused", reused == 0, reused, 0)

    history = pd.to_datetime(forecast["trip_history_latest_time"], errors="coerce")
    future_history = int((history.notna() & history.ge(forecast["decision_time"])).sum())
    check("trip_history_is_known_at_decision", future_history == 0, future_history, 0)
    audit_failures = int(pd.to_numeric(audit["failed_rows"], errors="coerce").fillna(0).sum())
    check("prospective_audit_has_no_failures", audit_failures == 0, audit_failures, 0)
    check("epoch_comparison_matches_posthoc_cases", len(comparison) == len(forecast),
          len(comparison), len(forecast))
    check("stage5_completed", (root / "stage_output/stage_05/05_fuzzy_memberships.csv").is_file())
    check("stage7_completed", (root / "stage_output/stage_07/07_overall_scenario_evaluation.csv").is_file())

    matched_count = int(matched.sum())
    unmatched_count = int((~matched).sum())
    coincidence = int((matched & forecast["decision_time"].eq(
        forecast["retrospective_reference_decision_time"])).sum())
    reason_counts = forecast["departure_match_reason"].value_counts(dropna=False).to_dict()
    maximum_release_delta = float(release_delta.abs().max()) if matched_count else None
    report = {
        "schema_version": "1.2",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if all(item["status"] == "PASS" for item in checks) else "FAIL",
        "checks": checks,
        "diagnostics": {
            "prospective_cases": len(forecast),
            "matched_departures": matched_count,
            "unmatched_cases_retained": unmatched_count,
            "posthoc_match_rate_percent": 100 * matched_count / max(len(forecast), 1),
            "eta_validation_cases": int(forecast["absolute_eta_error_min"].notna().sum()),
            "median_decision_to_departure_min": (
                float(forecast.loc[matched, "decision_to_observed_departure_min"].median())
                if matched_count else None),
            "median_epoch_shift_min": (
                float(forecast.loc[matched, "prospective_minus_retrospective_epoch_min"].median())
                if matched_count else None),
            "maximum_absolute_departure_to_episode_release_min": maximum_release_delta,
            "departure_match_reason_counts": reason_counts,
            "removed_future_episode_outcomes": sorted(FUTURE_EPISODE_OUTCOMES),
            "exact_retrospective_formula_coincidences": coincidence,
            "summary": dict(zip(summary["metric"], summary["value"])),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    lines = [
        "# Prompt 3 Acceptance Record", "",
        f"- Overall status: **{report['status']}**",
        f"- Prospective decision cases: {len(forecast):,}",
        f"- Same-episode post-hoc matches: {matched_count:,}",
        f"- Unmatched cases retained: {unmatched_count:,}",
        f"- ETA validation cases: {int(forecast['absolute_eta_error_min'].notna().sum()):,}",
        "", "| Check | Status | Actual | Expected |", "|---|---:|---:|---:|",
    ]
    for item in checks:
        lines.append(f"| `{item['check']}` | {item['status']} | {item.get('actual', '')} | {item.get('expected', '')} |")
    lines.extend([
        "", "## Epoch diagnostics", "",
        f"- Same-episode match rate: {100 * matched_count / max(len(forecast), 1):.2f}%",
        f"- Median decision-to-observed-departure lead: {report['diagnostics']['median_decision_to_departure_min']}",
        f"- Median prospective-minus-retrospective epoch shift: {report['diagnostics']['median_epoch_shift_min']}",
        f"- Maximum absolute departure-to-episode-release difference: {maximum_release_delta}",
        f"- Exact coincidences with `departure - horizon`: {coincidence}",
        "", "## Prospective feature contract", "",
        "- Current-state contract: `CURRENT_STATE_ONLY`",
        "- Removed future episode outcomes: `episode_class`, `eligible_for_turnaround_calibration`, `entry_observed`, `exit_observed`",
        "", "## Departure matching outcomes", "",
    ])
    for name, count in reason_counts.items():
        lines.append(f"- `{name}`: {count}")
    lines.extend([
        "", "## Methodological boundary", "",
        "Decision cases are emitted by a fixed-grid scan of contemporaneous Stage 03 berth states. "
        "Future episode outcomes are removed before forecast and fuzzy inference. "
        "Observed departures and the retrospective reference timestamp are attached only after prediction. "
        "A detected departure is valid for evaluation only when it is adjacent to the same quality-gated berth episode. "
        "Unmatched prospective cases remain in the fuzzy-input population.",
    ])
    args.markdown.parent.mkdir(parents=True, exist_ok=True)
    args.markdown.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
