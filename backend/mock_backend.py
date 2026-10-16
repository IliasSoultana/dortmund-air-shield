"""Minimal WebSocket backend for the Dortmund Air Shield dashboard.

Run:   pip install websockets && python backend/mock_backend.py
Open:  index.html?ws=ws://localhost:8765

Streams drone telemetry at 2 Hz and prints every operator command the
dashboard sends back (button clicks). Replace `telemetry()` with real data.
"""
import asyncio
import json
import math
import time

import websockets

HOST, PORT = "0.0.0.0", 8765

# (lat, lon) orbit centres, radius in degrees-ish, angular speed rad/s
ORBITS = {
    "DR-01": (51.5350, 7.4650, 0.008, 0.050),
    "DR-02": (51.5200, 7.4200, 0.007, -0.060),
    "DR-03": (51.5320, 7.3850, 0.009, 0.045),
    "DR-04": (51.5450, 7.4950, 0.008, -0.050),
    "DR-05": (51.4950, 7.4150, 0.008, 0.055),
    "DR-06": (51.4930, 7.4800, 0.009, -0.050),
    "DR-07": (51.5050, 7.3880, 0.012, 0.040),
    "DR-08": (51.5150, 7.5300, 0.009, 0.045),
    "DR-09": (51.4750, 7.4550, 0.008, -0.055),
    "DR-10": (51.4830, 7.3520, 0.009, -0.050),
}


def telemetry(t: float) -> list[dict]:
    drones = []
    for i, (drone_id, (lat, lon, r, w)) in enumerate(ORBITS.items()):
        a = i + w * t
        drones.append({
            "id": drone_id,
            "lat": lat + r * 0.6 * math.sin(a),
            "lon": lon + r * math.cos(a),
            "alt": 100 + 10 * math.sin(t * 0.1 + i),
            "battery": max(5.0, 95 - i * 3 - t * 0.02),
            # optional: "status": "ONLINE"|"OFFLINE"|"RTH", "gnss": "OK"|"LOST"|"SPOOFED", "band": "2.4GHz"|"868MHz"
        })
    return drones


async def handler(ws):
    print("dashboard connected")
    t0 = time.time()

    async def sender():
        tick = 0
        while True:
            t = time.time() - t0
            await ws.send(json.dumps({"type": "drones", "data": telemetry(t)}))
            if tick % 60 == 30:  # every 30 s toggle a jamming event
                active = (tick // 60) % 2 == 0
                await ws.send(json.dumps({"type": "event", "data": {"type": "JAMMING", "active": active}}))
                await ws.send(json.dumps({"type": "log", "data": {"level": "INFO", "msg": f"backend: jamming {'ON' if active else 'OFF'}"}}))
            tick += 1
            await asyncio.sleep(0.5)

    async def receiver():
        async for raw in ws:
            print("<-", raw)

    try:
        await asyncio.gather(sender(), receiver())
    except websockets.ConnectionClosed:
        print("dashboard disconnected")


async def main():
    async with websockets.serve(handler, HOST, PORT):
        print(f"Air Shield mock backend on ws://{HOST}:{PORT}")
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
