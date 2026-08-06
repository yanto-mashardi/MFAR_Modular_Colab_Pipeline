"""Runtime adapter for Prompt 3 prospective Stage 04.

The adapter enforces three contracts:
1. the trigger uses a fixed-grid scan of contemporaneous state only;
2. future episode outcomes are removed before forecast and fuzzy inference;
3. post-hoc validation matches only the departure adjacent to the same episode.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import mfar_prospective_forecast as implementation

_ORIGINAL_BUILD_EPOCHS = implementation.build_prospective_decision_epochs
_FUTURE_EPISODE_OUTCOME_COLUMNS = [
    "episode_class",
    "eligible_for_turnaround_calibration",
    "entry_observed",
    "exit_observed",
]


def build_prospective_decision_epochs(*args, **kwargs) -> pd.DataFrame:
    """Generate epochs and remove current-episode outcomes known only in hindsight."""
    out = _ORIGINAL_BUILD_EPOCHS(*args, **kwargs)
    removed = [column for column in _FUTURE_EPISODE_OUTCOME_COLUMNS if column in out.columns]
    out = out.drop(columns=removed, errors="ignore")
    out["prospective_feature_contract"] = "CURRENT_STATE_ONLY"
    out["future_episode_outcome_columns_removed"] = (
        ",".join(removed) if removed else "NONE_PRESENT"
    )
    return out


def attach_posthoc_validation(
    forecast: pd.DataFrame,
    departures: pd.DataFrame,
    episodes: pd.DataFrame,
    *,
    horizon_min: float,
    departure_match_window_min: float,
    arrival_match_window_min: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Attach future observations using the originating berth episode as anchor."""
    out = forecast.copy()
    if out.empty:
        return out, pd.DataFrame()

    dep = departures.copy()
    dep["baseline_departure_time"] = pd.to_datetime(
        dep["baseline_departure_time"], errors="coerce"
    )
    dep = dep.sort_values("baseline_departure_time").reset_index(drop=True)

    episode_frame = episodes.copy()
    for column in ["berth_entry_time", "observed_end", "observed_release_time"]:
        if column in episode_frame.columns:
            episode_frame[column] = pd.to_datetime(episode_frame[column], errors="coerce")
    episode_frame["mmsi"] = pd.to_numeric(
        episode_frame["mmsi"], errors="coerce"
    ).astype("Int64")
    episode_frame["berth_episode_id"] = pd.to_numeric(
        episode_frame["berth_episode_id"], errors="coerce"
    ).astype("Int64")

    tolerance = pd.Timedelta(minutes=max(float(departure_match_window_min), 0.0))
    used_departures: set[int] = set()
    observed_departures: list[pd.Timestamp | pd.NaT] = []
    matched_indices: list[float] = []
    episode_release_times: list[pd.Timestamp | pd.NaT] = []
    release_deltas: list[float] = []
    match_reasons: list[str] = []

    out = out.sort_values(["decision_time", "mmsi"]).reset_index(drop=True)
    for _, row in out.iterrows():
        decision = pd.Timestamp(row["decision_time"])
        mmsi = int(row["mmsi"])
        episode_id = int(row["berth_episode_id"])
        episode = episode_frame[
            episode_frame["mmsi"].eq(mmsi)
            & episode_frame["berth_episode_id"].eq(episode_id)
        ]
        if episode.empty:
            observed_departures.append(pd.NaT)
            matched_indices.append(np.nan)
            episode_release_times.append(pd.NaT)
            release_deltas.append(np.nan)
            match_reasons.append("EPISODE_NOT_IN_QUALITY_GATED_HISTORY")
            continue

        episode_row = episode.sort_values("berth_entry_time").iloc[0]
        release = pd.to_datetime(
            episode_row.get("observed_release_time"), errors="coerce"
        )
        if pd.isna(release):
            observed_end = pd.to_datetime(
                episode_row.get("observed_end"), errors="coerce"
            )
            release = observed_end if pd.notna(observed_end) else pd.NaT
        episode_release_times.append(release)
        if pd.isna(release):
            observed_departures.append(pd.NaT)
            matched_indices.append(np.nan)
            release_deltas.append(np.nan)
            match_reasons.append("EPISODE_RELEASE_UNAVAILABLE")
            continue

        candidates = dep[
            dep["mmsi"].eq(mmsi)
            & dep["origin"].astype(str).str.upper().eq(str(row["origin"]).upper())
            & dep["baseline_departure_time"].gt(decision)
            & dep["baseline_departure_time"].between(
                release - tolerance, release + tolerance
            )
        ].copy()
        candidates = candidates.loc[~candidates.index.isin(used_departures)]
        if candidates.empty:
            observed_departures.append(pd.NaT)
            matched_indices.append(np.nan)
            release_deltas.append(np.nan)
            match_reasons.append("NO_DEPARTURE_NEAR_SAME_EPISODE_RELEASE")
            continue

        candidates["_release_abs_delta"] = (
            candidates["baseline_departure_time"].sub(release).abs()
        )
        selected_index = int(
            candidates.sort_values(
                ["_release_abs_delta", "baseline_departure_time"]
            ).index[0]
        )
        selected_time = pd.Timestamp(dep.at[selected_index, "baseline_departure_time"])
        used_departures.add(selected_index)
        observed_departures.append(selected_time)
        matched_indices.append(float(selected_index))
        release_deltas.append((selected_time - release).total_seconds() / 60)
        match_reasons.append("MATCHED_SAME_EPISODE_POSTHOC")

    out["episode_observed_release_time"] = episode_release_times
    out["observed_departure_time"] = observed_departures
    out["baseline_departure_time"] = out["observed_departure_time"]
    out["matched_departure_index"] = matched_indices
    out["departure_to_episode_release_min"] = release_deltas
    out["departure_match_reason"] = match_reasons
    out["departure_match_status"] = np.where(
        out["observed_departure_time"].notna(),
        "MATCHED_SAME_EPISODE_POSTHOC",
        "UNMATCHED_RETAINED",
    )
    out["decision_to_observed_departure_min"] = (
        out["observed_departure_time"].sub(out["decision_time"])
        .dt.total_seconds().div(60)
    )
    out["retrospective_reference_decision_time"] = (
        out["observed_departure_time"]
        - pd.to_timedelta(float(horizon_min), unit="m")
    )
    out["prospective_minus_retrospective_epoch_min"] = (
        out["decision_time"].sub(out["retrospective_reference_decision_time"])
        .dt.total_seconds().div(60)
    )
    out["retrospective_reference_used_for_prediction"] = False

    observed_arrivals: list[pd.Timestamp | pd.NaT] = []
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
            & episode_frame["port_id"].astype(str).str.upper().eq(
                str(row["destination"]).upper()
            )
        ]
        observed_arrivals.append(
            future["berth_entry_time"].min() if not future.empty else pd.NaT
        )

    out["observed_destination_berth_time"] = observed_arrivals
    out["eta_error_min"] = (
        out["predicted_eta"].sub(out["observed_destination_berth_time"])
        .dt.total_seconds().div(60)
    )
    out["absolute_eta_error_min"] = out["eta_error_min"].abs()
    out["departure_error_min"] = (
        out["predicted_departure_time"].sub(out["observed_departure_time"])
        .dt.total_seconds().div(60)
    )
    comparison_columns = [
        "decision_case_id",
        "mmsi",
        "origin",
        "destination",
        "berth_episode_id",
        "decision_time",
        "episode_observed_release_time",
        "observed_departure_time",
        "departure_to_episode_release_min",
        "decision_to_observed_departure_min",
        "retrospective_reference_decision_time",
        "prospective_minus_retrospective_epoch_min",
        "departure_match_status",
        "departure_match_reason",
    ]
    return out, out[comparison_columns].copy()


def run_stage4(*args, **kwargs):
    """Run Prompt 3 with current-state features and same-episode validation."""
    previous_build = implementation.build_prospective_decision_epochs
    previous_attach = implementation.attach_posthoc_validation
    implementation.build_prospective_decision_epochs = build_prospective_decision_epochs
    implementation.attach_posthoc_validation = attach_posthoc_validation
    try:
        return implementation.run_stage4(*args, **kwargs)
    finally:
        implementation.build_prospective_decision_epochs = previous_build
        implementation.attach_posthoc_validation = previous_attach
