# SkyBlink

**Watch the sky change.** SkyBlink is a public web tool that lets anyone enter the
coordinates of a patch of sky and watch it change over time in real NASA **SPHEREx**
survey images — like a little video of the sky. Moving objects jump, variable stars
pulse, and artefacts fail our **Two-Epoch Check**.

Built by **Team Sohan Halwa** (Daim Ali & Ali Abdullah) for the
**NASA Space Apps Challenge 2026**, challenge *Planet X and SPHEREx*.

## Live

- Web app: *(deployed URL — see the Space Apps project page)*
- The five official test targets and the hero case are pre-rendered into
  `apps/web/cache/`, so the demo works even with the backend asleep.

## What it does

- **Coordinate / name search** — the challenge's stated objective: users enter a
  patch of sky (RA/Dec or an object name resolved via SIMBAD) and get a blink series.
- **Blink player** — aligned epochs flip in place; play/pause, step, timeline, speed.
- **Modes** — Blink · Side-by-side · Difference (later − earlier).
- **Five official test targets pre-loaded** — Barnard's Star, WISE 0855,
  Epsilon Indi B, RW Aurigae, R Draconis, each with its honest display recipe.
- **Case Files** — guided investigations, led by Case 1: interstellar comet
  **3I/ATLAS** in August vs December 2025.
- **Provenance everywhere** — every frame shows its release (DR1/QR3), observation
  date (from archive metadata, not file headers), detector and observation ID.

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

## Run it

Static site (targets + case files work with zero backend):

```bash
cd apps/web && python3 -m http.server 8000
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
.venv/bin/python scripts/pipeline.py 269.4521 4.6934 5 apps/web/cache/barnards-star
.venv/bin/python scripts/comet_case.py       # Case 1: 3I/ATLAS
```

## Data & credits

SPHEREx Level-2 images and archive services: **IRSA at IPAC (NASA/JPL-Caltech and
the SPHEREx team)** — releases DR1 (DOI 10.26131/IRSA662 family) and QR3; the
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
