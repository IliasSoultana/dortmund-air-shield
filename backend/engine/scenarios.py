"""Deterministic attack and resilience scenarios for Dortmund Air Shield."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class ScenarioSpec:
    name: str
    title: str
    duration_s: float
    onset_s: float
    expected_label: str
    is_novel: bool
    description: str
    step_hook: Callable[[Any, float], None]


def _noop(eng: Any, t: float) -> None:
    pass


def _jamming_hook(eng: Any, t: float) -> None:
    if abs(t - 10.0) < 1e-6:
        eng.set_jamming(True, power_db=38.0, ramp_dbps=0.0)
    elif abs(t - 45.0) < 1e-6:
        eng.set_jamming(False)


def _ramp_jam_hook(eng: Any, t: float) -> None:
    if abs(t - 10.0) < 1e-6:
        eng.set_jamming(True, power_db=8.5, ramp_dbps=1.55)
    elif abs(t - 50.0) < 1e-6:
        eng.set_jamming(False)


def _spoofing_hook(eng: Any, t: float) -> None:
    if abs(t - 10.0) < 1e-6:
        eng.set_spoofing(True, drift_mps=7.0, initial_offset_m=30.0)
    elif abs(t - 45.0) < 1e-6:
        eng.set_spoofing(False)


def _slow_spoof_hook(eng: Any, t: float) -> None:
    if abs(t - 10.0) < 1e-6:
        eng.set_spoofing(True, drift_mps=2.2, initial_offset_m=6.5)
    elif abs(t - 50.0) < 1e-6:
        eng.set_spoofing(False)


def _node_failure_hook(eng: Any, t: float) -> None:
    if abs(t - 10.0) < 1e-6:
        eng.fail_nodes(["DR-02", "DR-05"])


def _coordinated_hook(eng: Any, t: float) -> None:
    if abs(t - 10.0) < 1e-6:
        eng.set_jamming(True, power_db=20.0, ramp_dbps=0.4)
        eng.set_spoofing(True, drift_mps=3.5, initial_offset_m=11.5)
    elif abs(t - 45.0) < 1e-6:
        eng.set_jamming(False)
        eng.set_spoofing(False)


def _carrier_blackout_hook(eng: Any, t: float) -> None:
    if abs(t - 10.0) < 1e-6:
        eng.set_carrier_blackout(True)
    elif abs(t - 45.0) < 1e-6:
        eng.set_carrier_blackout(False)


def _full_demo_hook(eng: Any, t: float) -> None:
    if abs(t - 5.0) < 1e-6:
        eng.set_jamming(True, power_db=38.0, ramp_dbps=0.0)
    elif abs(t - 16.0) < 1e-6:
        eng.set_spoofing(True, drift_mps=7.0, initial_offset_m=15.0)
    elif abs(t - 28.0) < 1e-6:
        eng.fail_nodes(["DR-04", "DR-06"])
    elif abs(t - 42.0) < 1e-6:
        eng.set_rth(True)
    elif abs(t - 62.0) < 1e-6:
        eng.set_rth(False)
        eng.set_jamming(False)
        eng.set_spoofing(False)


SCENARIOS: dict[str, ScenarioSpec] = {
    "nominal": ScenarioSpec(
        name="nominal",
        title="Nominal Hybrid Mesh Operation",
        duration_s=60.0,
        onset_s=0.0,
        expected_label="NOMINAL",
        is_novel=False,
        description="Clean 10-drone orbit over Dortmund 3D city with FSOC LoS and DECT building fallback.",
        step_hook=_noop,
    ),
    "jamming": ScenarioSpec(
        name="jamming",
        title="Sudden Broadband RF/Optical Jamming",
        duration_s=50.0,
        onset_s=10.0,
        expected_label="jamming",
        is_novel=False,
        description="Step 38 dB jammer in Sector West (U-Tower) at t=10s.",
        step_hook=_jamming_hook,
    ),
    "ramp_jam": ScenarioSpec(
        name="ramp_jam",
        title="Slow-Ramping Smart Jammer",
        duration_s=55.0,
        onset_s=10.0,
        expected_label="jamming",
        is_novel=False,
        description="Ramping jammer starting at 8.5 dB and climbing at 1.55 dB/s to evade rolling baselines.",
        step_hook=_ramp_jam_hook,
    ),
    "spoofing": ScenarioSpec(
        name="spoofing",
        title="Counterfeit L1 GNSS Spoofing",
        duration_s=50.0,
        onset_s=10.0,
        expected_label="spoofing",
        is_novel=False,
        description="Sudden GNSS L1 spoofing pulling position fix at 7 m/s.",
        step_hook=_spoofing_hook,
    ),
    "slow_spoof": ScenarioSpec(
        name="slow_spoof",
        title="Stealth Slow-Drift GNSS Spoofing",
        duration_s=55.0,
        onset_s=10.0,
        expected_label="spoofing",
        is_novel=False,
        description="Gradual GNSS meaconing drift at 2.2 m/s starting below fixed plausibility thresholds.",
        step_hook=_slow_spoof_hook,
    ),
    "node_failure": ScenarioSpec(
        name="node_failure",
        title="Dual Relay Node Hardware Failure",
        duration_s=45.0,
        onset_s=10.0,
        expected_label="NOMINAL",
        is_novel=False,
        description="Two relay drones suffer watchdog/power-bus drop at t=10s and reboot after 20s.",
        step_hook=_node_failure_hook,
    ),
    "coordinated": ScenarioSpec(
        name="coordinated",
        title="Coordinated Hybrid RF + GNSS Attack",
        duration_s=50.0,
        onset_s=10.0,
        expected_label="coordinated_rf_gnss",
        is_novel=True,
        description="Simultaneous moderate RF jamming + GNSS drift creating a hybrid 4D signature.",
        step_hook=_coordinated_hook,
    ),
    "carrier_blackout": ScenarioSpec(
        name="carrier_blackout",
        title="Sector Carrier & Optical Blackout",
        duration_s=50.0,
        onset_s=10.0,
        expected_label="carrier_blackout",
        is_novel=True,
        description="Sudden severe packet-loss surge with moderate SNR pinch across primary uplinks.",
        step_hook=_carrier_blackout_hook,
    ),
    "full_demo": ScenarioSpec(
        name="full_demo",
        title="70s Hackathon Multi-Phase Resilience Demo",
        duration_s=70.0,
        onset_s=5.0,
        expected_label="jamming",
        is_novel=False,
        description="Full 70s scripted mission: nominal -> jamming -> spoofing -> node failure -> RTH -> recovery.",
        step_hook=_full_demo_hook,
    ),
}
