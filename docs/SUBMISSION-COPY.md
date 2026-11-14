# Space Apps project page — paste-ready copy (Team Sohan Halwa · SkyBlink)

**Project name:** SkyBlink

**High-level summary (draft):**
SkyBlink is a public web tool that lets anyone enter the coordinates of a patch of
sky and watch it change over time in real NASA SPHEREx survey images — like a
little video of the sky. It lines up SPHEREx observations of the same field taken
months apart (Data Release 1 + Quick Release 3, one uniformly processed set),
aligns them on a shared north-up grid with one shared brightness stretch, and
blinks them: moving objects jump, variable stars pulse, and false candidates are
screened out by our named Two-Epoch Check — a vetting method, documented in the
project and applied in its validation. The five test targets named in the challenge —
Barnard's Star, Epsilon Indi B, WISE 0855, RW Aurigae and R Draconis — are
pre-loaded with per-target dossier pages: a blink explorer with Blink /
Side-by-side / Difference modes, an ESA Gaia DR3 overlay proper-motion propagated
to each epoch, per-frame data-quality (clean-pixel %) and wavelength band, a
detector-band flux chart, and the field in the SPHEREx all-sky cube via Aladin
Lite. Barnard's Star's dossier also assembles a real 102-band-style spectrum
from 27 individual Level-2 exposures (0.84–4.79 µm): each point's wavelength
comes from that frame's own spectral WCS at the star's pixel, its flux from
aperture photometry on the archive data. Guided Case Files follow interstellar comet 3I/ATLAS between its August
and December 2025 visits, document the Two-Epoch Check, and present a measured
proper-motion case: Barnard's Star centroided in all five epochs agrees with
Gaia's prediction to within 1.3–7.4 arcsec (0.4–2.4 rendered pixels), with the scatter's likeliest confound stated
honestly. Every view carries its coordinates in the URL for sharing and
embedding, and the site ships in dark and light themes. A 35-second guided tour
walks a first-time visitor through a complete hunt. The method is validated, not
just described: 540 synthetic movers injected into real epoch pairs were
recovered at 100% (≥15σ; 97–98% at 8σ for shifts ≥2 px), and a control run on
uninjected pairs counts 439 raw ≥6σ residual peaks — the measured reason a
candidate must still be vetted by the Two-Epoch Check. The explorer is fully
keyboard-operable, its difference palette is colour-blind-safe, and it runs on
phones with no account and no tracking.

**Demo:** https://drive.google.com/file/d/15Kzl2TC1TY-ssvGV4cXGv0QP_1gZgAI_/view?usp=drivesdk (video, 29 s) · Direct-play mirror: https://daimx1214.github.io/skyblink/skyblink-demo.mp4 · Backup: 7-slide deck.

**Live site:** https://daimx1214.github.io/skyblink/ · **Code:** https://github.com/Daimx1214/skyblink

**Data & resources used:**
- SPHEREx Level-2 images + IRSA SIA/TAP archive services (IRSA at IPAC,
  NASA/JPL-Caltech & the SPHEREx team) — releases DR1 and QR3
- IRSA 3I/ATLAS observation table (comet positions per exposure)
- SPHEREx tutorial notebooks (IRSA) — cutout, spectral-WCS and photometry recipes
- ESA Gaia DR3 (DPAC) via ESA TAP — reference positions & proper motions
- SIMBAD (CDS) — name resolution; SkyBoT (IMCCE) — solar-system positions
- Aladin Lite / HiPS (CDS) — sky-browsing technology reference
- Astropy, astroquery, reproject, photutils (open-source Python astronomy stack)

**AI disclosure (paste as-is):**
AI assistants were used for research, planning and code drafting during this
hackathon, under the team's direction. All data shown are real archive products;
nothing is simulated.

**Team:** Daim Ali (owner) & Ali Abdullah — Team Sohan Halwa, Universal Event.
