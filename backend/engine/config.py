"""Configuration constants and Dortmund 3D geometry for the simulation engine."""
from __future__ import annotations

TICK: float = 0.5  # seconds per simulation step (2 Hz)
DEFAULT_SEED: int = 20260416

CFG = {
    "VERSION": "2.0.0",
    "TICK": TICK,
    "ORIGIN": {"lat": 51.5136, "lon": 7.4653},
    "HQ": {
        "id": "HQ",
        "lat": 51.5136,
        "lon": 7.4653,
        "alt": 65.0,
        "name": "REINOLDIKIRCHE · CONTROL CENTER",
    },
    "ZONE": {
        "lat": 51.5132,
        "lon": 7.4545,
        "radius_m": 620.0,
        "sector": "SECTOR WEST · U-TOWER",
    },
    "FSOC_RANGE_M": 2800.0,
    "DECT_RANGE_M": 4500.0,
    "FSOC_CAP_KBPS": 1_000_000.0,
    "DECT_CAP_KBPS": 4_800.0,
    "DEMAND_KBPS": {"c2": 1.2, "telemetry": 3.0, "inter": 12.0, "video": 3500.0},
    "REBOOT_S": 20.0,
    "GNSS_PLAUSIBILITY_M": 60.0,
    "NOISE_FLOOR_DBM": -101.0,
    "TARGETS": {"reach": 95.0, "latency": 50.0, "loss": 2.0, "recovery": 3.0},
}

OBSTACLES = [
    {"id": "U-TOWER", "name": "Dortmunder U-Tower Block", "lat": 51.5149, "lon": 7.4534, "rx": 95.0, "ry": 80.0, "height": 155.0},
    {"id": "HBF-TOWER", "name": "Dortmund Hbf / DB Tower", "lat": 51.5176, "lon": 7.4592, "rx": 85.0, "ry": 65.0, "height": 138.0},
    {"id": "SPARKASSE", "name": "Sparkassen-Finanzzentrum", "lat": 51.5142, "lon": 7.4612, "rx": 68.0, "ry": 58.0, "height": 142.0},
    {"id": "ELLIPSE", "name": "Ellipson & Westentor Block", "lat": 51.5122, "lon": 7.4568, "rx": 72.0, "ry": 58.0, "height": 135.0},
    {"id": "RWE-TOWER", "name": "RWE / City-Quartier Tower", "lat": 51.5114, "lon": 7.4638, "rx": 72.0, "ry": 60.0, "height": 148.0},
    {"id": "STADTHAUS", "name": "Stadthaus & Friedensplatz", "lat": 51.5105, "lon": 7.4675, "rx": 75.0, "ry": 62.0, "height": 132.0},
    {"id": "WESTFALEN-T", "name": "Westfalentower Block", "lat": 51.5092, "lon": 7.4755, "rx": 75.0, "ry": 60.0, "height": 145.0},
    {"id": "TELEKOM-BLK", "name": "Ostwall High-Rise Block", "lat": 51.5152, "lon": 7.4728, "rx": 72.0, "ry": 62.0, "height": 136.0},
]

FLEET_DEFS = [
    {"id": "DR-01", "lat": 51.5150, "lon": 7.4545, "r": 420.0, "v": 26.0, "dir": 1, "phase": 0.2, "alt": 88.0, "battery": 94.0, "ecc": 0.72},
    {"id": "DR-02", "lat": 51.5168, "lon": 7.4605, "r": 390.0, "v": 24.0, "dir": -1, "phase": 1.4, "alt": 92.0, "battery": 88.0, "ecc": 0.80},
    {"id": "DR-03", "lat": 51.5138, "lon": 7.4518, "r": 460.0, "v": 27.0, "dir": 1, "phase": 2.5, "alt": 82.0, "battery": 79.0, "ecc": 0.75},
    {"id": "DR-04", "lat": 51.5162, "lon": 7.4710, "r": 430.0, "v": 25.0, "dir": -1, "phase": 0.8, "alt": 96.0, "battery": 91.0, "ecc": 0.82},
    {"id": "DR-05", "lat": 51.5112, "lon": 7.4582, "r": 410.0, "v": 25.0, "dir": 1, "phase": 3.4, "alt": 85.0, "battery": 84.0, "ecc": 0.78},
    {"id": "DR-06", "lat": 51.5102, "lon": 7.4695, "r": 450.0, "v": 26.0, "dir": -1, "phase": 4.1, "alt": 94.0, "battery": 73.0, "ecc": 0.80},
    {"id": "DR-07", "lat": 51.5142, "lon": 7.4555, "r": 520.0, "v": 29.0, "dir": 1, "phase": 2.0, "alt": 78.0, "battery": 82.0, "ecc": 0.68},
    {"id": "DR-08", "lat": 51.5128, "lon": 7.4750, "r": 440.0, "v": 25.0, "dir": 1, "phase": 5.1, "alt": 98.0, "battery": 96.0, "ecc": 0.76},
    {"id": "DR-09", "lat": 51.5088, "lon": 7.4628, "r": 430.0, "v": 24.0, "dir": -1, "phase": 1.8, "alt": 90.0, "battery": 75.0, "ecc": 0.82},
    {"id": "DR-10", "lat": 51.5118, "lon": 7.4505, "r": 470.0, "v": 27.0, "dir": -1, "phase": 1.0, "alt": 80.0, "battery": 68.0, "ecc": 0.74},
]
