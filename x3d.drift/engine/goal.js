// loom:sim
// One goal rule for every tape (CONTRACT.md section 10), shared by tools/replay.mjs, tools/bot.mjs,
// the page's witness mode and the tapes the page saves, so a tape a player exports passes the same
// check as a bot's: attack = a valid lap; rush = the stated medal or better at the finish;
// race and tandem = the finish line; free = the tape's last tick.
import { medalRank } from './race.js';

/** True once the goal of a `mode` tape is met (call after each step; `last` = this was the last word). */
export function goalReached(sim, mode, want, last) {
  const r = sim.race;
  if (mode === 'attack') return r.lapTimes.some(l => l.valid);
  if (mode === 'rush') return r.phase === 'finished' && medalRank(r.medal) >= medalRank(want || 'gold');
  if (mode === 'race' || mode === 'tandem') return r.phase === 'finished';
  return !!last;
}

/** won / lost / unfinished from the goal tick (-1 = never met) and the final sim. */
export function goalState(goalTick, sim) {
  return goalTick >= 0 ? 'won' : sim.race.phase === 'finished' ? 'lost' : 'unfinished';
}

/** The medal a page tape states: the one it reached, or bronze when it reached none. */
export function statedMedal(sim) { return sim.race.medal !== 'none' ? sim.race.medal : 'bronze'; }
