"""WebSocket + HTTP state server for Dortmund Air Shield (port 8765)."""
from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

import websockets

from .config import DEFAULT_SEED, TICK
from .engine import Engine

HOST = "0.0.0.0"
PORT = 8765


class AirShieldServer:
    """Manages a deterministic Engine instance and streams 2 Hz telemetry over WebSocket."""

    def __init__(self, seed: int = DEFAULT_SEED) -> None:
        self.engine = Engine(seed=seed)
        self.clients: set[Any] = set()

    def handle_command(self, msg: dict[str, Any]) -> list[dict[str, Any]]:
        """Process a command message from the frontend or test harness and return outbound packets."""
        action = str(msg.get("action") or msg.get("command") or msg.get("type") or "").upper()
        val = msg.get("value", msg.get("active", True))
        outbound: list[dict[str, Any]] = []

        if action in ("SET_JAMMING", "JAM_ON", "JAM_OFF", "JAMMING"):
            on = False if action == "JAM_OFF" else bool(val)
            power_db = float(msg.get("power_db", 38.0))
            ramp_dbps = float(msg.get("ramp_dbps", 0.0))
            self.engine.set_jamming(on, power_db=power_db, ramp_dbps=ramp_dbps)
        elif action in ("SET_RAMP_JAM", "RAMP_JAM"):
            on = bool(val)
            self.engine.set_jamming(on, power_db=8.5, ramp_dbps=1.55)
        elif action in ("SET_SPOOFING", "SPOOF_ON", "SPOOF_OFF", "SPOOFING"):
            on = False if action == "SPOOF_OFF" else bool(val)
            drift = float(msg.get("drift_mps", 7.0))
            init_off = float(msg.get("initial_offset_m", 15.0 if on else 0.0))
            self.engine.set_spoofing(on, drift_mps=drift, initial_offset_m=init_off)
        elif action in ("SET_COORDINATED", "COORDINATED"):
            on = bool(val)
            if on:
                self.engine.set_jamming(True, power_db=18.0, ramp_dbps=0.5)
                self.engine.set_spoofing(True, drift_mps=5.5, initial_offset_m=16.0)
            else:
                self.engine.set_jamming(False)
                self.engine.set_spoofing(False)
        elif action in ("SET_CARRIER_BLACKOUT", "CARRIER_BLACKOUT"):
            self.engine.set_carrier_blackout(bool(val))
        elif action in ("FORCE_NODE_FAILURE", "NODE_FAILURE"):
            targets = val if isinstance(val, (list, int)) else 2
            self.engine.fail_nodes(targets)
        elif action in ("SAFE_RETURN_HOME", "RTH"):
            self.engine.set_rth(bool(val))
        elif action in ("SET_PROTECTION", "PROTECTION"):
            self.engine.set_protection(bool(val))
        elif action == "MOVE_ZONE":
            if isinstance(val, dict):
                self.engine.move_zone(
                    float(val.get("lat", self.engine.zone["lat"])),
                    float(val.get("lon", self.engine.zone["lon"])),
                    float(val["radius_m"]) if "radius_m" in val else None,
                )
        elif action == "RESET":
            self.engine.reset()
            outbound.append({"type": "event", "data": {"type": "RESET", "active": True}})

        while self.engine.events:
            ev = self.engine.events.pop(0)
            outbound.append({"type": "event", "data": ev})
        while self.engine.logs:
            lg = self.engine.logs.pop(0)
            outbound.append({"type": "log", "data": lg})

        return outbound

    def step_packets(self) -> list[dict[str, Any]]:
        """Advance engine by one tick and build WebSocket broadcast packets."""
        st = self.engine.tick(TICK)
        packets: list[dict[str, Any]] = [
            {"type": "drones", "data": st["drones"]},
            {"type": "metrics", "data": st["metrics"]},
            {"type": "links", "data": st["links"]},
        ]
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
                            "data": {"level": "OK", "msg": "Engine server connected (2 Hz deterministic mesh)"},
                        })
                    )
                elif mtype in ("command", "action") or "action" in msg:
                    pkts = self.handle_command(msg)
                    await self.broadcast(pkts)
                elif mtype == "state_request":
                    await ws.send(json.dumps({"type": "state", "data": self.engine.state()}))
        except websockets.ConnectionClosed:
            pass
        finally:
            self.clients.discard(ws)

    async def run_forever(self, host: str = HOST, port: int = PORT) -> None:
        async with websockets.serve(self.ws_handler, host, port):
            print(f"Dortmund Air Shield engine server listening on ws://{host}:{port}")
            while True:
                pkts = self.step_packets()
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
