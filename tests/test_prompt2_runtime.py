import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from src.mfar_prompt2_runtime import (
    _enforce_unique_berth_assignment,
    _propagate_causal_turnaround_prior,
)


class Prompt2RuntimeTests(unittest.TestCase):
    def test_turnaround_prior_is_forward_only_with_fallback_before_first_episode(self):
        frame = pd.DataFrame({
            "mmsi": [1, 1, 1, 1, 2],
            "grid_time": pd.to_datetime([
                "2026-01-01 10:00", "2026-01-01 10:05", "2026-01-01 10:10",
                "2026-01-01 10:15", "2026-01-01 10:00",
            ]),
            "turnaround_estimate_min": [np.nan, np.nan, 35.0, np.nan, np.nan],
            "turnaround_estimate_source": [None, None, "PRIOR_VESSEL_MEDIAN", None, None],
        })
        result = _propagate_causal_turnaround_prior(frame, fallback=40.0)
        vessel_one = result[result["mmsi"].eq(1)].sort_values("grid_time")
        self.assertEqual(vessel_one["turnaround_estimate_min"].tolist(), [40.0, 40.0, 35.0, 35.0])
        self.assertEqual(
            vessel_one["turnaround_estimate_source"].tolist(),
            ["CONFIGURED_FALLBACK", "CONFIGURED_FALLBACK", "PRIOR_VESSEL_MEDIAN", "PRIOR_VESSEL_MEDIAN"],
        )
        self.assertEqual(
            float(result.loc[result["mmsi"].eq(2), "turnaround_estimate_min"].iloc[0]),
            40.0,
        )
        self.assertTrue(result["turnaround_prior_is_finite"].all())

    def test_overlapping_candidates_receive_distinct_configured_berths(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory)
            pd.DataFrame({
                "parameter": [
                    "grid_interval_min", "state_continuity_gap_factor",
                    "state_stopped_speed_kn", "berth_exit_speed_kn",
                    "berth_exit_radius_multiplier",
                ],
                "value": [5.0, 1.5, 0.8, 1.2, 1.5],
            }).to_csv(config / "pipeline_parameters.csv", index=False)
            pd.DataFrame({
                "port_id": ["BENGKALIS", "BENGKALIS"],
                "berth_id": ["BENGKALIS_BERTH_1", "BENGKALIS_BERTH_2"],
                "latitude": [1.0, 1.0],
                "longitude": [102.0, 102.001],
                "occupancy_radius_nm": [0.12, 0.12],
            }).to_csv(config / "terminal_berths.csv", index=False)
            frame = pd.DataFrame({
                "grid_time": pd.to_datetime(["2026-01-01 10:00"] * 2),
                "mmsi": [1, 2],
                "sog": [0.2, 0.2],
                "nearest_port_id": ["BENGKALIS", "BENGKALIS"],
                "nearest_berth_id": ["BENGKALIS_BERTH_1", "BENGKALIS_BERTH_1"],
                "nearest_distance_nm": [0.02, 0.03],
                "nearest_berth_radius_nm": [0.12, 0.12],
                "distance_to_BENGKALIS_BERTH_1_nm": [0.02, 0.03],
                "distance_to_BENGKALIS_BERTH_2_nm": [0.11, 0.04],
            })
            result = _enforce_unique_berth_assignment(frame, config)
            assigned = result.sort_values("mmsi")["nearest_berth_id"].tolist()
            self.assertEqual(assigned, ["BENGKALIS_BERTH_1", "BENGKALIS_BERTH_2"])
            self.assertEqual(result["nearest_berth_id"].nunique(), 2)
            self.assertTrue(result["berth_assignment_selected"].all())

    def test_excess_candidate_is_demoted_when_both_berths_are_occupied(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory)
            pd.DataFrame({
                "parameter": ["grid_interval_min", "state_continuity_gap_factor", "state_stopped_speed_kn"],
                "value": [5.0, 1.5, 0.8],
            }).to_csv(config / "pipeline_parameters.csv", index=False)
            pd.DataFrame({
                "port_id": ["BENGKALIS", "BENGKALIS"],
                "berth_id": ["BENGKALIS_BERTH_1", "BENGKALIS_BERTH_2"],
                "latitude": [1.0, 1.0],
                "longitude": [102.0, 102.001],
                "occupancy_radius_nm": [0.12, 0.12],
            }).to_csv(config / "terminal_berths.csv", index=False)
            frame = pd.DataFrame({
                "grid_time": pd.to_datetime(["2026-01-01 10:00"] * 3),
                "mmsi": [1, 2, 3],
                "sog": [0.2, 0.2, 0.2],
                "nearest_port_id": ["BENGKALIS"] * 3,
                "nearest_berth_id": ["BENGKALIS_BERTH_1", "BENGKALIS_BERTH_2", "BENGKALIS_BERTH_1"],
                "nearest_distance_nm": [0.01, 0.01, 0.08],
                "nearest_berth_radius_nm": [0.12] * 3,
                "distance_to_BENGKALIS_BERTH_1_nm": [0.01, 0.11, 0.08],
                "distance_to_BENGKALIS_BERTH_2_nm": [0.11, 0.01, 0.09],
            })
            result = _enforce_unique_berth_assignment(frame, config)
            selected = result[result["berth_assignment_selected"]]
            demoted = result[~result["berth_assignment_selected"]]
            self.assertEqual(len(selected), 2)
            self.assertEqual(selected["nearest_berth_id"].nunique(), 2)
            self.assertEqual(len(demoted), 1)
            self.assertEqual(float(demoted.iloc[0]["nearest_berth_radius_nm"]), 0.0)
            self.assertEqual(demoted.iloc[0]["berth_assignment_method"], "UNASSIGNED_CAPACITY_CONFLICT")


if __name__ == "__main__":
    unittest.main()
