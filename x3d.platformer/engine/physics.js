// loom:sim
// A small deterministic 2D rigid-body solver: boxes and circles, sequential impulses with
// warm starting (after Erin Catto's Box2D-Lite, 2006), revolute joints and rope joints.
//
// Determinism contract: the step uses only IEEE-754 arithmetic plus Math.sqrt, Math.abs,
// Math.min, Math.max, Math.round and Math.floor, all of which are exactly specified.
// Math.sin and Math.cos are NOT exactly specified across JavaScript engines, so rotation
// uses dsin/dcos below (a fixed polynomial). Iteration orders are fixed by body id.

export const PI = 3.141592653589793;
export const TAU = 6.283185307179586;
export const HALF_PI = 1.5707963267948966;

const S3 = -1 / 6, S5 = 1 / 120, S7 = -1 / 5040, S9 = 1 / 362880, S11 = -1 / 39916800, S13 = 1 / 6227020800;

/** Portable sine: range-reduced Taylor polynomial, |error| < 1e-9 on any input. */
export function dsin(x) {
  x -= TAU * Math.round(x / TAU);
  if (x > HALF_PI) x = PI - x;
  else if (x < -HALF_PI) x = -PI - x;
  const x2 = x * x;
  return x * (1 + x2 * (S3 + x2 * (S5 + x2 * (S7 + x2 * (S9 + x2 * (S11 + x2 * S13))))));
}
export function dcos(x) { return dsin(x + HALF_PI); }

const ALLOWED_PEN = 0.01;
const BIAS = 0.2;
const MAX_V = 45;

export function createWorld(opts = {}) {
  return {
    gravityX: 0, gravityY: opts.gravity ?? -38,
    iterations: opts.iterations ?? 10,
    bodies: [], joints: [], arbiters: new Map(), nextId: 1,
    noCollide: new Set(), impacts: [], grid: new Map(), cell: 8, stamp: 0,
  };
}

export function addBody(world, o) {
  const b = {
    id: world.nextId++, name: o.name || '', role: o.role || 'solid', shape: o.shape || 'box',
    hx: o.hx ?? 0.5, hy: o.hy ?? 0.5, r: o.r ?? 0.5,
    x: o.x ?? 0, y: o.y ?? 0, a: o.a ?? 0, vx: o.vx ?? 0, vy: o.vy ?? 0, w: o.w ?? 0,
    px: 0, py: 0, pa: 0, c: 1, s: 0,
    fx: 0, fy: 0, t: 0,
    kind: o.kind || 'dynamic', mass: o.mass ?? 1, invM: 0, I: 0, invI: 0,
    friction: o.friction ?? 0.6, restitution: o.restitution ?? 0,
    gravityScale: o.gravityScale ?? 1, linDamp: o.linDamp ?? 0, angDamp: o.angDamp ?? 0.05,
    fixedRotation: !!o.fixedRotation, enabled: o.enabled ?? true,
    cat: o.cat ?? 1, mask: o.mask ?? 0xffff, data: o.data || null, cells: null,
  };
  b.px = b.x; b.py = b.y; b.pa = b.a;
  setKind(world, b, b.kind, b.mass);
  world.bodies.push(b);
  if (b.kind === 'static') gridInsert(world, b);
  return b;
}

/** Change a body between static, kinematic and dynamic at run time (crumbling platforms). */
export function setKind(world, b, kind, mass) {
  if (b.kind === 'static' && b.cells) gridRemove(world, b);
  b.kind = kind;
  if (mass !== undefined) b.mass = mass;
  if (kind === 'dynamic') {
    b.invM = 1 / b.mass;
    b.I = b.shape === 'circle' ? 0.5 * b.mass * b.r * b.r : b.mass * (4 * b.hx * b.hx + 4 * b.hy * b.hy) / 12;
    b.invI = b.fixedRotation ? 0 : 1 / b.I;
  } else {
    b.invM = 0; b.I = 0; b.invI = 0;
    if (kind === 'static') { b.vx = 0; b.vy = 0; b.w = 0; }
  }
  b.c = dcos(b.a); b.s = dsin(b.a);
  if (kind === 'static' && world.bodies.includes(b)) gridInsert(world, b);
  // drop stale arbiters so warm starting cannot carry impulses across the change
  for (const [k, arb] of world.arbiters) if (arb.b1 === b || arb.b2 === b) world.arbiters.delete(k);
}

export function setTransform(world, b, x, y, a = b.a) {
  const wasStatic = b.kind === 'static';
  if (wasStatic && b.cells) gridRemove(world, b);
  b.x = x; b.y = y; b.a = a; b.px = x; b.py = y; b.pa = a; b.c = dcos(a); b.s = dsin(a);
  if (wasStatic) gridInsert(world, b);
}

export function setEnabled(world, b, on) {
  if (b.enabled === on) return;
  b.enabled = on;
  if (b.kind === 'static') { if (on) gridInsert(world, b); else gridRemove(world, b); }
  if (!on) for (const [k, arb] of world.arbiters) if (arb.b1 === b || arb.b2 === b) world.arbiters.delete(k);
}

function aabb(b) {
  if (b.shape === 'circle') return [b.x - b.r, b.y - b.r, b.x + b.r, b.y + b.r];
  const ex = Math.abs(b.c) * b.hx + Math.abs(b.s) * b.hy;
  const ey = Math.abs(b.s) * b.hx + Math.abs(b.c) * b.hy;
  return [b.x - ex, b.y - ey, b.x + ex, b.y + ey];
}

function gridInsert(world, b) {
  if (!b.enabled) return;
  const [x0, , x1] = aabb(b);
  const c0 = Math.floor(x0 / world.cell), c1 = Math.floor(x1 / world.cell);
  b.cells = [];
  for (let c = c0; c <= c1; c++) {
    let list = world.grid.get(c);
    if (!list) { list = []; world.grid.set(c, list); }
    list.push(b); b.cells.push(c);
  }
}
function gridRemove(world, b) {
  if (!b.cells) return;
  for (const c of b.cells) {
    const list = world.grid.get(c);
    if (list) { const i = list.indexOf(b); if (i >= 0) list.splice(i, 1); }
  }
  b.cells = null;
}

export function addRevolute(world, b1, b2, ax, ay, o = {}) {
  const j = {
    type: 'revolute', b1, b2,
    l1x: 0, l1y: 0, l2x: 0, l2y: 0, r1x: 0, r1y: 0, r2x: 0, r2y: 0,
    m11: 0, m12: 0, m21: 0, m22: 0, bx: 0, by: 0, Px: 0, Py: 0,
    softness: o.softness ?? 0, biasFactor: o.biasFactor ?? 0.2, enabled: true,
  };
  // local anchors: R^T (anchor - position)
  let dx = ax - b1.x, dy = ay - b1.y;
  j.l1x = b1.c * dx + b1.s * dy; j.l1y = -b1.s * dx + b1.c * dy;
  dx = ax - b2.x; dy = ay - b2.y;
  j.l2x = b2.c * dx + b2.s * dy; j.l2y = -b2.s * dx + b2.c * dy;
  world.joints.push(j);
  if (!o.collide) world.noCollide.add(pairKey(b1, b2));
  return j;
}

/** One-sided distance limit between two anchor points (body-local), like a rope. */
export function addRope(world, b1, b2, l1x, l1y, l2x, l2y, maxLen) {
  const j = { type: 'rope', b1, b2, l1x, l1y, l2x, l2y, maxLen, ux: 0, uy: 0, r1x: 0, r1y: 0, r2x: 0, r2y: 0,
    len: 0, mass: 0, impulse: 0, enabled: true };
  world.joints.push(j);
  return j;
}
export function removeJoint(world, j) {
  const i = world.joints.indexOf(j);
  if (i >= 0) world.joints.splice(i, 1);
}

function pairKey(a, b) { return a.id < b.id ? a.id * 65536 + b.id : b.id * 65536 + a.id; }

// ---------------------------------------------------------------------------------------------
// Narrow phase. Every routine fills `out` with contacts {x, y, nx, ny, sep, f} whose normal
// points from body a to body b, and returns the count.

const EDGE1 = 1, EDGE2 = 2, EDGE3 = 3, EDGE4 = 4;
function fp(in1, out1, in2, out2) { return in1 | (out1 << 4) | (in2 << 8) | (out2 << 12); }
function flipFp(f) {
  const in1 = f & 15, out1 = (f >> 4) & 15, in2 = (f >> 8) & 15, out2 = (f >> 12) & 15;
  return fp(in2, out2, in1, out1);
}

function incidentEdge(hx, hy, px, py, c, s, nx, ny, out) {
  // normal from the reference box into the incident box's frame, flipped
  const lx = -(c * nx + s * ny), ly = -(-s * nx + c * ny);
  let v0x, v0y, f0, v1x, v1y, f1;
  if (Math.abs(lx) > Math.abs(ly)) {
    if (lx > 0) { v0x = hx; v0y = -hy; f0 = fp(0, 0, EDGE3, EDGE4); v1x = hx; v1y = hy; f1 = fp(0, 0, EDGE4, EDGE1); }
    else { v0x = -hx; v0y = hy; f0 = fp(0, 0, EDGE1, EDGE2); v1x = -hx; v1y = -hy; f1 = fp(0, 0, EDGE2, EDGE3); }
  } else {
    if (ly > 0) { v0x = hx; v0y = hy; f0 = fp(0, 0, EDGE4, EDGE1); v1x = -hx; v1y = hy; f1 = fp(0, 0, EDGE1, EDGE2); }
    else { v0x = -hx; v0y = -hy; f0 = fp(0, 0, EDGE2, EDGE3); v1x = hx; v1y = -hy; f1 = fp(0, 0, EDGE3, EDGE4); }
  }
  out[0] = { x: px + c * v0x - s * v0y, y: py + s * v0x + c * v0y, f: f0 };
  out[1] = { x: px + c * v1x - s * v1y, y: py + s * v1x + c * v1y, f: f1 };
}

function clip(vin, nx, ny, offset, clipEdge) {
  const out = [];
  const d0 = nx * vin[0].x + ny * vin[0].y - offset;
  const d1 = nx * vin[1].x + ny * vin[1].y - offset;
  if (d0 <= 0) out.push(vin[0]);
  if (d1 <= 0) out.push(vin[1]);
  if (d0 * d1 < 0) {
    const t = d0 / (d0 - d1);
    const v = { x: vin[0].x + t * (vin[1].x - vin[0].x), y: vin[0].y + t * (vin[1].y - vin[0].y), f: 0 };
    if (d0 > 0) { const f = vin[0].f; v.f = (f & ~0xf0f) | clipEdge; }       // inEdge1 = clip, inEdge2 = none
    else { const f = vin[1].f; v.f = (f & ~0xf0f0) | (clipEdge << 4); }      // outEdge1 = clip, outEdge2 = none
    out.push(v);
  }
  return out;
}

function boxBox(A, B, out) {
  const hAx = A.hx, hAy = A.hy, hBx = B.hx, hBy = B.hy;
  const dpx = B.x - A.x, dpy = B.y - A.y;
  const dAx = A.c * dpx + A.s * dpy, dAy = -A.s * dpx + A.c * dpy;
  const dBx = B.c * dpx + B.s * dpy, dBy = -B.s * dpx + B.c * dpy;
  // C = RotA^T RotB
  const c11 = A.c * B.c + A.s * B.s, c12 = -A.c * B.s + A.s * B.c;
  const c21 = -A.s * B.c + A.c * B.s, c22 = A.s * B.s + A.c * B.c;
  const a11 = Math.abs(c11), a12 = Math.abs(c12), a21 = Math.abs(c21), a22 = Math.abs(c22);
  const faceAx = Math.abs(dAx) - hAx - (a11 * hBx + a12 * hBy);
  const faceAy = Math.abs(dAy) - hAy - (a21 * hBx + a22 * hBy);
  if (faceAx > 0 || faceAy > 0) return 0;
  const faceBx = Math.abs(dBx) - (a11 * hAx + a21 * hAy) - hBx;
  const faceBy = Math.abs(dBy) - (a12 * hAx + a22 * hAy) - hBy;
  if (faceBx > 0 || faceBy > 0) return 0;

  let axis = 0, sep = faceAx;
  let nx = dAx > 0 ? A.c : -A.c, ny = dAx > 0 ? A.s : -A.s;
  const rel = 0.95, abs = 0.01;
  if (faceAy > rel * sep + abs * hAy) { axis = 1; sep = faceAy; nx = dAy > 0 ? -A.s : A.s; ny = dAy > 0 ? A.c : -A.c; }
  if (faceBx > rel * sep + abs * hBx) { axis = 2; sep = faceBx; nx = dBx > 0 ? B.c : -B.c; ny = dBx > 0 ? B.s : -B.s; }
  if (faceBy > rel * sep + abs * hBy) { axis = 3; sep = faceBy; nx = dBy > 0 ? -B.s : B.s; ny = dBy > 0 ? B.c : -B.c; }

  let fnx, fny, front, snx, sny, negSide, posSide, negEdge, posEdge;
  const inc = [];
  if (axis === 0) {
    fnx = nx; fny = ny; front = A.x * fnx + A.y * fny + hAx;
    snx = -A.s; sny = A.c; const side = A.x * snx + A.y * sny;
    negSide = -side + hAy; posSide = side + hAy; negEdge = EDGE3; posEdge = EDGE1;
    incidentEdge(hBx, hBy, B.x, B.y, B.c, B.s, fnx, fny, inc);
  } else if (axis === 1) {
    fnx = nx; fny = ny; front = A.x * fnx + A.y * fny + hAy;
    snx = A.c; sny = A.s; const side = A.x * snx + A.y * sny;
    negSide = -side + hAx; posSide = side + hAx; negEdge = EDGE2; posEdge = EDGE4;
    incidentEdge(hBx, hBy, B.x, B.y, B.c, B.s, fnx, fny, inc);
  } else if (axis === 2) {
    fnx = -nx; fny = -ny; front = B.x * fnx + B.y * fny + hBx;
    snx = -B.s; sny = B.c; const side = B.x * snx + B.y * sny;
    negSide = -side + hBy; posSide = side + hBy; negEdge = EDGE3; posEdge = EDGE1;
    incidentEdge(hAx, hAy, A.x, A.y, A.c, A.s, fnx, fny, inc);
  } else {
    fnx = -nx; fny = -ny; front = B.x * fnx + B.y * fny + hBy;
    snx = B.c; sny = B.s; const side = B.x * snx + B.y * sny;
    negSide = -side + hBx; posSide = side + hBx; negEdge = EDGE2; posEdge = EDGE4;
    incidentEdge(hAx, hAy, A.x, A.y, A.c, A.s, fnx, fny, inc);
  }
  const cp1 = clip(inc, -snx, -sny, negSide, negEdge);
  if (cp1.length < 2) return 0;
  const cp2 = clip(cp1, snx, sny, posSide, posEdge);
  if (cp2.length < 2) return 0;
  let n = 0;
  for (let i = 0; i < 2; i++) {
    const s = fnx * cp2[i].x + fny * cp2[i].y - front;
    if (s <= 0) {
      out[n++] = { x: cp2[i].x - s * fnx, y: cp2[i].y - s * fny, nx, ny, sep: s,
        f: axis >= 2 ? flipFp(cp2[i].f) : cp2[i].f };
    }
  }
  return n;
}

function circleCircle(A, B, out) {
  const dx = B.x - A.x, dy = B.y - A.y, d2 = dx * dx + dy * dy, rr = A.r + B.r;
  if (d2 > rr * rr) return 0;
  const d = Math.sqrt(d2);
  const nx = d > 1e-9 ? dx / d : 0, ny = d > 1e-9 ? dy / d : 1;
  out[0] = { x: A.x + nx * A.r, y: A.y + ny * A.r, nx, ny, sep: d - rr, f: 0 };
  return 1;
}

/** Box A against circle B; the normal points from the box to the circle. */
function boxCircle(A, B, out) {
  const dx = B.x - A.x, dy = B.y - A.y;
  const lx = A.c * dx + A.s * dy, ly = -A.s * dx + A.c * dy;
  const qx = Math.max(-A.hx, Math.min(A.hx, lx)), qy = Math.max(-A.hy, Math.min(A.hy, ly));
  let nlx, nly, sep, px, py;
  if (qx === lx && qy === ly) { // centre inside the box: push out along the shallowest face
    const ex = A.hx - Math.abs(lx), ey = A.hy - Math.abs(ly);
    if (ex < ey) { nlx = lx >= 0 ? 1 : -1; nly = 0; sep = -ex - B.r; px = nlx * A.hx; py = ly; }
    else { nlx = 0; nly = ly >= 0 ? 1 : -1; sep = -ey - B.r; px = lx; py = nly * A.hy; }
  } else {
    const ddx = lx - qx, ddy = ly - qy, d2 = ddx * ddx + ddy * ddy;
    if (d2 > B.r * B.r) return 0;
    const d = Math.sqrt(d2);
    nlx = ddx / d; nly = ddy / d; sep = d - B.r; px = qx; py = qy;
  }
  const nx = A.c * nlx - A.s * nly, ny = A.s * nlx + A.c * nly;
  out[0] = { x: A.x + A.c * px - A.s * py, y: A.y + A.s * px + A.c * py, nx, ny, sep, f: 0 };
  return 1;
}

function collide(a, b, out) {
  if (a.shape === 'box') return b.shape === 'box' ? boxBox(a, b, out) : boxCircle(a, b, out);
  if (b.shape === 'circle') return circleCircle(a, b, out);
  const n = boxCircle(b, a, out); // circle a, box b: flip the normal so it points a -> b
  for (let i = 0; i < n; i++) { out[i].nx = -out[i].nx; out[i].ny = -out[i].ny; }
  return n;
}

// ---------------------------------------------------------------------------------------------

function canCollide(world, a, b) {
  if ((a.cat & b.mask) === 0 || (b.cat & a.mask) === 0) return false;
  if (world.noCollide.has(pairKey(a, b))) return false;
  return true;
}

function updatePair(world, a, b, alive) {
  const b1 = a.id < b.id ? a : b, b2 = a.id < b.id ? b : a;
  const key = b1.id * 65536 + b2.id;
  const tmp = [];
  const n = collide(b1, b2, tmp);
  if (n === 0) return;
  alive.add(key);
  let arb = world.arbiters.get(key);
  if (!arb) {
    arb = { b1, b2, contacts: [], friction: Math.sqrt(b1.friction * b2.friction),
      restitution: Math.max(b1.restitution, b2.restitution), fresh: true };
    world.arbiters.set(key, arb);
  } else arb.fresh = false;
  const merged = [];
  for (let i = 0; i < n; i++) {
    const c = tmp[i];
    c.Pn = 0; c.Pt = 0;
    for (const o of arb.contacts) if (o.f === c.f) { c.Pn = o.Pn; c.Pt = o.Pt; break; }
    merged.push(c);
  }
  arb.contacts = merged;
}

function broadphase(world) {
  const alive = new Set();
  const movers = [];
  for (const b of world.bodies) if (b.enabled && b.kind !== 'static') movers.push(b);
  const boxes = movers.map(aabb);
  for (let i = 0; i < movers.length; i++) {
    const a = movers[i], A = boxes[i];
    // movers against movers
    for (let j = i + 1; j < movers.length; j++) {
      const b = movers[j];
      if (a.kind !== 'dynamic' && b.kind !== 'dynamic') continue;
      const B = boxes[j];
      if (A[2] < B[0] || B[2] < A[0] || A[3] < B[1] || B[3] < A[1]) continue;
      if (canCollide(world, a, b)) updatePair(world, a, b, alive);
    }
    if (a.kind !== 'dynamic') continue;
    // movers against statics through the grid
    world.stamp++;
    const c0 = Math.floor(A[0] / world.cell), c1 = Math.floor(A[2] / world.cell);
    for (let c = c0; c <= c1; c++) {
      const list = world.grid.get(c);
      if (!list) continue;
      for (const s of list) {
        if (s._stamp === world.stamp) continue;
        s._stamp = world.stamp;
        const S = aabb(s);
        if (A[2] < S[0] || S[2] < A[0] || A[3] < S[1] || S[3] < A[1]) continue;
        if (canCollide(world, a, s)) updatePair(world, a, s, alive);
      }
    }
  }
  for (const k of [...world.arbiters.keys()]) if (!alive.has(k)) world.arbiters.delete(k);
}

function prestepArbiter(world, arb, invDt) {
  const b1 = arb.b1, b2 = arb.b2;
  for (const c of arb.contacts) {
    const r1x = c.x - b1.x, r1y = c.y - b1.y, r2x = c.x - b2.x, r2y = c.y - b2.y;
    const rn1 = r1x * c.nx + r1y * c.ny, rn2 = r2x * c.nx + r2y * c.ny;
    const kN = b1.invM + b2.invM + b1.invI * (r1x * r1x + r1y * r1y - rn1 * rn1) + b2.invI * (r2x * r2x + r2y * r2y - rn2 * rn2);
    c.mN = kN > 0 ? 1 / kN : 0;
    const tx = c.ny, ty = -c.nx;
    const rt1 = r1x * tx + r1y * ty, rt2 = r2x * tx + r2y * ty;
    const kT = b1.invM + b2.invM + b1.invI * (r1x * r1x + r1y * r1y - rt1 * rt1) + b2.invI * (r2x * r2x + r2y * r2y - rt2 * rt2);
    c.mT = kT > 0 ? 1 / kT : 0;
    c.bias = -BIAS * invDt * Math.min(0, c.sep + ALLOWED_PEN);
    // approach speed before the solve (restitution and impact events)
    const dvx = b2.vx - b2.w * r2y - b1.vx + b1.w * r1y;
    const dvy = b2.vy + b2.w * r2x - b1.vy - b1.w * r1x;
    const vn = dvx * c.nx + dvy * c.ny;
    if (arb.restitution > 0 && vn < -1) c.bias = Math.max(c.bias, -arb.restitution * vn);
    if (arb.fresh && vn < -2.5) world.impacts.push({ x: c.x, y: c.y, speed: -vn, b1, b2 });
    c.r1x = r1x; c.r1y = r1y; c.r2x = r2x; c.r2y = r2y;
    // warm start
    const Px = c.Pn * c.nx + c.Pt * tx, Py = c.Pn * c.ny + c.Pt * ty;
    b1.vx -= b1.invM * Px; b1.vy -= b1.invM * Py; b1.w -= b1.invI * (r1x * Py - r1y * Px);
    b2.vx += b2.invM * Px; b2.vy += b2.invM * Py; b2.w += b2.invI * (r2x * Py - r2y * Px);
  }
  arb.fresh = false;
}

function solveArbiter(arb) {
  const b1 = arb.b1, b2 = arb.b2;
  for (const c of arb.contacts) {
    const { r1x, r1y, r2x, r2y } = c;
    let dvx = b2.vx - b2.w * r2y - b1.vx + b1.w * r1y;
    let dvy = b2.vy + b2.w * r2x - b1.vy - b1.w * r1x;
    const vn = dvx * c.nx + dvy * c.ny;
    let dPn = c.mN * (-vn + c.bias);
    const Pn0 = c.Pn; c.Pn = Math.max(Pn0 + dPn, 0); dPn = c.Pn - Pn0;
    let Px = dPn * c.nx, Py = dPn * c.ny;
    b1.vx -= b1.invM * Px; b1.vy -= b1.invM * Py; b1.w -= b1.invI * (r1x * Py - r1y * Px);
    b2.vx += b2.invM * Px; b2.vy += b2.invM * Py; b2.w += b2.invI * (r2x * Py - r2y * Px);

    dvx = b2.vx - b2.w * r2y - b1.vx + b1.w * r1y;
    dvy = b2.vy + b2.w * r2x - b1.vy - b1.w * r1x;
    const tx = c.ny, ty = -c.nx;
    const vt = dvx * tx + dvy * ty;
    let dPt = c.mT * (-vt);
    const maxPt = arb.friction * c.Pn;
    const Pt0 = c.Pt; c.Pt = Math.max(-maxPt, Math.min(maxPt, Pt0 + dPt)); dPt = c.Pt - Pt0;
    Px = dPt * tx; Py = dPt * ty;
    b1.vx -= b1.invM * Px; b1.vy -= b1.invM * Py; b1.w -= b1.invI * (r1x * Py - r1y * Px);
    b2.vx += b2.invM * Px; b2.vy += b2.invM * Py; b2.w += b2.invI * (r2x * Py - r2y * Px);
  }
}

function prestepJoint(j, invDt) {
  const b1 = j.b1, b2 = j.b2;
  j.r1x = b1.c * j.l1x - b1.s * j.l1y; j.r1y = b1.s * j.l1x + b1.c * j.l1y;
  j.r2x = b2.c * j.l2x - b2.s * j.l2y; j.r2y = b2.s * j.l2x + b2.c * j.l2y;
  const { r1x, r1y, r2x, r2y } = j;
  if (j.type === 'revolute') {
    const im = b1.invM + b2.invM;
    let k11 = im + b1.invI * r1y * r1y + b2.invI * r2y * r2y + j.softness;
    let k12 = -b1.invI * r1x * r1y - b2.invI * r2x * r2y;
    let k22 = im + b1.invI * r1x * r1x + b2.invI * r2x * r2x + j.softness;
    const det = k11 * k22 - k12 * k12;
    const id = det !== 0 ? 1 / det : 0;
    j.m11 = id * k22; j.m12 = -id * k12; j.m21 = -id * k12; j.m22 = id * k11;
    const dpx = b2.x + r2x - b1.x - r1x, dpy = b2.y + r2y - b1.y - r1y;
    j.bx = -j.biasFactor * invDt * dpx; j.by = -j.biasFactor * invDt * dpy;
    const Px = j.Px, Py = j.Py;
    b1.vx -= b1.invM * Px; b1.vy -= b1.invM * Py; b1.w -= b1.invI * (r1x * Py - r1y * Px);
    b2.vx += b2.invM * Px; b2.vy += b2.invM * Py; b2.w += b2.invI * (r2x * Py - r2y * Px);
  } else {
    const dx = b2.x + r2x - b1.x - r1x, dy = b2.y + r2y - b1.y - r1y;
    j.len = Math.sqrt(dx * dx + dy * dy);
    if (j.len > 1e-6) { j.ux = dx / j.len; j.uy = dy / j.len; } else { j.ux = 0; j.uy = 0; }
    const cr1 = r1x * j.uy - r1y * j.ux, cr2 = r2x * j.uy - r2y * j.ux;
    const k = b1.invM + b2.invM + b1.invI * cr1 * cr1 + b2.invI * cr2 * cr2;
    j.mass = k > 0 ? 1 / k : 0;
    j.C = j.len - j.maxLen;
    j.invDt = invDt;
    if (j.C <= 0) j.impulse = 0;
    const Px = j.impulse * j.ux, Py = j.impulse * j.uy;
    b1.vx -= b1.invM * Px; b1.vy -= b1.invM * Py; b1.w -= b1.invI * (r1x * Py - r1y * Px);
    b2.vx += b2.invM * Px; b2.vy += b2.invM * Py; b2.w += b2.invI * (r2x * Py - r2y * Px);
  }
}

function solveJoint(j) {
  const b1 = j.b1, b2 = j.b2, { r1x, r1y, r2x, r2y } = j;
  const dvx = b2.vx - b2.w * r2y - b1.vx + b1.w * r1y;
  const dvy = b2.vy + b2.w * r2x - b1.vy - b1.w * r1x;
  let Px, Py;
  if (j.type === 'revolute') {
    const ex = j.bx - dvx - j.softness * j.Px, ey = j.by - dvy - j.softness * j.Py;
    Px = j.m11 * ex + j.m12 * ey; Py = j.m21 * ex + j.m22 * ey;
    j.Px += Px; j.Py += Py;
  } else {
    let cdot = dvx * j.ux + dvy * j.uy;
    if (j.C < 0) cdot += j.invDt * j.C;          // slack: only stop it from overshooting the length
    else cdot += BIAS * j.invDt * j.C;           // taut: pull back to length
    let imp = -j.mass * cdot;
    const old = j.impulse; j.impulse = Math.min(0, old + imp); imp = j.impulse - old;
    Px = imp * j.ux; Py = imp * j.uy;
  }
  b1.vx -= b1.invM * Px; b1.vy -= b1.invM * Py; b1.w -= b1.invI * (r1x * Py - r1y * Px);
  b2.vx += b2.invM * Px; b2.vy += b2.invM * Py; b2.w += b2.invI * (r2x * Py - r2y * Px);
}

export function stepWorld(world, dt) {
  const invDt = 1 / dt;
  world.impacts.length = 0;
  for (const b of world.bodies) { b.px = b.x; b.py = b.y; b.pa = b.a; }
  broadphase(world);
  for (const b of world.bodies) {
    if (!b.enabled || b.kind !== 'dynamic') continue;
    b.vx += dt * (world.gravityX * b.gravityScale + b.invM * b.fx);
    b.vy += dt * (world.gravityY * b.gravityScale + b.invM * b.fy);
    b.w += dt * b.invI * b.t;
    if (b.linDamp) { const k = 1 / (1 + dt * b.linDamp); b.vx *= k; b.vy *= k; }
    if (b.angDamp) b.w *= 1 / (1 + dt * b.angDamp);
  }
  const arbs = [...world.arbiters.values()];
  for (const a of arbs) prestepArbiter(world, a, invDt);
  const joints = world.joints.filter(j => j.enabled && j.b1.enabled && j.b2.enabled);
  for (const j of joints) prestepJoint(j, invDt);
  for (let it = 0; it < world.iterations; it++) {
    for (const a of arbs) solveArbiter(a);
    for (const j of joints) solveJoint(j);
  }
  for (const b of world.bodies) {
    if (!b.enabled || b.kind === 'static') continue;
    if (b.kind === 'dynamic') {
      b.vx = Math.max(-MAX_V, Math.min(MAX_V, b.vx));
      b.vy = Math.max(-MAX_V, Math.min(MAX_V, b.vy));
    }
    b.x += dt * b.vx; b.y += dt * b.vy; b.a += dt * b.w;
    if (b.w !== 0 || b.kind === 'kinematic') { b.c = dcos(b.a); b.s = dsin(b.a); }
    b.fx = 0; b.fy = 0; b.t = 0;
  }
}

/** Contacts touching body b, with the normal turned to point toward b. */
export function contactsOf(world, b) {
  const out = [];
  for (const arb of world.arbiters.values()) {
    if (arb.b1 !== b && arb.b2 !== b) continue;
    const other = arb.b1 === b ? arb.b2 : arb.b1, sign = arb.b2 === b ? 1 : -1;
    for (const c of arb.contacts) out.push({ other, x: c.x, y: c.y, nx: sign * c.nx, ny: sign * c.ny, sep: c.sep, Pn: c.Pn });
  }
  return out;
}

/** Velocity of body b at world point (x, y). */
export function pointVelocity(b, x, y) {
  return [b.vx - b.w * (y - b.y), b.vy + b.w * (x - b.x)];
}

/** Ray straight down from (x, y): nearest static or solid top below, used for blob shadows and bots. */
export function castDown(world, x, y, maxDist, skip) {
  let best = maxDist;
  for (const b of world.bodies) {
    if (!b.enabled || b === skip || b.cat !== 1) continue;
    if (b.shape === 'circle') {
      const dx = x - b.x; if (Math.abs(dx) > b.r) continue;
      const top = b.y + Math.sqrt(b.r * b.r - dx * dx);
      if (top <= y && y - top < best) best = y - top;
      continue;
    }
    // rotated box: intersect the vertical line with the box in its local frame
    const ex = Math.abs(b.c) * b.hx + Math.abs(b.s) * b.hy;
    if (Math.abs(x - b.x) > ex) continue;
    // sample the top surface: solve for the highest local point on the line x
    let top = -Infinity;
    const corners = [[-b.hx, b.hy], [b.hx, b.hy], [b.hx, -b.hy], [-b.hx, -b.hy]];
    for (let i = 0; i < 4; i++) {
      const p = corners[i], q = corners[(i + 1) % 4];
      const ax = b.x + b.c * p[0] - b.s * p[1], ay = b.y + b.s * p[0] + b.c * p[1];
      const bx = b.x + b.c * q[0] - b.s * q[1], by = b.y + b.s * q[0] + b.c * q[1];
      if ((ax - x) * (bx - x) > 0 || ax === bx) continue;
      const t = (x - ax) / (bx - ax), yy = ay + t * (by - ay);
      if (yy > top) top = yy;
    }
    if (top <= y + 0.05 && y - top < best) best = Math.max(0, y - top);
  }
  return best;
}
