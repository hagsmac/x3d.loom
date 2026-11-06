// KANSEI picture side: DOM helpers, the HUD, the SVG minimap and the tachometer. Nothing here
// feeds the simulation; it only reads sim state that main.js hands it.

export const $ = (s, el = document) => el.querySelector(s);
export const $$ = (s, el = document) => [...el.querySelectorAll(s)];
export const clamp = (v, lo, hi) => (v < lo ? lo : v > hi ? hi : v);

export function fmtTime(t, dp = 3) {
  if (!(t > 0)) return dp === 3 ? '-:--.---' : '-:--.-';
  const m = Math.floor(t / 60), s = t - m * 60;
  return `${m}:${s.toFixed(dp).padStart(dp + 3, '0')}`;
}
export function fmtDelta(d) {
  if (!d) return '';
  const s = (d < 0 ? '−' : '+') + Math.abs(d).toFixed(3);
  return s;
}
export const fmtScore = n => Math.round(n).toLocaleString('en-US');
export const MEDAL_LABEL = { none: 'No medal', bronze: 'Bronze', silver: 'Silver', gold: 'Gold', platinum: 'Platinum' };
export const MEDAL_KANJI = { none: '無', bronze: '銅', silver: '銀', gold: '金', platinum: '極' };

/** Set text only when it changed (DOM writes are the expensive part of a HUD). */
export function txt(el, s) { if (el && el.__t !== s) { el.__t = s; el.textContent = s; } }
export function cls(el, name, on) { if (el && !!el.classList.contains(name) !== !!on) el.classList.toggle(name, !!on); }
export function attr(el, k, v) { if (el && el.getAttribute(k) !== String(v)) el.setAttribute(k, v); }

// -------------------------------------------------------------------------------------------
// Minimap: an SVG path from the centreline, fitted to a square box, north = -Z

export function mapFit(xs, zs, size = 200, pad = 12) {
  let x0 = 1e9, x1 = -1e9, z0 = 1e9, z1 = -1e9;
  for (let i = 0; i < xs.length; i++) { x0 = Math.min(x0, xs[i]); x1 = Math.max(x1, xs[i]); z0 = Math.min(z0, zs[i]); z1 = Math.max(z1, zs[i]); }
  const sc = (size - 2 * pad) / Math.max(x1 - x0, z1 - z0, 1);
  const ox = pad + ((size - 2 * pad) - (x1 - x0) * sc) / 2, oz = pad + ((size - 2 * pad) - (z1 - z0) * sc) / 2;
  // top view looking down -Y with -Z up the screen: screen right is +X, screen down is +Z
  return { sc, size, P: (x, z) => [ox + (x - x0) * sc, oz + (z - z0) * sc] };
}

export function mapPath(xs, zs, fit, step = 3) {
  let d = '';
  for (let i = 0; i < xs.length; i += step) { const [u, v] = fit.P(xs[i], zs[i]); d += (i ? 'L' : 'M') + u.toFixed(1) + ' ' + v.toFixed(1); }
  return d + 'Z';
}

/** Centreline from level text without parsing the whole scene (track cards on the menu). */
export function centerFromText(text) {
  const m = /name='center'\s+value='([^']*)'/.exec(text);
  if (!m) return null;
  const a = m[1].trim().split(/\s+/).map(Number), xs = [], zs = [];
  for (let i = 0; i + 7 < a.length; i += 8) { xs.push(a[i]); zs.push(a[i + 2]); }
  return { xs, zs };
}

export function miniCardSVG(xs, zs, accent = 'var(--beni)') {
  const fit = mapFit(xs, zs, 120, 8), d = mapPath(xs, zs, fit, 4);
  const [sx, sy] = fit.P(xs[0], zs[0]);
  return `<svg viewBox="0 0 120 120" aria-hidden="true"><path d="${d}" class="mm-base"/><path d="${d}" class="mm-line" style="stroke:${accent}"/><circle cx="${sx.toFixed(1)}" cy="${sy.toFixed(1)}" r="3.2" class="mm-start"/></svg>`;
}

export class Minimap {
  constructor(el, track) {
    this.el = el; this.T = track;
    const fit = this.fit = mapFit(track.x, track.z, 200, 14);
    const d = mapPath(track.x, track.z, fit, 2);
    let zones = '';
    for (const z of track.zones) {
      let zd = '';
      const n = track.n;
      const cnt = ((z.i1 - z.i0) % n + n) % n;
      for (let k = 0; k <= cnt; k += 2) {
        const i = (z.i0 + k) % n, hw = track.hw[i] * z.side;
        const x = track.x[i] + track.tz[i] * hw, zz = track.z[i] - track.tx[i] * hw;
        const [u, v] = fit.P(x, zz); zd += (k ? 'L' : 'M') + u.toFixed(1) + ' ' + v.toFixed(1);
      }
      zones += `<path d="${zd}" class="mm-zone${z.kind === 2 ? ' outer' : ''}"/>`;
    }
    const [sx, sy] = fit.P(track.x[track.checkpoints[0]], track.z[track.checkpoints[0]]);
    el.innerHTML = `<svg viewBox="0 0 200 200"><path d="${d}" class="mm-base"/><path d="${d}" class="mm-line"/>${zones}
      <rect x="${(sx - 4).toFixed(1)}" y="${(sy - 4).toFixed(1)}" width="8" height="8" class="mm-start"/>
      <circle r="5" class="mm-cp" id="mm-cp"/><g id="mm-cars"></g></svg>`;
    this.cp = el.querySelector('#mm-cp');
    this.carsG = el.querySelector('#mm-cars');
    this.dots = [];
  }
  setCars(list) {   // [{cls}] in sim order, plus optional ghost
    this.carsG.innerHTML = list.map((c, i) => `<g class="mm-car ${c.cls}" data-i="${i}"><path d="M0 -6 L4.5 5 L0 2.6 L-4.5 5 Z"/></g>`).join('');
    this.dots = [...this.carsG.children];
  }
  update(poses, nextCp) {
    for (let i = 0; i < this.dots.length; i++) {
      const p = poses[i];
      if (!p) { attr(this.dots[i], 'visibility', 'hidden'); continue; }
      const [u, v] = this.fit.P(p.x, p.z);
      // forward (sin yaw, cos yaw) is screen (dx, dy); the arrow points up, so rotate by 180 - yaw
      const a = 180 - p.yaw * 180 / Math.PI;
      attr(this.dots[i], 'visibility', 'visible');
      attr(this.dots[i], 'transform', `translate(${u.toFixed(1)} ${v.toFixed(1)}) rotate(${a.toFixed(0)})`);
    }
    if (nextCp !== undefined && nextCp >= 0) {
      const i = this.T.checkpoints[nextCp];
      const [u, v] = this.fit.P(this.T.x[i], this.T.z[i]);
      attr(this.cp, 'cx', u.toFixed(1)); attr(this.cp, 'cy', v.toFixed(1));
    }
  }
}

// -------------------------------------------------------------------------------------------
// Tachometer: a 240 degree arc drawn as SVG strokes, redline band, shift light row

export class Tach {
  constructor(el) {
    this.el = el;
    const R = 84, C = 2 * Math.PI * R, arc = C * (240 / 360);
    this.R = R; this.C = C; this.arc = arc;
    let ticks = '';
    for (let k = 0; k <= 10; k++) {
      const a = (-210 + k * 24) * Math.PI / 180, r0 = k % 2 ? 72 : 68;
      ticks += `<line x1="${(100 + Math.cos(a) * r0).toFixed(1)}" y1="${(100 + Math.sin(a) * r0).toFixed(1)}" x2="${(100 + Math.cos(a) * 76).toFixed(1)}" y2="${(100 + Math.sin(a) * 76).toFixed(1)}"/>`;
    }
    el.innerHTML = `<svg viewBox="0 0 200 200" class="tach-svg">
      <circle cx="100" cy="100" r="${R}" class="t-track" stroke-dasharray="${arc.toFixed(1)} ${C.toFixed(1)}" transform="rotate(150 100 100)"/>
      <circle cx="100" cy="100" r="${R}" class="t-red" id="t-red" transform="rotate(150 100 100)"/>
      <circle cx="100" cy="100" r="${R}" class="t-fill" id="t-fill" stroke-dasharray="0 ${C.toFixed(1)}" transform="rotate(150 100 100)"/>
      <g class="t-ticks">${ticks}</g>
      <circle cx="100" cy="100" r="62" class="t-boost-track" stroke-dasharray="${(2 * Math.PI * 62 * 0.5).toFixed(1)} 999" transform="rotate(165 100 100)"/>
      <circle cx="100" cy="100" r="62" class="t-boost" id="t-boost" stroke-dasharray="0 999" transform="rotate(165 100 100)"/>
    </svg>
    <div class="t-shift" id="t-shift">${'<i></i>'.repeat(9)}</div>
    <div class="t-gear" id="t-gear">N</div>
    <div class="t-speed"><b id="t-kmh">0</b><span>km/h</span></div>
    <div class="t-rpm" id="t-rpm">0 rpm</div>
    <div class="t-nos"><span>NOS</span><div class="bar"><i id="t-nos"></i></div></div>`;
    this.fill = el.querySelector('#t-fill'); this.red = el.querySelector('#t-red');
    this.boostEl = el.querySelector('#t-boost'); this.gear = el.querySelector('#t-gear');
    this.kmh = el.querySelector('#t-kmh'); this.rpmEl = el.querySelector('#t-rpm');
    this.nos = el.querySelector('#t-nos'); this.shift = el.querySelector('#t-shift');
    this.lights = [...this.shift.children];
    this.maxRpm = 9000; this.redline = 7000; this.lastSig = '';
  }
  setCar(spec) {
    this.maxRpm = Math.ceil((spec.limiterRpm + 600) / 1000) * 1000;
    this.redline = spec.redlineRpm; this.limiter = spec.limiterRpm;
    const f0 = this.redline / this.maxRpm, f1 = 1;
    attr(this.red, 'stroke-dasharray', `0 ${(this.arc * f0).toFixed(1)} ${(this.arc * (f1 - f0)).toFixed(1)} ${this.C.toFixed(1)}`);
  }
  update(car, t) {
    const rpm = car.rpm, f = clamp(rpm / this.maxRpm, 0, 1);
    const sig = (f * 400 | 0) + '|' + car.gear + '|' + Math.round(car.speed * 3.6) + '|' + (car.boost * 50 | 0) + '|' + (car.boostPressure * 30 | 0) + '|' + (car.boostActive ? 1 : 0);
    if (sig !== this.lastSig) {
      this.lastSig = sig;
      attr(this.fill, 'stroke-dasharray', `${(this.arc * f).toFixed(1)} ${this.C.toFixed(1)}`);
      attr(this.boostEl, 'stroke-dasharray', `${(2 * Math.PI * 62 * 0.5 * clamp(car.boostPressure, 0, 1)).toFixed(1)} 999`);
      txt(this.gear, car.gear === -1 ? 'R' : car.gear === 0 ? 'N' : String(car.gear));
      txt(this.kmh, String(Math.round(car.speed * 3.6)));
      txt(this.rpmEl, `${Math.round(rpm / 10) * 10} rpm`);
      this.nos.style.transform = `scaleX(${clamp(car.boost, 0, 1).toFixed(3)})`;
      cls(this.nos, 'on', car.boostActive);
    }
    // shift light: fills from 78% of redline, all flash at the limiter
    const s0 = this.redline * 0.78, k = clamp((rpm - s0) / (this.redline - s0), 0, 1);
    const n = Math.round(k * 9), flash = rpm >= this.redline - 60 && (Math.floor(t * 12) & 1);
    const lsig = n + (flash ? 'f' : '');
    if (lsig !== this.lsig) {
      this.lsig = lsig;
      for (let i = 0; i < 9; i++) this.lights[i].className = flash ? 'f' : i < n ? (i < 4 ? 'g' : i < 7 ? 'y' : 'r') : '';
    }
    cls(this.el, 'redline', rpm >= this.redline - 60);
  }
}

// -------------------------------------------------------------------------------------------
// Flash words and the banner

export function flash(container, word, kind = '', sub = '') {
  const el = document.createElement('div');
  el.className = 'flash ' + kind;
  el.innerHTML = `<b>${word}</b>${sub ? `<i>${sub}</i>` : ''}`;
  container.appendChild(el);
  setTimeout(() => el.remove(), 1300);
  while (container.children.length > 4) container.firstChild.remove();
}

export function toast(el, msg, ms = 1400) {
  el.textContent = msg; el.classList.remove('show'); void el.offsetWidth; el.classList.add('show');
  clearTimeout(el.__t2); el.__t2 = setTimeout(() => el.classList.remove('show'), ms);
}

/** Car stat bars (0..1) from the spec, for the car screen. */
export function carStats(spec) {
  const pw = spec.display.hp / spec.display.kg;
  return [
    ['Power', clamp(spec.display.hp / 720, 0.1, 1), `${spec.display.hp} hp`],
    ['Torque', clamp(spec.display.nm / 800, 0.1, 1), `${spec.display.nm} N·m`],
    ['Weight', clamp(1 - (spec.display.kg - 950) / 700, 0.1, 1), `${spec.display.kg} kg`],
    ['Grip', clamp((spec.tyre.mu - 1.0) / 0.3 + (spec.drive === 'awd' ? 0.2 : 0), 0.1, 1), spec.drive.toUpperCase()],
    ['Drift', clamp(spec.drive === 'awd' ? 0.42 : 0.55 + pw * 0.6 - (spec.tyre.mu - 1.1), 0.1, 1), spec.drive === 'awd' ? 'needs setup' : 'natural'],
  ];
}
