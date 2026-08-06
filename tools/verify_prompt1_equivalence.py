#!/usr/bin/env python3
"""Compare Prompt 1 outputs with the immutable Prompt 0 baseline."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def csv_rows(path: Path) -> int:
    with path.open("rb") as handle:
        return max(0, sum(1 for _ in handle) - 1)


def verify(baseline_path: Path, drive_root: Path) -> dict[str, Any]:
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    expected = baseline["canonical_artifacts"]
    checks = []
    for relative, record in expected.items():
        current = drive_root / relative
        exists = current.is_file()
        row_count = csv_rows(current) if exists and current.suffix.lower() == ".csv" else None
        digest = sha256(current) if exists else None
        checks.append({
            "artifact": relative,
            "exists": exists,
            "expected_rows": record.get("row_count"),
            "actual_rows": row_count,
            "rows_match": exists and row_count == record.get("row_count"),
            "expected_sha256": record.get("sha256"),
            "actual_sha256": digest,
            "sha256_match": exists and digest == record.get("sha256"),
        })
    passed = all(item["rows_match"] and item["sha256_match"] for item in checks)
    stage12 = [item for item in checks if "/stage_01/" in item["artifact"] or "/stage_02/" in item["artifact"]]
    downstream = [item for item in checks if item not in stage12]
    return {
        "schema_version": "1.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if passed else "FAIL",
        "criterion": "exact row-count and SHA-256 equivalence",
        "stage_01_02_status": "PASS" if all(x["rows_match"] and x["sha256_match"] for x in stage12) else "FAIL",
        "downstream_stage_03_07_status": "PASS" if all(x["rows_match"] and x["sha256_match"] for x in downstream) else "FAIL",
        "checks": checks,
    }


def markdown(report: dict[str, Any]) -> str:
    rows = [
        "# Prompt 1 Acceptance Record",
        "",
        f"- Overall equivalence: **{report['status']}**",
        f"- Stage 01–02 equivalence: **{report['stage_01_02_status']}**",
        f"- Downstream Stage 03–07 equivalence: **{report['downstream_stage_03_07_status']}**",
        f"- Criterion: {report['criterion']}",
        "",
        "| Artifact | Rows | SHA-256 |",
        "|---|---:|---|",
    ]
    for item in report["checks"]:
        rows.append(
            f"| `{item['artifact']}` | {'PASS' if item['rows_match'] else 'FAIL'} | "
            f"{'PASS' if item['sha256_match'] else 'FAIL'} |"
        )
    rows.extend([
        "",
        "Scientific parameters, thresholds, equations, filters, rule base, and downstream stage contracts were not changed in Prompt 1.",
        "",
    ])
    return "\n".join(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--drive-root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--markdown")
    args = parser.parse_args()
    report = verify(Path(args.baseline), Path(args.drive_root))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if args.markdown:
        md = Path(args.markdown)
        md.parent.mkdir(parents=True, exist_ok=True)
        md.write_text(markdown(report), encoding="utf-8")
    print(output)
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
