// KANSEI: the page. Menus over the garage showroom, then a session: the level's X3D bytes are fetched
// once, hashed, handed to the simulation (parseTrack) and to X_ITE (the same text), and a fixed 120 Hz
// tick runs under a render loop that only interpolates. Every input word is recorded, so a session is
// a tape: Replay re-simulates it, the best Time Attack lap becomes a ghost in a second sim.
import { parseTrack, createSim, step, hashSim, summary, packInput, ENGINE_VERSION, HZ, DT, CARS, CAR_IDS, DRIFT_SETUPS } from './engine/sim.js';
import { TUNE_KEYS, TUNE_RANGE, resolveTune } from './engine/cars.js';
import { encodeTape, decodeTape, simOptionsFromTape } from './engine/tape.js';
import { medalRank, medalTargets } from './engine/race.js';
import { goalReached, goalState, statedMedal } from './engine/goal.js';
import { gateImpact } from './engine/impact.js';
import { World, LIVERIES, QUALITY } from './engine/render.js';
import { CameraRig, CAMERAS, CAMERA_LABEL, qSlerp, qToAxisAngle, axisAngleToQ } from './engine/camera.js';
import { FX } from './engine/fx.js';
import { Audio } from './engine/audio.js';
import { $, $$, txt, cls, clamp, fmtTime, fmtDelta, fmtScore, MEDAL_LABEL, MEDAL_KANJI, Minimap, Tach, flash, toast, centerFromText, miniCardSVG, carStats } from './engine/ui.js';

const Q = new URLSearchParams(location.search);
const BASE = new URL('.', location.href).href;
const audio = new Audio();
const store = {
  get(k, d) { try { const v = localStorage.getItem('kansei.v1.' + k); return v ? JSON.parse(v) : d; } catch { return d; } },
  set(k, v) { try { localStorage.setItem('kansei.v1.' + k, JSON.stringify(v)); return true; } catch { return false; } },
};

const MODES = [
  { id: 'rush', name: 'Drift rush', jp: '一撃', blurb: '90 seconds. Chain slides, clip zones, bank points.', meta: 'medals' },
  { id: 'attack', name: 'Time attack', jp: '計時', blurb: 'Clean laps against the clock and your own ghost.', meta: 'ghost' },
  { id: 'race', name: 'Race', jp: '競走', blurb: 'Three rivals, a light-out start, door to door.', meta: '4 cars' },
  { id: 'tandem', name: 'Tandem', jp: '追走', blurb: 'Chase a drifting lead car. Stay close, match the angle.', meta: 'grades' },
  { id: 'free', name: 'Free roam', jp: '自由', blurb: 'No clock. Find your line, practise, take photos.', meta: 'open' },
];
const TIPS = [
  'Lift, flick, catch: lifting off moves weight to the nose and lets the rear step out.',
  'A transition (slide left into slide right) is worth a whole multiplier step.',
  'Rear wheels within 2 m of a cyan clipping zone score double; within 1 m at 35° is PERFECT.',
  'Nitrous recharges faster while you are sideways. Spend it to hold the angle up a hill.',
  'TEMPEST grips like glue. Press Drift setup on its tune card to wake the rear.',
  'Every run is a tape: replay it anywhere and it reaches the same hash, tick for tick.',
  'Handbrake to start the slide, throttle to hold it, countersteer to steer it.',
];
const STAR_UNLOCK = 12;
const RIVALS = ['HAYATE', 'KAGERO', 'TSUBAME', 'OBORO', 'SEIRAN', 'KOGARASHI'];
const EVENT_MODES = ['rush', 'attack', 'race', 'tandem'];

const S = {
  X3D: null, browser: null, levels: [], carsMan: null, screen: 'boot', history: [],
  sel: Object.assign({ mode: 'rush', car: 'ronin', track: 'salt-ring', surface: 'dry', laps: 3, skill: 0.9, quality: 'medium' }, store.get('sel', {})),
  liveries: store.get('liveries', {}), tunes: store.get('tunes', {}),
  settings: Object.assign({ master: 0.8, music: 0.5, sfx: 0.9, camera: 'chase', ghost: true }, store.get('settings', {})),
  garage: null, sess: null, texts: new Map(), centers: store.get('centers', {}),
  last: 0, frameTimes: [], fps: 0, fpsN: 0, fpsT: 0, telemetry: false, testInput: null, errors: [],
};

// -------------------------------------------------------------------------------------------
// progress and stars
function progress() { return store.get('progress', { events: {} }); }
function eventStars(e) { return e ? e.stars || 0 : 0; }
// records and best tapes are kept per circuit, mode, car and surface (the medal targets move with all
// of them, engine/race.js medalTargets); stars stay per circuit and mode, the best over any car
const recKey = (track, mode, car, surface) => `${track}:${mode}:${car}:${surface === 'wet' ? 'wet' : 'dry'}`;
function selTargets(L, car = S.sel.car, surface = S.sel.surface) { return medalTargets(L.targets || {}, car, resolveTune(car, tuneFor(car)).grip, surface); }
function totalStars(p = progress()) { let n = 0; for (const k in p.events) n += eventStars(p.events[k]); return n; }
function maxStars() { return S.levels.length * EVENT_MODES.length * 3; }
function unlocked(carId) { return carId !== 'banshee' || totalStars() >= STAR_UNLOCK || Q.get('unlock') === '1' || store.get('unlockAll', false); }
function starsFor(mode, r) {
  if (!r) return 0;
  if (mode === 'rush' || mode === 'attack') return Math.min(3, Math.max(0, medalRank(r.medal || 'none')));
  if (mode === 'race') return r.dnf ? 0 : r.position === 1 ? 3 : r.position <= 3 ? 2 : 1;
  if (mode === 'tandem') return { S: 3, A: 2, B: 1 }[r.grade] || 0;
  return 0;
}
const starStr = (n, of = 3) => `<span class="stars">${'★'.repeat(n)}<span class="off">${'★'.repeat(Math.max(0, of - n))}</span></span>`;

// -------------------------------------------------------------------------------------------
// input: keyboard, standard gamepad, touch; analog values quantised into the packed word per tick
const keys = new Set();
const latch = { up: false, down: false, reset: false, hb: false };
const touch = { left: false, right: false, gas: false, brake: false, hb: false, boost: false };
const ctl = { steer: 0, thr: 0, brk: 0 };
const KEYMAP = { KeyA: 'left', ArrowLeft: 'left', KeyD: 'right', ArrowRight: 'right', KeyW: 'gas', ArrowUp: 'gas', KeyS: 'brake', ArrowDown: 'brake',
  Space: 'hb', ShiftLeft: 'boost', ShiftRight: 'boost', KeyE: 'up', KeyQ: 'down' };
const held = name => { for (const k of keys) if (KEYMAP[k] === name) return true; return false; };
let pad = { steer: 0, thr: 0, brk: 0, hb: false, boost: false, active: false, prev: {} };

function readPad() {
  pad.active = false;
  const pads = navigator.getGamepads ? navigator.getGamepads() : [];
  for (const p of pads) {
    if (!p || !p.connected) continue;
    const B = i => p.buttons[i] ? p.buttons[i].value || (p.buttons[i].pressed ? 1 : 0) : 0;
    const ax = p.axes[0] || 0, dz = 0.12;
    const s = Math.abs(ax) < dz ? 0 : Math.sign(ax) * Math.pow((Math.abs(ax) - dz) / (1 - dz), 1.35);
    const dl = B(14), dr = B(15);
    pad.steer = dr ? 1 : dl ? -1 : s; pad.thr = Math.max(B(7), B(12) ? 1 : 0); pad.brk = Math.max(B(6), B(13) ? 1 : 0);
    pad.hb = B(0) > 0.5; pad.boost = B(1) > 0.5;
    const edge = (i, fn) => { const on = B(i) > 0.5; if (on && !pad.prev[i]) fn(); pad.prev[i] = on; };
    edge(4, () => { latch.down = true; }); edge(5, () => { latch.up = true; });
    edge(3, () => cycleCamera()); edge(9, () => togglePause()); edge(8, () => toggleTelemetry());
    pad.active = Math.abs(ax) > dz || pad.thr > 0.02 || pad.brk > 0.02 || pad.hb || pad.boost || dl || dr;
    if (pad.active) S.usingPad = true;
    return;
  }
}

/** One packed input word for this tick (dt = 1/120 s), from every device. */
function inputWord() {
  if (S.testInput) {
    const t = S.testInput;
    return packInput({ steer: (t.steer || 0) * 127, throttle: (t.throttle || 0) * 15, brake: (t.brake || 0) * 15, handbrake: !!t.handbrake, boost: !!t.boost,
      shiftUp: latch.up, shiftDown: latch.down, reset: latch.reset || !!t.reset });
  }
  readPad();
  const L = held('left') || touch.left, R = held('right') || touch.right;
  const target = (R ? 1 : 0) - (L ? 1 : 0);
  if (S.usingPad && pad.active && target === 0) ctl.steer = pad.steer;
  else {
    const back = target === 0 || Math.sign(target) !== Math.sign(ctl.steer);
    const rate = (back ? 16 : 10) * DT;   // quick: the sim rate-limits the wheels itself
    ctl.steer += clamp(target - ctl.steer, -rate, rate);
  }
  const g = held('gas') || touch.gas, b = held('brake') || touch.brake;
  ctl.thr = g ? Math.min(1, ctl.thr + 9 * DT) : 0;
  ctl.brk = b ? Math.min(1, ctl.brk + 10 * DT) : 0;
  const thr = Math.max(ctl.thr, pad.thr), brk = Math.max(ctl.brk, pad.brk);
  const w = packInput({ steer: Math.round(ctl.steer * 127), throttle: Math.round(thr * 15), brake: Math.round(brk * 15),
    handbrake: held('hb') || touch.hb || pad.hb || latch.hb, boost: held('boost') || touch.boost || pad.boost,
    shiftUp: held('up') || latch.up, shiftDown: held('down') || latch.down, reset: latch.reset });
  return w;
}
function clearLatch() { latch.up = latch.down = latch.reset = latch.hb = false; }

addEventListener('keydown', e => {
  audio.start();
  const sess = S.sess, playing = S.screen === 'play';
  if (KEYMAP[e.code] && playing) e.preventDefault();
  if (e.code === 'F2') { e.preventDefault(); toggleTelemetry(); return; }
  if (e.repeat) { if (KEYMAP[e.code]) keys.add(e.code); return; }
  if (KEYMAP[e.code]) {
    keys.add(e.code);
    if (KEYMAP[e.code] === 'up') latch.up = true;
    if (KEYMAP[e.code] === 'down') latch.down = true;
    if (KEYMAP[e.code] === 'hb') latch.hb = true;
  }
  if (e.code === 'KeyM') { audio.setMuted(!audio.muted); toast($('#toast'), audio.muted ? 'Sound off' : 'Sound on'); }
  if (playing && sess && sess.paused && /^Arrow(Up|Down)$/.test(e.code)) { menuNav(e.code === 'ArrowDown' ? 1 : -1); return; }
  if (playing && sess) {
    if (e.code === 'Escape' || e.code === 'KeyP') { if (sess.photo) setPhoto(false); else togglePause(); }
    else if (e.code === 'KeyC') cycleCamera();
    else if (e.code === 'KeyF') setPhoto(!sess.photo);
    else if (e.code === 'KeyR' && sess.phase === 'play') latch.reset = true;
  } else if (S.screen === 'replay' && sess) {
    if (e.code === 'Escape') exitReplay();
    else if (e.code === 'Space') { e.preventDefault(); replayPlay(!sess.rp.playing); }
    else if (e.code === 'KeyC') cycleCamera();
  } else if (['ArrowDown', 'ArrowUp', 'ArrowLeft', 'ArrowRight'].includes(e.code) && !(document.activeElement && document.activeElement.type === 'range' && /Left|Right/.test(e.code))) {
    e.preventDefault(); menuNav(e.code === 'ArrowDown' || e.code === 'ArrowRight' ? 1 : -1);
  } else if (e.code === 'Escape' || e.code === 'Backspace') { if (S.history.length && !$('#tapebox').classList.contains('show')) goBack(); }
  else if (e.code === 'Enter' && S.screen === 'title') go('mode');
});
addEventListener('keyup', e => keys.delete(e.code));
addEventListener('blur', () => { keys.clear(); if (S.screen === 'play' && S.sess && !S.sess.paused && !S.sess.photo && !Q.get('tape')) togglePause(true); });
document.addEventListener('visibilitychange', () => { if (document.hidden && S.screen === 'play' && S.sess && !S.sess.paused && !Q.get('tape')) togglePause(true); });

/** Menus without a mouse: arrows or the pad move the focus through the visible controls, A clicks, B goes back. */
function menuRoot() {
  for (const id of ['#tapebox', '#results', '#pause']) if ($(id).classList.contains('show')) return $(id);
  return $('#s-' + S.screen) || document.body;
}
function menuNav(dir) {
  const items = $$('button, input[type=range]', menuRoot()).filter(el => el.offsetParent !== null && !el.disabled);
  if (!items.length) return;
  const i = items.indexOf(document.activeElement);
  const next = items[i < 0 ? 0 : (i + dir + items.length) % items.length];
  next.focus(); if (next.scrollIntoView) next.scrollIntoView({ block: 'nearest' });
  audio.ui('tick');
}
const menuPad = { prev: {}, t: 0 };
function menuPadPoll(dt) {
  const pads = navigator.getGamepads ? navigator.getGamepads() : [];
  for (const p of pads) {
    if (!p || !p.connected) continue;
    const B = i => !!(p.buttons[i] && p.buttons[i].pressed);
    const ay = p.axes[1] || 0, ax = p.axes[0] || 0;
    const dirs = { down: B(13) || ay > 0.6 || B(15) || ax > 0.6, up: B(12) || ay < -0.6 || B(14) || ax < -0.6 };
    menuPad.t -= dt;
    for (const [k, d] of [['down', 1], ['up', -1]]) {
      if (dirs[k] && (!menuPad.prev[k] || menuPad.t <= 0)) { menuNav(d); menuPad.t = menuPad.prev[k] ? 0.12 : 0.4; }
      menuPad.prev[k] = dirs[k];
    }
    const edge = (i, fn) => { const on = B(i); if (on && !menuPad.prev['b' + i]) fn(); menuPad.prev['b' + i] = on; };
    edge(0, () => { audio.start(); const el = document.activeElement; if (el && el.click && el !== document.body) el.click(); else menuNav(1); });
    edge(1, () => { if ($('#tapebox').classList.contains('show')) $('#tapebox').classList.remove('show'); else if (S.history.length && !S.sess) goBack(); });
    edge(9, () => { if (S.screen === 'title') go('mode'); });
    return;
  }
}

function setupTouch() {
  const coarse = matchMedia('(pointer: coarse)').matches || Q.get('touch') === '1';
  if (!coarse) return;
  document.body.classList.add('touch');
  for (const el of $$('#touch [data-t]')) {
    const k = el.dataset.t;
    const on = e => {
      e.preventDefault(); audio.start(); try { el.setPointerCapture(e.pointerId); } catch { /* synthetic or already released pointer */ } el.classList.add('on');
      if (k === 'pause') togglePause(); else if (k === 'cam') cycleCamera(); else { touch[k] = true; if (k === 'hb') latch.hb = true; }
    };
    const off = e => { e.preventDefault(); el.classList.remove('on'); if (k in touch) touch[k] = false; };
    el.addEventListener('pointerdown', on); el.addEventListener('pointerup', off); el.addEventListener('pointercancel', off); el.addEventListener('lostpointercapture', off);
  }
}

// orbit and photo: drag and wheel on the canvas
(() => {
  let drag = null;
  const stage = $('#stage');
  stage.addEventListener('pointerdown', e => { if (S.sess && ['orbit', 'photo'].includes(S.sess.cam.mode)) { drag = { x: e.clientX, y: e.clientY }; try { stage.setPointerCapture(e.pointerId); } catch { /* ignore */ } } });
  stage.addEventListener('pointermove', e => { if (drag && S.sess) { S.sess.cam.drag(e.clientX - drag.x, e.clientY - drag.y); drag = { x: e.clientX, y: e.clientY }; } });
  stage.addEventListener('pointerup', () => { drag = null; });
  stage.addEventListener('wheel', e => { if (S.sess && ['orbit', 'photo'].includes(S.sess.cam.mode)) { e.preventDefault(); S.sess.cam.zoom(e.deltaY); } }, { passive: false });
})();

// -------------------------------------------------------------------------------------------
// boot
async function sha256(text) {
  try {
    const d = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
    return [...new Uint8Array(d)].map(x => x.toString(16).padStart(2, '0')).join('');
  } catch { return ''; }
}
async function levelText(id) {
  if (S.texts.has(id)) return S.texts.get(id);
  const L = S.levels.find(l => l.id === id);
  const p = fetch('levels/' + L.file).then(r => { if (!r.ok) throw new Error('level ' + L.file + ' ' + r.status); return r.text(); });
  S.texts.set(id, p);
  p.catch(() => S.texts.delete(id));
  return p;
}

async function boot() {
  await customElements.whenDefined('x3d-canvas');
  S.X3D = window.X3D;
  S.browser = $('#canvas').browser;
  try { S.browser.setBrowserOption('TextureQuality', 'HIGH'); S.browser.setBrowserOption('PrimitiveQuality', 'MEDIUM'); } catch { /* defaults */ }
  const [lm, cm] = await Promise.all([fetch('levels/MANIFEST.json').then(r => r.json()), fetch('cars/MANIFEST.json').then(r => r.json())]);
  S.levels = lm.levels; S.carsMan = cm;
  if (!S.levels.find(l => l.id === S.sel.track)) S.sel.track = S.levels[0].id;
  if (!unlocked(S.sel.car)) S.sel.car = 'ronin';
  for (const k of ['master', 'music', 'sfx']) audio.setVolume(k, S.settings[k]);
  setupTouch();
  if (Q.get('noanim') === '1') document.body.classList.add('noanim');
  $('#ver').textContent = `${ENGINE_VERSION} · X_ITE ${S.browser.version || ''} · ${HZ} Hz`;
  wireMenus();
  window.KANSEI.ready = true;
  if (Q.get('tape')) return tapeMode(Q.get('tape'));
  await loadGarage();
  if (Q.get('start')) { const [mode, track, car] = Q.get('start').split(':'); return startSession({ mode, track, car }); }
  go('title', true);
}

// -------------------------------------------------------------------------------------------
// garage backdrop
const GARAGE_CAM = { title: 3, mode: 2, car: 0, track: 4, setup: 1, career: 2, settings: 2 };
async function loadGarage() {
  const X = S.X3D, b = S.browser;
  const scene = await b.createX3DFromURL(new X.MFString(new URL('garage.x3d', BASE).href));
  await b.replaceWorld(scene);
  try { const q = QUALITY[S.sel.quality] || QUALITY.medium; const pin = +(Q.get('cscale') || 0); b.setBrowserOption('ContentScale', pin > 0 ? Math.min(2, pin) : q.scale || Math.min(2, window.devicePixelRatio || 1)); } catch { /* defaults */ }
  const N = k => { try { return scene.getNamedNode(k); } catch { return null; } };
  const cams = [];
  for (let i = 0; i < 5; i++) { const v = N('GarageCam' + i); if (v) cams.push({ pos: [v.position.x, v.position.y, v.position.z], q: axisAngleToQ([v.orientation.x, v.orientation.y, v.orientation.z, v.orientation.angle]), fov: v.fieldOfView }); }
  const vp = scene.createNode('Viewpoint');
  vp.description = 'Menu camera'; vp.fieldOfView = 0.62;
  if (scene.addRootNode) scene.addRootNode(vp); else scene.rootNodes.push(vp);
  vp.set_bind = true;
  S.garage = { scene, N, slot: N('CarSlot'), turn: N('Turntable'), vp, cams, cache: new Map(), carId: null, angle: 0.6,
    cam: { from: cams[3], to: cams[3], t: 1 }, world: null };
  S.garage.world = { put: (n, f, v) => { n[f] = f === 'position' ? new X.SFVec3f(...v) : f === 'orientation' ? new X.SFRotation(...v) : v; } };
  if (S.sess) { S.sess = null; }
  audio.stopEngine();
  audio.startMusic('menu');
  await showGarageCar(S.sel.car);
}
async function showGarageCar(carId) {
  const G = S.garage; if (!G) return;
  G.want = carId;
  let entry = G.cache.get(carId);
  if (!entry) {
    entry = S.browser.createX3DFromURL(new S.X3D.MFString(new URL('cars/' + carId + '.x3d', BASE).href)).then(sc => {
      const n = k => { try { return sc.getNamedNode(k); } catch { return null; } };
      const paint = n('Paint');
      return { root: n('Car'), paint, factory: paint ? [paint.baseColor.r, paint.baseColor.g, paint.baseColor.b] : null };
    });
    G.cache.set(carId, entry);
  }
  const e = await entry;
  if (G.want !== carId || S.garage !== G) return;
  applyLivery(e, S.liveries[carId] || 'factory');
  if (G.carId !== carId) {
    G.slot.children = new S.X3D.MFNode(e.root);
    G.carId = carId;
  }
}
function applyLivery(e, id) {
  const L = LIVERIES.find(l => l.id === id) || LIVERIES[0];
  const rgb = L.rgb || e.factory;
  if (rgb && e.paint) e.paint.baseColor = new S.X3D.SFColor(...rgb);
}
function garageFrame(dt) {
  const G = S.garage; if (!G || S.sess) return;
  G.angle += dt * (S.screen === 'car' ? 0.32 : 0.16);
  if (G.turn) G.turn.rotation = new S.X3D.SFRotation(0, 1, 0, G.angle % (Math.PI * 2));
  const c = G.cam;
  if (c.t < 1) {
    c.t = Math.min(1, c.t + dt / 1.1);
    const k = 1 - Math.pow(1 - c.t, 3);
    // move around the turntable axis, not through it: radius, angle and height are eased separately,
    // so the eye never comes closer to the car than the nearer of the two camera poses
    const a0 = Math.atan2(c.from.pos[0], c.from.pos[2]), a1 = Math.atan2(c.to.pos[0], c.to.pos[2]);
    let da = a1 - a0; while (da > Math.PI) da -= 2 * Math.PI; while (da < -Math.PI) da += 2 * Math.PI;
    const r0 = Math.hypot(c.from.pos[0], c.from.pos[2]), r1 = Math.hypot(c.to.pos[0], c.to.pos[2]);
    const a = a0 + da * k, r = r0 + (r1 - r0) * k;
    const p = [Math.sin(a) * r, c.from.pos[1] + (c.to.pos[1] - c.from.pos[1]) * k, Math.cos(a) * r];
    const q = qSlerp(c.from.q, c.to.q, k);
    G.vp.position = new S.X3D.SFVec3f(...p); G.vp.orientation = new S.X3D.SFRotation(...qToAxisAngle(q));
    G.vp.fieldOfView = c.from.fov + (c.to.fov - c.from.fov) * k;
    c.cur = { pos: p, q, fov: G.vp.fieldOfView };
  } else if (!c.placed) { c.placed = true; const t = c.to; G.vp.position = new S.X3D.SFVec3f(...t.pos); G.vp.orientation = new S.X3D.SFRotation(...qToAxisAngle(t.q)); G.vp.fieldOfView = t.fov; c.cur = t; }
}
function garageCam(screen) {
  const G = S.garage; if (!G || !G.cams.length) return;
  const to = G.cams[GARAGE_CAM[screen] ?? 0] || G.cams[0];
  if (G.cam.to === to) return;
  G.cam = { from: G.cam.cur || G.cam.to, to, t: 0, placed: false };
}

// -------------------------------------------------------------------------------------------
// menus
function crumbs() {
  const m = MODES.find(m => m.id === S.sel.mode), L = S.levels.find(l => l.id === S.sel.track);
  const parts = { mode: [], car: [m.name], track: [m.name, CARS[S.sel.car].name], setup: [m.name, CARS[S.sel.car].name, L ? L.name : ''] }[S.screen] || [];
  $('#crumbs').innerHTML = parts.map((p, i) => (i === parts.length - 1 ? `<b>${p}</b>` : p)).join(' / ');
}
function go(screen, root = false) {
  if (!root && S.screen !== screen && S.screen !== 'boot') S.history.push(S.screen);
  if (root) S.history = [];
  S.screen = screen;
  for (const el of $$('.screen')) el.classList.toggle('show', el.id === 's-' + screen);
  document.body.classList.toggle('menu', !!$('#s-' + screen));
  document.body.classList.toggle('playing', screen === 'play');
  garageCam(screen);
  if (screen === 'title') renderTitle();
  if (screen === 'mode') renderModes();
  if (screen === 'car') renderCars();
  if (screen === 'track') renderTracks();
  if (screen === 'setup') renderSetup();
  if (screen === 'career') renderCareer();
  if (screen === 'settings') renderSettings();
  crumbs();
  const st = totalStars(); txt($('#star-count'), String(st)); txt($('#star-total'), String(maxStars()));
  const first = $('#s-' + screen + ' .tile.on, #s-' + screen + ' .btn');
  if (first && !document.body.classList.contains('touch')) setTimeout(() => first.focus({ preventScroll: true }), 30);
  setTimeout(moreCue, 60);
}
/** The fade at the bottom of a menu screen while more of it is below the fold. */
function moreCue() {
  for (const el of $$('.screen')) el.classList.toggle('more', el.classList.contains('show') && el.scrollHeight - el.scrollTop - el.clientHeight > 8);
}
addEventListener('scroll', e => { if (e.target && e.target.classList && e.target.classList.contains('screen')) moreCue(); }, true);
addEventListener('resize', () => setTimeout(moreCue, 60));
function goBack() { audio.ui('back'); const prev = S.history.pop() || 'title'; S.screen = '__'; go(prev, prev === 'title'); if (prev !== 'title') S.history.pop(); }
function saveSel() { store.set('sel', S.sel); }

function renderTitle() {
  const p = progress(), st = totalStars(p);
  $('#title-stars').textContent = `${st} / ${maxStars()} stars`;
  $('#strip').innerHTML = S.levels.map(L => {
    let n = 0; for (const m of EVENT_MODES) n += eventStars(p.events[L.id + ':' + m]);
    return `<span class="ev">${L.name} ${starStr(Math.min(12, n), 12).replace(/★/g, '★')}</span>`;
  }).join('');
}
function renderModes() {
  const box = $('#modes');
  box.innerHTML = MODES.map((m, i) => `<button class="tile rise ${m.id === S.sel.mode ? 'on' : ''}" style="--i:${i + 2}" data-mode="${m.id}"><span class="jp">${m.jp}</span><b>${m.name}</b><span class="meta">${m.meta}</span><i>${m.blurb}</i></button>`).join('');
  for (const el of $$('[data-mode]', box)) el.onclick = () => { audio.start(); audio.ui('select'); S.sel.mode = el.dataset.mode; saveSel(); go('car'); };
}
function renderCars() {
  const box = $('#cars');
  box.innerHTML = CAR_IDS.map((id, i) => {
    const c = CARS[id], lock = !unlocked(id);
    return `<button class="tile rise ${id === S.sel.car ? 'on' : ''} ${lock ? 'locked' : ''}" style="--i:${i + 2}" data-car="${id}"><span class="jp">${['鯉', '浪', '嵐', '妖'][i]}</span><b>${c.name}</b><span class="meta">${lock ? `★ ${STAR_UNLOCK} to unlock` : `${c.drive.toUpperCase()} · ${c.display.hp} hp`}</span><i>${c.display.layout}</i></button>`;
  }).join('');
  for (const el of $$('[data-car]', box)) el.onclick = () => {
    audio.ui('tick');
    if (!unlocked(el.dataset.car)) { toast($('#toast'), `Earn ${STAR_UNLOCK} stars to unlock BANSHEE`); return; }
    S.sel.car = el.dataset.car; saveSel();
    for (const t of $$('[data-car]', box)) t.classList.toggle('on', t === el);
    carDetail(); showGarageCar(S.sel.car);
  };
  carDetail();
}
function carDetail() {
  const c = CARS[S.sel.car];
  txt($('#car-name'), c.name); txt($('#car-layout'), c.display.layout); txt($('#car-blurb'), c.blurb);
  $('#carstats').innerHTML = carStats(c).map(([k, v, s]) => `<div class="stat"><span>${k}</span><div class="bar"><i style="transform:scaleX(${v.toFixed(3)})"></i></div><span>${s}</span></div>`).join('');
  const cur = S.liveries[S.sel.car] || 'factory';
  const fac = (S.garage && S.garage.cache.get(S.sel.car)) ? null : null;
  $('#liveries').innerHTML = LIVERIES.map(L => {
    const srgb = c => `rgb(${c.map(v => Math.round(Math.pow(v, 1 / 2.2) * 255)).join(',')})`;
    const css = L.rgb ? srgb(L.rgb) : `linear-gradient(135deg, ${srgb(factoryRGB(S.sel.car))} 0 58%, ${srgb(FACTORY_STRIPE[S.sel.car] || [0.2, 0.2, 0.2])} 58% 74%, ${srgb(factoryRGB(S.sel.car))} 74%)`;
    return `<button class="sw ${L.rgb ? '' : 'factory'} ${L.id === cur ? 'on' : ''}" title="${L.name}" data-liv="${L.id}" style="background:${css}"></button>`;
  }).join('');
  txt($('#livery-name'), (LIVERIES.find(l => l.id === cur) || LIVERIES[0]).name);
  for (const el of $$('[data-liv]')) el.onclick = () => {
    audio.ui('tick'); S.liveries[S.sel.car] = el.dataset.liv; store.set('liveries', S.liveries);
    for (const s of $$('[data-liv]')) s.classList.toggle('on', s === el);
    txt($('#livery-name'), (LIVERIES.find(l => l.id === el.dataset.liv) || LIVERIES[0]).name);
    showGarageCar(S.sel.car);
  };
  void fac;
}
const FACTORY = { koi: [0.93, 0.36, 0.07], ronin: [0.9, 0.9, 0.88], tempest: [0.05, 0.2, 0.6], banshee: [0.46, 0.03, 0.05] };
const factoryRGB = id => FACTORY[id] || [0.5, 0.5, 0.5];
const FACTORY_STRIPE = { koi: [0.95, 0.95, 0.92], ronin: [0.75, 0.04, 0.06], tempest: [0.95, 0.75, 0.05], banshee: [0.02, 0.02, 0.02] };

function trackMedalLine(L) {
  const p = progress(), m = S.sel.mode, car = S.sel.car, surface = S.sel.surface;
  const e = p.events[L.id + ':' + m];
  const rec = (p.records || {})[recKey(L.id, m, car, surface)];
  const who = `${CARS[car].name}${surface === 'wet' ? ' · wet' : ''}`;
  let best = `no ${who} result yet`;
  if (rec) {
    if (m === 'attack') best = `${who} best ${fmtTime(rec.best)}`;
    else if (m === 'race') best = `${who} best P${rec.best}`;
    else if (m === 'tandem') best = `${who} best grade ${rec.grade}`;
    else best = `${who} best ${fmtScore(rec.best)}`;
  }
  const med = e && e.medal && e.medal !== 'none' ? `<span class="md ${e.medal}">${MEDAL_LABEL[e.medal]}</span>` : '';
  return `${m !== 'free' ? starStr(eventStars(e)) : ''} ${med}<span class="md">${best}</span>`;
}
async function renderTracks() {
  const box = $('#tracks');
  const m = MODES.find(x => x.id === S.sel.mode);
  txt($('#track-sub'), `${m.name}: stars and medal are your best here in any car; the record is ${CARS[S.sel.car].name} on the ${S.sel.surface === 'wet' ? 'wet' : 'dry'}.`);
  box.innerHTML = S.levels.map((L, i) => {
    const c = S.centers[L.sha256];
    return `<button class="tcard rise ${L.id === S.sel.track ? 'on' : ''}" style="--i:${i + 2}" data-track="${L.id}" data-time="${L.time}">
      <div class="map" data-time="${L.time}">${c ? miniCardSVG(c.xs, c.zs) : '<svg viewBox="0 0 120 120"></svg>'}</div>
      <div class="body"><b>${L.name}</b><i>${L.subtitle} · ${(L.length / 1000).toFixed(2)} km · ${L.zones} zones</i><div class="medals">${trackMedalLine(L)}</div></div></button>`;
  }).join('');
  for (const el of $$('[data-track]', box)) el.onclick = () => { audio.ui('select'); S.sel.track = el.dataset.track; saveSel(); go('setup'); };
  // minimaps: from the level bytes (fetched once; the session reuses them), cached by sha256
  for (const L of S.levels) {
    if (S.centers[L.sha256]) continue;
    levelText(L.id).then(text => {
      const c = centerFromText(text); if (!c) return;
      const step = Math.max(1, Math.floor(c.xs.length / 160));
      const small = { xs: c.xs.filter((_, i) => i % step === 0).map(v => Math.round(v)), zs: c.zs.filter((_, i) => i % step === 0).map(v => Math.round(v)) };
      S.centers[L.sha256] = small;
      const keep = {}; for (const l of S.levels) if (S.centers[l.sha256]) keep[l.sha256] = S.centers[l.sha256];
      store.set('centers', keep);
      const card = $(`[data-track="${L.id}"] .map`); if (card) card.innerHTML = miniCardSVG(small.xs, small.zs);
    }).catch(() => {});
  }
}

function tuneFor(car) { return Object.assign({}, S.tunes[car] || {}); }
function renderSetup() {
  const car = S.sel.car, spec = CARS[car], mode = S.sel.mode, L = S.levels.find(l => l.id === S.sel.track);
  txt($('#setup-sub'), `${MODES.find(m => m.id === mode).name} · ${spec.name} · ${L.name}`);
  const seg = (key, opts, val) => `<div class="seg" data-seg="${key}">${opts.map(([v, l]) => `<button data-v="${v}" class="${String(v) === String(val) ? 'on' : ''}">${l}</button>`).join('')}</div>`;
  const sess = $('#card-session');
  const lapsRow = mode === 'race' || mode === 'attack' ? `<div class="field"><label>${mode === 'attack' ? 'Laps in session' : 'Race laps'}</label>${seg('laps', mode === 'attack' ? [[1, '1'], [3, '3'], [5, '5'], [0, '∞']] : [[1, '1'], [2, '2'], [3, '3'], [5, '5']], S.sel.laps)}</div>` : '';
  const ghostRow = mode === 'attack' ? `<div class="field"><label>Ghost</label>${seg('ghost', [['on', 'On'], ['off', 'Off']], S.settings.ghost === false ? 'off' : 'on')}</div>` : '';
  const targetRow = mode === 'attack' || mode === 'rush' ? `<div class="field"><label>Medals</label><output class="wide" id="o-targets">${targetsText(L)}</output></div>` : '';
  const skillRow = mode === 'race' ? `<div class="field"><label>Rival skill</label><output id="o-skill">${Math.round(S.sel.skill * 100)}</output><input type="range" id="skill" min="0.8" max="1" step="0.01" value="${S.sel.skill}"></div>` : '';
  sess.innerHTML = `<h3>Session</h3>
    <div class="field"><label>Surface</label>${seg('surface', [['dry', 'Dry'], ['wet', 'Wet']], S.sel.surface)}</div>${lapsRow}${skillRow}${ghostRow}${targetRow}
    <div class="field"><label>Quality</label>${seg('quality', [['low', 'Low'], ['medium', 'Med'], ['high', 'High']], S.sel.quality)}</div>
    <div class="field"><label>Start camera</label>${seg('camera', [['chase', 'Chase'], ['close', 'Close'], ['hood', 'Hood']], S.settings.camera)}</div>`;
  for (const g of $$('[data-seg]', sess)) for (const b of $$('button', g)) b.onclick = () => {
    audio.ui('tick');
    const k = g.dataset.seg, v = b.dataset.v;
    if (k === 'camera') { S.settings.camera = v; store.set('settings', S.settings); }
    else if (k === 'ghost') { S.settings.ghost = v === 'on'; store.set('settings', S.settings); }
    else S.sel[k] = k === 'laps' ? +v : v;
    saveSel(); for (const x of $$('button', g)) x.classList.toggle('on', x === b);
    if (k === 'surface') updateTargetsRow();
  };
  const sk = $('#skill', sess); if (sk) { sk.oninput = () => { S.sel.skill = +sk.value; txt($('#o-skill'), String(Math.round(S.sel.skill * 100))); paint(sk); saveSel(); }; paint(sk); }
  // tune and assists: sliders over the car's TUNE_RANGE, stored per car
  const t = resolveTune(car, tuneFor(car));
  const label = { grip: 'Tyre grip', steerLock: 'Steering lock', finalDrive: 'Final drive', brakeBias: 'Brake bias (front)', diffLock: 'Diff lock', balance: 'Grip balance (front)', stability: 'Stability', driftAssist: 'Drift assist', traction: 'Traction control', awdSplit: 'AWD front split' };
  const fmt = { grip: v => v.toFixed(2) + '×', steerLock: v => v.toFixed(0) + '°', finalDrive: v => v.toFixed(2), brakeBias: v => Math.round(v * 100) + '%', awdSplit: v => Math.round(v * 100) + '%' };
  const slider = k => {
    const [lo, hi] = TUNE_RANGE[k], stepv = k === 'steerLock' ? 1 : (hi - lo) / 100;
    const f = fmt[k] || (v => Math.round(v * 100) + '%');
    return `<div class="field"><label>${label[k]}</label><output data-o="${k}">${f(t[k])}</output><input type="range" data-k="${k}" min="${lo}" max="${hi}" step="${stepv}" value="${t[k]}"></div>`;
  };
  const tuneKeys = ['grip', 'balance', 'steerLock', 'finalDrive', 'brakeBias', 'diffLock'].concat(spec.drive === 'awd' ? ['awdSplit'] : []);
  $('#card-tune').innerHTML = `<h3>Tune <span class="row"><button class="ibtn" id="tune-drift">Drift setup</button><button class="ibtn" id="tune-reset">Default</button></span></h3>` + tuneKeys.map(slider).join('');
  $('#card-assist').innerHTML = `<h3>Assists &amp; gearbox</h3>` + ['stability', 'driftAssist', 'traction'].map(slider).join('') +
    `<div class="field"><label>Gearbox</label>${seg('gearbox', [['auto', 'Auto'], ['manual', 'Manual']], t.gearbox)}</div>`;
  for (const r of $$('#card-tune input[type=range], #card-assist input[type=range]')) {
    paint(r);
    r.oninput = () => {
      const k = r.dataset.k, v = +r.value, tu = tuneFor(car); tu[k] = v; S.tunes[car] = tu; store.set('tunes', S.tunes);
      txt($(`[data-o="${k}"]`), (fmt[k] || (x => Math.round(x * 100) + '%'))(v)); paint(r);
      if (k === 'grip') updateTargetsRow();
    };
  }
  const gb = $('#card-assist [data-seg=gearbox]');
  for (const b of $$('button', gb)) b.onclick = () => { const tu = tuneFor(car); tu.gearbox = b.dataset.v; S.tunes[car] = tu; store.set('tunes', S.tunes); for (const x of $$('button', gb)) x.classList.toggle('on', x === b); audio.ui('tick'); };
  $('#tune-drift').onclick = () => { S.tunes[car] = Object.assign({}, DRIFT_SETUPS[car] || {}, { gearbox: tuneFor(car).gearbox }); store.set('tunes', S.tunes); audio.ui('select'); renderSetup(); toast($('#toast'), 'Drift setup applied'); };
  $('#tune-reset').onclick = () => { delete S.tunes[car]; store.set('tunes', S.tunes); audio.ui('back'); renderSetup(); };
}
function targetsText(L) {
  const tg = selTargets(L);
  return S.sel.mode === 'attack' ? `gold ${fmtTime(tg.goldLap, 1)} · silver ${fmtTime(tg.silverLap, 1)} · bronze ${fmtTime(tg.bronzeLap, 1)}`
    : `gold ${fmtScore(tg.rushGold)} · silver ${fmtScore(tg.rushSilver)} · bronze ${fmtScore(tg.rushBronze)}`;
}
function updateTargetsRow() {
  const o = $('#o-targets'); if (!o) return;
  o.textContent = targetsText(S.levels.find(l => l.id === S.sel.track));
}
function paint(r) { const p = (r.value - r.min) / (r.max - r.min) * 100; r.style.setProperty('--p', p + '%'); }

function renderCareer() {
  const p = progress(), st = totalStars(p);
  const k = Math.min(1, st / STAR_UNLOCK);
  $('#unlock').innerHTML = unlocked('banshee') && st >= STAR_UNLOCK ? `<b class="label"><b>BANSHEE unlocked</b></b><div class="bar"><i style="width:100%"></i></div><span class="stars">★ ${st}</span>`
    : `<span class="label">Unlock <b>BANSHEE</b></span><div class="bar"><i style="width:${(k * 100).toFixed(0)}%"></i></div><span class="stars">★ ${st} / ${STAR_UNLOCK}</span>`;
  let html = `<div class="h">Circuit</div>` + EVENT_MODES.map(m => `<div class="h">${MODES.find(x => x.id === m).name}</div>`).join('');
  for (const L of S.levels) {
    html += `<div class="t"><b>${L.name}</b></div>`;
    for (const m of EVENT_MODES) {
      const e = p.events[L.id + ':' + m];
      const extra = !e ? '' : m === 'attack' ? fmtTime(e.best) : m === 'rush' ? fmtScore(e.best) : m === 'race' ? 'P' + e.best : e.grade || '';
      html += `<div>${starStr(eventStars(e))}${e && e.medal === 'platinum' ? ' ♛' : ''}<br><span style="color:var(--mute);font-family:var(--num);font-size:11px">${extra}</span></div>`;
    }
  }
  $('#career-grid').innerHTML = html;
}
function avControls(el) {
  el.innerHTML = `<h3>${el.id === 'pause-av' ? 'Sound' : 'Sound &amp; picture'}</h3>` + [['master', 'Master volume'], ['music', 'Music'], ['sfx', 'Effects']].map(([k, l]) =>
    `<div class="field"><label>${l}</label><output data-vo="${k}">${Math.round(S.settings[k] * 100)}</output><input type="range" data-vol="${k}" min="0" max="1" step="0.01" value="${S.settings[k]}"></div>`).join('') +
    (el.id === 'pause-av' ? '' : `<div class="field"><label>Default quality</label><div class="seg" data-q>${['low', 'medium', 'high'].map(q => `<button data-v="${q}" class="${S.sel.quality === q ? 'on' : ''}">${q}</button>`).join('')}</div></div>
     <div class="field"><label>Progress</label><button class="ibtn" id="reset-progress">Reset career</button></div>`);
  for (const r of $$('[data-vol]', el)) { paint(r); r.oninput = () => { const k = r.dataset.vol; S.settings[k] = +r.value; audio.setVolume(k, +r.value); store.set('settings', S.settings); txt($(`[data-vo="${k}"]`, el), String(Math.round(+r.value * 100))); paint(r); }; }
  const qs = $('[data-q]', el);
  if (qs) for (const b of $$('button', qs)) b.onclick = () => { S.sel.quality = b.dataset.v; saveSel(); for (const x of $$('button', qs)) x.classList.toggle('on', x === b); audio.ui('tick'); };
  const rp = $('#reset-progress', el);
  if (rp) rp.onclick = () => { if (rp.dataset.armed) { store.set('progress', { events: {} }); store.set('bestTapes', {}); toast($('#toast'), 'Career reset'); rp.textContent = 'Reset career'; delete rp.dataset.armed; } else { rp.dataset.armed = '1'; rp.textContent = 'Tap again to confirm'; } };
}
function renderSettings() { avControls($('#card-av')); }

function wireMenus() {
  $('#go-play').onclick = () => { audio.start(); audio.ui('select'); go('mode'); };
  $('#go-career').onclick = () => { audio.start(); audio.ui('select'); go('career'); };
  $('#go-settings').onclick = () => { audio.start(); audio.ui('select'); go('settings'); };
  $('#car-next').onclick = () => { audio.ui('select'); go('track'); };
  for (const b of $$('[data-back]')) b.onclick = goBack;
  $('#start').onclick = () => { audio.start(); audio.ui('start'); startSession({ ...S.sel }); };
  $('#p-resume').onclick = () => togglePause(false);
  $('#p-restart').onclick = () => { togglePause(false); restartSession(); };
  $('#p-finish').onclick = () => { togglePause(false); endSession('manual'); };
  $('#p-camera').onclick = () => { cycleCamera(); };
  $('#p-photo').onclick = () => { togglePause(false); setPhoto(true); };
  $('#p-menu').onclick = () => { togglePause(false); quitToMenu(); };
  $('#r-replay').onclick = () => { audio.ui('select'); startReplay(); };
  $('#r-retry').onclick = () => { audio.ui('select'); restartSession(); };
  $('#r-tape').onclick = () => showTape();
  $('#r-menu').onclick = () => { audio.ui('back'); quitToMenu(); };
  $('#tape-close').onclick = () => $('#tapebox').classList.remove('show');
  $('#tape-copy').onclick = async () => {
    const ta = $('#tape-text'); ta.select();
    let ok = false;
    try { await navigator.clipboard.writeText(ta.value); ok = true; } catch { try { ok = document.execCommand('copy'); } catch { ok = false; } }
    toast($('#toast'), ok ? 'Tape copied' : 'Select all and copy');
  };
  $('#rp-play').onclick = () => replayPlay(!(S.sess && S.sess.rp && S.sess.rp.playing));
  for (const b of $$('#rp-speeds [data-s]')) b.onclick = () => { if (S.sess && S.sess.rp) { S.sess.rp.speed = +b.dataset.s; for (const x of $$('#rp-speeds [data-s]')) x.classList.toggle('on', x === b); } };
  $('#rp-cam').onclick = () => cycleCamera();
  $('#rp-exit').onclick = () => exitReplay();
  const scrub = $('#rp-scrub');
  scrub.oninput = () => { const sess = S.sess; if (sess && sess.rp) { sess.rp.scrubbing = true; txt($('#rp-time'), fmtTime(+scrub.value * DT, 1)); } };
  scrub.onchange = () => { const sess = S.sess; if (sess && sess.rp) { sess.rp.scrubbing = false; seekReplay(+scrub.value); } };
  $('#ph-exp').oninput = e => { try { S.browser.setBrowserOption('Exposure', +e.target.value); } catch { /* */ } paint(e.target); };
  $('#ph-fov').oninput = e => { if (S.sess) S.sess.cam.photo.fov = +e.target.value; paint(e.target); };
  $('#ph-roll').oninput = e => { if (S.sess) S.sess.cam.photo.roll = +e.target.value; paint(e.target); };
  $('#ph-hud').onclick = () => { document.body.classList.toggle('photo-clean'); $('#photo-bar').style.opacity = document.body.classList.contains('photo-clean') ? '0.15' : ''; };
  $('#photo-bar').addEventListener('pointerenter', () => { $('#photo-bar').style.opacity = ''; });
  $('#ph-exit').onclick = () => setPhoto(false);
  for (const r of $$('#photo-bar input[type=range]')) paint(r);
}

// -------------------------------------------------------------------------------------------
// sessions
function entrantsFor(o) {
  const me = { car: o.car, tune: tuneFor(o.car), driver: 'player', slot: 0 };
  if (o.tune) me.tune = o.tune;
  if (o.mode === 'race') {
    const rivals = CAR_IDS.filter(c => c !== o.car).slice(0, 3);
    while (rivals.length < 3) rivals.push('ronin');
    const sk = clamp(+o.skill || 0.9, 0.8, 1);
    return [{ ...me, slot: 3 }, ...rivals.map((c, i) => ({ car: c, driver: 'ai', ai: 'race', skill: +(sk - [0, 0.025, 0.05][i]).toFixed(3), slot: i }))];
  }
  if (o.mode === 'tandem') return [{ car: o.car, driver: 'ai', ai: 'drift', skill: 1, slot: 0 }, { ...me, slot: 1 }];
  return [me];
}

function showLoading(on, msg = 'Loading', k = 0) {
  $('#loading').classList.toggle('show', on);
  txt($('#load-msg'), msg); $('#load-bar').style.width = (k * 100).toFixed(0) + '%';
  if (on && !$('#load-tip').textContent) $('#load-tip').textContent = TIPS[Math.floor(Math.random() * TIPS.length)];
  if (!on) $('#load-tip').textContent = '';
}

/** Load a level and start a session. o: {mode, track, car, tune?, surface, laps, skill, quality, entrants?, livery?} */
async function startSession(o, flags = {}) {
  const L = S.levels.find(l => l.id === o.track) || S.levels[0];
  o = Object.assign({ surface: 'dry', laps: 3, skill: 0.9, quality: S.sel.quality }, o, { track: L.id });
  if (!CARS[o.car]) o.car = 'ronin';
  for (const id of ['#results', '#pause', '#tapebox', '#replay-bar', '#photo-bar']) $(id).classList.remove('show');
  document.body.classList.remove('photo', 'photo-clean', 'playing');
  S.sess = null;
  showLoading(true, 'Reading circuit', 0.1);
  audio.stopEngine();
  try {
    const text = await levelText(L.id);
    showLoading(true, 'Checking bytes', 0.25);
    const sha = await sha256(text);
    const track = parseTrack(text);
    showLoading(true, 'Building world', 0.4);
    const X = S.X3D, b = S.browser, url = new URL('levels/' + L.file, BASE).href;
    let scene;
    const saved = b.baseURL;
    try { b.baseURL = url; scene = await b.createX3DFromString(text); } finally { try { b.baseURL = saved; } catch { /* */ } }
    await b.replaceWorld(scene);
    S.garage = null;
    const entrants = o.entrants || entrantsFor(o);
    const laps = o.mode === 'race' ? (+o.laps || 3) : o.mode === 'tandem' ? 2 : undefined;
    const simOpts = { track, mode: o.mode, surface: o.surface === 'wet' ? 'wet' : 'dry', laps, entrants };
    const world = new World({ X3D: X, browser: b, scene, track, manifest: S.carsMan, quality: o.quality, base: BASE });
    const playerIndex = Math.max(0, entrants.findIndex(e => e.driver === 'player'));
    showLoading(true, 'Rolling out cars', 0.6);
    await Promise.all(entrants.map((e, i) => world.addCar(i, e.car, {
      livery: i === playerIndex ? (o.livery || S.liveries[e.car] || 'factory') : (o.mode === 'tandem' ? 'sumi' : 'factory'),
      headlight: i === playerIndex && track.time !== 'noon',
    })));
    const fx = new FX({ X3D: X, browser: b, scene, world, track, quality: world.q, wet: simOpts.surface === 'wet' });
    showLoading(true, 'Smoke and lights', 0.8);
    await fx.init(entrants.length);
    if (simOpts.surface === 'wet') world.setWet(true);
    const sess = {
      o, L, text, sha, track, scene, world, fx, simOpts, playerIndex, entrants,
      sim: null, rec: [], acc: 0, phase: 'play', paused: false, photo: false, dropped: 0, steps: 0, physMs: 0,
      cam: new CameraRig(), minimap: null, tach: null, ghost: null, endAt: -1, topSpeed: 0, ended: false, flags,
      hud: {}, chainShow: 0, lastChain: 0, results: null,
    };
    sess.cam.cams = world.trackCams;
    sess.cam.setMode(flags.camera || S.settings.camera || 'chase');
    S.sess = sess;
    resetSim(sess);
    if (o.mode === 'attack' && !flags.noGhost) await loadGhost(sess);
    setupHud(sess);
    audio.startEngine(o.car);
    audio.startMusic(L.id);
    showLoading(false);
    S.screen = 'play';
    for (const el of $$('.screen')) el.classList.remove('show');
    document.body.classList.remove('menu'); document.body.classList.add('playing');
    for (const m of MODES) document.body.classList.toggle('mode-' + m.id, m.id === o.mode);
    if (sha && sha !== L.sha256) console.warn('level bytes differ from levels/MANIFEST.json', L.file);
    flash($('#flashes'), L.name, 'lap', `${MODES.find(m => m.id === o.mode).name} · ${CARS[o.car].name}${simOpts.surface === 'wet' ? ' · wet' : ''}`);
    hintsFade();
    return sess;
  } catch (e) {
    showLoading(false);
    showError('Could not start: ' + (e && e.message || e));
    console.error(e);
    throw e;
  }
}

function resetSim(sess) {
  sess.sim = createSim(sess.simOpts);
  sess.rec = []; sess.acc = 0; sess.endAt = -1; sess.ended = false; sess.topSpeed = 0; sess.results = null; sess.phase = 'play'; sess.liveSim = null; sess.hits = {};
  sess.world.snap(sess.sim);
  sess.world.resetProps && sess.world.resetProps();
  sess.fx.clearSkids();
  sess.cam.reset();
  sess.lapsDone = 0;
  clearLatch(); ctl.steer = ctl.thr = ctl.brk = 0;
}

async function restartSession() {
  const sess = S.sess; if (!sess) return;
  $('#results').classList.remove('show'); $('#replay-bar').classList.remove('show');
  if (sess.photo) setPhoto(false);
  sess.paused = false; $('#pause').classList.remove('show');
  resetSim(sess);
  if (sess.o.mode === 'attack') await loadGhost(sess);
  setupHud(sess);
  S.screen = 'play'; document.body.classList.add('playing');
  audio.startEngine(sess.o.car);
}

async function quitToMenu() {
  const sess = S.sess;
  $('#results').classList.remove('show'); $('#replay-bar').classList.remove('show'); $('#photo-bar').classList.remove('show'); $('#pause').classList.remove('show');
  document.body.classList.remove('playing', 'photo-clean');
  audio.stopEngine();
  showLoading(true, 'Back to the garage', 0.5);
  S.sess = null;
  void sess;
  await loadGarage();
  showLoading(false);
  go('title', true);
}

// ---- ghost: the best Time Attack tape for this circuit, re-simulated in a second sim -----------
async function loadGhost(sess) {
  sess.ghost = null;
  if (S.settings.ghost === false) return;
  const best = store.get('bestTapes', {})[recKey(sess.L.id, 'attack', sess.o.car, sess.simOpts.surface)];
  if (!best || !best.tape) return;
  let t;
  try { t = decodeTape(best.tape); } catch { return; }
  if (t.level_sha256 !== sess.sha || t.engine !== ENGINE_VERSION) return;
  const gs = createSim(simOptionsFromTape(t, sess.track));
  const S14 = 14, rec = new Float32Array((t.words.length + 1) * S14);
  const one = [0];
  for (let i = 0; i < t.words.length; i++) {
    one[0] = t.words[i]; step(gs, one);
    const c = gs.cars[gs.playerIndex], o = i * S14;
    rec[o] = c.x; rec[o + 1] = c.y; rec[o + 2] = c.z; rec[o + 3] = c.yaw; rec[o + 4] = c.groundPitch; rec[o + 5] = c.groundRoll; rec[o + 6] = c.bodyPitch; rec[o + 7] = c.bodyRoll;
    rec[o + 8] = c.wheels[0].steer; rec[o + 9] = c.wheels[1].steer; for (let k = 0; k < 4; k++) rec[o + 10 + k] = c.wheels[k].spin;
  }
  const bt = gs.race.bestLapTicks;
  if (!(gs.race.bestLap > 0) || bt[0] < 0) return;
  // rows from the lap start to its end; rec row i is the pose after tick i+1
  const r0 = Math.max(0, Math.floor(bt[0]) - 1), r1 = Math.min(t.words.length - 1, Math.ceil(bt[1]));
  sess.ghost = { rec: rec.slice(r0 * S14, (r1 + 1) * S14), start: bt[0] - (r0 + 1), lap: gs.race.bestLap, car: t.car, verified: hashSim(gs) === t.expect.hash };
  if (!sess.world.ghost || sess.world.ghost.id !== t.car) { sess.world.removeGhost(); await sess.world.addCar(-1, t.car, { ghost: true }); }
}

// ---- the tick -----------------------------------------------------------------------------------
function tick(sess) {
  const sim = sess.sim;
  const w = sess.phase === 'play' && !sess.ended ? inputWord() : packInput({ brake: 6 });
  clearLatch();
  sess.world.beforeTick(sim);
  step(sim, [w]);
  sess.rec.push(w);
  sess.world.afterTick(sim);
  handleEvents(sess, sim.race.events, true);
  const pc = sim.cars[sim.playerIndex];
  if (pc.speed > sess.topSpeed) sess.topSpeed = pc.speed;
}

function handleEvents(sess, events, live) {
  const sim = sess.sim, me = sim.playerIndex, F = $('#flashes');
  for (const ev of events) {
    if (ev.type === 'crash') {
      // the sim reports wall and car contact every tick it lasts: a new impact (shake, flash, the
      // impact sound in audio.js) only 150 ms after the last one or when it hits 1.5x harder; while
      // the contact goes on it is a scrape, with a spark every 3rd tick
      const g = gateImpact(sess.hits || (sess.hits = {}), ev), s = g.s, impact = g.impact;
      ev.impact = impact;
      if ((ev.wall || ev.car === me || ev.other === me) && s > 0.08 && g.spark) sess.fx.spark(ev.x, ev.y, ev.z, impact ? s * 2 : s * 0.7);
      if (impact && (ev.car === me || ev.other === me)) { sess.cam.shake(0.25 + s * 0.8); if (live && s > 0.25) { const el = $('#hitfx'); el.classList.remove('on'); void el.offsetWidth; el.classList.add('on'); } }
    }
    audio.event(ev, me);
    if (!live || ev.car !== me && ev.type !== 'countdown' && ev.type !== 'go') continue;
    switch (ev.type) {
      case 'zoneClip': flash(F, 'CLIP', 'clip', '×2 zone'); break;
      case 'zonePerfect': flash(F, 'PERFECT', 'perfect', '×3 zone'); break;
      case 'transition': flash(F, 'TRANSITION', 'trans', `×${ev.multiplier.toFixed(1)}`); bumpMult(); break;
      case 'multiplier': bumpMult(); break;
      case 'chainBank': chainEnd(sess, 'banked', ev.points); if (ev.points > 1500) flash(F, '+' + fmtScore(ev.points), 'good', 'banked'); break;
      case 'chainLost': chainEnd(sess, 'lost', ev.points); flash(F, 'CHAIN LOST', 'bad'); break;
      case 'cone': flash(F, '−250', 'bad', 'cone'); break;
      case 'lapInvalid': if (sess.o.mode === 'attack' || sess.o.mode === 'race') flash(F, 'LAP INVALID', 'bad', ev.reason === 'reset' ? 'reset' : 'track limits'); break;
      case 'lap': onLap(sess, ev); break;
      case 'sector': sectorHud(sess, ev); break;
      case 'overtake': flash(F, 'P' + ev.position, 'good', 'overtake'); break;
      case 'medal': if (sess.o.mode === 'attack' && ev.medal !== 'none') flash(F, MEDAL_LABEL[ev.medal].toUpperCase(), 'perfect', 'medal pace'); break;
      case 'go': countdownHud(sess, 'go'); break;
      case 'finish': if (ev.car === me && sess.endAt < 0) { sess.endAt = sim.tick + Math.round(1.6 * HZ); sess.ended = true; flash(F, 'FINISH', 'perfect', sess.o.mode === 'race' ? 'P' + ev.position : ''); } break;
      case 'reset': sess.world.snap(sim); sess.cam.reset(); break;
      default: break;
    }
  }
}

function onLap(sess, ev) {
  const F = $('#flashes');
  if (ev.valid) flash(F, fmtTime(ev.time), ev.best ? 'purple' : ev.delta < 0 ? 'good' : 'lap', ev.best ? 'best lap' : ev.delta ? fmtDelta(ev.delta) : `lap ${ev.lap}`);
  else flash(F, fmtTime(ev.time), 'bad', 'invalid lap');
  const mode = sess.o.mode;
  if (mode === 'attack' && ev.valid && ev.best) saveBestTape(sess, 'attack', ev.time);
  sess.lapsDone = (sess.lapsDone || 0) + 1;
  if (mode === 'attack' && sess.o.laps && sess.lapsDone >= sess.o.laps && sess.endAt < 0) { sess.endAt = sess.sim.tick + Math.round(1.4 * HZ); sess.ended = false; }
  setTimeout(() => { for (const d of $$('#h-sectors div')) { d.className = ''; } }, 2500);
}

function tapeFor(sess, upto) {
  if (sess.loadedTape) return sess.loadedTape;          // a replayed tape is handed back as it came
  // after the results, a replay owns sess.sim: the tape is the run's, so read the run's own sim
  const sim = sess.liveSim || sess.sim, L = sess.L, mode = sess.o.mode;
  const words = upto ? sess.rec.slice(0, upto) : sess.rec;
  const sm = summary(sim);
  const r = sim.race;
  const want = mode === 'rush' ? statedMedal(sim) : undefined;
  const expect = { hash: hashSim(sim), frame: sim.tick, state: goalReached(sim, mode, want, true) ? 'won' : goalState(-1, sim) };
  if (mode === 'attack') Object.assign(expect, { lapTime: r.bestLap > 0 ? +r.bestLap.toFixed(4) : null, medal: r.medal, validLaps: sm.validLaps });
  else if (mode === 'rush') Object.assign(expect, { score: sm.score, medal: want, medalReached: r.medal });
  else Object.assign(expect, { score: sm.score, position: sm.position, results: sm.results });
  return encodeTape({ level: L.file, level_sha256: sess.sha, engine: ENGINE_VERSION, hz: HZ, mode, car: sess.o.car,
    tune: sess.entrants[sess.playerIndex].tune, surface: sess.simOpts.surface, laps: sess.simOpts.laps || 0, entrants: sess.entrants, words,
    expect, note: 'recorded in the KANSEI page' });
}
function saveBestTape(sess, kind, value) {
  const all = store.get('bestTapes', {}), key = recKey(sess.L.id, kind, sess.o.car, sess.simOpts.surface), cur = all[key];
  const better = !cur || (kind === 'attack' ? value < cur.value : value > cur.value);
  if (!better) return;
  all[key] = { value, car: sess.o.car, surface: sess.simOpts.surface, when: Date.now(), tape: tapeFor(sess) };
  if (!store.set('bestTapes', all)) { delete all[key]; store.set('bestTapes', all); }
}

// ---- HUD ---------------------------------------------------------------------------------------
function setupHud(sess) {
  const sim = sess.sim, mode = sess.o.mode;
  sess.minimap = new Minimap($('#minimap'), sess.track);
  const list = sim.cars.map((c, i) => ({ cls: i === sim.playerIndex ? 'me' : mode === 'tandem' ? 'lead' : '' }));
  if (sess.ghost) list.push({ cls: 'ghost' });
  sess.minimap.setCars(list);
  $('#minimap').insertAdjacentHTML('beforeend', `<div class="tag">${sess.L.name}</div>`);
  sess.tach = new Tach($('#tach'));
  sess.tach.setCar(CARS[sess.o.car]);
  txt($('#h-mode'), `${MODES.find(m => m.id === mode).name} · ${sess.L.name}`);
  for (const d of $$('#h-sectors div')) d.className = '';
  $('#h-sectors').style.display = mode === 'attack' || mode === 'race' ? '' : 'none';
  $('#h-bank').style.display = '';
  cls($('#h-ghost'), 'on', !!sess.ghost);
  if (sess.ghost) txt($('#h-ghost'), `◇ ghost ${fmtTime(sess.ghost.lap)} · ${CARS[sess.ghost.car].name}`);
  $('#h-chain').className = '';
  $('#countdown').className = 'hp';
  camLabel(sess);
}
function bumpMult() { const m = $('#h-mult'); m.classList.remove('bump'); void m.offsetWidth; m.classList.add('bump'); }
function chainEnd(sess, kind, pts) {
  const el = $('#h-chain');
  txt($('#h-pts'), fmtScore(pts));
  el.className = kind;
  sess.chainHold = performance.now() + 900;
}
function sectorHud(sess, ev) {
  const d = $$('#h-sectors div')[ev.sector - 1]; if (!d) return;
  txt(d, ev.delta ? fmtDelta(ev.delta) : fmtTime(ev.split, 2));
  d.className = ev.best ? 'best' : ev.delta < 0 ? 'good' : ev.delta > 0 ? 'bad' : '';
}
function countdownHud(sess, what) {
  const el = $('#countdown');
  if (what === 'go') { el.className = 'hp show go'; setTimeout(() => { el.className = 'hp'; }, 900); }
}
let hintTimer = 0;
function hintsFade() { const h = $('#h-hints'); h.classList.remove('fade'); clearTimeout(hintTimer); hintTimer = setTimeout(() => h.classList.add('fade'), 6000); }
function camLabel(sess) {
  const el = $('#h-cam'); txt(el, CAMERA_LABEL[sess.cam.mode] || sess.cam.mode);
  el.classList.add('show'); clearTimeout(el.__t); el.__t = setTimeout(() => el.classList.remove('show'), 1400);
  txt($('#p-camera'), 'Camera: ' + (CAMERA_LABEL[sess.cam.mode] || sess.cam.mode).toLowerCase());
  txt($('#rp-cam'), CAMERA_LABEL[sess.cam.mode] || sess.cam.mode);
}

function updateHud(sess, t) {
  const sim = sess.sim, r = sim.race, car = sim.cars[sim.playerIndex], mode = sess.o.mode;
  sess.tach.update(car, t);
  // timer
  let time = 0, warn = false, sub = '';
  const lapT = r.lapStart >= 0 ? (sim.tick - r.lapStart) / HZ : 0;
  if (mode === 'rush') {
    time = r.phase === 'grid' ? 90 : r.timer; warn = r.phase === 'running' && r.timer < 10;
    txt($('#h-time'), r.phase === 'grid' ? '1:30.0' : fmtTime(time, 1));
    sub = r.phase === 'grid' ? '<b>Roll to start the clock</b>' : `<span>best chain <b>${fmtScore(r.bestChain)}</b></span><span>cones <b>${r.cones}</b></span>`;
  } else if (mode === 'attack') {
    txt($('#h-time'), r.lapStart >= 0 ? fmtTime(lapT, 2) : '0:00.00');
    sub = `<span>lap <b>${r.lapTimes.length + 1}</b>${sess.o.laps ? '/' + sess.o.laps : ''}</span><span>best <b>${fmtTime(r.bestLap, 2)}</b></span>`;
  } else if (mode === 'race') {
    const rt = r.raceStart >= 0 ? (sim.tick - r.raceStart) / HZ : 0;
    txt($('#h-time'), rt > 0 ? fmtTime(rt, 2) : '0:00.00');
    sub = `<span>lap <b>${Math.min(r.laps, car.lap)}</b>/${r.laps}</span><span>best <b>${fmtTime(r.bestLap, 2)}</b></span>`;
  } else if (mode === 'tandem') {
    const lead = sim.cars[r.tandem.lead];
    txt($('#h-time'), r.time > 0 ? fmtTime(r.time, 1) : '0:00.0');
    sub = `<span>lap <b>${Math.min(r.laps, lead ? lead.lap : 1)}</b>/${r.laps}</span><span>lead <b>${lead ? CARS[lead.id].name : ''}</b></span>`;
  } else {
    txt($('#h-time'), r.time > 0 ? fmtTime(r.time, 1) : '0:00.0');
    sub = `<span>top <b>${Math.round(sess.topSpeed * 3.6)}</b> km/h</span><span>${(car.distance / 1000).toFixed(1)} km</span>`;
  }
  cls($('#h-time'), 'warn', warn);
  if (sess.hud.sub !== sub) { sess.hud.sub = sub; $('#h-sub').innerHTML = sub; }
  cls($('#h-invalid'), 'on', (mode === 'attack' || mode === 'race') && !r.valid && car.cpCount >= 1);
  // drift chain
  const chainEl = $('#h-chain');
  const driftMode = mode === 'rush' || mode === 'free' || mode === 'tandem';
  if (driftMode && r.chainActive) {
    if (chainEl.className !== 'on') chainEl.className = 'on';
    txt($('#h-pts'), fmtScore(r.chain));
    txt($('#h-mult'), '×' + r.multiplier.toFixed(1));
    $('#h-grace').style.transform = `scaleX(${clamp(r.grace / 2, 0, 1).toFixed(3)})`;
  } else if (chainEl.className && (!sess.chainHold || performance.now() > sess.chainHold)) chainEl.className = '';
  // bank / position / tandem
  const T = sess.sim.race.targets;     // this run's targets: the track's, scaled for the car, grip and surface
  if (driftMode) {
    txt($('#h-bank-l'), mode === 'tandem' ? 'Tandem' : 'Banked');
    txt($('#h-bank-v'), mode === 'tandem' ? fmtScore(r.tandem.score) : fmtScore(r.banked));
    txt($('#h-bank-s'), mode === 'tandem' ? `drift ${fmtScore(r.banked)}` : `zone ${r.zone ? (r.zone.perfect ? 'PERFECT' : r.zone.clip ? 'CLIP' : (r.zone.dist).toFixed(1) + ' m') : '—'}`);
    if (mode === 'rush') {
      const next = [['bronze', T.rushBronze], ['silver', T.rushSilver], ['gold', T.rushGold], ['platinum', T.rushPlatinum]].find(([, v]) => r.banked + r.chain < v);
      txt($('#h-next'), next ? `${MEDAL_LABEL[next[0]]} at ${fmtScore(next[1])}` : 'Platinum pace');
    } else txt($('#h-next'), '');
  } else if (mode === 'attack') {
    txt($('#h-bank-l'), 'Medal targets');
    txt($('#h-bank-v'), r.medal !== 'none' ? MEDAL_LABEL[r.medal] : '—');
    txt($('#h-bank-s'), `gold ${fmtTime(T.goldLap, 1)} · silver ${fmtTime(T.silverLap, 1)}`);
    txt($('#h-next'), sess.ghost ? `ghost ${fmtTime(sess.ghost.lap, 2)}` : `bronze ${fmtTime(T.bronzeLap, 1)}`);
  } else if (mode === 'race') {
    txt($('#h-bank-l'), 'Position'); txt($('#h-bank-v'), ''); txt($('#h-bank-s'), ''); txt($('#h-next'), '');
    txt($('#h-pos-n'), 'P' + car.position); txt($('#h-pos-of'), '/' + sim.cars.length);
  }
  if (mode === 'tandem' && r.tandem) {
    const d = r.tandem.distance;
    $('#h-tmeter').style.left = clamp(d / 16, 0, 1) * 100 + '%';
    txt($('#h-tdist'), `${d.toFixed(1)} m`); txt($('#h-tgrade'), r.tandem.grade); txt($('#h-tangle'), `angle ${Math.round(r.tandem.angleMatch * 100)}%`);
  }
  // countdown lights
  if (r.phase === 'countdown') {
    const el = $('#countdown');
    if (!el.classList.contains('show')) el.className = 'hp show';
    const lit = clamp(4 - Math.ceil(r.countdown), 1, 3);
    $$('#countdown i').forEach((i, k) => cls(i, 'on', k < lit));
  }
  // the gantry's start lights follow the start: red before it, green for 3 s after the go, then dark
  if (sess.gantry === undefined) { const a = sess.world.N ? sess.world.N('A_startlights') : null; sess.gantry = a && a.material ? { m: a.material, on: '' } : null; }
  if (sess.gantry) {
    const t0 = r.startTick >= 0 ? r.startTick : r.raceStart >= 0 ? r.raceStart : -1;
    const want = r.phase === 'grid' || r.phase === 'countdown' ? 'red' : t0 >= 0 && sess.sim.tick - t0 < 360 ? 'green' : 'off';
    if (want !== sess.gantry.on) {
      sess.gantry.on = want;
      const c = { red: [0.85, 0.06, 0.03], green: [0.08, 0.9, 0.25], off: [0.06, 0.01, 0.01] }[want];
      try { sess.gantry.m.emissiveColor = new S.X3D.SFColor(...c); } catch { /* the level has no gantry lights */ }
    }
  }
}

/** Draw calls and triangles, counted by wrapping the page's WebGL draw functions (installed the
 *  first time F2 opens; X_ITE has no public counter). Also pixel ratio, drawing buffer and JS heap. */
function glStats() {
  if (S.glStats) return S.glStats;
  const st = S.glStats = { calls: 0, tris: 0, frame: { calls: 0, tris: 0 }, gl: null };
  try {
    let gl = null;
    try { gl = S.browser.getContext && S.browser.getContext(); } catch { gl = null; }
    if (!gl) { const cv = $('#canvas').shadowRoot && $('#canvas').shadowRoot.querySelector('canvas'); gl = cv && (cv.getContext('webgl2') || cv.getContext('webgl')); }
    if (!gl) return st;
    st.gl = gl;
    const count = (mode, n, inst) => { st.calls++; if (mode === gl.TRIANGLES) st.tris += (n / 3) * inst; else if (mode === gl.TRIANGLE_STRIP || mode === gl.TRIANGLE_FAN) st.tris += Math.max(0, n - 2) * inst; };
    const wrap = (name, f) => { const o = gl[name]; if (typeof o === 'function') gl[name] = function (...a) { f(a); return o.apply(this, a); }; };
    wrap('drawElements', a => count(a[0], a[1], 1));
    wrap('drawArrays', a => count(a[0], a[2], 1));
    wrap('drawElementsInstanced', a => count(a[0], a[1], a[4] || 1));
    wrap('drawArraysInstanced', a => count(a[0], a[2], a[3] || 1));
  } catch { /* stats are optional */ }
  return st;
}
function telemetryFrame(sess, ms) {
  if (!S.telemetry || !sess) return;
  const gs = glStats();
  if (gs.calls) { gs.frame = { calls: gs.calls, tris: gs.tris }; gs.calls = 0; gs.tris = 0; }
  const buf = gs.gl ? `${gs.gl.drawingBufferWidth}×${gs.gl.drawingBufferHeight}` : '—';
  const heap = performance.memory ? (performance.memory.usedJSHeapSize / 1048576).toFixed(0) + ' MB' : 'n/a';
  const ft = S.frameTimes, sorted = ft.slice().sort((a, b) => a - b), p95 = sorted[Math.floor(sorted.length * 0.95)] || 0;
  const avg = ft.reduce((a, b) => a + b, 0) / (ft.length || 1);
  const car = sess.sim.cars[sess.sim.playerIndex];
  const rows = car.wheels.map((w, i) => `<tr><td class="k">${['FL', 'FR', 'RL', 'RR'][i]}</td><td>${Math.round(w.load)}</td><td>${w.temp.toFixed(0)}°</td><td>${(w.slipAngle * 57.3).toFixed(1)}°</td><td>${w.slipRatio.toFixed(2)}</td><td>${Math.round(w.grip * 100)}%</td><td>${w.surface}</td></tr>`).join('');
  const lat = car.lateralG || 0, lon = car.longG || 0;
  $('#telemetry').innerHTML = `<h4>TELEMETRY · F2</h4><table>
    <tr><td class="k">FPS</td><td>${S.fps}</td><td class="k">frame</td><td>${avg.toFixed(1)} ms</td><td class="k">P95</td><td>${p95.toFixed(1)}</td></tr>
    <tr><td class="k">physics</td><td>${sess.physMs.toFixed(2)} ms</td><td class="k">steps</td><td>${sess.steps}</td><td class="k">dropped</td><td>${sess.dropped}</td></tr>
    <tr><td class="k">tick</td><td>${sess.sim.tick}</td><td class="k">slip</td><td>${(car.slip * 57.3).toFixed(1)}°</td><td class="k">yaw</td><td>${(car.yawRate * 57.3).toFixed(0)}°/s</td></tr>
    <tr><td class="k">draws</td><td>${gs.gl ? gs.frame.calls : 'n/a'}</td><td class="k">tris</td><td>${gs.gl ? (gs.frame.tris / 1000).toFixed(0) + 'k' : 'n/a'}</td><td class="k">heap</td><td>${heap}</td></tr>
    <tr><td class="k">px ratio</td><td>${(window.devicePixelRatio || 1).toFixed(2)}</td><td class="k">buffer</td><td colspan="3">${buf} · ${sess.o.quality || S.sel.quality}</td></tr></table>
    <table style="margin-top:6px"><tr><td class="k">tyre</td><td class="k">load N</td><td class="k">temp</td><td class="k">α</td><td class="k">κ</td><td class="k">grip</td><td class="k">surf</td></tr>${rows}</table>
    <div style="display:flex;gap:12px;align-items:center"><div class="g"><i style="transform:translate(${(-lat * 28).toFixed(1)}px,${(-lon * 28).toFixed(1)}px)"></i></div>
    <div>lat <b>${lat.toFixed(2)} g</b><br>long <b>${lon.toFixed(2)} g</b><br>boost ${(car.boostPressure * 100).toFixed(0)}% · rpm ${Math.round(car.rpm)}</div></div>`;
  void ms;
}
function toggleTelemetry() { S.telemetry = !S.telemetry; cls($('#telemetry'), 'show', S.telemetry && !!S.sess); }

// ---- pause, camera, photo ------------------------------------------------------------------------
function togglePause(force) {
  const sess = S.sess; if (!sess || S.screen !== 'play' || sess.phase !== 'play') return;
  const want = force === undefined ? !sess.paused : !!force;
  if (want === sess.paused) return;
  sess.paused = want;
  if (want) { avControls($('#pause-av')); txt($('#pause-title'), `${MODES.find(m => m.id === sess.o.mode).name} · ${sess.L.name}`); }
  $('#p-finish').style.display = sess.o.mode === 'attack' || sess.o.mode === 'free' ? '' : 'none';
  cls($('#pause'), 'show', want);
  sess.fx.setPaused(want);
  audio.ui(want ? 'back' : 'select');
  sess.acc = 0;
}
function cycleCamera() {
  const sess = S.sess; if (!sess || sess.photo) return;
  if (S.screen === 'replay') {
    const order = ['replay', 'chase', 'close', 'orbit', 'hood', 'director'];
    sess.cam.setMode(order[(order.indexOf(sess.cam.mode) + 1) % order.length]);
  } else sess.cam.next();
  audio.ui('tick'); camLabel(sess);
}
function setPhoto(on) {
  const sess = S.sess; if (!sess) return;
  if (on === sess.photo) return;
  sess.photo = on;
  if (on) {
    sess.camBefore = sess.cam.mode;
    const ph = sess.cam.photo; ph.yaw = 2.5; ph.pitch = 0.14; ph.dist = 6.5; ph.roll = 0; ph.fov = 0.75;
    $('#ph-fov').value = 0.75; $('#ph-roll').value = 0;
    sess.cam.setMode('photo');
    sess.fx.setPaused(true);
  } else {
    sess.cam.setMode(sess.camBefore || 'chase');
    document.body.classList.remove('photo-clean');
    try { S.browser.setBrowserOption('Exposure', 1); } catch { /* */ }
    $('#ph-exp').value = 1;
  }
  for (const r of $$('#photo-bar input[type=range]')) paint(r);
  cls($('#photo-bar'), 'show', on);
  document.body.classList.toggle('photo', on);
  $('#photo-bar').style.opacity = '';
  camLabel(sess);
  sess.acc = 0;
}

// ---- end of a session, results ---------------------------------------------------------------
function endSession(why) {
  const sess = S.sess; if (!sess || sess.phase !== 'play') return;
  sess.phase = 'results';
  sess.liveSim = sess.sim;     // the run's own sim: a replay replaces sess.sim, tapes and records read this one
  sess.finalHash = hashSim(sess.sim);
  sess.finalTick = sess.sim.tick;
  sess.fx.setPaused(true);
  const sim = sess.sim, r = sim.race, mode = sess.o.mode, car = sim.cars[sim.playerIndex];
  let res;
  if (mode === 'rush') res = { medal: r.medal, score: Math.round(r.score), bestChain: Math.round(r.bestChain), cones: r.cones };
  else if (mode === 'attack') res = { medal: r.medal, bestLap: r.bestLap, laps: r.lapTimes };
  else if (mode === 'race') res = r.results || { position: car.position, dnf: !car.finished, finishOrder: r.finishOrder, bestLap: r.bestLap };
  else if (mode === 'tandem') res = r.results || { grade: r.tandem.grade, score: Math.round(r.tandem.score), quality: r.tandem.quality, contacts: r.tandem.contacts, drift: r.banked };
  else res = { score: Math.round(r.banked), bestChain: Math.round(r.bestChain) };
  sess.results = res;
  // progress
  let gained = 0, newBest = false;
  {
    // the record for this circuit, mode, car and surface (free roam keeps its best banked score too)
    const p = progress(), rk = recKey(sess.L.id, mode, sess.o.car, sess.simOpts.surface);
    p.records = p.records || {};
    const pr = p.records[rk];
    const v = mode === 'attack' ? res.bestLap : mode === 'race' ? (res.dnf ? 0 : res.position) : res.score;
    const better = v > 0 && (!pr || (mode === 'attack' || mode === 'race' ? v < pr.best : v > pr.best));
    if (better || (mode === 'tandem' && (!pr || 'DCBAS'.indexOf(res.grade) > 'DCBAS'.indexOf(pr.grade || 'D')))) {
      p.records[rk] = Object.assign({}, pr || {}, better ? { best: v } : {}, { when: Date.now(), medal: res.medal || (pr && pr.medal) || 'none' },
        mode === 'tandem' ? { grade: !pr || 'DCBAS'.indexOf(res.grade) > 'DCBAS'.indexOf(pr.grade || 'D') ? res.grade : pr.grade } : {});
      store.set('progress', p);
    }
    if (mode === 'free') newBest = better && !!pr;
  }
  if (mode !== 'free') {
    const p = progress(), key = sess.L.id + ':' + mode, prev = p.events[key];
    const stars = starsFor(mode, res);
    const value = mode === 'rush' ? res.score : mode === 'attack' ? res.bestLap : mode === 'race' ? res.position : res.score;
    const better = !prev || (mode === 'attack' ? value > 0 && (!(prev.best > 0) || value < prev.best) : mode === 'race' ? value < prev.best : value > prev.best);
    newBest = better && !!prev;
    const e = Object.assign({}, prev || {}, { stars: Math.max(stars, prev ? prev.stars || 0 : 0) });
    if (better && (mode !== 'attack' || value > 0)) { e.best = value; e.car = sess.o.car; }
    if (res.medal && medalRank(res.medal) > medalRank(e.medal || 'none')) e.medal = res.medal;
    if (mode === 'tandem' && (!e.grade || 'DCBAS'.indexOf(res.grade) > 'DCBAS'.indexOf(e.grade))) e.grade = res.grade;
    gained = e.stars - (prev ? prev.stars || 0 : 0);
    const before = totalStars(p);
    p.events[key] = e; store.set('progress', p);
    if (before < STAR_UNLOCK && totalStars(p) >= STAR_UNLOCK) setTimeout(() => flash($('#flashes'), 'BANSHEE UNLOCKED', 'perfect', `${STAR_UNLOCK} stars`), 900);
    if (mode === 'rush' && res.score > 0) saveBestTape(sess, 'rush', res.score);
  }
  showResults(sess, res, gained, newBest, why);
}

function showResults(sess, res, gained, newBest) {
  const mode = sess.o.mode, badge = $('#res-badge'), T = (sess.liveSim || sess.sim).race.targets;
  let title = '', sub = '', stats = [], kanji = '終', klass = '';
  if (mode === 'rush' || mode === 'attack') {
    klass = res.medal; kanji = MEDAL_KANJI[res.medal] || '無';
    title = MEDAL_LABEL[res.medal] || 'No medal';
    sub = mode === 'rush' ? `Drift rush · ${sess.L.name}` : `Time attack · ${sess.L.name}`;
  } else if (mode === 'race') { kanji = res.dnf ? '無' : ['', '一', '二', '三', '四', '五', '六'][res.position] || '—'; klass = res.position === 1 ? 'gold' : res.position <= 3 ? 'silver' : ''; title = res.dnf ? 'Did not finish' : `P${res.position} of ${sess.sim.cars.length}`; sub = `Race · ${sess.L.name}`; }
  else if (mode === 'tandem') { kanji = res.grade; klass = 'grade'; title = `Grade ${res.grade}`; sub = `Tandem · ${sess.L.name}`; }
  else { kanji = '自'; title = 'Session over'; sub = `Free roam · ${sess.L.name}`; }
  badge.className = 'medal-big ' + klass; badge.textContent = kanji;
  $('#res-title').innerHTML = `${title}<small>${sub}${gained > 0 ? ` · +${gained} ★` : ''}</small>`;
  $('#res-eyebrow').textContent = '結果 · results';
  const car = sess.sim.cars[sess.sim.playerIndex];
  if (mode === 'rush') stats = [['Score', fmtScore(res.score), newBest], ['Best chain', fmtScore(res.bestChain)], ['Cones', String(res.cones)], ['Next medal', nextRush(T, res.score)]];
  else if (mode === 'attack') stats = [['Best lap', fmtTime(res.bestLap), newBest], ['Laps', String(res.laps.length)], ['Gold', fmtTime(T.goldLap, 1)], ['Top speed', Math.round(sess.topSpeed * 3.6) + ' km/h']];
  else if (mode === 'race') stats = [['Position', res.dnf ? 'DNF' : 'P' + res.position], ['Best lap', fmtTime(res.bestLap)], ['Race time', car.finished ? fmtTime(car.raceTime) : '—'], ['Top speed', Math.round(sess.topSpeed * 3.6) + ' km/h']];
  else if (mode === 'tandem') stats = [['Tandem score', fmtScore(res.score), newBest], ['Quality', Math.round(res.quality * 100) + '%'], ['Contacts', String(res.contacts)], ['Drift points', fmtScore(res.drift)]];
  else stats = [['Banked', fmtScore(res.score)], ['Best chain', fmtScore(res.bestChain)], ['Top speed', Math.round(sess.topSpeed * 3.6) + ' km/h'], ['Distance', (car.distance / 1000).toFixed(2) + ' km']];
  $('#res-stats').innerHTML = stats.map(([k, v, n]) => `<div><span>${k}${n ? ' · new best' : ''}</span><b class="${n ? 'new' : ''}">${v}</b></div>`).join('');
  const laps = $('#res-laps');
  if (mode === 'attack' && res.laps.length) {
    laps.innerHTML = `<tr><th>Lap</th><th>S1</th><th>S2</th><th>S3</th><th>Time</th></tr>` + res.laps.map(l => `<tr class="${!l.valid ? 'invalid' : l.time === res.bestLap ? 'best' : ''}"><td>${l.lap}</td>${l.sectors.map(s => `<td>${s.toFixed(2)}</td>`).join('')}<td>${fmtTime(l.time)}</td></tr>`).join('');
  } else if (mode === 'race') {
    const order = sess.sim.race.finishOrder.concat(sess.sim.race.positions.filter(i => !sess.sim.race.finishOrder.includes(i)));
    laps.innerHTML = `<tr><th>Pos</th><th>Driver</th><th>Car</th><th>Time</th></tr>` + order.map((i, k) => { const c = sess.sim.cars[i]; return `<tr class="${i === sess.sim.playerIndex ? 'best' : ''}"><td>P${k + 1}</td><td>${i === sess.sim.playerIndex ? 'You' : RIVALS[i % RIVALS.length]}</td><td>${CARS[c.id].name}</td><td>${c.finished ? fmtTime(c.raceTime) : '—'}</td></tr>`; }).join('');
  } else laps.innerHTML = '';
  $('#res-hash').textContent = `run hash ${sess.finalHash} · ${sess.finalTick} ticks · level sha256 ${sess.sha.slice(0, 16)} · ${ENGINE_VERSION}`;
  $('#results').classList.add('show');
  $('#pause').classList.remove('show');
  S.screen = 'results';
  document.body.classList.remove('playing');
  audio.stopEngine();
}
function nextRush(T, s) {
  const n = [['Bronze', T.rushBronze], ['Silver', T.rushSilver], ['Gold', T.rushGold], ['Platinum', T.rushPlatinum]].find(([, v]) => s < v);
  return n ? `${n[0]} ${fmtScore(n[1])}` : 'all done';
}
function showTape() {
  const sess = S.sess; if (!sess) return;
  const tape = tapeFor(sess, sess.finalTick || sess.rec.length);
  $('#tape-text').value = JSON.stringify(tape);
  $('#tapebox').classList.add('show');
}

// ---- replay: re-simulate the recorded words, director cameras, slow motion, scrub ---------------
function startReplay(words, opts) {
  const sess = S.sess; if (!sess) return;
  $('#results').classList.remove('show');
  const w = words || sess.rec.slice(0, sess.finalTick || sess.rec.length);
  sess.rp = { words: w, pos: 0, speed: 1, playing: true, acc: 0, hash: opts && opts.hash || sess.finalHash, verified: null, lastHash: '' };
  sess.sim = createSim(sess.simOpts); sess.hits = {};
  sess.world.resetProps && sess.world.resetProps();
  sess.world.snap(sess.sim);
  sess.fx.clearSkids();
  sess.cam.reset();
  sess.cam.setMode('replay');
  sess.phase = 'replay';
  S.screen = 'replay';
  document.body.classList.add('playing');
  $('#rp-scrub').max = String(w.length);
  txt($('#rp-ok'), 're-simulating…');
  $('#replay-bar').classList.add('show');
  for (const x of $$('#rp-speeds [data-s]')) x.classList.toggle('on', x.dataset.s === '1');
  audio.startEngine(sess.o.car);
  camLabel(sess);
}
function replayPlay(on) {
  const sess = S.sess; if (!sess || !sess.rp) return;
  if (on && sess.rp.pos >= sess.rp.words.length) seekReplay(0);
  sess.rp.playing = on; txt($('#rp-play'), on ? '❚❚' : '▶');
}
function replayStep(sess, n, events) {
  const rp = sess.rp, one = [0];
  for (let k = 0; k < n && rp.pos < rp.words.length; k++) {
    one[0] = rp.words[rp.pos++];
    sess.world.beforeTick(sess.sim);
    step(sess.sim, one);
    sess.world.afterTick(sess.sim);
    if (events) handleEvents(sess, sess.sim.race.events, false);
  }
  if (rp.pos >= rp.words.length && rp.verified === null) {
    const h = hashSim(sess.sim);
    rp.verified = !rp.hash || h === rp.hash;
    txt($('#rp-ok'), rp.hash ? (rp.verified ? `✓ re-simulated · hash ${h}` : `✗ hash ${h} ≠ ${rp.hash}`) : `hash ${h}`);
    rp.playing = false; txt($('#rp-play'), '▶');
  }
}
function seekReplay(tickTo) {
  const sess = S.sess; if (!sess || !sess.rp) return;
  const rp = sess.rp;
  tickTo = clamp(Math.round(tickTo), 0, rp.words.length);
  if (tickTo < rp.pos) { sess.sim = createSim(sess.simOpts); rp.pos = 0; sess.world.resetProps && sess.world.resetProps(); rp.verified = null; }
  replayStep(sess, tickTo - rp.pos, false);
  sess.world.snap(sess.sim);
  sess.fx.clearSkids();
  sess.cam.reset();
  rp.acc = 0;
}
function exitReplay() {
  const sess = S.sess; if (!sess) return;
  $('#replay-bar').classList.remove('show');
  sess.phase = 'results'; sess.rp = null;
  audio.stopEngine();
  if (sess.flags.tapeOnly) { quitToMenu(); return; }
  document.body.classList.remove('playing');
  $('#results').classList.add('show');
  S.screen = 'results';
}

// ---- the frame loop ----------------------------------------------------------------------------
function frame(now) {
  requestAnimationFrame(frame);
  const dtWall = clamp((now - (S.last || now)) / 1000, 0, 0.25);
  S.last = now;
  S.frameTimes.push(dtWall * 1000); if (S.frameTimes.length > 120) S.frameTimes.shift();
  S.fpsN++; S.fpsT += dtWall; if (S.fpsT >= 1) { S.fps = Math.round(S.fpsN / S.fpsT); S.fpsN = 0; S.fpsT = 0; }
  const sess = S.sess;
  if (!sess || S.screen === 'results' || sess.paused) menuPadPoll(dtWall);
  if (!sess) { garageFrame(dtWall); return; }
  if (sess.witness) return;
  const t0 = performance.now();
  let steps = 0, dtSim = dtWall;
  if (sess.phase === 'play' && !sess.paused && !sess.photo) {
    sess.acc += dtWall;
    while (sess.acc >= DT && steps < 12) { tick(sess); sess.acc -= DT; steps++; }
    if (sess.acc >= DT) { sess.dropped += Math.floor(sess.acc / DT); sess.acc = 0; }
    if (sess.endAt >= 0 && sess.sim.tick >= sess.endAt) endSession('finish');
  } else if (sess.phase === 'replay' && sess.rp) {
    const rp = sess.rp;
    dtSim = dtWall * rp.speed;
    if (rp.playing && !rp.scrubbing) {
      rp.acc += dtSim;
      let n = Math.floor(rp.acc / DT); const cap = rp.speed > 1 ? 24 : 12;
      if (n > cap) { n = cap; rp.acc = 0; } else rp.acc -= n * DT;
      replayStep(sess, n, true); steps = n;
    }
    const sc = $('#rp-scrub'); if (!rp.scrubbing && +sc.value !== rp.pos) sc.value = String(rp.pos);
    if (!rp.scrubbing) txt($('#rp-time'), `${fmtTime(rp.pos * DT, 1)} / ${fmtTime(rp.words.length * DT, 1)}`);
  } else dtSim = 0;
  sess.physMs = performance.now() - t0; sess.steps = steps;
  renderFrame(sess, dtWall, dtSim, now / 1000);
}

function renderFrame(sess, dtWall, dtSim, t) {
  const sim = sess.sim;
  const alpha = sess.phase === 'play' ? clamp(sess.acc / DT, 0, 1) : sess.phase === 'replay' && sess.rp ? clamp(sess.rp.acc / DT, 0, 1) : 1;
  const poses = sess.world.frame(sim, alpha, dtSim, sim.tick);
  const me = poses[sim.playerIndex];
  let gp = null;
  if (sess.ghost && sim.race.lapStart >= 0 && sess.o.mode === 'attack') {
    const rowF = (sim.tick - 1 + alpha) - sim.race.lapStart + sess.ghost.start;
    gp = sess.world.ghostFrame(sess.ghost.rec, Math.floor(rowF), rowF - Math.floor(rowF));
  } else if (sess.world.ghost) sess.world.ghostFrame(null, -1, 0);
  const car = sim.cars[sim.playerIndex], spec = S.carsMan.cars.find(c => c.id === sess.o.car);
  const camDt = sess.photo || sess.paused ? dtWall : Math.max(dtSim, 0);
  if (me) {
    const p = { ...me, boost: car.boostActive };
    sess.cam.tallTan = innerHeight > innerWidth * 1.3 ? 0.38 : 0;
    const view = sess.cam.update(p, spec, camDt || 1e-4, { rumble: car.wheels.some(w => w.surf === 1) ? clamp(car.speed / 30, 0, 1) : 0 });
    sess.world.camera(view);
    sess.fx.update(sim, poses, view.pos, dtSim, { paused: sess.paused || sess.photo || dtSim === 0 });
  }
  if (sess.minimap) { const list = poses.slice(); if (sess.ghost) list.push(gp); sess.minimap.update(list, sim.race.nextCheckpoint); }
  if (S.screen === 'play' || S.screen === 'replay') updateHud(sess, t);
  cls(document.body, 'boosting', !!car.boostActive && sess.phase !== 'results');
  const sp = clamp((car.speed * 3.6 - 120) / 140, 0, 1);
  if (Math.abs(sp - (sess.spdFx || 0)) > 0.04) { sess.spdFx = sp; $('#speedfx').style.opacity = (sp * 0.55).toFixed(2); }
  const level = sess.paused || sess.photo || sess.phase === 'results' ? 0 : 1;
  audio.updateEngine(car, level, sess.phase === 'replay' && sess.rp ? sess.rp.speed : 1);
  telemetryFrame(sess, dtWall * 1000);
}

function showError(msg) { $('#err').textContent = msg; S.errors.push(msg); }

// ---- tape modes for the tools (browser witness, stills, clips) ----------------------------------
async function tapeMode(url) {
  const raw = await (await fetch(url)).json();
  const tape = decodeTape(raw);
  const L = S.levels.find(l => l.file === tape.level) || S.levels[0];
  const witness = Q.get('witness') === '1';
  const quality = Q.get('quality') || (witness ? 'low' : 'medium');
  const sess = await startSession({ mode: tape.mode, track: L.id, car: tape.car, surface: tape.surface, laps: tape.laps, entrants: tape.entrants, quality },
    { noGhost: true, camera: Q.get('cam') || 'chase', tapeOnly: true });
  sess.simOpts = Object.assign({}, simOptionsFromTape(tape, sess.track));
  sess.sim = createSim(sess.simOpts); sess.world.snap(sess.sim);
  if (Q.get('hud') === '0') document.body.classList.add('photo-clean');
  if (Q.get('cam')) sess.cam.setMode(Q.get('cam'));
  const shaOk = sess.sha === tape.level_sha256;
  if (witness) {
    sess.witness = true;
    const chunk = Math.max(1, +(Q.get('chunk') || 37));
    const t0 = performance.now(); let frames = 0, pos = 0, goalTick = -1;
    const one = [0], want = tape.expect && tape.expect.medal ? tape.expect.medal : 'gold';
    await new Promise(res => {
      const go = now => {
        const sim = sess.sim;
        for (let k = 0; k < chunk && pos < tape.words.length; k++, pos++) {
          one[0] = tape.words[pos];
          sess.world.beforeTick(sim); step(sim, one); sess.world.afterTick(sim);
          handleEvents(sess, sim.race.events, false);
          if (goalTick < 0 && goalReached(sim, tape.mode, want, pos === tape.words.length - 1)) goalTick = sim.tick;
        }
        renderFrame(sess, 1 / 30, chunk * DT, now / 1000); frames++;
        if (pos < tape.words.length) requestAnimationFrame(go); else res();
      };
      requestAnimationFrame(go);
    });
    const state = goalState(goalTick, sess.sim);
    window.__witness = { ...summary(sess.sim), state, level_sha256_ok: shaOk, frames_rendered: frames, ticks_per_frame: chunk,
      wall_ms: Math.round(performance.now() - t0), x_ite: S.browser.version, engine: ENGINE_VERSION, page_errors: S.errors.slice() };
    return;
  }
  // stills and clips: advance to `frame`, then `stride` ticks per window.__advance()
  sess.witness = true;   // the page loop stays out of the way; the tool drives frames
  const upto = +(Q.get('frame') || 0), stride = +(Q.get('stride') || 4);
  let pos = 0;
  const one = [0];
  const adv = (n, render) => {
    for (let k = 0; k < n && pos < tape.words.length; k++, pos++) {
      one[0] = tape.words[pos]; sess.world.beforeTick(sess.sim); step(sess.sim, one); sess.world.afterTick(sess.sim);
      handleEvents(sess, sess.sim.race.events, !!render);
      if (render && k % 2 === 1) renderFrame(sess, 2 * DT, 2 * DT, performance.now() / 1000);
    }
  };
  // the last `live` frames (12 ticks = 0.1 s each, the longest step X_ITE particles take per frame) are drawn one
  // by one, so tyre smoke has a short real history in the still
  const LT = 12, live = Math.max(0, Math.min(+(Q.get('live') ?? 4), Math.floor(upto / LT)));
  const warm = Math.min(upto - live * LT, 360);
  adv(upto - live * LT - warm, false);
  sess.world.snap(sess.sim); sess.fx.clearSkids(); sess.cam.reset();
  adv(warm, true);
  const nextFrame = () => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
  // particles step by 1 / frame rate (at most 0.1 s); here a drawn frame stands for n ticks of tape time, so the
  // browser reports the matching rate and smoke ages with the tape, not with the wall clock
  const tapeRate = n => { try { S.browser.getCurrentFrameRate = () => Math.max(10, 120 / n); } catch { /* read-only build */ } };
  tapeRate(LT);
  for (let i = 0; i < live; i++) { adv(LT, false); renderFrame(sess, LT * DT, LT * DT, performance.now() / 1000); await nextFrame(); }
  renderFrame(sess, DT, DT, performance.now() / 1000);
  S.screen = 'play'; document.body.classList.add('playing');
  window.__advance = (n = stride) => { tapeRate(n); adv(n, false); renderFrame(sess, n * DT, n * DT, performance.now() / 1000); return { pos, done: pos >= tape.words.length, ...summary(sess.sim) }; };
  window.__ready = { pos, ...summary(sess.sim), level_sha256_ok: shaOk };
}

// ---- the test hook ---------------------------------------------------------------------------------
window.KANSEI = {
  ready: false,
  state() {
    const sess = S.sess;
    const base = { screen: S.screen, engine: ENGINE_VERSION, errors: S.errors.slice(), stars: totalStars(), sel: { ...S.sel }, fps: S.fps, audio: audio.ctx ? audio.ctx.state : 'none', music: audio.song ? audio.song.id : null };
    if (!sess) return base;
    const sim = sess.sim, car = sim.cars[sim.playerIndex], r = sim.race;
    return Object.assign(base, {
      mode: sess.o.mode, track: sess.L.id, car: sess.o.car, phase: sess.phase, racePhase: r.phase, tick: sim.tick, paused: sess.paused, photo: sess.photo,
      camera: sess.cam.mode, kmh: Math.round(car.speed * 3.6), gear: car.gear, rpm: Math.round(car.rpm), slipDeg: +(car.slip * 57.2958).toFixed(1), drifting: car.drifting,
      score: Math.round(r.score), banked: Math.round(r.banked), chain: Math.round(r.chain), chainActive: r.chainActive, multiplier: r.multiplier,
      lap: car.lap, laps: r.lapTimes.length, bestLap: r.bestLap, position: car.position, timer: r.timer, medal: r.medal, ghost: !!sess.ghost,
      dropped: sess.dropped, results: sess.results, hash: hashSim(sim), sha_ok: sess.sha === sess.L.sha256,
      replay: sess.rp ? { pos: sess.rp.pos, of: sess.rp.words.length, speed: sess.rp.speed, playing: sess.rp.playing, verified: sess.rp.verified } : null,
      hud: { time: $('#h-time').textContent, sub: $('#h-sub').textContent, pts: $('#h-pts').textContent, chain: $('#h-chain').className, bank: $('#h-bank-v').textContent,
        kmh: $('#t-kmh') ? $('#t-kmh').textContent : '', gear: $('#t-gear') ? $('#t-gear').textContent : '', flashes: [...$$('#flashes .flash b')].map(b => b.textContent), cam: $('#h-cam').textContent },
    });
  },
  async start(opts = {}) {
    audio.start();
    const o = Object.assign({ ...S.sel }, opts);
    const sess = await startSession(o, { camera: opts.camera });
    return { ok: !!sess, tick: sess.sim.tick };
  },
  async replay(tape) {
    const raw = typeof tape === 'string' ? JSON.parse(tape) : tape;
    const t = decodeTape(raw);
    const L = S.levels.find(l => l.file === t.level) || S.levels[0];
    const sess = await startSession({ mode: t.mode, track: L.id, car: t.car, surface: t.surface, laps: t.laps, entrants: t.entrants }, { noGhost: true, tapeOnly: true });
    sess.simOpts = simOptionsFromTape(t, sess.track);
    sess.finalTick = t.words.length;
    sess.loadedTape = raw;
    startReplay(Array.from(t.words), { hash: t.expect && t.expect.hash });
    return { ok: true, ticks: t.words.length, sha_ok: sess.sha === t.level_sha256 };
  },
  input(o) { S.testInput = o ? { ...o } : null; },
  press(code) { dispatchEvent(new KeyboardEvent('keydown', { code, key: code })); dispatchEvent(new KeyboardEvent('keyup', { code, key: code })); },
  go(screen, o = {}) {
    go(screen);
    if (o.instant && S.garage) { S.garage.cam.t = 1; S.garage.cam.placed = false; garageFrame(0); }
    return S.screen;
  },
  click(sel) { const el = $(sel); if (!el) return false; el.click(); return true; },
  end() { endSession('manual'); return !!(S.sess && S.sess.results); },
  photo(on = true) { setPhoto(!!on); return !!(S.sess && S.sess.photo); },
  tape() { return S.sess ? tapeFor(S.sess, S.sess.finalTick || S.sess.rec.length) : null; },
  seek(t) { seekReplay(t); return S.sess && S.sess.rp ? S.sess.rp.pos : -1; },
  async menu() { await quitToMenu(); return S.screen; },
};

window.addEventListener('error', e => S.errors.push(String(e.message || e)));
window.addEventListener('unhandledrejection', e => S.errors.push(String(e.reason && e.reason.message || e.reason)));
requestAnimationFrame(frame);
boot().catch(e => { console.error(e); showError('Could not start: ' + (e && e.message || e)); });
