"""Frame authentication, OSNMA GNSS validation, and INS plausibility checks."""
from __future__ import annotations

import hashlib
import hmac
from typing import Any

from .config import CFG


class SecurityMonitor:
    """Deterministic security verifier for C2 frames and GNSS navigation fixes."""

    def __init__(self, secret: bytes = b"dortmund-air-shield-2026-key") -> None:
        self._secret = secret
        self.last_seq: dict[str, int] = {}

    def sign_frame(self, device_id: str, seq: int, payload: str) -> str:
        msg = f"{device_id}:{seq}:{payload}".encode("utf-8")
        return hmac.new(self._secret, msg, hashlib.sha256).hexdigest()[:16]

    def verify_frame(self, device_id: str, seq: int, payload: str, tag: str) -> bool:
        prev = self.last_seq.get(device_id, -1)
        if seq <= prev:
            return False
        expected = self.sign_frame(device_id, seq, payload)
        if not hmac.compare_digest(expected, tag):
            return False
        self.last_seq[device_id] = seq
        return True

    @staticmethod
    def check_gnss_plausibility(
        gnss_offset_m: float,
        protection_on: bool = True,
        threshold_m: float | None = None,
    ) -> dict[str, Any]:
        limit = threshold_m if threshold_m is not None else float(CFG["GNSS_PLAUSIBILITY_M"])
        disagrees = gnss_offset_m > limit
        rejected = bool(protection_on and disagrees)
        return {
            "offset_m": round(gnss_offset_m, 2),
            "threshold_m": limit,
            "disagrees_with_ins": disagrees,
            "gnss_rejected": rejected,
            "nav_source": "INS_DEAD_RECKONING" if rejected else "GNSS_L1",
        }
