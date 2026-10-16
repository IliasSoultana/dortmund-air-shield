"""Rule-based threshold anomaly detector with rolling baseline."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RuleVerdict:
    device: str
    label: str  # "NOMINAL" | "jamming" | "spoofing"
    score: float
    reason: str
    evidence: tuple[float, float, float, float]
    attributed: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "detector": "rule_based",
            "device": self.device,
            "label": self.label,
            "score": round(self.score, 3),
            "reason": self.reason,
            "evidence": [round(x, 4) for x in self.evidence],
            "attributed": self.attributed,
        }


@dataclass
class RuleBasedDetector:
    """Fixed threshold + rolling-baseline detector.

    Fast on sudden step attacks, but suffers from two structural limitations:
      1. Its rolling baseline absorbs slow-ramping attacks (like a ramping jammer)
         until the signal crosses a deep hard floor (~9.5 s delay).
      2. It only knows two fixed labels ("jamming" and "spoofing") and cannot
         flag novel/coordinated profiles as unexplained or learn new threat types.
    """

    window_size: int = 8
    snr_drop_thresh_db: float = 12.0
    snr_hard_floor_db: float = 10.8
    rssi_drop_thresh_db: float = 10.0
    rssi_hard_floor_dbm: float = -82.0
    loss_hard_ceil: float = 0.28
    gnss_offset_thresh_m: float = 28.0
    _history: dict[str, deque[tuple[float, float, float, float]]] = field(default_factory=dict)

    def reset(self) -> None:
        self._history.clear()

    def detect(
        self,
        device_id: str,
        features: tuple[float, float, float, float],
    ) -> RuleVerdict:
        rssi, snr, loss, gnss_offset_m = features
        hist = self._history.setdefault(device_id, deque(maxlen=self.window_size))

        if len(hist) >= 3:
            mean_rssi = sum(x[0] for x in hist) / len(hist)
            mean_snr = sum(x[1] for x in hist) / len(hist)
        else:
            mean_rssi = rssi
            mean_snr = snr

        snr_drop = mean_snr - snr
        rssi_drop = mean_rssi - rssi

        # Update rolling window (slow ramps get absorbed into the baseline!)
        hist.append(features)

        if (
            snr_drop >= self.snr_drop_thresh_db
            or rssi_drop >= self.rssi_drop_thresh_db
            or snr <= self.snr_hard_floor_db
            or rssi <= self.rssi_hard_floor_dbm
            or loss >= self.loss_hard_ceil
        ):
            score = max(snr_drop / self.snr_drop_thresh_db, (self.snr_hard_floor_db - snr + 12.0) / 12.0)
            return RuleVerdict(
                device=device_id,
                label="jamming",
                score=max(1.0, score),
                reason=f"SNR={snr:.1f}dB (Δ={-snr_drop:.1f}dB), RSSI={rssi:.1f}dBm, loss={loss:.2f}",
                evidence=features,
                attributed=True,
            )

        if gnss_offset_m >= self.gnss_offset_thresh_m:
            score = gnss_offset_m / self.gnss_offset_thresh_m
            return RuleVerdict(
                device=device_id,
                label="spoofing",
                score=max(1.0, score),
                reason=f"GNSS offset {gnss_offset_m:.1f}m >= {self.gnss_offset_thresh_m:.1f}m",
                evidence=features,
                attributed=True,
            )

        return RuleVerdict(
            device=device_id,
            label="NOMINAL",
            score=0.0,
            reason="within fixed thresholds",
            evidence=features,
            attributed=True,
        )
