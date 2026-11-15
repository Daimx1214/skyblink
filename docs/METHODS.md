# SkyBlink methods — the Two-Epoch Check

## The named method

A candidate moving/changing object is accepted only if it passes all three tests:

1. **Both epochs.** The candidate appears in at least two independent epochs,
   shifted or changed consistently (a single-epoch flash is a cosmic ray or a
   transient artefact until proven otherwise).
2. **Not a known star.** The new position is checked against the Gaia catalogue
   (positions propagated from Gaia's 2016.0 epoch to the observation epoch using
   Gaia proper motions — skipping this step misplaces Barnard's Star by ~100″).
3. **Survives the difference view.** In the later-minus-earlier difference image,
   a real mover leaves a clean positive/negative dipole; ghosts, crosstalk and
   persistence artefacts do not behave consistently.

## Pipeline decisions (and why)

- **Epochs and dates.** Epoch *grouping* starts from the SIA result (`t_min`),
  clustered by >20 days, but every frame's published date is that exposure's
  own FITS `DATE-OBS`, read from the file actually rendered. (`t_min` alone
  mislabelled 17 of 21 frames in an earlier build — the cluster's first row is
  not necessarily the rendered exposure.) The FITS `DATE` header is the
  *processing* date and is never used.
- **Frame choice per epoch.** SIA returns every frame whose footprint intersects
  the search circle; SPHEREx's six detectors have offset footprints, so the
  frame that contains the target is chosen by minimum centre distance
  (≤1.2°), and its true detector is recorded in the manifest.
- **One grid, one stretch.** All frames of a target are reprojected
  (`reproject`) onto a single north-up TAN grid at 3.1″/px and rendered with a
  single global percentile + asinh stretch, so blinking shows sky change, not
  scaling change.
- **Cutouts.** Server-side cutouts via IRSA's IBE service
  (`?center={ra},{dec}d&size={deg}` appended to the file URI, per IRSA's own
  tutorial notebooks), with patient retries — the service throttles with
  503 "Server busy" under load.
- **Releases.** DR1 (reprocessed surveys 1–2) and QR3 (surveys 3–4) form one
  uniformly processed set and are the only releases mixed in a blink set.
  QR2 is superseded and excluded — except the official 3I/ATLAS observation
  table, which is QR2-based and labelled as such wherever used.

## Known limits (stated, not hidden)

- Quick-look photometry/spectra are per-survey-image estimates (resolution
  R≈40–130); publication-grade work needs the separate Spectral WCS and
  Solid Angle Pixel Map calibration products.
- 3I/ATLAS is a low-SNR, extended source in SPHEREx data; the case file says so.
- Barnard's Star moves ~1–2 SPHEREx pixels per year; Case 3 treats it as a
  measurement exercise with uncertainties, not a visual jump.

## Overlays, spectra and staying current

- **Two overlays, two epochs.** The Gaia overlay propagates every Gaia DR3
  star to the frame's own date with its measured proper motion. The WISE
  overlay draws NASA AllWISE catalogue positions exactly as catalogued (the
  extract carries no proper motions; epoch ~2010), so a fast mover's WISE
  diamond can sit off its SPHEREx position — the same displacement WiseView
  hunters measure.
- **Spectra are sampled, not interpolated.** A dossier spectrum is built
  exposure by exposure: every archive visit covering the position contributes
  one point at the wavelength its spectral WCS assigns to the target's pixel.
  SPHEREx has 102 channels; a position has only been sampled in the channels
  its visits placed on it, so each chart states how many channels it shows.
  The backend runs the same measurement on demand (`/api/spectrum`).
- **Links carry the view.** Target views use `?t=<slug>`; live coordinate
  views use `?ra&dec&fov`. The FoV control re-renders live at 3–20 arcmin.
- **Staying current.** `scripts/update_check.py` rebuilds each target's frame
  set from the live archive and diffs observation IDs against the cached
  manifest; a weekly scheduled run applies, re-enriches, re-bundles and
  re-publishes any target with new epochs, and changes nothing otherwise.
