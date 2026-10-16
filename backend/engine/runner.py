"""Headless deterministic scenario runner for Dortmund Air Shield."""
from __future__ import annotations

import argparse
import json
from typing import Any

from .config import DEFAULT_SEED, TICK
from .engine import Engine
from .scenarios import SCENARIOS


def run_scenario(
    name: str = "nominal",
    seed: int = DEFAULT_SEED,
    duration_s: float | None = None,
) -> dict[str, Any]:
    if name not in SCENARIOS:
        raise ValueError(f"Unknown scenario '{name}'. Valid: {sorted(SCENARIOS)}")
    spec = SCENARIOS[name]
    eng = Engine(seed=seed)
    total_s = duration_s if duration_s is not None else spec.duration_s
    steps = int(round(total_s / TICK))

    history: list[dict[str, Any]] = []
    for _ in range(steps):
        next_t = round(eng.t + TICK, 6)
        spec.step_hook(eng, next_t)
        state = eng.tick(TICK)
        history.append({
            "t": state["t"],
            "metrics": state["metrics"],
            "policy": state["policy"]["posture"],
        })

    return {
        "scenario": spec.name,
        "title": spec.title,
        "seed": seed,
        "steps": steps,
        "final_state": eng.state(),
        "timeline": history,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a deterministic Dortmund Air Shield scenario.")
    parser.add_argument("--scenario", default="nominal", choices=sorted(SCENARIOS.keys()))
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--json", dest="json_path")
    args = parser.parse_args(argv)

    res = run_scenario(args.scenario, seed=args.seed)
    print(
        f"[{res['scenario']}] steps={res['steps']} "
        f"metrics={json.dumps(res['final_state']['metrics'])}"
    )
    if args.json_path:
        with open(args.json_path, "w", encoding="utf-8") as f:
            json.dump(res, f, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
