"""Reproducible evaluation harness comparing RuleBasedDetector vs ContrastiveDetector.

Usage:
    python3 -m backend.engine.threat_eval --json threat_eval.json
"""
from __future__ import annotations

import argparse
import json
import random
from typing import Any

from .anomaly import RuleBasedDetector
from .config import DEFAULT_SEED, TICK
from .contrastive import ContrastiveDetector
from .engine import Engine
from .scenarios import SCENARIOS


def warmup_and_seed_contrastive(
    seed: int = DEFAULT_SEED,
    warmup_ticks: int = 80,
) -> ContrastiveDetector:
    """Learn per-drone NOMINAL prototypes from clean operation and seed classic threats."""
    detector = ContrastiveDetector()
    eng = Engine(seed=seed, _warmup_contrastive=False)
    samples_by_drone: dict[str, list[tuple[float, float, float, float]]] = {
        d.id: [] for d in eng.drones
    }
    for _ in range(warmup_ticks):
        eng.tick(TICK)
        for d in eng.drones:
            if d.status == "ONLINE" and d.route_state == "OK":
                samples_by_drone[d.id].append(eng.anomaly_features(d))

    for dev_id, samples in samples_by_drone.items():
        if samples:
            detector.learn_nominal(dev_id, samples)

    # Seed canonical single-threat prototype 1: classic jamming
    jam_eng = Engine(seed=seed + 101, _warmup_contrastive=False)
    for _ in range(10):
        jam_eng.tick(TICK)
    jam_eng.set_jamming(True, power_db=38.0, ramp_dbps=0.0)
    jam_samples: list[dict[str, Any]] = []
    for _ in range(12):
        jam_eng.tick(TICK)
        for d in jam_eng.drones:
            if d.jam_spatial >= 0.8:
                jam_samples.append({"device": d.id, "evidence": jam_eng.anomaly_features(d)})
    detector.learn_threat("jamming", jam_samples)

    # Seed canonical single-threat prototype 2: classic spoofing
    spoof_eng = Engine(seed=seed + 202, _warmup_contrastive=False)
    for _ in range(10):
        spoof_eng.tick(TICK)
    spoof_eng.set_spoofing(True, drift_mps=7.0, initial_offset_m=30.0)
    spoof_samples: list[dict[str, Any]] = []
    for _ in range(12):
        spoof_eng.tick(TICK)
        for d in spoof_eng.drones:
            if d.spoof_spatial > 0.0:
                spoof_samples.append({"device": d.id, "evidence": spoof_eng.anomaly_features(d)})
    detector.learn_threat("spoofing", spoof_samples)

    return detector


def _evaluate_scenario(
    scenario_name: str,
    contrastive: ContrastiveDetector,
    seed: int = DEFAULT_SEED,
) -> dict[str, Any]:
    spec = SCENARIOS[scenario_name]
    eng = Engine(seed=seed, _warmup_contrastive=False)
    rule = RuleBasedDetector()
    eval_rng = random.Random(seed + 999)

    steps = int(round(spec.duration_s / TICK))
    rule_first_t: float | None = None
    rule_first_label: str | None = None
    contrastive_first_t: float | None = None
    contrastive_first_label: str | None = None
    contrastive_attributed: bool = False
    contrastive_best_sim: float = 0.0
    rule_false_flags = 0
    contrastive_false_flags = 0
    unexplained_samples: list[dict[str, Any]] = []

    for _ in range(steps):
        next_t = round(eng.t + TICK, 6)
        spec.step_hook(eng, next_t)
        eng.tick(TICK)

        for d in eng.drones:
            if d.status != "ONLINE" or d.route_state != "OK":
                continue
            feats = eng.anomaly_features_noisy(
                d,
                rng=eval_rng,
                sigma_rssi=0.45,
                sigma_snr=0.35,
                sigma_loss=0.001,
                sigma_gnss=0.20,
            )
            rv = rule.detect(d.id, feats)
            cv = contrastive.detect(d.id, feats)

            if spec.name == "nominal" or eng.t < spec.onset_s:
                if rv.label != "NOMINAL":
                    rule_false_flags += 1
                if cv.label != "NOMINAL":
                    contrastive_false_flags += 1
            else:
                if rv.label != "NOMINAL" and rule_first_t is None:
                    rule_first_t = eng.t
                    rule_first_label = rv.label
                if cv.label != "NOMINAL" and contrastive_first_t is None:
                    contrastive_first_t = eng.t
                    contrastive_first_label = cv.label
                    contrastive_attributed = cv.attributed
                    contrastive_best_sim = round(cv.similarity, 4)
                if cv.label == "UNEXPLAINED" and len(unexplained_samples) < 24:
                    unexplained_samples.append({
                        "device": d.id,
                        "evidence": list(feats),
                        "dims": cv.dims,
                    })

    rule_delay = (
        round(max(0.0, rule_first_t - spec.onset_s), 2)
        if rule_first_t is not None
        else None
    )
    contrastive_delay = (
        round(max(0.0, contrastive_first_t - spec.onset_s), 2)
        if contrastive_first_t is not None
        else None
    )

    return {
        "scenario": spec.name,
        "title": spec.title,
        "onset_s": spec.onset_s,
        "expected_label": spec.expected_label,
        "is_novel": spec.is_novel,
        "rule_based": {
            "detected": rule_first_t is not None,
            "delay_s": rule_delay,
            "label": rule_first_label or "NOMINAL",
            "correct_attribution": (rule_first_label == spec.expected_label)
            if spec.expected_label != "NOMINAL"
            else (rule_false_flags == 0),
            "false_flags": rule_false_flags,
        },
        "contrastive": {
            "detected": contrastive_first_t is not None,
            "delay_s": contrastive_delay,
            "label": contrastive_first_label or "NOMINAL",
            "attributed": contrastive_attributed,
            "similarity": contrastive_best_sim,
            "correct_attribution": (contrastive_first_label == spec.expected_label)
            if spec.expected_label != "NOMINAL"
            else (contrastive_false_flags == 0),
            "flagged_unexplained": contrastive_first_label == "UNEXPLAINED",
            "false_flags": contrastive_false_flags,
        },
        "_unexplained_samples": unexplained_samples,
    }


def run_evaluation(seed: int = DEFAULT_SEED) -> dict[str, Any]:
    """Run deterministic Pass 1 (classic profiles) and Pass 2 (operator-confirmed novel profiles)."""
    detector = warmup_and_seed_contrastive(seed=seed)

    eval_scenarios = [
        "nominal",
        "jamming",
        "ramp_jam",
        "spoofing",
        "slow_spoof",
        "coordinated",
        "carrier_blackout",
    ]

    pass_1: dict[str, Any] = {}
    learned_samples: dict[str, list[dict[str, Any]]] = {}
    for name in eval_scenarios:
        res = _evaluate_scenario(name, detector, seed=seed)
        samples = res.pop("_unexplained_samples", [])
        if SCENARIOS[name].is_novel and samples:
            learned_samples[SCENARIOS[name].expected_label] = samples
        pass_1[name] = res

    # Operator confirms novel UNEXPLAINED profiles once between Pass 1 and Pass 2
    confirmed_labels: list[str] = []
    for label, samples in learned_samples.items():
        detector.learn_threat(label, samples)
        confirmed_labels.append(label)

    pass_2: dict[str, Any] = {}
    for name in eval_scenarios:
        res = _evaluate_scenario(name, detector, seed=seed)
        res.pop("_unexplained_samples", None)
        pass_2[name] = res

    headline = {
        "seed": seed,
        "nominal_false_flags_rule_based": pass_1["nominal"]["rule_based"]["false_flags"],
        "nominal_false_flags_contrastive": pass_1["nominal"]["contrastive"]["false_flags"],
        "ramp_jam_delay_contrastive_s": pass_1["ramp_jam"]["contrastive"]["delay_s"],
        "ramp_jam_delay_rule_based_s": pass_1["ramp_jam"]["rule_based"]["delay_s"],
        "slow_spoof_delay_contrastive_s": pass_1["slow_spoof"]["contrastive"]["delay_s"],
        "slow_spoof_delay_rule_based_s": pass_1["slow_spoof"]["rule_based"]["delay_s"],
        "pass_1_novel_unexplained_count": sum(
            1 for k in ("coordinated", "carrier_blackout") if pass_1[k]["contrastive"]["flagged_unexplained"]
        ),
        "pass_2_novel_attributed_count": sum(
            1 for k in ("coordinated", "carrier_blackout") if pass_2[k]["contrastive"]["correct_attribution"]
        ),
        "operator_confirmed_prototypes": confirmed_labels,
    }

    return {
        "seed": seed,
        "tick_s": TICK,
        "headline": headline,
        "pass_1": pass_1,
        "pass_2": pass_2,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run deterministic anomaly detection evaluation.")
    parser.add_argument("--json", dest="json_path", help="Write full evaluation report to JSON file.")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="Deterministic RNG seed.")
    args = parser.parse_args(argv)

    report = run_evaluation(seed=args.seed)
    h = report["headline"]
    print(f"=== Dortmund Air Shield · Threat Evaluation (seed={args.seed}) ===")
    print(
        f"Nominal false flags:   contrastive={h['nominal_false_flags_contrastive']} | "
        f"rule_based={h['nominal_false_flags_rule_based']}"
    )
    print(
        f"Ramping jammer delay:  contrastive={h['ramp_jam_delay_contrastive_s']}s | "
        f"rule_based={h['ramp_jam_delay_rule_based_s']}s"
    )
    print(
        f"Slow spoofing delay:   contrastive={h['slow_spoof_delay_contrastive_s']}s | "
        f"rule_based={h['slow_spoof_delay_rule_based_s']}s"
    )
    print(
        f"Novel threats:         Pass 1 UNEXPLAINED={h['pass_1_novel_unexplained_count']}/2 -> "
        f"Pass 2 Attributed={h['pass_2_novel_attributed_count']}/2 "
        f"({', '.join(h['operator_confirmed_prototypes'])})"
    )

    if args.json_path:
        with open(args.json_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, sort_keys=False)
            f.write("\n")
        print(f"Wrote deterministic report to {args.json_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
