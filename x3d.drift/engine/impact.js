// Contact feedback rate limit (picture and sound only, never the sim). The sim reports wall and car
// contact on every tick it lasts, so a car leaning on a wall sends ~30 'crash' events a second.
// A new impact (impact sound, camera shake, hit flash) needs 150 ms since that contact's last event
// or a hit at least 1.5x harder; in between the contact is a scrape: the looped scrape sound follows
// its impulse and a spark flies every 3rd tick.
export const IMPACT_GAP = 18, IMPACT_JUMP = 1.5, SCRAPE_SPARK_EVERY = 3;

/** Classify one crash event: returns { impact, spark, s } and updates `hits` (one entry per contact pair). */
export function gateImpact(hits, ev, scale = 7000) {
  const s = Math.min(1, Math.max(0, (ev.impulse || 0) / scale));
  const key = ev.wall ? 'w' + ev.car : 'c' + Math.min(ev.car, ev.other) + ':' + Math.max(ev.car, ev.other);
  const h = hits[key] || (hits[key] = { tick: -1e9, s: 0, n: 0 });
  const impact = ev.tick - h.tick > IMPACT_GAP || ev.tick < h.tick || s >= IMPACT_JUMP * h.s;
  if (impact) { h.s = s; h.n = 0; } else { h.s = Math.max(h.s * 0.98, s); h.n++; }
  h.tick = ev.tick;
  return { impact, spark: impact || h.n % SCRAPE_SPARK_EVERY === 0, s };
}
