// loom:sim
// A tape is a run: the button bits of every 1/120 s tick, run-length encoded, bound to the
// sha256 of the level bytes it was recorded on and to the engine version. Replaying it through
// step() must reproduce `expect.hash` exactly; the Loom's play witness checks that.

export const TAPE_SCHEMA = 'nib.tape/1';

export function encodeTape({ level, level_sha256, engine, bits, expect, note }) {
  const rle = [];
  for (const b of bits) {
    const last = rle[rle.length - 1];
    if (last && last[0] === b) last[1]++;
    else rle.push([b, 1]);
  }
  return { schema: TAPE_SCHEMA, level, level_sha256, engine, hz: 120, ticks: bits.length, note: note || '', rle, expect };
}

export function decodeTape(t) {
  if (!t || t.schema !== TAPE_SCHEMA) throw new Error('not a ' + TAPE_SCHEMA + ' tape');
  const bits = new Uint8Array(t.ticks);
  let i = 0;
  for (const [b, n] of t.rle) { bits.fill(b, i, i + n); i += n; }
  if (i !== t.ticks) throw new Error(`tape length mismatch: rle covers ${i} ticks, header says ${t.ticks}`);
  return { ...t, bits };
}
