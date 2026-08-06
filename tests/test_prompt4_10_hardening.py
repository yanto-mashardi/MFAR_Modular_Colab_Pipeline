import unittest
import numpy as np
import pandas as pd
from src.mfar_prompt4_7 import _quality, _berth_gate, QUALITY_SEMANTICS
from src.mfar_prompt5_6 import operational_alert_score
from src.mfar_prompt8_10 import simulate_queue

class Prompt4To10Tests(unittest.TestCase):
    def test_quality_index_is_bounded_and_has_nonprobability_semantics(self):
        frame=pd.DataFrame({"bracket_gap_min":[0,20],"trip_history_latest_time":[pd.Timestamp("2026-01-01"),pd.NaT],"turnaround_estimate_source":["CALIBRATION_VESSEL_PORT_MEDIAN","CONFIGURED_FALLBACK"],"assigned_destination_berth":["B1",None],"predicted_berth_available_time_at_eta":[pd.Timestamp("2026-03-01 10:00"),pd.NaT],"forecast_confidence":[.9,.1]})
        out=_quality(frame,{})
        self.assertTrue(out["forecast_quality_index"].between(0,1).all())
        self.assertTrue(out["forecast_confidence_semantics"].eq(QUALITY_SEMANTICS).all())
        self.assertFalse(np.allclose(out["forecast_quality_index"],out["legacy_forecast_confidence"]))

    def test_berth_gate_is_logically_consistent(self):
        frame=pd.DataFrame({"predicted_eta":pd.to_datetime(["2026-03-01 10:00","2026-03-01 10:00"]),"predicted_berth_available_time_at_eta":pd.to_datetime(["2026-03-01 10:00","2026-03-01 10:20"]),"assigned_destination_berth":["B1","B2"]})
        out,audit=_berth_gate(frame)
        self.assertEqual(out["predicted_wait_min"].tolist(),[0.,20.])
        self.assertEqual(out["berth_availability_at_eta"].tolist(),[1.,0.])
        self.assertEqual(int(audit["failed_rows"].sum()),0)

    def test_alert_score_is_monotonic_in_queue(self):
        values=[]
        for q in np.linspace(0,5,101):
            values.append(operational_alert_score(pd.Series({"origin_queue_ratio":q,"berth_availability_at_eta":1,"predicted_wait_min":0,"forecast_quality_index":.8,"service_gap_min":45,"capacity_shortfall_ratio":0})))
        self.assertTrue((np.diff(values)>=-1e-12).all())

    def test_queue_simulator_conserves_mass_and_never_goes_negative(self):
        times=pd.to_datetime(["2026-03-01 07:00","2026-03-01 07:05","2026-03-01 07:10"])
        grid=pd.DataFrame({"simulation_time":times,"port_id":["A"]*3,"queue_ce":[0]*3,"queue_ratio":[0]*3})
        rates=pd.DataFrame({"port_id":["A"],"time_start":["00:00"],"time_end":["24:00"],"car_arrival_rate_30min":[6.0],"motorcycle_arrival_rate_30min":[0.0]})
        baseline=pd.DataFrame({"simulation_time":[times[1]],"port_id":["A"],"mmsi":[1],"service_capacity_ce":[2.0],"action":["BASELINE"]})
        scenario=baseline.copy()
        out=simulate_queue(grid,rates,baseline,scenario,.25,30.)
        self.assertLessEqual(out["baseline_mass_balance_residual_ce"].abs().max(),1e-12)
        self.assertLessEqual(out["scenario_mass_balance_residual_ce"].abs().max(),1e-12)
        self.assertTrue(out[["queue_ce","queue_ce_after"]].ge(0).all().all())

if __name__ == "__main__":
    unittest.main()
