# KANSEI: build contract

KANSEI is an original drift-racing game whose circuits and cars are X3D 4.0 files. The same track bytes are drawn by X_ITE 16.5.1 in the browser and read by the game's own deterministic vehicle simulation, exactly as NIB (`../x3d.platformer/`) does for platform levels. Read `../PLATFORMER.md` and `../x3d.platformer/README.md` first: KANSEI reuses that contract (sim tick owns the game, the picture interpolates, every track carries its proof of play).

Everything here is original: names, cars, circuits, art, sound. No real car makes, models or numbers; no real circuits.

## 0. Layout

```
x3d.drift/
  index.html, main.js          the page (menus, HUD, input, fixed-step loop, replay, photo mode)
  engine/                      // loom:sim files: fmath.js sim.js car.js cars.js track.js x3d.js race.js ai.js tape.js
                               picture files: render.js camera.js fx.js audio.js ui.js (free to use Math.sin etc.)
  build/build_world.py         writes levels/*.x3d, cars/*.x3d, garage.x3d, textures/*.png (stdlib + PIL + numpy only), --check rebuilds byte-identical
  levels/*.x3d, MANIFEST.json  circuits
  cars/*.x3d                   car models
  textures/                    generated PNGs (keep the whole folder under 8 MB)
  tapes/*.tape.json            proof-of-play tapes
  tools/                       bot.mjs replay.mjs check_browser.cjs shots.cjs fetch_xite.sh
  tests/                       handling.test.mjs race.test.mjs run_all.mjs
  docs/                        CONTRACT.md HANDLING-CARD.md media/
  vendor/x_ite -> X_ITE 16.5.1 dist (NOT committed; symlink for local runs, see tools/fetch_xite.sh)
```

`tools/fetch_xite.sh` puts the X_ITE 16.5.1 dist in `vendor/x_ite` (not committed); without it the page loads X_ITE from a CDN.

## 1. Units and frames

- SI units: metres, seconds, kilograms, newtons, radians inside the sim. km/h only on the HUD.
- X3D world: +Y up. The sim's ground plane is X–Z.
- A car's local frame: **+Z forward, +Y up, +X left**. Car models in `cars/*.x3d` face +Z with the wheels on y = 0 at rest.
- `yaw` is the rotation about +Y that maps local +Z to the heading, so the X3D Transform is `rotation 0 1 0 yaw` and forward = (sin yaw, 0, cos yaw), left = (cos yaw, 0, −sin yaw). yaw grows when the car turns toward its left.
- Steering input `steer` is −127..127, **positive = steer right** (yaw decreases).
- Fixed tick: dt = 1/120 s. Tick counter is the only clock in the sim.

## 2. Determinism rules (Loom `sim-nonportable-math`)

Files that start with `// loom:sim` may not use `Math.sin cos tan asin acos atan atan2 sinh cosh tanh exp expm1 log log1p log2 log10 pow cbrt hypot random`, the `**` operator, `Date`, or `performance`. `Math.sqrt`, `abs`, `min`, `max`, `floor`, `round`, `sign`, `trunc` are fine (IEEE exact). `engine/fmath.js` provides `dsin dcos datan2 datan dexp dtanh` as fixed polynomials or rational approximations with range reduction (copy NIB's dsin; write the rest; unit-test them against Math.* to 1e-6). Iteration order must be fixed (arrays, never `for…in` over objects with numeric-looking keys, never Map iteration that depends on insertion from non-deterministic sources). The page never writes sim state.

`ENGINE_VERSION = 'kansei-engine/4'` in `engine/sim.js`. Bump it on any change that alters a replay.

## 3. Track metadata (the sim reads only this)

Each `levels/<id>.x3d` carries, in the scene:

```xml
<WorldInfo DEF='TrackInfo' title='Kessel Pass'>
  <MetadataSet name='kansei:track' containerField='metadata'>
    <MetadataString name='id' value='"kessel-pass"'/>
    <MetadataString name='name' value='"Kessel Pass"'/>
    <MetadataString name='subtitle' value='"Mountain touge, sunset"'/>
    <MetadataString name='time' value='"sunset"'/>            <!-- sunset | night | noon | golden -->
    <MetadataInteger name='samples' value='N'/>
    <MetadataDouble name='center' value='x y z bank halfWidth wallL wallR grip ...'/>   <!-- 8 numbers per sample, closed loop, about 2 m apart -->
    <MetadataInteger name='checkpoints' value='i0 i1 ...'/>   <!-- sample indices, i0 = start/finish, at least 12 -->
    <MetadataInteger name='sectors' value='a b'/>             <!-- checkpoint ordinals where sectors 2 and 3 begin -->
    <MetadataDouble name='grid' value='x z yaw  x z yaw ...'/><!-- 6 slots behind the line -->
    <MetadataDouble name='zones' value='i0 i1 side kind ...'/><!-- clipping zones: sample range, side (+1 left edge, -1 right edge), kind (1 inner clip, 2 outer clip) -->
    <MetadataDouble name='props' value='kind x z r ...'/>     <!-- kind 1 cone (knockable), 2 post (static), 3 barrel (heavy) -->
    <MetadataDouble name='targets' value='goldLap silverLap bronzeLap  rushBronze rushSilver rushGold rushPlatinum'/>
    <MetadataString name='runoff' value='"grass"'/>          <!-- grass | sand | tarmac | gravel -->
  </MetadataSet>
</WorldInfo>
```

- `center` sample: position (x, y, z) of the road centreline at the road surface, `bank` (radians; positive bank raises the road's LEFT edge, the edge on a car's +X side when it drives forward along increasing sample index), `halfWidth` (asphalt half-width), `wallL`/`wallR` (distance from centre to the barrier face on each side, ≥ halfWidth + 1), `grip` (surface multiplier, 1.0 dry asphalt; painted curbs 0.92 live in the band halfWidth..halfWidth+1.2).
- Numbers are written by Python with fixed decimals (`%.4f`, banks `%.5f`) so the JS parser reads exactly what the mesh was built from.
- The sim reads the MetadataSet with a regex/attribute parser that works in Node without a DOM (see NIB `engine/x3d.js`). The mesh nodes are never read by the sim.

Off the asphalt (|lateral| > halfWidth + 1.2) the surface is `runoff`: grass 0.55, sand 0.45 (plus drag), gravel 0.5 (plus drag), tarmac 0.85. Barriers: a car's body circle (or 4 corner points) is pushed out of the wall line with restitution 0.25 and tangential friction; the impact impulse becomes an event.

## 4. Track DEF names (the page reads these)

Each track file defines, besides its static world:

- `DEF='Cars'` an empty `Group` where the page adds cars.
- `DEF='FX'` an empty `Group` for smoke, skid marks, sparks.
- `DEF='Sun'` the main `DirectionalLight` (shadows on; the page may turn shadows off on Low).
- `DEF='Env'` the `EnvironmentLight` if used; `DEF='Sky'` the `Background`; `DEF='Haze'` the `Fog`.
- `DEF='ChaseCam'` a `Viewpoint` the page drives every frame; `DEF='Nav'` a `NavigationInfo` with `type '"NONE"'` and `transitionType '"TELEPORT"'`.
- `DEF='TrackCam0'..'TrackCamN'` trackside `Viewpoint`s for the director and replays (8–16 per track, placed at good corners, each with a `description`).
- `DEF='Lamps'` group of night lamps (night tracks): the page dims or brightens them.
- `DEF='Rain'` an optional `Transform` the page fills with a rain `ParticleSystem` when wet.

## 5. Car files (`cars/<id>.x3d`)

Each car file is a complete X3D 4.0 scene whose root is `DEF='Car'` Transform containing:

- `DEF='Body'` Transform (the page applies roll and pitch here, pivot at the centre of mass).
- `DEF='WheelFL' 'WheelFR' 'WheelRL' 'WheelRR'` Transforms at the hub positions (the page sets steer rotation on the front pair and the suspension height on all four), each containing `DEF='SpinFL'` etc. (the page sets wheel spin about +X).
- `DEF='Paint'` the body `PhysicalMaterial` (the page sets livery colour), `DEF='BrakeGlow'` the tail-light `Material`/`PhysicalMaterial` (page drives emissiveColor), `DEF='HeadGlow'`, `DEF='ReverseGlow'`.
- Exhaust tip positions as `MetadataDouble name='exhaust' value='x y z x y z'` on the Car Transform; wheel hub positions, radius and track in `MetadataDouble name='hubs'` and `name='wheelRadius'`.

`cars/MANIFEST.json` lists each car with its sim id and file.

## 6. Sim API (`engine/sim.js`)

```js
export const ENGINE_VERSION = 'kansei-engine/4';
export const HZ = 120;
export function parseTrack(x3dText) -> track          // engine/x3d.js + engine/track.js
export function createSim({ track, mode, surface, laps, entrants }) -> sim
  // entrants: [{ car: 'ronin', tune: {...}, driver: 'player' | 'ai', skill: 0..1, slot: 0..5 }]
  // mode: 'free' | 'rush' | 'attack' | 'race' | 'tandem'
export function step(sim, inputs)                     // inputs: array of packed Input (one per player entrant), advances one tick
export function hashSim(sim) -> '16 hex chars'        // over every car's full state, race state and props, fixed order
export function packInput({ steer, throttle, brake, handbrake, boost, shiftUp, shiftDown, reset }) -> uint32
export function unpackInput(u32) -> {...}
```

Input packing: bits 0–7 steer + 128 (0..255), 8–11 throttle 0..15, 12–15 brake 0..15, 16 handbrake, 17 boost, 18 shiftUp, 19 shiftDown, 20 reset-to-track. Analog pads are quantised by the page before the sim sees them.

`sim.cars[i]` (read-only to the page) carries at least: `x y z yaw pitch roll vx vz yawRate speed (m/s) forwardSpeed slip (body slip angle, rad, signed) drifting rpm gear boost (0..1) steerAngle onRoad offTrack collided (impulse this tick) lap progress (0..1 of lap) distance (m)`, and `wheels[4]` (FL FR RL RR) each with `spin` (accumulated rad) `steer` `slipAngle` `slipRatio` `load` (N) `temp` (°C) `grip` (used fraction 0..1) `surface` `skid` (0..1, how much to draw a mark) `smoke` (0..1) `susp` (m, visual suspension offset) and `lights {brake, reverse, head}` `backfire` (tick when a pop happened) `shiftTick`.

`sim.race` carries: `mode phase ('grid'|'countdown'|'running'|'finished') tick countdown laps lapTimes[] sectors[] bestLap valid checkpoint nextCheckpoint score chain multiplier grace banked bestChain zone (active zone state) positions[] finishOrder[] tandem {distance, angleMatch, score} results` and an `events` array **cleared at the start of each step** with objects `{type, car, ...}` for: `countdown go checkpoint sector lap lapInvalid finish chainStart chainBank chainLost zoneClip zonePerfect transition crash cone shift backfire boostEmpty medal overtake`.

Determinism test: two sims created with the same args and fed the same inputs give the same `hashSim` every tick.

## 7. Vehicle model (what "pro" means here)

Planar rigid body (x, z, yaw, vx, vz, yawRate) on the track surface; y, pitch and roll come from the track height and bank under the car plus quasi-static load transfer (visual body roll/pitch from lateral and longitudinal acceleration, spring-damper filtered).

- Four contacts FL FR RL RR, Ackermann front steer, speed-sensitive lock, extra countersteer range.
- Normal loads: static weight split by CG position, plus longitudinal and lateral load transfer from last tick's accelerations (m a h / L, m a h / T), plus banking and grade components of gravity; clamp so every wheel keeps ≥ 5% load and the sum equals m g cosθ.
- Tyre: slip angle from contact-patch velocity; slip ratio from wheel angular speed (each wheel has its own spin state with inertia, driven by drive and brake torque); combined force by a friction-ellipse brush or simplified Pacejka (B C D E per car) with load sensitivity (μ falls as load rises) and temperature (grip peaks near 85–95 °C, heats with slip power, cools with speed). Fx² + Fy² ≤ (μ Fz)².
- Drivetrain: torque curve per car, 6-speed gearbox (auto with rev-matched downshifts, or manual), final drive, clutch slip at launch, rev limiter with fuel cut that produces `backfire` events, lift-off backfire pops, turbo spool on turbo cars (a `boostPressure` 0..1 field for the page's whistle and flutter sound), limited-slip diff on RWD (tunable lock), AWD torque split.
- Handbrake locks the rear wheels (huge rear slip ratio, rear lateral grip falls): the classic entry.
- Boost (nitrous): finite reserve, +35% torque, recharges slowly while not used and faster while drifting (drift earns boost, a reward loop).
- Aerodynamic drag ½ρCdA v², rolling resistance, downforce small.
- Assists (all tunable 0..1): **Stability** (ESC-like yaw damping that never prevents a held drift above 0.5), **Drift assist** (adds countersteer toward the velocity vector when the player is not countersteering, keyboard-friendly), **Traction** (cuts throttle when rear slip ratio is large, off by default for RWD drift cars).
- Tune per car: `grip steerLock finalDrive brakeBias diffLock balance (front/rear grip split) stability driftAssist traction gearbox ('auto'|'manual')`.

Cars (fictional; numbers are game-tuned):

| id | Name | Drive | Power / Torque | Mass | Character |
|---|---|---|---|---|---|
| `koi` | KOI | RWD, NA | 210 hp / 230 N·m | 1020 kg | light, flickable, teaches you to drift |
| `ronin` | RONIN | RWD, turbo | 380 hp / 470 N·m | 1290 kg | balanced default |
| `tempest` | TEMPEST | AWD, turbo | 520 hp / 620 N·m | 1480 kg | grip monster, fastest lap times |
| `banshee` | BANSHEE | RWD, V8 | 690 hp / 780 N·m | 1420 kg | pro drift, unlocked by stars |

Handling card windows (tests/handling.test.mjs measures each; docs/HANDLING-CARD.md records them):

| Measure | KOI | RONIN | TEMPEST | BANSHEE |
|---|---|---|---|---|
| 0–100 km/h dry (s) | 7.0–9.0 | 4.8–6.2 | 3.3–4.3 | 3.8–5.0 |
| Top speed (km/h) | 185–215 | 230–265 | 245–280 | 275–315 |
| 100–0 km/h dry (m) | 33–42 | 33–42 | 32–40 | 33–42 |
| Steady skidpad dry (g) | 0.90–1.10 | 0.92–1.12 | 1.00–1.20 | 0.90–1.12 |
| Wet skidpad / dry | 0.62–0.80 | same | same | same |
| Held drift 25–50° for ≥ 4 s by a simple closed-loop controller | yes | yes | yes (harder, needs handbrake) | yes |

## 8. Modes and scoring (`engine/race.js`)

- **Free roam**: open session, drift scoring live, no clock.
- **Drift Rush**: 90 s from the first roll. Drift points per tick = angleFactor × speedFactor × multiplier, where drifting means body slip ≥ 12°, speed ≥ 25 km/h, moving forward along the track (progress increasing) and at most 2 wheels off the asphalt. Chain grace 2.0 s; multiplier grows +0.5 every 2 s of continuous drift and +1 on a clean transition, max ×6. A transition counts when the slide changes sides within 1.0 s, the old side held ≥ 20° for ≥ 0.35 s while the car's course turned ≥ 15°, the new side reaches 20°, and the last transition was ≥ 1.2 s ago (a wobble down a straight is not a transition; `tests/exploits.test.mjs`). Wall contact over a threshold, or a reset, loses the pending chain (`chainLost`); banked points stay. **Clipping zones**: drifting with the car's rear within 2.0 m of the zone's edge gives `zoneClip` (×2 points while inside), within 1.0 m and slip ≥ 35° gives `zonePerfect` (×3). Knocking a cone costs 250 points. Medals from `targets` (Bronze, Silver, Gold, Platinum), which are written for a stock RONIN on the dry and scaled per run by `engine/race.js medalTargets(base, car, grip, surface)`: per-car pace (lap × KOI 1.04, TEMPEST 0.957, BANSHEE 0.974; rush × KOI 0.85, TEMPEST 0.35, BANSHEE 1.4), the wet (lap × 1.16, rush × 1.3) and the grip tune (lap ≈ grip^-0.45, rush ≈ grip^-1.5). `sim.race.targets` holds the run's targets.
- **Time Attack**: 1, 3 or 5 laps, or until stopped (∞); checkpoints in order and forward; a lap is invalid if any wheel set (≥ 3 wheels) spends more than 1.0 s beyond halfWidth + 1.2, or if the car resets (a reset voids the lap in Race too); three sectors with split deltas; the best valid lap's tape for the same car and surface is the ghost (the page re-simulates it in a second sim, it never collides; a setup toggle turns it off).
- **Race**: player plus 3 AI on the 6-slot grid, 3 laps (configurable), countdown 3 s with lights, car-to-car contact (oriented boxes or two-circle approximation with impulses), positions by laps + progress, finish order, `overtake` events.
- **Tandem**: an AI lead car drifts the circuit (AI drift mode); the player chases. Per tick, while both drift: proximity score (best at 1.5–4 m behind, nothing beyond 12 m), angle match (|slip_p − slip_lead|), line match (lateral offset difference), contact penalty. Two laps. Grades D C B A S.

## 9. AI drivers (`engine/ai.js`, sim side, deterministic)

- Racing line: per sample, a lateral offset toward the inside of curves, computed once from track curvature (smoothed), clamped inside the asphalt.
- Speed profile: v_max(i) = sqrt(μ g / |κ|) clipped to the car's top speed, then a backward pass for braking (a_brake) and a forward pass for acceleration.
- Steering: pure pursuit to a lookahead point (lookahead grows with speed) on the racing line; throttle and brake from the speed error.
- Skill 0..1 scales the speed profile (0.88..1.0) and adds deterministic line noise (from the tick and car index through an integer hash, never Math.random).
- **Drift mode** (tandem lead and the bots that record drift tapes): enters corners with a handbrake or feint (Scandinavian flick), holds a target body slip (30–40°) with a PD controller on countersteer and throttle, exits by easing off. It must survive every track without crashing (tests prove it).
- AI never reads player input; it sees the sim state only.

## 10. Tapes and the Loom

`engine/tape.js`: schema `kansei.tape/1`, `{ level, level_sha256, engine, hz, ticks, mode, car, tune, surface, entrants, rle: [[u32, count], ...], expect: { hash, state, lapTime?, score? } }`. `tools/bot.mjs` drives the player entrant with the AI (race line for Time Attack, drift mode for Drift Rush) and records tapes; `tools/replay.mjs <tape>` replays headless and prints one JSON line with at least `level_sha256 engine state hash frame` where `state` is `"won"` when the recorded goal is met (a valid lap for attack tapes; a medal at or above the tape's stated medal for rush tapes; the finish for race and tandem; the last tick for free). The rule lives in `engine/goal.js`, shared by the runner, the bot, the page's witness mode and the tapes the page saves. The Loom's `kit/loom play` runs that runner on every tape twice.

Per track: one Time Attack tape (a valid lap) and one Drift Rush tape (Gold or better). The bot's lap and rush score set the track's `targets` (except the Practice Pad's rush tiers, which come from the keyboard driver in `tests/keyboard.test.mjs`, since the bot's near-perfect circle is no measure of a person) (gold lap = bot lap × 1.02, silver × 1.08, bronze × 1.16; rush gold = bot score × 0.85, platinum = bot score × 1.1 …) so medals are honest. Race and Tandem tapes (`--mode race|tandem`) have the finish line as their goal: they prove the AI field replays from the player's inputs alone.

## 11. Page (`index.html`, `main.js`, picture files)

- Boot: load `levels/MANIFEST.json`, `cars/MANIFEST.json`; X_ITE `x3d-canvas` with `splashScreen='false' contextMenu='false' notifications='false' timings='false'`; the menu backdrop is the garage scene (`garage.x3d`, a turntable showroom).
- Menus: title → mode → car (turntable, stats bars, livery picker with 6 colours) → track (card with minimap and medals) → setup (tune sliders, assists, gearbox, surface dry/wet, laps, AI skill, quality Low/Medium/High) → start. Career strip: stars per event, unlock BANSHEE at 12 stars.
- Fixed-step loop: accumulator at 120 Hz, at most 12 steps per frame, dropped steps counted; the picture interpolates position and shortest-arc yaw.
- HUD: speed (km/h), tach arc with shift light, gear, boost bar, drift score popup (chain, multiplier, zone CLIP/PERFECT flashes, transition flashes), banked score, timer, lap and sector deltas (green/red/purple), position in race, tandem proximity meter, minimap (SVG from the centreline with cars, next checkpoint, zones), F2 telemetry (FPS, frame ms, P95, physics ms, steps, dropped, tyre loads/temps/slip, lateral and longitudinal G).
- Cameras (C cycles): chase (drift-aware: swings to frame the slide), close chase, bumper, hood, orbit (drag + wheel), director (trackside `TrackCam*`), plus photo mode (F: freeze, free orbit, exposure and FOV sliders, hide HUD).
- FX: tyre smoke (pooled billboards or X3D `ParticleSystem` with a moving emitter), skid marks (ring-buffer `IndexedTriangleSet`), sparks on wall hits, backfire flames at the exhaust, boost flame, brake-light glow, headlights at night, rain particles and a wet-road look when wet, camera shake on impacts, speed FOV kick.
- Replays: after a session, Replay re-simulates the recorded inputs with director cameras, slow motion, free scrub; Save Tape shows the tape JSON in a copy box (artifact pages block downloads), and stores the best tapes in localStorage.
- Audio (WebAudio, synthesised, no files): engine (harmonic stack following rpm and load, with a separate intake/exhaust character per car), turbo whistle and blow-off flutter, backfire pops, tyre squeal (filtered noise by slip and load), surface rumble, wind, shift clunk, impacts, cone hits, UI ticks, countdown beeps, and a little synth music loop per track with a volume slider.
- Input: keyboard (WASD/arrows, Space handbrake, Shift boost, Q/E shift in manual, C camera, F photo, R reset to track, Esc pause, M mute, F2 telemetry), standard gamepad (triggers, stick, A handbrake, B boost, bumpers shift, Y camera, Start pause), touch (left/right steer pads or tilt-free slider, gas, brake, handbrake, boost).
- Pause stops the sim clock; window blur pauses.
- `window.KANSEI` exposes a test hook: `{ state(), start(opts), replay(tape) }` for tools.

## 12. Public-repo rules

The repo is public. No keys, cloud project ids, account identities, costs, private links, AI vendor or model names in any file. Commits are made by the coordinator, not by builders.
