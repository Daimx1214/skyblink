# SkyBlink

**Watch the sky change.** SkyBlink is a public web tool that shows how a patch of
sky changes over time in real NASA **SPHEREx** survey images — like a little video
of the sky. Moving objects jump, variable stars pulse, and artefacts fail our
**Two-Epoch Check**. The deployed site pre-loads the five official test targets;
the same pipeline in this repo renders any coordinates locally or via its API
service.

Built by **Team Sohan Halwa** (Daim Ali & Ali Abdullah) for the
**NASA Space Apps Challenge 2026**, challenge *Planet X and SPHEREx*.

## Live

- Web app: https://daimx1214.github.io/skyblink/
- Static build: the five official test targets and the 3I/ATLAS case are
  pre-rendered (frame images embedded in `cache-data.js`), so the demo works
  without any backend or live IRSA query.

## What it does

Six pages, one job: show how the sky changes.

- **Coordinate / name search (backend)** — the challenge's stated objective: enter a
  patch of sky (RA/Dec or an object name resolved via SIMBAD) and get a blink series.
  Runs on the API service in `services/`; the deployed static site pre-loads the targets.
- **Blink player** — aligned, north-up epochs flip in place; play/pause, step,
  timeline, speed. **Modes** — Blink · Side-by-side · Difference (later − earlier).
- **Five official test targets pre-loaded** — Barnard's Star, WISE 0855,
  Epsilon Indi B, RW Aurigae, R Draconis, each with its honest display recipe.
- **Dossier page per target** — blink explorer plus facts, an **ESA Gaia DR3
  overlay** (positions proper-motion propagated to each frame's epoch), per-frame
  **data quality** (clean-pixel % from the SPHEREx FLAGS plane) and **wavelength
  band**, a **detector band-flux chart**, and the field inside the SPHEREx
  all-sky cube via **Aladin Lite**.
- **Shareable views** — every target lives at its own URL (`target.html?t=…`);
  a Share link button copies the current view.
- **Case Files** — guided investigations: interstellar comet **3I/ATLAS** between
  its August and December 2025 visits; the **Two-Epoch Check** candidate-vetting
  method; and a **measured proper-motion case** — Barnard's Star centroided in
  all five epochs against Gaia's prediction (offsets 1.3–7.4″, i.e. 0.4–2.4
  rendered pixels, with the scatter's likeliest confound stated).
- **Methods & Data pages** — the full pipeline, two pipeline mistakes we caught
  and fixed (a south-up rendering bug; a 4.4′ stale target centre), the stated
  limits, and a table of all eight challenge resources with how each was used.
- **Provenance everywhere** — every frame shows its release (DR1/QR3), observation
  date (from archive metadata, not file headers), detector and observation ID.
- **Dark & light themes**, responsive down to phones, no accounts, no tracking.

## How it works

```
IRSA SIA query ──► epoch clustering ──► per-epoch frame that actually
contains the target ──► IRSA cutout service ──► reproject to ONE shared
north-up grid (3.1″/px) ──► ONE shared asinh stretch ──► PNG frames + manifest
```

Key facts baked into the pipeline (all verified against IRSA's own SPHEREx
tutorial notebooks — see `docs/METHODS.md`):

- Observation dates come from SIA/TAP metadata (`t_min`), never the FITS `DATE`
  header (that's processing time).
- SPHEREx's six detectors do **not** share one footprint; the pipeline picks,
  per epoch, the frame that actually contains the target and records its detector.
- Wavelength in SPHEREx is per-pixel (spectral WCS); there is no `PIXSOLID`
  keyword — pixel solid angle is a separate calibration product.

## Demo & source

- **Demo video (29 s):** `skyblink-demo.mp4` in this repo.
- **Full source:** the pipeline (`scripts/`), API service (`services/`), docs
  (`docs/`) and target list (`data/targets.yaml`) are browsable in this repo;
  `skyblink-source.zip` bundles the same tree as one archive. The website itself
  (index.html, style.css, app.js, cache-data.js) lives at the repo root.

## Run it

Static site (targets + case files work with zero backend), from the repo root:

```bash
python3 -m http.server 8000
```

Live backend (any coordinates):

```bash
python3 -m venv .venv && .venv/bin/pip install astropy astroquery reproject photutils fastapi uvicorn pillow scipy
.venv/bin/uvicorn services.api.main:app --port 8000
# GET /api/health · /api/resolve?q=Barnard's Star · /api/frames?ra=269.4521&dec=4.6934&fov=5
```

Regenerate the pre-rendered targets:

```bash
.venv/bin/python scripts/precache_all.py     # the four remaining targets
.venv/bin/python scripts/pipeline.py 269.4464 4.7671 5 cache/barnards-star
.venv/bin/python scripts/comet_case.py       # Case 1: 3I/ATLAS
```

## Limits

- Frames from different SPHEREx detectors are different wavelength bands.
  Cross-band blinks show colour change as well as motion; same-band pairs are
  isolable in the viewer ("Same band only").
- Frames show the archive IMAGE plane as delivered: zodiacal light is not
  subtracted and flagged pixels are not masked; the "Clean pixels" figure
  reports the unflagged share (FLAGS 0, or the SOURCE bit alone).
- Injection tests use idealised Gaussians and our own detection rule; they
  measure the difference test's sensitivity, not performance on real movers.

## Data & credits

SPHEREx Level-2 images and archive services: **IRSA at IPAC (NASA/JPL-Caltech and
the SPHEREx team)** — DR1 Spectral Images (doi:10.26131/IRSA678), DR1 Spectral
All-Sky Cube (doi:10.26131/IRSA679), QR3 (doi:10.26131/IRSA662); the
3I/ATLAS observation table (QR2 processing) from IRSA's comet page. Reference
positions/proper motions: **ESA Gaia (DPAC)**. Name resolution: **SIMBAD (CDS)**.
Solar-system positions: **SkyBoT (IMCCE)**. This project is not affiliated with
or endorsed by NASA.

## AI disclosure

AI assistants were used for research, planning and code drafting during this
hackathon, under the team's direction. All data shown are real archive products;
nothing is simulated.

## License

MIT — see `LICENSE`.
