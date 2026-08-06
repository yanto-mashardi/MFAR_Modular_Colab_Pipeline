"""Runtime adapter for Prompt 2 Stage 03 outputs.

Two concerns are isolated here:
1. Plotly 6 with NumPy 2 cannot promote nullable integer MMSI and datetime
   hover columns in one timeline array. MMSI is converted only in a temporary
   visualization copy.
2. Stage 04 requires a finite turnaround prior at every decision state. Episode
   estimates exist on berth rows, so they are propagated forward within each
   vessel sequence. Rows before the first observed estimate use the configured
   fallback. Forward propagation is causal and does not use later episodes.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from . import mfar_state_episode as implementation
from .mfar_visuals import stage3_berth_outputs as original_stage3_berth_outputs


def _plotly_safe_stage3_outputs(state: pd.DataFrame, audit: pd.DataFrame, stage_dir: Path) -> None:
    visual_state = state.copy()
    if "mmsi" in visual_state.columns:
        visual_state["mmsi"] = visual_state["mmsi"].astype("string")
    original_stage3_berth_outputs(visual_state, audit, stage_dir)


def _configured_turnaround(config_dir: Path) -> float:
    parameters = pd.read_csv(Path(config_dir) / "pipeline_parameters.csv")
    values = dict(zip(parameters["parameter"], pd.to_numeric(parameters["value"], errors="coerce")))
    value = values.get("turnaround_min", 40.0)
    return float(value) if pd.notna(value) else 40.0


def _propagate_causal_turnaround_prior(state: pd.DataFrame, fallback: float) -> pd.DataFrame:
    out = state.copy()
    out["grid_time"] = pd.to_datetime(out["grid_time"], errors="coerce")
    out = out.sort_values(["mmsi", "grid_time"]).reset_index(drop=True)

    estimate = pd.to_numeric(out.get("turnaround_estimate_min"), errors="coerce")
    estimate = estimate.groupby(out["mmsi"]).ffill().fillna(float(fallback))
    out["turnaround_estimate_min"] = estimate.astype(float)

    source = out.get(
        "turnaround_estimate_source",
        pd.Series(index=out.index, dtype="object"),
    ).astype("string")
    source = source.groupby(out["mmsi"]).ffill().fillna("CONFIGURED_FALLBACK")
    out["turnaround_estimate_source"] = source.astype(str)
    out["turnaround_prior_is_finite"] = np.isfinite(out["turnaround_estimate_min"])
    return out


def run_stage3(
    state: pd.DataFrame,
    profiles: pd.DataFrame,
    stage_dir: Path,
    config_dir: Path,
):
    """Run Stage 03 with isolated visualization and causal-prior compatibility."""
    previous = implementation.stage3_berth_outputs
    implementation.stage3_berth_outputs = _plotly_safe_stage3_outputs
    try:
        result = implementation.run_stage3(state, profiles, stage_dir, config_dir)
    finally:
        implementation.stage3_berth_outputs = previous

    out, episodes, empirical, audit, calibration_cutoff = result
    out = _propagate_causal_turnaround_prior(
        out,
        fallback=_configured_turnaround(config_dir),
    )
    Path(stage_dir).mkdir(parents=True, exist_ok=True)
    out.to_csv(Path(stage_dir) / "03_input_state_enhanced.csv", index=False)
    return out, episodes, empirical, audit, calibration_cutoff
