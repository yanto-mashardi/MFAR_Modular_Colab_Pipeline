"""Behavior-preserving implementation of MFAR Stages 01 and 02.

The scientific transformations are intentionally identical to the frozen
MFAR_V1_RETROSPECTIVE baseline.  This module separates transformation,
validation, export, and notebook presentation so the stages remain auditable,
testable, and runnable independently in Google Colab.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


STAGE1_REQUIRED_SOURCE_COLUMNS = [
    "created_at", "mmsi", "lat", "lon", "sog", "cog", "valid", "navstatus",
]
STAGE2_REQUIRED_COLUMNS = [
    "timestamp", "mmsi", "latitude", "longitude", "sog", "cog",
]


@dataclass
class Stage1Result:
    raw: pd.DataFrame
    clean: pd.DataFrame
    rejected: pd.DataFrame
    summary: pd.DataFrame
    rejection_summary: pd.DataFrame
    vessel_summary: pd.DataFrame
    spatial_summary: pd.DataFrame
    trajectory: pd.DataFrame
    segment_summary: pd.DataFrame
    saved_files: list[Path]


@dataclass
class Stage2Result:
    ais: pd.DataFrame
    profiles: pd.DataFrame
    berths: pd.DataFrame
    interpolated: pd.DataFrame
    rejected_grid: pd.DataFrame
    output_grid: pd.DataFrame
    audit_checks: pd.DataFrame
    operational_audit: pd.DataFrame
    status_summary: pd.DataFrame
    summary: pd.DataFrame
    by_vessel: pd.DataFrame
    gap_distribution: pd.DataFrame
    validation_sample: pd.DataFrame
    saved_files: list[Path]


def _display(frame: pd.DataFrame, rows: int | None = None) -> None:
    """Display in notebooks while remaining harmless in headless execution."""
    try:
        from IPython.display import display
    except ImportError:
        return
    display(frame if rows is None else frame.head(rows))


def load_pipeline_parameters(config_dir: Path) -> dict[str, Any]:
    path = Path(config_dir) / "pipeline_parameters.csv"
    if not path.exists():
        return {}
    return pd.read_csv(path).set_index("parameter")["value"].to_dict()


def haversine_nm(lat1, lon1, lat2, lon2):
    radius_nm = 3440.065
    lat1 = np.radians(lat1)
    lon1 = np.radians(lon1)
    lat2 = np.radians(lat2)
    lon2 = np.radians(lon2)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = (
        np.sin(dlat / 2) ** 2
        + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    )
    return 2 * radius_nm * np.arcsin(np.sqrt(a))


def prepare_stage1_frames(
    raw: pd.DataFrame,
    *,
    max_sog_kn: float = 15.0,
    corridor_min_lat: float = 1.34,
    corridor_max_lat: float = 1.49,
    corridor_min_lon: float = 102.10,
    corridor_max_lon: float = 102.18,
    max_connection_gap_min: float = 20.0,
    max_implied_speed_kn: float = 15.0,
) -> Stage1Result:
    missing = [column for column in STAGE1_REQUIRED_SOURCE_COLUMNS if column not in raw]
    if missing:
        raise ValueError("Kolom wajib tidak ditemukan: " + ", ".join(missing))

    df = raw.copy()
    df = df.rename(
        columns={
            "created_at": "timestamp",
            "lat": "latitude",
            "lon": "longitude",
            "navstatus": "nav_status",
        }
    )
    df["timestamp_raw"] = df["timestamp"]
    df["timestamp"] = pd.to_datetime(
        df["timestamp"], errors="coerce", utc=True
    ).dt.tz_convert(None)

    for column in ["mmsi", "latitude", "longitude", "sog", "cog", "nav_status"]:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    valid_year = df["timestamp"].dt.year.between(2025, 2027)
    timestamp_valid_ratio = df["timestamp"].notna().mean()
    year_valid_ratio = valid_year.mean()
    if timestamp_valid_ratio < 0.95:
        raise ValueError("Lebih dari 5% timestamp gagal dibaca.")
    if year_valid_ratio < 0.95:
        raise ValueError(
            "Hasil parsing waktu tidak masuk akal. "
            "Notebook dihentikan agar tidak menghasilkan periode 1970."
        )

    df["inside_corridor_bbox"] = (
        df["latitude"].between(corridor_min_lat, corridor_max_lat)
        & df["longitude"].between(corridor_min_lon, corridor_max_lon)
    )
    df["rejection_reason"] = ""

    def set_reason(mask: pd.Series, reason: str) -> None:
        available = mask & df["rejection_reason"].eq("")
        df.loc[available, "rejection_reason"] = reason

    set_reason(df["timestamp"].isna(), "invalid_timestamp")
    set_reason(df["mmsi"].isna(), "invalid_mmsi")
    set_reason(
        df["latitude"].isna() | df["longitude"].isna(),
        "missing_coordinate",
    )
    set_reason(
        df["latitude"].eq(0) & df["longitude"].eq(0),
        "zero_coordinate",
    )
    set_reason(df["valid"].ne(True), "source_flag_invalid")
    set_reason(
        ~df["latitude"].between(-90, 90)
        | ~df["longitude"].between(-180, 180),
        "invalid_coordinate_range",
    )
    set_reason(
        df["sog"].lt(0) | df["sog"].gt(max_sog_kn),
        "invalid_sog",
    )
    set_reason(~df["inside_corridor_bbox"], "outside_research_corridor")

    duplicate_mask = df.duplicated(
        subset=["timestamp", "mmsi", "latitude", "longitude", "sog", "cog"],
        keep="first",
    )
    set_reason(duplicate_mask, "duplicate")

    rejected = df[df["rejection_reason"].ne("")].copy()
    clean = (
        df[df["rejection_reason"].eq("")]
        .copy()
        .sort_values(["mmsi", "timestamp"])
        .reset_index(drop=True)
    )
    clean["time_gap_min"] = (
        clean.groupby("mmsi")["timestamp"].diff().dt.total_seconds().div(60)
    )

    summary = pd.DataFrame(
        {
            "metric": [
                "raw_rows",
                "accepted_rows",
                "rejected_rows",
                "acceptance_rate",
                "vessel_count",
                "start_time",
                "end_time",
            ],
            "value": [
                len(df),
                len(clean),
                len(rejected),
                len(clean) / max(len(df), 1),
                clean["mmsi"].nunique(),
                clean["timestamp"].min(),
                clean["timestamp"].max(),
            ],
        }
    )
    rejection_summary = (
        rejected.groupby("rejection_reason")
        .size()
        .rename("rows")
        .reset_index()
        .sort_values("rows", ascending=False)
    )
    vessel_summary = (
        clean.groupby("mmsi")
        .agg(
            messages=("mmsi", "size"),
            start_time=("timestamp", "min"),
            end_time=("timestamp", "max"),
            median_sog_kn=("sog", "median"),
            p95_sog_kn=("sog", lambda values: values.quantile(0.95)),
            maximum_sog_kn=("sog", "max"),
            median_gap_min=("time_gap_min", "median"),
            p95_gap_min=("time_gap_min", lambda values: values.quantile(0.95)),
            maximum_gap_min=("time_gap_min", "max"),
            minimum_latitude=("latitude", "min"),
            maximum_latitude=("latitude", "max"),
            minimum_longitude=("longitude", "min"),
            maximum_longitude=("longitude", "max"),
        )
        .reset_index()
    )
    spatial_summary = pd.DataFrame(
        {
            "metric": [
                "raw_inside_corridor",
                "raw_outside_corridor",
                "accepted_inside_corridor",
                "minimum_latitude_clean",
                "maximum_latitude_clean",
                "minimum_longitude_clean",
                "maximum_longitude_clean",
            ],
            "value": [
                int(df["inside_corridor_bbox"].sum()),
                int((~df["inside_corridor_bbox"]).sum()),
                len(clean),
                clean["latitude"].min(),
                clean["latitude"].max(),
                clean["longitude"].min(),
                clean["longitude"].max(),
            ],
        }
    )

    trajectory = clean.copy()
    trajectory["previous_timestamp"] = (
        trajectory.groupby("mmsi")["timestamp"].shift(1)
    )
    trajectory["previous_latitude"] = (
        trajectory.groupby("mmsi")["latitude"].shift(1)
    )
    trajectory["previous_longitude"] = (
        trajectory.groupby("mmsi")["longitude"].shift(1)
    )
    trajectory["connection_gap_min"] = (
        trajectory["timestamp"] - trajectory["previous_timestamp"]
    ).dt.total_seconds() / 60
    trajectory["connection_distance_nm"] = haversine_nm(
        trajectory["previous_latitude"],
        trajectory["previous_longitude"],
        trajectory["latitude"],
        trajectory["longitude"],
    )
    trajectory["implied_speed_kn"] = (
        trajectory["connection_distance_nm"]
        / (trajectory["connection_gap_min"] / 60)
    )
    trajectory["same_date"] = (
        trajectory["timestamp"].dt.date
        == trajectory["previous_timestamp"].dt.date
    )
    trajectory["valid_connection"] = (
        trajectory["same_date"]
        & trajectory["connection_gap_min"].gt(0)
        & trajectory["connection_gap_min"].le(max_connection_gap_min)
        & trajectory["implied_speed_kn"].le(max_implied_speed_kn)
    )
    trajectory["new_segment"] = ~trajectory["valid_connection"]
    trajectory["trajectory_segment_id"] = (
        trajectory.groupby("mmsi")["new_segment"].cumsum().astype(int)
    )
    segment_summary = (
        trajectory.groupby(["mmsi", "trajectory_segment_id"])
        .agg(
            start_time=("timestamp", "min"),
            end_time=("timestamp", "max"),
            point_count=("timestamp", "size"),
            start_latitude=("latitude", "first"),
            start_longitude=("longitude", "first"),
            end_latitude=("latitude", "last"),
            end_longitude=("longitude", "last"),
            maximum_gap_min=("connection_gap_min", "max"),
            maximum_implied_speed_kn=("implied_speed_kn", "max"),
        )
        .reset_index()
    )
    segment_summary["duration_min"] = (
        segment_summary["end_time"] - segment_summary["start_time"]
    ).dt.total_seconds() / 60
    valid_segment_summary = segment_summary[
        segment_summary["point_count"].ge(2)
    ].copy()

    return Stage1Result(
        raw=raw,
        clean=clean,
        rejected=rejected,
        summary=summary,
        rejection_summary=rejection_summary,
        vessel_summary=vessel_summary,
        spatial_summary=spatial_summary,
        trajectory=trajectory,
        segment_summary=valid_segment_summary,
        saved_files=[],
    )


def run_stage1(
    *,
    ais_path: Path,
    vehicle_arrival_path: Path,
    config_dir: Path,
    stage_dir: Path,
    notebook_name: str,
    started_at: datetime,
) -> Stage1Result:
    from .mfar_maps import build_validation_map
    from .mfar_paths import (
        validate_csv_input,
        validate_raw_inputs,
        validate_writable_directory,
        write_execution_metadata,
    )
    from .mfar_visuals import stage1_quality_outputs

    stage_dir = Path(stage_dir)
    config_dir = Path(config_dir)
    validate_raw_inputs(notebook_name)
    validate_writable_directory(stage_dir, notebook_name, 1)
    raw = validate_csv_input(
        Path(ais_path), STAGE1_REQUIRED_SOURCE_COLUMNS, notebook_name, 1
    )
    params = load_pipeline_parameters(config_dir)
    result = prepare_stage1_frames(
        raw,
        max_sog_kn=float(params.get("max_sog_kn", 15)),
        corridor_min_lat=float(params.get("corridor_min_lat", 1.34)),
        corridor_max_lat=float(params.get("corridor_max_lat", 1.49)),
        corridor_min_lon=float(params.get("corridor_min_lon", 102.10)),
        corridor_max_lon=float(params.get("corridor_max_lon", 102.18)),
        max_connection_gap_min=20,
        max_implied_speed_kn=15,
    )

    result.clean.to_csv(stage_dir / "01_ais_clean.csv", index=False)
    result.rejected.to_csv(stage_dir / "01_ais_rejected.csv", index=False)
    result.summary.to_csv(stage_dir / "01_cleaning_summary.csv", index=False)
    result.rejection_summary.to_csv(
        stage_dir / "01_rejection_reason_summary.csv", index=False
    )
    result.vessel_summary.to_csv(stage_dir / "01_vessel_summary.csv", index=False)
    result.spatial_summary.to_csv(
        stage_dir / "01_spatial_validation_summary.csv", index=False
    )
    result.trajectory.to_csv(
        stage_dir / "01_ais_with_trajectory_fields.csv", index=False
    )
    result.segment_summary.to_csv(
        stage_dir / "01_trajectory_segment_summary.csv", index=False
    )

    berths = pd.read_csv(config_dir / "terminal_berths.csv")
    map_path, map_segments, map_audit = build_validation_map(
        result.clean,
        berths,
        stage_dir / "01_ais_full_validation_map.html",
        "timestamp",
        max_points=2500,
    )
    map_segments.to_csv(stage_dir / "01_map_segment_audit.csv", index=False)
    _display(pd.DataFrame([map_audit]))

    stage1_quality_outputs(
        result.summary,
        result.rejection_summary,
        result.vessel_summary,
        stage_dir,
    )
    saved_files = sorted(stage_dir.glob("01_*"))
    write_execution_metadata(
        stage=1,
        notebook=notebook_name,
        started_at=started_at,
        input_paths=[Path(ais_path), Path(vehicle_arrival_path)],
        input_rows={"raw": len(raw)},
        output_rows={"clean": len(result.clean)},
        output_files=saved_files,
    )
    result.saved_files = saved_files
    return result


def circular_interpolate_deg(value_before, value_after, weight):
    if pd.isna(value_before) or pd.isna(value_after):
        return np.nan
    start = np.deg2rad(value_before)
    end = np.deg2rad(value_after)
    delta = np.arctan2(np.sin(end - start), np.cos(end - start))
    result = start + weight * delta
    return float(np.rad2deg(result) % 360)


def interpolate_one_vessel(
    vessel_df: pd.DataFrame,
    interval_min: int = 5,
    max_gap_min: int = 20,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    vessel_df = (
        vessel_df.sort_values("timestamp")
        .drop_duplicates(subset=["timestamp"], keep="last")
        .reset_index(drop=True)
    )
    mmsi = int(vessel_df["mmsi"].iloc[0])
    grid_times = pd.date_range(
        vessel_df["timestamp"].min().ceil(f"{interval_min}min"),
        vessel_df["timestamp"].max().floor(f"{interval_min}min"),
        freq=f"{interval_min}min",
    )
    accepted_rows: list[dict[str, Any]] = []
    rejected_rows: list[dict[str, Any]] = []
    time_values = vessel_df["timestamp"].values.astype("datetime64[ns]")

    for grid_time in grid_times:
        grid_np = np.datetime64(grid_time)
        after_index = np.searchsorted(time_values, grid_np, side="left")
        if after_index >= len(vessel_df):
            rejected_rows.append(
                {
                    "grid_time": grid_time,
                    "mmsi": mmsi,
                    "rejection_reason": "no_after_observation",
                }
            )
            continue
        if vessel_df.iloc[after_index]["timestamp"] == grid_time:
            before_index = after_index
        else:
            before_index = after_index - 1
        if before_index < 0:
            rejected_rows.append(
                {
                    "grid_time": grid_time,
                    "mmsi": mmsi,
                    "rejection_reason": "no_before_observation",
                }
            )
            continue

        before = vessel_df.iloc[before_index]
        after = vessel_df.iloc[after_index]
        time_before = before["timestamp"]
        time_after = after["timestamp"]
        age_before_min = (grid_time - time_before).total_seconds() / 60
        age_after_min = (time_after - grid_time).total_seconds() / 60
        bracket_gap_min = (time_after - time_before).total_seconds() / 60

        if bracket_gap_min < 0:
            rejected_rows.append(
                {
                    "grid_time": grid_time,
                    "mmsi": mmsi,
                    "rejection_reason": "negative_bracket_gap",
                }
            )
            continue
        if bracket_gap_min > max_gap_min:
            rejected_rows.append(
                {
                    "grid_time": grid_time,
                    "mmsi": mmsi,
                    "source_time_before": time_before,
                    "source_time_after": time_after,
                    "age_before_min": age_before_min,
                    "age_after_min": age_after_min,
                    "bracket_gap_min": bracket_gap_min,
                    "rejection_reason": "bracket_gap_too_large",
                }
            )
            continue

        weight = 0.0 if bracket_gap_min == 0 else age_before_min / bracket_gap_min
        weight = float(np.clip(weight, 0, 1))
        latitude = before["latitude"] + weight * (
            after["latitude"] - before["latitude"]
        )
        longitude = before["longitude"] + weight * (
            after["longitude"] - before["longitude"]
        )
        sog = before["sog"] + weight * (after["sog"] - before["sog"])
        cog = circular_interpolate_deg(before["cog"], after["cog"], weight)
        nav_status_before = (
            before["nav_status"] if "nav_status" in before.index else np.nan
        )
        nav_status_after = (
            after["nav_status"] if "nav_status" in after.index else np.nan
        )
        nav_status = (
            nav_status_before if age_before_min <= age_after_min else nav_status_after
        )
        accepted_rows.append(
            {
                "grid_time": grid_time,
                "mmsi": mmsi,
                "source_time_before": time_before,
                "source_time_after": time_after,
                "age_before_min": age_before_min,
                "age_after_min": age_after_min,
                "bracket_gap_min": bracket_gap_min,
                "interpolation_weight": weight,
                "latitude": latitude,
                "longitude": longitude,
                "sog": sog,
                "cog": cog,
                "nav_status": nav_status,
            }
        )
    return pd.DataFrame(accepted_rows), pd.DataFrame(rejected_rows)


def _read_or_initialize_profiles(
    ais: pd.DataFrame, profile_file: Path
) -> pd.DataFrame:
    profiles = pd.read_csv(profile_file) if profile_file.exists() else pd.DataFrame()
    if profiles.empty:
        mmsi_values = sorted(
            ais["mmsi"].dropna().astype("int64").unique()
        )
        profiles = pd.DataFrame(
            {
                "mmsi": mmsi_values,
                "vessel_name": [f"MMSI_{value}" for value in mmsi_values],
                "normal_sog_kn": [
                    ais.loc[
                        ais["mmsi"].astype("int64").eq(value), "sog"
                    ].replace(0, np.nan).median()
                    for value in mmsi_values
                ],
                "vehicle_capacity_ce": 30,
                "eta_reliability": 1.0,
                "berth_duration_reliability": 1.0,
                "turnaround_min": 40,
                "approach_allowance_min": 5,
            }
        )
        profiles.to_csv(profile_file, index=False)
    profiles["mmsi"] = pd.to_numeric(
        profiles["mmsi"], errors="coerce"
    ).astype("Int64")
    return profiles


def _prepare_berths(berth_file: Path) -> pd.DataFrame:
    if not berth_file.exists():
        raise FileNotFoundError(f"Konfigurasi dermaga tidak ditemukan: {berth_file}")
    berths = pd.read_csv(berth_file)
    required = ["port_id", "berth_id", "latitude", "longitude"]
    missing = [column for column in required if column not in berths]
    if missing:
        raise ValueError(
            "terminal_berths.csv tidak lengkap. Kolom hilang: " + ", ".join(missing)
        )
    berths["port_id"] = berths["port_id"].astype(str).str.strip().str.upper()
    berths["berth_id"] = berths["berth_id"].astype(str).str.strip()
    berths["latitude"] = pd.to_numeric(berths["latitude"], errors="coerce")
    berths["longitude"] = pd.to_numeric(berths["longitude"], errors="coerce")
    berths = berths.dropna(subset=["latitude", "longitude"]).copy()
    if "occupancy_radius_nm" not in berths:
        berths["occupancy_radius_nm"] = 0.12
    berths["occupancy_radius_nm"] = pd.to_numeric(
        berths["occupancy_radius_nm"], errors="coerce"
    ).fillna(0.12)
    return berths


def build_operational_state(
    output_grid: pd.DataFrame,
    berths: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    output_grid = output_grid.copy()
    distance_metadata: list[dict[str, Any]] = []
    for _, berth in berths.iterrows():
        safe_id = (
            str(berth["berth_id"])
            .replace(" ", "_")
            .replace("-", "_")
            .replace("/", "_")
        )
        column = f"distance_to_{safe_id}_nm"
        output_grid[column] = haversine_nm(
            output_grid["latitude"],
            output_grid["longitude"],
            berth["latitude"],
            berth["longitude"],
        )
        distance_metadata.append(
            {
                "column": column,
                "berth_id": berth["berth_id"],
                "port_id": berth["port_id"],
                "radius_nm": float(berth["occupancy_radius_nm"]),
            }
        )

    distance_cols = [item["column"] for item in distance_metadata]
    if not distance_cols:
        raise ValueError("Tidak ada dermaga valid pada terminal_berths.csv.")
    nearest_col = output_grid[distance_cols].idxmin(axis=1)
    col_to_berth = {item["column"]: item["berth_id"] for item in distance_metadata}
    col_to_port = {item["column"]: item["port_id"] for item in distance_metadata}
    col_to_radius = {item["column"]: item["radius_nm"] for item in distance_metadata}
    output_grid["nearest_berth_id"] = nearest_col.map(col_to_berth)
    output_grid["nearest_port_id"] = nearest_col.map(col_to_port)
    output_grid["nearest_berth_radius_nm"] = nearest_col.map(col_to_radius)
    output_grid["nearest_distance_nm"] = output_grid[distance_cols].min(axis=1)

    port_centres = (
        berths.groupby("port_id")[["latitude", "longitude"]]
        .mean()
        .sort_index()
    )
    ports = list(port_centres.index)
    if len(ports) != 2:
        raise ValueError(
            "Model koridor Stage 2 mengharapkan tepat dua terminal. "
            f"Ditemukan: {ports}"
        )
    for port in ports:
        safe_port = str(port).lower().replace(" ", "_")
        output_grid[f"distance_to_{safe_port}_terminal_nm"] = haversine_nm(
            output_grid["latitude"],
            output_grid["longitude"],
            port_centres.loc[port, "latitude"],
            port_centres.loc[port, "longitude"],
        )

    output_grid = output_grid.sort_values(
        ["mmsi", "grid_time"]
    ).reset_index(drop=True)
    for port in ports:
        safe_port = str(port).lower().replace(" ", "_")
        distance_column = f"distance_to_{safe_port}_terminal_nm"
        output_grid[f"delta_{safe_port}_distance_nm"] = (
            output_grid.groupby("mmsi")[distance_column].diff()
        )

    stopped_speed_kn = 0.80
    maneuver_speed_kn = 3.00
    approach_radius_nm = 0.60
    movement_eps_nm = 0.005
    at_berth = (
        output_grid["nearest_distance_nm"]
        <= output_grid["nearest_berth_radius_nm"]
    ) & (
        pd.to_numeric(output_grid["sog"], errors="coerce").fillna(0.0)
        <= stopped_speed_kn
    )

    port_a, port_b = ports
    safe_a = str(port_a).lower().replace(" ", "_")
    safe_b = str(port_b).lower().replace(" ", "_")
    da = output_grid[f"delta_{safe_a}_distance_nm"]
    db = output_grid[f"delta_{safe_b}_distance_nm"]
    output_grid["destination"] = np.where(da < db, port_a, port_b)
    output_grid["origin"] = np.where(
        output_grid["destination"].eq(port_a), port_b, port_a
    )
    first_or_unknown = da.isna() | db.isna()
    dist_a = output_grid[f"distance_to_{safe_a}_terminal_nm"]
    dist_b = output_grid[f"distance_to_{safe_b}_terminal_nm"]
    output_grid.loc[first_or_unknown, "destination"] = np.where(
        dist_a[first_or_unknown] <= dist_b[first_or_unknown],
        port_a,
        port_b,
    )
    output_grid.loc[first_or_unknown, "origin"] = np.where(
        output_grid.loc[first_or_unknown, "destination"].eq(port_a),
        port_b,
        port_a,
    )
    output_grid.loc[at_berth, "origin"] = output_grid.loc[
        at_berth, "nearest_port_id"
    ]
    output_grid.loc[at_berth, "destination"] = np.where(
        output_grid.loc[at_berth, "nearest_port_id"].eq(port_a),
        port_b,
        port_a,
    )

    output_grid["operational_status"] = "SAILING"
    output_grid["current_berth_id"] = pd.Series(
        np.nan, index=output_grid.index, dtype="object"
    )
    output_grid.loc[at_berth, "current_berth_id"] = output_grid.loc[
        at_berth, "nearest_berth_id"
    ]
    output_grid.loc[at_berth, "operational_status"] = (
        "AT_BERTH_"
        + output_grid.loc[at_berth, "nearest_port_id"].astype(str)
    )

    near_terminal = output_grid["nearest_distance_nm"] <= approach_radius_nm
    nearest_port_delta = np.where(
        output_grid["nearest_port_id"].eq(port_a), da, db
    )
    nearest_port_delta = pd.Series(nearest_port_delta, index=output_grid.index)
    approaching = (
        near_terminal
        & ~at_berth
        & (nearest_port_delta < -movement_eps_nm)
        & (output_grid["sog"] <= maneuver_speed_kn)
    )
    departing = (
        near_terminal
        & ~at_berth
        & (nearest_port_delta > movement_eps_nm)
        & (output_grid["sog"] <= maneuver_speed_kn)
    )
    output_grid.loc[approaching, "destination"] = output_grid.loc[
        approaching, "nearest_port_id"
    ]
    output_grid.loc[approaching, "origin"] = np.where(
        output_grid.loc[approaching, "nearest_port_id"].eq(port_a),
        port_b,
        port_a,
    )
    output_grid.loc[approaching, "operational_status"] = (
        "APPROACHING_"
        + output_grid.loc[approaching, "nearest_port_id"].astype(str)
    )
    output_grid.loc[departing, "origin"] = output_grid.loc[
        departing, "nearest_port_id"
    ]
    output_grid.loc[departing, "destination"] = np.where(
        output_grid.loc[departing, "nearest_port_id"].eq(port_a),
        port_b,
        port_a,
    )
    output_grid.loc[departing, "operational_status"] = (
        "DEPARTING_"
        + output_grid.loc[departing, "nearest_port_id"].astype(str)
    )

    def destination_distance(row: pd.Series) -> float:
        destination = row["destination"]
        if destination not in port_centres.index:
            return np.nan
        return float(
            haversine_nm(
                row["latitude"],
                row["longitude"],
                port_centres.loc[destination, "latitude"],
                port_centres.loc[destination, "longitude"],
            )
        )

    output_grid["distance_to_destination_terminal_nm"] = output_grid.apply(
        destination_distance, axis=1
    )
    output_grid["is_at_berth"] = at_berth.astype(bool)

    operational_audit = pd.DataFrame(
        {
            "check": [
                "missing_operational_status",
                "missing_origin",
                "missing_destination",
                "missing_destination_distance",
                "at_berth_without_berth_id",
                "origin_equals_destination",
            ],
            "failed_rows": [
                int(output_grid["operational_status"].isna().sum()),
                int(output_grid["origin"].isna().sum()),
                int(output_grid["destination"].isna().sum()),
                int(
                    output_grid[
                        "distance_to_destination_terminal_nm"
                    ].isna().sum()
                ),
                int((at_berth & output_grid["current_berth_id"].isna()).sum()),
                int(
                    output_grid["origin"].eq(
                        output_grid["destination"]
                    ).sum()
                ),
            ],
        }
    )
    status_summary = (
        output_grid["operational_status"]
        .value_counts(dropna=False)
        .rename_axis("operational_status")
        .reset_index(name="rows")
    )
    return output_grid, operational_audit, status_summary


def prepare_stage2_frames(
    ais: pd.DataFrame,
    profiles: pd.DataFrame,
    berths: pd.DataFrame,
    *,
    grid_interval_min: int = 5,
    max_bracket_gap_min: int = 20,
) -> Stage2Result:
    missing = [column for column in STAGE2_REQUIRED_COLUMNS if column not in ais]
    if missing:
        raise ValueError(
            "Kolom wajib dari Notebook 1 tidak ditemukan: " + ", ".join(missing)
        )
    ais = ais.copy()
    ais["timestamp"] = pd.to_datetime(ais["timestamp"], errors="coerce")
    for column in ["mmsi", "latitude", "longitude", "sog", "cog"]:
        ais[column] = pd.to_numeric(ais[column], errors="coerce")
    ais = (
        ais.dropna(subset=STAGE2_REQUIRED_COLUMNS)
        .sort_values(["mmsi", "timestamp"])
        .reset_index(drop=True)
    )

    accepted_parts: list[pd.DataFrame] = []
    rejected_parts: list[pd.DataFrame] = []
    for _, vessel_df in ais.groupby("mmsi"):
        accepted_vessel, rejected_vessel = interpolate_one_vessel(
            vessel_df=vessel_df,
            interval_min=grid_interval_min,
            max_gap_min=max_bracket_gap_min,
        )
        if not accepted_vessel.empty:
            accepted_parts.append(accepted_vessel)
        if not rejected_vessel.empty:
            rejected_parts.append(rejected_vessel)
    interpolated = (
        pd.concat(accepted_parts, ignore_index=True)
        if accepted_parts
        else pd.DataFrame()
    )
    rejected_grid = (
        pd.concat(rejected_parts, ignore_index=True)
        if rejected_parts
        else pd.DataFrame()
    )
    interpolated = interpolated.sort_values(
        ["grid_time", "mmsi"]
    ).reset_index(drop=True)
    interpolated["mmsi"] = interpolated["mmsi"].astype("int64")
    profiles_merge = profiles.copy()
    profiles_merge["mmsi"] = profiles_merge["mmsi"].astype("int64")
    output_grid = interpolated.merge(
        profiles_merge, on="mmsi", how="left", validate="many_to_one"
    )
    output_grid["date"] = output_grid["grid_time"].dt.strftime("%Y-%m-%d")
    output_grid["time_of_day"] = output_grid["grid_time"].dt.strftime("%H:%M")
    output_grid, operational_audit, status_summary = build_operational_state(
        output_grid, berths
    )

    audit_checks = pd.DataFrame(
        {
            "check": [
                "grid_time_on_5_minute",
                "source_before_not_after_grid",
                "source_after_not_before_grid",
                "non_negative_age_before",
                "non_negative_age_after",
                "bracket_gap_within_limit",
                "weight_between_zero_and_one",
                "duplicate_mmsi_grid_time",
                "missing_latitude",
                "missing_longitude",
                "missing_sog",
            ],
            "failed_rows": [
                int(
                    (
                        (
                            output_grid["grid_time"].dt.minute
                            % grid_interval_min
                        ).ne(0)
                    ).sum()
                ),
                int(
                    (
                        output_grid["source_time_before"]
                        > output_grid["grid_time"]
                    ).sum()
                ),
                int(
                    (
                        output_grid["source_time_after"]
                        < output_grid["grid_time"]
                    ).sum()
                ),
                int(output_grid["age_before_min"].lt(0).sum()),
                int(output_grid["age_after_min"].lt(0).sum()),
                int(
                    output_grid["bracket_gap_min"]
                    .gt(max_bracket_gap_min)
                    .sum()
                ),
                int(
                    (
                        ~output_grid["interpolation_weight"].between(0, 1)
                    ).sum()
                ),
                int(
                    output_grid.duplicated(["grid_time", "mmsi"]).sum()
                ),
                int(output_grid["latitude"].isna().sum()),
                int(output_grid["longitude"].isna().sum()),
                int(output_grid["sog"].isna().sum()),
            ],
        }
    )
    if audit_checks["failed_rows"].sum() > 0:
        raise ValueError(
            "Validasi internal Notebook 2 gagal. Periksa tabel audit_checks."
        )

    summary = pd.DataFrame(
        {
            "metric": [
                "grid_interval_min",
                "maximum_bracket_gap_min",
                "input_ais_rows",
                "interpolated_grid_rows",
                "rejected_grid_rows",
                "vessel_count",
                "unique_grid_times",
                "start_grid_time",
                "end_grid_time",
                "median_age_before_min",
                "median_age_after_min",
                "median_bracket_gap_min",
                "p95_bracket_gap_min",
            ],
            "value": [
                grid_interval_min,
                max_bracket_gap_min,
                len(ais),
                len(output_grid),
                len(rejected_grid),
                output_grid["mmsi"].nunique(),
                output_grid["grid_time"].nunique(),
                output_grid["grid_time"].min(),
                output_grid["grid_time"].max(),
                output_grid["age_before_min"].median(),
                output_grid["age_after_min"].median(),
                output_grid["bracket_gap_min"].median(),
                output_grid["bracket_gap_min"].quantile(0.95),
            ],
        }
    )
    by_vessel = (
        output_grid.groupby("mmsi")
        .agg(
            interpolated_rows=("grid_time", "size"),
            start_grid_time=("grid_time", "min"),
            end_grid_time=("grid_time", "max"),
            median_age_before_min=("age_before_min", "median"),
            median_age_after_min=("age_after_min", "median"),
            median_bracket_gap_min=("bracket_gap_min", "median"),
            p95_bracket_gap_min=(
                "bracket_gap_min",
                lambda values: values.quantile(0.95),
            ),
            minimum_sog=("sog", "min"),
            median_sog=("sog", "median"),
            maximum_sog=("sog", "max"),
        )
        .reset_index()
    )
    gap_distribution = pd.DataFrame(
        {
            "range": ["0–5 min", ">5–10 min", ">10–15 min", ">15–20 min"],
            "rows": [
                output_grid["bracket_gap_min"]
                .between(0, 5, inclusive="both")
                .sum(),
                output_grid["bracket_gap_min"]
                .gt(5)
                .mul(output_grid["bracket_gap_min"].le(10))
                .sum(),
                output_grid["bracket_gap_min"]
                .gt(10)
                .mul(output_grid["bracket_gap_min"].le(15))
                .sum(),
                output_grid["bracket_gap_min"]
                .gt(15)
                .mul(output_grid["bracket_gap_min"].le(20))
                .sum(),
            ],
        }
    )
    validation_sample = (
        output_grid[
            [
                "grid_time",
                "mmsi",
                "source_time_before",
                "source_time_after",
                "age_before_min",
                "age_after_min",
                "bracket_gap_min",
                "interpolation_weight",
                "latitude",
                "longitude",
                "sog",
                "cog",
            ]
        ]
        .groupby("mmsi", group_keys=False)
        .head(50)
        .reset_index(drop=True)
    )
    return Stage2Result(
        ais=ais,
        profiles=profiles,
        berths=berths,
        interpolated=interpolated,
        rejected_grid=rejected_grid,
        output_grid=output_grid,
        audit_checks=audit_checks,
        operational_audit=operational_audit,
        status_summary=status_summary,
        summary=summary,
        by_vessel=by_vessel,
        gap_distribution=gap_distribution,
        validation_sample=validation_sample,
        saved_files=[],
    )


def run_stage2(
    *,
    input_ais: Path,
    profile_file: Path,
    berth_file: Path,
    stage_dir: Path,
    notebook_name: str,
    started_at: datetime,
    grid_interval_min: int = 5,
    max_bracket_gap_min: int = 20,
) -> Stage2Result:
    from .mfar_maps import build_validation_map
    from .mfar_paths import (
        validate_csv_input,
        validate_writable_directory,
        write_execution_metadata,
    )
    from .mfar_visuals import stage2_interpolation_outputs

    input_ais = Path(input_ais)
    profile_file = Path(profile_file)
    berth_file = Path(berth_file)
    stage_dir = Path(stage_dir)
    validate_writable_directory(stage_dir, notebook_name, 2)
    ais = validate_csv_input(
        input_ais, STAGE2_REQUIRED_COLUMNS, notebook_name, 2
    )
    profiles = _read_or_initialize_profiles(ais, profile_file)
    berths = _prepare_berths(berth_file)
    result = prepare_stage2_frames(
        ais,
        profiles,
        berths,
        grid_interval_min=grid_interval_min,
        max_bracket_gap_min=max_bracket_gap_min,
    )

    main_output = stage_dir / "02_vessel_interpolated_grid.csv"
    result.output_grid.to_csv(main_output, index=False)
    result.rejected_grid.to_csv(
        stage_dir / "02_interpolation_rejected_grid.csv", index=False
    )
    result.summary.to_csv(
        stage_dir / "02_interpolation_summary.csv", index=False
    )
    result.by_vessel.to_csv(
        stage_dir / "02_interpolation_by_vessel.csv", index=False
    )
    result.gap_distribution.to_csv(
        stage_dir / "02_interpolation_gap_distribution.csv", index=False
    )
    result.validation_sample.to_csv(
        stage_dir / "02_grid_validation_sample.csv", index=False
    )
    result.audit_checks.to_csv(
        stage_dir / "02_interpolation_audit_checks.csv", index=False
    )
    result.operational_audit.to_csv(
        stage_dir / "02_operational_state_audit.csv", index=False
    )
    result.status_summary.to_csv(
        stage_dir / "02_operational_status_summary.csv", index=False
    )

    if not main_output.exists():
        raise IOError(f"Gagal membuat output utama Stage 2: {main_output}")
    saved_check = pd.read_csv(main_output, nrows=5)
    required_saved_columns = [
        "grid_time",
        "mmsi",
        "latitude",
        "longitude",
        "sog",
        "cog",
        "age_before_min",
        "age_after_min",
        "bracket_gap_min",
        "operational_status",
        "current_berth_id",
        "origin",
        "destination",
        "distance_to_destination_terminal_nm",
    ]
    missing_saved_columns = [
        column
        for column in required_saved_columns
        if column not in saved_check
    ]
    if missing_saved_columns:
        raise IOError(
            "File utama berhasil dibuat tetapi kolomnya tidak lengkap: "
            + ", ".join(missing_saved_columns)
        )

    ais_compare = result.ais.copy()
    full_path, full_segments, full_audit = build_validation_map(
        result.output_grid,
        result.berths,
        stage_dir / "02_interpolated_full_validation_map.html",
        "grid_time",
        original=ais_compare,
        original_time_col="timestamp",
        max_points=1800,
        max_original_points=1000,
    )
    all_segment_audits = [full_segments.assign(map_file=full_path.name)]
    for mmsi, vessel in result.output_grid.groupby("mmsi"):
        density = (
            vessel.assign(map_date=vessel["grid_time"].dt.date)
            .groupby("map_date")
            .size()
        )
        selected_date = density.idxmax()
        view = vessel[vessel["grid_time"].dt.date.eq(selected_date)]
        original_view = ais_compare[
            (ais_compare["mmsi"].astype(str) == str(mmsi))
            & (ais_compare["timestamp"].dt.date.eq(selected_date))
        ]
        name = f"02_validation_map_{int(mmsi)}_{selected_date}.html"
        path, segments, _ = build_validation_map(
            view,
            result.berths,
            stage_dir / name,
            "grid_time",
            original=original_view,
            original_time_col="timestamp",
            max_points=2500,
            max_original_points=1200,
        )
        all_segment_audits.append(segments.assign(map_file=path.name))
    pd.concat(all_segment_audits, ignore_index=True).to_csv(
        stage_dir / "02_map_segment_audit.csv", index=False
    )
    _display(pd.DataFrame([full_audit]))

    stage2_interpolation_outputs(
        result.output_grid,
        result.summary,
        result.by_vessel,
        result.gap_distribution,
        result.audit_checks,
        stage_dir,
    )
    saved_files = sorted(stage_dir.glob("02_*"))
    write_execution_metadata(
        stage=2,
        notebook=notebook_name,
        started_at=started_at,
        input_paths=[input_ais, profile_file, berth_file],
        input_rows={"ais": len(result.ais)},
        output_rows={"output_grid": len(result.output_grid)},
        output_files=saved_files,
    )
    result.saved_files = saved_files
    return result
