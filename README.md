# Dortmund Air Shield — Off-Grid Air Mission Control

Simulation dashboard for **DO-DATA-HACKATHON 2026 · Morpheus Logistik · Challenge 02: OFF-GRID AIR**.

A single self-contained file (`index.html`, no build step, no dependencies) that simulates a 10-drone FANET over Dortmund with jamming, GNSS spoofing, node failures, mesh re-routing and measurable resilience metrics, ready to be driven by a Python backend.

## Run

Live demo: <https://soulnassim.github.io/dortmund-air-shield/> (append `?demo=1` for the scripted scenario).

Locally, open `index.html` in a browser, or serve it:

```bash
python3 -m http.server 8000   # → http://localhost:8000
```

URL parameters:

| Param | Effect |
|---|---|
| `?ws=ws://localhost:8765` | auto-connect to a WebSocket backend |
| `?poll=http://localhost:5000/state&interval=1000` | poll a REST endpoint instead |
| `?demo=1` | auto-run the 70 s demo scenario |

Keyboard: `J` jamming · `G` GPS spoofing · `F` node failure · `R` safe-return-home · `Esc` deselect.
Map: scroll to zoom, drag to pan, click a drone, **Shift+click** to relocate the threat zone.

## Backend integration

```bash
pip install websockets
python backend/mock_backend.py
# open index.html?ws=ws://localhost:8765
```

### Inbound messages (backend → dashboard)

Everything is JSON. Data from the backend is authoritative for 5 s per drone; after that the mock simulation takes over again, so partial feeds work.

```jsonc
{"type": "drones", "data": [{"id": "DR-07", "lat": 51.505, "lon": 7.37, "alt": 95, "battery": 81,
                             "status": "ONLINE|OFFLINE|RTH", "gnss": "OK|LOST|SPOOFED", "band": "2.4GHz|868MHz"}]}
{"type": "event",   "data": {"type": "JAMMING|SPOOFING|NODE_FAILURE|NODE_RESTORE|RTH|ZONE|RESET",
                             "active": true, "lat": 51.505, "lon": 7.365, "radius_m": 2200, "ids": ["DR-04"]}}
{"type": "metrics", "data": {"reachability": 97.2, "latency_ms": 23, "packet_loss": 1.1, "recovery_s": 1.4}}
{"type": "links",   "data": [{"a": "DR-01", "b": "HQ", "band": "2.4GHz", "quality": 0.82}]}
{"type": "log",     "data": {"level": "INFO|OK|WARN|CRIT|NET", "msg": "text"}}
{"type": "state_request"}
```

A bare array of drones, or a single drone object with an `id`, is also accepted. Unknown drone IDs are added to the fleet automatically.

### Outbound messages (dashboard → backend)

```jsonc
{"type": "hello", "client": "dortmund-air-shield", "version": "1.0.0", "fleet": ["DR-01", "..."]}
{"type": "command", "action": "SET_JAMMING|SET_SPOOFING|FORCE_NODE_FAILURE|SAFE_RETURN_HOME|MOVE_ZONE|RESET", "value": true, "ts": 0}
{"type": "state", "data": { /* full snapshot, reply to state_request */ }}
```

### JavaScript API

```js
window.updateDroneData([{ id: 'DR-07', lat: 51.505, lon: 7.37 }]);
AirShield.injectEvent({ type: 'JAMMING', active: true });
AirShield.updateMetrics({ reachability: 99 });
AirShield.updateLinks([{ a: 'DR-01', b: 'HQ', band: '868MHz', quality: 0.4 }]);
AirShield.connect('ws://localhost:8765');
AirShield.poll('http://localhost:5000/state', 1000);
AirShield.onCommand(cmd => console.log(cmd));
AirShield.getState();
```

## Simulation model

- **Link budget**: 2.4 GHz mesh, quality `1 − (d/4 km)³`; 868 MHz LoRa fallback up to 9 km at 5.5 kbps.
- **Jamming** removes 2.4 GHz links and GNSS inside the zone and degrades the fringe out to 1.35 × radius. Nodes fall back to LoRa automatically.
- **Spoofing** drags the GNSS fix of nodes within 1.5 × radius. A plausibility check against INS/VIO rejects GNSS once the offset passes 60 m.
- **Routing**: Dijkstra to HQ, with cost = latency + loss penalty + a LoRa penalty, plus hysteresis. A broken route triggers re-convergence (450 ms + 220 ms/hop, +900 ms over LoRa). The measured heal time is reported as **Recovery Time**.
- **QoS**: strict priority scheduling per path: C2 → Telemetry → Inter-drone → Video. Video is cut to 25 % while jamming or during RTH and dropped entirely over LoRa.
