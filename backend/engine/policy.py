"""Resilience policy engine consuming advisory detector verdicts."""
from __future__ import annotations

from typing import Any


class PolicyEngine:
    """Consumes advisory anomaly verdicts and determines mesh resilience posture.

    Detector contract: detectors are ADVISORY ONLY and never command maneuvers;
    PolicyEngine translates verdicts + protection toggle into band/QoS/nav posture.
    """

    def __init__(self) -> None:
        self.active_verdicts: dict[str, dict[str, Any]] = {}
        self.posture: str = "NOMINAL"

    def ingest_verdict(self, verdict: dict[str, Any]) -> None:
        dev = str(verdict.get("device") or "")
        if not dev:
            return
        label = str(verdict.get("label") or "NOMINAL")
        if label == "NOMINAL":
            self.active_verdicts.pop(dev, None)
        else:
            self.active_verdicts[dev] = verdict

    def evaluate(
        self,
        protection: bool,
        rth: bool,
        jamming_active: bool,
        spoofing_active: bool,
    ) -> dict[str, Any]:
        if not protection:
            self.posture = "UNPROTECTED · BEST EFFORT"
            return {
                "posture": self.posture,
                "allow_dect_fallback": False,
                "reject_spoofed_gnss": False,
                "shed_video": False,
                "c2_arq_retries": 0,
                "advisory_count": len(self.active_verdicts),
            }

        has_rf_threat = jamming_active or any(
            v.get("label") in ("jamming", "UNEXPLAINED", "coordinated_rf_gnss")
            for v in self.active_verdicts.values()
        )
        has_gnss_threat = spoofing_active or any(
            v.get("label") in ("spoofing", "UNEXPLAINED", "coordinated_rf_gnss")
            for v in self.active_verdicts.values()
        )

        if rth:
            self.posture = "EMERGENCY · C2 FIRST"
        elif has_rf_threat:
            self.posture = "ANTI-JAM · VIDEO SHED"
        elif has_gnss_threat:
            self.posture = "GNSS GUARD · INS LOCK"
        else:
            self.posture = "NOMINAL"

        return {
            "posture": self.posture,
            "allow_dect_fallback": True,
            "reject_spoofed_gnss": True,
            "shed_video": bool(rth or has_rf_threat),
            "c2_arq_retries": 3,
            "advisory_count": len(self.active_verdicts),
        }
