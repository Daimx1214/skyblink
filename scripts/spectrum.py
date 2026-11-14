#!/usr/bin/env python3
"""Barnard's Star spectrum from REAL individual SPHEREx exposures (v2).

Every SPHEREx Level-2 exposure is ONE spectral channel: its spectral WCS
gives the exact wavelength at every pixel. So a spectrum is assembled by
taking every DR1/QR3 exposure whose footprint covers the star (dozens,
across all six detectors and many epochs), reading the wavelength at the
star's pixel from the spectral WCS, and doing aperture photometry there.
Channels repeated across epochs are combined by median.

Output: apps/web/cache/barnards-star/spectrum.json
  {wave_um: [...], flux_mjy: [...], source, note}
Flux conversion (documented): [mJy] = [MJy/sr] x 23.5045 x pixscale^2 / 1000
per pixel, aperture-summed minus annulus background.
"""
import json
import os
import sys

import numpy as np
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.wcs import WCS

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pipeline import CACHE, cutout_url, fetch_cutout, sia_query  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "apps", "web", "cache", "barnards-star", "spectrum.json")
RA, DEC = 269.4464, 4.7671
MAX_FRAMES = 40


def frame_spectrum_point(fits_path):
    """Return (wave_um, flux_mjy) for the star in one exposure, or None."""
    with fits.open(fits_path) as hdul:
        img = hdul["IMAGE"]
        data = np.asarray(img.data, dtype=np.float64)
        hdr = img.header
        wcel = WCS(hdr, fobj=hdul, naxis=2)
        px, py = wcel.world_to_pixel(SkyCoord(RA, DEC, unit="deg"))
        px, py = float(px), float(py)
        h, w = data.shape
        if not (8 < px < w - 8 and 8 < py < h - 8):
            return None
        # wavelength at the star pixel from the spectral WCS (alternate key W)
        wave = None
        try:
            ww = WCS(hdr, fobj=hdul, key="W")
            world = ww.pixel_to_world(px, py)
            cands = world if isinstance(world, (list, tuple)) else [world]
            wave = None
            for x in cands:
                spec = getattr(x, "spectral", None)
                if spec is not None:
                    wave = float(np.ravel(spec.to(u.um).value)[0])
                    break
                try:  # a bare SpectralCoord converts directly
                    wave = float(np.ravel(x.to(u.um).value)[0])
                    break
                except Exception:  # noqa: BLE001
                    continue
        except Exception:  # noqa: BLE001
            wave = None
        if wave is None or not (0.7 < wave < 5.2):
            return None
        cd = wcel.proj_plane_pixel_scales()
        pixscale = float(cd[0].to(u.arcsec).value)
        factor = 23.5045 * pixscale ** 2 / 1000.0
        yy, xx = np.mgrid[0:h, 0:w]
        r2 = (xx - px) ** 2 + (yy - py) ** 2
        ap = r2 <= 2.0 ** 2
        ann = (r2 > 5.0 ** 2) & (r2 <= 8.0 ** 2)
        bg = np.nanmedian(data[ann])
        flux = float(np.nansum((data - bg)[ap]) * factor)
        return wave, flux


def main():
    if os.path.exists(OUT):
        print("spectrum.json already exists"); return
    res = sia_query(RA, DEC, 10)
    rows = [r for r in res if float(r["dist_deg"]) <= 1.2]
    print(f"{len(rows)} exposures cover the star")
    if len(rows) > MAX_FRAMES:  # spread evenly across the result set
        step = len(rows) / MAX_FRAMES
        rows = [rows[int(i * step)] for i in range(MAX_FRAMES)]
    pts = []
    for i, r in enumerate(rows):
        url = cutout_url(str(r["access_url"]), RA, DEC, 0.05)
        try:
            path = fetch_cutout(url)
            got = frame_spectrum_point(path)
        except Exception as e:  # noqa: BLE001
            print(f"  frame {i}: {type(e).__name__} {str(e)[:80]}", flush=True)
            continue
        if got:
            pts.append(got)
            print(f"  frame {i}: {got[0]:.3f} um  {got[1]:.1f} mJy", flush=True)
    print(f"{len(pts)} channel points")
    if len(pts) < 12:
        raise SystemExit("too few channels - will retry later")
    # bin near-identical wavelengths (same channel, different epochs): median
    pts.sort()
    bins = {}
    for wave, flux in pts:
        bins.setdefault(round(wave / 0.004), []).append((wave, flux))
    waves, fluxes = [], []
    for key in sorted(bins):
        grp = bins[key]
        waves.append(round(float(np.median([g[0] for g in grp])), 3))
        fluxes.append(round(float(np.median([g[1] for g in grp])), 2))
    payload = {
        "target": "Barnard's Star",
        "source": f"SPHEREx DR1+QR3 individual exposures via IRSA SIA "
                  f"({len(pts)} exposures, {len(waves)} distinct channels)",
        "wave_um": waves,
        "flux_mjy": fluxes,
        "note": "Each point is one real SPHEREx exposure: wavelength from that "
                "frame's spectral WCS at the star's pixel, flux from aperture "
                "photometry (r=2 px, annulus background), median-combined where "
                "epochs repeat a channel. Zodiacal light is modelled in the "
                "archive products, not subtracted from Level-2 data, so read "
                "the broad shape with care and the absorption structure as real.",
    }
    json.dump(payload, open(OUT, "w"), indent=1)
    print("wrote", OUT, "channels:", len(waves))


if __name__ == "__main__":
    main()
