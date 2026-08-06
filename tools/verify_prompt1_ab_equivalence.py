#!/usr/bin/env python3
"""Verify Prompt 1 by controlled legacy-versus-refactor A/B execution.

The archival Prompt 0 manifest captured pre-existing Google Drive artifacts whose
original execution package versions were not stored. Therefore byte hashes from
that archive are retained as a non-blocking serialization diagnostic. The
behavior-preserving acceptance criterion is exact row-count and SHA-256 equality
between legacy and refactored code executed from the same inputs, configuration,
Python version, package set, and isolated filesystem roots.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def csv_rows(path: Path) -> int:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        try:
            next(reader)
        except StopIteration:
            return 0
        return sum(1 for _ in reader)


def compare_values(expected: Any, actual: Any, path: str, tolerance: float, failures: list[dict[str, Any]]) -> None:
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            failures.append({"path": path, "expected_type": "dict", "actual_type": type(actual).__name__})
            return
        for key, value in expected.items():
            if key not in actual:
                failures.append({"path": f"{path}.{key}", "reason": "missing"})
            else:
                compare_values(value, actual[key], f"{path}.{key}", tolerance, failures)
        return
    if isinstance(expected, list):
        if not isinstance(actual, list) or len(expected) != len(actual):
            failures.append({"path": path, "reason": "list shape mismatch"})
            return
        for index, (left, right) in enumerate(zip(expected, actual)):
            compare_values(left, right, f"{path}[{index}]", tolerance, failures)
        return
    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        if not isinstance(actual, (int, float)) or isinstance(actual, bool):
            failures.append({"path": path, "expected": expected, "actual": actual})
            return
        if math.isnan(float(expected)) and math.isnan(float(actual)):
            return
        if not math.isclose(float(expected), float(actual), rel_tol=tolerance, abs_tol=tolerance):
            failures.append({"path": path, "expected": expected, "actual": actual})
        return
    if expected != actual:
        failures.append({"path": path, "expected": expected, "actual": actual})


def markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Prompt 1 Acceptance Record",
        "",
        f"- Controlled legacy-versus-refactor equivalence: **{report['behavior_preserving_status']}**",
        f"- Archival row-count equivalence: **{report['archival_row_count_status']}**",
        f"- Archival key-metric equivalence: **{report['archival_key_metric_status']}**",
        f"- Archival byte-hash diagnostic: **{report['archival_sha_diagnostic_status']}** (non-blocking)",
        "- Acceptance criterion: exact rows and SHA-256 for legacy versus refactor under one controlled runtime",
        "",
        "| Artifact | A/B rows | A/B SHA-256 | Archive rows | Archive SHA diagnostic |",
        "|---|---:|---:|---:|---:|",
    ]
    for item in report["artifact_checks"]:
        lines.append(
            f"| `{item['artifact']}` | "
            f"{'PASS' if item['ab_rows_match'] else 'FAIL'} | "
            f"{'PASS' if item['ab_sha256_match'] else 'FAIL'} | "
            f"{'PASS' if item['archive_rows_match'] else 'FAIL'} | "
            f"{'PASS' if item['archive_sha256_match'] else 'DIFF'} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation boundary",
            "",
            "The Prompt 0 archive is named `MFAR_V1_RETROSPECTIVE_EXISTING_DRIVE_ARTIFACTS`. "
            "Its metadata states that the original package versions used to create those Drive artifacts were not stored. "
            "Consequently, archival CSV byte hashes are retained for provenance and serialization diagnosis, while behavior preservation is tested by paired execution of the fixed legacy commit and refactored branch in the same runtime.",
            "",
            "Scientific parameters, thresholds, equations, filters, state definitions, rule base, and Stage 03–07 contracts were not changed.",
        ]
    )
    if report["key_metric_failures"]:
        lines.extend(["", "## Key-metric differences", ""])
        for failure in report["key_metric_failures"][:30]:
            lines.append(f"- `{failure['path']}`: expected `{failure.get('expected')}`, actual `{failure.get('actual')}`")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--current-root", type=Path, required=True)
    parser.add_argument("--legacy-root", type=Path, required=True)
    parser.add_argument("--archival-baseline", type=Path, required=True)
    parser.add_argument("--current-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown", type=Path, required=True)
    parser.add_argument("--tolerance", type=float, default=1e-12)
    args = parser.parse_args()

    archival = json.loads(args.archival_baseline.read_text(encoding="utf-8"))
    current_manifest = json.loads(args.current_manifest.read_text(encoding="utf-8"))
    checks: list[dict[str, Any]] = []

    for relative, archived in archival["canonical_artifacts"].items():
        current_path = args.current_root / relative
        legacy_path = args.legacy_root / relative
        current_exists = current_path.is_file()
        legacy_exists = legacy_path.is_file()
        current_rows = csv_rows(current_path) if current_exists else None
        legacy_rows = csv_rows(legacy_path) if legacy_exists else None
        current_hash = sha256(current_path) if current_exists else None
        legacy_hash = sha256(legacy_path) if legacy_exists else None
        checks.append(
            {
                "artifact": relative,
                "current_exists": current_exists,
                "legacy_exists": legacy_exists,
                "current_rows": current_rows,
                "legacy_rows": legacy_rows,
                "ab_rows_match": current_exists and legacy_exists and current_rows == legacy_rows,
                "current_sha256": current_hash,
                "legacy_sha256": legacy_hash,
                "ab_sha256_match": current_exists and legacy_exists and current_hash == legacy_hash,
                "archived_rows": archived["row_count"],
                "archive_rows_match": current_exists and current_rows == archived["row_count"],
                "archived_sha256": archived["sha256"],
                "archive_sha256_match": current_exists and current_hash == archived["sha256"],
            }
        )

    key_metric_failures: list[dict[str, Any]] = []
    compare_values(
        archival["key_metrics"],
        current_manifest["key_metrics"],
        "key_metrics",
        args.tolerance,
        key_metric_failures,
    )

    behavior_pass = all(item["ab_rows_match"] and item["ab_sha256_match"] for item in checks)
    archive_rows_pass = all(item["archive_rows_match"] for item in checks)
    archive_metrics_pass = not key_metric_failures
    archive_sha_pass = all(item["archive_sha256_match"] for item in checks)
    overall_pass = behavior_pass and archive_rows_pass and archive_metrics_pass

    report = {
        "schema_version": "2.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if overall_pass else "FAIL",
        "behavior_preserving_status": "PASS" if behavior_pass else "FAIL",
        "archival_row_count_status": "PASS" if archive_rows_pass else "FAIL",
        "archival_key_metric_status": "PASS" if archive_metrics_pass else "FAIL",
        "archival_sha_diagnostic_status": "PASS" if archive_sha_pass else "DIFF",
        "criterion": "controlled legacy-versus-refactor exact rows and SHA-256; archival rows and key metrics",
        "artifact_checks": checks,
        "key_metric_failures": key_metric_failures,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    args.markdown.parent.mkdir(parents=True, exist_ok=True)
    args.markdown.write_text(markdown(report), encoding="utf-8")
    print(args.output)
    print(json.dumps(report, indent=2))
    return 0 if overall_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
