import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from src.mfar_core import _calibration_cutoff, _earliest_berth_slot, run_stage6
from src.mfar_maps import audit_folium_html, build_validation_map, segment_trajectories
from src.mfar_visuals import _dynamic_explorer


ROOT = Path(__file__).resolve().parents[1]


class AuditedPipelineTests(unittest.TestCase):
    def test_calendar_holdout_uses_complete_final_month(self):
        values = pd.Series(pd.to_datetime(["2026-01-01 06:00", "2026-03-31 23:55"]))
        self.assertEqual(
            _calibration_cutoff(values),
            pd.Timestamp("2026-02-28 23:59:59.999999999"),
        )

    def test_berth_slot_respects_prior_causal_reservations(self):
        eta = pd.Timestamp("2026-03-01 10:00")
        start, end = _earliest_berth_slot(
            eta, 40, pd.Timestamp("2026-03-01 09:50"),
            [(pd.Timestamp("2026-03-01 09:55"), pd.Timestamp("2026-03-01 10:35"))],
        )
        self.assertEqual(start, pd.Timestamp("2026-03-01 10:35"))
        self.assertEqual(end, pd.Timestamp("2026-03-01 11:15"))

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

    def test_map_contains_selectable_ocean_and_bathymetry_layers(self):
        frame = pd.DataFrame({
            "mmsi": [1, 1],
            "timestamp": pd.to_datetime(["2026-03-01 10:00", "2026-03-01 10:05"]),
            "latitude": [1.40, 1.401],
            "longitude": [102.14, 102.141],
        })
        berths = pd.read_csv(ROOT / "config" / "terminal_berths.csv")
        with TemporaryDirectory() as tmp:
            path, _, audit = build_validation_map(
                frame, berths, Path(tmp) / "ocean-map.html", "timestamp"
            )
            html = path.read_text(encoding="utf-8")
        self.assertEqual(audit["status"], "PASS")
        self.assertTrue(audit["has_ocean_basemap"])
        self.assertTrue(audit["has_ocean_reference"])
        self.assertTrue(audit["has_gebco_2026"])
        self.assertTrue(audit["esri_native_zoom_16"])
        self.assertNotIn('"maxNativeZoom": 9', html)
        self.assertIn("Terminal dan titik muat", html)
        self.assertIn("bukan untuk navigasi", html.lower())

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

    def test_mamdani_outputs_cover_every_rule_consequence(self):
        memberships = pd.read_csv(ROOT / "config" / "membership_parameters.csv")
        rules = pd.read_csv(ROOT / "config" / "fuzzy_rules.csv")
        outputs = memberships[memberships["scope"].eq("output")]["membership_column"]
        expected = {f"mu_risk_{value.lower()}" for value in rules["consequence"].astype(str)}
        self.assertTrue(expected <= set(outputs))

    def test_stage6_produces_centroid_risk_and_phase_feasible_action(self):
        rules = pd.read_csv(ROOT / "config" / "fuzzy_rules.csv")
        antecedents = {
            str(value)
            for column in ["antecedent_1", "antecedent_2", "antecedent_3", "antecedent_4"]
            for value in rules[column].dropna()
            if str(value).strip()
        }
        case = {name: 0.0 for name in antecedents}
        case.update({
            "mu_origin_queue_critical": 1.0, "mu_service_gap_long": 1.0,
            "mu_capacity_shortfall_high": 1.0, "operational_phase": "AT_ORIGIN_TERMINAL",
            "simulation_time": pd.Timestamp("2026-03-01 10:00"), "decision_time": pd.Timestamp("2026-03-01 10:00"),
            "mmsi": 525002121, "origin": "BENGKALIS", "destination": "PAKNING",
        })
        with TemporaryDirectory() as tmp:
            out, _, _ = run_stage6(pd.DataFrame([case]), Path(tmp), ROOT / "config")
        self.assertEqual(out.loc[0, "defuzzification_method"], "CENTROID")
        self.assertGreater(out.loc[0, "mamdani_risk_score"], 70)
        self.assertEqual(out.loc[0, "selected_action"], "ADD_VESSEL")

    def test_dynamic_dashboard_has_conjunctive_selectors(self):
        frame = pd.DataFrame({"port": ["A", "B"], "vessel": [1, 2], "value": [3.0, 4.0]})
        html = _dynamic_explorer(
            frame, "qa-dashboard", [("port", "Pelabuhan"), ("vessel", "Kapal")],
            [("Baris", "", "count")],
            [{"type": "bar-count", "x": "port", "title": "QA"}], ["port", "vessel"],
        )
        self.assertIn("Semua filter diterapkan bersamaan", html)
        self.assertEqual(html.count("data-column"), 0)
        self.assertIn("select.dataset.column", html)

    def test_notebooks_do_not_embed_legacy_one_day_or_rules(self):
        text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted((ROOT / "notebooks").glob("0[3-7]_*.ipynb"))
        )
        for forbidden in ["SIM_DATE", "RULE_TEXT", "accepted_intervention_recommendations", "2026-01-01"]:
            self.assertNotIn(forbidden, text)

    def test_stage7_does_not_emit_legacy_validation_artifacts(self):
        source = (ROOT / "src" / "mfar_core.py").read_text(encoding="utf-8")
        writes = [line for line in source.splitlines() if ".to_csv(" in line or "write_text(" in line]
        rendered = "\n".join(writes)
        for forbidden in ["07_daily_validation_by_port", "07_overall_intervention_validation",
                          "07_intervention_validation_dashboard"]:
            self.assertNotIn(forbidden, rendered)


if __name__ == "__main__":
    unittest.main()
