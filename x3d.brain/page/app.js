/* Neural Canvas: page logic for the Brain Loom demo (X_ITE 16.6.0, plain JavaScript, no build step).
   Every callback that X_ITE, the DOM, a timer or a promise can invoke goes through guard() (Loom FM73/84/89): a throw is logged to the
   session log and shown as a toast, it never stops the render loop or the other buttons.
   Scene contract: x3d.brain/tools/check_contract.py (DEF names). The page adapts to what the scene really contains: a missing DEF disables
   the control that needs it instead of throwing. Window.__loom is a small read-only debug/test handle. */
(function () {
  'use strict';

  var CFG = window.PAGE_CONFIG || {};
  var X3D_ = null;           // window.X3D once X_ITE has loaded
  var B = null;              // X3DBrowser

  // ------------------------------------------------------------------------------------------------ tiny helpers
  function $(s, r) { return (r || document).querySelector(s); }
  function $$(s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); }
  function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }
  function clamp(x, a, b) { return Math.max(a, Math.min(b, x)); }
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
  function title(s) { s = String(s || '').replace(/_/g, ' '); return s.charAt(0).toUpperCase() + s.slice(1); }
  function fmtBytes(n) { return n >= 1048576 ? (n / 1048576).toFixed(1) + ' MB' : Math.max(1, Math.round(n / 1024)) + ' kB'; }
  function fmtNum(n) { return Number(n).toLocaleString('en-US'); }
  function reducedMotion() { try { return window.matchMedia('(prefers-reduced-motion: reduce)').matches; } catch (e) { return false; } }
  function isPhone() { try { return window.matchMedia('(max-width: 640px)').matches; } catch (e) { return false; } }
  function store(k, v) { try { if (v === undefined) return window.localStorage.getItem('nc.' + k); window.localStorage.setItem('nc.' + k, v); } catch (e) { /* private window or blocked storage */ } return null; }

  function el(tag, attrs) {
    var n = document.createElement(tag);
    if (attrs) Object.keys(attrs).forEach(function (k) {
      var v = attrs[k];
      if (v == null || v === false) return;
      if (k === 'class') n.className = v;
      else if (k === 'text') n.textContent = v;
      else if (k === 'html') n.innerHTML = v;
      else if (k === 'style') n.setAttribute('style', v);
      else if (k.slice(0, 2) === 'on') n.addEventListener(k.slice(2), guard(v, k));
      else n.setAttribute(k, v === true ? '' : v);
    });
    for (var i = 2; i < arguments.length; i++) {
      var c = arguments[i];
      if (c == null) continue;
      n.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
    }
    return n;
  }

  // ------------------------------------------------------------------------------------------------ session log + guard
  var LOG = [];
  var errCount = 0, errSeen = {};
  function log(level, msg) {
    LOG.push({ t: Math.round(performance.now()), level: level, msg: String(msg) });
    if (LOG.length > 300) LOG.shift();
    if (level === 'error') { try { console.error('[page] ' + msg); } catch (e) { /* console missing */ } }
    if (dlgOpen() && !$('#paneSession').hidden) renderSession();
  }
  function report(label, e) {
    var msg = (e && e.message) ? e.message : String(e);
    log('error', label + ': ' + msg);
    errCount++;
    var key = label + '|' + msg;
    if (!errSeen[key]) { errSeen[key] = 1; toast('Something went wrong in "' + label + '". The rest of the page still works. Details are in the Loom log.', 6000); }
    if (errCount === 8) showBanner('Several things went wrong', 'The page keeps running, but some controls may not respond. Reload to start fresh.', null);
  }
  function guard(fn, label) {
    return function () {
      try {
        var r = fn.apply(this, arguments);
        if (r && typeof r.then === 'function') r.then(null, function (e) { report(label || 'callback', e); });
        return r;
      } catch (e) { report(label || 'callback', e); }
    };
  }
  function on(target, type, fn, label, opts) { if (target) target.addEventListener(type, guard(fn, label || type), opts); }
  function later(fn, ms, label) { return setTimeout(guard(fn, label || 'timer'), ms); }
  function every(fn, ms, label) { return setInterval(guard(fn, label || 'interval'), ms); }
  function frame() { return new Promise(function (r) { requestAnimationFrame(function () { r(); }); }); }
  function nextFrames(n) {
    return (async function () { for (var i = 0; i < n; i++) { if (B && B.nextFrame) await Promise.race([B.nextFrame(), sleep(4000)]); else await frame(); } })();
  }
  function withTimeout(p, ms, what) {
    return new Promise(function (res, rej) {
      var t = setTimeout(function () { rej(new Error(what + ' took longer than ' + Math.round(ms / 1000) + ' s')); }, ms);
      p.then(function (v) { clearTimeout(t); res(v); }, function (e) { clearTimeout(t); rej(e); });
    });
  }
  window.addEventListener('error', guard(function (ev) { if (ev && ev.message && !/ResizeObserver/.test(ev.message)) log('error', 'window: ' + ev.message); }, 'window.error'));
  window.addEventListener('unhandledrejection', guard(function (ev) { log('error', 'unhandled: ' + (ev.reason && ev.reason.message ? ev.reason.message : ev.reason)); }, 'unhandledrejection'));

  // ------------------------------------------------------------------------------------------------ state
  var S = {
    kind: 'brain',            // brain | torso
    scene: null, nodes: {}, missing: {},
    data: {},                 // regions, facts, looks, tour, presets, torso, prov
    sw: {}, baseSw: {},       // Switch DEF -> whichChoice (0 shown, -1 hidden)
    glow: true, clip: false, baseGlow: true,
    touched: {},              // "DEF.field" -> {name, field, v} original values for restore
    lookId: null, prevLookImg: null,
    tourActive: false, tourIdx: -1, pre: null, presetOps: [],
    region: null, hover: null, regionPref: 'L',
    audio: { on: false, ok: false },
    cam: { vps: [], i: 0, name: 'VP_HOME', autoHidLeft: false },
    sheet: null, loadToken: 0, ready: false, quality: 'balanced',
    sensors: [], pin: null, ptr: { x: 0, y: 0, downX: 0, downY: 0, moved: 0, downT: 0, type: 'mouse' }
  };

  var BRAIN_LAYERS = [
    { key: 'glass', label: 'Glass cortex', def: 'SW_CORTEX', hint: 'See-through cortex with a fresnel rim' },
    { key: 'wet', label: 'Wet cortex', def: 'SW_WET', hint: 'Opaque glossy cortex' },
    { key: 'deep', label: 'Deep structures', def: 'SW_DEEP', hint: 'Thalamus, basal ganglia, hippocampus, ventricles, brainstem, cerebellum' },
    { key: 'tracts', label: 'Tracts', def: 'SW_TRACTS', tag: 'SYN', tagTitle: 'Synthetic: generated arcs, not tractography', hint: 'Synthetic fibre arcs' },
    { key: 'slices', label: 'MRI slices', def: 'SW_SLICES', hint: 'Six slices of the template T1 image' },
    { key: 'labels', label: 'Labels', def: 'SW_LABELS', hint: 'Region names' },
    { key: 'activation', label: 'Activation', def: 'SW_ACTIV', tag: 'ILL', tagTitle: 'Illustrative: placed glows, not measured activity', hint: 'Illustrative activation glows' }
  ];
  var MAIN_DEF = {};  // layer key -> switch DEF, may be overridden by tour.layer_switches
  BRAIN_LAYERS.forEach(function (l) { MAIN_DEF[l.key] = l.def; });
  var ALL_SW = ['SW_CORTEX', 'SW_WET', 'SW_DEEP', 'SW_TRACTS', 'SW_SLICES', 'SW_LABELS', 'SW_ACTIV', 'SW_AURA', 'SW_HEMI_L', 'SW_HEMI_R', 'SW_WETHEMI_L', 'SW_WETHEMI_R',
    'SW_PEDESTAL', 'SW_STAGE', 'SW_LBL_L', 'SW_LBL_R', 'SW_LBL_DEEP', 'SW_LBLLINES_L', 'SW_LBLLINES_R'];
  var VIEW_LABELS = { VP_HOME: 'Home', VP_LEFT: 'Left', VP_RIGHT: 'Right', VP_TOP: 'Top', VP_FRONT: 'Front', VP_MEDIAL: 'Medial', VP_INSIDE: 'Inside', VP_BACK: 'Back', VP_CHEST: 'Chest', VP_HEART: 'Heart', VP_HEAD: 'Head' };
  var TORSO_LAYER_LABELS = {
    SW_SKIN: 'Skin', SW_RIBCAGE: 'Ribcage', SW_SPINE: 'Spine', SW_GIRDLES: 'Shoulders and pelvis', SW_SKULL: 'Skull', SW_BRAIN: 'Brain (template)',
    SW_BRAIN_CT: 'Brain (CT mask)', SW_LUNGS: 'Lungs', SW_LUNGVESSELS: 'Lung vessels', SW_AIRWAY: 'Airway', SW_HEART: 'Heart', SW_VESSELS: 'Great vessels',
    SW_ORGANS: 'Organs', SW_VISCERA: 'Bowel'
  };
  var TORSO_GROUP_ACCENT = { SKIN: '#5bc0eb', RIBCAGE: '#9ad1ff', SPINE: '#9ad1ff', LIMBGIRDLE: '#9ad1ff', SKULL: '#cfe3ff', BRAIN: '#c792ff', BRAINCT: '#c792ff', LUNGS: '#8fd3ff',
    LUNGVESSELS: '#ff9a7a', AIRWAY: '#7fe6fb', HEART: '#ff6b57', VESSELS: '#ff7a66', ORGANS: '#ffb454', VISCERA: '#e8c27a' };
  var TORSO_GROUP_NAME = { SKIN: 'Skin', RIBCAGE: 'Ribcage', SPINE: 'Spine', LIMBGIRDLE: 'Shoulder and pelvic girdle', SKULL: 'Skull', BRAIN: 'Brain (template fit)', BRAINCT: 'Brain (CT mask)',
    LUNGS: 'Lungs', LUNGVESSELS: 'Lung vessels', AIRWAY: 'Airway', HEART: 'Heart', VESSELS: 'Vessels', ORGANS: 'Organs', VISCERA: 'Bowel' };
  var FACT_TABS = [['function', 'Function'], ['fact', 'Fact'], ['clinical', 'Clinical'], ['imaging', 'Imaging']];

  // ------------------------------------------------------------------------------------------------ UI feedback: toast, banner, tooltip, loader
  var toastTimer = null;
  function toast(text, ms) {
    var t = $('#toast'); if (!t) return;
    t.textContent = text; t.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = later(function () { t.hidden = true; }, ms || 3500, 'toast');
  }
  var bannerRetry = null;
  function showBanner(head, text, retry) {
    $('#bannerTitle').textContent = head; $('#bannerText').textContent = text ? ' ' + text : '';
    bannerRetry = retry; $('#bannerRetry').hidden = !retry; $('#banner').hidden = false;
  }
  function hideBanner() { $('#banner').hidden = true; }
  function setLoading(on, label) {
    var L = $('#loader'); if (!L) return;
    if (label) $('#loaderLabel').textContent = label;
    if (on) { L.hidden = false; L.classList.remove('is-done'); } else { L.classList.add('is-done'); }
    $('#app').setAttribute('data-state', on ? 'loading' : (S.ready ? 'ready' : 'error'));
  }

  // ------------------------------------------------------------------------------------------------ data
  async function fetchJSON(url, what) {
    var r = await withTimeout(fetch(url, { cache: 'no-cache' }), 20000, what);
    if (!r.ok) throw new Error(what + ': HTTP ' + r.status);
    return r.json();
  }
  async function loadData() {
    var D = CFG.data || {}, names = ['regions', 'facts', 'looks', 'tour', 'presets', 'torso', 'prov'];
    var res = await Promise.all(names.map(function (n) { return D[n] ? fetchJSON(D[n], n + '.json').then(function (v) { return { n: n, v: v }; }, function (e) { return { n: n, e: e }; }) : Promise.resolve({ n: n }); }));
    res.forEach(function (r) { if (r.e) { log('error', 'data ' + r.n + ': ' + r.e.message); } else if (r.v) S.data[r.n] = r.v; });
    var d = S.data;
    d.regions = d.regions || []; d.looks = d.looks || []; d.presets = d.presets || {}; d.tour = d.tour || null; d.facts = d.facts || { facts: {}, by_fact_key: {} };
    d.byId = {}; d.cortex = { L: [], R: [] }; d.deep = [];
    d.regions.forEach(function (r) {
      d.byId[r.id] = r;
      if (r.id.indexOf('ctx-') === 0) (r.hemi === 'R' ? d.cortex.R : d.cortex.L).push(r); else d.deep.push(r);
    });
    d.torsoRegions = (d.torso && d.torso.regions) || [];
    var missing = ['regions', 'looks', 'tour'].filter(function (n) { return !S.data[n] || (Array.isArray(S.data[n]) && !S.data[n].length); });
    if (missing.length) toast('Some data files did not load (' + missing.join(', ') + '). Those controls are limited.', 7000);
  }
  function factsFor(r) {
    var f = S.data.facts || {};
    var key = r.fact_key || r.id.replace(/^(ctx-[lr]h-|deep-)/, '');
    return (f.by_fact_key && typeof f.by_fact_key[key] === 'object' ? f.by_fact_key[key] : null) || (f.facts && f.facts[key]) ||
      (f.facts && f.facts[r.id.replace(/^(ctx-[lr]h-|deep-)/, '')]) || null;
  }

  // ------------------------------------------------------------------------------------------------ X_ITE boot
  function loadScript(src) {
    return new Promise(function (res, rej) {
      var s = document.createElement('script');
      s.src = src; s.async = true;
      s.onload = function () { res(); };
      s.onerror = function () { rej(new Error('could not load ' + src)); };
      document.head.appendChild(s);
    });
  }
  async function loadXite() {
    if (window.X3D) { X3D_ = window.X3D; return; }
    var X = CFG.xite || {}, srcs = [X.vendor, X.cdn].filter(Boolean), last = null;
    for (var i = 0; i < srcs.length; i++) {
      try { await withTimeout(loadScript(srcs[i]), 30000, 'X_ITE script'); if (window.X3D) { X3D_ = window.X3D; log('info', 'X_ITE loaded from ' + srcs[i]); return; } } catch (e) { last = e; log('warn', e.message); }
    }
    throw new Error('X_ITE could not be loaded (' + (last ? last.message : 'no source configured') + '). Run tools/fetch_xite.sh once, or check the network.');
  }
  function webglOk() {
    try { var c = document.createElement('canvas'); return !!(c.getContext('webgl2')); } catch (e) { return false; }
  }
  async function mountBrowser() {
    if (!webglOk()) throw new Error('WebGL 2 is not available in this browser or the GPU is blocked.');
    var t0 = performance.now(), br = null;
    while (!br && performance.now() - t0 < 15000) {
      try { br = X3D_.getBrowser('#stage'); } catch (e) { br = null; }
      if (!br) await sleep(50);
    }
    if (!br) throw new Error('The 3D canvas did not start.');
    B = br;
    try { B.setBrowserOption('ToneMapping', 'KHR_PBR_NEUTRAL'); } catch (e) { log('warn', 'ToneMapping: ' + e.message); }
    try { B.setBrowserOption('OrderIndependentTransparency', false); } catch (e) { /* option absent */ }   // OIT makes the custom glass vanish (FM97)
    try { B.setBrowserOption('Notifications', false); B.setBrowserOption('Timings', false); } catch (e) { /* cosmetic */ }
    applyQuality(S.quality, true);
    var C = X3D_.X3DConstants || {};
    ['INITIALIZED_ERROR', 'CONNECTION_ERROR'].forEach(function (k) {
      if (C[k] !== undefined) B.addBrowserCallback('page-' + k, C[k], guard(function () { log('warn', 'X_ITE event ' + k); }, 'browser ' + k));
    });
    log('info', 'X_ITE ' + B.version + ' ready');
  }
  function applyQuality(q, silent) {
    S.quality = q; store('quality', q);
    var dpr = window.devicePixelRatio || 1;
    var scale = q === 'fast' ? Math.max(0.5, Math.min(0.7, dpr * 0.5)) : q === 'sharp' ? Math.min(2, Math.max(1.25, dpr)) : 1;
    try { B.setBrowserOption('ContentScale', scale); } catch (e) { if (!silent) log('warn', 'ContentScale: ' + e.message); }
    $$('#qualRow .chip').forEach(function (b) { b.setAttribute('aria-pressed', String(b.dataset.q === q)); });
  }

  // ------------------------------------------------------------------------------------------------ scene access
  function node(name) {
    if (!S.scene) return null;
    if (S.nodes[name]) return S.nodes[name];
    if (S.missing[name]) return null;
    try { var n = S.scene.getNamedNode(name); S.nodes[name] = n; return n; } catch (e) { S.missing[name] = true; return null; }
  }
  function snap(v) {
    if (v === null || typeof v !== 'object') return v;
    var t = v.getTypeName();
    if (t === 'SFColor') return [v.r, v.g, v.b];
    if (t === 'SFVec3f') return [v.x, v.y, v.z];
    if (t === 'SFRotation') return [v.x, v.y, v.z, v.angle];
    if (t === 'MFColor') { var a = []; for (var i = 0; i < v.length; i++) a.push(v[i].r, v[i].g, v[i].b); return a; }
    return String(v);
  }
  function nums(v) { return typeof v === 'string' ? v.trim().split(/\s+/).map(Number) : (Array.isArray(v) ? v : [v]); }
  function assign(n, field, cur, value) {
    var t = (cur !== null && typeof cur === 'object' && cur.getTypeName) ? cur.getTypeName() : typeof cur;
    var a;
    if (t === 'number') n[field] = Number(value);
    else if (t === 'boolean') n[field] = !!value;
    else if (t === 'string') n[field] = String(value);
    else if (t === 'SFColor') { a = nums(value); n[field] = new X3D_.SFColor(a[0], a[1], a[2]); }
    else if (t === 'SFVec3f') { a = nums(value); n[field] = new X3D_.SFVec3f(a[0], a[1], a[2]); }
    else if (t === 'SFRotation') { a = nums(value); n[field] = new X3D_.SFRotation(a[0], a[1], a[2], a[3]); }
    else if (t === 'MFColor') { a = nums(value); var cols = []; for (var i = 0; i + 2 < a.length; i += 3) cols.push(new X3D_.SFColor(a[i], a[i + 1], a[i + 2])); n[field] = new X3D_.MFColor(...cols); }
    else throw new Error('unsupported field type ' + t + ' for ' + field);
  }
  /* Set a field and remember its original value the first time, so any look or preset can be undone exactly. */
  function setField(name, field, value) {
    var n = node(name);
    if (!n) return false;
    var key = name + '.' + field, cur = n[field];
    if (!S.touched[key]) S.touched[key] = { name: name, field: field, v: snap(cur) };
    assign(n, field, cur, value);
    return true;
  }
  function restoreTouched() {
    Object.keys(S.touched).forEach(function (k) {
      var t = S.touched[k], n = node(t.name);
      if (n) { try { assign(n, t.field, n[t.field], t.v); } catch (e) { log('warn', 'restore ' + k + ': ' + e.message); } }
    });
    S.touched = {};
  }
  /* MFColor in this X_ITE takes SFColor arguments as an array or a list; the MFColor branch above passes an array. */

  // ------------------------------------------------------------------------------------------------ switches (layers)
  function captureBaseline() {
    S.sw = {}; S.baseSw = {};
    var defs = S.kind === 'brain' ? ALL_SW : S.torsoSw;
    defs.forEach(function (d) { var n = node(d); if (n) { var v = n.whichChoice; S.sw[d] = v; S.baseSw[d] = v; } });
    var cp = node('CLIP_MIDSAG'); S.clip = cp ? !!cp.enabled : false; S.baseClip = S.clip;
    S.glow = (S.sw.SW_AURA === undefined) ? true : S.sw.SW_AURA === 0; S.baseGlow = S.glow;
  }
  function isOn(def) { return S.sw[def] === 0; }
  function applySwitches() {
    if (!S.scene) return;
    if (S.kind === 'brain') {
      if (S.sw.SW_AURA !== undefined || node('SW_AURA')) S.sw.SW_AURA = (isOn('SW_CORTEX') && S.glow) ? 0 : -1;
    }
    Object.keys(S.sw).forEach(function (d) { var n = node(d); if (n && n.whichChoice !== S.sw[d]) n.whichChoice = S.sw[d]; });
    var cp = node('CLIP_MIDSAG'); if (cp && cp.enabled !== S.clip) cp.enabled = S.clip;
    syncLayerUI();
  }
  function setHemi(side, on) {
    var v = on ? 0 : -1;
    ['SW_HEMI_' + side, 'SW_WETHEMI_' + side].forEach(function (d) { if (S.sw[d] !== undefined) S.sw[d] = v; });
  }
  function hemiOn(side) { return S.sw['SW_HEMI_' + side] === 0; }
  function setLayer(key, on) {
    var def = MAIN_DEF[key]; if (!def) return;
    S.sw[def] = on ? 0 : -1;
    if (key === 'wet' && on && isOn('SW_CORTEX')) { /* both can be on: the wet cortex then hides the glass; allowed, user choice */ }
    if (key === 'tracts') applyTractTint();
    applySwitches();
    announce(BRAIN_LAYERS.filter(function (l) { return l.key === key; })[0].label + (on ? ' on' : ' off'));
  }
  function announce(t) { var s = $('#toast'); if (!s || !t) return; log('info', t); }

  function buildLayerUI() {
    var ul = $('#layerList'); ul.textContent = '';
    var items;
    if (S.kind === 'brain') items = BRAIN_LAYERS.filter(function (l) { return node(MAIN_DEF[l.key]); }).map(function (l) { return { key: l.key, def: MAIN_DEF[l.key], label: l.label, tag: l.tag, tagTitle: l.tagTitle, hint: l.hint }; });
    else items = (S.torsoSw || []).map(function (d) { return { key: d, def: d, label: TORSO_LAYER_LABELS[d] || title(d.replace(/^SW_/, '').toLowerCase()), hint: '' }; });
    items.forEach(function (it) {
      var cb = el('input', { type: 'checkbox', id: 'ly-' + it.key, 'data-key': it.key, 'data-def': it.def, 'aria-describedby': it.tag ? 'tg-' + it.key : null });
      var label = el('label', { class: 'switch', title: it.hint || null, for: 'ly-' + it.key }, cb, el('span', { class: 'switch__track', 'aria-hidden': 'true' }), el('span', { class: 'switch__text', text: it.label }));
      if (it.tag) label.querySelector('.switch__text').appendChild(el('abbr', { class: 'tag', id: 'tg-' + it.key, title: it.tagTitle, text: it.tag }));
      on(cb, 'change', function () {
        if (S.kind === 'brain') setLayer(it.key, cb.checked);
        else { S.sw[it.def] = cb.checked ? 0 : -1; applySwitches(); }
      }, 'layer ' + it.key);
      ul.appendChild(el('li', { class: 'layer-list__item' }, label));
    });
    var opt = $('#optRow'); opt.textContent = '';
    var opts = S.kind === 'brain' ? [
      { id: 'glow', label: 'Glow', get: function () { return S.glow; }, set: function (v) { S.glow = v; } },
      { id: 'hemiL', label: 'Left half', get: function () { return hemiOn('L'); }, set: function (v) { setHemi('L', v); S.cam.autoHidLeft = false; }, needs: 'SW_HEMI_L' },
      { id: 'hemiR', label: 'Right half', get: function () { return hemiOn('R'); }, set: function (v) { setHemi('R', v); }, needs: 'SW_HEMI_R' },
      { id: 'clip', label: 'Cutaway', get: function () { return S.clip; }, set: function (v) { S.clip = v; }, needs: 'CLIP_MIDSAG' },
      { id: 'pedestal', label: 'Pedestal', get: function () { return isOn('SW_PEDESTAL'); }, set: function (v) { S.sw.SW_PEDESTAL = v ? 0 : -1; }, needs: 'SW_PEDESTAL' },
      { id: 'stage', label: 'Stage glow', get: function () { return isOn('SW_STAGE'); }, set: function (v) { S.sw.SW_STAGE = v ? 0 : -1; }, needs: 'SW_STAGE' }
    ] : [];
    S.opts = opts.filter(function (o) { return !o.needs || node(o.needs); });
    S.opts.forEach(function (o) {
      var b = el('button', { class: 'chip', type: 'button', 'data-opt': o.id, 'aria-pressed': 'false', text: o.label });
      on(b, 'click', function () { o.set(!o.get()); applySwitches(); }, 'option ' + o.id);
      opt.appendChild(b);
    });
    $('#optBlock').hidden = !S.opts.length;
    syncLayerUI();
  }
  function syncLayerUI() {
    $$('#layerList input[type=checkbox]').forEach(function (cb) { var on_ = isOn(cb.dataset.def); if (cb.checked !== on_) cb.checked = on_; });
    (S.opts || []).forEach(function (o) { var b = $('#optRow [data-opt="' + o.id + '"]'); if (b) b.setAttribute('aria-pressed', String(!!o.get())); });
  }

  // ------------------------------------------------------------------------------------------------ looks and presets
  function opIsSwitch(op) { return (op[0].indexOf('SW_') === 0 && op[1] === 'whichChoice') || (op[0] === 'CLIP_MIDSAG' && op[1] === 'enabled'); }
  function applySwitchOp(op) {
    var d = op[0], v = op[2];
    if (d === 'CLIP_MIDSAG') { S.clip = !!v; return; }
    if (d === 'SW_AURA') { S.glow = (v === 0); return; }
    if (d === 'SW_HEMI_L' || d === 'SW_WETHEMI_L') { setHemi('L', v === 0); return; }
    if (d === 'SW_HEMI_R' || d === 'SW_WETHEMI_R') { setHemi('R', v === 0); return; }
    if (S.sw[d] !== undefined) S.sw[d] = v;
  }
  function currentLook() { return S.data.looks.filter(function (l) { return l.id === S.lookId; })[0] || null; }
  /* Deep structures that a look draws as faint ghosts (caudate, putamen, amygdala, accumbens, ventricles, cerebellum) are still pickable; while one is the selected region it is drawn solid,
     and put back when the selection or the look changes. Kept apart from S.touched so the style pipeline can restore and re-push around it. */
  function clearHighlight() {
    if (!S.hl) return;
    var n = node(S.hl.mat); if (n) { try { n.transparency = S.hl.v; } catch (e) { /* node gone */ } }
    S.hl = null;
  }
  function applyHighlight() {
    clearHighlight();
    if (S.kind !== 'brain' || !S.region || S.region.id.indexOf('deep-') !== 0) return;
    var mat = 'MAT_' + S.region.id.slice(5), n = node(mat); if (!n) return;
    var cur = n.transparency;
    if (cur > 0.01) { S.hl = { mat: mat, v: cur }; n.transparency = 0; }
  }
  /* Style pipeline: undo every field a look/preset touched, then push the look, then the tour preset. Switches are layer state, handled separately. */
  function applyStyle() {
    if (!S.scene || S.kind !== 'brain') return;
    clearHighlight();
    restoreTouched();
    var look = currentLook(), n = 0, bad = 0;
    function push(op) { try { if (setField(op[0], op[1], op[2])) n++; else bad++; } catch (e) { bad++; log('warn', 'op ' + op[0] + '.' + op[1] + ': ' + e.message); } }
    if (look) look.push.forEach(function (op) { if (!opIsSwitch(op)) push(op); });
    S.presetOps.forEach(function (op) { if (!opIsSwitch(op)) push(op); });
    applyTractTint();
    applyHighlight();
    if (bad) log('warn', 'style: ' + bad + ' operations skipped (missing node or field)');
    return n;
  }
  /* Tract vertex colours override a line Material's emissive colour, so a tint look swaps the Color node out and tints the three line materials (core, halo 1, halo 2). */
  function applyTractTint() {
    var ils = node('GEO_TRACTS'); if (!ils) return;
    var look = currentLook(), tint = look && look.tract && look.tract.mode === 'tint' && look.tract.colors && look.tract.colors.length >= 3;
    if (!S.tractColorNode && ils.color) S.tractColorNode = ils.color;
    var mats = ['MAT_TRACT_CORE', 'MAT_TRACT_HALO1', 'MAT_TRACT_HALO2'];
    if (tint) {
      if (S.tractColorNode && ils.color) ils.color = null;
      mats.forEach(function (m, i) { var c = look.tract.colors[i]; var rgb = hexToRgb(c); var n_ = node(m); if (n_) { var cur = n_.emissiveColor; var k = 'TT.' + m; if (!S.touched[k]) S.touched[k] = { name: m, field: 'emissiveColor', v: snap(cur) }; n_.emissiveColor = new X3D_.SFColor(rgb[0], rgb[1], rgb[2]); } });
    } else if (S.tractColorNode && !ils.color) {
      ils.color = S.tractColorNode;
    }
  }
  function hexToRgb(h) { h = String(h).replace('#', ''); return [parseInt(h.slice(0, 2), 16) / 255, parseInt(h.slice(2, 4), 16) / 255, parseInt(h.slice(4, 6), 16) / 255]; }

  async function snapshot() {
    try {
      var c = $('#stage');
      await nextFrames(1);
      var u = c.toDataURL('image/jpeg', 0.72);
      return (u && u.length > 2000) ? u : null;
    } catch (e) { log('warn', 'snapshot: ' + e.message); return null; }
  }
  var veilBusy = false;
  async function crossfade(change) {
    var veil = $('#veil'), img = $('#veilImg');
    if (reducedMotion() || veilBusy) { change(); return; }
    veilBusy = true;
    try {
      var before = await snapshot();
      if (!before) { change(); return; }
      S.prevLookImg = before;
      img.src = before; veil.style.transition = 'none'; veil.style.opacity = '1';
      await frame();
      change();
      await nextFrames(2);
      veil.style.transition = 'opacity 900ms cubic-bezier(.2,.8,.2,1)';
      veil.style.opacity = '0';
    } finally { veilBusy = false; }
  }
  /* Looks named for a layer that is off by default bring that layer along (and give it back when another look is chosen). */
  var LOOK_EXTRAS = { 'tractography-neon': ['tracts'], 'cosmic-connectome': ['tracts'], 'bioluminescent-neurons': ['tracts'], 'holographic-slices': ['slices'], 'fmri-heatmap': ['activation'] };
  async function selectLook(id) {
    if (S.kind !== 'brain' || !S.scene) return;
    var look = S.data.looks.filter(function (l) { return l.id === id; })[0];
    if (!look && id !== null) return;
    var prev = S.lookId;
    await crossfade(function () {
      S.lookId = id;
      (S.lookExtras || []).forEach(function (k) { var d = MAIN_DEF[k]; if (d && S.baseSw) S.sw[d] = S.baseSw[d]; });   // undo the last look's companion layers
      S.lookExtras = [];
      if (look) {
        look.push.forEach(function (op) { if (opIsSwitch(op)) applySwitchOp(op); });
        (LOOK_EXTRAS[id] || []).forEach(function (k) { var d = MAIN_DEF[k]; if (d && node(d)) { S.sw[d] = 0; S.lookExtras.push(k); } });
      }
      else { S.sw = Object.assign({}, S.baseSw); S.glow = S.baseGlow; S.clip = S.baseClip; }
      applyStyle(); applySwitches();
    });
    renderLookState();
    $('#btnCompare').disabled = !S.prevLookImg;
    log('info', 'look ' + (prev || 'default') + ' -> ' + (id || 'default') + ' (' + Object.keys(S.touched).length + ' fields)');
  }
  function buildLookUI() {
    var g = $('#lookGrid'); g.textContent = '';
    S.data.looks.forEach(function (l, i) {
      var st = '--la:' + l.background[0] + ';--lb:' + l.background[1] + ';--lrim:' + l.rim + ';--lbody:' + l.body + ';--linner:' + l.inner + ';--lacc:' + l.accent;
      var b = el('button', { class: 'look', type: 'button', 'data-look': l.id, 'aria-pressed': 'false', 'aria-label': (i + 1) + '. ' + l.name, title: l.name, style: st });
      if (CFG.thumbs && l.board) { b.classList.add('look--img'); b.appendChild(el('img', { src: CFG.thumbs + l.board + '.jpg', alt: '', loading: 'lazy', decoding: 'async' })); }
      on(b, 'click', function () { return selectLook(l.id === S.lookId ? null : l.id); }, 'look ' + l.id);
      g.appendChild(b);
    });
    $('#pLook').hidden = !S.data.looks.length || S.kind !== 'brain';
    renderLookState();
  }
  function renderLookState() {
    var look = currentLook();
    $$('#lookGrid .look').forEach(function (b) { b.setAttribute('aria-pressed', String(b.dataset.look === S.lookId)); });
    $('#lookName').textContent = look ? look.name : 'Scene default';
    var note = $('#lookNote');
    note.textContent = look ? 'Palette only: the geometry is the same template brain and the tracts stay synthetic. Reference picture: ' + look.notes.replace(/ Measured on .*$/, '') : 'Twelve palettes measured from reference imagery, pushed into the live scene.';
    $('#btnLookReset').disabled = !look;
  }

  // ------------------------------------------------------------------------------------------------ camera
  function vec(v) { return [v.x, v.y, v.z]; }
  function poseOf(name) {
    var v = node(name); if (!v) return null;
    return { position: vec(v.position), orientation: [v.orientation.x, v.orientation.y, v.orientation.z, v.orientation.angle], center: vec(v.centerOfRotation), fov: v.fieldOfView };
  }
  function rotUp(o) {
    var l = Math.hypot(o[0], o[1], o[2]) || 1, k = [o[0] / l, o[1] / l, o[2] / l], c = Math.cos(o[3]), s_ = Math.sin(o[3]), v = [0, 1, 0];
    var kv = k[1], cr = [k[1] * 0 - k[2] * 1, k[2] * 0 - k[0] * 0, k[0] * 1 - k[1] * 0];   // k x (0,1,0)
    return [v[0] * c + cr[0] * s_ + k[0] * kv * (1 - c), v[1] * c + cr[1] * s_ + k[1] * kv * (1 - c), v[2] * c + cr[2] * s_ + k[2] * kv * (1 - c)];
  }
  function fovScale() {
    var w = window.innerWidth, h = window.innerHeight;
    if (w / h < 0.9) return 1.15;                                   // portrait phone: the field of view is the narrow (horizontal) side, so the model is width-limited and can fill it
    if (w < 900) return 1.5;
    if (w < 1500) return 1.42;
    return 1.25;
  }
  function makePageViewpoints() {
    S.cam.vps = [];
    for (var i = 0; i < 2; i++) {
      var v = S.scene.createNode('Viewpoint'); v.description = 'page camera ' + i;
      S.scene.rootNodes.push(v); S.cam.vps.push(v);
    }
    var nav = node('NAV');
    if (nav) { try { nav.transitionTime = 1.4; } catch (e) { /* field absent */ } }
  }
  /* The stage is full-bleed, but the model should sit in the part of it the HUD leaves free: between the top bar and the dock (on a phone, the open sheet too).
     fitStage() measures that band, moves the canvas so the band's centre is the canvas centre (it still covers the whole window) and returns how much
     wider the field of view must be for the model to fit in the band. Orbit state is untouched: only the canvas box and the field of view change. */
  function fitStage() {
    try {
      var app = $('#app').getBoundingClientRect(), H = app.height || window.innerHeight, top = 0, bottom = H;
      var tb = $('.hud__top'); if (tb) top = Math.max(0, tb.getBoundingClientRect().bottom - app.top);
      var cand = [$('.dock')]; if (window.innerWidth <= 640) cand.push($('#left'), $('#right'));
      cand.forEach(function (e) { if (!e) return; var r = e.getBoundingClientRect(); if (r.height > 0) bottom = Math.min(bottom, r.top - app.top); });
      if (bottom - top < 80) { top = 0; bottom = H; }
      var cf = (top + bottom) / 2, y0 = Math.min(0, 2 * cf - H), y1 = Math.max(H, 2 * cf);
      ['stage', 'veil'].forEach(function (id) { var e = document.getElementById(id); if (e) { e.style.top = y0 + 'px'; e.style.height = (y1 - y0) + 'px'; e.style.bottom = 'auto'; } });
      // at a field-of-view factor of 1 the home view is about 0.56 of the canvas' smaller side tall: widen the view only when the free band is shorter than that
      S.fit = clamp(0.56 * Math.min(app.width || window.innerWidth, y1 - y0) / (0.9 * Math.max(40, bottom - top - 8)), 1, 1.9);
      S.fitBand = [Math.round(top), Math.round(bottom)];
    } catch (e) { S.fit = 1; }
    return S.fit;
  }
  function refit() {
    if (S.fitQueued) return;
    S.fitQueued = true;
    requestAnimationFrame(guard(function () {
      S.fitQueued = false; fitStage();
      var v = S.cam.vps[S.cam.i]; if (v && S.cam.baseFov) { try { v.fieldOfView = clamp(S.cam.baseFov * S.fit, 0.2, 2.2); } catch (e) { /* viewpoint gone */ } }
    }, 'refit'));
  }
  function watchLayout() {
    if (window.ResizeObserver) {
      var ro = new ResizeObserver(guard(refit, 'layout watch'));
      ['.hud__top', '.dock', '#left', '#right'].forEach(function (q) { var e = $(q); if (e) ro.observe(e); });
    }
    on(window, 'resize', refit, 'resize');
  }
  function flyTo(pose, instant) {
    if (!pose || !S.cam.vps.length) return;
    S.cam.i = 1 - S.cam.i;
    var v = S.cam.vps[S.cam.i], nav = node('NAV');
    v.position = new X3D_.SFVec3f(pose.position[0], pose.position[1], pose.position[2]);
    v.orientation = new X3D_.SFRotation(pose.orientation[0], pose.orientation[1], pose.orientation[2], pose.orientation[3]);
    v.centerOfRotation = new X3D_.SFVec3f(pose.center[0], pose.center[1], pose.center[2]);
    fitStage();
    // Views nearer than the home view (350 mm) show the model larger: widen their field of view by the distance ratio so every named view fills the free band alike.
    // (Inside views, a few tens of mm from the target, are meant to be close and keep their own field of view.)
    var dist = Math.hypot(pose.position[0], pose.position[1], pose.position[2]), comp = (dist > 200 && dist < 350) ? 350 / dist : 1;
    S.cam.baseFov = 2 * Math.atan(Math.tan(pose.fov * fovScale() / 2) * comp);
    var fov = clamp(S.cam.baseFov * S.fit, 0.2, 2.2);
    v.fieldOfView = fov;
    S.cam.target = [pose.position[0], pose.position[1], pose.position[2]];
    if (nav) nav.transitionType = new X3D_.MFString((instant || reducedMotion()) ? 'TELEPORT' : 'ANIMATE');
    v.set_bind = true;
  }
  function viewList() {
    if (S.kind === 'brain') return ['VP_HOME', 'VP_LEFT', 'VP_RIGHT', 'VP_TOP', 'VP_FRONT', 'VP_MEDIAL', 'VP_INSIDE'].filter(function (n) { return node(n); });
    var out = [];
    S.scene.rootNodes.forEach(function (n) { try { if (n && n.getNodeTypeName() === 'Viewpoint') { var nm = n.getNodeName(); if (nm && nm.indexOf('VP_') === 0) out.push(nm); } } catch (e) { /* skip */ } });
    return out;
  }
  function setView(name, opts) {
    opts = opts || {};
    var pose = poseOf(name); if (!pose) { toast('That view is not in this scene.'); return; }
    if (S.kind === 'brain') {
      if (name === 'VP_MEDIAL' && hemiOn('L') && node('SW_HEMI_L')) { S.cam.autoHidLeft = true; setHemi('L', false); applySwitches(); toast('Left hemisphere hidden to show the medial wall.'); }
      else if (name !== 'VP_MEDIAL' && S.cam.autoHidLeft) { S.cam.autoHidLeft = false; setHemi('L', true); applySwitches(); }
    }
    S.cam.name = name;
    flyTo(pose, opts.instant);
    $$('#views .chip').forEach(function (b) { b.setAttribute('aria-pressed', String(b.dataset.vp === name)); });
  }
  function buildViewUI() {
    var v = $('#views'); v.textContent = '';
    viewList().forEach(function (name, i) {
      var n = node(name), desc = n && n.description ? n.description : '';
      var b = el('button', { class: 'chip', type: 'button', 'data-vp': name, 'aria-pressed': String(name === S.cam.name), title: desc || null, 'aria-label': (VIEW_LABELS[name] || title(name.slice(3).toLowerCase())) + ' view' + (i < 9 ? ' (key ' + (i + 1) + ')' : '') },
        el('span', { text: VIEW_LABELS[name] || title(name.slice(3).toLowerCase()) }));
      on(b, 'click', function () { setView(name); }, 'view ' + name);
      v.appendChild(b);
    });
  }
  // orientation (axis-angle) for a camera at `pos` looking at `target`, up = +Y
  function lookAtRot(pos, target) {
    var f = [target[0] - pos[0], target[1] - pos[1], target[2] - pos[2]], l = Math.hypot(f[0], f[1], f[2]) || 1; f = f.map(function (x) { return x / l; });
    var up = Math.abs(f[1]) > 0.98 ? [0, 0, -1] : [0, 1, 0];
    var r = [f[1] * up[2] - f[2] * up[1], f[2] * up[0] - f[0] * up[2], f[0] * up[1] - f[1] * up[0]], rl = Math.hypot(r[0], r[1], r[2]) || 1; r = r.map(function (x) { return x / rl; });
    var u = [r[1] * f[2] - r[2] * f[1], r[2] * f[0] - r[0] * f[2], r[0] * f[1] - r[1] * f[0]];
    var m00 = r[0], m01 = u[0], m02 = -f[0], m10 = r[1], m11 = u[1], m12 = -f[1], m20 = r[2], m21 = u[2], m22 = -f[2];
    var tr = m00 + m11 + m22, ang = Math.acos(clamp((tr - 1) / 2, -1, 1)), ax;
    if (ang < 1e-6) return [0, 1, 0, 0];
    if (Math.PI - ang < 1e-4) { ax = [Math.sqrt(Math.max(0, (m00 + 1) / 2)), Math.sqrt(Math.max(0, (m11 + 1) / 2)), Math.sqrt(Math.max(0, (m22 + 1) / 2))]; }
    else { var s = 2 * Math.sin(ang); ax = [(m21 - m12) / s, (m02 - m20) / s, (m10 - m01) / s]; }
    var al = Math.hypot(ax[0], ax[1], ax[2]) || 1;
    return [ax[0] / al, ax[1] / al, ax[2] / al, ang];
  }
  function focusRegion(r) {
    if (!r || S.kind !== 'brain') return;
    var c = r.centroid, a = r.anchor || c, nrm = r.anchor_normal, dir;
    var isDeep = r.id.indexOf('deep-') === 0;
    if (!isDeep) {
      var al = Math.hypot(a[0], a[1] - 5, a[2]) || 1, o = [a[0] / al, (a[1] - 5) / al, a[2] / al];
      dir = nrm ? [nrm[0] * 0.5 + o[0] * 0.5, nrm[1] * 0.5 + o[1] * 0.5, nrm[2] * 0.5 + o[2] * 0.5] : o;
    } else {
      var sx = c[0] > 3 ? 1 : -1; dir = [sx * 0.85, 0.28, c[2] > 0 ? 0.5 : -0.5];
    }
    var dl = Math.hypot(dir[0], dir[1], dir[2]) || 1; dir = dir.map(function (x) { return x / dl; });
    var d = 300, pos = [dir[0] * d, dir[1] * d + 15, dir[2] * d], tgt = [0, 15, 0];
    S.cam.name = null; $$('#views .chip').forEach(function (b) { b.setAttribute('aria-pressed', 'false'); });
    if (!isDeep && ((r.hemi === 'L' && !hemiOn('L')) || (r.hemi === 'R' && !hemiOn('R')))) { setHemi(r.hemi, true); applySwitches(); }
    flyTo({ position: pos, orientation: lookAtRot(pos, tgt), center: [0, 15, 0], fov: 0.56 });
  }

  // ------------------------------------------------------------------------------------------------ picking
  function dist2(p, q) { var x = p[0] - q[0], y = p[1] - q[1], z = p[2] - q[2]; return x * x + y * y + z * z; }
  /* Nearest region to a scene-space point. hemi 'L'/'R' limits cortical candidates; deep structures compete only when asked. */
  function nearestRegion(pt, hemi, includeDeep) {
    var D = S.data, best = null, bd = Infinity, list = [];
    if (hemi === 'L') list = D.cortex.L; else if (hemi === 'R') list = D.cortex.R; else list = D.cortex.L.concat(D.cortex.R);
    if (includeDeep) list = list.concat(D.deep);
    for (var i = 0; i < list.length; i++) {
      var r = list[i], c = r.anchor || r.centroid, d = dist2(pt, c);
      if (r.centroid && r.anchor) { var d2 = dist2(pt, r.centroid); if (d2 < d) d = d2; }
      if (d < bd) { bd = d; best = r; }
    }
    return best ? { region: best, distance: Math.sqrt(bd) } : null;
  }
  function nearestTorso(pt, sw) {
    var list = S.data.torsoRegions.filter(function (r) { return !sw || r.switch === sw; }), best = null, bd = Infinity;
    list.forEach(function (r) { var d = dist2(pt, r.centroid_mm); if (d < bd) { bd = d; best = r; } });
    return best ? { region: best, distance: Math.sqrt(bd) } : null;
  }
  /* The skin is a see-through shell in front of everything, so its sensor sees only the skin: follow the camera ray from the hit point inwards and take the
     visible part whose centre lies closest to that ray, nearer parts first (what you see through the skin is what you get). */
  function rayTorso(hit) {
    var cam = null; try { var p = B.getActiveLayer().getViewpoint().getUserPosition(); cam = [p.x, p.y, p.z]; } catch (e) { cam = null; }
    if (!cam) return nearestTorso(hit, null);
    var d = [hit[0] - cam[0], hit[1] - cam[1], hit[2] - cam[2]], len = Math.hypot(d[0], d[1], d[2]) || 1; d = [d[0] / len, d[1] / len, d[2] / len];
    var best = null, bs = Infinity, bd = 0;
    S.data.torsoRegions.forEach(function (r) {
      if (r.switch === 'SW_SKIN') return;
      var sw = node(r.switch); if (!sw || sw.whichChoice !== 0) return;
      var v = [r.centroid_mm[0] - hit[0], r.centroid_mm[1] - hit[1], r.centroid_mm[2] - hit[2]], t = v[0] * d[0] + v[1] * d[1] + v[2] * d[2];
      if (t < -15) return;
      var perp = Math.hypot(v[0] - t * d[0], v[1] - t * d[1], v[2] - t * d[2]), sc = perp + 0.25 * Math.max(t, 0);
      if (sc < bs) { bs = sc; best = r; bd = perp; }
    });
    return best ? { region: best, distance: bd } : nearestTorso(hit, null);
  }
  function resolveHit(src, pt) {
    if (S.kind === 'torso') return src.ray ? rayTorso(pt) : nearestTorso(pt, src.sw);
    if (src.deep) { var r = S.data.byId['deep-' + src.deep]; return r ? { region: r, distance: 0 } : null; }
    return nearestRegion(pt, src.hemi || (pt[0] < 0 ? 'L' : 'R'), false);
  }
  function addSensor(src, ts) {
    var rec = { src: src, ts: ts };
    // each body starts with try (the page-traps rule reads the first token; guard() does the same job for everything else)
    ts.addFieldCallback('page', 'hitPoint_changed', function (v) { try { onHover(rec, [v.x, v.y, v.z]); } catch (e) { report('hover ' + src.name, e); } });
    ts.addFieldCallback('page', 'isOver', function (over) { try { if (!over) onOut(rec); } catch (e) { report('over ' + src.name, e); } });
    ts.addFieldCallback('page', 'touchTime', function () { try { onTouch(rec); } catch (e) { report('touch ' + src.name, e); } });
    S.sensors.push(rec);
  }
  function installSensors() {
    S.sensors = [];
    if (S.kind === 'brain') {
      [['TS_CORTEX_L', 'L'], ['TS_CORTEX_R', 'R'], ['TS_WET_L', 'L'], ['TS_WET_R', 'R']].forEach(function (p) { var n = node(p[0]); if (n) addSensor({ name: p[0], hemi: p[1] }, n); });
      // The 1.03x aura shell, the slices and the activation sprites sit in front of the cortex and swallow the pointer: give each a sensor of its own.
      [['G_AURA', 'aura'], ['G_SLICES', 'slices'], ['G_ACTIV', 'activation']].forEach(function (p) {
        var g = node(p[0]); if (!g) return;
        try { var ts = S.scene.createNode('TouchSensor'); ts.description = p[1]; g.children.push(ts); addSensor({ name: 'TS_' + p[1], hemi: null }, ts); } catch (e) { log('warn', 'sensor ' + p[0] + ': ' + e.message); }
      });
      // One sensor per deep structure: wrap each Shape with a Group that also holds a TouchSensor (a sensor senses its siblings).
      var gd = node('G_DEEP');
      if (gd) {
        try {
          var kids = []; for (var i = 0; i < gd.children.length; i++) kids.push(gd.children[i]);
          var nk = [];
          kids.forEach(function (k) {
            var nm = k.getNodeName ? k.getNodeName() : '';
            if (nm && nm.indexOf('STRUCT_') === 0) {
              var grp = S.scene.createNode('Group'), ts2 = S.scene.createNode('TouchSensor'); ts2.description = nm;
              grp.children = new X3D_.MFNode(k, ts2); nk.push(grp);
              addSensor({ name: 'TS_' + nm, deep: nm.slice(7) }, ts2);
            } else nk.push(k);
          });
          gd.children = new X3D_.MFNode(...nk);
        } catch (e) { log('warn', 'deep sensors: ' + e.message); }
      }
    } else {
      (S.torsoSw || []).forEach(function (sw) {
        var n = node('TS_' + sw.replace(/^SW_/, '')); if (n) addSensor({ name: 'TS_' + sw.slice(3), sw: sw }, n);
      });
      // The skin shell has no sensor of its own and would swallow every click: give it one that looks through it.
      var gs = node('G_SKIN');
      if (gs) { try { var tk = S.scene.createNode('TouchSensor'); tk.description = 'skin'; gs.children.push(tk); addSensor({ name: 'TS_SKIN', sw: 'SW_SKIN', ray: true }, tk); } catch (e) { log('warn', 'sensor G_SKIN: ' + e.message); } }
    }
    log('info', S.sensors.length + ' pointer sensors installed');
  }
  function regionName(r) {
    if (S.kind === 'torso') return title((r.label || r.id).replace(/^STRUCT_/, ''));
    var f = factsFor(r), nm = (f && f.name) || r.name;
    return r.id.indexOf('ctx-') === 0 ? nm + ' (' + (r.hemi === 'R' ? 'right' : 'left') + ')' : nm;
  }
  function onHover(rec, pt) {
    var h = resolveHit(rec.src, pt); if (!h) return;
    S.hover = { region: h.region, point: pt };
    var tip = $('#tip'); tip.textContent = regionName(h.region); tip.hidden = false;
    var app = $('#app').getBoundingClientRect();
    tip.style.left = clamp(S.ptr.x - app.left + 14, 8, app.width - 220) + 'px'; tip.style.top = clamp(S.ptr.y - app.top - 34, 8, app.height - 40) + 'px';
    $('#stage').classList.add('is-pick');
  }
  function onOut() { S.hover = null; $('#tip').hidden = true; $('#stage').classList.remove('is-pick'); }
  function onTouch() {
    var p = S.ptr;
    // A click is a press and release that stayed put; how long it was held does not matter (a slow machine or a long press is still a pick). Movement is what tells an orbit
    // drag from a pick: 6 px for a mouse or pen, 12 px for a finger (touch jitter).
    if (p.moved > (p.type === 'touch' ? 12 : 6)) return;
    if (!S.hover) return;
    selectRegion(S.hover.region, { source: 'pick', point: S.hover.point });
  }

  // ------------------------------------------------------------------------------------------------ region card and pin
  function accentOf(r) { return S.kind === 'torso' ? (TORSO_GROUP_ACCENT[r.group] || '#7fe6fb') : (r.accent || (factsFor(r) && factsFor(r).accent) || '#7fe6fb'); }
  function selectRegion(r, opts) {
    opts = opts || {};
    if (typeof r === 'string') r = S.kind === 'torso' ? S.data.torsoRegions.filter(function (x) { return x.id === r; })[0] : S.data.byId[r];
    if (!r) return;
    S.region = r;
    renderRegion(r);
    applyHighlight();
    placePin(r, opts.point);
    if (opts.focus) focusRegion(r);
    if (isPhone() && opts.source === 'pick') openSheet('region');
    $$('#regionList .browse__item').forEach(function (b) { b.setAttribute('aria-current', b.dataset.id === r.id ? 'true' : 'false'); });
    log('info', 'region ' + r.id + ' (' + (opts.source || 'api') + ')');
  }
  function clearRegion() {
    S.region = null; clearHighlight(); $('#regionCard').hidden = true; $('#regionEmpty').hidden = false;
    if (S.pin) S.pin.show(false);
    $$('#regionList .browse__item').forEach(function (b) { b.setAttribute('aria-current', 'false'); });
  }
  function renderRegion(r) {
    $('#regionEmpty').hidden = true; $('#regionCard').hidden = false;
    var acc = accentOf(r);
    $('#rCard').style.setProperty('--region-accent', acc);
    var facts = $('#rFacts'), tabs = $('#rTabs'), note = $('#rNote');
    facts.textContent = ''; tabs.textContent = '';
    if (S.kind === 'torso') {
      $('#rName').textContent = regionName(r);
      $('#rLobe').textContent = (TORSO_GROUP_NAME[r.group] || title(r.group.toLowerCase())) + ' | CT subject s1397';
      var rows = [['Source', r.source === 'segmentation' ? 'Segmentation mask of the subject CT' : 'Threshold of the subject CT (not a segmentation)'],
        ['Volume', r.volume_ml == null ? 'Not measured for this part' : r.volume_ml + ' ml (voxel count at 3 mm)'],
        ['Centre', r.centroid_mm.map(function (x) { return Math.round(x); }).join(', ') + ' mm (x right, y up, z back)'],
        ['Mesh', fmtNum(r.lite_triangles) + ' triangles in the lite build']];
      rows.forEach(function (p) { facts.appendChild(el('div', { class: 'facts__item is-active' }, el('dt', { class: 'facts__label', text: p[0] }), el('dd', { class: 'facts__text', text: p[1] }))); });
      note.textContent = 'Derived from one subject\'s CT. Rendering is illustrative; not for diagnosis.';
      $('#btnFocus').hidden = true;
      return;
    }
    var f = factsFor(r);
    $('#rName').textContent = regionName(r);
    $('#rLobe').textContent = (f && f.lobe_or_system) || title(r.lobe || '');
    var first = null;
    FACT_TABS.forEach(function (t) {
      if (!f || !f[t[0]]) return;
      first = first || t[0];
      facts.appendChild(el('div', { class: 'facts__item', 'data-tab': t[0], id: 'fi-' + t[0] }, el('dt', { class: 'facts__label', text: t[1] }), el('dd', { class: 'facts__text', text: f[t[0]] })));
      var tb = el('button', { class: 'tab', role: 'tab', type: 'button', 'data-tab': t[0], 'aria-selected': 'false', 'aria-controls': 'fi-' + t[0], tabindex: '-1', text: t[1] });
      on(tb, 'click', function () { showFactTab(t[0]); }, 'fact tab');
      on(tb, 'keydown', function (e) { tabKeys(e, tabs, showFactTab); }, 'fact tab keys');
      tabs.appendChild(tb);
    });
    if (!f) facts.appendChild(el('div', { class: 'facts__item is-active' }, el('dt', { class: 'facts__label', text: 'Note' }), el('dd', { class: 'facts__text', text: 'No written summary for this region yet.' })));
    showFactTab(first);
    note.textContent = ((S.data.facts && S.data.facts._meta && S.data.facts._meta.notice) ? 'Generated text, rewritten and checked without expert review. ' : 'Generated text. ') + 'Check before any clinical use. Not medical advice.';
    $('#btnFocus').hidden = false;
  }
  function showFactTab(key) {
    $$('#rTabs .tab').forEach(function (t) { var on_ = t.dataset.tab === key; t.setAttribute('aria-selected', String(on_)); t.tabIndex = on_ ? 0 : -1; });
    $$('#rFacts .facts__item').forEach(function (i) { i.classList.toggle('is-active', i.dataset.tab === key); });
  }
  function tabKeys(e, container, fn) {
    var tabs = $$('[role=tab]', container), i = tabs.indexOf(document.activeElement);
    if (i < 0) return;
    var j = -1;
    if (e.key === 'ArrowRight') j = (i + 1) % tabs.length; else if (e.key === 'ArrowLeft') j = (i - 1 + tabs.length) % tabs.length; else if (e.key === 'Home') j = 0; else if (e.key === 'End') j = tabs.length - 1;
    if (j >= 0) { e.preventDefault(); tabs[j].focus(); fn(tabs[j].dataset.tab || tabs[j].dataset.pane); }
  }
  async function makePin() {
    var k = S.kind === 'torso' ? 5 : 1;
    var xml = "<X3D profile='Full' version='4.0'><Scene>" +
      "<Switch DEF='PIN_SW' whichChoice='-1'><Transform DEF='PIN_T'>" +
      "<Shape><Appearance><Material DEF='PIN_CORE' diffuseColor='0 0 0' emissiveColor='0.5 0.9 1'/></Appearance><Sphere radius='" + (2.1 * k) + "'/></Shape>" +
      "<Transform DEF='PIN_HALO'><Shape><Appearance><Material DEF='PIN_GLOW' diffuseColor='0 0 0' emissiveColor='0.5 0.9 1' transparency='0.7'/></Appearance><Sphere radius='" + (4.8 * k) + "'/></Shape></Transform>" +
      "</Transform></Switch>" +
      "<TimeSensor DEF='PIN_CLK' cycleInterval='1.8' loop='true'/><PositionInterpolator DEF='PIN_PULSE' key='0 0.5 1' keyValue='1 1 1 1.45 1.45 1.45 1 1 1'/>" +
      "<ROUTE fromNode='PIN_CLK' fromField='fraction_changed' toNode='PIN_PULSE' toField='set_fraction'/>" +
      "<ROUTE fromNode='PIN_PULSE' fromField='value_changed' toNode='PIN_HALO' toField='set_scale'/>" +
      "</Scene></X3D>";
    var imp = await B.createX3DFromString(xml);
    var pin = { sw: imp.getNamedNode('PIN_SW'), t: imp.getNamedNode('PIN_T'), core: imp.getNamedNode('PIN_CORE'), glow: imp.getNamedNode('PIN_GLOW') };
    var roots = []; for (var i = 0; i < imp.rootNodes.length; i++) roots.push(imp.rootNodes[i]);
    roots.forEach(function (n) { S.scene.rootNodes.push(n); });
    if (!reducedMotion()) {
      try {
        S.scene.addRoute(imp.getNamedNode('PIN_CLK'), 'fraction_changed', imp.getNamedNode('PIN_PULSE'), 'set_fraction');
        S.scene.addRoute(imp.getNamedNode('PIN_PULSE'), 'value_changed', imp.getNamedNode('PIN_HALO'), 'set_scale');
      } catch (e) { log('warn', 'pin pulse: ' + e.message); }
    }
    return {
      show: function (v) { pin.sw.whichChoice = v ? 0 : -1; },
      set: function (p, rgb) {
        pin.t.translation = new X3D_.SFVec3f(p[0], p[1], p[2]);
        pin.core.emissiveColor = new X3D_.SFColor(Math.min(1, rgb[0] * 0.6 + 0.4), Math.min(1, rgb[1] * 0.6 + 0.4), Math.min(1, rgb[2] * 0.6 + 0.4));
        pin.glow.emissiveColor = new X3D_.SFColor(rgb[0], rgb[1], rgb[2]);
      }
    };
  }
  function placePin(r, hit) {
    if (!S.pin) return;
    var p;
    if (S.kind === 'torso') p = r.centroid_mm;
    else if (r.id.indexOf('deep-') === 0) p = (hit && Math.sqrt(dist2(hit, r.centroid)) < 60) ? hit : r.centroid;
    else p = r.anchor || r.centroid;
    S.pin.set(p, hexToRgb(accentOf(r)));
    S.pin.show(true);
  }

  // ------------------------------------------------------------------------------------------------ region list
  function buildRegionList() {
    var D = S.data;
    var hr = $('#hemiRow'); hr.textContent = '';
    if (S.kind === 'brain') {
      ['L', 'R'].forEach(function (h) {
        var b = el('button', { class: 'chip', type: 'button', 'data-h': h, 'aria-pressed': String(S.regionPref === h), text: h === 'L' ? 'Left' : 'Right', title: 'Hemisphere used when a cortical region is picked from this list' });
        on(b, 'click', function () { S.regionPref = h; $$('#hemiRow .chip').forEach(function (x) { x.setAttribute('aria-pressed', String(x.dataset.h === h)); }); }, 'hemisphere');
        hr.appendChild(b);
      });
    }
    var ul = $('#regionList'); ul.textContent = '';
    var items = [];
    if (S.kind === 'brain') {
      D.deep.forEach(function (r) { items.push({ id: r.id, name: regionName(r), group: 'Deep structures', acc: accentOf(r), key: r.id }); });
      D.cortex.L.forEach(function (r) { var f = factsFor(r); items.push({ id: r.id, name: (f && f.name) || r.name, group: 'Cortex', acc: accentOf(r), key: r.desikan_label }); });
    } else {
      D.torsoRegions.forEach(function (r) { items.push({ id: r.id, name: regionName(r), group: TORSO_GROUP_NAME[r.group] || r.group, acc: accentOf(r), key: r.id }); });
    }
    S.listItems = items;
    items.forEach(function (it) {
      var b = el('button', { class: 'browse__item', type: 'button', 'data-id': it.id, 'data-key': it.key, 'data-name': it.name.toLowerCase() + ' ' + it.group.toLowerCase(), 'aria-current': 'false' },
        el('span', { class: 'dot', style: 'background:' + it.acc, 'aria-hidden': 'true' }), el('span', { class: 'browse__name', text: it.name }), el('span', { class: 'browse__group', text: it.group }));
      on(b, 'click', function () {
        var id = it.id;
        if (S.kind === 'brain' && id.indexOf('ctx-') === 0) id = 'ctx-' + (S.regionPref === 'R' ? 'rh' : 'lh') + '-' + it.key;
        selectRegion(id, { source: 'list', focus: true });
      }, 'region list');
      ul.appendChild(b);
    });
    $('#regionCount').textContent = '(' + items.length + ')';
    filterRegions();
  }
  function filterRegions() {
    var q = $('#regionFilter').value.trim().toLowerCase(), n = 0;
    $$('#regionList .browse__item').forEach(function (b) { var ok = !q || b.dataset.name.indexOf(q) >= 0; b.hidden = !ok; if (ok) n++; });
    $('#regionList').setAttribute('aria-label', n + ' regions shown');
  }

  // ------------------------------------------------------------------------------------------------ guided tour
  function tourSteps() { return (S.data.tour && S.data.tour.steps) || []; }
  function buildTourUI() {
    var d = $('#tourDots'); d.textContent = '';
    var steps = tourSteps();
    steps.forEach(function (s, i) {
      var b = el('button', { class: 'tour__dot', type: 'button', 'aria-label': 'Step ' + (i + 1) + ': ' + s.title, title: s.title });
      on(b, 'click', function () { goStep(i); }, 'tour dot');
      d.appendChild(b);
    });
    $('#btnTour').hidden = !steps.length || S.kind !== 'brain';
  }
  function startTour() {
    if (S.kind !== 'brain' || !tourSteps().length) return;
    if (!S.tourActive) {
      S.pre = { sw: Object.assign({}, S.sw), glow: S.glow, clip: S.clip, cam: S.cam.name, autoHid: S.cam.autoHidLeft };
      S.tourActive = true; $('#app').classList.add('is-touring');
      $('#tour').hidden = false; $('#btnTourLabel').textContent = 'Exit tour';
      if (isPhone()) openSheet(null);
    }
    goStep(0);
  }
  function endTour() {
    if (!S.tourActive) return;
    S.tourActive = false; S.presetOps = []; $('#app').classList.remove('is-touring');
    $('#tour').hidden = true; $('#btnTourLabel').textContent = 'Take the tour';
    if (S.pre) { S.sw = Object.assign({}, S.pre.sw); S.glow = S.pre.glow; S.clip = S.pre.clip; S.cam.autoHidLeft = S.pre.autoHid; }
    applyStyle(); applySwitches();
    setView(S.pre && S.pre.cam ? S.pre.cam : 'VP_HOME');
    S.pre = null;
  }
  function goStep(i) {
    var steps = tourSteps(); if (!steps.length) return;
    i = clamp(i, 0, steps.length - 1);
    var st = steps[i], pre = S.data.presets[st.preset] || { ops: [] };
    S.tourIdx = i;
    var map = (S.data.tour && S.data.tour.layer_switches) || {};
    Object.keys(map).forEach(function (k) { MAIN_DEF[k] = map[k]; });
    S.sw = Object.assign({}, S.baseSw); S.glow = S.baseGlow; S.clip = S.baseClip;
    S.presetOps = [];
    (pre.ops || []).forEach(function (op) { if (opIsSwitch(op)) applySwitchOp(op); else S.presetOps.push(op); });
    Object.keys(MAIN_DEF).forEach(function (k) { var d = MAIN_DEF[k]; if (S.sw[d] !== undefined) S.sw[d] = (st.layers || []).indexOf(k) >= 0 ? 0 : -1; });
    S.cam.autoHidLeft = false;
    applyStyle(); applySwitches();
    var pose = poseOf(st.viewpoint);
    if (pose) { S.cam.name = st.viewpoint; flyTo(pose); $$('#views .chip').forEach(function (b) { b.setAttribute('aria-pressed', String(b.dataset.vp === st.viewpoint)); }); }
    if (st.region) selectRegion(st.region, { source: 'tour' });
    $('#tourStep').textContent = 'Step ' + (i + 1) + ' of ' + steps.length;
    $('#tourTitle').textContent = st.title; $('#tourText').textContent = st.narration;
    $$('#tourDots .tour__dot').forEach(function (b, j) { b.classList.toggle('is-active', j === i); if (j === i) b.setAttribute('aria-current', 'step'); else b.removeAttribute('aria-current'); });
    $('#tourBack').disabled = i === 0;
    $('#tourNext').textContent = i === steps.length - 1 ? 'Finish' : 'Next';
    log('info', 'tour step ' + (i + 1) + ' ' + st.title);
  }

  // ------------------------------------------------------------------------------------------------ audio
  function audioNode() { return node('AUDIO'); }
  function setAudio(on) {
    var a = audioNode(); if (!a) { toast('This build has no music bed.'); return; }
    var now = Date.now() / 1000;
    if (on) { a.stopTime = 0; a.startTime = now; } else { a.stopTime = now; }
    S.audio.on = on;
    syncAudioUI();
    log('info', 'music ' + (on ? 'start' : 'stop'));
    if (on) later(function () { var an = audioNode(); if (an && S.audio.on && !an.isActive) { log('warn', 'AudioClip did not become active (autoplay policy or decode)'); } }, 4000, 'audio check');
  }
  function syncAudioUI() {
    var on_ = S.audio.on;
    var b1 = $('#btnSound'), b2 = $('#btnSound2');
    b1.setAttribute('aria-pressed', String(on_)); b1.setAttribute('aria-label', 'Music bed: ' + (on_ ? 'on' : 'off')); b1.classList.toggle('is-on', on_);
    b2.setAttribute('aria-pressed', String(on_)); b2.textContent = on_ ? 'Pause' : 'Play';
  }
  function initAudio() {
    var has = !!(CFG.audio && audioNode());
    S.audio.ok = has; S.audio.on = false;
    $('#btnSound').hidden = !has; $('#soundBlock').hidden = !has;
    if (has) {
      var snd = node('SND'); if (snd) { try { $('#vol').value = String(Math.round(snd.intensity * 100)); } catch (e) { /* default */ } }
      var a = audioNode(); a.loop = true;
      var C = $('#vol'); C.style.setProperty('--fill', C.value + '%');
    }
    syncAudioUI();
  }

  // ------------------------------------------------------------------------------------------------ panels, phone sheets, tabs, dialog
  function buildPhoneNav() {
    var nav = $('#phoneNav'); nav.textContent = '';
    var items = [['layers', 'Layers'], ['look', 'Look'], ['region', 'Region'], ['tour', 'Tour']];
    items.forEach(function (it) {
      var b = el('button', { class: 'phone-nav__btn', type: 'button', 'data-sheet': it[0], 'aria-pressed': 'false', text: it[1] });
      on(b, 'click', function () {
        if (it[0] === 'tour') { if (S.tourActive) endTour(); else startTour(); return; }
        openSheet(S.sheet === it[0] ? null : it[0]);
      }, 'phone nav');
      nav.appendChild(b);
    });
  }
  function openSheet(name) {
    S.sheet = name; applySheets();
  }
  function applySheets() {
    var phone = isPhone();
    ['layers', 'look', 'region'].forEach(function (k) {
      var p = $('[data-sheet="' + k + '"].panel'); if (!p) return;
      var allowed = !(k === 'look' && (S.kind !== 'brain' || !S.data.looks.length));
      p.hidden = !allowed || (phone && S.sheet !== k) || (phone && S.tourActive);
    });
    $$('#phoneNav .phone-nav__btn').forEach(function (b) { var k = b.dataset.sheet; b.setAttribute('aria-pressed', String(k === 'tour' ? S.tourActive : S.sheet === k)); });
    $('#app').setAttribute('data-sheet', phone ? (S.sheet || 'none') : 'desktop');
  }
  function initFolds() {
    $$('.panel__fold').forEach(function (b) {
      on(b, 'click', function () {
        var panel = b.closest('.panel'), col = panel.classList.toggle('is-collapsed');
        b.setAttribute('aria-expanded', String(!col)); b.setAttribute('aria-label', (col ? 'Expand' : 'Collapse') + b.getAttribute('aria-label').replace(/^(Collapse|Expand)/, ''));
      }, 'fold');
    });
  }
  function dlgOpen() { var d = $('#dlgBack'); return d && !d.hidden; }
  var dlgReturn = null;
  function openDialog(pane) {
    dlgReturn = document.activeElement;
    $('#dlgBack').hidden = false; showPane(pane || 'prov');
    var c = $('#dlgClose'); if (c) c.focus();
  }
  function closeDialog() { $('#dlgBack').hidden = true; if (dlgReturn && dlgReturn.focus) { try { dlgReturn.focus(); } catch (e) { /* gone */ } } }
  function showPane(p) {
    var ids = { prov: 'paneProv', session: 'paneSession', help: 'paneHelp' };
    Object.keys(ids).forEach(function (k) { $('#' + ids[k]).hidden = k !== p; });
    $$('#dlgTabs .tab').forEach(function (t) { var s = t.dataset.pane === p; t.setAttribute('aria-selected', String(s)); t.tabIndex = s ? 0 : -1; });
    $('#dlgTitle').textContent = p === 'prov' ? 'Loom log' : p === 'session' ? 'Session log' : 'Help';
    if (p === 'session') renderSession();
  }
  function trapFocus(e) {
    if (e.key !== 'Tab' || !dlgOpen()) return;
    var f = $$('#dlg button:not([disabled]), #dlg [tabindex="0"], #dlg a[href]').filter(function (x) { return x.offsetParent !== null; });
    if (!f.length) return;
    var first = f[0], last = f[f.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    else if (!$('#dlg').contains(document.activeElement)) { e.preventDefault(); first.focus(); }
  }
  function renderSession() {
    var p = $('#paneSession'); p.textContent = '';
    var info = el('p', { class: 'dim' }, 'Events from this page session. Nothing leaves your browser.');
    var ul = el('ol', { class: 'session-log', reversed: true });
    LOG.slice().reverse().slice(0, 120).forEach(function (r) { ul.appendChild(el('li', { class: 'session-log__row is-' + r.level }, el('span', { class: 'session-log__t num', text: (r.t / 1000).toFixed(1) + ' s' }), el('span', { class: 'session-log__l', text: r.level }), el('span', { class: 'session-log__m', text: r.msg }))); });
    p.appendChild(info); p.appendChild(ul);
  }
  function renderHelp() {
    var p = $('#paneHelp'); p.textContent = '';
    var rows = [['Drag', 'Orbit the model'], ['Scroll / pinch', 'Zoom'], ['Click or tap', 'Pick a region: opens its card and drops a marker'],
      ['1 to 7', 'Camera views (Home, Left, Right, Top, Front, Medial, Inside)'], ['T', 'Start or stop the guided tour'], ['Left / Right arrows', 'Previous or next tour step'],
      ['G W D R S L A', 'Toggle glass cortex, wet cortex, deep structures, tracts, slices, labels, activation'], ['M', 'Music on or off'], ['F', 'Full screen'], ['Esc', 'Close this window or leave the tour'], ['?', 'Open this help']];
    var dl = el('dl', { class: 'help' });
    rows.forEach(function (r) { dl.appendChild(el('div', { class: 'help__row' }, el('dt', null, el('span', { class: 'kbd', text: r[0] })), el('dd', { text: r[1] }))); });
    p.appendChild(dl);
    p.appendChild(el('p', { class: 'dim', text: 'Everything is a template or a model, not a person: no patient data. Synthetic parts are tagged SYN, illustrative parts ILL.' }));
  }
  function renderProv() {
    var P = S.data.prov, p = $('#paneProv'); p.textContent = '';
    if (!P) { p.appendChild(el('p', { class: 'dim', text: 'provenance.json did not load.' })); return; }
    p.appendChild(el('p', { class: 'dim', text: P.intro }));
    p.appendChild(el('h3', { class: 'prov-h', text: 'Notices' }));
    var nl = el('ul', { class: 'notice-list' });
    (P.notices || []).forEach(function (n) { nl.appendChild(el('li', { class: 'notice' }, el('span', { class: 'tagpill tagpill--' + n.tag.toLowerCase(), text: n.tag }), el('span', { text: n.text }))); });
    p.appendChild(nl);
    p.appendChild(el('h3', { class: 'prov-h', text: 'Data sources and licence grades' }));
    (P.sources || []).forEach(function (s) {
      var card = el('article', { class: 'src' },
        el('header', { class: 'src__head' }, el('h4', { class: 'src__name', text: s.name }), el('span', { class: 'grade grade--' + s.grade.toLowerCase(), title: (P.grades || {})[s.grade] || '', text: s.grade })),
        el('p', { class: 'src__line' }, el('b', { text: 'Used for ' }), s.used_for),
        el('p', { class: 'src__line' }, el('b', { text: 'Licence ' }), s.licence),
        el('p', { class: 'src__line' }, el('b', { text: 'Changes ' }), s.changes),
        el('p', { class: 'src__line dim' }, el('b', { text: 'Cite ' }), s.cite));
      p.appendChild(card);
    });
    if (P.generated_content) {
      p.appendChild(el('h3', { class: 'prov-h', text: 'Generated content' }));
      var gl = el('ul', { class: 'plain-list' });
      Object.keys(P.generated_content).forEach(function (k) { gl.appendChild(el('li', null, el('b', { text: title(k) + ': ' }), P.generated_content[k])); });
      p.appendChild(gl);
    }
    if (P.build) {
      p.appendChild(el('h3', { class: 'prov-h', text: 'This build' }));
      var kv = el('dl', { class: 'kv' });
      function row(k, v) { kv.appendChild(el('div', { class: 'kv__row' }, el('dt', { text: k }), el('dd', null, typeof v === 'string' ? document.createTextNode(v) : v))); }
      row('Kind', P.build.kind + (P.build.kind === 'repo' ? ' (lite scenes, no music, no style-board thumbnails)' : ' (full scenes, music, thumbnails)'));
      row('Tool', P.build.tool + ' sha256 ' + P.build.tool_sha256_16);
      (P.scenes || []).forEach(function (sc) {
        var c = sc.counts || {};
        var bits = [];
        if (c.shapes) bits.push(fmtNum(c.shapes) + ' shapes');
        if (c.triangles) bits.push(fmtNum(c.triangles) + ' triangles');
        if (c.vertices) bits.push(fmtNum(c.vertices) + ' vertices');
        if (c.tract_fibres) bits.push(fmtNum(c.tract_fibres) + ' SYNTHETIC tract arcs (' + fmtNum(c.tract_points) + ' points)');
        if (c.cortex_tris) bits.push(fmtNum(c.cortex_tris) + ' cortex triangles');
        row(sc.id + ' scene', sc.variant + ': ' + sc.file + ', ' + fmtBytes(sc.bytes) + (bits.length ? '; ' + bits.join(', ') : ''));
        row(sc.id + ' sha256', el('code', { class: 'hash', text: 'scene ' + sc.source_sha256 + (sc.served_sha256 !== sc.source_sha256 ? ' (served bytes differ: ' + sc.served_sha256 + ')' : '') }));
        if (sc.note) row(sc.id + ' note', sc.note);
      });
      (P.files || []).forEach(function (f) { row(f.path, el('code', { class: 'hash', text: f.sha256 + ' (' + fmtBytes(f.bytes) + ')' })); });
      p.appendChild(kv);
    }
    var R = P.receipt || {};
    p.appendChild(el('h3', { class: 'prov-h', text: 'Receipt' }));
    p.appendChild(el('p', { class: 'receipt' }, el('span', { class: 'tagpill', text: (R.status || 'placeholder').toUpperCase() }), el('code', { class: 'hash', text: R.sha256 || 'none' })));
    p.appendChild(el('p', { class: 'dim', text: R.note || '' }));
    var rt = el('div', { class: 'rig' });
    p.appendChild(el('h3', { class: 'prov-h', text: 'Rig' })); p.appendChild(rt); S.rigEl = rt; updateRig();
  }
  function updateRig() {
    if (!S.rigEl) return;
    var gl = '';
    try { var cv = document.createElement('canvas'), c = cv.getContext('webgl2'), e = c && c.getExtension('WEBGL_debug_renderer_info'); gl = e ? c.getParameter(e.UNMASKED_RENDERER_WEBGL) : (c ? c.getParameter(c.RENDERER) : 'no WebGL 2'); } catch (e) { gl = 'unknown'; }
    S.rigEl.textContent = '';
    var kv = el('dl', { class: 'kv' });
    [['X_ITE', B ? B.version : 'not loaded'], ['Renderer', gl], ['Tone mapping', 'KHR_PBR_NEUTRAL'], ['Transparency', 'Order-independent transparency off (it hides the custom glass)'],
      ['Scene load', S.loadMs ? (S.loadMs / 1000).toFixed(1) + ' s' : 'pending'], ['Frame rate', B ? B.getCurrentFrameRate().toFixed(1) + ' fps (relative: depends on this GPU)' : '-']].forEach(function (r) { kv.appendChild(el('div', { class: 'kv__row' }, el('dt', { text: r[0] }), el('dd', { text: r[1] }))); });
    S.rigEl.appendChild(kv);
  }

  // ------------------------------------------------------------------------------------------------ scene loading
  async function loadScene(kind, opts) {
    opts = opts || {};
    var url = (CFG.scenes || {})[kind];
    if (!url) throw new Error('No ' + kind + ' scene in this build.');
    var token = ++S.loadToken, t0 = performance.now();
    S.ready = false; S.scene = null; S.nodes = {}; S.missing = {}; S.pin = null; S.sensors = []; S.touched = {}; S.hl = null; S.tractColorNode = null;
    onOut(); setLoading(true, kind === 'brain' ? ((S.data.tour && S.data.tour.loading) || 'Loading the template brain') : 'Loading the torso CT');
    var bytes = (CFG.sceneBytes || {})[kind];
    var tick = every(function () { $('#loaderSub').textContent = ((performance.now() - t0) / 1000).toFixed(0) + ' s' + (bytes ? ' | ' + fmtBytes(bytes) + ' scene' : ''); }, 500, 'loader tick');
    try {
      await withTimeout(B.loadURL(new X3D_.MFString(url)), CFG.loadBudgetMs || 240000, 'Loading the ' + kind + ' scene');
      if (token !== S.loadToken) return;
      S.scene = B.currentScene; S.kind = kind;
      if (!node(kind === 'brain' ? 'SW_CORTEX' : 'SW_SKIN')) throw new Error('The scene loaded but does not contain the expected nodes (' + url + ').');
      S.loadMs = performance.now() - t0;
      await onSceneReady(kind);
      await nextFrames(2);
      S.ready = true;
      setLoading(false);
      log('info', kind + ' scene ready in ' + (S.loadMs / 1000).toFixed(1) + ' s');
      if (kind === 'brain' && !opts.quiet && S.data.tour && S.data.tour.hint && !S.hintShown) { S.hintShown = true; toast(S.data.tour.hint, 7000); }
    } catch (e) {
      S.ready = false;
      log('error', 'scene ' + kind + ': ' + e.message);
      setLoading(false); $('#app').setAttribute('data-state', 'error');
      showBanner('The ' + (kind === 'brain' ? 'brain' : 'torso') + ' scene did not load.', e.message, function () { hideBanner(); return switchTab(kind, true); });
      throw e;
    } finally { clearInterval(tick); }
  }
  async function onSceneReady(kind) {
    S.torsoSw = null;
    if (kind === 'torso') {
      S.torsoSw = [];
      for (var i = 0; i < S.scene.rootNodes.length; i++) { try { var n = S.scene.rootNodes[i]; var nm = n && n.getNodeName && n.getNodeName(); if (nm && /^SW_/.test(nm)) S.torsoSw.push(nm); } catch (e) { /* skip */ } }
    }
    captureBaseline();
    S.regionPref = 'L'; S.region = null; S.lookId = null; S.lookExtras = []; S.prevLookImg = null; S.presetOps = []; S.tourActive = false; S.cam.autoHidLeft = false; S.cam.name = 'VP_HOME';
    $('#tour').hidden = true; $('#app').classList.remove('is-touring');
    makePageViewpoints();
    try { S.pin = await makePin(); } catch (e) { log('warn', 'pin: ' + e.message); S.pin = null; }
    installSensors();
    buildLayerUI(); buildViewUI(); buildLookUI(); buildRegionList(); buildTourUI(); initAudio();
    clearRegion();
    $('#btnCompare').disabled = true;
    flyTo(poseOf('VP_HOME'), true);
    $$('#views .chip').forEach(function (b) { b.setAttribute('aria-pressed', String(b.dataset.vp === 'VP_HOME')); });
    $('#regionEmpty').textContent = kind === 'brain' ? 'Click or tap the brain, pick a region from the list, or take the tour.' : 'Click or tap the body, pick a structure from the list, or take the tour.';
    $('#badge').textContent = kind === 'brain' ? ((S.data.tour && S.data.tour.badge) || 'Synthetic illustration') : 'Illustrative rendering';
    applySheets();
    updateRig();
  }
  async function switchTab(kind, force) {
    if (!force && kind === S.kind && S.ready) return;
    if (!CFG.scenes[kind]) return;
    S.audio.on = false;
    $$('.tabs--top .tab').forEach(function (t) { var s = t.dataset.tab === kind; t.setAttribute('aria-selected', String(s)); t.tabIndex = s ? 0 : -1; });
    $('#app').setAttribute('data-tab', kind);
    hideBanner();
    try { await loadScene(kind, { quiet: true }); } catch (e) { /* banner shown by loadScene */ }
    applySheets();
  }

  // ------------------------------------------------------------------------------------------------ keyboard and global wiring
  function typing(t) { return t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT' || t.isContentEditable); }
  function onKey(e) {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    if (dlgOpen()) { if (e.key === 'Escape') { e.preventDefault(); closeDialog(); } else trapFocus(e); return; }
    if (typing(e.target)) { if (e.key === 'Escape') e.target.blur(); return; }
    var k = e.key, lk = k.length === 1 ? k.toLowerCase() : k;
    if (k === 'Escape') { if (S.tourActive) endTour(); else if (S.region) clearRegion(); return; }
    if (k === '?') { e.preventDefault(); openDialog('help'); return; }
    if (S.tourActive && (k === 'ArrowRight' || k === 'ArrowLeft')) { e.preventDefault(); if (k === 'ArrowRight') { if (S.tourIdx >= tourSteps().length - 1) endTour(); else goStep(S.tourIdx + 1); } else goStep(S.tourIdx - 1); return; }
    if (/^[1-9]$/.test(k)) { var vl = viewList(); var nm = vl[Number(k) - 1]; if (nm) { e.preventDefault(); setView(nm); } return; }
    if (lk === 't') { e.preventDefault(); if (S.tourActive) endTour(); else startTour(); return; }
    if (lk === 'f') { toggleFull(); return; }
    if (lk === 'm') { if (S.audio.ok) setAudio(!S.audio.on); return; }
    if (S.kind === 'brain') {
      var keys = { g: 'glass', w: 'wet', d: 'deep', r: 'tracts', s: 'slices', l: 'labels', a: 'activation' };
      if (keys[lk]) { e.preventDefault(); var d = MAIN_DEF[keys[lk]]; if (node(d)) setLayer(keys[lk], !isOn(d)); }
    }
  }
  function toggleFull() {
    try { if (document.fullscreenElement) document.exitFullscreen(); else if (document.documentElement.requestFullscreen) document.documentElement.requestFullscreen(); } catch (e) { log('warn', 'fullscreen: ' + e.message); }
  }
  function wireStatic() {
    on($('#btnTour'), 'click', function () { if (S.tourActive) endTour(); else startTour(); }, 'tour button');
    on($('#tourNext'), 'click', function () { if (S.tourIdx >= tourSteps().length - 1) endTour(); else goStep(S.tourIdx + 1); }, 'tour next');
    on($('#tourBack'), 'click', function () { goStep(S.tourIdx - 1); }, 'tour back');
    on($('#tourExit'), 'click', endTour, 'tour exit');
    on($('#btnLog'), 'click', function () { openDialog('prov'); }, 'open log');
    on($('#btnHelp'), 'click', function () { openDialog('help'); }, 'open help');
    on($('#bannerLog'), 'click', function () { openDialog('session'); }, 'banner details');
    on($('#bannerClose'), 'click', hideBanner, 'banner close');
    on($('#bannerRetry'), 'click', function () { if (bannerRetry) return bannerRetry(); }, 'banner retry');
    on($('#dlgClose'), 'click', closeDialog, 'close dialog');
    on($('#dlgBack'), 'pointerdown', function (e) { if (e.target === $('#dlgBack')) closeDialog(); }, 'dialog backdrop');
    $$('#dlgTabs .tab').forEach(function (t) { on(t, 'click', function () { showPane(t.dataset.pane); }, 'dialog tab'); on(t, 'keydown', function (e) { tabKeys(e, $('#dlgTabs'), showPane); }, 'dialog tab keys'); });
    $$('.tabs--top .tab').forEach(function (t) {
      on(t, 'click', function () { return switchTab(t.dataset.tab); }, 'scene tab');
      on(t, 'keydown', function (e) { var tabs = $$('.tabs--top .tab'), i = tabs.indexOf(t), j = e.key === 'ArrowRight' ? (i + 1) % tabs.length : e.key === 'ArrowLeft' ? (i - 1 + tabs.length) % tabs.length : -1; if (j >= 0) { e.preventDefault(); tabs[j].focus(); } }, 'scene tab keys');
    });
    on($('#btnSound'), 'click', function () { setAudio(!S.audio.on); }, 'sound button');
    on($('#btnSound2'), 'click', function () { setAudio(!S.audio.on); }, 'sound button 2');
    on($('#vol'), 'input', function () {
      var v = $('#vol'); v.style.setProperty('--fill', v.value + '%');
      var snd = node('SND'); if (snd) snd.intensity = Number(v.value) / 100;
    }, 'volume');
    on($('#btnFull'), 'click', toggleFull, 'fullscreen');
    if (!(document.documentElement.requestFullscreen)) $('#btnFull').hidden = true;
    on($('#btnReset'), 'click', resetAll, 'reset');
    on($('#btnLookReset'), 'click', function () { return selectLook(null); }, 'look reset');
    on($('#btnClear'), 'click', clearRegion, 'clear region');
    on($('#btnFocus'), 'click', function () { if (S.region) focusRegion(S.region); }, 'focus region');
    on($('#regionFilter'), 'input', filterRegions, 'filter regions');
    // hold-to-compare: show the previous look's snapshot while pressed
    var cmp = $('#btnCompare'), veil = $('#veil'), img = $('#veilImg');
    function cmpOn() { if (!S.prevLookImg) return; img.src = S.prevLookImg; veil.style.transition = 'none'; veil.style.opacity = '1'; }
    function cmpOff() { veil.style.transition = 'opacity 200ms'; veil.style.opacity = '0'; }
    on(cmp, 'pointerdown', cmpOn, 'compare down'); on(cmp, 'pointerup', cmpOff, 'compare up'); on(cmp, 'pointerleave', cmpOff, 'compare leave'); on(cmp, 'blur', cmpOff, 'compare blur');
    on(cmp, 'keydown', function (e) { if (e.key === ' ' || e.key === 'Enter') { e.preventDefault(); cmpOn(); } }, 'compare key down');
    on(cmp, 'keyup', function (e) { if (e.key === ' ' || e.key === 'Enter') { e.preventDefault(); cmpOff(); } }, 'compare key up');
    // detail (resolution) chips
    var qr = $('#qualRow'); qr.textContent = '';
    [['fast', 'Fast'], ['balanced', 'Balanced'], ['sharp', 'Sharp']].forEach(function (q) {
      var b = el('button', { class: 'chip', type: 'button', 'data-q': q[0], 'aria-pressed': String(q[0] === S.quality), text: q[1], title: 'Render resolution: faster on slow graphics, sharper on fast ones' });
      on(b, 'click', function () { applyQuality(q[0]); }, 'quality'); qr.appendChild(b);
    });
    // pointer bookkeeping so a click can be told from an orbit drag
    var stage = $('#stage');
    on(window, 'pointermove', function (e) { S.ptr.x = e.clientX; S.ptr.y = e.clientY; if (S.ptr.downT) S.ptr.moved = Math.max(S.ptr.moved, Math.hypot(e.clientX - S.ptr.downX, e.clientY - S.ptr.downY)); }, 'pointer move', { passive: true });
    on(window, 'pointerdown', function (e) { S.ptr.downX = e.clientX; S.ptr.downY = e.clientY; S.ptr.downT = performance.now(); S.ptr.moved = 0; S.ptr.type = e.pointerType || 'mouse'; S.ptr.x = e.clientX; S.ptr.y = e.clientY; }, 'pointer down', { capture: true, passive: true });
    on(stage, 'pointerleave', onOut, 'stage leave');
    on(document, 'keydown', onKey, 'keyboard');
    var mq = window.matchMedia ? window.matchMedia('(max-width: 640px)') : null;
    if (mq) on(mq, 'change', applySheets, 'media change');
    watchLayout();
    every(function () { if (!B || !S.ready) return; var f = B.getCurrentFrameRate(); $('#fps').textContent = f >= 10 ? f.toFixed(0) : f.toFixed(1); }, 1000, 'fps');
  }
  function resetAll() {
    if (S.tourActive) endTour();
    S.lookId = null; S.prevLookImg = null; S.presetOps = [];
    clearHighlight(); restoreTouched(); S.sw = Object.assign({}, S.baseSw); S.glow = S.baseGlow; S.clip = S.baseClip;
    applyStyle(); applySwitches(); renderLookState(); $('#btnCompare').disabled = true;
    clearRegion(); setView('VP_HOME');
    if (S.audio.on) setAudio(false);
    toast('Back to the scene as built.', 2200);
  }

  // ------------------------------------------------------------------------------------------------ boot
  async function boot() {
    try { var q = store('quality'); if (q === 'fast' || q === 'sharp' || q === 'balanced') S.quality = q; } catch (e) { /* default */ }
    wireStatic(); renderHelp();
    setLoading(true, 'Starting');
    var dataP = loadData();
    try {
      await loadXite();
      await dataP;
      var T = S.data.tour;
      if (T) {
        $('#brandTitle').textContent = T.title || 'Neural Canvas'; $('#brandTag').textContent = T.tagline || ''; $('#legal').textContent = T.footer ? (T.footer + ' Region text is model-written and can be wrong. No patient data.') : $('#legal').textContent;
        document.title = (T.title || 'Neural Canvas') + ' - Brain Loom demo';
      }
      if (T && T.layer_switches) Object.keys(T.layer_switches).forEach(function (k) { MAIN_DEF[k] = T.layer_switches[k]; });
      if (!CFG.scenes || !CFG.scenes.torso) { $$('.tabs--top .tab[data-tab="torso"]').forEach(function (t) { t.hidden = true; }); }
      renderProv(); buildPhoneNav(); initFolds();
      await mountBrowser();
      await loadScene('brain');
    } catch (e) {
      setLoading(false); $('#app').setAttribute('data-state', 'error');
      if ($('#banner').hidden) showBanner('The page could not start.', e.message, function () { location.reload(); });
      log('error', 'boot: ' + e.message);
    }
    S.bootDone = true;
  }
  window.__loom = {
    get state() { return { kind: S.kind, ready: S.ready, lookId: S.lookId, region: S.region && S.region.id, tour: S.tourActive ? S.tourIdx : null, sw: S.sw, glow: S.glow, clip: S.clip, audio: S.audio, cam: S.cam.name, sensors: S.sensors.length, touched: Object.keys(S.touched).length, errors: errCount }; },
    get log() { return LOG.slice(); },
    pick: function (pt, hemi, deep) { return nearestRegion(pt, hemi, deep); },
    select: function (id) { selectRegion(id, { source: 'api' }); },
    node: node,
    setAudio: setAudio,
    frames: nextFrames,
    camera: function () { try { var v = B.getActiveLayer().getViewpoint(), p = v.getUserPosition(); return { name: v.description, position: [p.x, p.y, p.z], target: S.cam.target }; } catch (e) { return null; } },
    version: 1
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', guard(boot, 'boot')); else guard(boot, 'boot')();
})();
