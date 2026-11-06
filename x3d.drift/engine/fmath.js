// loom:sim
// Portable transcendental functions for the simulation. ECMAScript leaves Math.sin, cos, atan2,
// exp and friends implementation-approximated, so a tape recorded in one JavaScript engine could
// diverge in another. These use only + - * /, Math.round, Math.floor, Math.abs and Math.sqrt,
// which IEEE-754 specifies exactly, so every engine produces the same bits.
// Accuracy against Math.* is measured in tests/fmath.test.mjs (all below 1e-9 on their ranges).

export const PI = 3.141592653589793;
export const TAU = 6.283185307179586;
export const HALF_PI = 1.5707963267948966;
export const DEG = PI / 180;
export const LN2 = 0.6931471805599453;

const S3 = -1 / 6, S5 = 1 / 120, S7 = -1 / 5040, S9 = 1 / 362880, S11 = -1 / 39916800, S13 = 1 / 6227020800, S15 = -1 / 1307674368000;

/** Sine: range-reduced Taylor polynomial (NIB's, with one more term). */
export function dsin(x) {
  x -= TAU * Math.round(x / TAU);
  if (x > HALF_PI) x = PI - x;
  else if (x < -HALF_PI) x = -PI - x;
  const x2 = x * x;
  return x * (1 + x2 * (S3 + x2 * (S5 + x2 * (S7 + x2 * (S9 + x2 * (S11 + x2 * (S13 + x2 * S15)))))));
}

/** Cosine via the sine with a quarter-turn shift (range reduction happens inside dsin). */
export function dcos(x) {
  x -= TAU * Math.round(x / TAU);
  return dsin(x + HALF_PI);
}

const TAN15 = 0.2679491924311227;     // tan(pi/12)
const INV_SQRT3 = 0.5773502691896258; // tan(pi/6)
const PI_6 = 0.5235987755982988;

/** Arctangent: fold to |x| <= 1, then to |x| <= tan(15 deg), then an odd Taylor series to x^19. */
export function datan(x) {
  let sign = 1;
  if (x < 0) { x = -x; sign = -1; }
  if (x !== x) return x;
  let off = 0;
  let inv = false;
  if (x > 1) { x = 1 / x; inv = true; }
  if (x > TAN15) { x = (x - INV_SQRT3) / (1 + x * INV_SQRT3); off = PI_6; }
  const x2 = x * x;
  // atan(x) = x - x^3/3 + x^5/5 - ... ; |x| <= 0.268 so x^21/21 < 2e-14
  let p = x * (1 + x2 * (-1 / 3 + x2 * (1 / 5 + x2 * (-1 / 7 + x2 * (1 / 9 + x2 * (-1 / 11 +
    x2 * (1 / 13 + x2 * (-1 / 15 + x2 * (1 / 17 + x2 * (-1 / 19))))))))));
  p += off;
  if (inv) p = HALF_PI - p;
  return sign * p;
}

/** atan2(y, x) with the usual quadrant rules (signed zeros are not distinguished). */
export function datan2(y, x) {
  if (x > 0) return datan(y / x);
  if (x < 0) return y >= 0 ? datan(y / x) + PI : datan(y / x) - PI;
  if (y > 0) return HALF_PI;
  if (y < 0) return -HALF_PI;
  return 0;
}

/** 2^k for an integer k by exact repeated doubling (no Math.pow). */
function pow2i(k) {
  let r = 1, b = k < 0 ? 0.5 : 2;
  let n = k < 0 ? -k : k;
  while (n > 0) { if (n & 1) r *= b; b *= b; n >>= 1; }
  return r;
}

/** Exponential: x = k ln2 + r with |r| <= ln2/2, Taylor series for e^r to r^13, times 2^k. */
export function dexp(x) {
  if (x !== x) return x;
  if (x > 709.7) return Infinity;
  if (x < -745) return 0;
  const k = Math.round(x / LN2);
  // two-part ln2 keeps the reduction exact enough for large k
  const r = (x - k * 0.6931471803691238) - k * 1.9082149292705877e-10;
  // Horner form of sum r^n/n!, n = 0..13: e^r = 1 + r(1 + r/2(1 + r/3(...)))
  let p = 1 + r / 13;
  p = 1 + r / 12 * p; p = 1 + r / 11 * p; p = 1 + r / 10 * p; p = 1 + r / 9 * p; p = 1 + r / 8 * p;
  p = 1 + r / 7 * p; p = 1 + r / 6 * p; p = 1 + r / 5 * p; p = 1 + r / 4 * p; p = 1 + r / 3 * p;
  p = 1 + r / 2 * p; p = 1 + r * p;
  if (k > 1000 || k < -1100) return k > 0 ? Infinity : 0;
  // split the scale so subnormal results do not lose the whole mantissa at once
  if (k < -1000) return p * pow2i(k + 500) * pow2i(-500);
  return p * pow2i(k);
}

/** Hyperbolic tangent from dexp, with a series near 0 to avoid cancellation. */
export function dtanh(x) {
  if (x > 20) return 1;
  if (x < -20) return -1;
  const ax = x < 0 ? -x : x;
  if (ax < 0.02) { const x2 = x * x; return x * (1 + x2 * (-1 / 3 + x2 * (2 / 15 + x2 * (-17 / 315)))); }
  const e = dexp(2 * x);
  return (e - 1) / (e + 1);
}

/** Wrap an angle to (-pi, pi]. */
export function wrapPi(a) {
  a -= TAU * Math.round(a / TAU);
  if (a <= -PI) a += TAU;
  return a;
}

export function clamp(v, lo, hi) { return v < lo ? lo : v > hi ? hi : v; }
export function lerp(a, b, t) { return a + (b - a) * t; }
/** Smooth 0..1 ramp between e0 and e1. */
export function smooth(e0, e1, x) {
  let t = (x - e0) / (e1 - e0);
  t = t < 0 ? 0 : t > 1 ? 1 : t;
  return t * t * (3 - 2 * t);
}
/** Deterministic integer hash (32-bit), for noise and chance without Math.random. */
export function ihash(a, b) {
  let h = Math.imul((a | 0) ^ 0x9e3779b9, 0x85ebca6b) ^ Math.imul((b | 0) + 0x7f4a7c15, 0xc2b2ae35);
  h ^= h >>> 16; h = Math.imul(h, 0x7feb352d); h ^= h >>> 15; h = Math.imul(h, 0x846ca68b); h ^= h >>> 16;
  return h >>> 0;
}
/** Smooth deterministic noise in [-1, 1]: hashed values every `period` ticks, eased between. */
export function inoise(tick, seed, period) {
  const k = Math.floor(tick / period);
  const f = (tick - k * period) / period;
  const a = ihash(k, seed) / 2147483647.5 - 1;
  const b = ihash(k + 1, seed) / 2147483647.5 - 1;
  const s = f * f * (3 - 2 * f);
  return a + (b - a) * s;
}
