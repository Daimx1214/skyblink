#!/usr/bin/env python3
"""Enrich each target set with judge-grade extras, all from real data:

- clean_pct: % of the exposure's cutout pixels whose SPHEREx FLAGS value is
  in the conservative good set {0 (no flag bits), 2097152 (SOURCE bit alone,
  bit 21: pixel mapped to a known source)}. Bit meanings are the archive's
  own MSKN/MSKD header descriptions; value 2 is the OVERFLOW bit and is NOT
  counted as clean.
- band_flux: aperture photometry (MJy/sr sum, r=3px, annulus background) at
  the target position on the reprojected frame, with the detector's
  wavelength band - the honest per-band view of the target.
- gaia: ESA Gaia DR3 sources in the field (ra, dec, G mag, proper motions,
  epoch 2016.0) for the browser overlay, propagated client-side per frame.

Writes apps/web/cache/<slug>/enrich.json. bundle_cache.py merges it.
"""
import json
import os
import sys

import numpy as np
import requests
from astropy.io import fits

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pipeline import CACHE as FITS_CACHE, render_frame, target_wcs  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_CACHE = os.path.join(ROOT, "apps", "web", "cache")
GOOD_FLAGS = {0, 2097152}
DET_WAVE = {1: (0.75, 1.09), 2: (1.10, 1.62), 3: (1.63, 2.41),
            4: (2.42, 3.82), 5: (3.83, 4.41), 6: (4.42, 5.00)}
GAIA_TAP = "https://gea.esac.esa.int/tap-server/tap/sync"


def obsid_map():
    m = {}
    for f in os.listdir(FITS_CACHE):
        if not f.endswith(".fits"):
            continue
        p = os.path.join(FITS_CACHE, f)
        try:
            with fits.open(p) as h:
                m[str(h["IMAGE"].header.get("OBSID", ""))] = p
        except Exception:
            pass
    return m


def clean_pct(fits_path):
    with fits.open(fits_path) as h:
        fl = h["FLAGS"].data
    vals, counts = np.unique(fl, return_counts=True)
    total = counts.sum()
    good = sum(c for v, c in zip(vals, counts) if int(v) in GOOD_FLAGS)
    return round(100.0 * good / total, 1)


def aperture_flux(arr):
    h, w = arr.shape
    cy, cx = h // 2, w // 2
    yy, xx = np.mgrid[0:h, 0:w]
    r = np.hypot(yy - cy, xx - cx)
    ap = (r <= 3) & np.isfinite(arr)
    ann = (r >= 6) & (r <= 9) & np.isfinite(arr)
    if ap.sum() == 0 or ann.sum() == 0:
        return None
    bg = np.median(arr[ann])
    return float((arr[ap] - bg).sum())


def gaia_cone(ra, dec, radius_deg):
    adql = (
        "SELECT ra, dec, phot_g_mean_mag, pmra, pmdec FROM gaiadr3.gaia_source "
        f"WHERE CONTAINS(POINT('ICRS', ra, dec), CIRCLE('ICRS', {ra}, {dec}, {radius_deg})) = 1 "
        "AND phot_g_mean_mag < 19 ORDER BY phot_g_mean_mag"
    )
    r = requests.post(GAIA_TAP, data={
        "REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "csv",
        "QUERY": adql}, timeout=120)
    r.raise_for_status()
    lines = r.text.strip().splitlines()[1:]
    out = []
    for ln in lines[:400]:
        parts = ln.split(",")
        if len(parts) < 5:
            continue
        def num(x):
            try:
                return float(x)
            except ValueError:
                return 0.0
        out.append({"ra": num(parts[0]), "dec": num(parts[1]),
                    "g": round(num(parts[2]), 1),
                    "pmra": num(parts[3]), "pmdec": num(parts[4])})
    return out


def main():
    omap = obsid_map()
    print(f"{len(omap)} cached FITS by OBSID")
    for slug in sorted(os.listdir(WEB_CACHE)):
        d = os.path.join(WEB_CACHE, slug)
        man_path = os.path.join(d, "manifest.json")
        if not os.path.isdir(d) or not os.path.exists(man_path):
            continue
        with open(man_path) as f:
            man = json.load(f)
        twcs, shape = target_wcs(man["ra"], man["dec"], man["fov_arcmin"])
        frames = []
        for fr in man["frames"]:
            p = omap.get(fr["obs_id"])
            if not p:
                print(slug, fr["obs_id"], "FITS not in cache - skipped")
                continue
            arr, _ = render_frame(p, twcs, shape)
            det = fr["detector"]
            frames.append({
                "obs_id": fr["obs_id"],
                "clean_pct": clean_pct(p),
                "band_flux": aperture_flux(arr),
                "wave_um": DET_WAVE.get(det),
            })
        radius = (man["fov_arcmin"] / 60.0) / 2 * 1.45
        try:
            gaia = gaia_cone(man["ra"], man["dec"], radius)
        except Exception as e:
            gaia = []
            print(slug, "gaia failed:", str(e)[:120])
        with open(os.path.join(d, "enrich.json"), "w") as f:
            json.dump({"frames": frames, "gaia": gaia}, f)
        print(slug, f"frames enriched {len(frames)}, gaia {len(gaia)}")
    print("ENRICH_DONE")


if __name__ == "__main__":
    main()
