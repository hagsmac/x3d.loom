// Every sound is synthesised with WebAudio at run time: no audio files, nothing to license.
// The music is a small original step sequencer (one pattern set per world).

export class Audio {
  constructor() { this.ctx = null; this.muted = false; this.musicOn = true; this.last = {}; this.seqTimer = null; this.world = 'meadow'; }

  start() {
    if (this.ctx) { if (this.ctx.state === 'suspended') this.ctx.resume(); return; }
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return;
    const ctx = this.ctx = new AC();
    this.master = ctx.createGain(); this.master.gain.value = 0.8;
    const comp = ctx.createDynamicsCompressor(); comp.threshold.value = -14; comp.ratio.value = 4;
    this.master.connect(comp); comp.connect(ctx.destination);
    this.sfx = ctx.createGain(); this.sfx.gain.value = 0.9; this.sfx.connect(this.master);
    this.mus = ctx.createGain(); this.mus.gain.value = 0.22; this.mus.connect(this.master);
    // a short echo for sparkle sounds
    this.echo = ctx.createDelay(1); this.echo.delayTime.value = 0.16;
    const fb = ctx.createGain(); fb.gain.value = 0.28; const wet = ctx.createGain(); wet.gain.value = 0.35;
    this.echo.connect(fb); fb.connect(this.echo); this.echo.connect(wet); wet.connect(this.sfx);
    const len = ctx.sampleRate * 1.0, buf = ctx.createBuffer(1, len, ctx.sampleRate), d = buf.getChannelData(0);
    let s = 12345; for (let i = 0; i < len; i++) { s = (s * 1103515245 + 12345) & 0x7fffffff; d[i] = s / 0x3fffffff - 1; }
    this.noiseBuf = buf;
    if (this.musicOn) this.startMusic(this.world);
  }

  setMuted(m) { this.muted = m; if (this.master) this.master.gain.value = m ? 0 : 0.8; }
  toggleMusic() { this.musicOn = !this.musicOn; if (this.mus) this.mus.gain.value = this.musicOn ? 0.22 : 0; }

  tone(type, f0, f1, dur, vol, { at = 0, attack = 0.005, dest, curve = 'exp', detune = 0 } = {}) {
    const ctx = this.ctx, t = ctx.currentTime + at;
    const o = ctx.createOscillator(), gn = ctx.createGain();
    o.type = type; o.frequency.setValueAtTime(f0, t); o.detune.value = detune;
    if (f1 !== f0) curve === 'exp' ? o.frequency.exponentialRampToValueAtTime(Math.max(1, f1), t + dur) : o.frequency.linearRampToValueAtTime(f1, t + dur);
    gn.gain.setValueAtTime(0.0001, t); gn.gain.exponentialRampToValueAtTime(vol, t + attack);
    gn.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    o.connect(gn); gn.connect(dest || this.sfx); o.start(t); o.stop(t + dur + 0.02);
    return o;
  }

  noise(dur, vol, { at = 0, type = 'lowpass', f0 = 1200, f1 = f0, q = 0.8, dest } = {}) {
    const ctx = this.ctx, t = ctx.currentTime + at;
    const src = ctx.createBufferSource(); src.buffer = this.noiseBuf;
    const fl = ctx.createBiquadFilter(); fl.type = type; fl.Q.value = q;
    fl.frequency.setValueAtTime(f0, t); fl.frequency.exponentialRampToValueAtTime(Math.max(20, f1), t + dur);
    const gn = ctx.createGain(); gn.gain.setValueAtTime(vol, t); gn.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    src.connect(fl); fl.connect(gn); gn.connect(dest || this.sfx); src.start(t, Math.random() * 0.5); src.stop(t + dur + 0.02);
  }

  play(name, o = {}) {
    if (!this.ctx || this.muted) return;
    const now = this.ctx.currentTime;
    const gap = { thud: 0.05, cog: 0.025, land: 0.06, creak: 0.2 }[name] || 0;
    if (gap && this.last[name] && now - this.last[name] < gap) return;
    this.last[name] = now;
    const PENTA = [0, 2, 4, 7, 9, 12, 14, 16, 19, 21, 24];
    switch (name) {
      case 'jump': this.tone('square', 300, 640, 0.11, 0.09); this.tone('sine', 600, 1100, 0.08, 0.05); break;
      case 'walljump': this.tone('square', 420, 820, 0.1, 0.08); this.noise(0.08, 0.1, { type: 'highpass', f0: 3000 }); break;
      case 'land': this.noise(0.09, 0.12 + 0.25 * (o.v || 0), { f0: 900, f1: 200 }); this.tone('sine', 140, 55, 0.12, 0.12 + 0.2 * (o.v || 0)); break;
      case 'cog': { const st = PENTA[Math.min(PENTA.length - 1, (o.combo || 1) - 1)]; const f = 988 * Math.pow(2, st / 12);
        this.tone('triangle', f, f, 0.07, 0.11); this.tone('triangle', f * 1.5, f * 1.5, 0.16, 0.09, { at: 0.055, dest: this.echo }); break; }
      case 'star': [0, 4, 7, 12, 16, 19, 24].forEach((st, i) => this.tone('square', 523 * Math.pow(2, st / 12), 523 * Math.pow(2, st / 12), 0.18, 0.06, { at: i * 0.06, dest: this.echo })); break;
      case 'spring': { const sup = o.super; const os = this.tone('sine', sup ? 160 : 200, sup ? 900 : 620, sup ? 0.5 : 0.36, 0.2, { curve: 'lin' });
        const lfo = this.ctx.createOscillator(), lg = this.ctx.createGain(); lfo.frequency.value = 22; lg.gain.value = 60; lfo.connect(lg); lg.connect(os.frequency); lfo.start(); lfo.stop(now + 0.5); break; }
      case 'poundstart': this.noise(0.12, 0.12, { type: 'bandpass', f0: 600, f1: 2600, q: 2 }); this.tone('square', 900, 300, 0.1, 0.05); break;
      case 'pound': this.tone('sine', 110, 38, 0.38, 0.4); this.noise(0.3, 0.32, { f0: 1600, f1: 120 }); this.tone('square', 70, 40, 0.15, 0.08); break;
      case 'break': this.noise(0.4, 0.35, { f0: 3000, f1: 200 }); this.tone('sine', 90, 40, 0.3, 0.3); for (let i = 0; i < 4; i++) this.noise(0.05, 0.12, { at: 0.06 * i + 0.05, type: 'bandpass', f0: 1800 - i * 300, q: 3 }); break;
      case 'hook': this.noise(0.07, 0.1, { type: 'highpass', f0: 4000 }); this.tone('square', 1400, 900, 0.06, 0.05); break;
      case 'unhook': this.noise(0.1, 0.06, { type: 'bandpass', f0: 1500, f1: 600, q: 1.5 }); break;
      case 'fling': this.noise(0.25, 0.12, { type: 'bandpass', f0: 500, f1: 3000, q: 1.2 }); this.tone('triangle', 400, 900, 0.18, 0.06); break;
      case 'die': this.tone('square', 660, 110, 0.45, 0.1, { curve: 'lin' }); this.noise(0.3, 0.15, { f0: 2500, f1: 300 }); break;
      case 'respawn': [0, 7, 12].forEach((st, i) => this.tone('sine', 660 * Math.pow(2, st / 12), 660 * Math.pow(2, st / 12), 0.15, 0.08, { at: i * 0.05, dest: this.echo })); break;
      case 'checkpoint': this.tone('sine', 880, 880, 0.8, 0.12, { dest: this.echo }); this.tone('sine', 1320, 1320, 0.6, 0.06, { at: 0.02 }); this.tone('triangle', 1760, 1760, 0.4, 0.04, { at: 0.12, dest: this.echo }); break;
      case 'goal': [0, 4, 7, 12, 7, 12, 16, 19, 24].forEach((st, i) => { const f = 392 * Math.pow(2, st / 12); this.tone('square', f, f, 0.22, 0.07, { at: i * 0.09 }); this.tone('triangle', f / 2, f / 2, 0.22, 0.08, { at: i * 0.09 }); }); break;
      case 'creak': this.tone('sawtooth', 120, 90, 0.25, 0.04, { curve: 'lin' }); break;
      case 'crumble': this.noise(0.5, 0.22, { f0: 800, f1: 150 }); break;
      case 'poof': this.noise(0.2, 0.12, { type: 'bandpass', f0: 2000, f1: 500 }); break;
      case 'thud': this.tone('sine', 160, 60, 0.12, 0.08 + 0.22 * (o.v || 0)); this.noise(0.07, 0.06 + 0.15 * (o.v || 0), { f0: 700, f1: 200 }); break;
      case 'ui': this.tone('triangle', 880, 1320, 0.07, 0.07); break;
      default: break;
    }
  }

  startMusic(world) {
    this.world = world;
    if (!this.ctx) return;
    if (this.seqTimer) clearInterval(this.seqTimer);
    const SONGS = {
      // root notes per bar (MIDI), tempo, lead scale steps; all patterns written for this game
      meadow: { bpm: 116, roots: [60, 57, 53, 55], lead: [0, 4, 7, 9, 7, 4, 2, 4, 0, 2, 4, 7, 12, 9, 7, 4], wave: 'square' },
      gorge: { bpm: 104, chord: [0, 3, 7], roots: [57, 53, 50, 52], lead: [0, 3, 7, 10, 7, 3, 5, 3, 0, 7, 10, 12, 10, 7, 5, 3], wave: 'triangle' },
      spire: { bpm: 124, chord: [0, 3, 7], roots: [62, 58, 60, 57], lead: [0, 7, 12, 7, 3, 7, 10, 7, 0, 5, 12, 10, 8, 7, 3, 2], wave: 'sawtooth' },
    };
    const S = SONGS[world] || SONGS.meadow, stepDur = 60 / S.bpm / 4;
    let step = 0, next = this.ctx.currentTime + 0.1;
    const midi = m => 440 * Math.pow(2, (m - 69) / 12);
    const tick = () => {
      const ctx = this.ctx;
      while (next < ctx.currentTime + 0.25) {
        const bar = Math.floor(step / 16) % S.roots.length, s = step % 16, root = S.roots[bar];
        const at = next - ctx.currentTime;
        if (s % 4 === 0) this.tone('sine', midi(root - 24) * 2, midi(root - 24), 0.16, 0.22, { at, dest: this.mus });         // kick
        if (s % 2 === 0) this.tone('triangle', midi(root - 12), midi(root - 12), stepDur * 1.8, 0.16, { at, dest: this.mus }); // bass
        if (s % 4 === 2) this.noise(0.04, 0.06, { at, type: 'highpass', f0: 7000, dest: this.mus });                        // hat
        if (s === 4 || s === 12) this.noise(0.12, 0.09, { at, type: 'bandpass', f0: 1800, q: 0.7, dest: this.mus });       // snare
        if (s % 2 === 1 || step % 64 > 31) {
          const n = root + S.lead[(s + (step >> 4)) % 16];
          this.tone(S.wave, midi(n), midi(n), stepDur * 0.9, 0.035, { at, dest: this.mus, detune: 4 });
        }
        if (s % 8 === 0) (S.chord || [0, 4, 7]).forEach(iv => this.tone('sine', midi(root + iv), midi(root + iv), stepDur * 7, 0.018, { at, dest: this.mus, attack: 0.05 }));
        step++; next += stepDur;
      }
    };
    this.seqTimer = setInterval(tick, 50);
    tick();
  }
}
