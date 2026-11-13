/* x3d.mol page: catalogue, colour schemes, residue picking, zinc sites, the AlphaFold PAE map and the receipt card. */
(function () {
  "use strict";
  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const hp = new URLSearchParams(location.hash.slice(1));
  const AA3 = { CYS: "C", HIS: "H", ASP: "D", GLU: "E" };
  const BAND = [[90, "very high", "#0053d6"], [70, "confident", "#65cbf3"], [50, "low", "#ffdb13"], [0, "very low", "#ff7d45"]];
  const SSNAME = { H: "helix", E: "strand", "-": "coil", n: "nucleic acid" };
  const state = { catalog: null, receipt: null, credits: null, body: null, entry: null, model: null, scheme: "file", pinned: null, paeLock: null, hover: -1 };

  async function getJSON(url) { const r = await fetch(url); if (!r.ok) throw new Error(url + " " + r.status); return r.json(); }
  async function sha256(text) { const d = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text)); return [...new Uint8Array(d)].map((b) => b.toString(16).padStart(2, "0")).join(""); }
  async function fetchScene(entry) {
    try {
      if (!window.__xmolPlain && typeof DecompressionStream !== "undefined") {  // a host that cannot serve .gz sets __xmolPlain
        const r = await fetch(entry.file + ".gz");
        if (r.ok) return await new Response(r.body.pipeThrough(new DecompressionStream("gzip"))).text();
      }
    } catch (e) { /* fall through to the plain file */ }
    const r = await fetch(entry.file); if (!r.ok) throw new Error(entry.file + " " + r.status);
    return r.text();
  }
  const band = (v) => BAND.find(([lo]) => v >= lo) || BAND[3];

  function buildCatalogue() {
    const groups = [["pdb", "Zinc fingers, 14 deposited structures"], ["afdb", "AlphaFold DB, 5 predicted models"]];
    $("#list").innerHTML = groups.map(([k, label]) => `<div data-kind="${k}"><h3>${label}</h3>` + state.catalog.scenes.filter((s) => s.kind === k).map((s) =>
      `<button class="item" data-id="${esc(s.id)}"><b>${esc(s.id.replace(/-F1$/, "").toUpperCase())}</b><span>${esc(s.title.replace(/^[^:]+:\s*/, "").replace(/ \[chains.*$/, ""))}</span>` +
      `<i>${s.residues} aa${s.sites.length ? " · " + s.sites.length + " Zn" : ""}${s.mean_plddt ? " · pLDDT " + s.mean_plddt : ""}</i></button>`).join("") + "</div>").join("");
    buildCinema(); buildDiffusionList();
    for (const t of document.querySelectorAll("#tabs button")) t.onclick = () => showTab(t.dataset.k);
    showTab("pdb");
    for (const b of document.querySelectorAll(".item")) b.onclick = () => load(b.dataset.id);
  }

  /* ---------- the Blender cut: Cycles stills of the same structures, and the X3D the Blender stage wrote ---------- */
  function buildCinema() {
    const c = state.cine; if (!c || !c.scenes) return;
    const ids = Object.keys(c.scenes).filter((id) => c.scenes[id].jpg);
    if (!ids.length) return;
    $("#cineN").textContent = ids.length; $('#tabs [data-k="cine"]').hidden = false;
    const title = (id) => { const e = state.catalog.scenes.find((s) => s.id === id); return e ? e.title.replace(/ \[chains.*$/, "") : id; };
    const div = document.createElement("div"); div.dataset.kind = "cine";
    div.innerHTML = `<h3>Rendered in Blender, ${ids.length} stills</h3>` + ids.map((id) => `<button class="shot" data-cine="${esc(id)}"><img src="cinema/${esc(c.scenes[id].jpg.file)}" alt="${esc(title(id))}, rendered in Blender" loading="lazy">` +
      `<span>${esc(title(id))}</span><i>${c.scenes[id].colour === "plddt" ? "coloured by pLDDT" : "element colours, zinc in gold"} · X3D ${Math.round(c.scenes[id].x3d.gz.bytes / 1024)} KB gzip</i></button>`).join("");
    $("#list").appendChild(div);
    for (const b of div.querySelectorAll(".shot")) b.onclick = () => openCinema(b.dataset.cine);
    $("#cineClose").onclick = () => { $("#cineBox").hidden = true; };
    $("#cineOpen").onclick = () => { $("#cineBox").hidden = true; const id = $("#cineBox").dataset.id; load(id); };
  }
  function openCinema(id) {
    const c = state.cine, s = c.scenes[id], g = state.gate && state.gate.scenes[id], t = c.tools, ctl = state.gate && state.gate.controls[id];
    const e = state.catalog.scenes.find((x) => x.id === id);
    const m = (g && g.measured) || {};
    const wit = g ? (g.witness === "pass" ? `<span class="ok">pass</span>` : `<span class="bad">${esc([].concat(g.witness).join("; "))}</span>`) : "not run";
    $("#cineBox").dataset.id = id;
    $("#cineBody").innerHTML = `<h2>${esc(e ? e.title.replace(/ \[chains.*$/, "") : id)}, rendered in Blender</h2>
      <img src="cinema/${esc(s.jpg.file)}" alt="${esc(id)} cartoon, rendered in Blender with Cycles">
      <p>molecularnodes ${esc(t.molecularnodes)} draws the cartoon in Blender ${esc(t.blender)}; Cycles renders it on the CPU at ${c.render.samples} samples with ${esc(s.denoise)} and the ${esc(s.view_transform)} view transform.
      ${s.colour === "plddt" ? "Colour is the AlphaFold confidence (pLDDT) band of each residue, in the molecularnodes palette." : "Colour is by element, with each chain's carbons in its own tint; zinc ions are gold spheres."}
      The same mesh is then written as X3D by x3d-blender-io and checked before it is offered here.</p>
      <dl><dt>X3D</dt><dd class="mono">${esc(s.x3d.file)} · ${s.evaluated_faces} faces · ${Math.round(s.x3d.bytes / 1024)} KB (${Math.round(s.x3d.gz.bytes / 1024)} KB gzip)</dd>
      <dt>sha256</dt><dd class="mono">${esc(s.x3d.sha256.slice(0, 16))}…</dd>
      <dt>written by</dt><dd>x3d-blender-io ${esc(t.x3d_blender_io.commit.slice(0, 12))}</dd>
      <dt>validator</dt><dd>${g ? `x3d_mcp fork ${esc(state.gate.validator.commit.slice(0, 12))} · ${g.xsd_valid ? "XSD valid" : "XSD INVALID"}, ${g.semantic_errors} semantic errors, ${g.semantic_warnings} warnings` : "not run"}</dd>
      <dt>witness</dt><dd>${wit}${m.ca_nearest_max_A !== undefined ? ` · every residue's backbone atom has a mesh vertex within ${m.ca_nearest_max_A} Å (median ${m.ca_nearest_median_A} Å) · ${(100 * m["mesh_within_3.5A_of_an_atom"]).toFixed(1)}% of vertices lie within 3.5 Å of an atom` : ""}${m.plddt_colour_agreement ? ` · ${(100 * m.plddt_colour_agreement).toFixed(1)}% of vertex colours match the nearest residue's pLDDT band` : ""}${m.zn_nearest_max_A !== undefined ? ` · every zinc within ${m.zn_nearest_max_A} Å of the mesh` : ""}</dd>
      <dt>controls</dt><dd>${ctl ? `${ctl.filter((x) => x.ok).length} of ${ctl.length} behaved (shifted, wrong-source${s.colour === "plddt" ? ", one-colour and channel-swapped" : ""} copies refused; the honest file passed)` : "not run"}</dd></dl>
      <p class="fine">${s.colour_channels_clamped_to_1 ? `${s.colour_channels_clamped_to_1} colour channels were clamped from 1.000169 to 1, because the X3D 4.0 schema refuses colours above 1. ` : ""}The live viewer on this page draws the scenes that the x3d.mol builder writes; drawing this Blender-made file live is the next step. The still is a picture of the same coordinates, not a measurement.</p>`;
    const base = window.__xmolFileBase, get = $("#cineGet");  // a host that blocks downloads (a sandboxed preview) links to the repository copy instead
    get.href = (base || "cinema/") + s.x3d.gz.file;
    if (base) { get.removeAttribute("download"); get.target = "_blank"; get.rel = "noopener"; get.textContent = "Get the X3D (gzip) from GitHub"; }
    $("#cineBox").hidden = false;
  }

  /* ---------- AlphaFold 3 diffusion illustration (src/anim.py writes the X3D; viewer/diffuse.js plays it) ---------- */
  function buildDiffusionList() {
    const a = state.animIndex; if (!a || !a.scenes || !a.scenes.length) return;
    $("#diffN").textContent = a.scenes.length; $('#tabs [data-k="diff"]').hidden = false;
    const div = document.createElement("div"); div.dataset.kind = "diff";
    div.innerHTML = `<h3>AlphaFold 3, diffusion · illustration</h3><p class="note">AlphaFold 3 places atoms by diffusion: it starts from atoms scattered as noise and removes the noise step by step, on a fixed schedule, until a structure is left. Here that schedule is run backwards onto known coordinates. <b>Nothing is predicted in your browser.</b></p>` +
      a.scenes.map((s) => `<button class="item" data-anim="${esc(s.id)}"><b>${esc(s.id.replace(/-F1$/, "").toUpperCase())}</b><span>${esc(s.title.replace(/^[^:]+:\s*/, "").replace(/, diffusion illustration$/, ""))}</span>` +
        `<i>${s.atoms.toLocaleString("en")} atoms${s.zinc ? " · " + s.zinc + " Zn" : ""} · ${s.keys} keys · ${s.kind === "afdb" ? "pLDDT and PAE" : "crystal, no scores"}</i></button>`).join("");
    const film = state.film && state.film.scenes ? Object.entries(state.film.scenes).filter(([, f]) => f.mp4) : [];
    if (film.length) div.insertAdjacentHTML("beforeend", `<h3>Rendered in Blender · Cycles</h3>` + film.map(([id, f]) =>
      `<figure class="film"><video src="cinema/${esc(f.mp4.file)}" poster="cinema/${esc(f.poster.file)}" controls loop muted playsinline preload="none" aria-label="${esc(id)} diffusion illustration, rendered in Blender"></video>` +
      `<figcaption>${esc(id.replace(/-F1$/, "").toUpperCase())} · the same X3D keyframes, ${f.frames} frames in Cycles · last frame ${f.check ? f.check.last_frame_rms_from_rest_A : "?"} Å from the file's atoms · illustration, not a live run</figcaption></figure>`).join(""));
    $("#list").appendChild(div);
    for (const b of div.querySelectorAll("[data-anim]")) b.onclick = () => openAnim(b.dataset.anim);
  }
  function stopAnim() {
    const p = state.player; if (!p) return;
    p.dispose(); state.player = null; document.body.classList.remove("anim"); $("#diff").hidden = true;
    for (const m of state.body.meshes) { m.visibility = 1; m.isPickable = true; }
    state.body.setLayer("sites", $("#l_sites").checked);
    if (state.paeDraw) { state.paeDraw.restore(); state.paeDraw = null; }
    for (const b of document.querySelectorAll("[data-anim]")) b.classList.remove("on");
  }
  async function openAnim(id) {
    stopAnim();
    const ae = state.animIndex.scenes.find((s) => s.id === id) || state.animIndex.scenes[0];
    await load(ae.id, true);
    $("#busy").hidden = false; $("#busy").textContent = "Reading the diffusion keyframes…";
    const text = await fetchScene(ae);
    const shaOk = (await sha256(text)) === ae.sha256;
    const anim = XMolDiffuse.parse(text);
    const low = matchMedia("(max-width:700px)").matches;
    const p = XMolDiffuse.create(state.body, anim, { low });
    state.player = p; state.animEntry = ae; state.animShaOk = shaOk; state.follow = true;
    for (const b of document.querySelectorAll(".item")) b.classList.toggle("on", b.dataset.anim === ae.id);
    showTab("diff");
    document.body.classList.add("anim"); $("#diff").hidden = false;
    $("#dNote").textContent = anim.disclaimer;
    const sw = (c, t) => `<span><u style="background:${c}"></u>${t}</span>`;
    $("#dLegend").innerHTML = sw("#b8d6ff", "not yet placed") + (ae.kind === "afdb"
      ? BAND.map((b, i) => sw(b[2], b[1])).join("")
      : sw("#8c9ead", "C") + sw("#4073ff", "N") + sw("#ff4740", "O") + sw("#ffd940", "S") + sw("#ff8c1a", "P") + sw("#b3cceb", "Zn"));
    const ext = p.extent(), B = BABYLON, near = Math.max(36, state.body.radius * 2.15), far = Math.max(near, ext.radius * 2.3);
    const ctr = new B.Vector3(...ext.center);
    state.body.tween({ target: ctr, radius: far, alpha: -1.0, beta: 1.15 }, 0);
    const pae = state.model.meta.pae_half_angstrom;
    state.paeDraw = pae && state.pae ? XMolDiffuse.paeReveal($("#paeCanvas"), pae, state.pae.N, state.pae.M) : null;
    const scrub = $("#dScrub");
    p.onFrame = (info) => {
      if (!state.scrubbing) scrub.value = String(Math.round(info.fraction * 1000));
      const vis = info.hold;
      for (const m of state.body.meshes) { m.visibility = vis; m.isPickable = vis > 0.9; }
      state.body.sitesNode.setEnabled($("#l_sites").checked && vis > 0.6);
      if (state.follow) { const cam = state.body.camera, want = near + (far - near) * Math.pow(Math.min(1, info.shown / info.cap), 0.7); cam.radius += (want - cam.radius) * (p.playing ? 0.3 : 1); cam.setTarget(B.Vector3.Lerp(cam.target, ctr, p.playing ? 0.3 : 1)); }
      if (state.paeDraw) state.paeDraw(Math.min(1, info.fraction / anim.meta.denoise_fraction[0]));
      if ((state.tickA = (state.tickA || 0) + 1) % 4 === 0 || !p.playing) {
        $("#dRead").innerHTML = info.sigma > 0
          ? `step <b>${info.step}</b> of ${info.steps} · noise σ <b>${info.sigma >= 100 ? Math.round(info.sigma) : info.sigma.toFixed(1)} Å</b>${info.sigma - info.shown > 0.05 ? ` (drawn at ${info.shown.toFixed(1)} Å)` : ""} · <b>${Math.round(info.settled * 100)}%</b> of atoms within 1 Å of their place`
          : `step <b>${info.steps}</b> of ${info.steps} · noise 0 · every atom on the ${ae.kind === "afdb" ? "AlphaFold DB model" : "deposited crystal"} coordinates`;
      }
    };
    $("#dPlay").textContent = "Pause";
    renderAnimReceipt();
    $("#busy").hidden = true;
    if (!window.__xmolNoHash) history.replaceState(null, "", "#anim=" + ae.id);
    window.__xmolAnimReady = { id: ae.id, atoms: anim.n, keys: anim.key.length, shaOk };
  }
  function renderAnimReceipt() {
    const ae = state.animEntry, r = state.receipt && state.receipt.anim, sc = r && r.scenes && r.scenes[ae.id];
    const dl = document.createElement("dl"); dl.className = "animrc";
    dl.innerHTML = `<dt>diffusion</dt><dd>${esc(ae.file.split("/").pop())} · ${(ae.bytes / 1024).toFixed(0)} KB · ${ae.atoms} atoms × ${ae.keys} keys</dd>
      <dt>sha256</dt><dd class="mono">${esc(ae.sha256.slice(0, 16))}… ${state.animShaOk ? '<b class="ok">matches the file served</b>' : '<b class="bad">DIFFERS</b>'}</dd>
      <dt>checked</dt><dd>${sc ? `${sc.xsd_valid ? "XSD valid" : "<b class='bad'>XSD invalid</b>"}, ${sc.semantic_errors} semantic errors · witness ${sc.witness === "pass" ? '<b class="ok">pass</b>' : '<b class="bad">' + esc(sc.witness) + "</b>"} (last key equals the source atoms; noise follows the stated schedule) · ${r.controls.negative} refusal controls` : "receipt not loaded"}</dd>`;
    $("#receipt dl").after(dl);
  }

  function showTab(k) {
    for (const t of document.querySelectorAll("#tabs button")) t.classList.toggle("on", t.dataset.k === k);
    for (const d of document.querySelectorAll("#list [data-kind]")) d.hidden = d.dataset.kind !== k;
  }
  function schemeOptions(model) {
    const o = [["file", "As written in the file"]];
    if (model.meta.plddt) o.push(["plddt", "Confidence (pLDDT bands)"], ["plddt-smooth", "Confidence (smooth)"]);
    o.push(["ss", "Secondary structure"], ["rainbow", "N to C terminus"], ["chain", "Chain"]);
    if (model.meta.bfactor) o.push(["bfactor", "B-factor"]);
    return o;
  }

  function legend(model) {
    const m = model.meta;
    if (state.scheme === "plddt" || state.scheme === "plddt-smooth" || (state.scheme === "file" && m.plddt)) {
      const cnt = [0, 0, 0, 0]; for (const v of m.plddt) cnt[v >= 90 ? 0 : v >= 70 ? 1 : v >= 50 ? 2 : 3]++;
      return BAND.map((b, i) => `<span><u style="background:${b[2]}"></u>${b[1]} (${i === 0 ? "&gt;90" : i === 3 ? "&lt;50" : b[0] + " to " + BAND[i - 1][0]}) ${cnt[i]}</span>`).join("");
    }
    if (state.scheme === "ss" || (state.scheme === "file" && !m.plddt)) return `<span><u style="background:#ed5485"></u>helix</span><span><u style="background:#f7c740"></u>strand</span><span><u style="background:#8caac7"></u>coil</span><span><u style="background:#40bfb3"></u>nucleic acid</span>`;
    if (state.scheme === "chain") return m.chains.map((c, i) => { const k = XMolBody.CHAIN[i % XMolBody.CHAIN.length]; return `<span><u style="background:rgb(${k.map((v) => Math.round(v * 255)).join(",")})"></u>chain ${esc(c)}</span>`; }).join("");
    if (state.scheme === "rainbow") return `<span class="grad"></span><span>N → C</span>`;
    return "";
  }

  function renderInfo(model, entry) {
    const m = model.meta, c = entry.citation || {};
    const cite = entry.kind === "afdb"
      ? `AlphaFold Protein Structure Database (DeepMind, EMBL-EBI), model ${esc(entry.source.file)} of ${esc((entry.source.created || "").slice(0, 10))}, CC-BY 4.0. Jumper et al., Nature 2021; Varadi et al., Nucleic Acids Res. 2024.`
      : `${c.title ? esc(c.title) + ". " : ""}${c.first_author ? esc(c.first_author[0]) + " et al., " : ""}${esc(c.journal || "")} ${esc(c.year || "")}${c.doi ? ` · <a href="https://doi.org/${esc(c.doi)}" target="_blank" rel="noopener">doi:${esc(c.doi)}</a>` : ""}. Coordinates: wwPDB, CC0.`;
    const sites = (model.sites || []).map((s) => {
      const cls = s.donors.filter((d) => d.glow).sort((a, b) => a.index - b.index).map((d) => AA3[d.res.slice(0, 3)] || "x").join("");
      return `<button class="chip" data-site="${esc(s.site)}">Zn ${esc(s.site)} · ${esc(cls)}</button>`;
    }).join("");
    $("#info").innerHTML = `<h2>${esc(model.title.replace(/ \[chains.*$/, ""))}</h2>
      <p class="meta">${m.residues.length} residues · chains ${esc(m.chains.join(", "))}${m.focus ? ` · <span title="${esc(m.focus[0])}">focus view</span>` : ""}${entry.dssp_agreement ? ` · secondary structure by DSSP (pydssp), ${(entry.dssp_agreement.fraction * 100).toFixed(0)}% residue agreement with the deposited records` : " · secondary structure by DSSP (pydssp)"}</p>
      ${sites ? `<div class="chips">${sites}</div>` : ""}<p class="cite">${cite}</p>`;
    for (const b of document.querySelectorAll("[data-site]")) b.onclick = () => state.body.focusSite(b.dataset.site);
    $("#legend").innerHTML = legend(model);
  }

  function renderReceipt(entry, shaOk, text) {
    const r = state.receipt, sc = r && r.scenes && r.scenes[entry.id], bi = state.body.info();
    const fx = Object.entries(bi.effects).filter(([, v]) => v).map(([k, v]) => k + (typeof v === "number" ? " " + v + "x" : "")).join(", ");
    $("#receipt").innerHTML = `<h4>Receipt</h4>
      <dl><dt>scene</dt><dd>${esc(entry.id)}.x3d · ${(entry.bytes / 1024).toFixed(0)} KB (${(entry.gz_bytes / 1024).toFixed(0)} KB gzip)</dd>
      <dt>sha256</dt><dd class="mono">${esc(entry.sha256.slice(0, 16))}… ${shaOk ? '<b class="ok">matches the file served</b>' : '<b class="bad">DIFFERS from the catalog</b>'}</dd>
      <dt>validator</dt><dd>${r ? esc(r.validator.tool) + " <span class='mono'>" + esc(r.validator.commit.slice(0, 12)) + "</span>" + (sc ? ` · ${sc.xsd_valid ? "XSD valid" : "<b class='bad'>XSD invalid</b>"}, ${sc.semantic_errors} semantic errors, ${sc.semantic_warnings} warnings` : "") : "receipt not loaded"}</dd>
      <dt>witness</dt><dd>${r && sc ? (sc.witness === "pass" ? '<b class="ok">pass</b>' : '<b class="bad">' + esc(sc.witness) + "</b>") + ` · ${r.controls.negative} negative controls rejected, ${r.controls.positive} positive passed` : "n/a"}</dd>
      <dt>drawn by</dt><dd>${esc(bi.backend)} · Babylon ${esc(bi.babylon)}${bi.renderer ? " · " + esc(bi.renderer) : ""}</dd>
      <dt>effects</dt><dd>${esc(fx || "none")}${bi.notes.length ? " · skipped: " + esc(bi.notes.join("; ")) : ""}</dd>
      <dt>skipped nodes</dt><dd>${esc(JSON.stringify(state.model.skipped) === "{}" ? "none" : JSON.stringify(state.model.skipped))}</dd>
      <dt>fps</dt><dd id="fps">…</dd></dl><p class="fine">No GPU timing is claimed anywhere on this page.</p>`;
  }

  /* ---------- residue card ---------- */
  function residueCard(i, pinned) {
    const m = state.model.meta, [ch, name, num] = m.residues[i].split(":");
    const v = m.plddt ? m.plddt[i] : null, bf = m.bfactor ? m.bfactor[i] : null, ss = m.ss[0][i];
    const b = v !== null ? band(v) : null;
    $("#residue").hidden = false;
    $("#residue").innerHTML = `<b>${esc(name)} ${esc(num)}</b> <span>chain ${esc(ch)}</span>${pinned ? " <em>pinned</em>" : ""}<br>` +
      (v !== null ? `pLDDT <b style="color:${b[2]}">${v.toFixed(1)}</b> · ${b[1]}` : `B-factor ${bf.toFixed(1)}`) + `<br>${SSNAME[ss]}`;
  }
  function setHover(i) {
    if (i === state.hover) return; state.hover = i;
    const map = new Map(); if (state.paeLock) for (const [k, c] of state.paeLock) map.set(k, c);
    if (state.pinned !== null) map.set(state.pinned, [1, 1, 1]);
    if (i >= 0) map.set(i, [0.8, 1, 1]);
    state.body.highlight(map);
    if (i >= 0) residueCard(i, i === state.pinned); else if (state.pinned !== null) residueCard(state.pinned, true); else $("#residue").hidden = true;
  }

  /* ---------- PAE teaser ---------- */
  function paeColor(v) { // 0 A dark green .. 30 A white (the AlphaFold DB convention: low error is dark)
    const t = Math.min(1, v / 31), stops = [[0, [0.0, 0.3, 0.2]], [0.45, [0.35, 0.75, 0.6]], [1, [0.97, 0.99, 0.98]]];
    for (let k = 1; k < stops.length; k++) if (t <= stops[k][0]) { const a = stops[k - 1], b = stops[k], u = (t - a[0]) / (b[0] - a[0]); return a[1].map((x, j) => Math.round(255 * (x + (b[1][j] - x) * u))); }
    return [247, 252, 250];
  }
  function buildPAE(model) {
    const m = model.meta, box = $("#pae");
    $("#paeBtn").hidden = !m.pae_half_angstrom;
    if (!m.pae_half_angstrom) { box.hidden = true; return; }
    box.hidden = false;
    const N = m.residues.length, q = m.pae_half_angstrom, M = 8, W = N + M;
    const cv = $("#paeCanvas"); cv.width = W; cv.height = W;
    const g = cv.getContext("2d"), img = g.createImageData(W, W);
    for (let p = 0; p < W * W; p++) { img.data[p * 4 + 3] = 255; img.data[p * 4] = img.data[p * 4 + 1] = img.data[p * 4 + 2] = 10; }
    for (let i = 0; i < N; i++) for (let j = 0; j < N; j++) { const c = paeColor(q[i * N + j] * 0.5), o = ((i + M) * W + (j + M)) * 4; img.data[o] = c[0]; img.data[o + 1] = c[1]; img.data[o + 2] = c[2]; }
    const hex = (h) => [parseInt(h.slice(1, 3), 16), parseInt(h.slice(3, 5), 16), parseInt(h.slice(5, 7), 16)];
    for (let i = 0; i < N; i++) { const c = hex(band(m.plddt[i])[2]); for (let k = 0; k < M - 3; k++) { let o = ((i + M) * W + k) * 4; img.data.set([c[0], c[1], c[2]], o); o = (k * W + i + M) * 4; img.data.set([c[0], c[1], c[2]], o); } }
    g.putImageData(img, 0, 0);
    state.pae = { N, M, W };
    cv.onpointermove = (e) => paeAt(e, false);
    cv.onpointerleave = () => { if (!state.paeLocked) paeClear(); };
    cv.onclick = (e) => { state.paeLocked = !state.paeLocked; if (state.paeLocked) paeAt(e, true); else paeClear(); };
  }
  function paeAt(e, force) {
    if (state.paeLocked && !force) return;
    const { N, M, W } = state.pae, r = e.currentTarget.getBoundingClientRect();
    const j = Math.floor(((e.clientX - r.left) / r.width) * W) - M, i = Math.floor(((e.clientY - r.top) / r.height) * W) - M;
    if (i < 0 || j < 0 || i >= N || j >= N) return;
    const v = state.model.meta.pae_half_angstrom[i * N + j] * 0.5, ca = state.model.meta.ca, lab = (k) => state.model.meta.residues[k].split(":").slice(1).join(" ");
    $("#paeRead").innerHTML = `row <b>${lab(i)}</b> · column <b>${lab(j)}</b><br>PAE <b>${v.toFixed(1)} Å</b> (half-Å steps; entry [${i + 1}][${j + 1}] of the file, not symmetric)`;
    state.paeLock = new Map([[i, [0.2, 0.9, 1]], [j, [1, 0.35, 0.85]]]);
    state.hover = -2; setHover(-1);
    state.body.arc([ca[i * 3], ca[i * 3 + 1], ca[i * 3 + 2]], [ca[j * 3], ca[j * 3 + 1], ca[j * 3 + 2]], v < 5 ? [0.3, 1, 0.7] : v < 15 ? [1, 0.85, 0.3] : [1, 0.4, 0.3]);
  }
  function paeClear() { state.paeLock = null; state.body.arc(null); state.hover = -2; setHover(-1); $("#paeRead").textContent = "Hover the map: each cell is the model's own error estimate for one pair of residues."; }

  /* ---------- labels for the zinc bonds ---------- */
  function buildLabels(model) {
    const host = $("#labels"); host.innerHTML = "";
    state.labelEls = model.labels.map((l) => { const d = document.createElement("div"); d.className = "lbl"; d.textContent = l.text; host.appendChild(d); return { el: d, pos: l.pos }; });
  }
  function placeLabels() {
    const on = state.body.layers.sites !== false && !(state.player && state.player.info && state.player.info.hold < 0.6);
    for (const l of state.labelEls || []) {
      const p = state.body.project(l.pos);
      const dist = state.body.camera.position.subtract(new BABYLON.Vector3(...l.pos)).length();
      l.el.style.display = on && p.visible && dist < 90 ? "block" : "none";
      l.el.style.transform = `translate(${p.x}px,${p.y}px) translate(-50%,-50%)`;
      l.el.style.opacity = String(Math.max(0.25, Math.min(1, 1.3 - dist / 90)));
    }
  }

  /* ---------- loading ---------- */
  async function load(id, forAnim) {
    if (!forAnim) stopAnim();
    const entry = state.catalog.scenes.find((s) => s.id === id) || state.catalog.scenes[0];
    $("#busy").hidden = false; $("#busy").textContent = "Reading " + entry.id + "…";
    for (const b of document.querySelectorAll(".item")) b.classList.toggle("on", b.dataset.id === entry.id);
    showTab(entry.kind);
    const text = await fetchScene(entry);
    const shaOk = (await sha256(text)) === entry.sha256;
    const model = XMolReader.parseX3D(text);
    state.entry = entry; state.model = model; state.pinned = null; state.paeLock = null; state.paeLocked = false; state.hover = -1;
    state.body.setModel(model);
    state.scheme = "file";
    $("#scheme").innerHTML = schemeOptions(model).map(([v, l]) => `<option value="${v}">${esc(l)}</option>`).join("");
    const want = hp.get("scheme"); if (want && [...$("#scheme").options].some((o) => o.value === want)) { $("#scheme").value = want; state.scheme = want; state.body.setScheme(want); }
    $("#core").hidden = !model.meta.plddt;
    renderInfo(model, entry); renderReceipt(entry, shaOk); buildPAE(model); buildLabels(model);
    $("#residue").hidden = true; paeClear && state.pae && paeClear();
    $("#busy").hidden = true;
    if (!forAnim && !window.__xmolNoHash) history.replaceState(null, "", "#scene=" + entry.id + (state.scheme !== "file" ? "&scheme=" + state.scheme : ""));
    window.__xmolReady = { id: entry.id, meshes: state.body.meshes.length, backend: state.body.backend };
  }

  async function boot() {
    try {
      const [cat, rec, cred, cine, gate, anim, film] = await Promise.all([getJSON("scenes/catalog.json"), getJSON("scenes/receipt.json").catch(() => null), getJSON("scenes/credits.json").catch(() => null),
        getJSON("cinema/receipt.json").catch(() => null), getJSON("cinema/gate.json").catch(() => null), getJSON("scenes/anim/anim.json").catch(() => null), getJSON("cinema/diffusion.json").catch(() => null)]);
      Object.assign(state, { catalog: cat, receipt: rec, credits: cred, cine, gate, animIndex: anim, film });
      buildCatalogue();
      const q = hp.get("q") || (matchMedia("(max-width:700px)").matches ? "low" : "high");
      state.body = await XMolBody.create($("#stage"), { quality: q, webgpu: hp.get("gpu") !== "0" });
      $("#backend").textContent = state.body.backend === "webgpu" ? "WebGPU" : "WebGL2";
      if (state.body.backend !== "webgpu") $("#gpuhint").hidden = false;
      $("#scheme").onchange = (e) => { state.scheme = e.target.value; state.body.setScheme(state.scheme); renderInfo(state.model, state.entry); };
      for (const k of ["sites", "sticks", "nucleic"]) $("#l_" + k).onchange = (e) => state.body.setLayer(k, e.target.checked);
      $("#cinema").onclick = () => { const on = !state.body.cinema; state.body.setCinema(on); $("#cinema").classList.toggle("on", on); document.body.classList.toggle("cinema", on); };
      $("#shot").onclick = async () => { const b = await state.body.screenshot(); const a = document.createElement("a"); a.href = URL.createObjectURL(b); a.download = `x3d-mol-${state.entry.id}.png`; a.click(); };
      $("#reset").onclick = () => state.body.frame(false);
      $("#core").onclick = () => state.body.focusCore(70);
      $("#hide").onclick = () => document.body.classList.toggle("nui");
      $("#about").onclick = () => { $("#aboutBox").hidden = false; };
      $("#dPlay").onclick = () => { const p = state.player; if (!p) return; p.play(!p.playing); $("#dPlay").textContent = p.playing ? "Pause" : "Play"; };
      $("#dExit").onclick = () => { const id = state.animEntry && state.animEntry.id; stopAnim(); if (id) load(id); };
      $("#dFollow").onclick = () => { state.follow = !state.follow; $("#dFollow").classList.toggle("on", state.follow); };
      const scrub = $("#dScrub");
      scrub.addEventListener("pointerdown", () => { state.scrubbing = true; });
      scrub.addEventListener("input", () => { const p = state.player; if (!p) return; if (p.playing) { p.play(false); $("#dPlay").textContent = "Play"; } p.seek(+scrub.value / 1000); });
      scrub.addEventListener("change", () => { state.scrubbing = false; });
      $("#aboutClose").onclick = () => { $("#aboutBox").hidden = true; };
      document.addEventListener("keydown", (e) => { if (e.target.tagName === "SELECT") return; if (e.key === "h") $("#hide").click(); if (e.key === "c") $("#cinema").click(); if (e.key === " " && state.player && e.target.tagName !== "BUTTON" && e.target.tagName !== "INPUT") { e.preventDefault(); $("#dPlay").click(); } if (e.key === "Escape") { $("#cineBox").hidden = true; state.pinned = null; paeClear && state.pae && (state.paeLocked = false, paeClear()); setHover(-1); } });
      const cv = $("#stage");
      let down = null;
      cv.addEventListener("pointerdown", (e) => { down = [e.clientX, e.clientY]; if (state.player && state.follow) { state.follow = false; $("#dFollow").classList.remove("on"); } });
      cv.addEventListener("pointerup", (e) => {
        if (!down || Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 4) return; down = null;
        const r = cv.getBoundingClientRect(), p = state.body.pick(e.clientX - r.left, e.clientY - r.top);
        state.pinned = p ? p.resid : null; state.hover = -2; setHover(p ? p.resid : -1);
      });
      let pending = false;
      cv.addEventListener("pointerleave", () => { if (!state.paeLocked) setHover(-1); });
      cv.addEventListener("pointermove", (e) => {
        if (e.buttons || pending) return; pending = true;
        const x = e.clientX, y = e.clientY;
        requestAnimationFrame(() => { pending = false; const r = cv.getBoundingClientRect(), p = state.body.pick(x - r.left, y - r.top); cv.style.cursor = p ? "pointer" : "grab"; setHover(p ? p.resid : -1); });
      });
      state.body.scene.onAfterRenderObservable.add(() => { placeLabels(); const f = $("#fps"); if (f && (state.tick = (state.tick || 0) + 1) % 30 === 0) f.textContent = state.body.engine.getFps().toFixed(0) + " fps (this machine, this frame size; not a benchmark)"; });
      renderAbout(); window.__xmolState = state;
      if (hp.get("anim") && state.animIndex) await openAnim(hp.get("anim"));
      else await load(hp.get("scene") || "1aay");
      if (hp.get("cinema") === "1") $("#cinema").click();
      if (hp.get("ui") === "0") document.body.classList.add("nui");
    } catch (e) {
      console.error(e); $("#busy").hidden = false; $("#busy").textContent = "Could not start: " + e.message; window.__xmolError = String(e.stack || e);
    }
  }

  function renderAbout() {
    const c = state.credits;
    const papers = c ? c.papers.map((p) => `<li>${esc(p.authors)} <i>${esc(p.title)}</i>. ${p.journal ? esc(p.journal) + " " : ""}${esc(p.year || "")}${p.doi ? ` · <a href="https://doi.org/${esc(p.doi)}" target="_blank" rel="noopener">doi:${esc(p.doi)}</a>` : ""}</li>`).join("") : "";
    $("#aboutBody").innerHTML = `<h2>About x3d.mol</h2>
      <p>Public protein structures, written as X3D 4.0, checked by a validator and a second reader, and drawn by Babylon.js. Every number in the Receipt card names the instrument behind it.</p>
      <h3>Credit</h3>
      <p>The zinc finger work follows the published research of Sarah Lucie Jane Michel's laboratory at the University of Maryland School of Pharmacy on zinc finger proteins (tristetraprolin, ZRANB2, YY1, PARP1, CPSF30). The structures drawn here were determined by other groups and are cited on each entry. <b>This project is independent: the laboratory did not review or endorse it.</b></p>
      ${papers ? `<details><summary>${c.papers.length} published papers by the laboratory on these proteins</summary><ul class="papers">${papers}</ul><p class="fine">Bibliographic data: ${esc(c.source)}, retrieved ${esc(c.retrieved)}.</p></details>` : ""}
      <h3>Data and licences</h3>
      <ul><li>Zinc finger entries: wwPDB archive snapshot of 1 January 2026, CC0 1.0.</li>
      <li>Predicted models: AlphaFold Protein Structure Database (DeepMind and EMBL-EBI), CC-BY 4.0. Jumper et al., Nature 596, 583 (2021); Varadi et al., Nucleic Acids Res. 52, D368 (2024).</li>
      <li>Secondary structure: DSSP rules as implemented in pydssp. Parsing: gemmi. Rendering: Babylon.js 9.32.0 (Apache-2.0).</li></ul>
      <h3>Reading the picture</h3>
      <ul><li>Colour on the AlphaFold models is the database's pLDDT palette. Low confidence is common in flexible stretches and is not an error in the drawing.</li>
      <li>Bonds to zinc glow only while they measure under 2.5 Å; each label is the length measured from the deposited coordinates.</li>
      <li>Materials, lights, bloom, depth of field and the studio environment are look, not data.</li></ul>
      <p class="fine">Where WebGPU is blocked (some Windows Chrome builds list the Intel UHD 620 as unsupported), enable <span class="mono">chrome://flags/#enable-unsafe-webgpu</span>; the page falls back to WebGL2 on its own.</p>`;
  }
  boot();
})();
