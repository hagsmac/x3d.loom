// KANSEI picture side: every sound is synthesised with WebAudio (no files). Engine: a harmonic stack
// at the firing frequency with per-car character (cylinders, sub-order lump, intake rasp), through a
// load-driven waveshaper and filter. Turbo whistle and blow-off flutter, backfire pops, tyre squeal from
// slip and load, curb and gravel rumble, wind, shift clunks, impacts, cone knocks, UI ticks, countdown
// beeps and a small step-sequenced music loop per circuit. Free to use Math.random (never in the sim).

const clamp = (v, lo, hi) => (v < lo ? lo : v > hi ? hi : v);
const VOICE = {
  koi: { cyl: 4, sub: 0.15, rasp: 0.5, drive: 2.2, bright: 1.25, gain: 0.9 },
  ronin: { cyl: 6, sub: 0.1, rasp: 0.3, drive: 1.6, bright: 1.0, gain: 0.85 },
  tempest: { cyl: 6, sub: 0.25, rasp: 0.45, drive: 2.0, bright: 0.9, gain: 0.85 },
  banshee: { cyl: 8, sub: 0.55, rasp: 0.2, drive: 2.8, bright: 0.75, gain: 1.0 },
};
// music: tempo, root (Hz), scale steps, bass pattern, mood
const SONGS = {
  'kessel-pass': { bpm: 112, root: 55, scale: [0, 3, 5, 7, 10], lead: 'tri', pad: 0.5, swing: 0.04 },
  'neon-overpass': { bpm: 124, root: 49, scale: [0, 3, 7, 8, 10], lead: 'saw', pad: 0.7, swing: 0 },
  'salt-ring': { bpm: 100, root: 58.27, scale: [0, 2, 3, 7, 9], lead: 'tri', pad: 0.4, swing: 0.08 },
  'cliffside': { bpm: 108, root: 61.74, scale: [0, 2, 4, 7, 9], lead: 'sq', pad: 0.45, swing: 0.05 },
  'practice-pad': { bpm: 96, root: 51.91, scale: [0, 3, 5, 7, 10], lead: 'tri', pad: 0.35, swing: 0.1 },
  'menu': { bpm: 88, root: 55, scale: [0, 3, 7, 10, 14], lead: 'tri', pad: 0.8, swing: 0 },
};

export class Audio {
  constructor() {
    this.ctx = null; this.vol = { master: 0.8, music: 0.5, sfx: 0.9 }; this.muted = false;
    this.engine = null; this.song = null; this.started = false;
  }
  start() {
    if (this.ctx) { if (this.ctx.state === 'suspended') this.ctx.resume().catch(() => {}); return; }
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return;
    try { this.ctx = new AC(); } catch { return; }
    const c = this.ctx;
    this.master = c.createGain(); this.master.connect(c.destination);
    const comp = c.createDynamicsCompressor(); comp.threshold.value = -14; comp.ratio.value = 4; comp.connect(this.master);
    this.sfx = c.createGain(); this.sfx.connect(comp);
    this.mus = c.createGain(); this.mus.connect(comp);
    this.applyVolume();
    // shared noise buffers
    const len = c.sampleRate * 2;
    this.white = c.createBuffer(1, len, c.sampleRate);
    this.brown = c.createBuffer(1, len, c.sampleRate);
    const w = this.white.getChannelData(0), b = this.brown.getChannelData(0);
    let last = 0;
    for (let i = 0; i < len; i++) { w[i] = Math.random() * 2 - 1; last = (last + 0.02 * w[i]) / 1.02; b[i] = last * 3.5; }
    this.shaperCurves = {};
    this.started = true;
    if (this.pendingSong) { const s = this.pendingSong; this.pendingSong = null; this.startMusic(s); }
  }
  applyVolume() {
    if (!this.ctx) return;
    const t = this.ctx.currentTime;
    this.master.gain.setTargetAtTime(this.muted ? 0 : this.vol.master, t, 0.05);
    this.sfx.gain.setTargetAtTime(this.vol.sfx, t, 0.05);
    this.mus.gain.setTargetAtTime(this.vol.music * 0.55, t, 0.05);
  }
  setVolume(k, v) { this.vol[k] = clamp(+v, 0, 1); this.applyVolume(); }
  setMuted(m) { this.muted = m; this.applyVolume(); }

  noise(brown = false, loop = true) {
    const s = this.ctx.createBufferSource(); s.buffer = brown ? this.brown : this.white; s.loop = loop;
    s.loopStart = Math.random(); return s;
  }
  curve(k) {
    if (this.shaperCurves[k]) return this.shaperCurves[k];
    const n = 1024, a = new Float32Array(n);
    for (let i = 0; i < n; i++) { const x = i / (n - 1) * 2 - 1; a[i] = Math.tanh(x * k) / Math.tanh(k); }
    return (this.shaperCurves[k] = a);
  }

  // ---- the engine and the continuous layers -----------------------------------------------
  startEngine(carId) {
    if (!this.ctx) return;
    this.stopEngine();
    const c = this.ctx, V = VOICE[carId] || VOICE.ronin, t = c.currentTime;
    const out = c.createGain(); out.gain.value = 0; out.connect(this.sfx);
    const lp = c.createBiquadFilter(); lp.type = 'lowpass'; lp.Q.value = 1.6; lp.connect(out);
    const sh = c.createWaveShaper(); sh.curve = this.curve(V.drive); sh.oversample = '2x'; sh.connect(lp);
    const pre = c.createGain(); pre.gain.value = 0.5; pre.connect(sh);
    const o1 = c.createOscillator(); o1.type = 'sawtooth';
    const o2 = c.createOscillator(); o2.type = 'square';
    const o3 = c.createOscillator(); o3.type = 'sawtooth'; o3.detune.value = 7;
    const g1 = c.createGain(), g2 = c.createGain(), g3 = c.createGain();
    g1.gain.value = 0.55; g2.gain.value = V.sub; g3.gain.value = 0.25;
    o1.connect(g1).connect(pre); o2.connect(g2).connect(pre); o3.connect(g3).connect(pre);
    // intake / exhaust rasp: band-passed noise amplitude-modulated at the firing frequency
    const nz = this.noise(); const bp = c.createBiquadFilter(); bp.type = 'bandpass'; bp.Q.value = 1.2; bp.frequency.value = 1400;
    const am = c.createGain(); am.gain.value = 0; const amOsc = c.createOscillator(); amOsc.type = 'square';
    const amDepth = c.createGain(); amDepth.gain.value = V.rasp * 0.5; amOsc.connect(amDepth).connect(am.gain);
    nz.connect(bp).connect(am).connect(lp);
    // turbo whistle + spool hiss
    const wh = c.createOscillator(); wh.type = 'sine'; const whG = c.createGain(); whG.gain.value = 0;
    wh.connect(whG).connect(this.sfx);
    // tyres: squeal (narrow band noise + a wobbling tone), gravel crunch, curb rumble, wind
    const sq = this.noise(); const sqF = c.createBiquadFilter(); sqF.type = 'bandpass'; sqF.Q.value = 9; sqF.frequency.value = 1000;
    const sqG = c.createGain(); sqG.gain.value = 0; sq.connect(sqF).connect(sqG).connect(this.sfx);
    const sqT = c.createOscillator(); sqT.type = 'triangle'; sqT.frequency.value = 900; const sqTG = c.createGain(); sqTG.gain.value = 0;
    const vib = c.createOscillator(); vib.frequency.value = 7; const vibG = c.createGain(); vibG.gain.value = 18; vib.connect(vibG).connect(sqT.frequency);
    sqT.connect(sqTG).connect(this.sfx);
    const gr = this.noise(true); const grF = c.createBiquadFilter(); grF.type = 'lowpass'; grF.frequency.value = 500; const grG = c.createGain(); grG.gain.value = 0;
    gr.connect(grF).connect(grG).connect(this.sfx);
    const rb = this.noise(true); const rbF = c.createBiquadFilter(); rbF.type = 'lowpass'; rbF.frequency.value = 140; const rbG = c.createGain(); rbG.gain.value = 0;
    const rbAm = c.createGain(); rbAm.gain.value = 0; const rbOsc = c.createOscillator(); rbOsc.type = 'square'; rbOsc.frequency.value = 20; rbOsc.connect(rbAm.gain);
    rb.connect(rbF).connect(rbAm).connect(rbG).connect(this.sfx);
    const wn = this.noise(); const wnF = c.createBiquadFilter(); wnF.type = 'highpass'; wnF.frequency.value = 700; const wnG = c.createGain(); wnG.gain.value = 0;
    wn.connect(wnF).connect(wnG).connect(this.sfx);
    // wall scrape: grinding band noise with a rough flutter, its gain follows the contact impulse
    const sc = this.noise(); const scF = c.createBiquadFilter(); scF.type = 'bandpass'; scF.Q.value = 2.2; scF.frequency.value = 2400;
    const scG = c.createGain(); scG.gain.value = 0; const scAm = c.createGain(); scAm.gain.value = 0.6;
    const scOsc = c.createOscillator(); scOsc.type = 'sawtooth'; scOsc.frequency.value = 31; const scOd = c.createGain(); scOd.gain.value = 0.4; scOsc.connect(scOd).connect(scAm.gain);
    sc.connect(scF).connect(scAm).connect(scG).connect(this.sfx);
    this.scrapeLevel = 0; this.scrapeT = -1;
    for (const s of [o1, o2, o3, nz, amOsc, wh, sq, sqT, vib, gr, rb, rbOsc, wn, sc, scOsc]) s.start(t);
    this.engine = { V, out, lp, pre, o1, o2, o3, am, amOsc, bp, wh, whG, sqF, sqG, sqT, sqTG, grG, grF, rbG, rbOsc, wnG, scG, scF, srcs: [o1, o2, o3, nz, amOsc, wh, sq, sqT, vib, gr, rb, rbOsc, wn, sc, scOsc], level: 0 };
  }
  stopEngine() {
    const e = this.engine; if (!e || !this.ctx) return;
    const t = this.ctx.currentTime;
    e.out.gain.setTargetAtTime(0, t, 0.05);
    for (const g of [e.whG, e.sqG, e.sqTG, e.grG, e.rbG, e.wnG, e.scG]) g.gain.setTargetAtTime(0, t, 0.05);
    setTimeout(() => { for (const s of e.srcs) try { s.stop(); } catch { /* */ } try { e.out.disconnect(); } catch { /* */ } }, 300);
    this.engine = null;
  }
  /** Follow the player car (read only). k: 0..1 overall level (0 while paused), slow: replay speed. */
  updateEngine(car, k = 1, slow = 1) {
    const e = this.engine; if (!e || !this.ctx) return;
    const t = this.ctx.currentTime, V = e.V, tc = 0.03;
    const rpm = Math.max(600, car.rpm) * (slow < 1 ? 0.55 + 0.45 * slow : 1);
    const f = rpm / 60 * V.cyl / 2;
    const thr = car.ctrl ? car.ctrl.throttle : 0;
    const load = clamp(thr * 0.8 + (car.boostActive ? 0.25 : 0), 0, 1);
    const limit = car.P && rpm > car.P.spec.limiterRpm - 40;
    e.o1.frequency.setTargetAtTime(f, t, tc); e.o2.frequency.setTargetAtTime(f * 0.5, t, tc); e.o3.frequency.setTargetAtTime(f * 2, t, tc);
    e.amOsc.frequency.setTargetAtTime(f, t, tc);
    e.lp.frequency.setTargetAtTime((350 + rpm * 0.32 * V.bright + load * 2600 * V.bright), t, 0.04);
    e.pre.gain.setTargetAtTime(0.35 + load * 0.55, t, 0.05);
    e.am.gain.setTargetAtTime(V.rasp * (0.15 + load * 0.5), t, 0.05);
    const lvl = k * V.gain * (0.22 + load * 0.2 + rpm / 9000 * 0.18) * (limit ? 0.6 + 0.4 * Math.random() : 1);
    e.out.gain.setTargetAtTime(lvl * 0.5, t, 0.03);
    // turbo
    const bp = car.boostPressure || 0;
    e.wh.frequency.setTargetAtTime(1600 + bp * 4200, t, 0.08);
    e.whG.gain.setTargetAtTime(k * bp * bp * 0.035 * (0.3 + thr * 0.7), t, 0.06);
    // tyres
    let sl = 0, ld = 0, off = 0, curb = 0;
    if (car.wheels) for (const w of car.wheels) {
      const s = Math.max(Math.abs(w.slipAngle) - 0.1, 0) * 2.4 + Math.max(Math.abs(w.slipRatio) - 0.12, 0) * 1.6;
      if (w.surf === 2) off += 0.25; else { sl = Math.max(sl, s); ld += w.load; }
      if (w.surf === 1) curb += 0.25;
    }
    const v = car.speed || 0;
    const loadF = car.P ? clamp(ld / (car.P.m * 9.81), 0.2, 1.3) : 1;
    const sq = clamp(sl, 0, 1) * clamp(v / 8, 0, 1) * loadF * k;
    e.sqF.frequency.setTargetAtTime(820 + clamp(sl, 0, 1.5) * 380 + v * 2, t, 0.05);
    e.sqG.gain.setTargetAtTime(sq * 0.22, t, 0.04);
    e.sqT.frequency.setTargetAtTime(760 + clamp(sl, 0, 1.5) * 260, t, 0.05);
    e.sqTG.gain.setTargetAtTime(sq * 0.035, t, 0.04);
    e.grG.gain.setTargetAtTime(k * off * clamp(v / 15, 0, 1) * 0.35, t, 0.05);
    e.grF.frequency.setTargetAtTime(300 + v * 12, t, 0.1);
    e.rbOsc.frequency.setTargetAtTime(Math.max(4, v / 0.9), t, 0.05);
    e.rbG.gain.setTargetAtTime(k * curb * clamp(v / 10, 0, 1) * 0.5, t, 0.04);
    e.wnG.gain.setTargetAtTime(k * clamp(v / 85, 0, 1) ** 2 * 0.16, t, 0.1);
    // scrape: held while contact events keep coming (within 80 ms), then fades
    const scraping = this.scrapeT >= 0 && t - this.scrapeT < 0.08;
    if (!scraping) this.scrapeLevel *= 0.8;
    e.scG.gain.setTargetAtTime(scraping ? k * clamp(this.scrapeLevel, 0.1, 1) * 0.35 * clamp(v / 6, 0.2, 1) : 0, t, scraping ? 0.03 : 0.08);
    e.scF.frequency.setTargetAtTime(1600 + v * 40, t, 0.05);
  }

  // ---- one-shots ------------------------------------------------------------------------------
  env(node, t, a, peak, d) { node.gain.setValueAtTime(0.0001, t); node.gain.exponentialRampToValueAtTime(peak, t + a); node.gain.exponentialRampToValueAtTime(0.0001, t + a + d); }
  burst({ freq = 1000, type = 'lowpass', q = 1, peak = 0.3, a = 0.003, d = 0.12, brown = false, dest = null }) {
    const c = this.ctx, t = c.currentTime, n = this.noise(brown, false), f = c.createBiquadFilter(), g = c.createGain();
    f.type = type; f.frequency.value = freq; f.Q.value = q;
    n.connect(f).connect(g).connect(dest || this.sfx); this.env(g, t, a, peak, d);
    n.start(t, Math.random()); n.stop(t + a + d + 0.05);
    return { f, g, t };
  }
  tone({ freq = 440, to = null, type = 'sine', peak = 0.2, a = 0.004, d = 0.15, at = 0, dest = null }) {
    const c = this.ctx, t = c.currentTime + at, o = c.createOscillator(), g = c.createGain();
    o.type = type; o.frequency.setValueAtTime(freq, t); if (to) o.frequency.exponentialRampToValueAtTime(to, t + a + d);
    o.connect(g).connect(dest || this.sfx); this.env(g, t, a, peak, d);
    o.start(t); o.stop(t + a + d + 0.05);
  }
  /** Sim events for the player car (and big hits from anyone). */
  event(ev, player) {
    if (!this.ctx) return;
    const mine = ev.car === player;
    switch (ev.type) {
      case 'backfire': if (mine) { this.burst({ freq: 700 + Math.random() * 500, peak: 0.45, d: 0.07, brown: false }); this.tone({ freq: 70, to: 40, peak: 0.35, d: 0.09 }); } break;
      case 'blowoff': if (mine) {
        const b = this.burst({ freq: 1500, type: 'bandpass', q: 1.6, peak: 0.16 * clamp(ev.pressure || 0.6, 0.3, 1), a: 0.01, d: 0.42 });
        const lfo = this.ctx.createOscillator(), lg = this.ctx.createGain(); lfo.type = 'square'; lfo.frequency.value = 22; lg.gain.value = 0.06;
        lfo.connect(lg).connect(b.g.gain); lfo.start(b.t); lfo.stop(b.t + 0.45);
        b.f.frequency.setValueAtTime(1900, b.t); b.f.frequency.exponentialRampToValueAtTime(700, b.t + 0.42);
      } break;
      case 'shift': if (mine) { this.tone({ freq: 95, to: 55, peak: 0.2, d: 0.06 }); this.burst({ freq: 3000, type: 'highpass', peak: 0.05, d: 0.025 }); } break;
      case 'crash': {
        const s = clamp((ev.impulse || 500) / 9000, 0.05, 1);
        if (!mine && ev.other !== player) break;
        // sustained contact feeds the scrape loop; only a fresh impact (ev.impact, set by the page's
        // rate limit) fires the one-shot thump
        this.scrapeLevel = Math.max(this.scrapeLevel || 0, s); this.scrapeT = this.ctx.currentTime;
        if (ev.impact === false) break;
        this.burst({ freq: 380 + s * 900, peak: 0.25 + s * 0.6, d: 0.18 + s * 0.3, brown: true });
        this.tone({ freq: 120, to: 45, peak: 0.2 + s * 0.4, d: 0.2 });
        if (s > 0.3) this.burst({ freq: 4200, type: 'highpass', peak: 0.12 * s, d: 0.25 });
      } break;
      case 'cone': if (mine) { this.tone({ freq: 620, to: 210, type: 'triangle', peak: 0.25, d: 0.12 }); this.burst({ freq: 2200, type: 'bandpass', q: 3, peak: 0.1, d: 0.05 }); } break;
      case 'countdown': this.tone({ freq: 520, type: 'square', peak: 0.12, d: 0.18 }); break;
      case 'go': this.tone({ freq: 1040, type: 'square', peak: 0.14, d: 0.5 }); break;
      case 'chainBank': if (mine) [0, 0.07, 0.14].forEach((at, i) => this.tone({ freq: [784, 988, 1319][i], type: 'triangle', peak: 0.1, d: 0.2, at })); break;
      case 'chainLost': if (mine) this.tone({ freq: 300, to: 120, type: 'sawtooth', peak: 0.08, d: 0.3 }); break;
      case 'zoneClip': if (mine) this.tone({ freq: 1320, type: 'sine', peak: 0.1, d: 0.15 }); break;
      case 'zonePerfect': if (mine) { this.tone({ freq: 1568, type: 'sine', peak: 0.12, d: 0.25 }); this.tone({ freq: 2093, type: 'sine', peak: 0.08, d: 0.3, at: 0.06 }); } break;
      case 'transition': if (mine) this.tone({ freq: 880, to: 1320, type: 'triangle', peak: 0.08, d: 0.12 }); break;
      case 'lap': if (mine) [0, 0.1].forEach((at, i) => this.tone({ freq: [660, 990][i], type: 'triangle', peak: 0.1, d: 0.18, at })); break;
      case 'checkpoint': if (mine) this.tone({ freq: 1180, type: 'sine', peak: 0.03, d: 0.05 }); break;
      case 'lapInvalid': if (mine) this.tone({ freq: 220, to: 160, type: 'square', peak: 0.06, d: 0.25 }); break;
      case 'overtake': if (mine) this.tone({ freq: 740, to: 1100, type: 'triangle', peak: 0.07, d: 0.15 }); break;
      case 'medal': case 'finish': if (mine) [0, 0.12, 0.24, 0.36].forEach((at, i) => this.tone({ freq: [523, 659, 784, 1047][i], type: 'triangle', peak: 0.1, d: 0.35, at })); break;
      case 'boostEmpty': if (mine) this.tone({ freq: 400, to: 200, type: 'sine', peak: 0.05, d: 0.12 }); break;
      default: break;
    }
  }
  ui(kind = 'tick') {
    if (!this.ctx) return;
    if (kind === 'tick') this.tone({ freq: 1500, type: 'sine', peak: 0.04, d: 0.03 });
    else if (kind === 'select') { this.tone({ freq: 880, type: 'triangle', peak: 0.07, d: 0.07 }); this.tone({ freq: 1320, type: 'triangle', peak: 0.06, d: 0.1, at: 0.05 }); }
    else if (kind === 'back') this.tone({ freq: 660, to: 440, type: 'triangle', peak: 0.06, d: 0.08 });
    else if (kind === 'start') { this.burst({ freq: 300, peak: 0.2, d: 0.5, brown: true }); this.tone({ freq: 55, to: 110, type: 'sawtooth', peak: 0.12, d: 0.6 }); }
  }

  // ---- music ------------------------------------------------------------------------------
  startMusic(id) {
    if (!this.ctx) { this.pendingSong = id; return; }
    if (this.song && this.song.id === id) return;
    this.stopMusic();
    const S = SONGS[id] || SONGS.menu;
    let seed = 0; for (const ch of id) seed = (seed * 31 + ch.charCodeAt(0)) >>> 0;
    const rnd = () => ((seed = (seed * 1664525 + 1013904223) >>> 0) / 4294967296);
    // a 4-bar progression of scale degrees and a 16-step pattern per voice
    const prog = [0, rnd() < 0.5 ? 3 : 2, rnd() < 0.5 ? 4 : 1, rnd() < 0.5 ? 2 : 3];
    const bass = Array.from({ length: 16 }, (_, i) => (i % 4 === 0 ? 1 : rnd() < 0.3 ? 1 : 0));
    const arp = Array.from({ length: 16 }, () => (rnd() < 0.55 ? Math.floor(rnd() * 5) : -1));
    const kick = id === 'menu' ? [1, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0] : [1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, rnd() < 0.5 ? 1 : 0];
    const step = 60 / S.bpm / 4;
    this.song = { id, S, prog, bass, arp, kick, step, next: this.ctx.currentTime + 0.1, i: 0 };
    this.song.timer = setInterval(() => this.schedule(), 60);
  }
  stopMusic() { if (this.song) { clearInterval(this.song.timer); this.song = null; } }
  schedule() {
    const s = this.song, c = this.ctx; if (!s || !c) return;
    while (s.next < c.currentTime + 0.25) {
      const i = s.i % 16, bar = Math.floor(s.i / 16) % 4, t = s.next + (i % 2 ? s.S.swing * s.step : 0);
      const deg = s.prog[bar], sc = s.S.scale, root = s.S.root;
      const note = d => root * Math.pow(2, (sc[((d % sc.length) + sc.length) % sc.length] + 12 * Math.floor(d / sc.length)) / 12);
      if (s.kick[i]) this.mtone(t, 'sine', 110, 40, 0.5, 0.18);
      if (i % 2 === 1 && s.id !== 'menu') this.mhat(t, i % 4 === 3 ? 0.06 : 0.035);
      if (s.bass[i]) this.mtone(t, 'sawtooth', note(deg) , null, 0.16, s.step * 1.6, 380);
      if (s.arp[i] >= 0) this.mtone(t, s.S.lead === 'saw' ? 'sawtooth' : s.S.lead === 'sq' ? 'square' : 'triangle', note(deg + s.arp[i] + 10), null, 0.045, s.step * 1.2, 2400);
      if (i === 0) for (const k of [0, 2, 4]) this.mtone(t, 'sawtooth', note(deg + k + 5), null, 0.03 * s.S.pad, s.step * 15, 900, 0.3);
      s.next += s.step; s.i++;
    }
  }
  mtone(t, type, f, to, peak, d, lp = 0, a = 0.005) {
    const c = this.ctx, o = c.createOscillator(), g = c.createGain();
    o.type = type; o.frequency.setValueAtTime(f, t); if (to) o.frequency.exponentialRampToValueAtTime(to, t + d);
    let n = o;
    if (lp) { const fl = c.createBiquadFilter(); fl.type = 'lowpass'; fl.frequency.value = lp; o.connect(fl); n = fl; }
    n.connect(g).connect(this.mus);
    g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(peak, t + a); g.gain.exponentialRampToValueAtTime(0.0001, t + a + d);
    o.start(t); o.stop(t + a + d + 0.05);
  }
  mhat(t, peak) {
    const c = this.ctx, n = this.noise(false, false), f = c.createBiquadFilter(), g = c.createGain();
    f.type = 'highpass'; f.frequency.value = 7000; n.connect(f).connect(g).connect(this.mus);
    g.gain.setValueAtTime(peak, t); g.gain.exponentialRampToValueAtTime(0.0001, t + 0.04);
    n.start(t, Math.random()); n.stop(t + 0.06);
  }
}
