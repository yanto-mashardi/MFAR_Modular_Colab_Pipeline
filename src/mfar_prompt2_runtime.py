"""Runtime adapter for Prompt 2 Stage 03 outputs.

The adapter isolates three Stage 03 contracts:
1. one vessel may occupy a configured berth at a given grid time;
2. every downstream decision state receives a finite causal turnaround prior;
3. Plotly receives string MMSI values only in a temporary visualization copy.

No Stage 01–02 file is modified. Conflict-aware berth assignment is applied to
an in-memory Stage 03 copy using the precomputed berth-distance columns.
"""
from __future__ import annotations

from itertools import combinations, permutations
from pathlib import Path

import numpy as np
import pandas as pd

from . import mfar_state_episode as implementation
from .mfar_visuals import stage3_berth_outputs as original_stage3_berth_outputs


def _parameters(config_dir: Path) -> dict[str, float]:
    frame = pd.read_csv(Path(config_dir) / "pipeline_parameters.csv")
    return dict(zip(frame["parameter"], pd.to_numeric(frame["value"], errors="coerce")))


def _configured_turnaround(config_dir: Path) -> float:
    value = _parameters(config_dir).get("turnaround_min", 40.0)
    return float(value) if pd.notna(value) else 40.0


def _distance_column(berth_id: str) -> str:
    safe = str(berth_id).replace(" ", "_").replace("-", "_").replace("/", "_")
    return f"distance_to_{safe}_nm"


def _best_unique_assignment(
    row_indices: list[int],
    berth_ids: list[str],
    eligible: dict[tuple[int, str], bool],
    costs: dict[tuple[int, str], float],
) -> dict[int, str]:
    """Maximize assigned vessels, then minimize continuity-aware distance cost."""
    best: dict[int, str] = {}
    best_key = (0, float("inf"))
    maximum = min(len(row_indices), len(berth_ids))
    for count in range(1, maximum + 1):
        for selected_rows in combinations(row_indices, count):
            for selected_berths in combinations(berth_ids, count):
                for ordered_berths in permutations(selected_berths):
                    pairs = list(zip(selected_rows, ordered_berths))
                    if not all(eligible.get(pair, False) for pair in pairs):
                        continue
                    total_cost = float(sum(costs[pair] for pair in pairs))
                    key = (count, -total_cost)
                    if key > best_key:
                        best_key = key
                        best = {row: berth for row, berth in pairs}
    return best


def _enforce_unique_berth_assignment(state: pd.DataFrame, config_dir: Path) -> pd.DataFrame:
    """Resolve overlapping berth candidates with a one-to-one physical constraint."""
    out = state.copy()
    out["grid_time"] = pd.to_datetime(out["grid_time"], errors="coerce")
    out["mmsi"] = pd.to_numeric(out["mmsi"], errors="coerce").astype("Int64")
    out["sog"] = pd.to_numeric(out["sog"], errors="coerce")
    out = out.sort_values(["grid_time", "nearest_port_id", "mmsi"]).reset_index(drop=True)

    params = _parameters(config_dir)
    stopped_speed = float(params.get("state_stopped_speed_kn", 0.8))
    exit_speed = float(params.get("berth_exit_speed_kn", 1.2))
    exit_multiplier = float(params.get("berth_exit_radius_multiplier", 1.5))
    grid_min = float(params.get("grid_interval_min", 5.0))
    continuity_limit = grid_min * float(params.get("state_continuity_gap_factor", 1.5))

    berths = pd.read_csv(Path(config_dir) / "terminal_berths.csv")
    berths["port_id"] = berths["port_id"].astype(str).str.upper()
    berths["berth_id"] = berths["berth_id"].astype(str)
    berths["occupancy_radius_nm"] = pd.to_numeric(
        berths["occupancy_radius_nm"], errors="coerce"
    ).fillna(0.12)
    berth_lookup = berths.set_index("berth_id")

    out["nearest_berth_id_stage2"] = out["nearest_berth_id"].astype(str)
    out["nearest_distance_nm_stage2"] = pd.to_numeric(out["nearest_distance_nm"], errors="coerce")
    out["nearest_berth_radius_nm_stage2"] = pd.to_numeric(
        out["nearest_berth_radius_nm"], errors="coerce"
    )
    out["berth_assignment_selected"] = False
    out["berth_assignment_conflict"] = False
    out["berth_assignment_method"] = "STAGE2_NEAREST"

    previous_berth: dict[int, str | None] = {}
    previous_time: dict[int, pd.Timestamp] = {}

    for (grid_time, port), group in out.groupby(["grid_time", "nearest_port_id"], sort=True):
        port = str(port).upper()
        port_berths = berths.loc[berths["port_id"].eq(port), "berth_id"].tolist()
        if not port_berths:
            continue

        row_indices = list(group.index)
        eligible: dict[tuple[int, str], bool] = {}
        costs: dict[tuple[int, str], float] = {}
        candidate_rows: list[int] = []
        for idx in row_indices:
            mmsi = int(out.at[idx, "mmsi"])
            sog = out.at[idx, "sog"]
            prior = previous_berth.get(mmsi)
            prior_time = previous_time.get(mmsi)
            continuous = (
                prior_time is not None
                and pd.notna(grid_time)
                and 0 < (pd.Timestamp(grid_time) - pd.Timestamp(prior_time)).total_seconds() / 60 <= continuity_limit
            )
            row_has_candidate = False
            for berth_id in port_berths:
                distance_column = _distance_column(berth_id)
                distance = pd.to_numeric(
                    pd.Series([out.at[idx, distance_column] if distance_column in out else np.nan]),
                    errors="coerce",
                ).iloc[0]
                radius = float(berth_lookup.at[berth_id, "occupancy_radius_nm"])
                strong = pd.notna(distance) and pd.notna(sog) and distance <= radius and sog <= stopped_speed
                retained = (
                    prior == berth_id
                    and continuous
                    and pd.notna(distance)
                    and pd.notna(sog)
                    and distance <= radius * exit_multiplier
                    and sog <= exit_speed
                )
                allowed = bool(strong or retained)
                eligible[(idx, berth_id)] = allowed
                if allowed:
                    row_has_candidate = True
                    continuity_penalty = 0.0 if retained else radius * 2.0
                    costs[(idx, berth_id)] = float(distance) + continuity_penalty
            if row_has_candidate:
                candidate_rows.append(idx)

        assignments = _best_unique_assignment(candidate_rows, port_berths, eligible, costs)
        candidate_nearest = [
            str(out.at[idx, "nearest_berth_id_stage2"])
            for idx in candidate_rows
        ]
        duplicate_nearest = len(candidate_nearest) != len(set(candidate_nearest))

        for idx in candidate_rows:
            mmsi = int(out.at[idx, "mmsi"])
            selected = assignments.get(idx)
            if selected is None:
                out.at[idx, "nearest_berth_radius_nm"] = 0.0
                out.at[idx, "berth_assignment_conflict"] = True
                out.at[idx, "berth_assignment_method"] = "UNASSIGNED_CAPACITY_CONFLICT"
                previous_berth[mmsi] = None
                previous_time[mmsi] = pd.Timestamp(grid_time)
                continue

            distance_column = _distance_column(selected)
            out.at[idx, "nearest_berth_id"] = selected
            out.at[idx, "nearest_port_id"] = port
            out.at[idx, "nearest_distance_nm"] = float(out.at[idx, distance_column])
            out.at[idx, "nearest_berth_radius_nm"] = float(
                berth_lookup.at[selected, "occupancy_radius_nm"]
            )
            out.at[idx, "berth_assignment_selected"] = True
            changed = selected != str(out.at[idx, "nearest_berth_id_stage2"])
            out.at[idx, "berth_assignment_conflict"] = bool(changed or duplicate_nearest)
            out.at[idx, "berth_assignment_method"] = (
                "UNIQUE_MATCH_REASSIGNED" if changed else "UNIQUE_MATCH_NEAREST"
            )
            previous_berth[mmsi] = selected
            previous_time[mmsi] = pd.Timestamp(grid_time)

        candidate_mmsi = {int(out.at[idx, "mmsi"]) for idx in candidate_rows}
        for idx in row_indices:
            mmsi = int(out.at[idx, "mmsi"])
            if mmsi not in candidate_mmsi:
                previous_berth[mmsi] = None
                previous_time[mmsi] = pd.Timestamp(grid_time)

    return out.sort_values(["mmsi", "grid_time"]).reset_index(drop=True)


def _plotly_safe_stage3_outputs(state: pd.DataFrame, audit: pd.DataFrame, stage_dir: Path) -> None:
    visual_state = state.copy()
    if "mmsi" in visual_state.columns:
        visual_state["mmsi"] = visual_state["mmsi"].astype("string")
    original_stage3_berth_outputs(visual_state, audit, stage_dir)


def _propagate_causal_turnaround_prior(state: pd.DataFrame, fallback: float) -> pd.DataFrame:
    out = state.copy()
    out["grid_time"] = pd.to_datetime(out["grid_time"], errors="coerce")
    out = out.sort_values(["mmsi", "grid_time"]).reset_index(drop=True)

    estimate = pd.to_numeric(out.get("turnaround_estimate_min"), errors="coerce")
    estimate = estimate.groupby(out["mmsi"]).ffill().fillna(float(fallback))
    out["turnaround_estimate_min"] = estimate.astype(float)

    source = out.get(
        "turnaround_estimate_source",
        pd.Series(index=out.index, dtype="object"),
    ).astype("string")
    source = source.groupby(out["mmsi"]).ffill().fillna("CONFIGURED_FALLBACK")
    out["turnaround_estimate_source"] = source.astype(str)
    out["turnaround_prior_is_finite"] = np.isfinite(out["turnaround_estimate_min"])
    return out


def run_stage3(
    state: pd.DataFrame,
    profiles: pd.DataFrame,
    stage_dir: Path,
    config_dir: Path,
):
    """Run Stage 03 with unique berth assignment and causal priors."""
    assigned_state = _enforce_unique_berth_assignment(state, config_dir)
    previous = implementation.stage3_berth_outputs
    implementation.stage3_berth_outputs = _plotly_safe_stage3_outputs
    try:
        result = implementation.run_stage3(assigned_state, profiles, stage_dir, config_dir)
    finally:
        implementation.stage3_berth_outputs = previous

    out, episodes, empirical, audit, calibration_cutoff = result
    out = _propagate_causal_turnaround_prior(
        out,
        fallback=_configured_turnaround(config_dir),
    )
    Path(stage_dir).mkdir(parents=True, exist_ok=True)
    out.to_csv(Path(stage_dir) / "03_input_state_enhanced.csv", index=False)
    return out, episodes, empirical, audit, calibration_cutoff
