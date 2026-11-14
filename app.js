/* SkyBlink explorer - vanilla JS, no build step.
   Data contract: cache/<slug>/manifest.json with frames[] rendered from
   REAL SPHEREx archive cutouts by scripts/pipeline.py. */
"use strict";

const TARGETS = [
  { slug: "barnards-star", name: "Barnard's Star", ra: 269.4464, dec: 4.7671, fov: 5,
    kind: "Proper motion · 10.4″/yr",
    blurb: "The fastest-moving star in the sky.",
    look: "The fastest-moving star in the sky. Blink: it creeps. Difference mode: a blue–orange dipole. Its measured shift is compared with Gaia's prediction in the case file. The dark block at its centre in some frames is its saturated core — the star is too bright for the detector there, so the position is measured from the unsaturated wings." },
  { slug: "wise-0855", name: "WISE 0855", ra: 133.7951, dec: -7.2451, fov: 3,
    kind: "Proper motion · 8.1″/yr",
    blurb: "The coldest known brown dwarf (~250 K).",
    look: "Essentially invisible below 3 µm, faint at 4–5 µm — only the long-wavelength detectors see it. If the spectrum is noise, we show honest upper limits, not a fake detection." },
  { slug: "epsilon-indi-b", name: "Epsilon Indi B", ra: 331.0438, dec: -56.7828, fov: 5,
    kind: "Proper motion · 4.7″/yr",
    blurb: "A pair of brown dwarfs orbiting a nearby star.",
    look: "A binary brown dwarf (Ba+Bb) orbiting Epsilon Indi A, ~24 arcmin away. Centred on B. It moves with the system; difference mode reveals it." },
  { slug: "rw-aurigae", name: "RW Aurigae", ra: 76.9565, dec: 30.4014, fov: 5,
    kind: "Variable star",
    blurb: "A young star with deep dust-dimming events.",
    look: "A young T-Tauri star with deep dust-dimming events: the blink pulses instead of shifting. Flux per epoch tells the story." },
  { slug: "r-draconis", name: "R Draconis", ra: 248.1675, dec: 66.7550, fov: 5,
    kind: "Variable · Mira, ~246 d",
    blurb: "A pulsating Mira variable near the north ecliptic pole.",
    look: "A Mira variable near the north ecliptic pole — the most-visited target in this list, so it has the most epochs. Watch for saturation flags at maximum light." },
];

const API = window.SKYBLINK_API || null; // live backend base URL when deployed
const $ = (s) => document.querySelector(s);

const state = {
  target: TARGETS[0], manifest: null, idx: 0, playing: false,
  timer: null, mode: "blink", imgCache: new Map(), gaiaOn: false, bandOnly: false,
};
const HAS_EXPLORER = !!document.querySelector("#frame-a");

/* ---------- target cards ---------- */
function buildCards() {
  const grid = $("#target-grid");
  TARGETS.forEach((t) => {
    const b = document.createElement("button");
    b.className = "target-card" + (t.slug === state.target.slug ? " active" : "");
    b.dataset.slug = t.slug;
    b.innerHTML = `<div class="kind">${t.kind}</div><h3>${t.name}</h3>
      <p>${t.blurb}</p><div class="tstatus mono" data-status>checking cache…</div>`;
    b.addEventListener("click", () => {
      if (HAS_EXPLORER) loadTarget(t.slug, true);
      else location.href = `target.html?t=${t.slug}`;
    });
    grid.appendChild(b);
    const st = b.querySelector("[data-status]");
    if ((window.SKYBLINK_CACHE || {})[t.slug]) { st.textContent = "frames ready"; }
    else {
      fetch(`cache/${t.slug}/manifest.json`).then((r) => {
        st.textContent = r.ok ? "frames ready" : "being prepared";
      }).catch(() => { st.textContent = "being prepared"; });
    }
  });
}

/* ---------- loading ---------- */
async function loadTarget(slug, scroll) {
  const t = TARGETS.find((x) => x.slug === slug);
  if (!t) return;
  stopPlay();
  state.target = t; state.idx = 0; state.imgCache.clear();
  state.bandOnly = false;
  const bb0 = $("#btn-band");
  if (bb0) bb0.classList.remove("on");
  document.querySelectorAll(".target-card").forEach((c) =>
    c.classList.toggle("active", c.dataset.slug === slug));
  $("#viewer-title").textContent = t.name;
  $("#viewer-sub").textContent =
    `RA ${t.ra.toFixed(4)}° · Dec ${t.dec >= 0 ? "+" : ""}${t.dec.toFixed(4)}° · FoV ${t.fov}′`;
  $("#look-for").textContent = t.look;
  $("#legend").textContent = "Loading frames…";
  try {
    const bundled = (window.SKYBLINK_CACHE || {})[slug];
    if (bundled) { state.manifest = bundled.manifest; }
    else {
      const r = await fetch(`cache/${slug}/manifest.json`);
      if (!r.ok) throw new Error("not cached");
      state.manifest = await r.json();
    }
  } catch (e) {
    state.manifest = null;
    $("#legend").textContent = "Frames for this target are still being prepared from the archive. Try Barnard's Star meanwhile.";
    $("#frame-info").innerHTML = "";
    $("#timeline").innerHTML = "";
    return;
  }
  setupBandButton();
  buildTimeline();
  showFrame(0);
  renderBandChart();
  renderSpectrum();
  fillDetail();
  try {
    const u = new URL(location.href);
    u.searchParams.set("t", slug);
    history.replaceState(null, "", u);
  } catch (e) {}
  if (scroll) $("#explorer").scrollIntoView({ behavior: "smooth" });
}

/* Same-band mode: SPHEREx detectors are different wavelength bands, so a
   cross-detector blink mixes colour change with motion. When bandOnly is on,
   stepping/play cycles only the frames from the most-observed detector. */
function allowedFrames() {
  const frames = state.manifest.frames;
  if (!state.bandOnly) return frames.map((_, i) => i);
  const counts = {};
  frames.forEach((f) => { counts[f.detector] = (counts[f.detector] || 0) + 1; });
  const det = Number(Object.keys(counts).sort((a, b) => counts[b] - counts[a])[0]);
  return frames.map((f, i) => (f.detector === det ? i : -1)).filter((i) => i >= 0);
}
function stepFrame(dir) {
  if (!state.manifest) return;
  const allowed = allowedFrames();
  if (!allowed.length) return;
  let pos = allowed.indexOf(state.idx);
  if (pos < 0) pos = dir > 0 ? -1 : 0;
  showFrame(allowed[(pos + dir + allowed.length) % allowed.length]);
}
function baseFrame() {
  const a = allowedFrames();
  return state.manifest.frames[a.length ? a[0] : 0];
}
function setupBandButton() {
  const b = $("#btn-band");
  if (!b || !state.manifest) return;
  const counts = {};
  state.manifest.frames.forEach((f) => { counts[f.detector] = (counts[f.detector] || 0) + 1; });
  const best = Math.max(...Object.values(counts));
  if (best < 2) {
    b.disabled = true;
    b.title = "Every epoch of this target comes from a different detector (a different wavelength band) — there is no same-band pair to isolate.";
  } else {
    b.disabled = false;
    b.title = "Blink only the frames taken with the same detector — the same wavelength band — so colour differences cannot imitate motion";
  }
}

function buildTimeline() {
  const tl = $("#timeline");
  tl.innerHTML = "";
  const allowed = state.manifest ? allowedFrames() : [];
  state.manifest.frames.forEach((f, i) => {
    const wrap = document.createElement("div");
    wrap.className = "tick-wrap" + (i === state.idx ? " on" : "") +
      (state.bandOnly && !allowed.includes(i) ? " off" : "");
    const tick = document.createElement("button");
    tick.className = "tick" + (i === state.idx ? " on" : "");
    tick.title = `${f.release} · ${f.date}`;
    tick.addEventListener("click", () => {
      if (state.bandOnly && !allowedFrames().includes(i)) return;
      stopPlay(); showFrame(i);
    });
    const lab = document.createElement("span");
    lab.className = "tick-date";
    lab.textContent = f.date.slice(0, 7);
    wrap.appendChild(tick);
    wrap.appendChild(lab);
    tl.appendChild(wrap);
  });
}

/* ---------- display ---------- */
function frameURL(f) {
  const bundled = (window.SKYBLINK_CACHE || {})[state.target.slug];
  if (bundled && bundled.frames[f.png]) return bundled.frames[f.png];
  return `cache/${state.target.slug}/${f.png}`;
}

function loadImg(url) {
  if (!state.imgCache.has(url)) {
    state.imgCache.set(url, new Promise((res, rej) => {
      const im = new Image();
      im.onload = () => res(im); im.onerror = rej; im.src = url;
    }));
  }
  return state.imgCache.get(url);
}

async function showFrame(i) {
  const frames = state.manifest.frames;
  state.idx = (i + frames.length) % frames.length;
  const f = frames[state.idx];
  document.querySelectorAll(".tick").forEach((el, j) =>
    el.classList.toggle("on", j === state.idx));
  document.querySelectorAll(".tick-wrap").forEach((el, j) =>
    el.classList.toggle("on", j === state.idx));
  $("#legend").innerHTML =
    `Frame ${String.fromCharCode(65 + state.idx)} · <span class="rel rel-${f.release}">${f.release}</span>` +
    ` · ${f.date}<span class="det det-${f.detector}"></span>detector ${f.detector} · obs ${f.obs_id}`;
  $("#frame-info").innerHTML = `
    <div><dt>Release</dt><dd>${f.release}</dd></div>
    <div><dt>Observed</dt><dd>${f.date}</dd></div>
    <div><dt>Detector</dt><dd>D${f.detector}</dd></div>
    ${f.wave_um ? `<div><dt>Band</dt><dd>${f.wave_um[0]}–${f.wave_um[1]} µm</dd></div>` : ""}
    <div><dt>Observation</dt><dd>${f.obs_id}</dd></div>
    ${f.clean_pct != null ? `<div><dt>Clean pixels</dt><dd>${f.clean_pct}%</dd></div>` : ""}
    <div><dt>Frames in set</dt><dd>${frames.length} epochs</dd></div>
    <div><dt>Stretch</dt><dd>asinh · shared</dd></div>`;
  drawGaia();
  if (state.mode === "blink") {
    const a = $("#frame-a");
    a.src = frameURL(f);
    a.classList.remove("hidden"); $("#frame-b").classList.add("hidden");
    $("#diff-canvas").classList.add("hidden"); $("#side-pair").classList.add("hidden");
    $("#frame-wrap").classList.remove("hidden");
  } else if (state.mode === "side") {
    const f0 = baseFrame();
    $("#side-a").src = frameURL(f0); $("#side-b").src = frameURL(f);
    $("#side-a-cap").textContent = `${f0.release} · ${f0.date} · D${f0.detector}`;
    $("#side-b-cap").textContent = `${f.release} · ${f.date} · D${f.detector}`;
    $("#frame-wrap").classList.add("hidden");
    $("#side-pair").classList.remove("hidden");
  } else if (state.mode === "diff") {
    $("#frame-wrap").classList.remove("hidden");
    $("#frame-a").classList.add("hidden"); $("#frame-b").classList.add("hidden");
    $("#side-pair").classList.add("hidden");
    await renderDiff(baseFrame(), f);
  }
}

async function renderDiff(fa, fb) {
  const cv = $("#diff-canvas");
  try {
    const [ia, ib] = await Promise.all([loadImg(frameURL(fa)), loadImg(frameURL(fb))]);
    const w = ia.naturalWidth, h = ia.naturalHeight;
    cv.width = w; cv.height = h;
    const mk = (im) => {
      const c = document.createElement("canvas"); c.width = w; c.height = h;
      const x = c.getContext("2d"); x.drawImage(im, 0, 0);
      return x.getImageData(0, 0, w, h).data;
    };
    const da = mk(ia), db = mk(ib);
    const ctx = cv.getContext("2d");
    const out = ctx.createImageData(w, h);
    // Diverging, colour-blind-safe map: gain = orange, loss = blue, on near-black.
    for (let p = 0; p < da.length; p += 4) {
      let v = (db[p] - da[p]) * 1.6 / 127.5;
      v = Math.max(-1, Math.min(1, v));
      if (v >= 0) { out.data[p] = 255 * v; out.data[p + 1] = 138 * v; out.data[p + 2] = 30 * v; }
      else { const a = -v; out.data[p] = 45 * a; out.data[p + 1] = 115 * a; out.data[p + 2] = 255 * a; }
      out.data[p + 3] = 255;
    }
    ctx.putImageData(out, 0, 0);
    cv.classList.remove("hidden");
  } catch (e) { /* frames not decodable yet */ }
}

/* ---------- Gaia overlay (ESA Gaia DR3, epoch 2016.0, PM-propagated) ---------- */
function drawGaia() {
  const cv = $("#gaia-canvas");
  if (!cv) return;
  const ctx = cv.getContext("2d");
  const wrap = $("#frame-wrap");
  const W = wrap.clientWidth || 520;
  cv.width = W; cv.height = W;
  ctx.clearRect(0, 0, W, W);
  if (!state.gaiaOn || !state.manifest || !state.manifest.gaia ||
      state.mode !== "blink") { cv.classList.add("hidden"); return; }
  const f = state.manifest.frames[state.idx];
  const yearFrac = Number(f.date.slice(0, 4)) + (Number(f.date.slice(5, 7)) - 0.5) / 12;
  const dt = yearFrac - 2016.0;
  const ra0 = state.manifest.ra, dec0 = state.manifest.dec;
  const fovDeg = state.manifest.fov_arcmin / 60;
  const cosD = Math.cos(dec0 * Math.PI / 180);
  ctx.strokeStyle = "rgba(45,212,191,0.9)";
  ctx.lineWidth = 1.4;
  state.manifest.gaia.forEach((s) => {
    const raP = s.ra + (s.pmra / 3.6e6) * dt / cosD;
    const decP = s.dec + (s.pmdec / 3.6e6) * dt;
    const fx = 0.5 - ((raP - ra0) * cosD) / fovDeg;
    const fy = 0.5 - (decP - dec0) / fovDeg;
    if (fx < 0 || fx > 1 || fy < 0 || fy > 1) return;
    const r = Math.max(2.5, Math.min(9, 10 - (s.g - 10) * 0.75));
    ctx.beginPath();
    ctx.arc(fx * W, fy * W, r, 0, Math.PI * 2);
    ctx.stroke();
  });
  cv.classList.remove("hidden");
}

/* ---------- band chart (target detail page) ---------- */
function renderBandChart() {
  const el = $("#band-chart");
  if (!el || !state.manifest) return;
  const fr = state.manifest.frames.filter((f) => f.band_flux != null);
  if (!fr.length) { el.innerHTML = ""; return; }
  const max = Math.max(...fr.map((f) => Math.abs(f.band_flux))) || 1;
  const bw = 58, gap = 34, H = 168, base = H - 50;
  const width = fr.length * (bw + gap) + gap;
  const bars = fr.map((f, i) => {
    const h = Math.max(3, (Math.abs(f.band_flux) / max) * (base - 18));
    const x = gap + i * (bw + gap), y = base - h;
    return `<g>
      <rect x="${x}" y="${y}" width="${bw}" height="${h}" rx="5" fill="var(--d${f.detector})"></rect>
      <text x="${x + bw / 2}" y="${base + 16}" text-anchor="middle" class="bc-x">D${f.detector}</text>
      <text x="${x + bw / 2}" y="${base + 31}" text-anchor="middle" class="bc-x2">${f.wave_um ? f.wave_um[0] + "–" + f.wave_um[1] + " µm" : ""}</text>
      <text x="${x + bw / 2}" y="${base + 45}" text-anchor="middle" class="bc-x2">${f.date}</text>
    </g>`;
  }).join("");
  el.innerHTML = `<svg viewBox="0 0 ${width} ${H}" role="img" aria-label="Aperture flux per detector band">${bars}</svg>
    <p class="fineprint">Aperture flux at the target position in each frame, normalised to the
    brightest. Each bar is a different detector band <i>and</i> a different visit — SPHEREx
    surveys a field with different detectors at different times — so read this as the
    target's band-by-band presence, not a calibrated spectrum.</p>`;
}

/* ---------- target detail fill (target.html) ---------- */
function renderSpectrum() {
  const sec = $("#spectrum-section"), el = $("#spectrum-chart"), note = $("#spectrum-note");
  if (!sec || !el) return;
  const sp = state.manifest && state.manifest.spectrum;
  if (!sp || !sp.wave_um || !sp.wave_um.length) { sec.hidden = true; return; }
  sec.hidden = false;
  if (note) note.innerHTML = `Measured from the <b>${sp.source}</b> — aperture photometry at this
    target's position in every spectral plane of the cube. ${sp.note || ""}`;
  const W = 860, H = 240, padL = 46, padB = 30, padT = 12;
  const xs = sp.wave_um, ys = sp.flux_mjy;
  const x0 = Math.min(...xs), x1 = Math.max(...xs);
  const y1 = Math.max(...ys) * 1.1, y0 = Math.min(0, Math.min(...ys));
  const X = (v) => padL + (Math.log(v) - Math.log(x0)) / (Math.log(x1) - Math.log(x0)) * (W - padL - 12);
  const Y = (v) => padT + (y1 - v) / (y1 - y0) * (H - padT - padB);
  const pts = xs.map((v, i) => `${X(v).toFixed(1)},${Y(ys[i]).toFixed(1)}`).join(" ");
  const ticks = [0.8, 1, 1.5, 2, 3, 4, 5].filter(t => t >= x0 && t <= x1)
    .map(t => `<text x="${X(t)}" y="${H - 8}" text-anchor="middle" class="bc-x2">${t} µm</text>`).join("");
  el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Spectrum chart">
    <line x1="${padL}" y1="${Y(0)}" x2="${W - 12}" y2="${Y(0)}" stroke="var(--line)"/>
    <polyline points="${pts}" fill="none" stroke="var(--teal)" stroke-width="1.6"/>
    ${xs.map((v, i) => `<circle cx="${X(v)}" cy="${Y(ys[i])}" r="2.1" fill="var(--amber)"/>`).join("")}
    <text x="6" y="${Y(y1) + 4}" class="bc-x2">mJy</text>${ticks}</svg>`;
}

function fillDetail() {
  const story = $("#target-story");
  if (!story || !state.manifest) return;
  const t = state.target, fr = state.manifest.frames;
  const dets = [...new Set(fr.map((f) => "D" + f.detector))].join(", ");
  const rels = [...new Set(fr.map((f) => f.release))].join(" + ");
  story.innerHTML = `
    <p>${t.look}</p>
    <dl class="mono fact-grid">
      <div><dt>Coordinates</dt><dd>RA ${t.ra.toFixed(4)}° · Dec ${t.dec >= 0 ? "+" : ""}${t.dec.toFixed(4)}°</dd></div>
      <div><dt>Field of view</dt><dd>${t.fov} arcmin</dd></div>
      <div><dt>Epochs</dt><dd>${fr.length} (${fr[0].date} → ${fr[fr.length - 1].date})</dd></div>
      <div><dt>Releases</dt><dd>${rels}</dd></div>
      <div><dt>Detectors</dt><dd>${dets}</dd></div>
      <div><dt>Gaia stars in field</dt><dd>${(state.manifest.gaia || []).length}</dd></div>
    </dl>`;
  document.title = `${t.name} — SkyBlink`;
}

/* ---------- transport ---------- */
function stopPlay() {
  state.playing = false;
  if (state.timer) { clearInterval(state.timer); state.timer = null; }
  $("#btn-play").textContent = "▶";
}
function togglePlay() {
  if (!state.manifest) return;
  if (state.playing) { stopPlay(); return; }
  state.playing = true;
  $("#btn-play").textContent = "⏸";
  const step = () => stepFrame(1);
  const restart = () => {
    if (state.timer) clearInterval(state.timer);
    state.timer = setInterval(step, 1000 / Number($("#fps").value));
  };
  restart();
  $("#fps").oninput = restart;
}

/* ---------- search ---------- */
/* ---------- helpers + keyboard shortcuts ---------- */
function frameCount() { return state.manifest ? state.manifest.frames.length : 0; }
function setMode(m) {
  const b = document.querySelector(`.mode-tabs button[data-mode="${m}"]`);
  if (b) b.click();
}
document.addEventListener("keydown", (e) => {
  if (!HAS_EXPLORER) return;
  const tag = (e.target.tagName || "").toLowerCase();
  if (tag === "input" || tag === "textarea") return;
  if (e.code === "Space") { e.preventDefault(); togglePlay(); }
  else if (e.key === "ArrowRight") { stopPlay(); stepFrame(1); }
  else if (e.key === "ArrowLeft") { stopPlay(); stepFrame(-1); }
  else if (e.key === "g" || e.key === "G") { const b = $("#btn-gaia"); if (b) b.click(); }
  else if (e.key === "1") setMode("blink");
  else if (e.key === "2") setMode("side");
  else if (e.key === "3") setMode("diff");
});

/* ---------- guided tour (home page) ---------- */
const TOUR = [
  { at: 0, cap: "This is Barnard's Star — the fastest-moving star in the sky. The bright star near the centre is our suspect.",
    run() { loadTarget("barnards-star", true); } },
  { at: 2600, cap: "Five real SPHEREx visits — Aug 2025 to Aug 2026. Blink them, the way astronomers have hunted movers for a century:",
    run() { if (!state.playing) togglePlay(); } },
  { at: 11000, cap: "See it creep? Every other star stands still. In Difference view, motion turns into a blue–orange dipole:",
    run() { setMode("diff"); } },
  { at: 18500, cap: "Now check it against ESA Gaia DR3 — every known star, proper-motion propagated to this exact date. Rings sit on stars; nothing sits where the suspect is going.",
    run() { setMode("blink"); state.gaiaOn = true; const b = $("#btn-gaia"); if (b) b.classList.add("on"); drawGaia(); } },
  { at: 26500, cap: "We measured the shift in all five epochs — it matches Gaia's prediction to about a pixel. The full evidence is in Case Files. The sky is yours now.",
    run() {} },
];
let tourTimers = [];
function endTour() {
  tourTimers.forEach(clearTimeout); tourTimers = [];
  const bar = $("#tour-bar"); if (bar) bar.hidden = true;
}
function startTour() {
  const bar = $("#tour-bar"), cap = $("#tour-cap");
  if (!bar || !cap) return;
  endTour(); bar.hidden = false;
  TOUR.forEach(s => tourTimers.push(setTimeout(() => { cap.textContent = s.cap; s.run(); }, s.at)));
  tourTimers.push(setTimeout(endTour, 35000));
}

function handleSearch(qRaw) {
  const q = qRaw.trim().toLowerCase();
  if (!q) return;
  const hit = TARGETS.find((t) => t.name.toLowerCase().includes(q) || q.includes(t.name.toLowerCase().split(" ")[0]));
  if (hit) { loadTarget(hit.slug, true); return; }
  const m = q.match(/(-?\d+\.?\d*)[,\s]+(-?\d+\.?\d*)/);
  if (m) {
    const ra = parseFloat(m[1]), dec = parseFloat(m[2]);
    if (API) {
      $("#legend").textContent = `Live query for RA ${ra}, Dec ${dec} sent to the SkyBlink backend…`;
      fetch(`${API}/api/frames?ra=${ra}&dec=${dec}&fov=5`).then((r) => r.json())
        .then((man) => {
          if (man && man.ok) {
            state.target = { slug: null, name: `${ra.toFixed(4)}°, ${dec >= 0 ? "+" : ""}${dec.toFixed(4)}°`, ra, dec, fov: 5, look: "Custom coordinates." };
            state.manifest = man; buildTimeline(); showFrame(0);
          } else { $("#legend").textContent = "No SPHEREx frames found for those coordinates yet."; }
        }).catch(() => { $("#legend").textContent = "Live backend unreachable — the five targets below are pre-loaded."; });
    } else {
      $("#legend").textContent = "Live coordinate search runs on the SkyBlink backend, which is offline in this static preview. The five official targets below are fully loaded.";
      $("#targets").scrollIntoView({ behavior: "smooth" });
    }
    return;
  }
  $("#legend").textContent = `“${qRaw.trim()}” isn't one of the five pre-loaded targets. Try a target name, or coordinates like 269.4521, 4.6934.`;
}

/* ---------- wire up ---------- */
if (HAS_EXPLORER) {
  document.querySelectorAll(".mode-tabs button").forEach((b) => {
    b.addEventListener("click", () => {
      document.querySelectorAll(".mode-tabs button").forEach((x) => x.classList.remove("active"));
      b.classList.add("active");
      state.mode = b.dataset.mode;
      if (state.manifest) showFrame(state.idx);
    });
  });
  $("#btn-play").addEventListener("click", togglePlay);
  $("#btn-prev").addEventListener("click", () => { stopPlay(); stepFrame(-1); });
  $("#btn-next").addEventListener("click", () => { stopPlay(); stepFrame(1); });
  const gaiaBtn = $("#btn-gaia");
  if (gaiaBtn) gaiaBtn.addEventListener("click", () => {
    state.gaiaOn = !state.gaiaOn;
    gaiaBtn.classList.toggle("on", state.gaiaOn);
    drawGaia();
  });
  const bandBtn = $("#btn-band");
  if (bandBtn) bandBtn.addEventListener("click", () => {
    if (!state.manifest) return;
    state.bandOnly = !state.bandOnly;
    bandBtn.classList.toggle("on", state.bandOnly);
    stopPlay();
    if (state.bandOnly && !allowedFrames().includes(state.idx)) showFrame(allowedFrames()[0]);
    buildTimeline();
    showFrame(state.idx);
  });
  const tourBtn = $("#btn-tour");
  if (tourBtn) tourBtn.addEventListener("click", startTour);
  const tourExit = $("#tour-exit");
  if (tourExit) tourExit.addEventListener("click", endTour);
  const shareBtn = $("#btn-share");
  if (shareBtn) shareBtn.addEventListener("click", async () => {
    const u = new URL(location.href);
    u.searchParams.set("t", state.target.slug);
    history.replaceState(null, "", u.toString());
    try { await navigator.clipboard.writeText(u.toString()); shareBtn.textContent = "Link copied ✓"; }
    catch (e) { shareBtn.textContent = u.toString(); }
    setTimeout(() => { shareBtn.textContent = "Share link"; }, 2200);
  });
  window.addEventListener("resize", drawGaia);
}
const searchForm = $("#search-form");
if (searchForm) searchForm.addEventListener("submit", (e) => { e.preventDefault(); handleSearch($("#search-input").value); });

// Light / dark theme (default dark; the star stage stays black in both)
const themeBtn = $("#theme-btn");
if (themeBtn) {
  const paintThemeBtn = () => { themeBtn.textContent = document.documentElement.dataset.theme === "light" ? "🌙" : "☀️"; };
  themeBtn.addEventListener("click", () => {
    const next = document.documentElement.dataset.theme === "light" ? "dark" : "light";
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem("skyblink-theme", next); } catch (e) {}
    paintThemeBtn();
  });
  paintThemeBtn();
}

if (API && $("#foot-status")) $("#foot-status").textContent = "live backend connected";
if ($("#target-grid")) buildCards();
if (HAS_EXPLORER) {
  const params = new URLSearchParams(location.search);
  const start = TARGETS.some((t) => t.slug === params.get("t")) ? params.get("t") : "barnards-star";
  loadTarget(start, false);
}
