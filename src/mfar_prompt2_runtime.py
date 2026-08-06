"""Runtime compatibility adapter for Prompt 2 Stage 03 visual outputs.

The analytical Stage 03 dataframe retains numeric MMSI values. Plotly 6 with
NumPy 2 cannot promote nullable integer MMSI and datetime hover columns in one
array when constructing the legacy timeline. This adapter converts MMSI only in
the temporary visualization copy; persisted CSV contracts and analytical dtypes
remain unchanged.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import mfar_state_episode as implementation
from .mfar_visuals import stage3_berth_outputs as original_stage3_berth_outputs


def _plotly_safe_stage3_outputs(state: pd.DataFrame, audit: pd.DataFrame, stage_dir: Path) -> None:
    visual_state = state.copy()
    if "mmsi" in visual_state.columns:
        visual_state["mmsi"] = visual_state["mmsi"].astype("string")
    original_stage3_berth_outputs(visual_state, audit, stage_dir)


def run_stage3(*args, **kwargs):
    """Run Stage 03 while isolating the Plotly dtype compatibility conversion."""
    previous = implementation.stage3_berth_outputs
    implementation.stage3_berth_outputs = _plotly_safe_stage3_outputs
    try:
        return implementation.run_stage3(*args, **kwargs)
    finally:
        implementation.stage3_berth_outputs = previous
