"""RF / optical link budget, jamming attenuation, and GNSS degradation models."""
from __future__ import annotations

import math
from typing import Any

from .config import CFG


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def jam_factor_at(
    x: float,
    y: float,
    zone_x: float,
    zone_y: float,
    radius_m: float,
    active: bool = True,
) -> float:
    """Spatial jamming profile: 1.0 inside radius_m, linear falloff to 0 at 1.35 * radius_m."""
    if not active:
        return 0.0
    d = math.hypot(x - zone_x, y - zone_y)
    if d <= radius_m:
        return 1.0
    if d >= radius_m * 1.35:
        return 0.0
    return 1.0 - (d - radius_m) / (0.35 * radius_m)


def spoof_factor_at(
    x: float,
    y: float,
    zone_x: float,
    zone_y: float,
    radius_m: float,
    active: bool = True,
) -> float:
    """Spatial GNSS spoofing reach aligned with the active threat sector."""
    if not active:
        return 0.0
    d = math.hypot(x - zone_x, y - zone_y)
    if d <= radius_m:
        return 1.0
    if d >= radius_m * 1.35:
        return 0.0
    return 1.0 - (d - radius_m) / (0.35 * radius_m)


def evaluate_link(
    band: str,
    dist_m: float,
    jam_level: float,
    jam_power_db: float = 38.0,
) -> dict[str, Any]:
    """Compute link quality, latency (ms), packet loss (0..1), and capacity (kbps)."""
    eff_jam = clamp(jam_level * (jam_power_db / 38.0), 0.0, 1.5)
    if band == "FSOC":
        rng = CFG["FSOC_RANGE_M"]
        q_dist = max(0.0, 1.0 - (dist_m / rng) ** 2.6)
        q = q_dist * max(0.0, 1.0 - eff_jam * 0.85)
        q = clamp(q, 0.05, 1.0)
        latency = 1.5 + 8.0 * ((1.0 - q) ** 1.5) + (3.0 if eff_jam > 0.05 else 0.0)
        loss = clamp(0.0005 + 0.02 * ((1.0 - q) ** 2) + eff_jam * 0.08, 0.0, 0.95)
        cap = CFG["FSOC_CAP_KBPS"] * q
    else:
        rng = CFG["DECT_RANGE_M"]
        q_dist = max(0.0, 1.0 - (dist_m / rng) ** 1.7)
        q = clamp(q_dist * max(0.15, 1.0 - 0.32 * eff_jam), 0.10, 1.0)
        latency = 18.0 + 38.0 * (1.0 - q) + 28.0 * eff_jam
        loss = clamp(0.006 + 0.045 * (1.0 - q) + 0.06 * eff_jam, 0.0, 0.95)
        cap = CFG["DECT_CAP_KBPS"] * q

    return {
        "band": band,
        "quality": q,
        "latency_ms": latency,
        "loss": loss,
        "cap_kbps": cap,
    }


def drone_radio_telemetry(
    dist_hq_m: float,
    band: str,
    jam_spatial: float,
    jam_power_db: float,
    carrier_blackout: bool = False,
) -> tuple[float, float, float]:
    """Compute (rssi_dbm, snr_db, packet_loss) for a drone given its distance and threat environment.

    In nominal operation:
      rssi_dbm ~ -64 .. -69 dBm
      snr_db   ~ 31 .. 36 dB
      loss     ~ 0.003 .. 0.009
    Under jamming (jam_spatial > 0 and jam_power_db > 0):
      effective jam dB = jam_spatial * jam_power_db
      rssi_dbm drops, snr_db drops sharply by effective jam dB, packet_loss rises.
    """
    d_km = max(0.15, dist_hq_m / 1000.0)
    base_rssi = -62.0 - 8.5 * math.log10(d_km * 2.5)
    if band == "DECT":
        base_rssi -= 1.2
    eff_jam_db = jam_spatial * max(0.0, jam_power_db)
    blackout_loss = 0.55 if carrier_blackout else 0.0
    blackout_db = 2.5 if carrier_blackout else 0.0

    rssi_dbm = base_rssi - 0.48 * eff_jam_db - 0.8 * blackout_db
    noise_dbm = CFG["NOISE_FLOOR_DBM"] + 0.85 * eff_jam_db + blackout_db
    snr_db = (base_rssi - CFG["NOISE_FLOOR_DBM"]) - 0.95 * eff_jam_db - blackout_db
    loss = clamp(
        0.004 + 0.003 * d_km + 0.011 * max(0.0, eff_jam_db) + blackout_loss,
        0.001,
        0.98,
    )
    _ = noise_dbm
    return rssi_dbm, snr_db, loss
