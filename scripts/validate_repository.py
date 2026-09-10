"""Lightweight repository audit for MFAR.

The audit intentionally avoids reading private Google Drive data. It validates the
versioned scientific configuration, notebook structure, repository hygiene, and
cross-file contracts that can be checked from a clean GitHub checkout.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_NOTEBOOKS = [
    "00_Run_All_Stages.ipynb",
    "01_AIS_Input_and_Cleaning.ipynb",
    "02_Time_Grid_and_State_Preparation.ipynb",
    "03_Monitoring_State.ipynb",
    "04_No_Intervention_Forecast.ipynb",
    "05_Fuzzification.ipynb",
    "06_Rule_Evaluation.ipynb",
    "07_Candidate_Action.ipynb",
]

REQUIRED_CONFIGS = [
    "action_constraints.csv",
    "fuzzy_rules.csv",
    "membership_parameters.csv",
    "pipeline_parameters.csv",
    "terminal_berths.csv",
    "vessel_profiles.csv",
]

FORBIDDEN_FILENAMES = {
    "desktop.ini",
    "Thumbs.db",
    ".DS_Store",
    ".env",
}

FORBIDDEN_DIRECTORIES = {
    "data_raw",
    "stage_output",
    "outputs",
    "artifacts",
    "In_Out_MFAR_Modular_Colab_Pipeline",
}


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = reader.fieldnames or []
        rows = list(reader)
    return headers, rows


def require_columns(path: Path, required: set[str], errors: list[str]) -> list[dict[str, str]]:
    headers, rows = read_csv(path)
    missing = sorted(required - set(headers))
    if missing:
        errors.append(f"{path.relative_to(ROOT)} missing columns: {', '.join(missing)}")
    if len(headers) != len(set(headers)):
        errors.append(f"{path.relative_to(ROOT)} contains duplicate column names")
    if not rows:
        errors.append(f"{path.relative_to(ROOT)} contains no data rows")
    return rows


def validate_notebooks(errors: list[str]) -> None:
    notebook_dir = ROOT / "notebooks"
    for name in REQUIRED_NOTEBOOKS:
        path = notebook_dir / name
        if not path.is_file():
            errors.append(f"Missing required notebook: notebooks/{name}")
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            errors.append(f"Invalid notebook JSON in notebooks/{name}: {exc}")
            continue
        if payload.get("nbformat") != 4:
            errors.append(f"notebooks/{name} must use notebook format 4")
        if not isinstance(payload.get("cells"), list):
            errors.append(f"notebooks/{name} has no valid cells list")


def validate_config_contracts(errors: list[str]) -> None:
    config_dir = ROOT / "config"
    for name in REQUIRED_CONFIGS:
        if not (config_dir / name).is_file():
            errors.append(f"Missing required configuration: config/{name}")

    if errors:
        return

    membership_rows = require_columns(
        config_dir / "membership_parameters.csv",
        {"membership_column", "scope"},
        errors,
    )
    rule_rows = require_columns(
        config_dir / "fuzzy_rules.csv",
        {
            "antecedent_1",
            "antecedent_2",
            "antecedent_3",
            "antecedent_4",
            "consequence",
            "response",
        },
        errors,
    )
    constraint_rows = require_columns(
        config_dir / "action_constraints.csv",
        {"action", "phase", "feasible"},
        errors,
    )
    require_columns(
        config_dir / "pipeline_parameters.csv",
        set(),
        errors,
    )
    require_columns(
        config_dir / "terminal_berths.csv",
        set(),
        errors,
    )
    require_columns(
        config_dir / "vessel_profiles.csv",
        set(),
        errors,
    )

    defined_memberships = {
        row.get("membership_column", "").strip()
        for row in membership_rows
        if row.get("membership_column", "").strip()
    }
    used_antecedents = {
        row.get(column, "").strip()
        for row in rule_rows
        for column in ("antecedent_1", "antecedent_2", "antecedent_3", "antecedent_4")
        if row.get(column, "").strip()
    }
    undefined = sorted(used_antecedents - defined_memberships)
    if undefined:
        errors.append("Rules use undefined memberships: " + ", ".join(undefined))

    configured_actions = {
        row.get("action", "").strip()
        for row in constraint_rows
        if row.get("action", "").strip()
    }
    rule_actions = {
        row.get("response", "").strip()
        for row in rule_rows
        if row.get("response", "").strip()
    }
    missing_actions = sorted(rule_actions - configured_actions)
    if missing_actions:
        errors.append("Rules use actions without phase constraints: " + ", ".join(missing_actions))


def validate_repository_hygiene(errors: list[str]) -> None:
    for path in ROOT.rglob("*"):
        relative = path.relative_to(ROOT)
        if ".git" in relative.parts:
            continue
        if path.is_file() and path.name in FORBIDDEN_FILENAMES:
            errors.append(f"Forbidden local/system file is tracked: {relative}")
        if path.is_dir() and path.name in FORBIDDEN_DIRECTORIES:
            errors.append(f"Generated/private directory must stay outside Git: {relative}")

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    if "Folder ID:" in readme:
        errors.append("README.md exposes a Google Drive folder identifier")


def main() -> int:
    errors: list[str] = []
    validate_notebooks(errors)
    validate_config_contracts(errors)
    validate_repository_hygiene(errors)

    if errors:
        print("MFAR repository audit: FAIL")
        for error in errors:
            print(f"- {error}")
        return 1

    print("MFAR repository audit: PASS")
    print(f"- notebooks validated: {len(REQUIRED_NOTEBOOKS)}")
    print(f"- configuration files validated: {len(REQUIRED_CONFIGS)}")
    print("- repository hygiene checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
