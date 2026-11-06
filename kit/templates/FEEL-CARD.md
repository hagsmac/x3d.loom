# Feel card (template)

For any interactive world whose controls must feel right. Write the windows **before** tuning, measure them in a dedicated level with a fixed tick, and run the measurement as the `feel` witness (`kit/loom command PROJECT --evidence RUN/evidence --name feel -- node tests/feel.test.mjs`). Exit 0 only when every number is inside its window. Grade the windows honestly: chosen from practice is L; confirmed by playtests is C.

| Quantity | Why it matters | Window | How it is measured | Measured |
|---|---|---|---|---|
| Full jump apex | | | hold jump from rest on flat ground | |
| Tap jump apex | | | one-tick press | |
| Time to apex | | | ticks from take-off to vy ≤ 0 | |
| Running jump distance | | | full speed, held jump, flat ground | |
| Time to full speed | | | from rest, direction held | |
| Stop distance | | | from full speed, release | |
| Coyote time | | | latest tick after leaving a ledge that still jumps | |
| Jump buffer | | | earliest tick before landing that still jumps | |
| (game-specific) | | | | |

Rules: the windows live in code next to the tuning (one source); the measurement level is generated like any other; a level may never ask for more than a window guarantees (a gap wider than the shortest running jump is a bug).
