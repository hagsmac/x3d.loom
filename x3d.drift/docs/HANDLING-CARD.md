# KANSEI handling card

Measured by `node tests/handling.test.mjs` on the fixture tracks in `tests/fixtures/`. The test fails if any number leaves its window (CONTRACT.md section 7). The figures below come from the run that produced this file. The sim is deterministic, so a rerun on the same engine prints the same figures.

| Measure | KOI | RONIN | TEMPEST | BANSHEE |
|---|---|---|---|---|
| 0–100 km/h dry, launch (Traction 1) | **7.42 s** (7.0–9.0) | **5.38 s** (4.8–6.2) | **3.79 s** (3.3–4.3) | **4.49 s** (3.8–5.0) |
| 0–100 km/h, shipped tune (Traction off on the RWD cars) | 7.42 s | 5.97 s | 3.85 s | 5.10 s |
| Top speed | **208.8 km/h** (185–215) | **252.9 km/h** (230–265) | **266.4 km/h** (245–280) | **299.9 km/h** (275–315) |
| 100–0 km/h dry | **39.0 m** (33–42) | **36.6 m** (33–42) | **33.0 m** (32–40) | **34.5 m** (33–42) |
| 100–0 km/h wet | 52.3 m | 49.5 m | 50.4 m | 48.0 m |
| Steady skidpad dry, left / right | **0.989 / 0.989 g** (0.90–1.10) | **1.011 / 1.011 g** (0.92–1.12) | **1.078 / 1.077 g** (1.00–1.20) | **1.013 / 1.013 g** (0.90–1.12) |
| Wet skidpad | 0.709 g, ratio **0.717** | 0.749 g, ratio **0.740** | 0.810 g, ratio **0.751** | 0.749 g, ratio **0.740** |
| Held drift 25–50°, AI drift mode on the skidpad | **34.4 s**, mean 36° | **35.1 s**, mean 36° | **13.3 s**, mean 33° (drift setup) | **36.0 s**, mean 36° |

Windows are in brackets. Every row passes. The checks also cover:

- **Left/right symmetry:** the skidpad left against right (within 0.03%), and a mirrored step-steer plus handbrake flick at 70 km/h. Peak yaw rate and peak slip match within 1e-12 for every car. The window is 2%.
- **Load conservation:** the four wheel loads sum to m g cos(θ) plus downforce every tick, on the banked oval and the twisty fixture with grade. The worst relative error is 4e-16. The lightest wheel never drops below the 5% floor.
- **Character order:** acceleration rises KOI < RONIN < BANSHEE < TEMPEST. Top speed rises KOI < RONIN < TEMPEST < BANSHEE. TEMPEST has the most grip.

## Race AI lap times

These are from `tests/race.test.mjs`: the second of two Time Attack laps by the race-line AI at skill 1. Every lap is valid with no wall contact.

| Track | KOI | RONIN | TEMPEST | BANSHEE |
|---|---|---|---|---|
| fixture skidpad | 14.69 | 14.47 | **13.89** | 14.54 |
| fixture oval | 41.29 | 39.21 | 37.77 | **37.70** |
| fixture twisty | 59.85 | 56.36 | **53.67** | 54.66 |
| Kessel Pass | 82.1 | 78.7 | **74.9** | 76.2 |
| Neon Overpass | 80.8 | 77.3 | **74.3** | 74.4 |
| Salt Ring | 50.7 | 48.9 | **46.6** | 47.5 |
| Cliffside | 89.3 | 84.9 | **81.3** | 81.6 |
| Practice Pad | 14.5 | 14.3 | **13.8** | 14.4 |

TEMPEST has the fastest lap everywhere except the power oval, where BANSHEE's extra 170 hp is worth 0.07 s.

## How each number is measured

- **0–100 km/h:** a standing start on the 3 km straight of the strip fixture, full throttle, auto gearbox. A plain lane-keeping steering law holds the car straight.
  - The card value uses Traction 1, which acts as launch control. The RWD cars ship with Traction 0 so the throttle can break the rear loose, and the second row shows that tune.
  - The clutch slips up to each car's launch rpm, so these are clutch launches.
- **Top speed:** two rolling starts on the same straight, one below the window and one above it, each run flat out for 3 km. They converge to within 1.2 km/h of each other, and the card value is their mean, which is the drag-limited equilibrium.
- **100–0 km/h:** steady 100 km/h, then the full brake pedal. ABS is always on: it caps each wheel's brake torque at what the tyre can return, given the lateral grip already in use.
- **Skidpad:** a circle of 60 m radius. Speed creeps up 0.2 m/s every second while a pure-pursuit driver holds the circle. The value is the best 2 s mean of v²/r while the car still holds the radius within 2 m with under 5.7° of body slip.
  - Wet uses the same circle and the wet surface.
- **Held drift:** the AI drift mode (`engine/ai.js`) drives the skidpad for 40 s. The value is the longest unbroken stretch with body slip between 25° and 50° at more than 25 km/h, with no wall hits and no resets.
  - The controller uses three feedback loops: yaw rate on the steering, path curvature on the throttle, and slip angle through the yaw-rate target.
  - TEMPEST runs `DRIFT_SETUPS.tempest` from `engine/cars.js`: Traction 0, Stability 0, front split 0.2 and balance 0.8. On its shipped grip setup it holds 0.85 s before the AWD pulls it straight. A drift-mode AI entrant given no tune uses its car's drift setup.
  - The drift AI aims for 42° on the RWD cars and 37° on the AWD car (`DRIFT.awdBeta`): driven front wheels pull an AWD slide straight, so it is held shallower. The line trim takes a few degrees back, which is why the means sit at 33–36°.

## Tuning rationale

- **KOI (light FR, naturally aspirated).** This is the car you learn to slide in.
  - The peaky torque curve gives slow, readable power. Its launch is power-limited, so Traction changes nothing.
  - Low rear grip, a soft slide plateau (0.72 of peak) and a 0.54 front balance let it rotate on lift-off or the handbrake at low speed.
  - A 380 N·m clutch cap and an ignition cut on upshifts stop shifts from kicking the rear out unasked.
- **RONIN (turbo FR, the default).** It is balanced.
  - The turbo's 0.5 s lag means the throttle loosens the rear a beat after you ask, a timing skill to learn.
  - The 0.6 diff lock keeps both rear wheels spinning together once the slide starts. Its 1.01 g skidpad sits in the middle of the field.
- **TEMPEST (AWD twin-turbo).** It grips.
  - It has the best skidpad (1.08 g), the shortest stops and the fastest laps.
  - The centre coupling sends 34% of the torque forward with a viscous lock, so power pulls the car straight. To slide it, the player dials in the drift setup and commits with the handbrake ("harder, needs handbrake").
- **BANSHEE (big-block V8 FR).** It is the pro car.
  - It has 780 N·m from low rpm, the stiffest diff (150 N·m preload, 0.6 power ramp) and the highest slide plateau (0.81), so it holds big angles at speed. It gets the highest drift scores on every circuit.
  - Without Traction, a careless foot costs 0.6 s to 100 km/h.
  - Its high drag (CdA 1.22) caps it at about 300 km/h.
- **Wet:** grip is ×0.72 on asphalt and curbs. Measured skidpad ratios are 0.72–0.75, and braking distances grow by 30–50%.
  - The AI reads the surface. Its speed profiles use the wet grip, and the drift controller shrinks its yaw-braking and lateral-stopping budgets by the same factor and aims 8° shallower. On the wet the race AI laps the five circuits 14–18% slower than on the dry (RONIN: Kessel 91.9, Neon 88.2, Salt 57.6, Cliffside 97.9, Pad 16.8 s), every lap valid, with no wall contact, so wet Time Attack targets are the dry ones × 1.16 (`engine/race.js medalTargets`). As the Tandem lead every car drifts two wet laps of every circuit with no wall contact (`tests/circuits.test.mjs`).
  - Wet Drift Rush tends to score more: slides start more easily and the slower speeds give more time. Over every car and circuit the drift AI's wet scores average 1.11× its dry ones (geometric mean, `kansei-engine/4`), RONIN on the four circuits 1.30× (29978 / 38803 / 21429 / 13319 wet against 10435 / 28070 / 35666 / 11170 dry, Kessel / Neon / Salt / Cliffside) and the keyboard driver 1.36× on the Pad. Wet rush targets are the dry ones × 1.3, so in total the AI's wet medals are no better than its dry ones (`tests/exploits.test.mjs`); on Kessel alone the wet is still easier for it.
- **Boost:** +35% torque, a finite reserve, drained in about 5 s. It recharges slowly off the button and about four times faster while drifting.

## Performance

Six cars at 120 Hz cost 34–43 µs per tick in Node 22, so a simulated second costs 4–5 ms. This is the `performance` check in `tests/race.test.mjs`, with all six cars AI-driven (four racing, two drifting) on the twisty fixture. The budget is 1 ms per tick.

## A keyboard player can drift every car

`node tests/keyboard.test.mjs` drives each car with keys only: steer −127 / 0 / +127, throttle off or full, and a handbrake tap. It decides every 10 ticks (a key held at least about 80 ms) on the slide angle a quarter second ahead. It flicks in with the handbrake, holds the gas, taps into the corner when the angle fades, taps out and lifts when the angle grows too far, and lifts when the car runs wide. The run is a 95 s Drift Rush on the Practice Pad with each car's shipped assists.

| | KOI | RONIN | TEMPEST | BANSHEE |
|---|---|---|---|---|
| Dry: time drifting, mean angle | 63%, 25.3° | 65%, 26.4° | 46%, 21.8° | 72%, 30.9° |
| Dry: spins, wall hits, steer presses per second | 0, 0, 1.7 | 0, 0, 1.7 | 0, 0, 0.7 | 0, 0, 1.4 |
| Wet: time drifting, mean angle | 79%, 29.0° | 80%, 30.8° | 51%, 23.9° | 76%, 31.6° |
| Wet: spins, wall hits | 0, 0 | 0, 0 | 0, 0 | 0, 0 |

- Every car can be drifted from a keyboard, on the dry and the wet, with no spin and no wall hit. TEMPEST, the grip car with Traction and Stability on, slides for less of the run and at a shallower angle.
- **Assists work.** With Stability and Drift assist off, BANSHEE spins 5 times in the same run (mean angle 34.5°); with its shipped assists it does not spin. With both at 1, every car holds a shallower angle (KOI 22.5°, BANSHEE 27.1°).
- The cars feel different from the keys: KOI and RONIN hold 25–26°, BANSHEE holds 31° and carries the most speed, and TEMPEST needs the handbrake and still slides least.

## The AI on the shipped circuits

`node tests/circuits.test.mjs` (70 checks, about 22 s) proves on all five circuits:

- **Race-line AI**, every car: at skill 1 both Time Attack laps are valid with no wall contact; at skill 0.5 they are also clean and 2.8–5.6% slower (the lap-time table above is skill 1).
- **Drift AI as the Tandem lead**, every car, two laps, dry and wet: no wall contact and no reset anywhere. On the dry its held slides average 31–36° on the RWD cars and 28.4–30.6° on TEMPEST:

| Held slide, mean (dry) | KOI | RONIN | TEMPEST | BANSHEE |
|---|---|---|---|---|
| Kessel Pass | 31.9° | 31.1° | 28.6° | 34.1° |
| Neon Overpass | 31.3° | 33.2° | 28.4° | 33.1° |
| Salt Ring | 31.7° | 32.1° | 28.8° | 33.3° |
| Cliffside | 32.1° | 32.2° | 28.9° | 33.9° |
| Practice Pad | 35.9° | 35.6° | 30.6° | 35.6° |

- **Races** (three laps, the player entrant driven by the race AI at skill 0.9 as a stand-in): three RONINs at skill 1.0, 0.75 and 0.5 finish within 2.7–6.6% of each other with the skill-1 car ahead of the skill-0.5 car, nobody touches in the first 15 s, and nobody hits a wall. The default grid (TEMPEST, BANSHEE, KOI against the player's RONIN) also finishes with no contact off the start.
- The race AI keeps its grid lane into the first corner, then merges onto the line. It passes a slower car where the road runs straight, committed to one side with a car's width of air, and follows when there is no room. A pass already half alongside carries on into the bend. Off the line on the inside of a bend it slows for the tighter radius.

## Proof of play and medal targets

The medal targets in `build/build_world.py` come from the bot (`node tools/bot.mjs levels/<id>.x3d`): RONIN, dry, skill 1, two Time Attack laps (the best valid one counts) and one 90 s Drift Rush. Gold lap = bot lap × 1.02, silver × 1.08, bronze × 1.16; rush bronze = bot score × 0.35, silver × 0.6, gold × 0.85, platinum × 1.1. The Practice Pad's rush tiers are the exception: the bot drives a near-perfect circle (177268), the keyboard driver of `tests/keyboard.test.mjs` scores 55–70k with the RWD cars, so its tiers are 25k / 45k / 70k / 120k.

The targets are for a stock RONIN on the dry. Each run's targets (`sim.race.targets`, from `engine/race.js medalTargets`) are scaled by the pace the bots measured against RONIN over the five circuits (geometric means): lap × 1.04 KOI, 0.957 TEMPEST, 0.974 BANSHEE; rush × 0.85 KOI, 0.35 TEMPEST, 1.4 BANSHEE; wet lap × 1.16, wet rush × 1.3; grip tune lap ≈ grip^-0.45 and rush ≈ grip^-1.5 (grip 1.2 laps 7.8% faster, 0.8 laps 10.7% slower; no other tune key moves the AI's lap by more than 0.4%, balance excepted, which only slows it). With that, the race-line AI beats no car's or grip tune's gold on Kessel Pass by more than 2.8% (`tests/exploits.test.mjs`).

Transitions: +1 to the multiplier only when the slide changes sides within 1 s, the old side held at least 20° for 0.35 s while the car's course turned 15°, the new side reaches 20°, and 1.2 s have passed since the last one. Before `kansei-engine/4` a 12° wobble counted; a weaving road-follower reached gold on Salt Ring (32433) and bronze on Kessel. Now no scripted wobble, spinner, weaver or wall-leaner earns a medal on Salt Ring, Kessel Pass or the Pad, and a straight-line wobble never passes ×2 (`tests/exploits.test.mjs`). The bot's real transitions still count, and its scores barely moved. In a Drift Rush the bot links corners: when a bend ends with another within 160 m it keeps a 22° slide down the straight so the chain lives (dry Drift Rush only).

| Circuit | Bot lap | Gold / silver / bronze lap | Bot rush | Bronze / silver / gold / platinum |
|---|---|---|---|---|
| Kessel Pass | 78.745 s | 80.3 / 85.0 / 91.3 | 10435 | 3650 / 6250 / 8850 / 11500 |
| Neon Overpass | 77.277 s | 78.8 / 83.5 / 89.6 | 28070 | 9800 / 16850 / 23850 / 30900 |
| Salt Ring | 48.864 s | 49.8 / 52.8 / 56.7 | 35666 | 12500 / 21400 / 30300 / 39250 |
| Cliffside | 84.886 s | 86.6 / 91.7 / 98.5 | 11170 | 3900 / 6700 / 9500 / 12300 |
| Practice Pad | 14.317 s | 14.6 / 15.5 / 16.6 | 177268 (keyboard 61k) | 25000 / 45000 / 70000 / 120000 |

The ten tapes in `tapes/` are those runs (`<id>-attack.tape.json`, `<id>-rush.tape.json`). Each replays as won with its recorded hash (`node tools/replay.mjs <tape>`), twice in a row, and under `kit/loom play`.

Two more tapes prove the modes with AI cars: `salt-ring-race.tape.json` (RONIN by the race-line AI from the back of the default four-car grid, two laps; it finishes third behind TEMPEST and BANSHEE) and `salt-ring-tandem.tape.json` (RONIN by the drift AI chasing the drift-AI lead, throttle held back inside 6 m; two contacts, grade D, because the sim has no chase AI yet). Their goal is the finish line. `node tools/bot.mjs levels/salt-ring.x3d --mode race --laps 2` and `--mode tandem` record them. All eighteen tapes (twelve here, six fixture tapes) were re-recorded by the bot under `kansei-engine/4`: the transition rule, the medal scaling, the deep-overlap car contact, a reset that never lands on another car (and voids a Race lap) and a state hash that now covers every AI field changed the hashes.
