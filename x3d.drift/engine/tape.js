// loom:sim
// A tape is a run: the packed Input word (engine/sim.js packInput) of the player entrant for every
// 1/120 s tick, run-length encoded, bound to the sha256 of the level bytes it was recorded on and
// to the engine version. Replaying it through step() must reproduce `expect.hash` exactly.
// Schema kansei.tape/1 (CONTRACT.md section 10):
//   { schema, level, level_sha256, engine, hz, ticks, mode, car, tune, surface, laps, entrants,
//     rle: [[u32, count], ...], expect: { hash, state, frame, lapTime?, score?, medal? }, note }

export const TAPE_SCHEMA = 'kansei.tape/1';

export function encodeTape({ level, level_sha256, engine, hz = 120, mode, car, tune, surface, laps, entrants, words, expect, note }) {
  const rle = [];
  for (let i = 0; i < words.length; i++) {
    const w = words[i] >>> 0;
    const last = rle[rle.length - 1];
    if (last && last[0] === w) last[1]++;
    else rle.push([w, 1]);
  }
  return { schema: TAPE_SCHEMA, level, level_sha256, engine, hz, ticks: words.length, mode, car, tune: tune || {}, surface: surface || 'dry',
    laps: laps || 0, entrants, note: note || '', rle, expect };
}

export function decodeTape(t) {
  if (!t || t.schema !== TAPE_SCHEMA) throw new Error('not a ' + TAPE_SCHEMA + ' tape');
  const words = new Uint32Array(t.ticks);
  let i = 0;
  for (const [w, n] of t.rle) { if (i + n > t.ticks) throw new Error('tape rle overruns its tick count'); words.fill(w >>> 0, i, i + n); i += n; }
  if (i !== t.ticks) throw new Error(`tape length mismatch: rle covers ${i} ticks, header says ${t.ticks}`);
  return { ...t, words };
}

/** Recorder for the page and the bots: push one word per tick, then encode. */
export function createRecorder() {
  const words = [];
  return { words, push(w) { words.push(w >>> 0); }, get ticks() { return words.length; } };
}

/** Options for createSim() rebuilt from a tape header. */
export function simOptionsFromTape(t, track) {
  return { track, mode: t.mode, surface: t.surface, laps: t.laps, entrants: t.entrants };
}
