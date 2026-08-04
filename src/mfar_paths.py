"""Central path resolution and stage-boundary validation for MFAR notebooks."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import pandas as pd

DRIVE_FOLDER_NAME = "In_Out_MFAR_Modular_Colab_Pipeline"
DRIVE_FOLDER_ID = "1CrvswSCmR0_Tr7mWYufrOXYgCMdRQpgq"
GDRIVE_URL = (
    "https://drive.google.com/drive/folders/"
    f"{DRIVE_FOLDER_ID}?usp=sharing"
)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"


def _is_colab() -> bool:
    try:
        import google.colab  # type: ignore  # noqa: F401
    except ImportError:
        return False
    return True


def _mount_colab_drive() -> None:
    if not _is_colab():
        return
    from google.colab import drive  # type: ignore

    drive.mount("/content/drive", force_remount=False)


def _candidate_roots() -> list[Path]:
    candidates: list[Path] = []
    override = os.environ.get("MFAR_GDRIVE_ROOT", "").strip()
    if override:
        candidates.append(Path(override).expanduser())

    candidates.extend(
        [
            Path("/content/drive/MyDrive") / DRIVE_FOLDER_NAME,
            Path("/content/drive/MyDrive") / "Post Doctor" / DRIVE_FOLDER_NAME,
            Path("/content/drive/Shareddrives") / DRIVE_FOLDER_NAME,
        ]
    )

    # Common Google Drive for Desktop locations on Windows. The environment
    # override remains the reliable option for custom drive letters/locations.
    if os.name == "nt":
        for letter in "GHIJKLMNOPQRSTUVWXYZ":
            base = Path(f"{letter}:/")
            candidates.extend(
                [
                    base / "My Drive" / DRIVE_FOLDER_NAME,
                    base / "MyDrive" / DRIVE_FOLDER_NAME,
                    base / DRIVE_FOLDER_NAME,
                ]
            )
        user_profile = os.environ.get("USERPROFILE", "").strip()
        if user_profile:
            home = Path(user_profile)
            candidates.extend(
                [
                    home / "Google Drive" / "My Drive" / DRIVE_FOLDER_NAME,
                    home / "My Drive" / DRIVE_FOLDER_NAME,
                ]
            )

    # Preserve order while removing duplicates.
    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key not in seen:
            seen.add(key)
            unique.append(candidate)
    return unique


def resolve_drive_root() -> Path:
    """Resolve the synchronized/mounted I/O folder or fail with diagnostics."""
    _mount_colab_drive()
    checked = _candidate_roots()
    for candidate in checked:
        try:
            if candidate.is_dir() and candidate.name == DRIVE_FOLDER_NAME:
                return candidate.resolve()
        except OSError:
            # An unavailable or sandbox-restricted mounted drive must not mask
            # the actionable resolver diagnostic below.
            continue

    rendered = "\n".join(f"  - {path}" for path in checked)
    raise FileNotFoundError(
        f"Folder Google Drive '{DRIVE_FOLDER_NAME}' tidak ditemukan.\n"
        f"Path yang diperiksa:\n{rendered}\n"
        "Mount/sinkronkan Google Drive, lalu tetapkan MFAR_GDRIVE_ROOT ke path "
        "folder tersebut (bukan folder ID atau URL). "
        f"Folder ID dokumentasi: {DRIVE_FOLDER_ID}"
    )


DRIVE_ROOT = resolve_drive_root()
DATA_RAW_DIR = DRIVE_ROOT / "data_raw"
STAGE_OUTPUT_DIR = DRIVE_ROOT / "stage_output"
AIS_RAW_PATH = DATA_RAW_DIR / "ais_raw.csv"
VEHICLE_ARRIVAL_PATH = DATA_RAW_DIR / "vehicle_arrival_rate_30min.csv"
STAGE_01_DIR = STAGE_OUTPUT_DIR / "stage_01"
STAGE_02_DIR = STAGE_OUTPUT_DIR / "stage_02"
STAGE_03_DIR = STAGE_OUTPUT_DIR / "stage_03"
STAGE_04_DIR = STAGE_OUTPUT_DIR / "stage_04"
STAGE_05_DIR = STAGE_OUTPUT_DIR / "stage_05"
STAGE_06_DIR = STAGE_OUTPUT_DIR / "stage_06"
STAGE_07_DIR = STAGE_OUTPUT_DIR / "stage_07"
STAGE_DIRS = {
    1: STAGE_01_DIR,
    2: STAGE_02_DIR,
    3: STAGE_03_DIR,
    4: STAGE_04_DIR,
    5: STAGE_05_DIR,
    6: STAGE_06_DIR,
    7: STAGE_07_DIR,
}

for _stage_dir in STAGE_DIRS.values():
    _stage_dir.mkdir(parents=True, exist_ok=True)


def validate_writable_directory(path: Path, notebook: str, stage: int) -> None:
    """Verify output writability without deleting or replacing user artifacts."""
    path.mkdir(parents=True, exist_ok=True)
    probe = path / f".mfar_stage_{stage:02d}_write_probe.tmp"
    try:
        probe.write_text("mfar-write-test", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        raise PermissionError(
            f"{notebook} (Stage {stage:02d}) tidak dapat menulis ke {path}: {exc}"
        ) from exc


def validate_csv_input(
    path: Path,
    required_columns: Sequence[str],
    notebook: str,
    stage: int,
) -> pd.DataFrame:
    """Read a non-empty CSV and enforce its stage-boundary schema."""
    if not path.is_file():
        raise FileNotFoundError(
            f"{notebook} (Stage {stage:02d}) membutuhkan file: {path}"
        )
    try:
        frame = pd.read_csv(path)
    except Exception as exc:
        raise ValueError(
            f"{notebook} (Stage {stage:02d}) gagal membaca CSV {path}: {exc}"
        ) from exc
    if frame.empty:
        raise ValueError(
            f"{notebook} (Stage {stage:02d}) menerima CSV kosong: {path}"
        )
    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        raise ValueError(
            f"{notebook} (Stage {stage:02d}) menemukan kolom wajib hilang "
            f"pada {path}: {', '.join(missing)}"
        )
    return frame


def validate_raw_inputs(notebook: str = "01_AIS_Input_and_Cleaning.ipynb") -> None:
    """Validate existence/readability and minimal schemas of both raw inputs."""
    validate_csv_input(
        AIS_RAW_PATH,
        ["created_at", "mmsi", "lat", "lon", "sog", "cog", "valid", "navstatus"],
        notebook,
        1,
    )
    validate_csv_input(
        VEHICLE_ARRIVAL_PATH,
        [
            "port_id",
            "time_start",
            "time_end",
            "car_arrival_rate_30min",
            "motorcycle_arrival_rate_30min",
        ],
        notebook,
        1,
    )


def write_execution_metadata(
    stage: int,
    notebook: str,
    started_at: datetime,
    input_paths: Iterable[Path],
    input_rows: Mapping[str, int],
    output_rows: Mapping[str, int],
    output_files: Iterable[Path],
) -> Path:
    """Write a stable JSON execution summary and print every saved artifact."""
    output_dir = STAGE_DIRS[stage]
    files = [Path(path) for path in output_files]
    metadata_path = output_dir / f"{stage:02d}_execution_metadata.json"
    payload = {
        "stage": stage,
        "notebook": notebook,
        "started_at_utc": started_at.astimezone(timezone.utc).isoformat(),
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "drive_root": str(DRIVE_ROOT),
        "input_sources": [str(Path(path)) for path in input_paths],
        "input_rows": dict(input_rows),
        "output_rows": dict(output_rows),
        "output_directory": str(output_dir),
        "output_files": [str(path) for path in files],
    }
    metadata_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print("File berhasil disimpan:")
    for path in [*files, metadata_path]:
        print(f"- {path}")
    return metadata_path
