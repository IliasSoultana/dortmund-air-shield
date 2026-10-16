"""Local ENU projection and 3D building Line-of-Sight (LoS) raycasting."""
from __future__ import annotations

import math
from typing import Any

from .config import CFG, OBSTACLES

M_PER_DEG_LAT: float = 110540.0
M_PER_DEG_LON: float = 111320.0 * math.cos(CFG["ORIGIN"]["lat"] * math.pi / 180.0)


def to_xy(lat: float, lon: float) -> tuple[float, float]:
    """Convert (lat, lon) to local ENU metres (x, y) relative to Dortmund center."""
    x = (lon - CFG["ORIGIN"]["lon"]) * M_PER_DEG_LON
    y = (lat - CFG["ORIGIN"]["lat"]) * M_PER_DEG_LAT
    return x, y


def to_latlon(x: float, y: float) -> tuple[float, float]:
    """Convert local ENU metres (x, y) back to (lat, lon)."""
    lat = CFG["ORIGIN"]["lat"] + y / M_PER_DEG_LAT
    lon = CFG["ORIGIN"]["lon"] + x / M_PER_DEG_LON
    return lat, lon


def dist2(ax: float, ay: float, bx: float, by: float) -> float:
    return math.hypot(ax - bx, ay - by)


def dist3(ax: float, ay: float, az: float, bx: float, by: float, bz: float) -> float:
    return math.hypot(ax - bx, ay - by, az - bz)


def build_obstacle_boxes(obstacles: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    src = obstacles if obstacles is not None else OBSTACLES
    boxes: list[dict[str, Any]] = []
    for ob in src:
        cx, cy = to_xy(ob["lat"], ob["lon"])
        boxes.append({
            **ob,
            "x": cx,
            "y": cy,
            "min_x": cx - ob["rx"],
            "max_x": cx + ob["rx"],
            "min_y": cy - ob["ry"],
            "max_y": cy + ob["ry"],
        })
    return boxes


OBSTACLE_BOXES = build_obstacle_boxes()


def check_los_3d(
    ax: float,
    ay: float,
    az: float,
    bx: float,
    by: float,
    bz: float,
    boxes: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Slab-method 3D segment vs. building AABB intersection test.

    Returns the first occluding building hit dictionary or None if LoS is clear.
    """
    obs = boxes if boxes is not None else OBSTACLE_BOXES
    dx = bx - ax
    dy = by - ay
    dz = bz - az
    for ob in obs:
        tmin, tmax = 0.04, 0.96
        if abs(dx) < 1e-6:
            if ax < ob["min_x"] or ax > ob["max_x"]:
                continue
        else:
            t1 = (ob["min_x"] - ax) / dx
            t2 = (ob["max_x"] - ax) / dx
            if t1 > t2:
                t1, t2 = t2, t1
            tmin = max(tmin, t1)
            tmax = min(tmax, t2)
            if tmin > tmax:
                continue

        if abs(dy) < 1e-6:
            if ay < ob["min_y"] or ay > ob["max_y"]:
                continue
        else:
            t1 = (ob["min_y"] - ay) / dy
            t2 = (ob["max_y"] - ay) / dy
            if t1 > t2:
                t1, t2 = t2, t1
            tmin = max(tmin, t1)
            tmax = min(tmax, t2)
            if tmin > tmax:
                continue

        t_mid = 0.5 * (tmin + tmax)
        z_at_hit = az + dz * t_mid
        if z_at_hit < ob["height"]:
            return {
                "obstacle": ob,
                "t": t_mid,
                "x": ax + dx * t_mid,
                "y": ay + dy * t_mid,
                "z": z_at_hit,
            }
    return None
