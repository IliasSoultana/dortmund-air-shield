"""Deterministic seeded drone-mesh simulation engine for Dortmund Air Shield."""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any

from .anomaly import RuleBasedDetector
from .config import CFG, DEFAULT_SEED, FLEET_DEFS, TICK
from .geo import OBSTACLE_BOXES, check_los_3d, dist3, to_latlon, to_xy
from .link_budget import (
    clamp,
    drone_radio_telemetry,
    evaluate_link,
    jam_factor_at,
    spoof_factor_at,
)
from .policy import PolicyEngine
from .security import SecurityMonitor


@dataclass
class DroneState:
    id: str
    index: int
    cx: float
    cy: float
    r: float
    w: float
    phase: float
    ecc: float
    dir: int
    base_alt: float
    battery: float
    x: float = 0.0
    y: float = 0.0
    alt: float = 85.0
    vx: float = 0.0
    vy: float = 0.0
    speed: float = 0.0
    heading: float = 0.0
    status: str = "ONLINE"  # ONLINE | OFFLINE
    mode: str = "MISSION"   # MISSION | RTH
    gnss: str = "OK"        # OK | LOST | SPOOFED
    band: str = "FSOC"      # FSOC | DECT | NONE
    nlos_reason: str | None = None
    jam_spatial: float = 0.0
    spoof_spatial: float = 0.0
    spoof_offset_x: float = 0.0
    spoof_offset_y: float = 0.0
    gnss_offset_m: float = 1.1
    rssi_dbm: float = -65.0
    snr_db: float = 34.0
    loss: float = 0.005
    latency_ms: float = 4.0
    delivery: float = 0.995
    hops: int = 1
    route: list[str] = field(default_factory=list)
    route_state: str = "OK"
    reboot_at_s: float = 0.0

    @property
    def lat(self) -> float:
        return to_latlon(self.x, self.y)[0]

    @property
    def lon(self) -> float:
        return to_latlon(self.x, self.y)[1]

    def orbit_target(self, t_s: float) -> tuple[float, float]:
        ang = self.phase + self.w * t_s
        return (
            self.cx + self.r * math.cos(ang),
            self.cy + self.r * self.ecc * math.sin(ang),
        )


class Engine:
    """Deterministic 2 Hz simulation engine for the 10-drone Dortmund mesh."""

    def __init__(self, seed: int = DEFAULT_SEED) -> None:
        self.seed = seed
        self.rng = random.Random(seed)
        self.t: float = 0.0
        self.tick_count: int = 0
        self.protection: bool = True
        self.rth: bool = False

        hq_x, hq_y = to_xy(CFG["HQ"]["lat"], CFG["HQ"]["lon"])
        self.hq = {
            "id": "HQ",
            "x": hq_x,
            "y": hq_y,
            "alt": float(CFG["HQ"]["alt"]),
            "lat": float(CFG["HQ"]["lat"]),
            "lon": float(CFG["HQ"]["lon"]),
        }

        zx, zy = to_xy(CFG["ZONE"]["lat"], CFG["ZONE"]["lon"])
        self.zone = {
            "x": zx,
            "y": zy,
            "lat": float(CFG["ZONE"]["lat"]),
            "lon": float(CFG["ZONE"]["lon"]),
            "radius_m": float(CFG["ZONE"]["radius_m"]),
            "sector": str(CFG["ZONE"]["sector"]),
        }

        self.jam = {
            "active": False,
            "power_db": 0.0,
            "ramp_dbps": 0.0,
            "max_power_db": 42.0,
        }
        self.spoof = {
            "active": False,
            "drift_mps": 7.0,
            "initial_offset_m": 0.0,
            "vec_x": -5.0,
            "vec_y": 4.8,
        }
        self.carrier_blackout: bool = False

        self.drones: list[DroneState] = []
        self.drone_map: dict[str, DroneState] = {}
        self.links: list[dict[str, Any]] = []
        self.recoveries: list[float] = []
        self.events: list[dict[str, Any]] = []
        self.logs: list[dict[str, str]] = []

        self.security = SecurityMonitor()
        self.policy = PolicyEngine()
        self.rule_detector = RuleBasedDetector()
        self.rule_verdicts: dict[str, dict[str, Any]] = {}

        self._init_fleet()
        self._update_mesh_and_telemetry(dt=0.0)

    def _init_fleet(self) -> None:
        self.drones.clear()
        self.drone_map.clear()
        for idx, d in enumerate(FLEET_DEFS):
            cx, cy = to_xy(d["lat"], d["lon"])
            w = d["dir"] * (d["v"] / d["r"])
            ds = DroneState(
                id=d["id"],
                index=idx,
                cx=cx,
                cy=cy,
                r=float(d["r"]),
                w=w,
                phase=float(d["phase"]),
                ecc=float(d["ecc"]),
                dir=int(d["dir"]),
                base_alt=float(d["alt"]),
                battery=float(d["battery"]),
            )
            tx, ty = ds.orbit_target(0.0)
            ds.x, ds.y = tx, ty
            ds.alt = ds.base_alt
            ds.route = [ds.id, "HQ"]
            self.drones.append(ds)
            self.drone_map[ds.id] = ds

    def reset(self, seed: int | None = None) -> None:
        if seed is not None:
            self.seed = seed
        self.rng = random.Random(self.seed)
        self.t = 0.0
        self.tick_count = 0
        self.rth = False
        self.jam = {"active": False, "power_db": 0.0, "ramp_dbps": 0.0, "max_power_db": 42.0}
        self.spoof = {"active": False, "drift_mps": 7.0, "initial_offset_m": 0.0, "vec_x": -5.0, "vec_y": 4.8}
        self.carrier_blackout = False
        self.recoveries.clear()
        self.events.clear()
        self.logs.clear()
        self.rule_detector.reset()
        self.rule_verdicts.clear()
        self.policy = PolicyEngine()
        self._init_fleet()
        self._update_mesh_and_telemetry(dt=0.0)

    def log(self, level: str, msg: str) -> None:
        self.logs.append({"level": level.upper(), "msg": msg, "t": f"{self.t:.1f}s"})
        if len(self.logs) > 200:
            self.logs.pop(0)

    def set_jamming(
        self,
        active: bool,
        power_db: float = 38.0,
        ramp_dbps: float = 0.0,
    ) -> None:
        self.jam["active"] = bool(active)
        if active:
            self.jam["power_db"] = float(power_db)
            self.jam["ramp_dbps"] = float(ramp_dbps)
            self.log("CRIT", f"RF JAMMING ACTIVE ({power_db:.1f} dB, ramp={ramp_dbps:.2f} dB/s)")
        else:
            self.jam["power_db"] = 0.0
            self.jam["ramp_dbps"] = 0.0
            self.log("OK", "Jamming cleared — spectrum nominal")
        self.events.append({
            "type": "JAMMING",
            "active": bool(active),
            "lat": self.zone["lat"],
            "lon": self.zone["lon"],
            "radius_m": self.zone["radius_m"],
        })

    def set_spoofing(
        self,
        active: bool,
        drift_mps: float = 7.0,
        initial_offset_m: float = 0.0,
    ) -> None:
        self.spoof["active"] = bool(active)
        if active:
            self.spoof["drift_mps"] = float(drift_mps)
            self.spoof["initial_offset_m"] = float(initial_offset_m)
            ang = 2.25
            self.spoof["vec_x"] = math.cos(ang) * drift_mps
            self.spoof["vec_y"] = math.sin(ang) * drift_mps
            for d in self.drones:
                sf = spoof_factor_at(
                    d.x, d.y, self.zone["x"], self.zone["y"], self.zone["radius_m"], True
                )
                if sf > 0 and initial_offset_m > 0:
                    d.spoof_offset_x = math.cos(ang) * initial_offset_m * sf
                    d.spoof_offset_y = math.sin(ang) * initial_offset_m * sf
            self.log("CRIT", f"GNSS SPOOFING ACTIVE (drift={drift_mps:.1f} m/s)")
        else:
            self.spoof["initial_offset_m"] = 0.0
            self.log("OK", "GNSS spoofing neutralised")
        self.events.append({
            "type": "SPOOFING",
            "active": bool(active),
            "lat": self.zone["lat"],
            "lon": self.zone["lon"],
            "radius_m": self.zone["radius_m"],
        })

    def set_carrier_blackout(self, active: bool) -> None:
        self.carrier_blackout = bool(active)
        if active:
            self.log("CRIT", "CARRIER BLACKOUT — severe uplink packet loss surge")
        else:
            self.log("OK", "Carrier blackout cleared")

    def set_protection(self, active: bool) -> None:
        self.protection = bool(active)
        self.events.append({"type": "PROTECTION", "active": self.protection})
        self.log("OK" if self.protection else "WARN", f"Protection set to {self.protection}")

    def set_rth(self, active: bool) -> None:
        self.rth = bool(active)
        for d in self.drones:
            if d.status == "ONLINE":
                d.mode = "RTH" if self.rth else "MISSION"
        self.events.append({"type": "RTH", "active": self.rth})
        self.log("CRIT" if self.rth else "OK", f"Safe Return Home {'ENGAGED' if self.rth else 'RELEASED'}")

    def move_zone(self, lat: float, lon: float, radius_m: float | None = None) -> None:
        zx, zy = to_xy(lat, lon)
        self.zone["x"] = zx
        self.zone["y"] = zy
        self.zone["lat"] = float(lat)
        self.zone["lon"] = float(lon)
        if radius_m is not None:
            self.zone["radius_m"] = float(radius_m)
        self.events.append({
            "type": "ZONE",
            "lat": self.zone["lat"],
            "lon": self.zone["lon"],
            "radius_m": self.zone["radius_m"],
        })

    def fail_nodes(self, ids_or_count: list[str] | int = 2) -> list[str]:
        if isinstance(ids_or_count, list):
            targets = [self.drone_map[i] for i in ids_or_count if i in self.drone_map]
        else:
            online = [d for d in self.drones if d.status == "ONLINE"]
            count = min(int(ids_or_count), max(0, len(online) - 1))
            targets = self.rng.sample(online, count)
        failed_ids: list[str] = []
        for d in targets:
            if d.status == "OFFLINE":
                continue
            d.status = "OFFLINE"
            d.band = "NONE"
            d.route = []
            d.route_state = "DOWN"
            d.reboot_at_s = self.t + float(CFG["REBOOT_S"])
            failed_ids.append(d.id)
        if failed_ids:
            self.events.append({"type": "NODE_FAILURE", "ids": failed_ids, "active": True})
            self.log("CRIT", f"Node failure on {', '.join(failed_ids)}")
        return failed_ids

    def anomaly_features(self, d: DroneState) -> tuple[float, float, float, float]:
        """Return clean 4-dim telemetry evidence vector: (rssi, snr, loss, gnss_offset_m)."""
        return (d.rssi_dbm, d.snr_db, d.loss, d.gnss_offset_m)

    def anomaly_features_noisy(
        self,
        d: DroneState,
        rng: random.Random | None = None,
        sigma_rssi: float = 0.45,
        sigma_snr: float = 0.35,
        sigma_loss: float = 0.001,
        sigma_gnss: float = 0.20,
    ) -> tuple[float, float, float, float]:
        """Return 4-dim telemetry evidence vector with seeded Gaussian measurement noise."""
        r = rng if rng is not None else self.rng
        rssi = d.rssi_dbm + r.gauss(0.0, sigma_rssi)
        snr = d.snr_db + r.gauss(0.0, sigma_snr)
        loss = clamp(d.loss + r.gauss(0.0, sigma_loss), 0.0, 1.0)
        gnss = max(0.1, d.gnss_offset_m + r.gauss(0.0, sigma_gnss))
        return (rssi, snr, loss, gnss)

    def _update_mesh_and_telemetry(self, dt: float) -> None:
        if self.jam["active"] and self.jam["ramp_dbps"] != 0.0 and dt > 0.0:
            self.jam["power_db"] = min(
                float(self.jam["max_power_db"]),
                float(self.jam["power_db"]) + float(self.jam["ramp_dbps"]) * dt,
            )

        jam_active = bool(self.jam["active"])
        jam_power = float(self.jam["power_db"]) if jam_active else 0.0
        spoof_active = bool(self.spoof["active"])

        for d in self.drones:
            if d.status == "OFFLINE":
                d.speed = 0.0
                d.alt = max(35.0, d.alt - dt * 0.8)
                if d.reboot_at_s > 0.0 and self.t >= d.reboot_at_s:
                    d.status = "ONLINE"
                    d.reboot_at_s = 0.0
                    d.route_state = "OK"
                    d.band = "FSOC"
                    self.events.append({"type": "NODE_RESTORE", "ids": [d.id], "active": True})
                    self.log("INFO", f"{d.id} watchdog reboot complete")
                continue

            if self.rth or d.mode == "RTH":
                rr = 120.0 + d.index * 24.0
                ang = d.phase + self.t * 0.05 * d.dir
                tx = self.hq["x"] + rr * math.cos(ang)
                ty = self.hq["y"] + rr * math.sin(ang)
                vmax = 55.0
            else:
                tx, ty = d.orbit_target(self.t)
                vmax = 34.0

            if not self.protection and d.gnss == "SPOOFED":
                tx -= d.spoof_offset_x
                ty -= d.spoof_offset_y

            if dt > 0.0:
                dx = tx - d.x
                dy = ty - d.y
                dist = math.hypot(dx, dy)
                max_step = vmax * dt
                nx = tx if dist <= max_step else d.x + (dx / dist) * max_step
                ny = ty if dist <= max_step else d.y + (dy / dist) * max_step
                d.vx = 0.85 * d.vx + 0.15 * ((nx - d.x) / dt)
                d.vy = 0.85 * d.vy + 0.15 * ((ny - d.y) / dt)
                d.x, d.y = nx, ny
                d.speed = math.hypot(d.vx, d.vy)
                if d.speed > 0.5:
                    d.heading = math.atan2(d.vy, d.vx)
                alt_target = (
                    55.0 + d.index * 7.0
                    if d.mode == "RTH"
                    else d.base_alt + 7.0 * math.sin(self.t * 0.04 + d.phase)
                )
                d.alt = d.alt + clamp(dt * 0.5, 0.0, 1.0) * (alt_target - d.alt)
                d.battery = max(0.0, d.battery - dt * (0.004 + d.speed * 0.0003))

            d.jam_spatial = jam_factor_at(
                d.x, d.y, self.zone["x"], self.zone["y"], self.zone["radius_m"], jam_active
            )
            d.spoof_spatial = spoof_factor_at(
                d.x, d.y, self.zone["x"], self.zone["y"], self.zone["radius_m"], spoof_active
            )

            eff_jam_norm = d.jam_spatial * (jam_power / 38.0)
            if eff_jam_norm > 0.55 and not spoof_active:
                d.gnss = "LOST"
            elif d.spoof_spatial > 0.0:
                d.gnss = "SPOOFED"
            elif eff_jam_norm > 0.55:
                d.gnss = "LOST"
            else:
                d.gnss = "OK"

            if d.spoof_spatial > 0.0 and dt > 0.0:
                d.spoof_offset_x += float(self.spoof["vec_x"]) * d.spoof_spatial * dt
                d.spoof_offset_y += float(self.spoof["vec_y"]) * d.spoof_spatial * dt
            elif d.spoof_spatial == 0.0 and dt > 0.0:
                decay = math.exp(-dt / 12.0)
                d.spoof_offset_x *= decay
                d.spoof_offset_y *= decay
                if math.hypot(d.spoof_offset_x, d.spoof_offset_y) < 1.5:
                    d.spoof_offset_x = 0.0
                    d.spoof_offset_y = 0.0

            base_gnss_jitter = 1.05 + 0.25 * math.sin(self.t * 0.3 + d.index)
            spoof_mag = math.hypot(d.spoof_offset_x, d.spoof_offset_y)
            d.gnss_offset_m = base_gnss_jitter + spoof_mag

        # Compute mesh links and per-drone active band
        online = [d for d in self.drones if d.status == "ONLINE"]
        links: list[dict[str, Any]] = []
        for d in online:
            dist_hq = dist3(d.x, d.y, d.alt, self.hq["x"], self.hq["y"], self.hq["alt"])
            hit = check_los_3d(
                d.x, d.y, d.alt, self.hq["x"], self.hq["y"], self.hq["alt"], OBSTACLE_BOXES
            )
            eff_jam_norm = d.jam_spatial * (jam_power / 38.0)
            need_dect = (hit is not None) or (eff_jam_norm > 0.5) or self.carrier_blackout

            if not need_dect and dist_hq <= CFG["FSOC_RANGE_M"]:
                d.band = "FSOC"
                d.nlos_reason = None
                lk = evaluate_link("FSOC", dist_hq, d.jam_spatial, jam_power)
                d.route = [d.id, "HQ"]
                d.route_state = "OK"
                d.hops = 1
                d.latency_ms = lk["latency_ms"] * 2.0
                d.delivery = 1.0 - lk["loss"]
                links.append({"a": d.id, "b": "HQ", "band": "FSOC", "quality": round(lk["quality"], 3)})
            elif self.protection and dist_hq <= CFG["DECT_RANGE_M"]:
                d.band = "DECT"
                d.nlos_reason = (
                    hit["obstacle"]["name"]
                    if hit is not None
                    else ("RF Jamming Zone" if eff_jam_norm > 0.5 else "Carrier Blackout")
                )
                lk = evaluate_link("DECT", dist_hq, d.jam_spatial, jam_power)
                d.route = [d.id, "HQ"]
                d.route_state = "OK"
                d.hops = 1
                d.latency_ms = lk["latency_ms"] * 2.0
                d.delivery = 1.0 - lk["loss"]
                links.append({"a": d.id, "b": "HQ", "band": "DECT", "quality": round(lk["quality"], 3)})
            else:
                d.band = "NONE"
                d.route = []
                d.route_state = "ISOLATED"
                d.hops = 0
                d.latency_ms = 0.0
                d.delivery = 0.0

            rssi, snr, loss = drone_radio_telemetry(
                dist_hq_m=dist_hq,
                band=d.band if d.band != "NONE" else "FSOC",
                jam_spatial=d.jam_spatial,
                jam_power_db=jam_power,
                carrier_blackout=self.carrier_blackout and d.index in (0, 2, 6),
            )
            d.rssi_dbm = rssi
            d.snr_db = snr
            d.loss = loss

        self.links = links

    def tick(self, dt: float = TICK) -> dict[str, Any]:
        self.t = round(self.t + dt, 6)
        self.tick_count += 1
        self._update_mesh_and_telemetry(dt=dt)

        for d in self.drones:
            if d.status != "ONLINE" or d.route_state != "OK":
                continue
            feats = self.anomaly_features_noisy(d)
            rv = self.rule_detector.detect(d.id, feats)
            self.rule_verdicts[d.id] = rv.to_dict()
            self.policy.ingest_verdict(self.rule_verdicts[d.id])

        return self.state()

    def metrics(self) -> dict[str, float]:
        online = [d for d in self.drones if d.status == "ONLINE"]
        ok = [d for d in online if d.route_state == "OK"]
        reach = (len(ok) / len(online) * 100.0) if online else 0.0
        latency = (sum(d.latency_ms for d in ok) / len(ok)) if ok else 0.0
        loss = (
            (1.0 - sum(d.delivery for d in ok) / len(online)) * 100.0
            if online
            else 100.0
        )
        recovery = self.recoveries[-1] if self.recoveries else 1.2
        return {
            "reachability": round(reach, 2),
            "latency_ms": round(latency, 2),
            "packet_loss": round(loss, 2),
            "recovery_s": round(recovery, 2),
        }

    def state(self) -> dict[str, Any]:
        pol = self.policy.evaluate(
            protection=self.protection,
            rth=self.rth,
            jamming_active=bool(self.jam["active"]),
            spoofing_active=bool(self.spoof["active"]),
        )
        return {
            "t": self.t,
            "tick": self.tick_count,
            "protection": self.protection,
            "rth": self.rth,
            "jam": dict(self.jam),
            "spoof": dict(self.spoof),
            "zone": dict(self.zone),
            "policy": pol,
            "metrics": self.metrics(),
            "drones": [
                {
                    "id": d.id,
                    "lat": round(d.lat, 6),
                    "lon": round(d.lon, 6),
                    "alt": round(d.alt, 1),
                    "battery": round(d.battery, 1),
                    "status": d.status,
                    "mode": d.mode,
                    "gnss": d.gnss,
                    "band": d.band,
                    "rssi_dbm": round(d.rssi_dbm, 2),
                    "snr_db": round(d.snr_db, 2),
                    "loss": round(d.loss, 4),
                    "gnss_offset_m": round(d.gnss_offset_m, 2),
                }
                for d in self.drones
            ],
            "links": list(self.links),
            "rule_based": dict(self.rule_verdicts),
        }
