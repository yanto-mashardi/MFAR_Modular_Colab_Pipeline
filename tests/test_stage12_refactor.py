import json
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from src.mfar_stage12 import (
    build_operational_state,
    circular_interpolate_deg,
    interpolate_one_vessel,
    prepare_stage1_frames,
)

ROOT = Path(__file__).resolve().parents[1]


class Stage12RefactorTests(unittest.TestCase):
    def _valid_row(self, minute: int, **changes):
        row = {
            "created_at": f"2026-01-01 00:{minute:02d}:00+00:00",
            "mmsi": 525002121,
            "lat": 1.40,
            "lon": 102.14,
            "sog": 5.0,
            "cog": 90.0,
            "valid": True,
            "navstatus": 0,
        }
        row.update(changes)
        return row

    def test_stage1_rejection_priority_and_duplicate_contract(self):
        rows = [self._valid_row(i) for i in range(20)]
        rows.extend([
            self._valid_row(20, lat=0.0, lon=0.0, sog=99.0),
            self._valid_row(21, sog=16.0),
            self._valid_row(22, lat=1.60),
            self._valid_row(0),
        ])
        result = prepare_stage1_frames(pd.DataFrame(rows))
        counts = result.rejected["rejection_reason"].value_counts().to_dict()
        self.assertEqual(counts["zero_coordinate"], 1)
        self.assertEqual(counts["invalid_sog"], 1)
        self.assertEqual(counts["outside_research_corridor"], 1)
        self.assertEqual(counts["duplicate"], 1)
        self.assertTrue(result.clean["timestamp"].is_monotonic_increasing)

    def test_stage1_segment_breaks_on_day_gap_and_implied_speed(self):
        rows = [
            self._valid_row(0, lat=1.4000, lon=102.1400),
            self._valid_row(5, lat=1.4001, lon=102.1401),
            self._valid_row(30, lat=1.4002, lon=102.1402),
        ]
        rows[2]["created_at"] = "2026-01-02 00:30:00+00:00"
        result = prepare_stage1_frames(pd.DataFrame(rows))
        self.assertEqual(result.trajectory["trajectory_segment_id"].nunique(), 2)

    def test_circular_interpolation_uses_shortest_angle(self):
        value = circular_interpolate_deg(350.0, 10.0, 0.5)
        self.assertTrue(np.isclose(value, 0.0) or np.isclose(value, 360.0))

    def test_interpolation_rejects_bracket_above_twenty_minutes(self):
        frame = pd.DataFrame({
            "timestamp": pd.to_datetime(["2026-01-01 00:01", "2026-01-01 00:29"]),
            "mmsi": [1, 1], "latitude": [1.4, 1.41], "longitude": [102.14, 102.15],
            "sog": [5.0, 7.0], "cog": [350.0, 10.0], "nav_status": [0, 0],
        })
        accepted, rejected = interpolate_one_vessel(frame, 5, 20)
        self.assertTrue(accepted.empty)
        self.assertTrue((rejected["rejection_reason"] == "bracket_gap_too_large").all())

    def test_operational_state_contract_has_no_failed_audit(self):
        grid = pd.DataFrame({
            "grid_time": pd.to_datetime(["2026-01-01 00:00", "2026-01-01 00:05"]),
            "mmsi": [1, 1], "latitude": [1.4000, 1.4001],
            "longitude": [102.1400, 102.1401], "sog": [0.0, 0.0], "cog": [0.0, 0.0],
        })
        berths = pd.DataFrame({
            "port_id": ["A", "A", "B", "B"], "berth_id": ["A1", "A2", "B1", "B2"],
            "latitude": [1.4000, 1.4002, 1.4500, 1.4502],
            "longitude": [102.1400, 102.1402, 102.1500, 102.1502],
            "occupancy_radius_nm": [0.12, 0.12, 0.12, 0.12],
        })
        out, audit, _ = build_operational_state(grid, berths)
        self.assertEqual(int(audit["failed_rows"].sum()), 0)
        self.assertTrue(out["operational_status"].str.startswith("AT_BERTH").all())

    def test_stage_notebooks_are_thin_independent_colab_controllers(self):
        for name, runner in [
            ("01_AIS_Input_and_Cleaning.ipynb", "run_stage1"),
            ("02_Time_Grid_and_State_Preparation.ipynb", "run_stage2"),
        ]:
            notebook = json.loads((ROOT / "notebooks" / name).read_text(encoding="utf-8"))
            self.assertLessEqual(len(notebook["cells"]), 6)
            self.assertTrue(all(str(cell.get("id", "")).strip() for cell in notebook["cells"]))
            text = "\n".join("".join(cell.get("source", [])) for cell in notebook["cells"])
            self.assertIn(runner, text)
            self.assertIn("MFAR_CODE_ROOT", text)
            self.assertIn("refactor/prompt1-stage01-02", text)


if __name__ == "__main__":
    unittest.main()
