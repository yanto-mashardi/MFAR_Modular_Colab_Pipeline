#!/usr/bin/env python3
"""Apply maintenance-only fixes used by Prompt 1.

The script changes presentation/runtime compatibility metadata only:
- replaces deprecated openpyxl style-copy calls with ``copy.copy``;
- assigns deterministic cell IDs required by current nbformat versions.

It does not change model parameters, equations, thresholds, data filters, or
scientific stage outputs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def _stable_cell_id(path: Path, index: int, cell: dict) -> str:
    source = "".join(cell.get("source", []))
    seed = f"{path.as_posix()}::{index}::{cell.get('cell_type')}::{source}"
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]


def normalize_notebook(path: Path) -> bool:
    notebook = json.loads(path.read_text(encoding="utf-8"))
    changed = False
    for index, cell in enumerate(notebook.get("cells", [])):
        cell_id = str(cell.get("id", "")).strip()
        if not cell_id:
            cell_id = _stable_cell_id(path, index, cell)
            cell["id"] = cell_id
            changed = True
        metadata = cell.setdefault("metadata", {})
        if not metadata.get("id"):
            metadata["id"] = cell_id
            changed = True
    if int(notebook.get("nbformat_minor", 0)) < 5:
        notebook["nbformat_minor"] = 5
        changed = True
    if changed:
        path.write_text(
            json.dumps(notebook, ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8",
        )
    return changed


def patch_openpyxl_copy(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    original = text
    if "from copy import copy\n" not in text:
        text = text.replace(
            "from __future__ import annotations\n\n",
            "from __future__ import annotations\n\nfrom copy import copy\n",
            1,
        )
    text = text.replace(
        '                cell.font = cell.font.copy(bold=True, color="FFFFFF")\n'
        '                cell.fill = cell.fill.copy(fill_type="solid", fgColor="0B5FA5")\n',
        '                header_font = copy(cell.font)\n'
        '                header_font.bold = True\n'
        '                header_font.color = "FFFFFF"\n'
        '                cell.font = header_font\n'
        '                header_fill = copy(cell.fill)\n'
        '                header_fill.fill_type = "solid"\n'
        '                header_fill.fgColor = "0B5FA5"\n'
        '                cell.fill = header_fill\n',
    )
    if ".font.copy(" in text or ".fill.copy(" in text:
        raise RuntimeError("Deprecated openpyxl style copy call remains.")
    if text != original:
        path.write_text(text, encoding="utf-8")
        return True
    return False


def apply(repo_root: Path) -> list[str]:
    changed: list[str] = []
    visual = repo_root / "src" / "mfar_visuals.py"
    if patch_openpyxl_copy(visual):
        changed.append(visual.relative_to(repo_root).as_posix())
    for path in sorted((repo_root / "notebooks").glob("*.ipynb")):
        if normalize_notebook(path):
            changed.append(path.relative_to(repo_root).as_posix())
    return changed


def check(repo_root: Path) -> None:
    visual = (repo_root / "src" / "mfar_visuals.py").read_text(encoding="utf-8")
    if ".font.copy(" in visual or ".fill.copy(" in visual:
        raise AssertionError("Deprecated openpyxl style-copy API remains.")
    missing = []
    for path in sorted((repo_root / "notebooks").glob("*.ipynb")):
        notebook = json.loads(path.read_text(encoding="utf-8"))
        for index, cell in enumerate(notebook.get("cells", [])):
            if not str(cell.get("id", "")).strip():
                missing.append(f"{path.name}:cell-{index}")
    if missing:
        raise AssertionError("Notebook cells without IDs: " + ", ".join(missing))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    root = Path(args.repo_root).resolve()
    if args.check:
        check(root)
        print("Behavior-preserving maintenance check: PASS")
        return 0
    changed = apply(root)
    check(root)
    print("Changed files:")
    for item in changed:
        print("-", item)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
