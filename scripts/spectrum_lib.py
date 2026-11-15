#!/usr/bin/env python3
"""Shared spectrum machinery: one SPHEREx Level-2 exposure = one spectral
channel at a sky position (its spectral WCS gives the wavelength at that
pixel). A spectrum = aperture photometry at the position in every exposure
whose footprint covers it, median-binned by channel.

Used by scripts/spectrum_harvest.py (pre-computed dossier spectra) and by
services/api/main.py (/api/spectrum, on-the-fly).
"""
import glob
import os
import sys
import time

import numpy as np
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.wcs import WCS

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pipeline import CACHE as PIPE_CACHE  # noqa: E402  (data/cache)
from s3fetch import cached_listing, fetch_image_hdu, list_keys  # noqa: E402


def frame_spectrum_point(fits_path, ra, dec):
    """(wave_um, flux_mjy) for the position in one exposure, or None."""
    with fits.open(fits_path) as hdul:
        img = hdul["IMAGE"]
        data = np.asarray(img.data, dtype=np.float64)
        hdr = img.header
        wcel = WCS(hdr, fobj=hdul, naxis=2)
        px, py = wcel.world_to_pixel(SkyCoord(ra, dec, unit="deg"))
        px, py = float(px), float(py)
        h, w = data.shape
        if not (8 < px < w - 8 and 8 < py < h - 8):
            return None
        wave = None
        try:
            ww = WCS(hdr, fobj=hdul, key="W")
            world = ww.pixel_to_world(px, py)
            cands = world if isinstance(world, (list, tuple)) else [world]
            for x in cands:
                spec = getattr(x, "spectral", None)
                if spec is not None:
                    wave = float(np.ravel(spec.to(u.um).value)[0])
                    break
                try:
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


def bin_points(pts):
    """Median-bin near-identical wavelengths (same channel, many epochs)."""
    bins = {}
    for wave, flux in pts:
        bins.setdefault(round(wave / 0.004), []).append((wave, flux))
    waves, fluxes = [], []
    for key in sorted(bins):
        grp = bins[key]
        waves.append(round(float(np.median([g[0] for g in grp])), 3))
        fluxes.append(round(float(np.median([g[1] for g in grp])), 2))
    return waves, fluxes


def cache_pass(ra, dec, log=print):
    """Points from every already-downloaded FITS in data/cache (free)."""
    pts = []
    files = sorted(glob.glob(os.path.join(PIPE_CACHE, "*.fits")))
    for p in files:
        try:
            got = frame_spectrum_point(p, ra, dec)
        except Exception:  # noqa: BLE001
            got = None
        if got:
            pts.append(got)
    log(f"cache pass: {len(pts)} points from {len(files)} files")
    return pts


def s3_pass(ra, dec, rows, max_fetches=180, deadline_s=None, log=print,
            have_tags=None):
    """Points from SIA rows via the S3 bucket (range-fetched mini-FITS).

    rows: SIA result rows (need obs_collection + access_url is NOT used;
    the S3 key is found by listing the pointing and matching the file whose
    name carries the same obs stem the archive used). We instead match by
    listing each pointing once and trying every not-yet-cached file whose
    sequence is in the row set — simpler: the caller passes rows already
    reduced to (tree, pointing, obs_stem) tuples via sia_rows_to_s3()."""
    pts = []
    fetched = 0
    t0 = time.time()
    listings = {}
    for tree, pointing, stem in rows:
        if fetched >= max_fetches:
            log(f"s3 pass: fetch cap {max_fetches} reached")
            break
        if deadline_s and time.time() - t0 > deadline_s:
            log("s3 pass: deadline reached")
            break
        tag = stem
        if have_tags and tag in have_tags:
            continue
        if pointing not in listings:
            try:
                listings[pointing] = cached_listing(tree, pointing)
            except Exception as e:  # noqa: BLE001
                log(f"s3 pass: list {pointing} failed {str(e)[:80]}")
                listings[pointing] = []
        key = next((k for k in listings[pointing]
                    if f"level2_{stem}_" in k and k.endswith(".fits")), None)
        if not key:
            continue
        try:
            path = fetch_image_hdu(key, tag)
            fetched += 1
            if have_tags is not None:
                have_tags.add(tag)
            got = frame_spectrum_point(path, ra, dec)
            if got:
                pts.append(got)
        except Exception as e:  # noqa: BLE001
            log(f"s3 pass: {stem} failed {str(e)[:80]}")
    log(f"s3 pass: {len(pts)} points, {fetched} fetched")
    return pts


def sia_rows_to_s3(res):
    """Reduce SIA rows (dist<=1.2 deg) to (tree, pointing, obs_stem) tuples.
    The obs stem is read from the access_url's file name, which carries the
    same level2_<stem>_spx name as the S3 key."""
    out = []
    seen = set()
    for r in res:
        if float(r["dist_deg"]) > 1.2:
            continue
        url = str(r["access_url"])
        stem = None
        for part in url.replace("?", "/").split("/"):
            if part.startswith("level2_") and "_spx" in part:
                stem = part[len("level2_"):].split("_spx")[0]
                break
        if not stem or stem in seen:
            continue
        seen.add(stem)
        coll = str(r["obs_collection"]).lower()
        tree = "dr1" if "dr1" in coll else "qr3"
        pointing = "_".join(stem.split("_")[:2])
        out.append((tree, pointing, stem))
    out.sort(key=lambda t: t[2])
    return out
