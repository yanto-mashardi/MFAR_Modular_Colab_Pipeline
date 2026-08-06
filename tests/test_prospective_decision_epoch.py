import unittest

import pandas as pd

from src.mfar_prospective_forecast import (
    attach_posthoc_validation,
    build_prospective_decision_epochs,
)


class ProspectiveDecisionEpochTests(unittest.TestCase):
    @staticmethod
    def _state(future_departure_minute: int) -> pd.DataFrame:
        times = pd.to_datetime([
            "2026-03-01 10:00",
            "2026-03-01 10:05",
            "2026-03-01 10:10",
            f"2026-03-01 10:{future_departure_minute:02d}",
        ])
        return pd.DataFrame({
            "grid_time": times,
            "mmsi": [1] * 4,
            "is_at_berth": [True, True, True, False],
            "operational_status": ["AT_BERTH_BENGKALIS"] * 3 + ["DEPARTING_BENGKALIS"],
            "operational_phase": ["AT_ORIGIN_TERMINAL"] * 3 + ["DEPARTING"],
            "origin": ["BENGKALIS"] * 4,
            "destination": ["PAKNING"] * 4,
            "berth_episode_id": [1, 1, 1, pd.NA],
            "predicted_berth_release_time": pd.to_datetime([
                "2026-03-01 10:30", "2026-03-01 10:25",
                "2026-03-01 10:20", pd.NaT,
            ]),
            "elapsed_berth_min": [0.0, 5.0, 10.0, 0.0],
        })

    def _build(self, state: pd.DataFrame) -> pd.DataFrame:
        return build_prospective_decision_epochs(
            state,
            cutoff=pd.Timestamp("2026-02-28 23:59:59"),
            scan_interval_min=5,
            horizon_min=15,
            operating_start_min=420,
            operating_end_min=1435,
        )

    def test_epoch_is_invariant_to_future_observed_departure(self):
        early = self._build(self._state(20))
        late = self._build(self._state(40))
        self.assertEqual(len(early), 1)
        self.assertEqual(len(late), 1)
        self.assertEqual(early.loc[0, "decision_time"], pd.Timestamp("2026-03-01 10:10"))
        self.assertEqual(early.loc[0, "decision_time"], late.loc[0, "decision_time"])
        self.assertFalse(bool(early.loc[0, "observed_departure_used_to_generate_case"]))

    def test_only_first_eligible_scan_is_emitted_per_episode(self):
        state = self._state(40)
        state.loc[1:2, "predicted_berth_release_time"] = pd.Timestamp("2026-03-01 10:15")
        cases = self._build(state)
        self.assertEqual(len(cases), 1)
        self.assertEqual(cases.loc[0, "decision_time"], pd.Timestamp("2026-03-01 10:05"))
        self.assertEqual(cases.loc[0, "decision_epoch_mode"], "PROSPECTIVE_FIXED_GRID")

    def test_overdue_release_is_retained_as_prospective_alert(self):
        state = self._state(40)
        state.loc[0, "predicted_berth_release_time"] = pd.Timestamp("2026-03-01 09:55")
        cases = self._build(state)
        self.assertEqual(cases.loc[0, "decision_time"], pd.Timestamp("2026-03-01 10:00"))
        self.assertEqual(cases.loc[0, "decision_trigger_source"], "PREDICTED_RELEASE_OVERDUE")

    def test_observed_departure_is_attached_posthoc(self):
        cases = self._build(self._state(40))
        cases["predicted_eta"] = pd.Timestamp("2026-03-01 11:10")
        cases["predicted_departure_time"] = pd.Timestamp("2026-03-01 10:20")
        departures = pd.DataFrame({
            "mmsi": [1], "origin": ["BENGKALIS"],
            "baseline_departure_time": pd.to_datetime(["2026-03-01 10:40"]),
        })
        episodes = pd.DataFrame({
            "mmsi": [1], "port_id": ["PAKNING"],
            "berth_entry_time": pd.to_datetime(["2026-03-01 11:20"]),
        })
        validated, comparison = attach_posthoc_validation(
            cases, departures, episodes,
            horizon_min=15,
            departure_match_window_min=180,
            arrival_match_window_min=120,
        )
        self.assertEqual(validated.loc[0, "departure_match_status"], "MATCHED_POSTHOC")
        self.assertEqual(
            validated.loc[0, "retrospective_reference_decision_time"],
            pd.Timestamp("2026-03-01 10:25"),
        )
        self.assertFalse(bool(validated.loc[0, "retrospective_reference_used_for_prediction"]))
        self.assertEqual(len(comparison), 1)


if __name__ == "__main__":
    unittest.main()
