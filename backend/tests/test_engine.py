"""Unit tests for the Dortmund Air Shield backend engine."""
from __future__ import annotations

import unittest

from backend.engine.anomaly import RuleBasedDetector
from backend.engine.config import DEFAULT_SEED, FLEET_DEFS, TICK
from backend.engine.contrastive import ContrastiveDetector
from backend.engine.engine import Engine
from backend.engine.geo import check_los_3d, to_latlon, to_xy
from backend.engine.link_budget import evaluate_link, jam_factor_at
from backend.engine.policy import PolicyEngine
from backend.engine.runner import run_scenario
from backend.engine.scenarios import SCENARIOS
from backend.engine.security import SecurityMonitor
from backend.engine.threat_eval import run_evaluation, warmup_and_seed_contrastive


class TestEngineSuite(unittest.TestCase):
    def test_01_geo_roundtrip(self) -> None:
        lat, lon = 51.5149, 7.4534
        x, y = to_xy(lat, lon)
        lat2, lon2 = to_latlon(x, y)
        self.assertAlmostEqual(lat, lat2, places=6)
        self.assertAlmostEqual(lon, lon2, places=6)

    def test_02_los_3d_raycast_utower(self) -> None:
        ux, uy = to_xy(51.5149, 7.4534)
        hit = check_los_3d(ux - 200.0, uy, 80.0, ux + 200.0, uy, 80.0)
        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual(hit["obstacle"]["id"], "U-TOWER")
        clear = check_los_3d(ux - 200.0, uy, 190.0, ux + 200.0, uy, 190.0)
        self.assertIsNone(clear)

    def test_03_link_budget_and_spatial_jam(self) -> None:
        jf_inside = jam_factor_at(0.0, 0.0, 0.0, 0.0, 620.0, True)
        jf_far = jam_factor_at(1000.0, 0.0, 0.0, 0.0, 620.0, True)
        self.assertEqual(jf_inside, 1.0)
        self.assertEqual(jf_far, 0.0)
        fsoc = evaluate_link("FSOC", 800.0, 0.0)
        dect = evaluate_link("DECT", 800.0, 0.8)
        self.assertGreater(fsoc["cap_kbps"], dect["cap_kbps"])
        self.assertLess(fsoc["latency_ms"], dect["latency_ms"])

    def test_04_security_hmac_and_gnss_plausibility(self) -> None:
        sec = SecurityMonitor()
        tag = sec.sign_frame("DR-01", 1, "C2_HOLD")
        self.assertTrue(sec.verify_frame("DR-01", 1, "C2_HOLD", tag))
        # Replay with same seq must fail
        self.assertFalse(sec.verify_frame("DR-01", 1, "C2_HOLD", tag))
        plaus = sec.check_gnss_plausibility(75.0, protection_on=True)
        self.assertTrue(plaus["gnss_rejected"])

    def test_05_policy_advisory_consumption(self) -> None:
        pol = PolicyEngine()
        pol.ingest_verdict({"device": "DR-01", "label": "jamming"})
        res = pol.evaluate(protection=True, rth=False, jamming_active=False, spoofing_active=False)
        self.assertEqual(res["posture"], "ANTI-JAM · VIDEO SHED")
        self.assertTrue(res["shed_video"])

    def test_06_deterministic_seeded_runs_bit_identical(self) -> None:
        e1 = Engine(seed=DEFAULT_SEED)
        e2 = Engine(seed=DEFAULT_SEED)
        for _ in range(25):
            s1 = e1.tick(TICK)
            s2 = e2.tick(TICK)
            self.assertEqual(s1, s2)

    def test_07_fleet_size_and_nominal_reachability(self) -> None:
        eng = Engine(seed=DEFAULT_SEED)
        self.assertEqual(len(eng.drones), len(FLEET_DEFS))
        st = eng.tick(TICK)
        self.assertEqual(st["metrics"]["reachability"], 100.0)

    def test_08_ramping_jammer_power_climbs_in_tick(self) -> None:
        eng = Engine(seed=DEFAULT_SEED)
        eng.set_jamming(True, power_db=8.5, ramp_dbps=1.55)
        p0 = eng.jam["power_db"]
        eng.tick(TICK)
        self.assertGreater(eng.jam["power_db"], p0)

    def test_09_nine_scenarios_registered_and_runnable(self) -> None:
        self.assertEqual(len(SCENARIOS), 9)
        self.assertIn("ramp_jam", SCENARIOS)
        self.assertIn("slow_spoof", SCENARIOS)
        out = run_scenario("nominal", duration_s=5.0)
        self.assertEqual(out["steps"], 10)

    def test_10_rule_based_detector_absorbs_slow_ramp_initially(self) -> None:
        det = RuleBasedDetector()
        # Simulate slow SNR ramp-down of 0.8 dB per tick from 34 dB
        verdicts = []
        for i in range(10):
            snr = 34.0 - i * 0.8
            verdicts.append(det.detect("DR-01", (-65.0 - i * 0.3, snr, 0.01, 1.0)).label)
        self.assertTrue(all(v == "NOMINAL" for v in verdicts))

    def test_11_contrastive_detector_flags_ramp_onset(self) -> None:
        det = warmup_and_seed_contrastive(seed=DEFAULT_SEED)
        eng = Engine(seed=DEFAULT_SEED)
        eng.set_jamming(True, power_db=8.5, ramp_dbps=1.55)
        eng.tick(TICK)
        d1 = eng.drone_map["DR-01"]
        v = det.detect(d1.id, eng.anomaly_features(d1))
        self.assertEqual(v.label, "jamming")
        self.assertTrue(v.attributed)

    def test_12_contrastive_unexplained_then_learn_threat(self) -> None:
        det = warmup_and_seed_contrastive(seed=DEFAULT_SEED)
        eng = Engine(seed=DEFAULT_SEED)
        eng.set_jamming(True, power_db=20.0, ramp_dbps=0.4)
        eng.set_spoofing(True, drift_mps=3.5, initial_offset_m=11.5)
        eng.tick(TICK)
        d1 = eng.drone_map["DR-01"]
        feats = eng.anomaly_features(d1)
        v_before = det.detect(d1.id, feats)
        self.assertEqual(v_before.label, "UNEXPLAINED")
        self.assertFalse(v_before.attributed)

        det.learn_threat("coordinated_rf_gnss", [{"device": d1.id, "evidence": feats}])
        v_after = det.detect(d1.id, feats)
        self.assertEqual(v_after.label, "coordinated_rf_gnss")
        self.assertTrue(v_after.attributed)

    def test_13_threat_eval_headline_numbers(self) -> None:
        rep = run_evaluation(seed=DEFAULT_SEED)
        h = rep["headline"]
        self.assertEqual(h["nominal_false_flags_contrastive"], 0)
        self.assertEqual(h["nominal_false_flags_rule_based"], 0)
        self.assertEqual(h["ramp_jam_delay_contrastive_s"], 0.0)
        self.assertEqual(h["ramp_jam_delay_rule_based_s"], 9.5)
        self.assertEqual(h["pass_1_novel_unexplained_count"], 2)
        self.assertEqual(h["pass_2_novel_attributed_count"], 2)


if __name__ == "__main__":
    unittest.main()
