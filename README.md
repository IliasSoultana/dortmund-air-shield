# Dortmund OFF-Grid Air (`Dortmund-OFF-grid-air`)

**A hybrid FSOC laser (1550 nm) and DECT NR+ (1.9 GHz) mesh, flown over a 3D Dortmund with real-world aerospace & RF physics.**

Ten drones. One control center at the Reinoldikirche. A city that keeps getting in the way. The dashboard is a single file, `index.html`, with no build step. Open it and the mission is already running. A Python backend can take over the telemetry; until it does, the built-in simulation flies the whole thing.

DO-DATA-HACKATHON 2026 · Morpheus Logistik · Challenge 02: OFF-GRID AIR

**Live GitHub Pages** · <https://soulnassim.github.io/Dortmund-OFF-grid-air/> · **Repository** · <https://github.com/SoulNassim/Dortmund-OFF-grid-air>

---

## The problem

A drone over a European city center goes quiet in three ways, and they stack. The hackathon question is what the fleet does in the minute after that happens.

### The building eats the laser

Free-space optical is the fast link: a laser, gigabit-class, a few milliseconds. A laser stops at the first solid object. Dortmund Innenstadt is a canyon. The Dortmunder U-Tower, the Hbf tower, Sparkasse, Ellipson, the RWE block, the Stadthaus, Westfalentower, Ostwall — several of them are taller than a drone cruising at 80–100 m.

A node behind the U-Tower still has a perfect radio day and a dead optical path to HQ. The beam hits concrete. Video, telemetry and command die on the same face of the building. A mesh that only draws straight lines on a flat map never shows you why.

### The jammer eats the radio that survives the building

The link that can pass a wall is the link a jammer is built to kill. Sector West, centered on the U-Tower, lifts the noise floor on 2.4 GHz, 5.8 GHz and GNSS L1. Inside the circle the laser is already contested and the satellite fix is gone. A fleet with one band leaves the map the moment it crosses that line, still airborne, still on its orbit, unreachable.

### The position can be a lie, and the relay can just die

Spoofing does not cut the radio. It moves the fix, a few metres a second, until the autopilot is flying a place the airframe is not. Separately, a relay can drop: heartbeat timeout, power bus. Every route that used it is gone. The drones on the far side can still see each other and have no way home.

The number that matters is whether HQ can still reach every node after all three have happened, and how many seconds that took.

---

## What the mesh does

Every 200 ms, each drone tries three things, in this order.

1. **Keep a path to HQ.**
2. **Keep a position it can trust.**
3. **Spend the pipe on command-and-control first.**

The buttons along the bottom only start the attack. The mesh answers by itself. **Protected / Unprotected** (`P`) turns those answers off, so the same attack can be shown both ways.

```mermaid
flowchart TD
  tick["Every 200 ms, per drone"] --> radio["1 · Keep a path to HQ"]
  radio --> pos["2 · Trust the fix only if it agrees with INS"]
  pos --> pipe["3 · Fill the pipe: C2, then telemetry, then everyone else"]
  radio --> seen["Map beams, fleet row, Recovery Time"]
  pos --> seen2["Ghost fix, GNSS badge"]
  pipe --> seen3["QoS bars, policy label"]
```

| | Protected (`FSOC + DECT NR+`) | Unprotected (`Standard 2.4 GHz Funk`) |
|---|---|---|
| Line of sight | A blocked 1550 nm laser (confirmed via 3 s hysteresis) switches to a 1.9 GHz DECT NR+ hop through the building | Standard 2.4 GHz Funk drops behind 3D concrete buildings (`LoS Blocked · Funk Lost`) |
| Jamming (LoS clear) | **FSOC 1550 nm laser is 100% immune (`0%` loss)** to RF jamming as long as 3D LoS is clear | 2.4 GHz Funk collapses (`Funk Jammed · RIP`) |
| Jamming + NLOS (`>150 m` Outer Zone) | DECT NR+ survives via FHSS/DSSS ($1/r^2$ inverse-square law), triggers **`QoS EMERGENCY MODE`**: Video `0%`, `+40 ms` latency, **`12 kbps` C2 locked** (`ONLINE · Degraded`) | Total link loss |
| Jamming Core (`<150 m`) + NLOS Shadow | **Honest Double-Fail → `ISOLATED • AUTONOMOUS POP-UP (INS/VIO)`**: after `1.5 s`, the drone climbs vertically (`50 m → 125 m` in `~3.2 s`) until it clears the `95 m` roof and locks FSOC Laser onto High-Altitude Relays (`DR-01` / `DR-02` at `120 m`) | Total link loss; drone remains stranded |
| Position | GNSS is rejected once it disagrees with INS/VIO by 60 m. The airframe stays on the real track | The autopilot flies the fake fix |
| Routing | Broken routes are rebuilt via Dijkstra or High-Altitude Relays (`120 m`). Cut-off groups outside the `<150 m` core get a DECT bridge | The drone waits for the static direct link to return |
| Traffic | Strict priority: C2 (`12 kbps`, 3× ARQ), telemetry, inter-drone, then video | Best-effort shared pipe; video competes with C2 |

---

## The visualisation

The city is the interface. MapLibre draws Dortmund at a 60° pitch, bearing −18°, centered on `51.5136° N, 7.4653° E`. OpenStreetMap buildings extrude from real heights. Eight landmark volumes — the U-Tower among them — are also drawn as the exact blocks the line-of-sight raycast uses, so the thing that breaks the laser is the thing you are looking at.

Drones sit at their real altitude, with a drop-line down to a shadow on the street. HQ is the optical mast over the Reinoldikirche.

![Desktop mission control: 3D Dortmund at 60 degrees, green FSOC beams, amber DECT fallback through the U-Tower, fleet on the left, resilience scorecard on the right](docs/img/desktop-3d-los.png)

*Nominal hybrid mesh. Green beams are clear line of sight. Amber dashes are DECT NR+ where a building already ate the laser. The fleet list and the scorecard float over the city.*

| Region | What it shows |
|---|---|
| Map | Pitched Dortmund. Drones are quadcopters labelled with id and altitude. HQ is the ring on the mast. |
| Fleet, left | One row per drone: status dot, id, mesh IP `10.41.0.x`, band, latency. Click a row to expand altitude, speed, battery, hops, 3D line of sight and GNSS, and to pin that drone. |
| Scorecard, right | Reachability, latency, packet loss, recovery time, each with a sparkline. Under them, four traffic bars. |
| Toast, top | The latest log line. Click it for the full event log. The pill is the threat level: NOMINAL, ELEVATED, CRITICAL. |
| Dock, bottom | Protection, the four injections, demo, reset, simulation speed. |

Scroll to zoom. Drag to pan. Right-drag or Ctrl-drag to orbit and change pitch. `3D` snaps between 60° and a shallower view. `⌖` flies back to the Innenstadt.

Click a drone, click it again to dismiss, **Shift+click** to move the threat zone. Keys: `P` protection · `J` jamming · `G` GPS spoofing · `F` node failure · `R` return home · `Esc` deselect.

On a narrow screen the same panels collapse: fleet becomes a chip strip, the scorecard becomes a sheet, the dock scrolls sideways. The map stays full-bleed.

### How to read the air

| You see | It means |
|---|---|
| Solid green beam | FSOC laser on a clear 3D line of sight |
| Green stub ending in a red ✕ | The laser reached a building face and stopped. The label on the block is the occluder |
| Dashed amber line through a building | DECT NR+ fallback. The path is allowed to be non-line-of-sight |
| `NLOS · DECT NR+` next to a drone | That node's route home is on the fallback radio |
| Amber wireframe on the U-Tower | The landmark volume used by the raycast, drawn so the blocker is obvious |
| Pulsing amber dot | Fallback, spoofed fix, or a route still rebuilding |
| Pulsing red dot | GNSS lost, isolated, or no radio at all |
| Amber ghost on a dashed tether | The fake GNSS fix. The airframe stays on the real track while protection is on |
| Red disc, Sector West | Jamming, centered on the U-Tower |
| Wider amber ring | Spoofing reach, 1.5× the jam zone |

---

## The two links

DECT NR+ here is the second radio **inside the simulation**. It is not a hardware modem and the Python backend does not speak it. The backend sends positions and events. The dashboard decides the band, by raycasting every candidate hop against the building volumes.

| | FSOC laser | DECT NR+ 1.9 GHz |
|---|---|---|
| Role | Primary, when the 3D path is clear | Automatic fallback through buildings, jamming and partitions |
| Needs line of sight | yes — the beam dies on the first block it hits | no — the hop is drawn through the block |
| Reach | 2.8 km | 4.5 km |
| Capacity | up to 1 Gbps, scaled by link quality | 4.8 Mbps |
| Latency | a few milliseconds | tens of milliseconds, higher inside the jam |
| Carries full video | yes | video is shed; C2, telemetry and inter-drone still fit |
| On the map | solid green | dashed amber |

```mermaid
flowchart TD
  A["Drone is online"] --> B{"Clear 3D line of sight to a neighbor, inside 2.8 km, jam under half strength?"}
  B -->|yes| W["Lock the FSOC laser"]
  B -->|no| P{"Protection on?"}
  P -->|yes| L["Open DECT NR+ through the building, up to 3 neighbors inside 4.5 km"]
  P -->|no| N["No link. The drone is still flying and off the network"]
  W --> I{"Its group still reaches HQ?"}
  I -->|yes| R["Dijkstra picks the cheapest route to HQ"]
  I -->|"no, and protection is on"| G["The group member closest to the rest opens a DECT bridge"]
  G --> R
  L --> R
```

Routing cost is latency plus packet loss weighted hard, with an extra penalty on every DECT hop. A clear laser wins whenever it still reaches HQ. DECT is taken when it is the path that still works. A route already in use is kept until a new one is clearly cheaper, so the mesh does not flap every time a rotor crosses a roofline.

---

## Four ways the city fights back

### Jamming — `J`

A transmitter in **Sector West · U-Tower** (620 m, full strength inside, gone at 1.35×) takes 2.4 / 5.8 GHz and GNSS L1. Drones whose orbits cross the circle lose the laser and the satellite fix.

| | Protected | Unprotected |
|---|---|---|
| Radio | The hop turns dashed amber. The row reads `NLOS - DECT Fallback` | The lines vanish. The row reads `Isolated` |
| GNSS | Fix marked lost. Navigation continues on inertial dead-reckoning | Same loss of fix, and no second radio to report it on |
| Video | Shed so C2 stays full. Policy label moves to anti-jam | Video keeps asking for a pipe that is already gone |
| Scorecard | Reachability holds. Latency and loss rise, because the surviving path is the slower one | Reachability drops by about one tenth per drone that loses its links |

### GPS spoofing — `G`

The radio stays up. Every drone inside 1.5× the zone is fed a counterfeit L1 fix that drifts at about 7 m/s. The cheat is an amber ghost tethered to the airframe.

| | Protected | Unprotected |
|---|---|---|
| Under 60 m | Badge says spoofed. The drone still flies its real orbit | The autopilot is already steering toward the fake fix |
| Past 60 m | The fix disagrees with INS and is rejected. The airframe stays on the real track | The drone leaves its orbit and the drift keeps growing |
| After you turn it off | The offset decays and the fix is trusted again | The drone has to fly back to the orbit it left |

### Node failure — `F`

Two random drones die: heartbeat timeout, power bus. They stop, descend, and reboot themselves after 20 s. This is a different event from falling off the network. The node is actually offline.

Everyone who was routing through them loses that hop. Protected, Dijkstra installs a new route. The wait is about **450 ms plus 220 ms per hop**, plus **900 ms** when the new path uses DECT, plus a little jitter. That measured wait is the **Recovery Time** number. Unprotected, no new route is searched. Those drones stay broken until the dead relay finishes rebooting.

If a whole group still meshes locally and has lost every path to HQ, protection picks the member closest to the rest of the network and opens a DECT bridge. The others ride that bridge home.

### Return home — `R`

The one response that waits for the operator. The mesh will not fly the fleet home by itself. Pressing it pulls every drone toward HQ, sheds video, and marks C2 as emergency. Press again and the fleet returns to its orbits.

---

## When a drone falls off

Falling off means the drone is still airborne and still flying, and it has no usable path to HQ. Command, telemetry, inter-drone traffic and video from that drone all deliver nothing.

```mermaid
stateDiagram-v2
  [*] --> Joining
  Joining --> OnRoute: a path to HQ is found
  OnRoute --> Rerouting: a hop on the route dies
  Rerouting --> OnRoute: protection builds a new path
  Rerouting --> Isolated: the wait expires and no path exists
  Isolated --> Rerouting: a path becomes possible again
  OnRoute --> Offline: node failure
  Offline --> Joining: watchdog reboot after 20 s
```

What you see, in order:

1. The green beams disappear. With protection off, no amber DECT lines replace them. The log says the optical and DECT links are gone.
2. For about a second the drone is **rerouting**. Route empty, latency a dash.
3. The wait expires and the drone is **isolated**. A pulsing red dot replaces its links. The flight code keeps the mission orbit. With spoofing on and protection off, it keeps steering toward the fake fix.
4. It still counts as online, so the fleet header does not move it to Off. It counts as unreachable, so reachability falls and packet loss jumps.
5. Average latency can look healthier after the drop. Only drones that still have a route are in that average. Read reachability when nodes have gone isolated.

It comes back when a path to HQ exists again. Protected, that is the moment a DECT or FSOC route appears, and the heal time is recorded. Unprotected, it happens when the original links return: jamming off, or the failed relay rebooted. Switching the shield back to Protected during the attack pulls isolated drones in within a few seconds.

---

## The four numbers

| Number | Target | What moves it |
|---|---|---|
| Reachability | > 95 % | Share of online drones that currently have a route to HQ. One isolated drone is about −10 % |
| Avg latency | < 50 ms | Round trip of the drones that still have a route. DECT pushes this up. Isolated drones are left out |
| Packet loss | < 2 % | Traffic that does not arrive. An isolated drone counts as a total loss |
| Recovery time | < 3 s | Seconds the mesh took to install a new route after one broke. During a heal it shows the wait so far |

White is inside the target. Amber, then red, means the target has been crossed. The small label under each number says whether the figure is from the live simulation, a WebSocket feed, or a metric override.

---

## Traffic, in order

Each drone's path is filled strictly. C2 is about 1.2 kbps and is retried three times, so it stays near full on a lossy hop. Telemetry is about 3 kbps. Inter-drone is about 12 kbps. Video wants 3.5 Mbps.

```mermaid
flowchart LR
  pipe["Bits available on the path to HQ"] --> c2["1 · C2"]
  c2 --> tel["2 · Telemetry"]
  tel --> inter["3 · Inter-drone"]
  inter --> vid["4 · Video, only with what is left"]
```

On DECT the pipe is 4.8 Mbps, so video is the first thing shed and the first three still fit. During jamming or return-home, video that is still on the laser is cut back on purpose. Unprotected, the order is removed: all four classes take a proportional share, video included, and C2 gets no retries.

---

## Seventy seconds

`?demo=1` runs the attack on its own. Add `?protect=0` for the same script with the defenses off.

| Time | What happens |
|---|---|
| 0.5 s | Hybrid mesh over 3D Dortmund, lasers where the sky is clear |
| 5 s | Jammer on in Sector West, on the U-Tower |
| 16 s | Spoofer joins the jammer |
| 28 s | Two relay drones fail |
| 42 s | Operator sends return home |
| 62 s | Threat cleared, lasers come back, fleet returns to mission |
| 70 s | Scenario ends |

---

## Run

```bash
python3 -m http.server 8000   # → http://localhost:8000
```

| URL | What you get |
|---|---|
| `?demo=1` | 70 s scripted attack, then all-clear |
| `?protect=0` | start with every automatic defense off |
| `?protect=0&demo=1` | the scripted attack with no protection — open it beside `?demo=1` |
| `?ws=ws://localhost:8765` | connect to the Python backend on load |
| `?poll=http://localhost:5000/state&interval=1000` | poll a REST endpoint instead |

---

## Backend & Reproducible Threat Detection

### Run the real deterministic backend

```bash
pip install websockets
python3 -m backend.engine.server
# open index.html?ws=ws://localhost:8765
```

For lightweight 2 Hz position-only telemetry testing, `python3 backend/mock_backend.py` is also available. When `backend.engine.server` is running on `ws://localhost:8765`, it drives the deterministic 10-drone 3D Dortmund engine, broadcasts live `CONTRASTIVE` verdicts and `ANALYSIS` assessments, and accepts `CONFIRM_THREAT` and `ANALYZE` operator commands.

### Contrastive Prototype Pipeline (Judges' 5-Sentence Overview)

Every online drone's 4D telemetry vector `(RSSI, SNR, packet loss, GNSS-INS offset)` is evaluated in parallel by a fixed-threshold rule-based detector and a contrastive prototype detector. During clean operation, the contrastive detector learns per-drone nominal prototypes `(mean, std)` and scores incoming telemetry via directional axis-aligned Mahalanobis z-scores, catching slow-ramping attacks that rolling baselines absorb. When an anomaly exceeds the z-score gate, its unit direction vector in z-score space is compared via cosine similarity against known threat prototypes (`jamming`, `spoofing`). If no known prototype matches above threshold (`cos >= 0.84`), the detector refuses to guess and emits `UNEXPLAINED — new profile, needs operator label`. Once the operator confirms the novel signature with a single click (`CONFIRM_THREAT` -> `learn_threat()`), the new prototype is stored and every subsequent encounter of that attack profile is immediately attributed by name.

### Reproducible Evaluation Harness & Headline Numbers

Run the deterministic, bit-identical Pass 1 vs Pass 2 benchmark in one command:

```bash
python3 -m backend.engine.threat_eval --json threat_eval.json
```

- **0 false flags** in nominal operation across both rule-based and contrastive detectors (`seed=20260416`).
- **Ramping jammer detection delay: `0.0 s` (contrastive) vs `9.5 s` (rule-based)** — the rule-based rolling baseline absorbs the slow 1.55 dB/s climb until the hard floor is breached, whereas the contrastive nominal prototype flags the deviation at onset.
- **Slow GNSS spoofing detection delay: `0.0 s` (contrastive) vs `9.0 s` (rule-based)**.
- **Novel multi-vector threats (`coordinated_rf_gnss`, `carrier_blackout`)**: `2/2` honestly flagged as `UNEXPLAINED` in Pass 1 (before operator confirmation) and `2/2` (`100%`) accurately attributed at `0.0 s` onset in Pass 2 after `learn_threat()`.

Run the full unit test suite (19 tests covering 3D raycasting, link budgets, HMAC security, contrastive online learning, and the LLM analyst):

```bash
python3 -m unittest discover -s backend/tests -v
```

### LLM Layer (Security Analyst CoPilot)

The LLM never detects. It explains what the deterministic detectors found, proposes concrete countermeasures, files issues for the operator — the same CoPilot pattern the team used to win the 2025 federal BIM hackathon. Sitting strictly downstream of the rule-based and contrastive detectors (`backend/engine/llm_analyst.py`), the analyst consumes structured verdicts plus the 4D evidence window and outputs a German situational summary, hypothesis, confidence score, executable engine command buttons (`SET_PROTECTION`, `SAFE_RETURN_HOME`, `MOVE_ZONE`, `CONFIRM_THREAT`), and a prioritized operator issue (`LOW` / `MED` / `CRIT`). The demo default is the deterministic, offline `MockAnalyst` (`LLM_ANALYST=mock`, zero latency, bit-identical), while the live university LLM (`http://chat.kiconnect.nrw/v1/responses`, model `gpt-6-studierende`) is a single environment variable switch away (`LLM_ANALYST=uni` or `LLS_ANALYST=uni`) with automatic zero-downtime fallback to the mock analyst if the network or endpoint is unreachable.

### Backend → dashboard

```jsonc
{"type": "drones", "data": [{"id": "DR-07", "lat": 51.514, "lon": 7.454, "alt": 78, "battery": 81,
                             "status": "ONLINE|OFFLINE|RTH", "gnss": "OK|LOST|SPOOFED", "band": "FSOC|DECT"}]}
{"type": "event",   "data": {"type": "JAMMING|SPOOFING|NODE_FAILURE|NODE_RESTORE|RTH|PROTECTION|ZONE|RESET",
                             "active": true, "lat": 51.5132, "lon": 7.4545, "radius_m": 620, "ids": ["DR-04"]}}
{"type": "CONTRASTIVE", "data": {"device": "DR-01", "label": "UNEXPLAINED", "similarity": 0.612,
                                 "dims": {"rssi": 3.4, "snr": 4.8, "loss": 2.1, "gnss_offset_m": 5.2},
                                 "evidence": [-84.0, 12.5, 0.14, 18.2], "attributed": false}}
{"type": "ANALYSIS",    "data": {"backend": "MOCK|UNI", "device": "DR-01", "summary": "...",
                                 "hypothesis": "unbekanntes Muster", "confidence": 0.72,
                                 "recommended_actions": [{"command": "CONFIRM_THREAT", "label": "..."}],
                                 "issue": {"title": "...", "severity": "CRIT", "assignee_role": "..."}}}
{"type": "metrics", "data": {"reachability": 97.2, "latency_ms": 23, "packet_loss": 1.1, "recovery_s": 1.4}}
{"type": "links",   "data": [{"a": "DR-01", "b": "HQ", "band": "FSOC", "quality": 0.82}]}
{"type": "log",     "data": {"level": "INFO|OK|WARN|CRIT|NET", "msg": "text"}}
{"type": "state_request"}
```

A bare array of drones, or a single drone object with an `id`, is also accepted. Unknown drone IDs are added to the fleet. `PROTECTION` with `"active": false` is the same switch as the shield. Older band strings (`2.4GHz`, `868MHz`, `LORA`) still map: anything that looks like a sub-GHz fallback becomes DECT, everything else becomes FSOC.

### Dashboard → backend

```jsonc
{"type": "hello", "client": "dortmund-air-shield", "version": "2.0.0", "fleet": ["DR-01"]}
{"type": "command", "action": "SET_JAMMING|SET_SPOOFING|SET_RAMP_JAM|SET_COORDINATED|CONFIRM_THREAT|ANALYZE|FORCE_NODE_FAILURE|SAFE_RETURN_HOME|SET_PROTECTION|MOVE_ZONE|RESET", "value": true, "ts": 0}
{"type": "state", "data": { }}
```

### JavaScript

```js
window.updateDroneData([{ id: 'DR-07', lat: 51.514, lon: 7.454, alt: 78 }]);
AirShield.injectEvent({ type: 'JAMMING', active: true });
AirShield.injectEvent({ type: 'PROTECTION', active: false });
AirShield.updateMetrics({ reachability: 99 });
AirShield.updateLinks([{ a: 'DR-01', b: 'HQ', band: 'DECT', quality: 0.4 }]);
AirShield.connect('ws://localhost:8765');
AirShield.poll('http://localhost:5000/state', 1000);
AirShield.onCommand(cmd => console.log(cmd));
AirShield.getState();
```

---

## Constants

| Constant | Value |
|---|---|
| Fleet | `DR-01 … DR-10` (`DR-01` & `DR-02` High-Altitude Relays at `120 m`; `DR-03` & `DR-07` urban canyon nodes at `50–52 m`; others cruise at `85–105 m`), plus HQ at Reinoldikirche (`65 m`) |
| Mesh addresses | `10.41.0.1` … `10.41.0.10` |
| Camera | zoom 14.35, pitch 60°, bearing −18°, Dortmund center |
| Occluders | Realistic Dortmund heights: RWE Tower (`100 m`), Dortmunder U-Tower (`95 m`), Westfalentower (`86 m`), Sparkasse (`78 m`), Ellipson (`76 m`), Hbf Tower (`74 m`), plus typical urban blocks (`22–28 m`) |
| 3D LoS Hysteresis | `3000 ms` (`3 s` debounce on building edges) |
| Jam zone ($1/r^2$) | `51.5132° N, 7.4545° E`, outer radius `620 m` (DECT NR+ FHSS/DSSS `QoS EMERGENCY MODE` `>150 m`), inner core `<150 m` (total RF blackout) |
| Autonomous Pop-Up | Triggered after `1.5 s` in `ISOLATED` (`<150 m` jam core + NLOS shadow): `INS/VIO` vertical climb `50 m → 125 m` (`>95 m` roof clearance in `~3.2 s`) |
| GNSS lost | jam strength above 0.55 (`INS/VIO` dead-reckoning with zero RF/GPS) |
| Spoof radius | 1.5× the jam zone, drift ~7 m/s |
| GNSS rejected | offset greater than 60 m against INS |
| FSOC (1550 nm) | `2.8 km`, up to `1 Gbps`, `0%` RF jammer loss, requires a clear 3D ray |
| DECT NR+ (1.9 GHz) | `4.5 km`, `4.8 Mbps`, NLOS building penetration, `+40 ms` latency & `12 kbps` C2 lock under outer jamming |
| Failed node | back after 20 s |
| Network tick | every 200 ms |
