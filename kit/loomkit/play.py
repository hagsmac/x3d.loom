"""Play witness: is every playable level proven beatable by a recorded run, bound to its exact bytes?

New on 6 Nov 2026, from x3d.platformer (NIB). An interactive world makes a claim a scene file cannot
show: "this can be played and finished". Grammar, Meaning and Traps read the file; Behaviour shows it
loads. None of them notices a level that cannot be beaten, or an engine change that makes yesterday's
run diverge. The proof of play is a tape: the input bits of every fixed tick, bound to the sha256 of the
level bytes and to the engine version, with the outcome it produced (goal reached, state hash).

For each tape the witness runs the project's own headless replay runner (any program that prints one
JSON object per tape) `repeats` times and checks, in this order, each with a stable code (law 19):

  PLAY_LEVEL_STALE        the level file's sha256 is not the one the tape was recorded on (law 17)
  PLAY_ENGINE_DRIFT       the runner's engine version is not the tape's
  PLAY_NONDETERMINISTIC   two replays of the same tape ended in different state hashes
  PLAY_GOAL_NOT_REACHED   the replay did not finish the level
  PLAY_HASH_DRIFT         it finished, but not in the state the tape recorded
  PLAY_LEVEL_UNPROVEN     a listed level has no tape at all
  PLAY_NO_TAPES           nothing to judge (a pass over nothing is not a pass, law 36)

A runner that crashes, times out or prints no JSON is an instrument error (exit 2), never a fail.
Standard library only; every gate raises (no assert), so it holds under python -O (law 18).
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from .core import InstrumentError, need

RUNNER_KEYS = ("level_sha256", "engine", "state", "hash", "frame")


def run_tape(node: str, runner: Path, tape: Path, timeout: int = 600) -> dict:
    try:
        p = subprocess.run([node, str(runner), str(tape)], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise InstrumentError(f"replay runner timed out after {timeout} s on {tape.name}") from None
    except FileNotFoundError as e:
        raise InstrumentError(f"cannot start the replay runner: {e}") from None
    if p.returncode != 0:
        raise InstrumentError(f"replay runner exited {p.returncode} on {tape.name}: {p.stderr[-600:]}")
    lines = [x for x in p.stdout.strip().splitlines() if x.strip()]
    try:
        out = json.loads(lines[-1])
    except (IndexError, json.JSONDecodeError):
        raise InstrumentError(f"replay runner printed no JSON for {tape.name}: {p.stdout[-300:]!r}") from None
    missing = [k for k in RUNNER_KEYS if k not in out]
    if missing:
        raise InstrumentError(f"replay runner output for {tape.name} lacks {missing}")
    return out


def check(tapes: list[Path], levels: list[Path], runner: Path, node: str = "node", repeats: int = 2) -> dict:
    """Return per-tape measurements; raise GateError on the first broken contract."""
    need(tapes, "PLAY_NO_TAPES", "no tape matched")
    need(repeats >= 2, "PLAY_REPEATS_TOO_FEW", f"repeats={repeats}: determinism needs at least two replays")
    by_name = {p.name: p for p in levels}
    proven, rows = set(), {}
    for t in tapes:
        try:
            tj = json.loads(t.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise InstrumentError(f"tape {t.name} is not JSON: {e}") from None
        level = by_name.get(tj.get("level", ""))
        need(level is not None, "PLAY_LEVEL_MISSING", f"{t.name} names {tj.get('level')!r}, not among the listed levels")
        actual = hashlib.sha256(level.read_bytes()).hexdigest()
        need(actual == tj.get("level_sha256"), "PLAY_LEVEL_STALE",
             f"{t.name}: recorded on {str(tj.get('level_sha256'))[:12]}, level is now {actual[:12]}")
        runs = [run_tape(node, runner, t) for _ in range(repeats)]
        r = runs[0]
        need(r["level_sha256"] == actual, "PLAY_LEVEL_STALE", f"{t.name}: the runner read {r['level_sha256'][:12]}, the file is {actual[:12]}")
        need(r["engine"] == tj.get("engine"), "PLAY_ENGINE_DRIFT", f"{t.name}: tape {tj.get('engine')!r}, runner {r['engine']!r}")
        hashes = sorted({x["hash"] for x in runs})
        need(len(hashes) == 1, "PLAY_NONDETERMINISTIC", f"{t.name}: {len(runs)} replays gave {hashes}")
        need(r["state"] == "won", "PLAY_GOAL_NOT_REACHED", f"{t.name}: replay ended in state {r['state']!r} at tick {r['frame']}")
        expect = (tj.get("expect") or {}).get("hash")
        need(r["hash"] == expect, "PLAY_HASH_DRIFT", f"{t.name}: replay hash {r['hash']}, tape expects {expect}")
        proven.add(level.name)
        rows[t.name] = {"level": level.name, "level_sha256": actual, "engine": r["engine"], "ticks": tj.get("ticks"),
                        "goal_tick": r.get("goal_tick"), "hash": r["hash"], "replays": len(runs),
                        "cogs": r.get("cogs"), "stars": r.get("stars"), "deaths": r.get("deaths"),
                        "runner_cpu_ms": [x.get("cpu_ms") for x in runs], "runtime": r.get("node")}
    unproven = sorted(set(by_name) - proven)
    need(not unproven, "PLAY_LEVEL_UNPROVEN", ", ".join(unproven))
    return {"tapes": rows, "levels_proven": sorted(proven), "repeats": repeats}
