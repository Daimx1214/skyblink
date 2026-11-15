#!/usr/bin/env python3
"""SkyBlink data pipeline: SIA discovery -> cutout -> aligned PNG frames.

Verified routes (NASA Space Apps 2026 build, 14 Nov):
- SIA via astroquery Irsa.query_sia, collections spherex_dr1/_deep/_cube,
  spherex_qr3/_deep. Observation dates are taken from the rendered exposure's
  own FITS DATE-OBS header (the SIA cluster's first-row t_min proved WRONG
  for 17 of 21 frames in the Nov 2026 build - it dates the cluster's earliest
  row, not the picked frame; DATE-OBS always agrees with the OBSID week).
- Cutout: append "?center={ra},{dec}d&size={deg}" to the file URI
  (the literal trailing "d" after dec is IRSA's own example format).
- Wavelength is per-pixel (spectral WCS key "W"); there is no PIXSOLID
  keyword - pixel solid angle is a separate calibration product.
- Frames are reprojected onto ONE shared north-up TAN grid and rendered
  with ONE shared stretch so blinking shows sky change, not scaling change.
"""
import hashlib
import json
import os

import numpy as np
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.time import Time
from astropy.wcs import WCS
from astroquery.ipac.irsa import Irsa
from PIL import Image
from reproject import reproject_interp

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.environ.get("SKYBLINK_FITS_CACHE") or os.path.join(ROOT, "data", "cache")
try:
    os.makedirs(CACHE, exist_ok=True)
except OSError:  # read-only host (e.g. Vercel): fall back to /tmp
    CACHE = "/tmp/skyblink-fits-cache"
    os.makedirs(CACHE, exist_ok=True)

COLLECTIONS = ["spherex_dr1", "spherex_dr1_deep", "spherex_qr3", "spherex_qr3_deep"]
PIXSCALE_ARCSEC = 3.1  # half the native ~6.2"/px: smooth display grid


def sia_query(ra, dec, fov_arcmin):
    import time
    coord = SkyCoord(ra, dec, unit="deg")
    radius = (fov_arcmin / 2.0 + 2.0) * u.arcmin  # margin for pointing offsets
    last = None
    for attempt in range(4):
        try:
            res = Irsa.query_sia(pos=(coord, radius), collection=COLLECTIONS)
            break
        except Exception as e:  # IRSA/proxy flakiness: 502s happen
            last = e
            print(f"  SIA retry {attempt + 1}/4: {str(e)[:100]}", flush=True)
            time.sleep(20 * (attempt + 1))
    else:
        raise last
    # SIA returns every frame whose footprint intersects the search circle -
    # the target can sit outside a frame whose centre is up to ~1.9 deg away
    # (frame FoV 3.485 deg). Record centre distance so callers can pick
    # frames that actually contain the target.
    dra = (np.asarray(res["s_ra"]) - ra) * np.cos(np.deg2rad(dec))
    ddec = np.asarray(res["s_dec"]) - dec
    res["dist_deg"] = np.sqrt(dra ** 2 + ddec ** 2)
    return res


def _release_of(row):
    c = str(row["obs_collection"]).lower()
    return "DR1" if "dr1" in c else ("QR3" if "qr3" in c else c)


def group_epochs(res):
    """Group SIA rows into epoch clusters separated by >20 days."""
    rows = sorted(res, key=lambda r: float(r["t_min"]))
    groups, cur, last = [], [], None
    for r in rows:
        t = float(r["t_min"])
        if last is None or t - last <= 20:
            cur.append(r)
        else:
            groups.append(cur); cur = [r]
        last = t
    if cur:
        groups.append(cur)
    out = []
    for g in groups:
        t = Time(float(g[0]["t_min"]), format="mjd")
        out.append({
            "date": t.iso[0:10],
            "mjd": float(g[0]["t_min"]),
            "release": _release_of(g[0]),
            "rows": g,
        })
    return out


def cutout_url(access_url, ra, dec, size_deg):
    sep = "&" if "?" in access_url else "?"
    return f"{access_url}{sep}center={ra},{dec}d&size={size_deg:.4f}"


def pick_row(group_rows, detector=None):
    """From one epoch cluster, pick the frame whose centre is closest to the
    target - i.e. the frame that actually contains it. NOTE: SPHEREx's six
    detectors do NOT share one footprint (their strips are offset), so the
    covering detector varies by pointing; forcing one detector loses whole
    epochs (RW Aurigae: every D2 frame was >1.2 deg away while D1/D3 frames
    covered the star). The manifest records each frame's real detector.
    Returns None if even the closest frame is implausibly far (>1.2 deg)."""
    best = min(group_rows, key=lambda r: float(r["dist_deg"]))
    return best if float(best["dist_deg"]) <= 1.2 else None


def fetch_cutout(url):
    """Download with patient retries - the IRSA IBE server answers
    503 'Server busy, retry later' (and occasional 422) under load."""
    import time
    import requests
    key = hashlib.sha256(url.encode()).hexdigest()[:20] + ".fits"
    path = os.path.join(CACHE, key)
    if os.path.exists(path) and os.path.getsize(path) > 10000:
        return path
    last = None
    for attempt in range(8):
        try:
            with requests.get(url, headers={"User-Agent": "SkyBlink/0.1"},
                              stream=True, timeout=300) as r:
                if r.status_code == 200:
                    with open(path, "wb") as f:
                        for chunk in r.iter_content(1 << 20):
                            f.write(chunk)
                    return path
                last = f"HTTP {r.status_code}"
        except Exception as e:  # proxy drops etc.
            last = str(e)[:120]
        wait = 15 * (attempt + 1)
        print(f"  fetch retry {attempt + 1}/8 ({last}); waiting {wait}s", flush=True)
        time.sleep(wait)
    raise RuntimeError(f"cutout fetch failed: {last} :: {url}")


def target_wcs(ra, dec, fov_arcmin):
    n = int(round(fov_arcmin * 60.0 / PIXSCALE_ARCSEC))
    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    w.wcs.cunit = ["deg", "deg"]
    w.wcs.crpix = [n / 2.0, n / 2.0]
    w.wcs.cdelt = [-PIXSCALE_ARCSEC / 3600.0, PIXSCALE_ARCSEC / 3600.0]
    w.wcs.crval = [ra, dec]
    return w, (n, n)


def render_frame(fits_path, twcs, shape):
    with fits.open(fits_path) as hdul:
        img = hdul["IMAGE"].data.astype(np.float64)
        hdr = hdul["IMAGE"].header
        meta = {
            "detector": int(hdr.get("DETECTOR", 0) or 0),
            "obs_id": str(hdr.get("OBSID", "")),
            "date_obs": str(hdr.get("DATE-OBS", "")),
        }
        src_wcs = WCS(hdr)
    arr, _ = reproject_interp((img, src_wcs), twcs, shape_out=shape)
    return arr, meta


def stretch_pair(arrays):
    """One global percentile stretch across all frames (science-honest)."""
    sample = np.concatenate([a[np.isfinite(a)].ravel()[::37] for a in arrays])
    lo, hi = np.nanpercentile(sample, [1.0, 99.5])
    return lo, hi


def to_png(arr, lo, hi, path):
    # Fill off-footprint pixels (rotated source frames leave wedges) with the
    # stretch floor so they read as sky background, not black slabs.
    arr = np.where(np.isfinite(arr), arr, lo)
    # reproject arrays are row-0 = lowest Dec; flip so the PNG is north-up
    # (verified against Gaia-propagated Barnard's Star position, 14 Nov).
    arr = arr[::-1, :]
    x = (arr - lo) / max(hi - lo, 1e-12)
    x = np.nan_to_num(x, nan=0.0)
    x = np.arcsinh(x * 12.0) / np.arcsinh(12.0)  # asinh stretch
    img = Image.fromarray((np.clip(x, 0, 1) * 255).astype(np.uint8), mode="L")
    img.save(path)
    return path


def build_frames(ra, dec, fov_arcmin, outdir, detector=2):
    """Full route: query -> epoch groups -> cutouts -> aligned PNGs + manifest."""
    os.makedirs(outdir, exist_ok=True)
    res = sia_query(ra, dec, fov_arcmin)
    if len(res) == 0:
        return {"ok": False, "reason": "no SIA rows"}
    groups = group_epochs(res)
    twcs, shape = target_wcs(ra, dec, fov_arcmin)
    size_deg = fov_arcmin / 60.0
    picked, arrays = [], []
    for g in groups:
        row = pick_row(g["rows"], detector)
        if row is None:
            continue
        url = cutout_url(str(row["access_url"]), ra, dec, size_deg)
        path = fetch_cutout(url)
        arr, meta = render_frame(path, twcs, shape)
        pick = {**g, **meta, "center_dist_deg": float(row["dist_deg"])}
        if meta.get("date_obs"):
            # The frame's own DATE-OBS outranks the cluster's first-row t_min.
            pick["date"] = meta["date_obs"][0:10]
            pick["mjd"] = Time(meta["date_obs"]).mjd
        picked.append(pick)
        arrays.append(arr)
    if not arrays:
        return {"ok": False, "reason": "no epoch frame contains the target"}
    lo, hi = stretch_pair(arrays)
    frames = []
    for i, (p, arr) in enumerate(zip(picked, arrays)):
        png = os.path.join(outdir, f"frame_{i}.png")
        to_png(arr, lo, hi, png)
        frames.append({
            "index": i, "release": p["release"], "date": p["date"],
            "detector": p["detector"], "obs_id": p["obs_id"],
            "center_dist_deg": round(p.get("center_dist_deg", -1), 3),
            "png": os.path.basename(png),
        })
    manifest = {"ok": True, "ra": ra, "dec": dec, "fov_arcmin": fov_arcmin,
                "stretch": {"lo": lo, "hi": hi, "type": "asinh, global"},
                "frames": frames}
    with open(os.path.join(outdir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)
    return manifest


if __name__ == "__main__":
    import sys
    ra = float(sys.argv[1]); dec = float(sys.argv[2])
    fov = float(sys.argv[3]) if len(sys.argv) > 3 else 5.0
    out = sys.argv[4] if len(sys.argv) > 4 else os.path.join(CACHE, "test")
    print(json.dumps(build_frames(ra, dec, fov, out), indent=2))
