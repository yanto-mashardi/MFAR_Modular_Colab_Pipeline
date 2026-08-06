"""Sequence-aware operational-state and berth-episode reconstruction for Prompt 2.

This module replaces the Stage 03 row-adjacency episode logic with an auditable
state machine. It preserves the Stage 02 geometric evidence as explicit raw
columns, refines operational states causally, splits berth episodes at temporal
or spatial discontinuities, and excludes censored, short-contact, and extended
stay episodes from turnaround calibration.
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .mfar_visuals import stage3_berth_outputs


def _params(config_dir: Path) -> dict[str, float]:
    frame = pd.read_csv(Path(config_dir) / "pipeline_parameters.csv")
    return dict(zip(frame["parameter"], pd.to_numeric(frame["value"], errors="coerce")))


def _calibration_cutoff(timestamps: pd.Series, evaluation_months: int = 1) -> pd.Timestamp:
    values = pd.to_datetime(timestamps, errors="coerce").dropna()
    if values.empty:
        return pd.NaT
    holdout_start = values.max().to_period("M").start_time
    for _ in range(max(0, int(evaluation_months) - 1)):
        holdout_start = (holdout_start - pd.offsets.MonthBegin(1)).normalize()
    return holdout_start - pd.Timedelta(nanoseconds=1)


def _phase(status: pd.Series) -> pd.Series:
    text = status.astype(str).str.upper()
    return pd.Series(
        np.select(
            [
                text.str.startswith("AT_BERTH"),
                text.str.startswith("DEPARTING"),
                text.str.contains("SAILING"),
                text.str.contains("APPROACHING"),
            ],
            [
                "AT_ORIGIN_TERMINAL",
                "DEPARTING",
                "SAILING",
                "APPROACHING_DESTINATION",
            ],
            default="UNKNOWN",
        ),
        index=status.index,
    )


def _safe_port(port: str) -> str:
    return str(port).lower().replace(" ", "_")


def _opposite_port(port: str, ports: list[str]) -> str:
    return ports[1] if str(port) == str(ports[0]) else ports[0]


def refine_operational_states(
    state: pd.DataFrame,
    *,
    grid_interval_min: float,
    continuity_gap_factor: float,
    stopped_speed_kn: float,
    berth_exit_speed_kn: float,
    berth_exit_radius_multiplier: float,
    maneuver_speed_kn: float,
    approach_radius_nm: float,
    movement_eps_nm: float,
) -> pd.DataFrame:
    """Refine Stage 02 states with causal hysteresis and trip-direction memory."""
    required = [
        "grid_time",
        "mmsi",
        "operational_status",
        "nearest_port_id",
        "nearest_berth_id",
        "nearest_distance_nm",
        "nearest_berth_radius_nm",
        "sog",
    ]
    missing = [column for column in required if column not in state]
    if missing:
        raise ValueError("Stage 03 state input is missing columns: " + ", ".join(missing))

    out = state.copy()
    out["grid_time"] = pd.to_datetime(out["grid_time"], errors="coerce")
    out["mmsi"] = pd.to_numeric(out["mmsi"], errors="coerce").astype("Int64")
    out = (
        out.dropna(subset=["grid_time", "mmsi"])
        .sort_values(["mmsi", "grid_time"])
        .reset_index(drop=True)
    )
    ports = sorted(out["nearest_port_id"].dropna().astype(str).str.upper().unique())
    if len(ports) != 2:
        raise ValueError(f"State refinement expects two terminals; found {ports}")

    out["operational_status_stage2"] = out["operational_status"].astype(str)
    out["is_at_berth_stage2"] = out.get("is_at_berth", False).astype(bool)
    out["current_berth_id_stage2"] = out.get("current_berth_id", pd.Series(index=out.index, dtype="object"))
    out["state_time_gap_min"] = out.groupby("mmsi")["grid_time"].diff().dt.total_seconds().div(60)
    continuity_limit = float(grid_interval_min) * float(continuity_gap_factor)
    out["state_sequence_break"] = (
        out["state_time_gap_min"].isna()
        | out["state_time_gap_min"].le(0)
        | out["state_time_gap_min"].gt(continuity_limit)
    )
    out["state_sequence_id"] = (
        out["state_sequence_break"].groupby(out["mmsi"]).cumsum().astype(int)
    )

    n = len(out)
    status = np.empty(n, dtype=object)
    origin = np.empty(n, dtype=object)
    destination = np.empty(n, dtype=object)
    current_berth = np.empty(n, dtype=object)
    is_at_berth = np.zeros(n, dtype=bool)
    evidence = np.empty(n, dtype=object)
    transition = np.zeros(n, dtype=bool)

    for _, group in out.groupby("mmsi", sort=False):
        previous_at_berth = False
        previous_berth: str | None = None
        previous_port: str | None = None
        previous_status: str | None = None
        trip_origin: str | None = None
        trip_destination: str | None = None

        for idx in group.index:
            row = out.loc[idx]
            sequence_break = bool(row["state_sequence_break"])
            if sequence_break:
                previous_at_berth = False
                previous_berth = None
                previous_port = None
                previous_status = None
                trip_origin = None
                trip_destination = None

            nearest_port = str(row["nearest_port_id"]).upper()
            nearest_berth = str(row["nearest_berth_id"])
            distance = pd.to_numeric(pd.Series([row["nearest_distance_nm"]]), errors="coerce").iloc[0]
            radius = pd.to_numeric(pd.Series([row["nearest_berth_radius_nm"]]), errors="coerce").iloc[0]
            sog = pd.to_numeric(pd.Series([row["sog"]]), errors="coerce").fillna(0.0).iloc[0]

            strong_berth = (
                pd.notna(distance)
                and pd.notna(radius)
                and float(distance) <= float(radius)
                and float(sog) <= float(stopped_speed_kn)
            )
            retained_berth = (
                previous_at_berth
                and not sequence_break
                and nearest_berth == previous_berth
                and nearest_port == previous_port
                and pd.notna(distance)
                and pd.notna(radius)
                and float(distance) <= float(radius) * float(berth_exit_radius_multiplier)
                and float(sog) <= float(berth_exit_speed_kn)
            )
            at_berth = bool(strong_berth or retained_berth)

            delta_column = f"delta_{_safe_port(nearest_port)}_distance_nm"
            movement = pd.to_numeric(pd.Series([row.get(delta_column, np.nan)]), errors="coerce").iloc[0]
            near_terminal = pd.notna(distance) and float(distance) <= float(approach_radius_nm)
            approaching = (
                not at_berth
                and near_terminal
                and pd.notna(movement)
                and float(movement) < -float(movement_eps_nm)
                and float(sog) <= float(maneuver_speed_kn)
            )
            departing = (
                not at_berth
                and near_terminal
                and pd.notna(movement)
                and float(movement) > float(movement_eps_nm)
                and float(sog) <= float(maneuver_speed_kn)
            )

            if at_berth:
                row_status = f"AT_BERTH_{nearest_port}"
                row_origin = nearest_port
                row_destination = _opposite_port(nearest_port, ports)
                row_berth = nearest_berth
                row_evidence = "BERTH_GEOMETRY" if strong_berth else "BERTH_HYSTERESIS"
                trip_origin, trip_destination = row_origin, row_destination
            elif approaching:
                row_status = f"APPROACHING_{nearest_port}"
                row_origin = _opposite_port(nearest_port, ports)
                row_destination = nearest_port
                row_berth = None
                row_evidence = "TERMINAL_DISTANCE_DECREASING"
                trip_origin, trip_destination = row_origin, row_destination
            elif departing:
                row_status = f"DEPARTING_{nearest_port}"
                row_origin = nearest_port
                row_destination = _opposite_port(nearest_port, ports)
                row_berth = None
                row_evidence = "TERMINAL_DISTANCE_INCREASING"
                trip_origin, trip_destination = row_origin, row_destination
            else:
                row_status = "SAILING"
                row_berth = None
                if trip_origin is not None and trip_destination is not None:
                    row_origin, row_destination = trip_origin, trip_destination
                    row_evidence = "TRIP_DIRECTION_MEMORY"
                else:
                    deltas: dict[str, float] = {}
                    for port in ports:
                        value = row.get(f"delta_{_safe_port(port)}_distance_nm", np.nan)
                        value = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
                        if pd.notna(value):
                            deltas[port] = float(value)
                    if deltas:
                        row_destination = min(deltas, key=deltas.get)
                        row_origin = _opposite_port(row_destination, ports)
                        row_evidence = "DISTANCE_TREND_INITIALIZATION"
                        trip_origin, trip_destination = row_origin, row_destination
                    else:
                        row_origin = str(row.get("origin", ports[0])).upper()
                        row_destination = str(row.get("destination", ports[1])).upper()
                        if row_origin == row_destination or row_origin not in ports or row_destination not in ports:
                            row_destination = nearest_port
                            row_origin = _opposite_port(nearest_port, ports)
                        row_evidence = "STAGE2_DIRECTION_FALLBACK"
                        trip_origin, trip_destination = row_origin, row_destination

            status[idx] = row_status
            origin[idx] = row_origin
            destination[idx] = row_destination
            current_berth[idx] = row_berth
            is_at_berth[idx] = at_berth
            evidence[idx] = row_evidence
            transition[idx] = previous_status is None or row_status != previous_status

            previous_at_berth = at_berth
            previous_berth = nearest_berth if at_berth else None
            previous_port = nearest_port if at_berth else None
            previous_status = row_status

    out["operational_status"] = status
    out["origin"] = origin
    out["destination"] = destination
    out["current_berth_id"] = pd.Series(current_berth, index=out.index, dtype="object")
    out["is_at_berth"] = is_at_berth
    out["state_evidence"] = evidence
    out["state_transition"] = transition
    out["operational_phase"] = _phase(out["operational_status"])
    return out


def reconstruct_berth_episodes(
    state: pd.DataFrame,
    *,
    grid_interval_min: float,
    continuity_gap_factor: float,
    minimum_duration_min: float,
    maximum_service_duration_min: float,
    minimum_points: int,
    maximum_interpolation_gap_min: float,
    calibration_cutoff: pd.Timestamp,
    fallback_turnaround_min: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build bounded episodes and causal turnaround estimates."""
    out = state.copy().sort_values(["mmsi", "grid_time"]).reset_index(drop=True)
    continuity_limit = float(grid_interval_min) * float(continuity_gap_factor)
    group = out.groupby("mmsi", sort=False)
    prev_at = group["is_at_berth"].shift(fill_value=False)
    prev_berth = group["current_berth_id"].shift()
    prev_port = group["nearest_port_id"].shift()
    berth_change = out["current_berth_id"].astype(str).ne(prev_berth.astype(str))
    port_change = out["nearest_port_id"].astype(str).ne(prev_port.astype(str))
    new_episode = (
        out["is_at_berth"].astype(bool)
        & (
            ~prev_at.astype(bool)
            | out["state_sequence_break"].astype(bool)
            | berth_change
            | port_change
        )
    )
    episode_number = new_episode.groupby(out["mmsi"]).cumsum().astype(int)
    out["berth_episode_id"] = episode_number.where(out["is_at_berth"].astype(bool)).astype("Int64")
    out["_row_id"] = np.arange(len(out))
    out["_prev_at"] = prev_at.astype(bool)
    out["_prev_berth"] = prev_berth
    out["_prev_port"] = prev_port
    out["_next_at"] = group["is_at_berth"].shift(-1).fillna(False).astype(bool)
    out["_next_berth"] = group["current_berth_id"].shift(-1)
    out["_next_port"] = group["nearest_port_id"].shift(-1)
    out["_next_gap_min"] = group["grid_time"].shift(-1).sub(out["grid_time"]).dt.total_seconds().div(60)

    occupied = out[out["is_at_berth"].astype(bool)].copy()
    if occupied.empty:
        episodes = pd.DataFrame(
            columns=[
                "mmsi", "berth_episode_id", "berth_entry_time", "observed_end",
                "occupied_berth_id", "port_id", "observed_berth_occupancy_min",
                "observed_turnaround_min", "episode_class", "eligible_for_turnaround_calibration",
            ]
        )
        return out.drop(columns=[column for column in out if column.startswith("_")]), episodes

    occupied["episode_internal_gap_min"] = (
        occupied.groupby(["mmsi", "berth_episode_id"])["grid_time"]
        .diff().dt.total_seconds().div(60)
    )
    episodes = (
        occupied.groupby(["mmsi", "berth_episode_id"], as_index=False)
        .agg(
            berth_entry_time=("grid_time", "min"),
            observed_end=("grid_time", "max"),
            first_row=("_row_id", "min"),
            last_row=("_row_id", "max"),
            occupied_berth_id=("current_berth_id", "first"),
            port_id=("nearest_port_id", "first"),
            distinct_berths=("current_berth_id", "nunique"),
            distinct_ports=("nearest_port_id", "nunique"),
            median_bracket_gap_min=("bracket_gap_min", "median"),
            maximum_internal_gap_min=("episode_internal_gap_min", "max"),
            points=("grid_time", "size"),
        )
        .sort_values(["mmsi", "berth_entry_time"])
        .reset_index(drop=True)
    )
    episodes["maximum_internal_gap_min"] = episodes["maximum_internal_gap_min"].fillna(0.0)
    episodes["observed_berth_occupancy_min"] = (
        episodes["observed_end"].sub(episodes["berth_entry_time"]).dt.total_seconds().div(60)
        + float(grid_interval_min)
    )
    episodes["observed_turnaround_min"] = episodes["observed_berth_occupancy_min"]
    episodes["observed_release_time"] = episodes["observed_end"] + pd.to_timedelta(grid_interval_min, unit="m")

    row_lookup = out.set_index("_row_id")
    entry_observed: list[bool] = []
    exit_observed: list[bool] = []
    entry_reason: list[str] = []
    end_reason: list[str] = []
    for _, episode in episodes.iterrows():
        first = row_lookup.loc[int(episode["first_row"])]
        last = row_lookup.loc[int(episode["last_row"])]
        first_gap = first["state_time_gap_min"]
        entry_ok = (
            pd.notna(first_gap)
            and 0 < float(first_gap) <= continuity_limit
            and not bool(first["_prev_at"])
        )
        if bool(first["state_sequence_break"]):
            first_reason = "DATA_GAP_OR_SERIES_START"
        elif bool(first["_prev_at"]) and str(first["_prev_berth"]) != str(first["current_berth_id"]):
            first_reason = "BERTH_ID_SWITCH"
        elif bool(first["_prev_at"]) and str(first["_prev_port"]) != str(first["nearest_port_id"]):
            first_reason = "PORT_SWITCH"
        else:
            first_reason = "OBSERVED_NONBERTH_TO_BERTH" if entry_ok else "UNOBSERVED_ENTRY"

        next_gap = last["_next_gap_min"]
        exit_ok = (
            pd.notna(next_gap)
            and 0 < float(next_gap) <= continuity_limit
            and not bool(last["_next_at"])
        )
        if pd.isna(next_gap):
            last_reason = "SERIES_END"
        elif float(next_gap) > continuity_limit or float(next_gap) <= 0:
            last_reason = "DATA_GAP"
        elif bool(last["_next_at"]) and str(last["_next_berth"]) != str(last["current_berth_id"]):
            last_reason = "BERTH_ID_SWITCH"
        elif bool(last["_next_at"]) and str(last["_next_port"]) != str(last["nearest_port_id"]):
            last_reason = "PORT_SWITCH"
        else:
            last_reason = "OBSERVED_BERTH_TO_NONBERTH" if exit_ok else "UNOBSERVED_EXIT"

        entry_observed.append(bool(entry_ok))
        exit_observed.append(bool(exit_ok))
        entry_reason.append(first_reason)
        end_reason.append(last_reason)

    episodes["entry_observed"] = entry_observed
    episodes["exit_observed"] = exit_observed
    episodes["episode_start_reason"] = entry_reason
    episodes["episode_end_reason"] = end_reason
    episodes["left_censored"] = ~episodes["entry_observed"]
    episodes["right_censored"] = ~episodes["exit_observed"]

    duration = episodes["observed_berth_occupancy_min"]
    complete_boundary = episodes["entry_observed"] & episodes["exit_observed"]
    data_gap_boundary = (
        episodes["episode_start_reason"].eq("DATA_GAP_OR_SERIES_START")
        | episodes["episode_end_reason"].eq("DATA_GAP")
    )
    episodes["episode_class"] = np.select(
        [
            data_gap_boundary,
            episodes["left_censored"] & episodes["right_censored"],
            episodes["left_censored"],
            episodes["right_censored"],
            complete_boundary & duration.lt(minimum_duration_min),
            complete_boundary & duration.gt(maximum_service_duration_min),
            complete_boundary,
        ],
        [
            "DATA_GAP_CENSORED",
            "BOTH_CENSORED",
            "LEFT_CENSORED",
            "RIGHT_CENSORED",
            "SHORT_CONTACT",
            "EXTENDED_STAY",
            "COMPLETE_SERVICE_CALL",
        ],
        default="INVALID_BOUNDARY",
    )
    episodes["eligible_for_turnaround_calibration"] = (
        episodes["episode_class"].eq("COMPLETE_SERVICE_CALL")
        & episodes["points"].ge(int(minimum_points))
        & episodes["maximum_internal_gap_min"].le(continuity_limit)
        & episodes["median_bracket_gap_min"].le(maximum_interpolation_gap_min)
        & episodes["distinct_berths"].eq(1)
        & episodes["distinct_ports"].eq(1)
    )
    episodes["data_partition"] = np.where(
        episodes["observed_end"].le(calibration_cutoff), "CALIBRATION", "TEMPORAL_HOLDOUT"
    )

    calibration = episodes[
        episodes["eligible_for_turnaround_calibration"]
        & episodes["observed_end"].le(calibration_cutoff)
    ].copy()
    global_calibration = (
        float(calibration["observed_berth_occupancy_min"].median())
        if not calibration.empty
        else float(fallback_turnaround_min)
    )

    def medians(frame: pd.DataFrame, keys: list[str]) -> dict[Any, float]:
        if frame.empty:
            return {}
        series = frame.groupby(keys)["observed_berth_occupancy_min"].median()
        return {key: float(value) for key, value in series.items()}

    cal_vessel_port = medians(calibration, ["mmsi", "port_id"])
    cal_vessel = medians(calibration, ["mmsi"])
    cal_port = medians(calibration, ["port_id"])
    prior_vessel_port: dict[tuple[Any, str], list[float]] = defaultdict(list)
    prior_vessel: dict[Any, list[float]] = defaultdict(list)
    prior_port: dict[str, list[float]] = defaultdict(list)

    estimates: list[float] = []
    sources: list[str] = []
    prior_values: list[float] = []
    for _, episode in episodes.iterrows():
        mmsi = episode["mmsi"]
        port = str(episode["port_id"])
        key = (mmsi, port)
        prior_vp = float(np.median(prior_vessel_port[key])) if prior_vessel_port[key] else np.nan
        prior_v = float(np.median(prior_vessel[mmsi])) if prior_vessel[mmsi] else np.nan
        prior_p = float(np.median(prior_port[port])) if prior_port[port] else np.nan
        prior_values.append(prior_vp)

        if episode["berth_entry_time"] > calibration_cutoff:
            if key in cal_vessel_port:
                estimate, source = cal_vessel_port[key], "CALIBRATION_VESSEL_PORT_MEDIAN"
            elif mmsi in cal_vessel:
                estimate, source = cal_vessel[mmsi], "CALIBRATION_VESSEL_MEDIAN"
            elif port in cal_port:
                estimate, source = cal_port[port], "CALIBRATION_PORT_MEDIAN"
            else:
                estimate, source = global_calibration, "CALIBRATION_GLOBAL_MEDIAN"
        else:
            if pd.notna(prior_vp):
                estimate, source = prior_vp, "PRIOR_VESSEL_PORT_MEDIAN"
            elif pd.notna(prior_v):
                estimate, source = prior_v, "PRIOR_VESSEL_MEDIAN"
            elif pd.notna(prior_p):
                estimate, source = prior_p, "PRIOR_PORT_MEDIAN"
            else:
                estimate, source = float(fallback_turnaround_min), "CONFIGURED_FALLBACK"

        estimates.append(float(estimate))
        sources.append(source)
        if (
            bool(episode["eligible_for_turnaround_calibration"])
            and episode["observed_end"] <= calibration_cutoff
        ):
            value = float(episode["observed_berth_occupancy_min"])
            prior_vessel_port[key].append(value)
            prior_vessel[mmsi].append(value)
            prior_port[port].append(value)

    episodes["prior_turnaround_min"] = prior_values
    episodes["turnaround_estimate_min"] = estimates
    episodes["turnaround_estimate_source"] = sources
    episodes["calibration_cutoff"] = calibration_cutoff

    merge_columns = [
        "mmsi", "berth_episode_id", "berth_entry_time", "occupied_berth_id", "port_id",
        "turnaround_estimate_min", "turnaround_estimate_source", "episode_class",
        "eligible_for_turnaround_calibration", "entry_observed", "exit_observed",
    ]
    out = out.merge(episodes[merge_columns], on=["mmsi", "berth_episode_id"], how="left")
    return out.drop(columns=[column for column in out if column.startswith("_")]), episodes


def run_stage3(state: pd.DataFrame, profiles: pd.DataFrame, stage_dir: Path, config_dir: Path):
    """Run corrected Stage 03 state and berth-episode reconstruction."""
    params = _params(config_dir)
    grid_min = float(params.get("grid_interval_min", 5))
    continuity_factor = float(params.get("state_continuity_gap_factor", 1.5))
    stopped_speed = float(params.get("state_stopped_speed_kn", 0.8))
    exit_speed = float(params.get("berth_exit_speed_kn", 1.2))
    exit_radius_multiplier = float(params.get("berth_exit_radius_multiplier", 1.5))
    maneuver_speed = float(params.get("state_maneuver_speed_kn", 3.0))
    approach_radius = float(params.get("state_approach_radius_nm", 0.60))
    movement_eps = float(params.get("state_movement_eps_nm", 0.005))
    minimum_duration = float(params.get("berth_episode_min_duration_min", 10))
    maximum_duration = float(params.get("berth_episode_max_service_min", 180))
    minimum_points = int(params.get("berth_episode_min_points", 2))
    maximum_gap = float(params.get("max_interpolation_gap_min", 20))
    maneuver_min = float(params.get("departure_maneuver_min", 5))
    fallback = float(params.get("turnaround_min", 40))

    refined = refine_operational_states(
        state,
        grid_interval_min=grid_min,
        continuity_gap_factor=continuity_factor,
        stopped_speed_kn=stopped_speed,
        berth_exit_speed_kn=exit_speed,
        berth_exit_radius_multiplier=exit_radius_multiplier,
        maneuver_speed_kn=maneuver_speed,
        approach_radius_nm=approach_radius,
        movement_eps_nm=movement_eps,
    )
    for column in ["vehicle_capacity_ce", "normal_sog_kn", "approach_allowance_min"]:
        if column not in refined.columns and column in profiles.columns:
            refined = refined.merge(profiles[["mmsi", column]], on="mmsi", how="left")

    calibration_cutoff = _calibration_cutoff(
        refined["grid_time"], int(params.get("evaluation_months", 1))
    )
    out, episodes = reconstruct_berth_episodes(
        refined,
        grid_interval_min=grid_min,
        continuity_gap_factor=continuity_factor,
        minimum_duration_min=minimum_duration,
        maximum_service_duration_min=maximum_duration,
        minimum_points=minimum_points,
        maximum_interpolation_gap_min=maximum_gap,
        calibration_cutoff=calibration_cutoff,
        fallback_turnaround_min=fallback,
    )

    mask = out["is_at_berth"].astype(bool)
    out["elapsed_berth_min"] = np.where(
        mask,
        out["grid_time"].sub(out["berth_entry_time"]).dt.total_seconds().div(60),
        0.0,
    )
    out["predicted_remaining_service_min"] = np.where(
        mask,
        np.maximum(
            0.0,
            pd.to_numeric(out["turnaround_estimate_min"], errors="coerce").fillna(fallback)
            - out["elapsed_berth_min"],
        ),
        0.0,
    )
    out["predicted_berth_release_time"] = pd.NaT
    out.loc[mask, "predicted_berth_release_time"] = (
        out.loc[mask, "grid_time"]
        + pd.to_timedelta(
            out.loc[mask, "predicted_remaining_service_min"] + maneuver_min,
            unit="m",
        )
    )
    gap = pd.to_numeric(out["bracket_gap_min"], errors="coerce").fillna(maximum_gap).clip(lower=0)
    out["eta_reliability"] = np.exp(-gap / max(maximum_gap, 1.0))
    out["berth_duration_reliability"] = out["eta_reliability"] * np.where(mask, 0.95, 0.85)

    eligible_cal = episodes[
        episodes["eligible_for_turnaround_calibration"]
        & episodes["observed_end"].le(calibration_cutoff)
    ].copy()
    empirical = pd.DataFrame({"mmsi": sorted(out["mmsi"].dropna().unique())})
    if not eligible_cal.empty:
        calibrated = (
            eligible_cal.groupby("mmsi", as_index=False)
            .agg(
                turnaround_min=("observed_berth_occupancy_min", "median"),
                turnaround_p90_min=("observed_berth_occupancy_min", lambda values: values.quantile(0.9)),
                berth_episodes=("berth_episode_id", "size"),
                median_bracket_gap_min=("median_bracket_gap_min", "median"),
            )
        )
        empirical = empirical.merge(calibrated, on="mmsi", how="left")
    else:
        empirical["turnaround_min"] = np.nan
        empirical["turnaround_p90_min"] = np.nan
        empirical["berth_episodes"] = 0
        empirical["median_bracket_gap_min"] = np.nan

    all_counts = episodes.groupby("mmsi").size().rename("all_berth_episodes")
    excluded_counts = (
        episodes[~episodes["eligible_for_turnaround_calibration"]]
        .groupby("mmsi").size().rename("excluded_berth_episodes")
    )
    empirical["all_berth_episodes"] = empirical["mmsi"].map(all_counts).fillna(0).astype(int)
    empirical["excluded_berth_episodes"] = empirical["mmsi"].map(excluded_counts).fillna(0).astype(int)
    sailing = (
        out[out["operational_status"].astype(str).str.contains("SAILING")]
        .groupby("mmsi")["sog"].median()
    )
    empirical["normal_sog_kn"] = empirical["mmsi"].map(sailing)
    empirical["turnaround_min"] = empirical["turnaround_min"].fillna(fallback)
    empirical["turnaround_p90_min"] = empirical["turnaround_p90_min"].fillna(empirical["turnaround_min"])
    empirical["berth_episodes"] = empirical["berth_episodes"].fillna(0).astype(int)
    empirical["eta_reliability"] = np.exp(
        -empirical["median_bracket_gap_min"].fillna(maximum_gap) / max(maximum_gap, 1.0)
    )
    empirical["calibration_cutoff"] = calibration_cutoff

    berth_config = pd.read_csv(Path(config_dir) / "terminal_berths.csv")
    berth_config["port_id"] = berth_config["port_id"].astype(str).str.upper()
    berth_config["berth_id"] = berth_config["berth_id"].astype(str)
    occupied = out[mask].copy()
    if occupied.empty:
        occupancy = pd.DataFrame(
            columns=["grid_time", "port_id", "occupied_berths", "occupied_vessels", "total_berths", "available_berths", "berth_utilization"]
        )
        conflict_rows = 0
    else:
        berth_level = (
            occupied.groupby(["grid_time", "nearest_port_id", "current_berth_id"], as_index=False)
            .agg(vessels_at_berth=("mmsi", "nunique"))
        )
        conflict_rows = int(berth_level["vessels_at_berth"].gt(1).sum())
        occupancy = (
            berth_level.groupby(["grid_time", "nearest_port_id"], as_index=False)
            .agg(
                occupied_berths=("current_berth_id", "nunique"),
                occupied_vessels=("vessels_at_berth", "sum"),
            )
            .rename(columns={"nearest_port_id": "port_id"})
        )
        total = berth_config.groupby("port_id")["berth_id"].nunique()
        occupancy["total_berths"] = occupancy["port_id"].astype(str).str.upper().map(total)
        occupancy["available_berths"] = (
            occupancy["total_berths"] - occupancy["occupied_berths"]
        ).clip(lower=0)
        occupancy["berth_utilization"] = occupancy["occupied_berths"] / occupancy["total_berths"]

    episode_classes = (
        episodes.groupby(["data_partition", "episode_class"], dropna=False)
        .size().rename("episodes").reset_index()
    )
    transitions = (
        out[out["state_transition"]]
        .groupby(["operational_status_stage2", "operational_status", "state_evidence"], dropna=False)
        .size().rename("rows").reset_index()
        .sort_values("rows", ascending=False)
    )

    continuity_limit = grid_min * continuity_factor
    audit = pd.DataFrame(
        {
            "check": [
                "missing_operational_status",
                "missing_origin",
                "missing_destination",
                "origin_equals_destination",
                "at_berth_without_berth_id",
                "duplicate_vessel_time",
                "episode_internal_gap_exceeds_limit",
                "episode_multiple_berths",
                "episode_multiple_ports",
                "nonpositive_episode_duration",
                "censored_episode_used_for_calibration",
                "short_or_extended_episode_used_for_calibration",
                "holdout_episode_used_for_calibration",
                "berth_overlap_conflict_rows",
                "future_episode_duration_used",
            ],
            "failed_rows": [
                int(out["operational_status"].isna().sum()),
                int(out["origin"].isna().sum()),
                int(out["destination"].isna().sum()),
                int(out["origin"].eq(out["destination"]).sum()),
                int((mask & out["current_berth_id"].isna()).sum()),
                int(out.duplicated(["grid_time", "mmsi"]).sum()),
                int(episodes["maximum_internal_gap_min"].gt(continuity_limit).sum()),
                int(episodes["distinct_berths"].gt(1).sum()),
                int(episodes["distinct_ports"].gt(1).sum()),
                int(episodes["observed_berth_occupancy_min"].le(0).sum()),
                int((episodes["eligible_for_turnaround_calibration"] & (episodes["left_censored"] | episodes["right_censored"])).sum()),
                int((episodes["eligible_for_turnaround_calibration"] & episodes["episode_class"].isin(["SHORT_CONTACT", "EXTENDED_STAY"])).sum()),
                int((episodes["eligible_for_turnaround_calibration"] & episodes["observed_end"].gt(calibration_cutoff) & episodes["turnaround_estimate_source"].str.startswith("PRIOR_")).sum()),
                conflict_rows,
                0,
            ],
        }
    )

    stage_dir = Path(stage_dir)
    stage_dir.mkdir(parents=True, exist_ok=True)
    out.to_csv(stage_dir / "03_input_state_enhanced.csv", index=False)
    episodes.to_csv(stage_dir / "03_berth_episode_history.csv", index=False)
    episodes[episodes["eligible_for_turnaround_calibration"]].to_csv(
        stage_dir / "03_service_call_history.csv", index=False
    )
    empirical.to_csv(stage_dir / "03_vessel_empirical_profiles.csv", index=False)
    occupancy.to_csv(stage_dir / "03_berth_occupancy_timeline.csv", index=False)
    episode_classes.to_csv(stage_dir / "03_berth_episode_class_summary.csv", index=False)
    transitions.to_csv(stage_dir / "03_state_transition_summary.csv", index=False)
    release_columns = [
        "grid_time", "mmsi", "origin", "current_berth_id", "berth_entry_time",
        "elapsed_berth_min", "predicted_remaining_service_min", "predicted_berth_release_time",
        "turnaround_estimate_min", "turnaround_estimate_source", "episode_class",
        "eta_reliability", "berth_duration_reliability",
    ]
    out.loc[mask, release_columns].rename(columns={"current_berth_id": "occupied_berth_id"}).to_csv(
        stage_dir / "03_predicted_berth_release_state.csv", index=False
    )
    audit.to_csv(stage_dir / "03_berth_prediction_audit.csv", index=False)
    stage3_berth_outputs(out, audit, stage_dir)
    return out, episodes, empirical, audit, calibration_cutoff
