"""Prospective fixed-grid decision epochs for MFAR Stage 04.

Prompt 3 removes the oracle-style construction ``observed departure - lead``.
Decision cases are emitted by an online-equivalent scan of contemporaneous
Stage 03 states. Observed departures are attached only after prediction for
holdout validation and retrospective epoch comparison.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .mfar_core import (
    _arrival_rate,
    _calibration_cutoff,
    _detect_departures,
    _earliest_berth_slot,
    _params,
    _phase,
)
from .mfar_visuals import stage4_forecast_outputs


def _numeric(value: Any, fallback: float) -> float:
    parsed = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return float(parsed) if pd.notna(parsed) and np.isfinite(parsed) else float(fallback)


def _minute_of_day(values: pd.Series) -> pd.Series:
    stamp = pd.to_datetime(values, errors="coerce")
    return stamp.dt.hour * 60 + stamp.dt.minute


def _scan_aligned(values: pd.Series, interval_min: float) -> pd.Series:
    stamp = pd.to_datetime(values, errors="coerce")
    interval = max(int(round(float(interval_min))), 1)
    minute = stamp.dt.hour * 60 + stamp.dt.minute
    return stamp.notna() & stamp.dt.second.eq(0) & stamp.dt.microsecond.eq(0) & minute.mod(interval).eq(0)


def build_prospective_decision_epochs(
    state: pd.DataFrame,
    *,
    cutoff: pd.Timestamp,
    scan_interval_min: float,
    horizon_min: float,
    operating_start_min: int,
    operating_end_min: int,
    minimum_elapsed_berth_min: float = 0.0,
) -> pd.DataFrame:
    """Emit the first eligible fixed-grid decision for each berth episode.

    Eligibility uses information available at the scan time: current berth
    state, causal turnaround prior, elapsed berth time, and predicted release.
    The function deliberately accepts no observed-departure table.
    """
    required = [
        "grid_time",
        "mmsi",
        "is_at_berth",
        "operational_status",
        "operational_phase",
        "origin",
        "destination",
        "berth_episode_id",
        "predicted_berth_release_time",
        "elapsed_berth_min",
    ]
    missing = [column for column in required if column not in state.columns]
    if missing:
        raise ValueError("Prospective epoch input is missing columns: " + ", ".join(missing))

    out = state.copy()
    out["grid_time"] = pd.to_datetime(out["grid_time"], errors="coerce")
    out["predicted_berth_release_time"] = pd.to_datetime(
        out["predicted_berth_release_time"], errors="coerce"
    )
    out["mmsi"] = pd.to_numeric(out["mmsi"], errors="coerce").astype("Int64")
    out["elapsed_berth_min"] = pd.to_numeric(out["elapsed_berth_min"], errors="coerce")
    out["release_lead_min"] = (
        out["predicted_berth_release_time"].sub(out["grid_time"]).dt.total_seconds().div(60)
    )
    minute = _minute_of_day(out["grid_time"])
    aligned = _scan_aligned(out["grid_time"], scan_interval_min)
    at_origin = (
        out["is_at_berth"].astype(bool)
        & out["operational_status"].astype(str).str.startswith("AT_BERTH")
        & out["operational_phase"].astype(str).str.upper().eq("AT_ORIGIN_TERMINAL")
    )
    eligible = (
        out["grid_time"].gt(pd.Timestamp(cutoff))
        & aligned
        & minute.between(int(operating_start_min), int(operating_end_min))
        & at_origin
        & out["berth_episode_id"].notna()
        & out["predicted_berth_release_time"].notna()
        & out["release_lead_min"].le(float(horizon_min))
        & out["elapsed_berth_min"].ge(float(minimum_elapsed_berth_min))
        & out["origin"].notna()
        & out["destination"].notna()
        & out["origin"].astype(str).ne(out["destination"].astype(str))
    )

    issued: set[tuple[int, int]] = set()
    cases: list[dict[str, Any]] = []
    candidates = out.loc[eligible].sort_values(["grid_time", "mmsi"])
    for _, row in candidates.iterrows():
        key = (int(row["mmsi"]), int(row["berth_episode_id"]))
        if key in issued:
            continue
        issued.add(key)
        decision = pd.Timestamp(row["grid_time"])
        lead = float(row["release_lead_min"])
        payload = row.to_dict()
        payload.update(
            {
                "decision_case_id": f"P3-{decision.strftime('%Y%m%dT%H%M')}-{key[0]}-{key[1]}",
                "simulation_time": decision,
                "decision_time": decision,
                "decision_epoch_mode": "PROSPECTIVE_FIXED_GRID",
                "decision_trigger_source": (
                    "PREDICTED_RELEASE_WITHIN_HORIZON"
                    if lead >= 0
                    else "PREDICTED_RELEASE_OVERDUE"
                ),
                "decision_scan_interval_min": float(scan_interval_min),
                "decision_horizon_min": float(horizon_min),
                "trigger_release_lead_min": lead,
                "case_generation_known_until": decision,
                "observed_departure_used_to_generate_case": False,
                "observed_departure_used_in_eta": False,
            }
        )
        cases.append(payload)

    if cases:
        return pd.DataFrame(cases).sort_values(["decision_time", "mmsi"]).reset_index(drop=True)
    columns = list(out.columns) + [
        "decision_case_id",
        "simulation_time",
        "decision_time",
        "decision_epoch_mode",
        "decision_trigger_source",
        "decision_scan_interval_min",
        "decision_horizon_min",
        "trigger_release_lead_min",
        "case_generation_known_until",
        "observed_departure_used_to_generate_case",
        "observed_departure_used_in_eta",
    ]
    return pd.DataFrame(columns=list(dict.fromkeys(columns)))


def _evaluation_departures(
    departures: pd.DataFrame,
    cutoff: pd.Timestamp,
    operating_start_min: int,
    operating_end_min: int,
) -> pd.DataFrame:
    if departures.empty:
        return departures.copy()
    out = departures.copy()
    out["baseline_departure_time"] = pd.to_datetime(
        out["baseline_departure_time"], errors="coerce"
    )
    minute = _minute_of_day(out["baseline_departure_time"])
    return (
        out[
            out["baseline_departure_time"].gt(cutoff)
            & minute.between(int(operating_start_min), int(operating_end_min))
        ]
        .sort_values("baseline_departure_time")
        .reset_index(drop=True)
    )


def _build_queue_baseline(
    state: pd.DataFrame,
    evaluation_departures: pd.DataFrame,
    rates: pd.DataFrame,
    profiles: pd.DataFrame,
    *,
    cutoff: pd.Timestamp,
    motor_ce: float,
    scan_interval_min: float,
    operating_start_min: int,
    operating_end_min: int,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[tuple[pd.Timestamp, str], dict[str, Any]]]:
    dates = sorted(state.loc[state["grid_time"].gt(cutoff), "grid_time"].dt.date.unique())
    ports = sorted(rates["port_id"].astype(str).str.upper().unique())
    capacity_default = _numeric(profiles["vehicle_capacity_ce"].median(), 30.0)
    step = max(int(round(float(scan_interval_min))), 1)
    queues: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    lookup: dict[tuple[pd.Timestamp, str], dict[str, Any]] = {}

    for date in dates:
        q = {port: {"car": 0.0, "motor": 0.0} for port in ports}
        start = pd.Timestamp(date) + pd.Timedelta(minutes=int(operating_start_min))
        end = pd.Timestamp(date) + pd.Timedelta(minutes=int(operating_end_min))
        times = pd.date_range(start, end, freq=f"{step}min")
        day_events = evaluation_departures[
            evaluation_departures["baseline_departure_time"].dt.date.eq(date)
        ]
        for stamp in times:
            for port in ports:
                car, motor, _ = _arrival_rate(rates, port, stamp, motor_ce)
                q[port]["car"] += car
                q[port]["motor"] += motor
            for _, event in day_events[
                day_events["baseline_departure_time"].eq(stamp)
            ].iterrows():
                port = str(event["origin"]).upper()
                if port not in q:
                    continue
                available = q[port]["car"] + motor_ce * q[port]["motor"]
                capacity = _numeric(event.get("vehicle_capacity_ce"), capacity_default)
                served = min(capacity, available)
                served_car = min(q[port]["car"], served)
                q[port]["car"] -= served_car
                remaining = served - served_car
                if remaining > 0:
                    q[port]["motor"] = max(0.0, q[port]["motor"] - remaining / max(motor_ce, 1e-9))
                events.append(
                    {
                        "simulation_time": stamp,
                        "mmsi": event["mmsi"],
                        "origin": port,
                        "destination": event["destination"],
                        "capacity_ce": capacity,
                        "served_ce": served,
                        "event_type": "AIS_DEPARTURE",
                        "source": "temporal_holdout_observed_baseline",
                    }
                )
            for port in ports:
                ce = q[port]["car"] + motor_ce * q[port]["motor"]
                row = {
                    "simulation_time": stamp,
                    "port_id": port,
                    "queue_car": q[port]["car"],
                    "queue_motorcycle": q[port]["motor"],
                    "queue_ce": ce,
                    "queue_ratio": ce / max(capacity_default, 1e-9),
                    "evaluation_date": date,
                }
                queues.append(row)
                lookup[(stamp, port)] = row
    return pd.DataFrame(queues), pd.DataFrame(events), lookup


def _trip_history(episodes: pd.DataFrame) -> pd.DataFrame:
    trips: list[dict[str, Any]] = []
    if episodes.empty:
        return pd.DataFrame(columns=["mmsi", "origin", "destination", "trip_min", "known_at"])
    for mmsi, group in episodes.sort_values("berth_entry_time").groupby("mmsi"):
        rows = group.reset_index(drop=True)
        for idx in range(len(rows) - 1):
            origin = rows.iloc[idx]
            destination = rows.iloc[idx + 1]
            if str(origin["port_id"]).upper() == str(destination["port_id"]).upper():
                continue
            duration = (
                pd.Timestamp(destination["berth_entry_time"])
                - pd.Timestamp(origin["observed_end"])
            ).total_seconds() / 60
            if 10 <= duration <= 120:
                trips.append(
                    {
                        "mmsi": mmsi,
                        "origin": str(origin["port_id"]).upper(),
                        "destination": str(destination["port_id"]).upper(),
                        "trip_min": float(duration),
                        "known_at": pd.Timestamp(destination["berth_entry_time"]),
                    }
                )
    return pd.DataFrame(trips)


def _profile_capacity_lookup(profiles: pd.DataFrame) -> tuple[dict[int, float], float]:
    frame = profiles.copy()
    frame["mmsi"] = pd.to_numeric(frame["mmsi"], errors="coerce").astype("Int64")
    frame["vehicle_capacity_ce"] = pd.to_numeric(frame["vehicle_capacity_ce"], errors="coerce")
    fallback = _numeric(frame["vehicle_capacity_ce"].median(), 30.0)
    lookup = {
        int(row["mmsi"]): float(row["vehicle_capacity_ce"])
        for _, row in frame.dropna(subset=["mmsi", "vehicle_capacity_ce"]).iterrows()
    }
    return lookup, fallback


def _predict_from_cases(
    cases: pd.DataFrame,
    *,
    state: pd.DataFrame,
    trips: pd.DataFrame,
    evaluation_departures: pd.DataFrame,
    queue_lookup: dict[tuple[pd.Timestamp, str], dict[str, Any]],
    rates: pd.DataFrame,
    profiles: pd.DataFrame,
    berths: pd.DataFrame,
    params: dict[str, float],
    cutoff: pd.Timestamp,
) -> pd.DataFrame:
    if cases.empty:
        return cases.copy()

    motor_ce = float(params.get("motorcycle_ce", 0.25))
    fallback_trip = float(params.get("fallback_trip_min", 45.0))
    fallback_turnaround = float(params.get("turnaround_min", 40.0))
    scan_interval = float(params.get("decision_scan_interval_min", params.get("grid_interval_min", 5.0)))
    capacity_lookup, capacity_default = _profile_capacity_lookup(profiles)
    berth_reservations: dict[str, list[tuple[pd.Timestamp, pd.Timestamp]]] = {
        str(berth_id): [] for berth_id in berths["berth_id"].astype(str)
    }
    forecasts: list[dict[str, Any]] = []

    for _, case in cases.sort_values(["decision_time", "mmsi"]).iterrows():
        decision = pd.Timestamp(case["decision_time"])
        origin = str(case["origin"]).upper()
        destination = str(case["destination"]).upper()
        history = (
            trips[
                trips["known_at"].lt(decision)
                & trips["origin"].astype(str).str.upper().eq(origin)
                & trips["destination"].astype(str).str.upper().eq(destination)
            ]
            if not trips.empty
            else pd.DataFrame()
        )
        sailing_min = float(history["trip_min"].median()) if not history.empty else fallback_trip
        release = pd.to_datetime(case.get("predicted_berth_release_time"), errors="coerce")
        if pd.isna(release):
            continue
        predicted_departure = max(decision, pd.Timestamp(release))
        departure_source = (
            "CAUSAL_BERTH_RELEASE_ESTIMATE"
            if pd.Timestamp(release) >= decision
            else "OVERDUE_RELEASE_CLIPPED_TO_DECISION"
        )
        approach = _numeric(case.get("approach_allowance_min"), 5.0)
        eta = predicted_departure + pd.Timedelta(minutes=sailing_min + approach)

        at_decision = state[state["grid_time"].eq(decision) & state["is_at_berth"].astype(bool)]
        releases: dict[str, pd.Timestamp] = {}
        destination_berths = berths.loc[
            berths["port_id"].astype(str).str.upper().eq(destination), "berth_id"
        ].astype(str)
        for berth_id in destination_berths:
            occupied = at_decision[at_decision["current_berth_id"].astype(str).eq(berth_id)]
            predicted_release = (
                pd.to_datetime(occupied["predicted_berth_release_time"], errors="coerce").max()
                if not occupied.empty
                else pd.NaT
            )
            releases[berth_id] = pd.Timestamp(predicted_release) if pd.notna(predicted_release) else decision
        if not releases:
            continue

        service_min = _numeric(case.get("turnaround_estimate_min"), fallback_turnaround)
        candidate_slots = {
            berth_id: _earliest_berth_slot(
                eta,
                service_min,
                release_time,
                berth_reservations.get(berth_id, []),
            )
            for berth_id, release_time in releases.items()
        }
        selected = min(candidate_slots, key=lambda key: candidate_slots[key][0])
        available, service_end = candidate_slots[selected]
        berth_reservations.setdefault(selected, []).append((available, service_end))
        wait = max(0.0, (available - eta).total_seconds() / 60)

        decision_floor = decision.floor(f"{max(int(round(scan_interval)), 1)}min")
        origin_queue = queue_lookup.get((decision_floor, origin), {"queue_ratio": 0.0})["queue_ratio"]
        destination_queue = queue_lookup.get((decision_floor, destination), {"queue_ratio": 0.0})["queue_ratio"]
        prior_departures = evaluation_departures[
            evaluation_departures["origin"].astype(str).str.upper().eq(origin)
            & evaluation_departures["baseline_departure_time"].lt(decision)
        ]
        service_gap = (
            (decision - prior_departures["baseline_departure_time"].max()).total_seconds() / 60
            if not prior_departures.empty
            else 180.0
        )
        future_arrivals = sum(
            _arrival_rate(
                rates,
                origin,
                decision_floor + pd.Timedelta(minutes=offset),
                motor_ce,
            )[2]
            for offset in range(0, 60, max(int(round(scan_interval)), 1))
        )
        mmsi = int(case["mmsi"])
        state_capacity = pd.to_numeric(pd.Series([case.get("vehicle_capacity_ce")]), errors="coerce").iloc[0]
        if pd.notna(state_capacity) and float(state_capacity) > 0:
            capacity = float(state_capacity)
            capacity_source = "CURRENT_STATE_PROFILE"
        elif mmsi in capacity_lookup:
            capacity = capacity_lookup[mmsi]
            capacity_source = "VESSEL_PROFILE_LOOKUP"
        else:
            capacity = capacity_default
            capacity_source = "PROFILE_MEDIAN_FALLBACK"
        shortfall = max(0.0, future_arrivals - capacity)
        confidence = _numeric(case.get("eta_reliability"), 0.5) * _numeric(
            case.get("berth_duration_reliability"), 0.5
        )

        payload = case.to_dict()
        payload.update(
            {
                "event_type": "PROSPECTIVE_PRE_DEPARTURE_DECISION",
                "predicted_departure_time": predicted_departure,
                "departure_prediction_source": departure_source,
                "trip_history_latest_time": history["known_at"].max() if not history.empty else pd.NaT,
                "operational_phase": _phase(pd.Series([case["operational_status"]])).iloc[0],
                "capacity_ce": capacity,
                "capacity_source": capacity_source,
                "predicted_eta": eta,
                "assigned_destination_berth": selected,
                "predicted_berth_available_time_at_eta": available,
                "predicted_berth_service_start": available,
                "predicted_berth_service_end": service_end,
                "berth_service_duration_min": service_min,
                "predicted_wait_min": wait,
                "berth_availability_at_eta": float(wait == 0),
                "origin_queue_ratio": float(origin_queue),
                "destination_queue_ratio": float(destination_queue),
                "forecast_confidence": float(confidence),
                "service_gap_min": float(service_gap),
                "capacity_shortfall_ratio": shortfall / max(capacity_default, 1e-9),
                "calibration_cutoff": cutoff,
                "data_partition": "TEMPORAL_HOLDOUT",
            }
        )
        forecasts.append(payload)
    return pd.DataFrame(forecasts)


def attach_posthoc_validation(
    forecast: pd.DataFrame,
    departures: pd.DataFrame,
    episodes: pd.DataFrame,
    *,
    horizon_min: float,
    departure_match_window_min: float,
    arrival_match_window_min: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Attach future observations after forecasts have already been created."""
    out = forecast.copy()
    if out.empty:
        return out, pd.DataFrame()
    dep = departures.copy()
    dep["baseline_departure_time"] = pd.to_datetime(dep["baseline_departure_time"], errors="coerce")
    dep = dep.sort_values("baseline_departure_time").reset_index(drop=True)
    used_departures: set[int] = set()
    observed_departures: list[pd.Timestamp | pd.NaT] = []
    matched_indices: list[float] = []

    out = out.sort_values(["decision_time", "mmsi"]).reset_index(drop=True)
    for _, row in out.iterrows():
        decision = pd.Timestamp(row["decision_time"])
        candidates = dep[
            dep["mmsi"].eq(row["mmsi"])
            & dep["origin"].astype(str).str.upper().eq(str(row["origin"]).upper())
            & dep["baseline_departure_time"].gt(decision)
            & dep["baseline_departure_time"].le(
                decision + pd.Timedelta(minutes=float(departure_match_window_min))
            )
        ]
        candidates = candidates.loc[~candidates.index.isin(used_departures)]
        if candidates.empty:
            observed_departures.append(pd.NaT)
            matched_indices.append(np.nan)
            continue
        selected_index = int(candidates.index[0])
        used_departures.add(selected_index)
        observed_departures.append(pd.Timestamp(dep.at[selected_index, "baseline_departure_time"]))
        matched_indices.append(float(selected_index))

    out["observed_departure_time"] = observed_departures
    out["baseline_departure_time"] = out["observed_departure_time"]
    out["matched_departure_index"] = matched_indices
    out["departure_match_status"] = np.where(
        out["observed_departure_time"].notna(), "MATCHED_POSTHOC", "UNMATCHED_RETAINED"
    )
    out["decision_to_observed_departure_min"] = (
        out["observed_departure_time"].sub(out["decision_time"]).dt.total_seconds().div(60)
    )
    out["retrospective_reference_decision_time"] = (
        out["observed_departure_time"] - pd.to_timedelta(float(horizon_min), unit="m")
    )
    out["prospective_minus_retrospective_epoch_min"] = (
        out["decision_time"].sub(out["retrospective_reference_decision_time"]).dt.total_seconds().div(60)
    )
    out["retrospective_reference_used_for_prediction"] = False

    observed_arrivals: list[pd.Timestamp | pd.NaT] = []
    episode_frame = episodes.copy()
    episode_frame["berth_entry_time"] = pd.to_datetime(episode_frame["berth_entry_time"], errors="coerce")
    for _, row in out.iterrows():
        departure = row["observed_departure_time"]
        if pd.isna(departure):
            observed_arrivals.append(pd.NaT)
            continue
        future = episode_frame[
            episode_frame["mmsi"].eq(row["mmsi"])
            & episode_frame["berth_entry_time"].gt(departure)
            & episode_frame["berth_entry_time"].le(
                departure + pd.Timedelta(minutes=float(arrival_match_window_min))
            )
            & episode_frame["port_id"].astype(str).str.upper().eq(str(row["destination"]).upper())
        ]
        observed_arrivals.append(future["berth_entry_time"].min() if not future.empty else pd.NaT)
    out["observed_destination_berth_time"] = observed_arrivals
    out["eta_error_min"] = (
        out["predicted_eta"].sub(out["observed_destination_berth_time"]).dt.total_seconds().div(60)
    )
    out["absolute_eta_error_min"] = out["eta_error_min"].abs()
    out["departure_error_min"] = (
        out["predicted_departure_time"].sub(out["observed_departure_time"]).dt.total_seconds().div(60)
    )
    comparison_columns = [
        "decision_case_id",
        "mmsi",
        "origin",
        "destination",
        "berth_episode_id",
        "decision_time",
        "observed_departure_time",
        "decision_to_observed_departure_min",
        "retrospective_reference_decision_time",
        "prospective_minus_retrospective_epoch_min",
        "departure_match_status",
    ]
    comparison = out[comparison_columns].copy()
    return out, comparison


def _audit_forecast(
    forecast: pd.DataFrame,
    *,
    scan_interval_min: float,
    horizon_min: float,
) -> pd.DataFrame:
    if forecast.empty:
        return pd.DataFrame({"check": ["prospective_cases_nonempty"], "failed_rows": [1]})
    matched = forecast["observed_departure_time"].notna()
    duplicate_episode = forecast.duplicated(["mmsi", "berth_episode_id"], keep=False)
    aligned = _scan_aligned(forecast["decision_time"], scan_interval_min)
    checks = {
        "prospective_cases_nonempty": 0,
        "non_prospective_epoch_mode": int(forecast["decision_epoch_mode"].ne("PROSPECTIVE_FIXED_GRID").sum()),
        "decision_not_on_scan_grid": int((~aligned).sum()),
        "decision_not_at_origin_berth": int(
            (
                ~forecast["is_at_berth"].astype(bool)
                | forecast["operational_phase"].astype(str).str.upper().ne("AT_ORIGIN_TERMINAL")
            ).sum()
        ),
        "duplicate_decision_per_berth_episode": int(duplicate_episode.sum()),
        "observed_departure_used_to_generate_case": int(
            forecast["observed_departure_used_to_generate_case"].astype(bool).sum()
        ),
        "observed_departure_used_in_eta": int(forecast["observed_departure_used_in_eta"].astype(bool).sum()),
        "retrospective_reference_used_for_prediction": int(
            forecast["retrospective_reference_used_for_prediction"].astype(bool).sum()
        ),
        "decision_after_or_equal_matched_departure": int(
            (matched & forecast["decision_time"].ge(forecast["observed_departure_time"])).sum()
        ),
        "trip_history_not_known_at_decision": int(
            (
                forecast["trip_history_latest_time"].notna()
                & forecast["trip_history_latest_time"].ge(forecast["decision_time"])
            ).sum()
        ),
        "non_holdout_case": int(forecast["data_partition"].ne("TEMPORAL_HOLDOUT").sum()),
        "invalid_confidence": int((~forecast["forecast_confidence"].between(0, 1)).sum()),
        "predicted_departure_before_decision": int(
            forecast["predicted_departure_time"].lt(forecast["decision_time"]).sum()
        ),
        "trigger_release_exceeds_horizon": int(
            forecast["trigger_release_lead_min"].gt(float(horizon_min) + 1e-9).sum()
        ),
        "matched_departure_reused": int(
            forecast.loc[matched, "matched_departure_index"].duplicated().sum()
        ),
        "invalid_capacity_source": int(
            (~forecast["capacity_source"].isin(
                ["CURRENT_STATE_PROFILE", "VESSEL_PROFILE_LOOKUP", "PROFILE_MEDIAN_FALLBACK"]
            )).sum()
        ),
    }
    return pd.DataFrame({"check": list(checks.keys()), "failed_rows": list(checks.values())})


def run_stage4(
    state: pd.DataFrame,
    episodes: pd.DataFrame,
    rates: pd.DataFrame,
    profiles: pd.DataFrame,
    berths: pd.DataFrame,
    stage_dir: Path,
    config_dir: Path,
):
    """Run prospective fixed-grid decisions and post-hoc holdout validation."""
    params = _params(config_dir)
    scan_interval = float(
        params.get("decision_scan_interval_min", params.get("grid_interval_min", 5.0))
    )
    horizon = float(params.get("decision_horizon_min", params.get("decision_lead_min", 15.0)))
    operating_start = int(params.get("decision_operating_start_min", 7 * 60))
    operating_end = int(params.get("decision_operating_end_min", 23 * 60 + 55))
    minimum_elapsed = float(params.get("decision_min_elapsed_berth_min", 0.0))
    departure_match_window = float(params.get("departure_match_window_min", 180.0))
    arrival_match_window = float(params.get("arrival_match_window_min", 120.0))
    motor_ce = float(params.get("motorcycle_ce", 0.25))

    state = state.copy()
    state["grid_time"] = pd.to_datetime(state["grid_time"], errors="coerce")
    state["predicted_berth_release_time"] = pd.to_datetime(
        state["predicted_berth_release_time"], errors="coerce"
    )
    episodes = episodes.copy()
    for column in ["berth_entry_time", "observed_end"]:
        episodes[column] = pd.to_datetime(episodes[column], errors="coerce")
    cutoff = _calibration_cutoff(state["grid_time"], int(params.get("evaluation_months", 1)))

    prospective_cases = build_prospective_decision_epochs(
        state,
        cutoff=cutoff,
        scan_interval_min=scan_interval,
        horizon_min=horizon,
        operating_start_min=operating_start,
        operating_end_min=operating_end,
        minimum_elapsed_berth_min=minimum_elapsed,
    )

    departures, departure_audit = _detect_departures(state)
    evaluation_departures = _evaluation_departures(departures, cutoff, operating_start, operating_end)
    queue, event_log, queue_lookup = _build_queue_baseline(
        state,
        evaluation_departures,
        rates,
        profiles,
        cutoff=cutoff,
        motor_ce=motor_ce,
        scan_interval_min=scan_interval,
        operating_start_min=operating_start,
        operating_end_min=operating_end,
    )
    trips = _trip_history(episodes)
    forecast = _predict_from_cases(
        prospective_cases,
        state=state,
        trips=trips,
        evaluation_departures=evaluation_departures,
        queue_lookup=queue_lookup,
        rates=rates,
        profiles=profiles,
        berths=berths,
        params=params,
        cutoff=cutoff,
    )
    forecast, epoch_comparison = attach_posthoc_validation(
        forecast,
        evaluation_departures,
        episodes,
        horizon_min=horizon,
        departure_match_window_min=departure_match_window,
        arrival_match_window_min=arrival_match_window,
    )
    eta_audit = _audit_forecast(forecast, scan_interval_min=scan_interval, horizon_min=horizon)

    matched = forecast["observed_departure_time"].notna() if not forecast.empty else pd.Series(dtype=bool)
    evaluation_days = len(sorted(state.loc[state["grid_time"].gt(cutoff), "grid_time"].dt.date.unique()))
    summary_values = {
        "calibration_end": cutoff,
        "evaluation_days": evaluation_days,
        "ais_departures_used": len(event_log),
        "prospective_decision_cases": len(forecast),
        "predeparture_decisions": len(forecast),
        "matched_departure_cases": int(matched.sum()) if len(matched) else 0,
        "unmatched_departure_cases": int((~matched).sum()) if len(matched) else 0,
        "departure_match_rate_percent": 100.0 * float(matched.mean()) if len(matched) else np.nan,
        "median_decision_to_observed_departure_min": (
            forecast.loc[matched, "decision_to_observed_departure_min"].median()
            if len(matched) and matched.any()
            else np.nan
        ),
        "median_prospective_minus_retrospective_epoch_min": (
            forecast.loc[matched, "prospective_minus_retrospective_epoch_min"].median()
            if len(matched) and matched.any()
            else np.nan
        ),
        "max_queue_ce": queue["queue_ce"].max() if not queue.empty else np.nan,
        "mean_predicted_wait_min": forecast["predicted_wait_min"].mean() if not forecast.empty else np.nan,
        "unavailable_at_eta_rows": int(forecast["predicted_wait_min"].gt(0).sum()) if not forecast.empty else 0,
        "eta_holdout_mae_min": forecast["absolute_eta_error_min"].mean() if not forecast.empty else np.nan,
        "eta_holdout_cases": int(forecast["absolute_eta_error_min"].notna().sum()) if not forecast.empty else 0,
    }
    summary = pd.DataFrame({"metric": list(summary_values.keys()), "value": list(summary_values.values())})

    stage_dir = Path(stage_dir)
    stage_dir.mkdir(parents=True, exist_ok=True)
    queue.to_csv(stage_dir / "04_holdout_port_queue_baseline.csv", index=False)
    queue.to_csv(stage_dir / "04_daily_port_queue_forecast.csv", index=False)
    event_log.to_csv(stage_dir / "04_daily_event_log.csv", index=False)
    prospective_cases.to_csv(stage_dir / "04_prospective_decision_epochs.csv", index=False)
    forecast.to_csv(stage_dir / "04_fuzzy_input.csv", index=False)
    forecast.to_csv(stage_dir / "04_predeparture_forecast.csv", index=False)
    forecast.to_csv(stage_dir / "04_daily_vessel_forecast.csv", index=False)
    epoch_comparison.to_csv(stage_dir / "04_epoch_comparison.csv", index=False)
    forecast[forecast["departure_match_status"].eq("UNMATCHED_RETAINED")].to_csv(
        stage_dir / "04_unmatched_prospective_cases.csv", index=False
    )
    validation_columns = [
        "decision_case_id",
        "mmsi",
        "origin",
        "destination",
        "decision_time",
        "predicted_departure_time",
        "observed_departure_time",
        "departure_error_min",
        "predicted_eta",
        "observed_destination_berth_time",
        "eta_error_min",
        "absolute_eta_error_min",
        "forecast_confidence",
    ]
    forecast.loc[
        forecast["observed_destination_berth_time"].notna(), validation_columns
    ].to_csv(stage_dir / "04_temporal_holdout_validation.csv", index=False)
    summary.to_csv(stage_dir / "04_forecast_summary.csv", index=False)
    summary.to_csv(stage_dir / "04_ais_eta_berth_summary.csv", index=False)
    eta_audit.to_csv(stage_dir / "04_eta_berth_forecast_audit.csv", index=False)
    eta_audit.to_csv(stage_dir / "04_prospective_epoch_audit.csv", index=False)
    departure_audit.to_csv(stage_dir / "04_ais_departure_audit.csv", index=False)
    stage4_forecast_outputs(
        queue,
        forecast,
        event_log,
        summary,
        eta_audit,
        departure_audit,
        stage_dir,
    )
    return queue, event_log, forecast, summary, eta_audit, departure_audit
