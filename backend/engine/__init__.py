"""Deterministic simulation, mesh link-budget, and anomaly detection engine."""
from .config import CFG, FLEET_DEFS, OBSTACLES, TICK
from .engine import Engine

__all__ = ["CFG", "FLEET_DEFS", "OBSTACLES", "TICK", "Engine"]
