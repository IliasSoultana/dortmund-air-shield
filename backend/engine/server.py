"""WebSocket + HTTP state server for Dortmund Air Shield (port 8765)."""
from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

try:
    import websockets
except ImportError:  # pragma: no cover - allows running unit tests without websockets installed
    websockets = None  # type: ignore[assignment]

from .config import DEFAULT_SEED, TICK
from .engine import Engine
from .llm_analyst import LLMAnalyst

HOST = "0.0.0.0"
PORT = 8765
ANALYSIS_DEBOUNCE_S = 5.0


class AirShieldServer:
    """Manages a deterministic Engine instance and streams 2 Hz telemetry over WebSocket."""

    def __init__(
        self,
        seed: int = DEFAULT_SEED,
        analyst: LLMAnalyst | None = None,
    ) -> None:
        self.engine = Engine(seed=seed)
        self.analyst = analyst or LLMAnalyst()
        self.clients: set[Any] = set()
        self._last_verdict_labels: dict[str, str] = {
            d.id: "NOMINAL" for d in self.engine.drones
        }
        self._last_analysis_t: float = -999.0
        self.last_analysis: dict[str, Any] | None = None

    def _select_verdict_for_analysis(self, device: str | None = None) -> dict[str, Any]:
        verdicts = self.engine.contrastive_verdicts
        if device and device in verdicts:
            return verdicts[device]
        # Prefer UNEXPLAINED first, then any non-nominal verdict with highest z_score
        unexplained = [v for v in verdicts.values() if v.get("label") == "UNEXPLAINED"]
        if unexplained:
            return max(unexplained, key=lambda v: float(v.get("z_score", 0.0)))
        non_nominal = [v for v in verdicts.values() if v.get("label") != "NOMINAL"]
        if non_nominal:
            return max(non_nominal, key=lambda v: float(v.get("z_score", 0.0)))
        if verdicts:
            return next(iter(verdicts.values()))
        return {
            "device": device or "DR-01",
            "label": "NOMINAL",
            "similarity": 1.0,
            "z_score": 0.0,
            "dims": {"rssi": 0.0, "snr": 0.0, "loss": 0.0, "gnss_offset_m": 0.0},
            "evidence": [-65.0, 34.0, 0.005, 1.1],
            "attributed": True,
        }

    def run_analysis(self, device: str | None = None) -> dict[str, Any]:
        verdict = self._select_verdict_for_analysis(device)
        dev_id = str(verdict.get("device") or "DR-01")
        ev_win = list(self.engine.evidence_windows.get(dev_id, []))
        ctx = {
            "t": self.engine.t,
            "protection": self.engine.protection,
            "rth": self.engine.rth,
            "policy": self.engine.policy.posture,
            "known_prototypes": list(self.engine.contrastive.threat_prototypes.keys()),
        }
        res = self.analyst.analyze(verdict, ev_win, ctx)
        self.last_analysis = res
        self._last_analysis_t = self.engine.t
        return res

    def handle_command(self, msg: dict[str, Any]) -> list[dict[str, Any]]:
        """Process a command message from the frontend or test harness and return outbound packets."""
        raw_type = str(msg.get("type") or "").upper()
        action = str(
            msg.get("action")
            or msg.get("command")
            or (raw_type if raw_type not in ("COMMAND", "ACTION") else "")
        ).upper()
        val = msg.get("value", msg.get("active", True))
        outbound: list[dict[str, Any]] = []

        if action in ("SET_JAMMING", "JAM_ON", "JAM_OFF", "JAMMING"):
            on = False if action == "JAM_OFF" else bool(val if not isinstance(val, dict) else val.get("active", True))
            power_db = float(
                msg.get("power_db", val.get("power_db", 38.0) if isinstance(val, dict) else 38.0)
            )
            ramp_dbps = float(
                msg.get("ramp_dbps", val.get("ramp_dbps", 0.0) if isinstance(val, dict) else 0.0)
            )
            self.engine.set_jamming(on, power_db=power_db, ramp_dbps=ramp_dbps)
        elif action in ("SET_RAMP_JAM", "RAMP_JAM"):
            on = bool(val if not isinstance(val, dict) else val.get("active", True))
            self.engine.set_jamming(on, power_db=8.5, ramp_dbps=1.55)
        elif action in ("SET_SPOOFING", "SPOOF_ON", "SPOOF_OFF", "SPOOFING"):
            on = False if action == "SPOOF_OFF" else bool(val if not isinstance(val, dict) else val.get("active", True))
            drift = float(msg.get("drift_mps", 7.0))
            init_off = float(msg.get("initial_offset_m", 15.0 if on else 0.0))
            self.engine.set_spoofing(on, drift_mps=drift, initial_offset_m=init_off)
        elif action in ("SET_COORDINATED", "COORDINATED"):
            on = bool(val if not isinstance(val, dict) else val.get("active", True))
            if on:
                self.engine.set_jamming(True, power_db=20.0, ramp_dbps=0.4)
                self.engine.set_spoofing(True, drift_mps=3.5, initial_offset_m=11.5)
            else:
                self.engine.set_jamming(False)
                self.engine.set_spoofing(False)
        elif action in ("SET_CARRIER_BLACKOUT", "CARRIER_BLACKOUT"):
            on = bool(val if not isinstance(val, dict) else val.get("active", True))
            self.engine.set_carrier_blackout(on)
        elif action in ("FORCE_NODE_FAILURE", "NODE_FAILURE"):
            targets = val if isinstance(val, (list, int)) else 2
            self.engine.fail_nodes(targets)
        elif action in ("SAFE_RETURN_HOME", "RTH"):
            self.engine.set_rth(bool(val))
        elif action in ("SET_PROTECTION", "PROTECTION"):
            self.engine.set_protection(bool(val))
        elif action == "MOVE_ZONE":
            z_arg = val if isinstance(val, dict) else msg
            if "lat" in z_arg and "lon" in z_arg:
                self.engine.move_zone(
                    float(z_arg.get("lat", self.engine.zone["lat"])),
                    float(z_arg.get("lon", self.engine.zone["lon"])),
                    float(z_arg["radius_m"]) if "radius_m" in z_arg else None,
                )
        elif action == "CONFIRM_THREAT":
            payload = val if isinstance(val, dict) else msg
            label = str(payload.get("label") or msg.get("label") or "coordinated_rf_gnss").strip()
            device = payload.get("device") or msg.get("device")
            samples = payload.get("samples") or msg.get("samples")
            confirm_res = self.engine.confirm_threat(
                label=label,
                device=str(device) if device else None,
                samples=samples if isinstance(samples, list) else None,
            )
            outbound.append({"type": "THREAT_CONFIRMED", "data": confirm_res})
            while self.engine.contrastive_events:
                cv_ev = self.engine.contrastive_events.pop(0)
                outbound.append({"type": "CONTRASTIVE", "data": cv_ev})
            analysis = self.run_analysis(device=str(device) if device else None)
            outbound.append({"type": "ANALYSIS", "data": analysis})
        elif action == "ANALYZE":
            payload = val if isinstance(val, dict) else msg
            device = payload.get("device") or msg.get("device")
            analysis = self.run_analysis(device=str(device) if device else None)
            outbound.append({"type": "ANALYSIS", "data": analysis})
        elif action == "RESET":
            self.engine.reset(preserve_learned_threats=False)
            self._last_verdict_labels = {d.id: "NOMINAL" for d in self.engine.drones}
            outbound.append({"type": "event", "data": {"type": "RESET", "active": True}})

        while self.engine.events:
            ev = self.engine.events.pop(0)
            outbound.append({"type": "event", "data": ev})
        while self.engine.logs:
            lg = self.engine.logs.pop(0)
            outbound.append({"type": "log", "data": lg})

        return outbound

    def step_packets(self, include_auto_analysis: bool = True) -> list[dict[str, Any]]:
        """Advance engine by one tick and build WebSocket broadcast packets."""
        st = self.engine.tick(TICK)
        packets: list[dict[str, Any]] = [
            {"type": "drones", "data": st["drones"]},
            {"type": "metrics", "data": st["metrics"]},
            {"type": "links", "data": st["links"]},
            {"type": "contrastive_state", "data": st["contrastive"]},
        ]

        label_changed_device: str | None = None
        while self.engine.contrastive_events:
            cv_ev = self.engine.contrastive_events.pop(0)
            packets.append({"type": "CONTRASTIVE", "data": cv_ev})
            dev = str(cv_ev.get("device") or "")
            lbl = str(cv_ev.get("label") or "NOMINAL")
            prev = self._last_verdict_labels.get(dev, "NOMINAL")
            if lbl != prev:
                self._last_verdict_labels[dev] = lbl
                if lbl != "NOMINAL" and label_changed_device is None:
                    label_changed_device = dev
            elif lbl == "UNEXPLAINED" and label_changed_device is None:
                label_changed_device = dev

        if (
            include_auto_analysis
            and label_changed_device is not None
            and (self.engine.t - self._last_analysis_t) >= ANALYSIS_DEBOUNCE_S
        ):
            analysis = self.run_analysis(device=label_changed_device)
            packets.append({"type": "ANALYSIS", "data": analysis})

        while self.engine.events:
            packets.append({"type": "event", "data": self.engine.events.pop(0)})
        while self.engine.logs:
            packets.append({"type": "log", "data": self.engine.logs.pop(0)})
        return packets

    async def broadcast(self, packets: list[dict[str, Any]]) -> None:
        if not self.clients or not packets:
            return
        dead: list[Any] = []
        for ws in list(self.clients):
            try:
                for pkt in packets:
                    await ws.send(json.dumps(pkt))
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.clients.discard(ws)

    async def ws_handler(self, ws: Any) -> None:
        self.clients.add(ws)
        try:
            st = self.engine.state()
            await ws.send(json.dumps({"type": "drones", "data": st["drones"]}))
            await ws.send(json.dumps({"type": "metrics", "data": st["metrics"]}))
            await ws.send(json.dumps({"type": "links", "data": st["links"]}))
            await ws.send(json.dumps({"type": "contrastive_state", "data": st["contrastive"]}))
            init_analysis = await asyncio.to_thread(self.run_analysis, None)
            await ws.send(json.dumps({"type": "ANALYSIS", "data": init_analysis}))

            async for raw in ws:
                try:
                    msg = json.loads(raw)
                except Exception:
                    continue
                if not isinstance(msg, dict):
                    continue
                mtype = str(msg.get("type") or "").lower()
                if mtype == "hello":
                    await ws.send(
                        json.dumps({
                            "type": "log",
                            "data": {
                                "level": "OK",
                                "msg": f"Engine server connected · Contrastive + LLM Analyst ({self.analyst.active_backend_name})",
                            },
                        })
                    )
                elif mtype in ("command", "action", "confirm_threat", "analyze") or "action" in msg or "command" in msg:
                    pkts = await asyncio.to_thread(self.handle_command, msg)
                    await self.broadcast(pkts)
                elif mtype == "state_request":
                    await ws.send(json.dumps({"type": "state", "data": self.engine.state()}))
        except websockets.ConnectionClosed:
            pass
        finally:
            self.clients.discard(ws)

    async def run_forever(self, host: str = HOST, port: int = PORT) -> None:
        async with websockets.serve(self.ws_handler, host, port):
            print(
                f"Dortmund Air Shield engine server listening on ws://{host}:{port} "
                f"(LLM_ANALYST={self.analyst.active_backend_name})"
            )
            while True:
                pkts = await asyncio.to_thread(self.step_packets, True)
                await self.broadcast(pkts)
                await asyncio.sleep(TICK)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Dortmund Air Shield WebSocket server.")
    parser.add_argument("--host", default=HOST)
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args(argv)

    srv = AirShieldServer(seed=args.seed)
    try:
        asyncio.run(srv.run_forever(host=args.host, port=args.port))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
