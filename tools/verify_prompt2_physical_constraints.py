#!/usr/bin/env python3
"""Verify finite causal priors and physically unique berth occupancy."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--drive-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    stage3 = args.drive_root / "stage_output" / "stage_03"
    state = pd.read_csv(stage3 / "03_input_state_enhanced.csv", low_memory=False)
    audit = pd.read_csv(stage3 / "03_berth_prediction_audit.csv")
    state["grid_time"] = pd.to_datetime(state["grid_time"], errors="coerce")
    at_berth = state[state["is_at_berth"].astype(str).str.lower().isin(["true", "1"])].copy()

    duplicate_berth_time = int(
        at_berth.duplicated(["grid_time", "current_berth_id"], keep=False).sum()
    )
    duplicate_vessel_time = int(state.duplicated(["grid_time", "mmsi"]).sum())
    turnaround = pd.to_numeric(state["turnaround_estimate_min"], errors="coerce")
    nonfinite_turnaround = int((~np.isfinite(turnaround)).sum())
    nonpositive_turnaround = int(turnaround.le(0).sum())
    audit_overlap = int(
        pd.to_numeric(
            audit.loc[audit["check"].eq("berth_overlap_conflict_rows"), "failed_rows"],
            errors="coerce",
        ).fillna(0).sum()
    )

    checks = {
        "unique_vessel_grid_time": duplicate_vessel_time,
        "unique_physical_berth_grid_time": duplicate_berth_time,
        "audit_berth_overlap_conflict_rows": audit_overlap,
        "nonfinite_turnaround_prior_rows": nonfinite_turnaround,
        "nonpositive_turnaround_prior_rows": nonpositive_turnaround,
    }
    status = "PASS" if all(value == 0 for value in checks.values()) else "FAIL"
    report = {
        "status": status,
        "checks": checks,
        "at_berth_rows": len(at_berth),
        "reassigned_rows": int(
            state.get("berth_assignment_method", pd.Series(dtype="object"))
            .astype(str).eq("UNIQUE_MATCH_REASSIGNED").sum()
        ),
        "capacity_conflict_demotions": int(
            state.get("berth_assignment_method", pd.Series(dtype="object"))
            .astype(str).eq("UNASSIGNED_CAPACITY_CONFLICT").sum()
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
