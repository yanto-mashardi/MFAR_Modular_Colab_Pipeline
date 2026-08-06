import unittest

import numpy as np
import pandas as pd

from src.mfar_prompt2_runtime import _propagate_causal_turnaround_prior


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


if __name__ == "__main__":
    unittest.main()
