import unittest
from pathlib import Path

import pandas as pd

from src.mfar_core import _calibration_cutoff
from src.mfar_maps import segment_trajectories


ROOT = Path(__file__).resolve().parents[1]


class AuditedPipelineTests(unittest.TestCase):
    def test_calendar_holdout_uses_complete_final_month(self):
        values = pd.Series(pd.to_datetime(["2026-01-01 06:00", "2026-03-31 23:55"]))
        self.assertEqual(
            _calibration_cutoff(values),
            pd.Timestamp("2026-02-28 23:59:59.999999999"),
        )

    def test_track_segmentation_breaks_day_gap_and_spatial_jump(self):
        frame = pd.DataFrame({
            "mmsi": [1, 1, 1, 1],
            "timestamp": pd.to_datetime(["2026-03-01 10:00", "2026-03-01 10:05",
                                          "2026-03-02 10:00", "2026-03-02 10:05"]),
            "latitude": [1.40, 1.401, 1.40, 1.46],
            "longitude": [102.14, 102.141, 102.14, 102.17],
        })
        segmented = segment_trajectories(frame, "timestamp", max_gap_min=20, max_jump_nm=1.5)
        self.assertEqual(segmented["map_segment_id"].nunique(), 3)

    def test_every_rule_antecedent_is_configured(self):
        memberships = pd.read_csv(ROOT / "config" / "membership_parameters.csv")
        rules = pd.read_csv(ROOT / "config" / "fuzzy_rules.csv")
        defined = set(memberships["membership_column"])
        used = {
            str(value)
            for column in ["antecedent_1", "antecedent_2", "antecedent_3", "antecedent_4"]
            for value in rules[column].dropna()
            if str(value).strip()
        }
        self.assertTrue(used <= defined)

    def test_actions_have_phase_constraints(self):
        rules = pd.read_csv(ROOT / "config" / "fuzzy_rules.csv")
        constraints = pd.read_csv(ROOT / "config" / "action_constraints.csv")
        self.assertTrue(set(rules["response"]) <= set(constraints["action"]))
        feasible_depart = constraints[
            constraints["action"].isin(["DEPART_NOW", "HOLD_DEPARTURE"])
            & constraints["feasible"].eq(1)
        ]
        self.assertEqual(set(feasible_depart["phase"]), {"AT_ORIGIN_TERMINAL"})
        feasible_reduce = constraints[
            constraints["action"].eq("REDUCE_SPEED") & constraints["feasible"].eq(1)
        ]
        self.assertEqual(set(feasible_reduce["phase"]), {"SAILING", "APPROACHING_DESTINATION"})

    def test_notebooks_do_not_embed_legacy_one_day_or_rules(self):
        text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted((ROOT / "notebooks").glob("0[3-7]_*.ipynb"))
        )
        for forbidden in ["SIM_DATE", "RULE_TEXT", "accepted_intervention_recommendations", "2026-01-01"]:
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
