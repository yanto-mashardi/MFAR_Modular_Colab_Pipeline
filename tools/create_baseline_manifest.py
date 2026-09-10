#!/usr/bin/env python3
"""Create and compare reproducibility manifests for the MFAR pipeline.

This utility is intentionally read-only with respect to the scientific pipeline.
It records the code revision, runtime, input/configuration/output checksums,
row counts, and selected Stage 01-07 metrics. It never changes model inputs,
parameters, equations, or stage outputs.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PACKAGE_NAMES = [
    "pandas", "numpy", "matplotlib", "folium", "ipywidgets",
    "plotly", "openpyxl", "nbconvert", "jupyter",
]
CONFIG_FILES = [
    "action_constraints.csv",
    "fuzzy_rules.csv",
    "membership_parameters.csv",
    "pipeline_parameters.csv",
    "terminal_berths.csv",
    "vessel_profiles.csv",
]
CANONICAL_OUTPUTS = [
    "stage_01/01_ais_clean.csv",
    "stage_02/02_vessel_interpolated_grid.csv",
    "stage_03/03_input_state_enhanced.csv",
    "stage_03/03_berth_episode_history.csv",
    "stage_04/04_fuzzy_input.csv",
    "stage_04/04_temporal_holdout_validation.csv",
    "stage_05/05_fuzzy_memberships.csv",
    "stage_06/06_rule_evaluation.csv",
    "stage_07/07_accepted_operational_recommendations.csv",
    "stage_07/07_queue_service_intervention_events.csv",
    "stage_07/07_daily_scenario_by_port.csv",
    "stage_07/07_overall_scenario_evaluation.csv",
    "stage_07/07_scenario_baseline_vs_actions.csv",
]


def _json_scalar(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        value = float(value)
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    return value


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def csv_row_count(path: Path) -> int | None:
    if not path.is_file() or path.suffix.lower() != ".csv":
        return None
    with path.open("rb") as handle:
        rows = sum(1 for _ in handle)
    return max(0, rows - 1)


def artifact_record(path: Path, relative_to: Path, *, with_rows: bool = True) -> dict[str, Any]:
    stat = path.stat()
    record: dict[str, Any] = {
        "path": path.relative_to(relative_to).as_posix(),
        "size_bytes": stat.st_size,
        "sha256": sha256_file(path),
        "modified_time_utc": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
    }
    if with_rows and path.suffix.lower() == ".csv":
        record["row_count"] = csv_row_count(path)
    return record


def package_versions() -> dict[str, str | None]:
    versions: dict[str, str | None] = {}
    for name in PACKAGE_NAMES:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    return versions


def git_commit(repo_root: Path, fallback: str | None = None) -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return fallback


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.is_file() else pd.DataFrame()


def _metric(rows: list[dict[str, Any]], stage: str, name: str, value: Any,
            unit: str, source: str) -> None:
    rows.append({
        "stage": stage,
        "metric": name,
        "value": _json_scalar(value),
        "unit": unit,
        "source": source,
    })


def collect_metrics(drive_root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    out = drive_root / "stage_output"
    metrics: list[dict[str, Any]] = []
    key: dict[str, Any] = {}

    raw = _read_csv(drive_root / "data_raw" / "ais_raw.csv")
    arrival = _read_csv(drive_root / "data_raw" / "vehicle_arrival_rate_30min.csv")
    clean = _read_csv(out / "stage_01" / "01_ais_clean.csv")
    rejected = _read_csv(out / "stage_01" / "01_ais_rejected.csv")
    grid = _read_csv(out / "stage_02" / "02_vessel_interpolated_grid.csv")
    rejected_grid = _read_csv(out / "stage_02" / "02_interpolation_rejected_grid.csv")
    state = _read_csv(out / "stage_03" / "03_input_state_enhanced.csv")
    episodes = _read_csv(out / "stage_03" / "03_berth_episode_history.csv")
    forecast = _read_csv(out / "stage_04" / "04_fuzzy_input.csv")
    eta = _read_csv(out / "stage_04" / "04_temporal_holdout_validation.csv")
    memberships = _read_csv(out / "stage_05" / "05_fuzzy_memberships.csv")
    rules = _read_csv(out / "stage_06" / "06_rule_evaluation.csv")
    accepted = _read_csv(out / "stage_07" / "07_accepted_operational_recommendations.csv")
    effects = _read_csv(out / "stage_07" / "07_queue_service_intervention_events.csv")
    daily = _read_csv(out / "stage_07" / "07_daily_scenario_by_port.csv")
    scenario = _read_csv(out / "stage_07" / "07_scenario_baseline_vs_actions.csv")

    basic = {
        "raw_ais_rows": len(raw),
        "vehicle_arrival_profile_rows": len(arrival),
        "clean_ais_rows": len(clean),
        "rejected_ais_rows": len(rejected),
        "grid_state_rows": len(grid),
        "rejected_grid_rows": len(rejected_grid),
        "enhanced_state_rows": len(state),
        "berth_episode_rows": len(episodes),
        "decision_case_rows": len(forecast),
        "eta_validation_rows": len(eta),
        "membership_rows": len(memberships),
        "rule_evaluation_rows": len(rules),
        "accepted_recommendation_rows": len(accepted),
        "queue_effect_event_rows": len(effects),
        "day_terminal_rows": len(daily),
        "scenario_interval_rows": len(scenario),
    }
    for name, value in basic.items():
        _metric(metrics, "FUNNEL", name, value, "rows", "canonical CSV")
    key["funnel"] = basic

    if not grid.empty and "operational_status" in grid:
        counts = grid["operational_status"].value_counts(dropna=False).to_dict()
        key["stage_02_state_counts"] = {str(k): int(v) for k, v in counts.items()}
        for label, value in counts.items():
            _metric(metrics, "02", f"state_{label}", value, "rows", "02_vessel_interpolated_grid.csv")

    if not episodes.empty and "observed_turnaround_min" in episodes:
        values = pd.to_numeric(episodes["observed_turnaround_min"], errors="coerce")
        stage3 = {
            "turnaround_median_min": values.median(),
            "turnaround_p90_min": values.quantile(0.90),
            "turnaround_mean_min": values.mean(),
            "turnaround_max_min": values.max(),
        }
        key["stage_03"] = {k: _json_scalar(v) for k, v in stage3.items()}
        for name, value in stage3.items():
            _metric(metrics, "03", name, value, "minutes", "03_berth_episode_history.csv")

    if not eta.empty and {"absolute_eta_error_min", "eta_error_min"} <= set(eta.columns):
        ae = pd.to_numeric(eta["absolute_eta_error_min"], errors="coerce")
        err = pd.to_numeric(eta["eta_error_min"], errors="coerce")
        stage4 = {
            "eta_mae_min": ae.mean(),
            "eta_rmse_min": float(np.sqrt(np.nanmean(np.square(err)))),
            "eta_median_absolute_error_min": ae.median(),
            "eta_bias_min": err.mean(),
            "eta_within_10_min_fraction": (ae <= 10).mean(),
            "eta_within_20_min_fraction": (ae <= 20).mean(),
            "eta_within_30_min_fraction": (ae <= 30).mean(),
        }
        key["stage_04"] = {k: _json_scalar(v) for k, v in stage4.items()}
        for name, value in stage4.items():
            unit = "fraction" if name.endswith("fraction") else "minutes"
            _metric(metrics, "04", name, value, unit, "04_temporal_holdout_validation.csv")

    if not memberships.empty:
        mu = memberships.filter(regex=r"^mu_")
        stage5 = {
            "membership_column_count": len(mu.columns),
            "membership_missing_cells": int(mu.isna().sum().sum()),
            "membership_below_zero_cells": int((mu < 0).sum().sum()),
            "membership_above_one_cells": int((mu > 1).sum().sum()),
        }
        key["stage_05"] = stage5
        for name, value in stage5.items():
            _metric(metrics, "05", name, value, "count", "05_fuzzy_memberships.csv")

    if not rules.empty:
        score = pd.to_numeric(rules.get("mamdani_risk_score"), errors="coerce")
        area = pd.to_numeric(rules.get("mamdani_aggregate_area"), errors="coerce")
        stage6: dict[str, Any] = {
            "risk_score_mean": score.mean(),
            "risk_score_median": score.median(),
            "risk_score_max": score.max(),
            "zero_coverage_cases": int(area.eq(0).sum()),
        }
        if "selected_action" in rules:
            stage6["selected_action_counts"] = {
                str(k): int(v) for k, v in rules["selected_action"].value_counts().to_dict().items()
            }
        if "dominant_risk_consequence" in rules:
            stage6["dominant_consequence_counts"] = {
                str(k): int(v)
                for k, v in rules["dominant_risk_consequence"].value_counts().to_dict().items()
            }
        key["stage_06"] = {
            k: _json_scalar(v) if not isinstance(v, dict) else v for k, v in stage6.items()
        }
        for name in ["risk_score_mean", "risk_score_median", "risk_score_max", "zero_coverage_cases"]:
            unit = "score" if "risk" in name else "cases"
            _metric(metrics, "06", name, stage6[name], unit, "06_rule_evaluation.csv")

    if not daily.empty and "queue_area_reduction_percent" in daily:
        reduction = pd.to_numeric(daily["queue_area_reduction_percent"], errors="coerce")
        critical_before = pd.to_numeric(daily.get("critical_duration_baseline_min"), errors="coerce")
        critical_after = pd.to_numeric(daily.get("critical_duration_after_min"), errors="coerce")
        stage7: dict[str, Any] = {
            "queue_area_reduction_median_percent": reduction.median(),
            "queue_area_reduction_mean_percent": reduction.mean(),
            "day_terminal_improved": int(reduction.gt(0).sum()),
            "day_terminal_unchanged": int(reduction.eq(0).sum()),
            "day_terminal_worsened": int(reduction.lt(0).sum()),
            "queue_area_reduction_min_percent": reduction.min(),
            "queue_area_reduction_max_percent": reduction.max(),
            "critical_duration_baseline_min": critical_before.sum(),
            "critical_duration_scenario_min": critical_after.sum(),
            "critical_duration_change_min": (critical_after - critical_before).sum(),
        }
        if not accepted.empty and "selected_action" in accepted:
            stage7["accepted_action_counts"] = {
                str(k): int(v)
                for k, v in accepted["selected_action"].value_counts().to_dict().items()
            }
        key["stage_07"] = {
            k: _json_scalar(v) if not isinstance(v, dict) else v for k, v in stage7.items()
        }
        for name, value in stage7.items():
            if isinstance(value, dict):
                continue
            unit = "percent" if "percent" in name else ("minutes" if "duration" in name else "cases")
            _metric(metrics, "07", name, value, unit, "07_daily_scenario_by_port.csv")

    return metrics, key


def resolve_drive_root(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    env = os.environ.get("MFAR_GDRIVE_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    try:
        from src.mfar_paths import DRIVE_ROOT  # type: ignore
        return Path(DRIVE_ROOT).resolve()
    except Exception as exc:
        raise RuntimeError(
            "Drive root tidak dapat ditentukan. Gunakan --drive-root atau MFAR_GDRIVE_ROOT."
        ) from exc


def snapshot(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).expanduser().resolve()
    drive_root = resolve_drive_root(args.drive_root)
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    input_dir = drive_root / "data_raw"
    stage_output = drive_root / "stage_output"
    config_dir = repo_root / "config"
    snapshot_dir = repo_root / "validation" / "baseline" / "config_snapshot"

    required = [
        input_dir / "ais_raw.csv",
        input_dir / "vehicle_arrival_rate_30min.csv",
        config_dir,
        stage_output,
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError("Baseline input/output belum lengkap: " + "; ".join(missing))

    inputs = [
        artifact_record(input_dir / "ais_raw.csv", drive_root),
        artifact_record(input_dir / "vehicle_arrival_rate_30min.csv", drive_root),
    ]
    configs = [artifact_record(config_dir / name, repo_root) for name in CONFIG_FILES]
    snapshot_configs = [
        artifact_record(snapshot_dir / name, repo_root)
        for name in CONFIG_FILES
        if (snapshot_dir / name).is_file()
    ]
    config_snapshot_matches = (
        len(snapshot_configs) == len(configs)
        and {Path(item["path"]).name: item["sha256"] for item in configs}
        == {Path(item["path"]).name: item["sha256"] for item in snapshot_configs}
    )

    outputs = [
        artifact_record(path, drive_root)
        for path in sorted(stage_output.rglob("*"))
        if path.is_file()
    ]
    canonical: dict[str, Any] = {}
    for relative in CANONICAL_OUTPUTS:
        path = stage_output / relative
        canonical[relative] = artifact_record(path, drive_root) if path.is_file() else None

    metric_rows, key_metrics = collect_metrics(drive_root)
    manifest = {
        "schema_version": "1.0",
        "baseline_name": args.source_label,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "repository": {
            "name": "yanto-mashardi/MFAR_Modular_Colab_Pipeline",
            "branch": args.branch,
            "commit_sha": git_commit(repo_root, args.baseline_sha),
            "repo_root": str(repo_root),
        },
        "runtime": {
            "python_version": sys.version,
            "python_implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "package_versions": package_versions(),
        },
        "paths": {"drive_root": str(drive_root), "stage_output": str(stage_output)},
        "integrity": {
            "configuration_snapshot_matches_active": config_snapshot_matches,
            "scientific_algorithms_modified_by_manifest_tool": False,
            "scientific_parameters_modified_by_manifest_tool": False,
        },
        "inputs": inputs,
        "active_configuration": configs,
        "configuration_snapshot": snapshot_configs,
        "outputs": outputs,
        "canonical_outputs": canonical,
        "key_metrics": key_metrics,
    }

    manifest_path = output_dir / "baseline_manifest.json"
    metrics_path = output_dir / "baseline_metrics.csv"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    pd.DataFrame(metric_rows).to_csv(metrics_path, index=False, quoting=csv.QUOTE_MINIMAL)
    print(manifest_path)
    print(metrics_path)
    if not config_snapshot_matches:
        print("WARNING: config snapshot tidak identik dengan konfigurasi aktif.", file=sys.stderr)
        return 2
    return 0


def _flatten_metrics(data: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    flat: dict[str, Any] = {}
    for key, value in data.items():
        name = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            flat.update(_flatten_metrics(value, name))
        else:
            flat[name] = value
    return flat


def compare(args: argparse.Namespace) -> int:
    first = json.loads(Path(args.first).read_text(encoding="utf-8"))
    second = json.loads(Path(args.second).read_text(encoding="utf-8"))
    checks: list[dict[str, Any]] = []

    def add(name: str, left: Any, right: Any, *, tolerance: float = 0.0) -> None:
        if isinstance(left, (int, float)) and isinstance(right, (int, float)):
            passed = math.isclose(float(left), float(right), rel_tol=tolerance, abs_tol=tolerance)
        else:
            passed = left == right
        checks.append({"check": name, "passed": passed, "run_a": left, "run_b": right})

    add("repository.commit_sha", first["repository"].get("commit_sha"), second["repository"].get("commit_sha"))
    add("inputs.sha256", [item["sha256"] for item in first["inputs"]],
        [item["sha256"] for item in second["inputs"]])
    add("configuration.sha256", [item["sha256"] for item in first["active_configuration"]],
        [item["sha256"] for item in second["active_configuration"]])

    first_canonical = first.get("canonical_outputs", {})
    second_canonical = second.get("canonical_outputs", {})
    for path in CANONICAL_OUTPUTS:
        left = first_canonical.get(path)
        right = second_canonical.get(path)
        add(
            f"canonical_output.{path}.row_count",
            None if left is None else left.get("row_count"),
            None if right is None else right.get("row_count"),
        )
        if args.require_canonical_hashes:
            add(
                f"canonical_output.{path}.sha256",
                None if left is None else left.get("sha256"),
                None if right is None else right.get("sha256"),
            )

    first_metrics = _flatten_metrics(first.get("key_metrics", {}))
    second_metrics = _flatten_metrics(second.get("key_metrics", {}))
    for name in sorted(set(first_metrics) | set(second_metrics)):
        add(
            f"metric.{name}",
            first_metrics.get(name),
            second_metrics.get(name),
            tolerance=args.tolerance,
        )

    passed = all(item["passed"] for item in checks)
    report = {
        "schema_version": "1.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if passed else "FAIL",
        "require_canonical_hashes": bool(args.require_canonical_hashes),
        "numeric_tolerance": args.tolerance,
        "checks": checks,
    }
    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(output)
    return 0 if passed else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    snap = sub.add_parser("snapshot", help="Create baseline manifest and metrics.")
    snap.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    snap.add_argument("--drive-root")
    snap.add_argument("--output-dir", required=True)
    snap.add_argument("--baseline-sha")
    snap.add_argument("--branch", default="revision/q1-logic-mfar")
    snap.add_argument("--source-label", default="MFAR_V1_RETROSPECTIVE")
    snap.set_defaults(func=snapshot)

    comp = sub.add_parser("compare", help="Compare two complete baseline runs.")
    comp.add_argument("--first", required=True)
    comp.add_argument("--second", required=True)
    comp.add_argument("--output", required=True)
    comp.add_argument("--tolerance", type=float, default=1e-12)
    comp.add_argument("--require-canonical-hashes", action="store_true")
    comp.set_defaults(func=compare)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
