"""Contrastive prototype anomaly detector with operator-in-the-loop threat learning."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Iterable

DIMS: tuple[str, str, str, str] = ("rssi", "snr", "loss", "gnss_offset_m")
MIN_STD: tuple[float, float, float, float] = (1.5, 1.1, 0.025, 0.85)


@dataclass
class NominalPrototype:
    device: str
    mean: tuple[float, float, float, float]
    std: tuple[float, float, float, float]
    count: int


@dataclass
class ContrastiveVerdict:
    device: str
    label: str  # "NOMINAL" | <known_label> | "UNEXPLAINED"
    similarity: float
    z_score: float
    dims: dict[str, float]
    evidence: tuple[float, float, float, float]
    attributed: bool
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "detector": "contrastive",
            "device": self.device,
            "label": self.label,
            "similarity": round(self.similarity, 4),
            "z_score": round(self.z_score, 3),
            "dims": {k: round(v, 3) for k, v in self.dims.items()},
            "evidence": [round(x, 4) for x in self.evidence],
            "attributed": self.attributed,
            "message": self.message,
        }


class ContrastiveDetector:
    """Interpretable contrastive prototype detector.

    1. Learns per-drone NOMINAL prototypes (mean, std) over benign 4-dim
       telemetry: (rssi, snr, loss, gnss_offset_m).
    2. Computes axis-aligned Mahalanobis z-score deviations per dimension.
    3. Attributes anomalies by cosine similarity against unit threat prototypes.
       If an anomaly exceeds z_threshold but no known threat prototype matches
       above similarity_threshold, emits:
         label="UNEXPLAINED", attributed=False,
         message="UNEXPLAINED — new profile, needs operator label"
    4. When the operator confirms once via learn_threat(label, samples), stores
       the new prototype so subsequent encounters are automatically attributed.
    """

    def __init__(
        self,
        z_threshold: float = 4.5,
        similarity_threshold: float = 0.84,
    ) -> None:
        self.z_threshold = z_threshold
        self.similarity_threshold = similarity_threshold
        self.nominal: dict[str, NominalPrototype] = {}
        self.global_nominal: NominalPrototype = NominalPrototype(
            device="GLOBAL",
            mean=(-65.0, 34.0, 0.006, 1.2),
            std=MIN_STD,
            count=1,
        )
        self.threat_prototypes: dict[str, tuple[float, float, float, float]] = {}

    def learn_nominal(
        self,
        device_id: str,
        samples: Iterable[SequenceLike],
    ) -> NominalPrototype:
        rows = [tuple(float(x) for x in s[:4]) for s in samples]
        if not rows:
            raise ValueError(f"learn_nominal({device_id}) requires at least 1 sample")
        n = len(rows)
        means = tuple(sum(r[i] for r in rows) / n for i in range(4))
        stds_list: list[float] = []
        for i in range(4):
            var = sum((r[i] - means[i]) ** 2 for r in rows) / max(1, n - 1)
            stds_list.append(max(MIN_STD[i], math.sqrt(var)))
        proto = NominalPrototype(
            device=device_id,
            mean=(means[0], means[1], means[2], means[3]),
            std=(stds_list[0], stds_list[1], stds_list[2], stds_list[3]),
            count=n,
        )
        self.nominal[device_id] = proto
        self._update_global_nominal()
        return proto

    def _update_global_nominal(self) -> None:
        if not self.nominal:
            return
        protos = list(self.nominal.values())
        k = len(protos)
        mean = tuple(sum(p.mean[i] for p in protos) / k for i in range(4))
        std = tuple(
            max(MIN_STD[i], sum(p.std[i] for p in protos) / k)
            for i in range(4)
        )
        self.global_nominal = NominalPrototype(
            device="GLOBAL",
            mean=(mean[0], mean[1], mean[2], mean[3]),
            std=(std[0], std[1], std[2], std[3]),
            count=sum(p.count for p in protos),
        )

    def z_vector(
        self,
        device_id: str,
        features: tuple[float, float, float, float],
    ) -> tuple[float, float, float, float]:
        """Compute directional anomaly z-scores relative to device's nominal prototype.

        Drops in RSSI/SNR and increases in loss/GNSS offset map to positive z-deviations.
        """
        proto = self.nominal.get(device_id, self.global_nominal)
        rssi, snr, loss, gnss = features
        z_rssi = max(0.0, (proto.mean[0] - rssi) / proto.std[0])
        z_snr = max(0.0, (proto.mean[1] - snr) / proto.std[1])
        z_loss = max(0.0, (loss - proto.mean[2]) / proto.std[2])
        z_gnss = max(0.0, (gnss - proto.mean[3]) / proto.std[3])
        return (z_rssi, z_snr, z_loss, z_gnss)

    @staticmethod
    def _normalize(vec: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
        norm = math.sqrt(sum(v * v for v in vec))
        if norm < 1e-9:
            return (0.0, 0.0, 0.0, 0.0)
        return (vec[0] / norm, vec[1] / norm, vec[2] / norm, vec[3] / norm)

    @staticmethod
    def _cosine(
        a: tuple[float, float, float, float],
        b: tuple[float, float, float, float],
    ) -> float:
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(x * x for x in b))
        if na < 1e-9 or nb < 1e-9:
            return 0.0
        return sum(x * y for x, y in zip(a, b)) / (na * nb)

    def learn_threat(
        self,
        label: str,
        samples: Iterable[Any],
        device_id: str | None = None,
    ) -> tuple[float, float, float, float]:
        """Learn or update a named threat prototype from single-threat evidence tuples.

        IMPORTANT: Pass clean single-threat evidence only (co-active evidence from
        unrelated simultaneous events can poison single-threat prototypes; use a
        dedicated label such as 'coordinated_rf_gnss' when confirming hybrid attacks).
        """
        z_rows: list[tuple[float, float, float, float]] = []
        for s in samples:
            if isinstance(s, dict):
                if "dims" in s and isinstance(s["dims"], dict):
                    d = s["dims"]
                    z_rows.append((
                        float(d.get("rssi", 0.0)),
                        float(d.get("snr", 0.0)),
                        float(d.get("loss", 0.0)),
                        float(d.get("gnss_offset_m", 0.0)),
                    ))
                    continue
                ev = s.get("evidence")
                dev = str(s.get("device") or device_id or "GLOBAL")
                if ev is not None:
                    feat = (float(ev[0]), float(ev[1]), float(ev[2]), float(ev[3]))
                    z_rows.append(self.z_vector(dev, feat))
                    continue
            seq = tuple(float(x) for x in s[:4])
            # Heuristic: raw telemetry has negative RSSI (e.g. -65 dBm), whereas z-vectors are >= 0
            if seq[0] < 0.0:
                z_rows.append(self.z_vector(device_id or "GLOBAL", (seq[0], seq[1], seq[2], seq[3])))
            else:
                z_rows.append((seq[0], seq[1], seq[2], seq[3]))

        if not z_rows:
            raise ValueError(f"learn_threat({label}) requires non-empty samples")

        mean_z = tuple(sum(r[i] for r in z_rows) / len(z_rows) for i in range(4))
        unit = self._normalize((mean_z[0], mean_z[1], mean_z[2], mean_z[3]))
        self.threat_prototypes[label] = unit
        return unit

    def detect(
        self,
        device_id: str,
        features: tuple[float, float, float, float],
    ) -> ContrastiveVerdict:
        z_vec = self.z_vector(device_id, features)
        z_norm = math.sqrt(sum(z * z for z in z_vec))
        dims_map = {DIMS[i]: z_vec[i] for i in range(4)}

        if z_norm < self.z_threshold:
            return ContrastiveVerdict(
                device=device_id,
                label="NOMINAL",
                similarity=1.0,
                z_score=z_norm,
                dims=dims_map,
                evidence=features,
                attributed=True,
                message="Nominal operation within learned prototype envelope",
            )

        best_label = "UNEXPLAINED"
        best_sim = 0.0
        for name, proto_vec in self.threat_prototypes.items():
            sim = self._cosine(z_vec, proto_vec)
            if sim > best_sim:
                best_sim = sim
                best_label = name

        if best_sim >= self.similarity_threshold and best_label != "UNEXPLAINED":
            return ContrastiveVerdict(
                device=device_id,
                label=best_label,
                similarity=best_sim,
                z_score=z_norm,
                dims=dims_map,
                evidence=features,
                attributed=True,
                message=f"Attributed to '{best_label}' (cos={best_sim:.2f}, z={z_norm:.1f})",
            )

        return ContrastiveVerdict(
            device=device_id,
            label="UNEXPLAINED",
            similarity=best_sim,
            z_score=z_norm,
            dims=dims_map,
            evidence=features,
            attributed=False,
            message="UNEXPLAINED — new profile, needs operator label",
        )


SequenceLike = tuple[float, ...] | list[float]
