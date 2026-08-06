#!/usr/bin/env python3
"""Verify Prompt 2 state and berth-episode methodological contracts."""
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
}


def rows(path: Path) -> int:
    return len(pd.read_csv(path, low_memory=False))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--drive-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown", type=Path, required=True)
    args = parser.parse_args()

    root = args.drive_root
    checks: list[dict] = []

    def check(name: str, passed: bool, actual=None, expected=None, detail: str = "") -> None:
        checks.append({
            "check": name,
            "status": "PASS" if bool(passed) else "FAIL",
            "actual": actual,
            "expected": expected,
            "detail": detail,
        })

    for relative, expected_rows in CANONICAL_ROWS.items():
        path = root / relative
        actual = rows(path) if path.is_file() else None
        check(f"unchanged_rows::{relative}", actual == expected_rows, actual, expected_rows)

    state2 = pd.read_csv(root / "stage_output/stage_02/02_vessel_interpolated_grid.csv", low_memory=False)
    state3 = pd.read_csv(root / "stage_output/stage_03/03_input_state_enhanced.csv", low_memory=False)
    episodes = pd.read_csv(root / "stage_output/stage_03/03_berth_episode_history.csv", low_memory=False)
    service = pd.read_csv(root / "stage_output/stage_03/03_service_call_history.csv", low_memory=False)
    audit = pd.read_csv(root / "stage_output/stage_03/03_berth_prediction_audit.csv", low_memory=False)
    forecast = pd.read_csv(root / "stage_output/stage_04/04_fuzzy_input.csv", low_memory=False)

    state3["grid_time"] = pd.to_datetime(state3["grid_time"], errors="coerce")
    episodes["berth_entry_time"] = pd.to_datetime(episodes["berth_entry_time"], errors="coerce")
    episodes["observed_end"] = pd.to_datetime(episodes["observed_end"], errors="coerce")
    eligible = episodes["eligible_for_turnaround_calibration"].astype(str).str.lower().isin(["true", "1"])
    left = episodes["left_censored"].astype(str).str.lower().isin(["true", "1"])
    right = episodes["right_censored"].astype(str).str.lower().isin(["true", "1"])

    check("stage3_preserves_stage2_row_domain", len(state3) == len(state2), len(state3), len(state2))
    check("unique_vessel_grid_time", not state3.duplicated(["mmsi", "grid_time"]).any(),
          int(state3.duplicated(["mmsi", "grid_time"]).sum()), 0)
    check("all_states_classified", state3["operational_status"].notna().all(),
          int(state3["operational_status"].isna().sum()), 0)
    check("direction_is_valid", not state3["origin"].eq(state3["destination"]).any(),
          int(state3["origin"].eq(state3["destination"]).sum()), 0)
    check("raw_state_is_preserved", "operational_status_stage2" in state3.columns)
    check("state_evidence_is_recorded", "state_evidence" in state3.columns)
    check("episode_internal_gap_limit", episodes["maximum_internal_gap_min"].fillna(0).le(7.5 + 1e-12).all(),
          float(episodes["maximum_internal_gap_min"].fillna(0).max()), "<=7.5")
    check("one_berth_per_episode", episodes["distinct_berths"].eq(1).all(),
          int(episodes["distinct_berths"].gt(1).sum()), 0)
    check("one_port_per_episode", episodes["distinct_ports"].eq(1).all(),
          int(episodes["distinct_ports"].gt(1).sum()), 0)
    check("eligible_episodes_have_complete_boundaries", not (eligible & (left | right)).any(),
          int((eligible & (left | right)).sum()), 0)
    check("eligible_duration_lower_bound", episodes.loc[eligible, "observed_berth_occupancy_min"].ge(10).all(),
          float(episodes.loc[eligible, "observed_berth_occupancy_min"].min()) if eligible.any() else None, ">=10")
    check("eligible_duration_upper_bound", episodes.loc[eligible, "observed_berth_occupancy_min"].le(180).all(),
          float(episodes.loc[eligible, "observed_berth_occupancy_min"].max()) if eligible.any() else None, "<=180")
    check("service_history_matches_quality_gate", len(service) == int(eligible.sum()), len(service), int(eligible.sum()))
    check("service_history_nonempty", len(service) > 0, len(service), ">0")

    if "severity" in audit.columns:
        blocking = audit[audit["severity"].astype(str).str.upper().eq("ERROR")]
    else:
        blocking = audit[~audit["check"].eq("berth_overlap_conflict_rows")]
    check("blocking_stage3_audit", pd.to_numeric(blocking["failed_rows"], errors="coerce").fillna(0).sum() == 0,
          int(pd.to_numeric(blocking["failed_rows"], errors="coerce").fillna(0).sum()), 0)
    check("stage4_completed_with_corrected_service_calls", len(forecast) > 0, len(forecast), ">0")
    check("stage7_completed", (root / "stage_output/stage_07/07_overall_scenario_evaluation.csv").is_file())

    class_counts = episodes["episode_class"].value_counts(dropna=False).to_dict()
    status_counts = state3["operational_status"].value_counts(dropna=False).to_dict()
    changed_states = int(
        state3["operational_status"].astype(str).ne(state3["operational_status_stage2"].astype(str)).sum()
    )
    report = {
        "schema_version": "1.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if all(item["status"] == "PASS" for item in checks) else "FAIL",
        "checks": checks,
        "diagnostics": {
            "state_rows": len(state3),
            "state_rows_changed_from_stage2_label": changed_states,
            "state_change_rate": changed_states / max(len(state3), 1),
            "state_counts": status_counts,
            "all_episodes": len(episodes),
            "eligible_service_calls": int(eligible.sum()),
            "excluded_episodes": int((~eligible).sum()),
            "episode_class_counts": class_counts,
            "maximum_all_episode_duration_min": float(episodes["observed_berth_occupancy_min"].max()),
            "maximum_eligible_duration_min": float(episodes.loc[eligible, "observed_berth_occupancy_min"].max()) if eligible.any() else None,
            "stage4_forecast_rows": len(forecast),
        },
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    lines = [
        "# Prompt 2 Acceptance Record",
        "",
        f"- Overall status: **{report['status']}**",
        f"- State rows: {len(state3):,}",
        f"- State labels changed from Stage 02 instantaneous labels: {changed_states:,}",
        f"- Reconstructed berth episodes: {len(episodes):,}",
        f"- Quality-gated service calls: {int(eligible.sum()):,}",
        f"- Excluded or censored episodes: {int((~eligible).sum()):,}",
        "",
        "| Check | Status | Actual | Expected |",
        "|---|---:|---:|---:|",
    ]
    for item in checks:
        lines.append(
            f"| `{item['check']}` | {item['status']} | {item.get('actual', '')} | {item.get('expected', '')} |"
        )
    lines.extend(["", "## Episode classes", ""])
    for name, count in class_counts.items():
        lines.append(f"- `{name}`: {count}")
    lines.extend([
        "",
        "## Methodological boundary",
        "",
        "Prompt 2 intentionally changes Stage 03 state labels and berth-episode membership. "
        "Stage 01–02 row domains remain fixed. Censored, short-contact, extended-stay, multi-berth, "
        "multi-port, and discontinuous episodes are prohibited from turnaround calibration and from the Stage 04 service-call history.",
    ])
    args.markdown.parent.mkdir(parents=True, exist_ok=True)
    args.markdown.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
