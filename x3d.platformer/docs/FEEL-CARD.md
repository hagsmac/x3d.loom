# Feel card: Nib

What the controls must feel like, as numbers. `engine/feel.js` holds the tuning (`FEEL`) and the windows (`FEEL_WINDOWS`); `tests/feel.test.mjs` drives Nib in the Feel Lab level (`levels/0-0-feel-lab.x3d`) at the fixed 120 Hz tick and fails if any measurement leaves its window. The windows were set from platformer practice by the builder, not from playtests (grade L for "feels good"; grade C for "the numbers hold").

| Quantity | Why it matters | Window | Measured (engine 2, 6 Nov) |
|---|---|---|---|
| Full jump apex | the height every level is built around | 3.0 to 3.6 m | 3.10 m |
| Tap jump apex | short hops need to be really short (variable jump) | 0.9 to 1.6 m | 1.17 m |
| Time to apex | floaty above 0.5 s, twitchy below 0.36 s | 0.36 to 0.5 s | 0.458 s |
| Running jump distance | the widest gap a level may ask for | 6.0 to 8.2 m | 7.02 m |
| Time to full speed | responsive, but with a sense of weight | 0.08 to 0.16 s | 0.108 s |
| Stop distance from full speed | no ice skating | 0.25 to 0.6 m | 0.33 m |
| Coyote time | a jump just after leaving a ledge still counts | 10 to 14 ticks | 12 |
| Jump buffer | a jump pressed just before landing still counts | 12 to 17 ticks | 14 |
| Wall-jump height gain | a shaft is climbable, but each jump has to be earned | 2.0 to 3.2 m | 2.43 m |

Other tuning that is not windowed yet: apex hang (gravity × 0.55 near the top), fall gravity × 1.7, jump-cut gravity × 2.7, terminal fall 23 m/s, wall slide 3.4 m/s, ground pound hover 0.11 s then 28 m/s, hook range 5.4 m, spring 21.5 m/s (× 1.32 from a pound), hitstop 75 ms.
