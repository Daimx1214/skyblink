#!/usr/bin/env python3
"""Case 3 measurement: centroid Barnard's Star in every reprojected frame
and compare with the Gaia DR3 prediction (proper-motion propagated).

Gaia DR3 4472832130942575872, epoch 2016.0: ra 269.44850, dec +4.73942,
pmra -801.6 mas/yr (cos-dec applied), pmdec +10362.4 mas/yr.
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from astropy.io import fits  # noqa: E402
from astropy.time import Time  # noqa: E402
from astropy.wcs import WCS  # noqa: E402
from astropy.coordinates import SkyCoord  # noqa: E402
import astropy.units as u  # noqa: E402
from enrich import FITS_CACHE  # noqa: E402
from pipeline import render_frame, target_wcs  # noqa: E402


def obsid_map_centred(ra, dec):
    """OBSID -> cutout path, using only full archive MEFs (with a FLAGS
    plane) and preferring the cutout centred on the target. (The shared
    enrich.obsid_map is last-file-wins over every cached FITS, including
    partial S3 header fetches - that once silently broke this script.)"""
    from collections import defaultdict
    d = defaultdict(list)
    for f in os.listdir(FITS_CACHE):
        p = os.path.join(FITS_CACHE, f)
        if not f.endswith(".fits"):
            continue
        try:
            with fits.open(p) as h:
                if "FLAGS" not in [x.name for x in h]:
                    continue
                oid = h["IMAGE"].header.get("OBSID")
                if oid:
                    d[str(oid).strip()].append(p)
        except Exception:
            continue
    target = SkyCoord(ra, dec, unit="deg")

    def cdist(p):
        with fits.open(p) as h:
            w = WCS(h["IMAGE"].header, naxis=2)
            ny, nx = h["IMAGE"].data.shape
            return target.separation(w.pixel_to_world(nx / 2, ny / 2)).to(u.arcmin).value

    return {k: min(v, key=cdist) for k, v in d.items()}

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RA0, DEC0 = 269.44850, 4.73942
PMRA, PMDEC = -801.6, 10362.4  # mas/yr


def propagate(year):
    dt = year - 2016.0
    ra = RA0 + (PMRA / 3.6e6) * dt / np.cos(np.deg2rad(DEC0))
    dec = DEC0 + (PMDEC / 3.6e6) * dt
    return ra, dec


def centroid_near(arr, px, py, box=7, rad=5):
    h, w = arr.shape
    x0, x1 = max(int(px) - box, 0), min(int(px) + box + 1, w)
    y0, y1 = max(int(py) - box, 0), min(int(py) + box + 1, h)
    sub = arr[y0:y1, x0:x1].copy()
    yy, xx = np.mgrid[y0:y1, x0:x1]
    keep = np.hypot(xx - px, yy - py) <= rad
    sub = np.where(keep, sub, np.nan)
    bg = np.nanmedian(sub)
    wts = np.clip(sub - bg, 0, None) ** 2
    if np.nansum(wts) == 0:
        return None
    cx = float(np.nansum(xx * wts) / np.nansum(wts))
    cy = float(np.nansum(yy * wts) / np.nansum(wts))
    return cx, cy


def main():
    with open(os.path.join(ROOT, "apps/web/cache/barnards-star/manifest.json")) as f:
        man = json.load(f)
    omap = obsid_map_centred(man["ra"], man["dec"])
    twcs, shape = target_wcs(man["ra"], man["dec"], man["fov_arcmin"])
    rows = []
    for fr in man["frames"]:
        year = Time(fr["date"]).decimalyear
        ra_s, dec_s = propagate(year)
        px, py = twcs.world_to_pixel_values(ra_s, dec_s)
        arr, _ = render_frame(omap[fr["obs_id"]], twcs, shape)
        c = centroid_near(arr, float(px), float(py))
        if c is None:
            rows.append({**fr, "meas": None})
            continue
        # array row 0 = lowest Dec; PNG flips rows. Report in sky terms:
        # offset of measured centroid from prediction, in arcsec.
        dx_arcsec = (c[0] - float(px)) * 3.1
        dy_arcsec = (c[1] - float(py)) * 3.1
        rows.append({
            "date": fr["date"], "release": fr["release"],
            "detector": fr["detector"], "obs_id": fr["obs_id"],
            "pred_px": [round(float(px), 2), round(float(py), 2)],
            "meas_px": [round(c[0], 2), round(c[1], 2)],
            "offset_arcsec": round(float(np.hypot(dx_arcsec, dy_arcsec)), 2),
        })
    print(json.dumps(rows, indent=1))
    with open(os.path.join(ROOT, "apps/web/cache/barnards-star/measure.json"), "w") as f:
        json.dump(rows, f)


if __name__ == "__main__":
    main()
