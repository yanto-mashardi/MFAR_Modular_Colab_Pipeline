import unittest

import pandas as pd

from src.mfar_state_episode import refine_operational_states, reconstruct_berth_episodes


class StateEpisodeReconstructionTests(unittest.TestCase):
    def _state(self, times, distances, sogs, nearest_ports=None, nearest_berths=None):
        n = len(times)
        nearest_ports = nearest_ports or ["BENGKALIS"] * n
        nearest_berths = nearest_berths or ["BENGKALIS_BERTH_1"] * n
        frame = pd.DataFrame({
            "grid_time": pd.to_datetime(times),
            "mmsi": [525002121] * n,
            "operational_status": ["SAILING"] * n,
            "origin": ["BENGKALIS"] * n,
            "destination": ["PAKNING"] * n,
            "nearest_port_id": nearest_ports,
            "nearest_berth_id": nearest_berths,
            "current_berth_id": [None] * n,
            "is_at_berth": [False] * n,
            "nearest_distance_nm": distances,
            "nearest_berth_radius_nm": [0.12] * n,
            "sog": sogs,
            "bracket_gap_min": [5.0] * n,
            "delta_bengkalis_distance_nm": [None] + [distances[i] - distances[i - 1] for i in range(1, n)],
            "delta_pakning_distance_nm": [None] * n,
        })
        return frame

    def _refine(self, frame):
        return refine_operational_states(
            frame,
            grid_interval_min=5,
            continuity_gap_factor=1.5,
            stopped_speed_kn=0.8,
            berth_exit_speed_kn=1.2,
            berth_exit_radius_multiplier=1.5,
            maneuver_speed_kn=3.0,
            approach_radius_nm=0.6,
            movement_eps_nm=0.005,
        )

    def _episodes(self, frame):
        return reconstruct_berth_episodes(
            frame,
            grid_interval_min=5,
            continuity_gap_factor=1.5,
            minimum_duration_min=10,
            maximum_service_duration_min=180,
            minimum_points=2,
            maximum_interpolation_gap_min=20,
            calibration_cutoff=pd.Timestamp("2026-02-28 23:59:59.999999999"),
            fallback_turnaround_min=40,
        )

    def test_berth_hysteresis_retains_one_borderline_point(self):
        raw = self._state(
            ["2026-01-01 10:00", "2026-01-01 10:05", "2026-01-01 10:10"],
            [0.10, 0.15, 0.20],
            [0.2, 0.9, 1.5],
        )
        refined = self._refine(raw)
        self.assertEqual(refined["is_at_berth"].tolist(), [True, True, False])
        self.assertEqual(refined.loc[1, "state_evidence"], "BERTH_HYSTERESIS")

    def test_sailing_direction_is_carried_from_departure(self):
        raw = self._state(
            ["2026-01-01 10:00", "2026-01-01 10:05", "2026-01-01 10:10"],
            [0.10, 0.20, 1.50],
            [0.2, 2.0, 7.0],
        )
        raw["delta_bengkalis_distance_nm"] = [None, 0.10, 1.30]
        raw["delta_pakning_distance_nm"] = [None, -0.05, -0.50]
        refined = self._refine(raw)
        self.assertEqual(refined.loc[1, "operational_status"], "DEPARTING_BENGKALIS")
        self.assertEqual(refined.loc[2, "operational_status"], "SAILING")
        self.assertEqual(refined.loc[2, "origin"], "BENGKALIS")
        self.assertEqual(refined.loc[2, "destination"], "PAKNING")
        self.assertEqual(refined.loc[2, "state_evidence"], "TRIP_DIRECTION_MEMORY")

    def test_episode_is_split_at_data_gap_even_when_both_rows_are_at_berth(self):
        raw = self._state(
            ["2026-01-01 10:00", "2026-01-01 10:05", "2026-01-02 10:00", "2026-01-02 10:05"],
            [0.10, 0.10, 0.10, 0.10],
            [0.1, 0.1, 0.1, 0.1],
        )
        refined = self._refine(raw)
        _, episodes = self._episodes(refined)
        self.assertEqual(len(episodes), 2)
        self.assertLessEqual(episodes["observed_berth_occupancy_min"].max(), 10)
        self.assertTrue(episodes["episode_class"].eq("DATA_GAP_CENSORED").any())

    def test_complete_service_call_is_eligible(self):
        raw = self._state(
            [
                "2026-01-01 09:55", "2026-01-01 10:00", "2026-01-01 10:05",
                "2026-01-01 10:10", "2026-01-01 10:15",
            ],
            [0.20, 0.10, 0.10, 0.10, 0.20],
            [2.0, 0.2, 0.2, 0.2, 2.0],
        )
        refined = self._refine(raw)
        _, episodes = self._episodes(refined)
        complete = episodes[episodes["episode_class"].eq("COMPLETE_SERVICE_CALL")]
        self.assertEqual(len(complete), 1)
        self.assertTrue(bool(complete.iloc[0]["eligible_for_turnaround_calibration"]))
        self.assertEqual(float(complete.iloc[0]["observed_berth_occupancy_min"]), 15.0)

    def test_extended_stay_is_excluded_from_calibration(self):
        times = pd.date_range("2026-01-01 09:55", periods=40, freq="5min")
        distances = [0.20] + [0.10] * 38 + [0.20]
        sogs = [2.0] + [0.2] * 38 + [2.0]
        raw = self._state(times, distances, sogs)
        refined = self._refine(raw)
        _, episodes = self._episodes(refined)
        extended = episodes[episodes["episode_class"].eq("EXTENDED_STAY")]
        self.assertEqual(len(extended), 1)
        self.assertFalse(bool(extended.iloc[0]["eligible_for_turnaround_calibration"]))
        self.assertGreater(float(extended.iloc[0]["observed_berth_occupancy_min"]), 180.0)

    def test_episode_cannot_span_multiple_berths(self):
        raw = self._state(
            ["2026-01-01 10:00", "2026-01-01 10:05", "2026-01-01 10:10", "2026-01-01 10:15"],
            [0.10, 0.10, 0.10, 0.10],
            [0.1, 0.1, 0.1, 0.1],
            nearest_berths=["BENGKALIS_BERTH_1", "BENGKALIS_BERTH_1", "BENGKALIS_BERTH_2", "BENGKALIS_BERTH_2"],
        )
        refined = self._refine(raw)
        _, episodes = self._episodes(refined)
        self.assertEqual(len(episodes), 2)
        self.assertTrue(episodes["distinct_berths"].eq(1).all())


if __name__ == "__main__":
    unittest.main()
