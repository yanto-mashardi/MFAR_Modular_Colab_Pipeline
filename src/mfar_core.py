"""Auditable operational logic for MFAR Stages 03–07.

The module enforces temporal separation, pre-departure decision epochs,
configuration-driven fuzzy inference, phase feasibility, and scenario wording.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from .mfar_visuals import (
    stage3_berth_outputs,
    stage4_forecast_outputs,
    stage5_fuzzy_outputs,
    stage6_rule_outputs,
    stage7_intervention_outputs,
)


def _params(config_dir: Path) -> dict[str, float]:
    frame = pd.read_csv(Path(config_dir) / "pipeline_parameters.csv")
    return dict(zip(frame["parameter"], pd.to_numeric(frame["value"], errors="coerce")))


def _calibration_cutoff(timestamps: pd.Series, evaluation_months: int = 1) -> pd.Timestamp:
    """Use complete calendar months; the final month(s) form the holdout."""
    values = pd.to_datetime(timestamps, errors="coerce").dropna()
    holdout_start = values.max().to_period("M").start_time
    for _ in range(max(0, int(evaluation_months) - 1)):
        holdout_start = (holdout_start - pd.offsets.MonthBegin(1)).normalize()
    return holdout_start - pd.Timedelta(nanoseconds=1)


def _phase(status: pd.Series) -> pd.Series:
    text = status.astype(str).str.upper()
    return pd.Series(np.select(
        [text.str.startswith("AT_BERTH"), text.str.startswith("DEPARTING"),
         text.str.contains("SAILING"), text.str.contains("APPROACHING")],
        ["AT_ORIGIN_TERMINAL", "DEPARTING", "SAILING", "APPROACHING_DESTINATION"],
        default="UNKNOWN"), index=status.index)


def _detect_departures(state: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    day = state.sort_values(["mmsi", "grid_time"]).copy()
    group = day.groupby("mmsi", sort=False)
    day["prev_status"] = group["operational_status"].shift()
    day["next_status"] = group["operational_status"].shift(-1)
    day["next_sog"] = group["sog"].shift(-1)
    day["prev_nearest_distance_nm"] = group["nearest_distance_nm"].shift()
    day["next_nearest_distance_nm"] = group["nearest_distance_nm"].shift(-1)
    mask = (
        day["prev_status"].astype(str).str.startswith("AT_BERTH")
        & day["operational_status"].astype(str).str.match(r"DEPARTING|SAILING")
        & pd.to_numeric(day["sog"], errors="coerce").fillna(0).ge(0.8)
        & pd.to_numeric(day["next_sog"], errors="coerce").fillna(0).ge(0.8)
        & pd.to_numeric(day["nearest_distance_nm"], errors="coerce").gt(
            pd.to_numeric(day["prev_nearest_distance_nm"], errors="coerce"))
        & pd.to_numeric(day["next_nearest_distance_nm"], errors="coerce").ge(
            pd.to_numeric(day["nearest_distance_nm"], errors="coerce"))
    )
    events = day.loc[mask].copy()
    events["baseline_departure_time"] = events["grid_time"]
    previous = events.groupby("mmsi")["baseline_departure_time"].shift()
    events = events[previous.isna() | events["baseline_departure_time"].sub(previous).dt.total_seconds().div(60).ge(20)]
    events["event_type"] = "AIS_DEPARTURE"
    audit = pd.DataFrame({
        "check": ["previous_at_berth", "speed_persistence", "distance_increase", "deduplicated_20min"],
        "failed_rows": [
            int((~events["prev_status"].astype(str).str.startswith("AT_BERTH")).sum()),
            int((pd.to_numeric(events["next_sog"], errors="coerce").fillna(0) < .8).sum()),
            int((events["nearest_distance_nm"] <= events["prev_nearest_distance_nm"]).sum()), 0,
        ],
    })
    return events.reset_index(drop=True), audit


def run_stage3(state: pd.DataFrame, profiles: pd.DataFrame, stage_dir: Path, config_dir: Path):
    """Estimate berth service from preceding episodes instead of fixed 40 minutes."""
    params = _params(config_dir)
    grid_min = float(params.get("grid_interval_min", 5))
    maneuver_min = float(params.get("departure_maneuver_min", 5))
    fallback = float(params.get("turnaround_min", 40))
    out = state.copy()
    out["grid_time"] = pd.to_datetime(out["grid_time"], errors="coerce")
    out = out.dropna(subset=["grid_time", "mmsi"]).sort_values(["mmsi", "grid_time"])
    for col in ["vehicle_capacity_ce", "normal_sog_kn", "approach_allowance_min"]:
        if col not in out:
            out = out.merge(profiles[["mmsi", col]], on="mmsi", how="left")
    out["is_at_berth"] = out["operational_status"].astype(str).str.startswith("AT_BERTH")
    start = out["is_at_berth"] & ~out.groupby("mmsi")["is_at_berth"].shift(fill_value=False)
    out["berth_episode_start"] = start
    out["berth_episode_id"] = start.groupby(out["mmsi"]).cumsum().astype(int)
    occupied = out[out["is_at_berth"]].copy()
    episodes = (occupied.groupby(["mmsi", "berth_episode_id"], as_index=False)
                .agg(berth_entry_time=("grid_time", "min"), observed_end=("grid_time", "max"),
                     occupied_berth_id=("current_berth_id", "first"), port_id=("nearest_port_id", "first"),
                     median_bracket_gap_min=("bracket_gap_min", "median"), points=("grid_time", "size")))
    episodes["observed_turnaround_min"] = episodes["observed_end"].sub(episodes["berth_entry_time"]).dt.total_seconds().div(60).add(grid_min)
    episodes = episodes.sort_values(["mmsi", "berth_entry_time"])
    episodes["prior_turnaround_min"] = (episodes.groupby("mmsi")["observed_turnaround_min"]
                                        .transform(lambda s: s.shift().expanding().median()))
    calibration_cutoff = _calibration_cutoff(out["grid_time"], int(params.get("evaluation_months", 1)))
    cal = episodes[episodes["observed_end"] <= calibration_cutoff]
    global_cal = float(cal["observed_turnaround_min"].median()) if not cal.empty else fallback
    episodes["turnaround_estimate_min"] = episodes["prior_turnaround_min"].fillna(global_cal)
    out = out.merge(episodes[["mmsi", "berth_episode_id", "berth_entry_time", "occupied_berth_id",
                              "turnaround_estimate_min"]], on=["mmsi", "berth_episode_id"], how="left")
    out["elapsed_berth_min"] = np.where(out["is_at_berth"], out["grid_time"].sub(out["berth_entry_time"]).dt.total_seconds().div(60), 0)
    out["predicted_remaining_service_min"] = np.where(out["is_at_berth"],
        np.maximum(0, out["turnaround_estimate_min"].fillna(global_cal) - out["elapsed_berth_min"]), 0)
    out["predicted_berth_release_time"] = pd.NaT
    mask = out["is_at_berth"]
    out.loc[mask, "predicted_berth_release_time"] = out.loc[mask, "grid_time"] + pd.to_timedelta(
        out.loc[mask, "predicted_remaining_service_min"] + maneuver_min, unit="m")
    out["operational_phase"] = _phase(out["operational_status"])
    gap = pd.to_numeric(out["bracket_gap_min"], errors="coerce").fillna(20).clip(lower=0)
    out["eta_reliability"] = np.exp(-gap / max(float(params.get("max_interpolation_gap_min", 20)), 1))
    out["berth_duration_reliability"] = out["eta_reliability"] * np.where(out["is_at_berth"], .95, .85)
    empirical = (cal.groupby("mmsi", as_index=False)
                 .agg(turnaround_min=("observed_turnaround_min", "median"),
                      turnaround_p90_min=("observed_turnaround_min", lambda s: s.quantile(.9)),
                      berth_episodes=("berth_episode_id", "size"),
                      median_bracket_gap_min=("median_bracket_gap_min", "median")))
    sailing = out[out["operational_status"].astype(str).str.contains("SAILING")].groupby("mmsi")["sog"].median()
    empirical["normal_sog_kn"] = empirical["mmsi"].map(sailing)
    empirical["eta_reliability"] = np.exp(-empirical["median_bracket_gap_min"].fillna(20) / 20)
    empirical["calibration_cutoff"] = calibration_cutoff
    stage_dir = Path(stage_dir); stage_dir.mkdir(parents=True, exist_ok=True)
    out.to_csv(stage_dir / "03_input_state_enhanced.csv", index=False)
    episodes.to_csv(stage_dir / "03_berth_episode_history.csv", index=False)
    empirical.to_csv(stage_dir / "03_vessel_empirical_profiles.csv", index=False)
    release = out.loc[mask, ["grid_time", "mmsi", "origin", "occupied_berth_id", "berth_entry_time",
                             "elapsed_berth_min", "predicted_remaining_service_min", "predicted_berth_release_time",
                             "turnaround_estimate_min", "eta_reliability", "berth_duration_reliability"]]
    release.to_csv(stage_dir / "03_predicted_berth_release_state.csv", index=False)
    audit = pd.DataFrame({"check": ["missing_release", "negative_elapsed", "negative_remaining", "duplicate_vessel_time", "future_episode_duration_used"],
                          "failed_rows": [int(out.loc[mask, "predicted_berth_release_time"].isna().sum()),
                                          int((out["elapsed_berth_min"] < 0).sum()),
                                          int((out["predicted_remaining_service_min"] < 0).sum()),
                                          int(out.duplicated(["grid_time", "mmsi"]).sum()), 0]})
    audit.to_csv(stage_dir / "03_berth_prediction_audit.csv", index=False)
    stage3_berth_outputs(out, audit, stage_dir)
    return out, episodes, empirical, audit, calibration_cutoff


def _arrival_rate(rates: pd.DataFrame, port: str, stamp: pd.Timestamp, motor_ce: float) -> tuple[float, float, float]:
    hhmm = stamp.strftime("%H:%M")
    rows = rates[rates["port_id"].astype(str).str.upper().eq(str(port).upper())]
    for _, row in rows.iterrows():
        end = str(row["time_end"])
        valid = hhmm >= str(row["time_start"]) if end == "24:00" else str(row["time_start"]) <= hhmm < end
        if valid:
            car = float(row["car_arrival_rate_30min"]) / 6
            motor = float(row["motorcycle_arrival_rate_30min"]) / 6
            return car, motor, car + motor_ce * motor
    return 0., 0., 0.


def _earliest_berth_slot(
    eta: pd.Timestamp,
    service_min: float,
    current_release: pd.Timestamp,
    prior_reservations: list[tuple[pd.Timestamp, pd.Timestamp]],
) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Find the earliest non-overlapping berth interval using known reservations."""
    start = max(pd.Timestamp(eta), pd.Timestamp(current_release))
    duration = pd.Timedelta(minutes=max(float(service_min), 1.0))
    for reserved_start, reserved_end in sorted(prior_reservations, key=lambda item: item[0]):
        reserved_start, reserved_end = pd.Timestamp(reserved_start), pd.Timestamp(reserved_end)
        if start + duration <= reserved_start:
            break
        if start < reserved_end and start + duration > reserved_start:
            start = reserved_end
    return start, start + duration


def run_stage4(state: pd.DataFrame, episodes: pd.DataFrame, rates: pd.DataFrame, profiles: pd.DataFrame,
               berths: pd.DataFrame, stage_dir: Path, config_dir: Path):
    """Run temporal-holdout, pre-departure forecasts over every evaluation day."""
    params = _params(config_dir)
    motor_ce = float(params.get("motorcycle_ce", .25))
    decision_lead = float(params.get("decision_lead_min", 15))
    fallback_trip = float(params.get("fallback_trip_min", 45))
    state = state.copy(); state["grid_time"] = pd.to_datetime(state["grid_time"], errors="coerce")
    episodes = episodes.copy(); episodes[["berth_entry_time", "observed_end"]] = episodes[["berth_entry_time", "observed_end"]].apply(pd.to_datetime, errors="coerce")
    departures, departure_audit = _detect_departures(state)
    cutoff = _calibration_cutoff(state["grid_time"], int(params.get("evaluation_months", 1)))
    evaluation_departures = departures[departures["baseline_departure_time"] > cutoff].copy()
    minute_of_day = evaluation_departures["baseline_departure_time"].dt.hour * 60 + evaluation_departures["baseline_departure_time"].dt.minute
    evaluation_departures = (evaluation_departures[minute_of_day.between(7 * 60, 23 * 60 + 55)]
                              .sort_values("baseline_departure_time").copy())
    dates = sorted(state.loc[state["grid_time"] > cutoff, "grid_time"].dt.date.unique())
    ports = sorted(rates["port_id"].astype(str).str.upper().unique())
    capacity = float(profiles["vehicle_capacity_ce"].median())
    queues, event_log = [], []
    queue_lookup = {}
    for date in dates:
        q = {p: {"car": 0., "motor": 0.} for p in ports}
        times = pd.date_range(pd.Timestamp(date) + pd.Timedelta(hours=7), pd.Timestamp(date) + pd.Timedelta(hours=23, minutes=55), freq="5min")
        day_events = evaluation_departures[evaluation_departures["baseline_departure_time"].dt.date == date]
        for stamp in times:
            for port in ports:
                car, motor, _ = _arrival_rate(rates, port, stamp, motor_ce)
                q[port]["car"] += car; q[port]["motor"] += motor
            for _, event in day_events[day_events["baseline_departure_time"].eq(stamp)].iterrows():
                port = str(event["origin"]).upper()
                if port not in q: continue
                available = q[port]["car"] + motor_ce * q[port]["motor"]
                cap = float(event.get("vehicle_capacity_ce", capacity) or capacity)
                served = min(cap, available)
                served_car = min(q[port]["car"], served); q[port]["car"] -= served_car
                remaining = served - served_car
                if remaining > 0: q[port]["motor"] = max(0, q[port]["motor"] - remaining / motor_ce)
                event_log.append({"simulation_time": stamp, "mmsi": event["mmsi"], "origin": port,
                                  "destination": event["destination"], "capacity_ce": cap, "served_ce": served,
                                  "event_type": "AIS_DEPARTURE", "source": "temporal_holdout"})
            for port in ports:
                ce = q[port]["car"] + motor_ce * q[port]["motor"]
                row = {"simulation_time": stamp, "port_id": port, "queue_car": q[port]["car"],
                       "queue_motorcycle": q[port]["motor"], "queue_ce": ce, "queue_ratio": ce / capacity,
                       "evaluation_date": date}
                queues.append(row); queue_lookup[(stamp, port)] = row
    queue = pd.DataFrame(queues); event_log = pd.DataFrame(event_log)

    trips = []
    for mmsi, group in episodes.sort_values("berth_entry_time").groupby("mmsi"):
        rows = group.reset_index(drop=True)
        for idx in range(len(rows) - 1):
            a, b = rows.iloc[idx], rows.iloc[idx + 1]
            if a["port_id"] == b["port_id"]: continue
            duration = (b["berth_entry_time"] - a["observed_end"]).total_seconds() / 60
            if 10 <= duration <= 120:
                trips.append({"mmsi": mmsi, "origin": str(a["port_id"]), "destination": str(b["port_id"]),
                              "trip_min": duration, "known_at": b["berth_entry_time"]})
    trips = pd.DataFrame(trips)
    forecasts = []
    berth_reservations: dict[str, list[tuple[pd.Timestamp, pd.Timestamp]]] = {
        str(berth_id): [] for berth_id in berths["berth_id"].astype(str)
    }
    for _, event in evaluation_departures.iterrows():
        dep = event["baseline_departure_time"]
        decision = dep - pd.Timedelta(minutes=decision_lead)
        candidates = state[(state["mmsi"] == event["mmsi"]) & (state["grid_time"] <= decision)]
        if candidates.empty: continue
        snap = candidates.iloc[-1]
        origin, destination = str(event["origin"]).upper(), str(event["destination"]).upper()
        history = trips[(trips["known_at"] < decision) & (trips["origin"].astype(str).str.upper() == origin)
                        & (trips["destination"].astype(str).str.upper() == destination)] if not trips.empty else pd.DataFrame()
        sailing_min = float(history["trip_min"].median()) if not history.empty else fallback_trip
        release = pd.to_datetime(snap.get("predicted_berth_release_time"), errors="coerce")
        earliest_configured = decision + pd.Timedelta(minutes=decision_lead)
        predicted_departure = max(earliest_configured, release) if pd.notna(release) else earliest_configured
        departure_source = "BERTH_RELEASE_ESTIMATE" if pd.notna(release) and release > earliest_configured else "CONFIGURED_DECISION_LEAD"
        eta = predicted_departure + pd.Timedelta(minutes=sailing_min + float(snap.get("approach_allowance_min", 5)))
        at_decision = state[state["grid_time"].eq(decision) & state["is_at_berth"].astype(bool)]
        releases = {}
        for berth_id in berths.loc[berths["port_id"].astype(str).str.upper().eq(destination), "berth_id"].astype(str):
            occ = at_decision[at_decision["current_berth_id"].astype(str).eq(berth_id)]
            releases[berth_id] = occ["predicted_berth_release_time"].max() if not occ.empty else decision
        if not releases: continue
        service_min = float(snap.get("turnaround_estimate_min", params.get("turnaround_min", 40))
                            or params.get("turnaround_min", 40))
        candidate_slots = {
            berth_id: _earliest_berth_slot(
                eta, service_min, pd.Timestamp(release_time), berth_reservations.get(berth_id, []),
            )
            for berth_id, release_time in releases.items()
        }
        selected = min(candidate_slots, key=lambda key: candidate_slots[key][0])
        available, service_end = candidate_slots[selected]
        berth_reservations.setdefault(selected, []).append((available, service_end))
        wait = max(0., (available - eta).total_seconds() / 60)
        origin_q = queue_lookup.get((decision.floor("5min"), origin), {"queue_ratio": 0})["queue_ratio"]
        dest_q = queue_lookup.get((decision.floor("5min"), destination), {"queue_ratio": 0})["queue_ratio"]
        prior = evaluation_departures[(evaluation_departures["origin"].astype(str).str.upper() == origin)
                                      & (evaluation_departures["baseline_departure_time"] < decision)]
        service_gap = (decision - prior["baseline_departure_time"].max()).total_seconds() / 60 if not prior.empty else 180.
        future_arrivals = sum(_arrival_rate(rates, origin, decision.floor("5min") + pd.Timedelta(minutes=i), motor_ce)[2]
                              for i in range(0, 60, 5))
        shortfall = max(0., future_arrivals - float(event.get("vehicle_capacity_ce", capacity) or capacity))
        reliability = float(snap.get("eta_reliability", .5)) * float(snap.get("berth_duration_reliability", .5))
        forecasts.append({**snap.to_dict(), "simulation_time": decision, "decision_time": decision,
                          "baseline_departure_time": dep, "event_type": "PRE_DEPARTURE_DECISION",
                          "predicted_departure_time": predicted_departure,
                          "departure_prediction_source": departure_source,
                          "observed_departure_used_in_eta": False,
                          "trip_history_latest_time": history["known_at"].max() if not history.empty else pd.NaT,
                          "operational_phase": _phase(pd.Series([snap["operational_status"]])).iloc[0],
                          "capacity_ce": float(event.get("vehicle_capacity_ce", capacity) or capacity),
                          "predicted_eta": eta, "assigned_destination_berth": selected,
                          "predicted_berth_available_time_at_eta": available,
                          "predicted_berth_service_start": available,
                          "predicted_berth_service_end": service_end,
                          "berth_service_duration_min": service_min,
                          "predicted_wait_min": wait,
                          "berth_availability_at_eta": float(wait == 0), "origin_queue_ratio": origin_q,
                          "destination_queue_ratio": dest_q, "forecast_confidence": reliability,
                          "service_gap_min": service_gap, "capacity_shortfall_ratio": shortfall / capacity,
                          "calibration_cutoff": cutoff, "data_partition": "TEMPORAL_HOLDOUT"})
    forecast = pd.DataFrame(forecasts)
    observed_arrivals = []
    for _, row in forecast.iterrows():
        future = episodes[(episodes["mmsi"] == row["mmsi"])
                          & (episodes["berth_entry_time"] > row["baseline_departure_time"])
                          & (episodes["berth_entry_time"] <= row["baseline_departure_time"] + pd.Timedelta(minutes=120))
                          & (episodes["port_id"].astype(str).str.upper() == str(row["destination"]).upper())]
        observed_arrivals.append(future["berth_entry_time"].min() if not future.empty else pd.NaT)
    forecast["observed_destination_berth_time"] = observed_arrivals
    forecast["eta_error_min"] = (forecast["predicted_eta"] - forecast["observed_destination_berth_time"]).dt.total_seconds().div(60)
    forecast["absolute_eta_error_min"] = forecast["eta_error_min"].abs()
    forecast["departure_error_min"] = forecast["predicted_departure_time"].sub(
        forecast["baseline_departure_time"]).dt.total_seconds().div(60)
    stage_dir = Path(stage_dir); stage_dir.mkdir(parents=True, exist_ok=True)
    queue.to_csv(stage_dir / "04_holdout_port_queue_baseline.csv", index=False)
    queue.to_csv(stage_dir / "04_daily_port_queue_forecast.csv", index=False)
    event_log.to_csv(stage_dir / "04_daily_event_log.csv", index=False)
    forecast.to_csv(stage_dir / "04_fuzzy_input.csv", index=False)
    forecast.to_csv(stage_dir / "04_predeparture_forecast.csv", index=False)
    forecast.loc[forecast["observed_destination_berth_time"].notna(), [
        "mmsi", "origin", "destination", "decision_time", "predicted_departure_time",
        "baseline_departure_time", "departure_error_min", "predicted_eta",
        "observed_destination_berth_time", "eta_error_min", "absolute_eta_error_min", "forecast_confidence"
    ]].to_csv(stage_dir / "04_temporal_holdout_validation.csv", index=False)
    forecast.to_csv(stage_dir / "04_daily_vessel_forecast.csv", index=False)
    summary = pd.DataFrame({"metric": ["calibration_end", "evaluation_days", "ais_departures_used", "predeparture_decisions",
                                                   "max_queue_ce", "mean_predicted_wait_min", "unavailable_at_eta_rows",
                                                   "eta_holdout_mae_min", "eta_holdout_cases"],
                            "value": [cutoff, len(dates), len(event_log), len(forecast), queue["queue_ce"].max(),
                                      forecast["predicted_wait_min"].mean(), (forecast["predicted_wait_min"] > 0).sum(),
                                      forecast["absolute_eta_error_min"].mean(), forecast["absolute_eta_error_min"].notna().sum()]})
    summary.to_csv(stage_dir / "04_forecast_summary.csv", index=False)
    summary.to_csv(stage_dir / "04_ais_eta_berth_summary.csv", index=False)
    eta_audit = pd.DataFrame({"check": ["decision_after_departure", "observed_departure_used_as_prediction",
                                                     "trip_history_not_known_at_decision", "non_holdout_case", "invalid_confidence"],
                              "failed_rows": [int((forecast["decision_time"] >= forecast["baseline_departure_time"]).sum()),
                                              int(forecast["observed_departure_used_in_eta"].astype(bool).sum()),
                                              int((forecast["trip_history_latest_time"].notna()
                                                   & (forecast["trip_history_latest_time"] >= forecast["decision_time"])).sum()),
                                              int((forecast["data_partition"] != "TEMPORAL_HOLDOUT").sum()),
                                              int((~forecast["forecast_confidence"].between(0, 1)).sum())]})
    eta_audit.to_csv(stage_dir / "04_eta_berth_forecast_audit.csv", index=False)
    departure_audit.to_csv(stage_dir / "04_ais_departure_audit.csv", index=False)
    stage4_forecast_outputs(queue, forecast, event_log, summary, eta_audit, departure_audit, stage_dir)
    return queue, event_log, forecast, summary, eta_audit, departure_audit


def _membership(values, function: str, a: float, b: float, c: float, d: float):
    x = np.asarray(values, dtype=float)
    if function == "left_shoulder":
        return np.where(x <= b, 1., np.where(x >= c, 0., (c - x) / max(c - b, 1e-9)))
    if function == "right_shoulder":
        return np.where(x <= b, 0., np.where(x >= c, 1., (x - b) / max(c - b, 1e-9)))
    if function == "triangle":
        return np.maximum(0, np.minimum((x - a) / max(b - a, 1e-9), (c - x) / max(c - b, 1e-9)))
    if function == "trapezoid":
        return np.maximum(0, np.minimum(np.minimum((x - a) / max(b - a, 1e-9), 1), (d - x) / max(d - c, 1e-9)))
    if function == "identity": return np.clip(x, 0, 1)
    if function == "complement": return 1 - np.clip(x, 0, 1)
    raise ValueError(f"Unsupported membership function: {function}")


def run_stage5(forecast: pd.DataFrame, stage_dir: Path, config_dir: Path):
    definitions = pd.read_csv(Path(config_dir) / "membership_parameters.csv")
    input_definitions = definitions[
        definitions.get("scope", pd.Series("input", index=definitions.index)).astype(str).str.lower().ne("output")
    ].copy()
    out = forecast.copy()
    for _, row in input_definitions.iterrows():
        column = str(row["input_column"]); membership = str(row["membership_column"])
        if column not in out: raise KeyError(f"Membership input missing: {column}")
        values = pd.to_numeric(out[column], errors="coerce").fillna(0)
        out[membership] = _membership(values, str(row["function"]),
                                      float(row.get("a", 0) or 0), float(row.get("b", 0) or 0),
                                      float(row.get("c", 0) or 0), float(row.get("d", 0) or 0))
    mu = out.filter(regex=r"^mu_")
    audit = pd.DataFrame({"check": ["below_zero", "above_one", "missing_membership", "configuration_rows_applied"],
                          "failed_rows": [int((mu < 0).sum().sum()), int((mu > 1).sum().sum()), int(mu.isna().sum().sum()),
                                          int(len(mu.columns) != len(input_definitions))]})
    stage_dir = Path(stage_dir); out.to_csv(stage_dir / "05_fuzzy_memberships.csv", index=False)
    audit.to_csv(stage_dir / "05_fuzzification_audit.csv", index=False)
    definitions.to_csv(stage_dir / "05_membership_configuration_used.csv", index=False)
    import matplotlib.pyplot as plt
    plot_names = {
        "origin_queue_ratio": "05_membership_queue_ratio.png",
        "predicted_wait_min": "05_membership_predicted_wait.png",
        "service_gap_min": "05_membership_service_gap.png",
    }
    for input_column, filename in plot_names.items():
        subset = input_definitions[input_definitions["input_column"] == input_column]
        if subset.empty:
            continue
        maximum = max(
            float(subset[["a", "b", "c", "d"]].max().max()),
            float(pd.to_numeric(out[input_column], errors="coerce").quantile(.99)),
        )
        x = np.linspace(0, max(maximum, 1), 400)
        fig, axis = plt.subplots(figsize=(9, 5))
        for _, definition in subset.iterrows():
            y = _membership(
                x, str(definition["function"]), float(definition["a"]),
                float(definition["b"]), float(definition["c"]), float(definition["d"]),
            )
            axis.plot(x, y, label=str(definition["membership_column"]).replace("mu_", ""))
        axis.set(xlabel=input_column, ylabel="Membership degree", ylim=(-.02, 1.02))
        axis.grid(True, alpha=.25)
        axis.legend()
        fig.tight_layout()
        fig.savefig(stage_dir / filename, dpi=180)
        plt.close(fig)
    stage5_fuzzy_outputs(out, audit, stage_dir)
    return out, definitions, audit


def run_stage6(memberships: pd.DataFrame, stage_dir: Path, config_dir: Path):
    rules = pd.read_csv(Path(config_dir) / "fuzzy_rules.csv")
    constraints = pd.read_csv(Path(config_dir) / "action_constraints.csv")
    definitions = pd.read_csv(Path(config_dir) / "membership_parameters.csv")
    output_definitions = definitions[
        definitions.get("scope", pd.Series("input", index=definitions.index)).astype(str).str.lower().eq("output")
    ].copy()
    if output_definitions.empty:
        raise ValueError("Output membership definitions for Mamdani inference are missing")
    universe = np.linspace(0.0, 100.0, 1001)
    output_curves = {
        str(row["membership_column"]): _membership(
            universe, str(row["function"]), float(row.get("a", 0) or 0),
            float(row.get("b", 0) or 0), float(row.get("c", 0) or 0),
            float(row.get("d", 0) or 0),
        )
        for _, row in output_definitions.iterrows()
    }
    out = memberships.copy()
    action_constraints = constraints.assign(action=constraints["action"].astype(str).str.upper())
    results = []
    for _, case in out.iterrows():
        fired = []
        for _, rule in rules.iterrows():
            ants = [str(rule[c]) for c in ["antecedent_1", "antecedent_2", "antecedent_3", "antecedent_4"]
                    if c in rule and pd.notna(rule[c]) and str(rule[c]).strip()]
            vals = [float(case.get(a, 0)) for a in ants]
            raw_strength = (min(vals) if str(rule["operator"]).upper() == "MIN" else max(vals)) if vals else 0.
            raw_strength *= float(rule.get("weight", 1))
            action = str(rule["response"]).upper()
            phase = str(case.get("operational_phase", "UNKNOWN")).upper()
            feasible = action_constraints[(action_constraints["phase"].astype(str).str.upper() == phase)
                                          & (action_constraints["action"] == action)]
            is_feasible = bool(len(feasible) and int(feasible.iloc[0]["feasible"]) == 1)
            consequence = str(rule["consequence"])
            fired.append((str(rule["rule_id"]), action, raw_strength,
                          raw_strength if is_feasible else 0., int(rule.get("priority", 0)),
                          is_feasible, consequence))
        action_scores = {}
        for rid, action, raw_strength, feasible_strength, priority, feasible, consequence in fired:
            candidate = (feasible_strength, priority, rid)
            if action not in action_scores or candidate > action_scores[action]: action_scores[action] = candidate
        ranked = sorted(((score[0], score[1], action, score[2]) for action, score in action_scores.items()), reverse=True)
        if not ranked or ranked[0][0] <= 0: selected = (1., 0, "NO_INTERVENTION", "DEFAULT")
        else: selected = ranked[0]
        aggregate = np.zeros_like(universe)
        consequence_strengths = {}
        for rid, action, raw_strength, feasible_strength, priority, feasible, consequence in fired:
            key = f"mu_risk_{consequence.strip().lower()}"
            if key not in output_curves:
                raise KeyError(f"Mamdani consequence membership missing: {key}")
            aggregate = np.maximum(aggregate, np.minimum(raw_strength, output_curves[key]))
            consequence_strengths[consequence] = max(consequence_strengths.get(consequence, 0.0), raw_strength)
        area = float(np.trapezoid(aggregate, universe))
        risk_score = float(np.trapezoid(universe * aggregate, universe) / area) if area > 0 else 0.0
        dominant_consequence = max(consequence_strengths, key=consequence_strengths.get) if consequence_strengths else "Normal"
        result = {f"firing_{rid}": feasible_strength for rid, _, _, feasible_strength, _, _, _ in fired}
        result.update({f"raw_firing_{rid}": raw_strength for rid, _, raw_strength, _, _, _, _ in fired})
        result.update({"selected_rule_strength": selected[0], "selected_action": selected[2],
                       "dominant_rule": selected[3], "phase_constraint_applied": True,
                       "infeasible_rule_count": sum((not feasible) and raw_strength > 0
                                                    for _, _, raw_strength, _, _, feasible, _ in fired),
                       "mamdani_risk_score": risk_score, "mamdani_aggregate_area": area,
                       "dominant_risk_consequence": dominant_consequence,
                       "defuzzification_method": "CENTROID"})
        results.append(result)
    out = pd.concat([out.reset_index(drop=True), pd.DataFrame(results)], axis=1)
    stage_dir = Path(stage_dir); out.to_csv(stage_dir / "06_rule_evaluation.csv", index=False)
    catalog = rules.copy(); catalog.to_csv(stage_dir / "06_fuzzy_rule_catalog.csv", index=False)
    summary = pd.DataFrame([{"rule_id": rid, "active_rows": int((out[f"firing_{rid}"] > 0).sum()),
                             "mean_firing_strength": float(out[f"firing_{rid}"].mean()),
                             "max_firing_strength": float(out[f"firing_{rid}"].max())} for rid in rules["rule_id"]])
    summary.to_csv(stage_dir / "06_rule_firing_summary.csv", index=False)
    constraints.to_csv(stage_dir / "06_action_constraints_used.csv", index=False)
    output_definitions.to_csv(stage_dir / "06_output_membership_configuration_used.csv", index=False)
    stage6_rule_outputs(out, catalog, summary, stage_dir)
    return out, catalog, summary


def run_stage7(queue: pd.DataFrame, events: pd.DataFrame, evaluated: pd.DataFrame, rates: pd.DataFrame,
               profiles: pd.DataFrame, stage_dir: Path, config_dir: Path):
    """Evaluate configured actions as a scenario; never label it empirical validation."""
    params = _params(config_dir); constraints = pd.read_csv(Path(config_dir) / "action_constraints.csv")
    constraints["action"] = constraints["action"].astype(str).str.upper()
    threshold = float(params.get("minimum_rule_strength", .35)); motor_ce = float(params.get("motorcycle_ce", .25))
    capacity = float(profiles["vehicle_capacity_ce"].median())
    candidates = evaluated[(evaluated["selected_rule_strength"] >= threshold)
                           & (evaluated["selected_action"] != "NO_INTERVENTION")].sort_values("simulation_time").copy()
    accepted, last = [], {}
    for _, row in candidates.iterrows():
        cfg = constraints[(constraints["phase"].astype(str).str.upper() == str(row["operational_phase"]).upper())
                          & (constraints["action"] == str(row["selected_action"]).upper())]
        if cfg.empty or int(cfg.iloc[0]["feasible"]) != 1: continue
        key = (str(row["origin"]), str(row["selected_action"])); cooldown = float(cfg.iloc[0]["cooldown_min"])
        if key in last and (row["simulation_time"] - last[key]).total_seconds() / 60 < cooldown: continue
        enriched = row.to_dict(); enriched.update(cfg.iloc[0].to_dict()); accepted.append(enriched); last[key] = row["simulation_time"]
    accepted = pd.DataFrame(accepted)
    baseline_services = events[["simulation_time", "origin", "served_ce", "mmsi"]].copy()
    baseline_services["port_id"] = baseline_services["origin"].astype(str)
    scenario_services = baseline_services.copy(); scenario_services["action"] = "BASELINE"
    effects = []
    for _, row in accepted.iterrows():
        effect = str(row.get("effect_type", "none")); action = str(row["selected_action"])
        if effect == "shift_existing_service":
            mask = (scenario_services["mmsi"] == row["mmsi"]) & (scenario_services["port_id"] == str(row["origin"]))
            future = scenario_services[mask & (scenario_services["simulation_time"] >= row["simulation_time"])].sort_values("simulation_time")
            if future.empty: continue
            idx = future.index[0]; old = scenario_services.loc[idx, "simulation_time"]
            new = old + pd.Timedelta(minutes=float(row.get("time_shift_min", 0)))
            scenario_services.loc[idx, "simulation_time"] = new.ceil("5min"); scenario_services.loc[idx, "action"] = action
            effects.append({"simulation_time": new.ceil("5min"), "port_id": row["origin"], "action": action,
                            "effect_type": effect, "served_capacity_ce": scenario_services.loc[idx, "served_ce"], "replaces_time": old})
        elif effect == "extra_service":
            stamp = row["simulation_time"] + pd.Timedelta(minutes=float(row.get("lead_time_min", 0)))
            cap = capacity * float(row.get("capacity_multiplier", 0)) * float(row["selected_rule_strength"])
            newrow = {"simulation_time": stamp.ceil("5min"), "origin": row["origin"], "port_id": row["origin"],
                      "served_ce": cap, "mmsi": np.nan, "action": action}
            scenario_services = pd.concat([scenario_services, pd.DataFrame([newrow])], ignore_index=True)
            effects.append({"simulation_time": stamp.ceil("5min"), "port_id": row["origin"], "action": action,
                            "effect_type": effect, "served_capacity_ce": cap, "replaces_time": pd.NaT})
    effects = pd.DataFrame(effects)
    rows = []
    for (date, port), group in queue.groupby([queue["simulation_time"].dt.date, "port_id"]):
        qb = qa = 0.
        for stamp in group.sort_values("simulation_time")["simulation_time"]:
            _, _, arrivals = _arrival_rate(rates, port, stamp, motor_ce)
            base = baseline_services[(baseline_services["port_id"] == port) & (baseline_services["simulation_time"] == stamp)]["served_ce"].sum()
            scen = scenario_services[(scenario_services["port_id"] == port) & (scenario_services["simulation_time"] == stamp)]["served_ce"].sum()
            qb = max(0., qb + arrivals - base); qa = max(0., qa + arrivals - scen)
            rows.append({"simulation_time": stamp, "evaluation_date": date, "port_id": port, "arrival_ce": arrivals,
                         "baseline_service_ce": base, "scenario_service_ce": scen, "queue_ce": qb,
                         "queue_ce_after": qa, "queue_ratio": qb / capacity, "queue_ratio_after": qa / capacity})
    sim = pd.DataFrame(rows)
    sim["intervention_service_ce"] = sim["scenario_service_ce"] - sim["baseline_service_ce"]
    sim["critical_baseline"] = sim["queue_ratio"] >= 3; sim["critical_after"] = sim["queue_ratio_after"] >= 3
    sim["critical_case_status"] = np.select([sim["critical_baseline"] & ~sim["critical_after"],
                                              sim["critical_baseline"] & sim["critical_after"],
                                              ~sim["critical_baseline"] & sim["critical_after"]],
                                             ["RESOLVED", "REMAINING", "NEW"], default="SAFE")
    daily = (sim.groupby(["evaluation_date", "port_id"], as_index=False)
             .agg(max_queue_baseline_ce=("queue_ce", "max"), max_queue_after_ce=("queue_ce_after", "max"),
                  mean_queue_baseline_ce=("queue_ce", "mean"), mean_queue_after_ce=("queue_ce_after", "mean"),
                  critical_duration_baseline_min=("critical_baseline", lambda s: int(s.sum() * 5)),
                  critical_duration_after_min=("critical_after", lambda s: int(s.sum() * 5))))
    daily["queue_area_reduction_percent"] = 100 * (daily["mean_queue_baseline_ce"] - daily["mean_queue_after_ce"]) / daily["mean_queue_baseline_ce"].replace(0, np.nan)
    overall = pd.DataFrame({"metric": ["evaluation_type", "evaluation_days", "operational_recommendations_accepted",
                                                    "queue_effect_events", "total_critical_baseline", "total_critical_after",
                                                    "median_daily_queue_area_reduction_percent", "days_queue_improved_percent"],
                            "value": ["SCENARIO_EVALUATION_NOT_EMPIRICAL_VALIDATION", daily["evaluation_date"].nunique(), len(accepted),
                                      len(effects), int(sim["critical_baseline"].sum()), int(sim["critical_after"].sum()),
                                      daily["queue_area_reduction_percent"].median(),
                                      100 * daily["queue_area_reduction_percent"].gt(0).mean()]})
    stage_dir = Path(stage_dir)
    stage_dir.mkdir(parents=True, exist_ok=True)
    for obsolete_name in [
        "07_full_day_baseline_vs_intervention.csv",
        "07_accepted_intervention_events.csv",
        "07_daily_validation_by_port.csv",
        "07_overall_intervention_validation.csv",
        "07_intervention_validation_dashboard.html",
    ]:
        obsolete = stage_dir / obsolete_name
        if obsolete.exists():
            obsolete.unlink()
    sim.to_csv(stage_dir / "07_scenario_baseline_vs_actions.csv", index=False)
    accepted.to_csv(stage_dir / "07_accepted_operational_recommendations.csv", index=False)
    effects.to_csv(stage_dir / "07_queue_service_intervention_events.csv", index=False)
    daily.to_csv(stage_dir / "07_daily_scenario_by_port.csv", index=False)
    overall.to_csv(stage_dir / "07_overall_scenario_evaluation.csv", index=False)
    stage7_intervention_outputs(sim, accepted, effects, daily, overall, stage_dir)
    return sim, accepted, effects, daily, overall
