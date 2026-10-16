"""Unit tests for Phase 2 LLM Security Analyst (backend/engine/llm_analyst.py)."""
from __future__ import annotations

import asyncio
import json
import unittest

from backend.engine.config import DEFAULT_SEED, TICK
from backend.engine.engine import Engine
from backend.engine.llm_analyst import VALID_COMMANDS, LLMAnalyst, MockAnalyst, UniAnalyst
from backend.engine.server import AirShieldServer


class _FakeWebSocket:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send(self, raw: str) -> None:
        self.sent.append(json.loads(raw))


class TestLLMAnalystSuite(unittest.TestCase):
    def test_01_mock_analyst_deterministic_for_fixed_verdict(self) -> None:
        analyst = MockAnalyst()
        verdict = {
            "device": "DR-01",
            "label": "UNEXPLAINED",
            "similarity": 0.612,
            "dims": {"rssi": 3.4, "snr": 4.8, "loss": 2.1, "gnss_offset_m": 5.2},
            "evidence": [-84.0, 12.5, 0.14, 18.2],
            "attributed": False,
        }
        window = [(-83.5, 13.0, 0.12, 16.0), (-84.0, 12.5, 0.14, 18.2)]
        ctx = {"sim_time": 12.5, "protection": True}

        r1 = analyst.analyze(verdict, window, ctx)
        r2 = analyst.analyze(verdict, window, ctx)
        self.assertEqual(r1, r2)
        self.assertEqual(r1["hypothesis"], "unbekanntes Muster")
        self.assertGreaterEqual(r1["confidence"], 0.0)
        self.assertLessEqual(r1["confidence"], 1.0)
        self.assertIn("DR-01", r1["summary"])
        self.assertTrue(len(r1["recommended_actions"]) >= 1)
        for act in r1["recommended_actions"]:
            self.assertIn(act["command"], VALID_COMMANDS)
        self.assertIn(r1["issue"]["severity"], ("LOW", "MED", "CRIT"))
        self.assertTrue(bool(r1["issue"]["title"]))
        self.assertTrue(bool(r1["issue"]["assignee_role"]))

    def test_02_uni_analyst_unreachable_fallback_returns_mock_without_raising(self) -> None:
        # Point UniAnalyst to an unreachable local port with short timeout
        uni = UniAnalyst(base_url="http://127.0.0.1:59999/v1", timeout_s=0.3)
        mock = MockAnalyst()
        verdict = {
            "device": "DR-02",
            "label": "jamming",
            "similarity": 0.94,
            "dims": {"rssi": 4.2, "snr": 6.1, "loss": 3.0, "gnss_offset_m": 0.2},
            "evidence": [-88.0, 8.0, 0.22, 1.1],
            "attributed": True,
        }
        window = [(-88.0, 8.0, 0.22, 1.1)]
        ctx = {"sim_time": 15.0}

        with self.assertLogs("backend.engine.llm_analyst", level="WARNING"):
            res = uni.analyze(verdict, window, ctx)
        expected = mock.analyze(verdict, window, ctx)
        self.assertEqual(res, expected)
        self.assertEqual(res["backend"], "MOCK")

    def test_03_facade_selection_and_fallback(self) -> None:
        analyst_mock = LLMAnalyst(mode="mock")
        self.assertEqual(analyst_mock.active_backend_name, "MOCK")
        analyst_uni = LLMAnalyst(mode="uni")
        self.assertEqual(analyst_uni.active_backend_name, "UNI")

    def test_04_server_analyze_and_confirm_threat_roundtrip(self) -> None:
        srv = AirShieldServer(seed=DEFAULT_SEED)

        # Trigger coordinated attack on engine
        srv.engine.set_jamming(True, power_db=20.0, ramp_dbps=0.4)
        srv.engine.set_spoofing(True, drift_mps=3.5, initial_offset_m=11.5)
        srv.engine.tick(TICK)

        # Send ANALYZE command
        out1 = srv.handle_command(
            {"type": "command", "action": "ANALYZE", "value": {"device": "DR-01"}}
        )
        analysis_msgs = [m for m in out1 if m.get("type") == "ANALYSIS"]
        self.assertTrue(len(analysis_msgs) >= 1)
        a_data = analysis_msgs[-1]["data"]
        self.assertEqual(a_data["device"], "DR-01")
        self.assertEqual(a_data["hypothesis"], "unbekanntes Muster")

        # Send CONFIRM_THREAT command
        out2 = srv.handle_command(
            {
                "type": "command",
                "action": "CONFIRM_THREAT",
                "value": {"device": "DR-01", "label": "coordinated_rf_gnss"},
            }
        )
        types = [m.get("type") for m in out2]
        self.assertIn("THREAT_CONFIRMED", types)
        self.assertIn("CONTRASTIVE", types)
        self.assertIn("ANALYSIS", types)
        new_analysis = [m["data"] for m in out2 if m.get("type") == "ANALYSIS"][-1]
        self.assertEqual(new_analysis["hypothesis"], "coordinated_rf_gnss")


if __name__ == "__main__":
    unittest.main()
