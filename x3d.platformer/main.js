// NIB: the page. Loads a level's X3D bytes once, hands the same text to the simulation and to
// X_ITE, then runs a fixed 120 Hz tick under a render loop that only interpolates.
import { createGame, step, summary, stateHash, BTN, ENGINE_VERSION } from './engine/game.js';
import { DT, HZ } from './engine/feel.js';
import { Renderer } from './engine/render.js';
import { Audio } from './engine/audio.js';
import { decodeTape, encodeTape } from './engine/tape.js';

const Q = new URLSearchParams(location.search);
const $ = s => document.querySelector(s);
const audio = new Audio();
const store = {
  get(k, d) { try { const v = localStorage.getItem('nib.' + k); return v ? JSON.parse(v) : d; } catch { return d; } },
  set(k, v) { try { localStorage.setItem('nib.' + k, JSON.stringify(v)); } catch { /* private mode: progress is per session */ } },
};

const S = { browser: null, X3D: null, manifest: null, levels: [], idx: 0, g: null, r: null, text: '', sha: '',
  mode: 'title', paused: false, acc: 0, last: 0, rec: [], tape: null, tapePos: 0, attract: false, hintEl: null };

// ---------------------------------------------------------------------------------------------
// input: held bits plus latched presses, so a tap shorter than one frame still reaches a tick
const keys = new Set();
let latched = 0, touchBits = 0;
const KEYMAP = { ArrowLeft: BTN.L, KeyA: BTN.L, ArrowRight: BTN.R, KeyD: BTN.R, ArrowUp: BTN.U, KeyW: BTN.U,
  ArrowDown: BTN.D, KeyS: BTN.D, Space: BTN.J, KeyZ: BTN.J, KeyK: BTN.J, ShiftLeft: BTN.A, ShiftRight: BTN.A, KeyX: BTN.A, KeyJ: BTN.A, KeyL: BTN.A };
addEventListener('keydown', e => {
  audio.start();
  if (KEYMAP[e.code] !== undefined) { if (!keys.has(e.code)) latched |= KEYMAP[e.code]; keys.add(e.code); e.preventDefault(); }
  if (e.repeat) return;
  if (e.code === 'Escape' || e.code === 'KeyP') togglePause();
  if (e.code === 'KeyR' && S.mode === 'play') restart();
  if (e.code === 'KeyM') { audio.setMuted(!audio.muted); toast(audio.muted ? 'Sound off' : 'Sound on'); }
  if (e.code === 'KeyN') { audio.toggleMusic(); toast(audio.musicOn ? 'Music on' : 'Music off'); }
  if ((e.code === 'Enter' || e.code === 'Space') && S.mode === 'title') openSelect();
  if (e.code === 'Enter' && S.mode === 'win') nextLevel();
});
addEventListener('keyup', e => { keys.delete(e.code); });
addEventListener('blur', () => { keys.clear(); if (S.mode === 'play' && !S.paused) togglePause(); });

function padBits() {
  let b = 0;
  for (const p of (navigator.getGamepads ? navigator.getGamepads() : [])) {
    if (!p) continue;
    const ax = p.axes[0] || 0, ay = p.axes[1] || 0, B = i => p.buttons[i] && p.buttons[i].pressed;
    if (ax < -0.35 || B(14)) b |= BTN.L;
    if (ax > 0.35 || B(15)) b |= BTN.R;
    if (ay < -0.5 || B(12)) b |= BTN.U;
    if (ay > 0.5 || B(13) || B(1)) b |= BTN.D;
    if (B(0)) b |= BTN.J;
    if (B(2) || B(5) || B(7)) b |= BTN.A;
    if (B(9) && !S.padStart) togglePause();
    S.padStart = B(9);
  }
  return b;
}
let prevPad = 0;
function inputBits() {
  let b = touchBits;
  for (const k of keys) b |= KEYMAP[k] || 0;
  const pb = padBits(); latched |= pb & ~prevPad; prevPad = pb; b |= pb;
  return b | latched;
}

function setupTouch() {
  const coarse = matchMedia('(pointer: coarse)').matches || 'ontouchstart' in window;
  if (!coarse) return;
  document.body.classList.add('touch');
  for (const el of document.querySelectorAll('#touch [data-b]')) {
    const bit = BTN[el.dataset.b];
    const on = e => { e.preventDefault(); audio.start(); el.setPointerCapture?.(e.pointerId); touchBits |= bit; latched |= bit; el.classList.add('on'); };
    const off = e => { e.preventDefault(); touchBits &= ~bit; el.classList.remove('on'); };
    el.addEventListener('pointerdown', on); el.addEventListener('pointerup', off); el.addEventListener('pointercancel', off); el.addEventListener('pointerleave', off);
  }
}

// ---------------------------------------------------------------------------------------------
async function sha256(text) {
  const d = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return [...new Uint8Array(d)].map(x => x.toString(16).padStart(2, '0')).join('');
}

async function boot() {
  await customElements.whenDefined('x3d-canvas');
  S.X3D = window.X3D;
  const canvas = $('#canvas');
  S.browser = canvas.browser;
  const lite = Q.get('lite') === '1' || store.get('lite', false);
  try {
    S.browser.setBrowserOption('PrimitiveQuality', lite ? 'LOW' : 'HIGH');
    S.browser.setBrowserOption('TextureQuality', 'MEDIUM');
  } catch { /* older X_ITE: defaults */ }
  S.manifest = await (await fetch('levels/MANIFEST.json')).json();
  S.levels = S.manifest.levels.filter(l => !l.file.startsWith('0-0') || Q.get('lab') === '1');
  setupTouch();
  buildSelect();
  $('#ver').textContent = `${ENGINE_VERSION} · X_ITE ${S.browser.version || ''} · ${HZ} Hz fixed tick`;
  const want = Q.get('level');
  if (Q.get('tape')) return runTapeMode(Q.get('tape'));
  if (want) { const i = S.levels.findIndex(l => l.file.startsWith(want)); await loadLevel(i >= 0 ? i : 0, 'play'); }
  else { await loadLevel(0, 'title'); startAttract(); }
  requestAnimationFrame(loop);
}

async function loadLevel(i, mode) {
  S.idx = i;
  const L = S.levels[i];
  S.text = await (await fetch('levels/' + L.file)).text();
  S.sha = await sha256(S.text);
  if (S.sha !== L.sha256) console.warn('level bytes differ from MANIFEST.json', L.file);
  const scene = await S.browser.createX3DFromString(S.text);
  S.browser.replaceWorld(scene);
  S.g = createGame(S.text);
  S.r = new Renderer(S.X3D, scene, S.g);
  S.rec = []; S.acc = 0; S.mode = mode; S.paused = false; S.tape = null; S.attract = false;
  audio.startMusic(S.g.P.theme || 'meadow');
  document.body.dataset.theme = S.g.P.theme || 'meadow';
  $('#lvname').textContent = `${S.g.P.key}  ${S.g.P.title}`;
  showScreen(mode === 'play' ? null : mode);
  if (mode === 'play') banner(S.g.P.title, S.g.P.subtitle);
  updateHud(true);
  // a few picture frames so the camera settles before the first visible frame
  for (let k = 0; k < 30; k++) S.r.frame(0, 1 / 60);
}

function restart() { loadLevel(S.idx, 'play'); }
function nextLevel() { loadLevel((S.idx + 1) % S.levels.length, 'play'); }

// ---------------------------------------------------------------------------------------------
function tick() {
  let bits;
  if (S.tape) { bits = S.tape[S.tapePos] ?? 0; S.tapePos++; }
  else { bits = inputBits(); latched = 0; }
  step(S.g, bits);
  if (!S.tape) S.rec.push(bits);
  for (const ev of S.g.events) {
    S.r.handle(ev, audio);
    if (ev.type === 'goal' && S.mode === 'play' && !S.attract) setTimeout(() => showWin(), 1300);
  }
  S.g.events.length = 0;
}

function loop(now) {
  const dt = Math.min(0.1, (now - (S.last || now)) / 1000);
  S.last = now;
  if (S.g && !S.paused && (S.mode === 'play' || S.attract)) {
    S.acc += dt;
    let n = 0;
    while (S.acc >= DT && n < 12) { tick(); S.acc -= DT; n++; }
    if (n === 12) S.acc = 0;
    if (S.attract && S.tape && S.tapePos >= S.tape.length) startAttract();
  }
  if (S.r) S.r.frame(Math.min(1, S.acc / DT), dt);
  updateHud();
  requestAnimationFrame(loop);
}

// ---------------------------------------------------------------------------------------------
// HUD and screens
let hudSig = '';
function updateHud(force) {
  const g = S.g;
  if (!g) return;
  const t = g.state === 'won' ? (g.wonFrame) * DT : g.frame * DT;
  const sig = `${g.cogs}|${g.stars.join()}|${Math.floor(t * 10)}|${g.deaths}`;
  if (sig !== hudSig || force) {
    hudSig = sig;
    $('#cogs').textContent = `${g.cogs}/${g.cogsTotal}`;
    $('#stars').innerHTML = g.stars.map(s => `<span class="${s ? 'on' : ''}">★</span>`).join('');
    $('#time').textContent = fmtTime(t);
    $('#deaths').textContent = g.deaths;
  }
  // tutorial hints: the nearest sign within 4 m
  let hint = null;
  for (const e of g.entities) if (e.kind === 'hint' && Math.abs(e.x - g.hero.x) < 4 && Math.abs(e.y - g.hero.y) < 4) hint = e;
  const el = $('#hint');
  if (hint && S.mode === 'play' && !S.attract) { if (el.textContent !== hint.text) el.textContent = hint.text; el.classList.add('show'); }
  else el.classList.remove('show');
}
const fmtTime = t => `${Math.floor(t / 60)}:${(t % 60).toFixed(1).padStart(4, '0')}`;

function showScreen(id) {
  for (const el of document.querySelectorAll('.screen')) el.classList.toggle('show', el.id === id);
  document.body.classList.toggle('playing', !id);
}
function toast(msg) { const el = $('#toast'); el.textContent = msg; el.classList.add('show'); clearTimeout(toast.t); toast.t = setTimeout(() => el.classList.remove('show'), 1200); }
function banner(title, sub) {
  const el = $('#banner'); el.querySelector('b').textContent = title; el.querySelector('i').textContent = sub || '';
  el.classList.remove('show'); void el.offsetWidth; el.classList.add('show');
}

function togglePause() {
  if (S.mode !== 'play') return;
  S.paused = !S.paused;
  showScreen(S.paused ? 'pause' : null);
  audio.play('ui');
}

function rank(g) {
  const t = g.wonFrame * DT, par = g.P.par || 60, c = g.cogs / Math.max(1, g.cogsTotal);
  if (t <= par && c >= 0.9 && g.deaths === 0) return 'S';
  if (t <= par * 1.35 && c >= 0.7 && g.deaths <= 2) return 'A';
  if (t <= par * 2) return 'B';
  return 'C';
}

function showWin() {
  const g = S.g, t = g.wonFrame * DT, key = g.P.key, rk = rank(g);
  const best = store.get('best', {});
  const prev = best[key];
  const better = !prev || t < prev.time;
  best[key] = { time: better ? t : prev.time, cogs: Math.max(g.cogs, prev ? prev.cogs : 0),
    stars: Math.max(g.stars.filter(Boolean).length, prev ? prev.stars : 0), rank: !prev || 'SABC'.indexOf(rk) < 'SABC'.indexOf(prev.rank) ? rk : prev.rank };
  store.set('best', best);
  $('#w-time').textContent = fmtTime(t) + (better && prev ? '  NEW BEST' : '');
  $('#w-cogs').textContent = `${g.cogs} / ${g.cogsTotal}`;
  $('#w-stars').innerHTML = g.stars.map(s => `<span class="${s ? 'on' : ''}">★</span>`).join('');
  $('#w-deaths').textContent = g.deaths;
  $('#w-rank').textContent = rk; $('#w-rank').dataset.rank = rk;
  $('#w-hash').textContent = `run hash ${stateHash(g)} · ${g.frame} ticks · level sha256 ${S.sha.slice(0, 12)}`;
  S.mode = 'win';
  showScreen('win');
  buildSelect();
}

function saveReplay() {
  const L = S.levels[S.idx];
  const tape = encodeTape({ level: L.file, level_sha256: S.sha, engine: ENGINE_VERSION, bits: S.rec, expect: summary(S.g) });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([JSON.stringify(tape, null, 1)], { type: 'application/json' }));
  a.download = `nib-${S.g.P.key}-${fmtTime(S.g.wonFrame * DT).replace(':', 'm')}s.tape.json`;
  a.click();
}

function buildSelect() {
  const best = store.get('best', {});
  const box = $('#cards'); box.innerHTML = '';
  S.levels.forEach((L, i) => {
    const key = L.file.slice(0, 3), b = best[key];
    const card = document.createElement('button');
    card.className = 'card'; card.dataset.theme = L.theme || '';
    card.innerHTML = `<span class="num">${key}</span><b>${L.title || L.file}</b><i>${L.subtitle || ''}</i>
      <span class="best">${b ? `★ ${b.stars}/${L.counts.stars} · ${b.cogs}/${L.counts.cogs} cogs · ${fmtTime(b.time)} · <em data-rank="${b.rank}">${b.rank}</em>` : 'not cleared yet'}</span>`;
    card.onclick = () => { audio.start(); audio.play('ui'); loadLevel(i, 'play'); };
    box.appendChild(card);
  });
}

function openSelect() { audio.start(); audio.play('ui'); S.mode = 'select'; showScreen('select'); }

async function startAttract() {
  // the title screen plays a recorded tape of world 1 behind the logo
  try {
    const L = S.levels[0];
    const tape = decodeTape(await (await fetch(`tapes/${L.file.replace('.x3d', '.tape.json')}`)).json());
    if (S.g.P.key !== L.file.slice(0, 3)) await loadLevel(0, 'title');
    else { S.g = createGame(S.text); S.r = new Renderer(S.X3D, S.browser.currentScene, S.g); }
    S.tape = tape.bits; S.tapePos = 0; S.attract = true;
  } catch { S.attract = false; }
}

// ---------------------------------------------------------------------------------------------
// tape modes (used by the browser witness and by the screenshot and GIF tools)
async function runTapeMode(url) {
  const raw = await (await fetch(url)).json();
  const tape = decodeTape(raw);
  const i = Math.max(0, S.levels.findIndex(l => l.file === tape.level));
  await loadLevel(i, 'play');
  showScreen(null);
  if (Q.get('hud') === '0') document.body.classList.add('nohud');
  const shaOk = S.sha === tape.level_sha256;
  const chunk = +(Q.get('chunk') || 0);
  if (Q.get('witness') === '1') {
    // play the whole tape inside the live page: N ticks per animation frame, rendering between
    const t0 = performance.now(); let frames = 0, pos = 0;
    await new Promise(res => {
      const go = () => {
        for (let k = 0; k < chunk && pos < tape.bits.length; k++, pos++) { step(S.g, tape.bits[pos]); for (const ev of S.g.events) S.r.handle(ev, null); S.g.events.length = 0; }
        S.r.frame(1, chunk * DT); frames++;
        if (pos < tape.bits.length) requestAnimationFrame(go); else res();
      };
      requestAnimationFrame(go);
    });
    window.__witness = { ...summary(S.g), level_sha256_ok: shaOk, frames_rendered: frames, ticks_per_frame: chunk,
      wall_ms: Math.round(performance.now() - t0), x_ite: S.browser.version, user_agent: navigator.userAgent };
    return;
  }
  // still or film: advance to `frame`, then step `stride` ticks per call of window.__advance()
  const upto = +(Q.get('frame') || 0), stride = +(Q.get('stride') || 4);
  let pos = 0;
  const adv = n => { for (let k = 0; k < n && pos < tape.bits.length; k++, pos++) { step(S.g, tape.bits[pos]); for (const ev of S.g.events) S.r.handle(ev, null); S.g.events.length = 0; } };
  const warm = Math.min(upto, 240);
  adv(upto - warm);
  for (let k = 0; k < warm; k += 2) { adv(2); S.r.frame(1, 2 * DT); }
  S.r.frame(1, 1 / 60);
  updateHud(true);
  window.__advance = () => { adv(stride); S.r.frame(1, stride * DT); updateHud(); return { pos, done: pos >= tape.bits.length, ...summary(S.g) }; };
  window.__ready = { pos, ...summary(S.g), level_sha256_ok: shaOk };
}

// ---------------------------------------------------------------------------------------------
$('#start').onclick = openSelect;
$('#resume').onclick = togglePause;
$('#p-restart').onclick = () => { S.paused = false; restart(); };
$('#p-menu').onclick = () => { S.paused = false; openSelect(); };
$('#w-next').onclick = nextLevel;
$('#w-retry').onclick = restart;
$('#w-menu').onclick = openSelect;
$('#w-save').onclick = saveReplay;
$('#back').onclick = () => { S.mode = 'title'; showScreen('title'); };
$('#lite').onclick = () => { store.set('lite', !store.get('lite', false)); location.reload(); };
$('#lite').textContent = store.get('lite', false) ? 'Lite graphics: on' : 'Lite graphics: off';
document.addEventListener('visibilitychange', () => { if (document.hidden && S.mode === 'play' && !S.paused) togglePause(); });
boot().catch(e => { console.error(e); $('#err').textContent = 'Could not start: ' + e.message; });
