#!/usr/bin/env python3
"""Spectrum points from S3 Level-2 exposures WITHOUT any IRSA query.

For a target, take the observation sequences its dossier frames came from
(from the bundled manifest). Within a sequence the bucket holds every
channel x detector file; most do not cover the target, so each candidate is
probed with header-only Range fetches (plus the small WCS-WAVE table): the
spectral WCS says whether the position falls in the exposure and at what
wavelength. Only for covering files do we fetch the 17 image rows around
the pixel and run spectrum_lib.frame_spectrum_point's exact aperture math
(r=2 px aperture, 5-8 px annulus background, same unit conversion).

Usage: spectrum_s3point.py --slug rw-aurigae --ra .. --dec .. --name ".."
"""
import argparse
import io
import json
import os
import sys

import numpy as np
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.wcs import WCS

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s3fetch  # noqa: E402
from s3fetch import BUCKET, cached_listing  # noqa: E402
from spectrum_lib import bin_points, cache_pass  # noqa: E402
from spectrum_cube import open_extension  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BLOCK = 2880


def fetch_header(url, offset):
    """(cards dict, header_bytes_len, raw_header_bytes) at offset."""
    size = BLOCK * 12
    while True:
        buf = s3fetch._get_range(url, offset, offset + size - 1)
        cards, hbytes = s3fetch._parse_header(buf)
        if cards is not None:
            return cards, hbytes, buf[:hbytes]
        size *= 2
        if size > BLOCK * 80:
            raise RuntimeError("header too long")


def probe_and_measure(key, ra, dec):
    """(wave_um, flux_mjy) if the exposure covers the position, else None.
    Costs a few small Range fetches; image rows only when covered."""
    url = f"{BUCKET}/{key}"
    offset = 0
    img = None      # (cards, data_start, raw_header)
    wave_hdu = None
    for _ in range(14):
        cards, hbytes, raw = fetch_header(url, offset)
        dsize = s3fetch._data_size(cards)
        ext = cards.get("EXTNAME", "").strip()
        if ext == "IMAGE":
            img = (cards, offset + hbytes, raw)
        elif ext == "WCS-WAVE":
            data = s3fetch._get_range(url, offset + hbytes,
                                      offset + hbytes + dsize - 1)
            wave_hdu = (raw, data)
            break
        offset += hbytes + dsize
    if img is None or wave_hdu is None:
        return None
    icards, istart, iraw = img
    hdr = fits.Header.fromstring(iraw.decode("ascii"), sep="")
    with open_extension(wave_hdu[0], wave_hdu[1]) as hdul:
        wcel = WCS(hdr, fobj=hdul, naxis=2)
        px, py = wcel.world_to_pixel(SkyCoord(ra, dec, unit="deg"))
        px, py = float(px), float(py)
        h = int(icards["NAXIS2"])
        wdt = int(icards["NAXIS1"])
        if not (8 < px < wdt - 8 and 8 < py < h - 8):
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
    row0 = int(np.floor(py)) - 8
    nrows = 17
    row_bytes = wdt * 4
    buf = s3fetch._get_range(url, istart + row0 * row_bytes,
                             istart + (row0 + nrows) * row_bytes - 1)
    data = np.frombuffer(buf, dtype=">f4").astype(np.float64).reshape(
        nrows, wdt)
    yy, xx = np.mgrid[0:nrows, 0:wdt]
    r2 = (xx - px) ** 2 + (yy - (py - row0)) ** 2
    ap = r2 <= 2.0 ** 2
    ann = (r2 > 5.0 ** 2) & (r2 <= 8.0 ** 2)
    bg = np.nanmedian(data[ann])
    flux = float(np.nansum((data - bg)[ap]) * factor)
    return wave, flux


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", required=True)
    ap.add_argument("--ra", type=float, required=True)
    ap.add_argument("--dec", type=float, required=True)
    ap.add_argument("--name", required=True)
    a = ap.parse_args()

    man = json.load(open(os.path.join(
        ROOT, "apps", "web", "cache", a.slug, "manifest.json")))
    seqs = {}
    for fr in man["frames"]:
        oid = fr["obs_id"]
        seq = oid.rsplit("_", 1)[0]
        seqs.setdefault(seq, fr["detector"])
    print(f"{a.slug}: sequences {list(seqs)}", flush=True)

    pts = list(cache_pass(a.ra, a.dec, log=lambda *x: None))
    print(f"{a.slug}: cache points {len(pts)}", flush=True)
    seen_keys = set()
    for seq, anchor_det in seqs.items():
        pointing = "_".join(seq.split("_")[:2])
        keys = []
        for tree in ("dr1", "qr3"):
            try:
                keys += [k for k in cached_listing(tree, pointing)
                         if f"/level2_{seq}_" in k and k.endswith(".fits")]
            except Exception as e:  # noqa: BLE001
                print("listing failed", tree, pointing, str(e)[:80],
                      flush=True)
        by_ch = {}
        for k in keys:
            stem = k.split("level2_")[1].split("_spx")[0]  # SEQ_CH D DET
            tail = stem[len(seq) + 1:]                     # e.g. "3D5"
            ch_s, det_s = tail.split("D")
            by_ch.setdefault(int(ch_s), {})[int(det_s)] = k
        print(f"{a.slug}: {seq}: {len(by_ch)} channels on bucket",
              flush=True)
        last_det = anchor_det
        for ch in sorted(by_ch):
            dets = by_ch[ch]
            order = sorted(dets, key=lambda d: (abs(d - last_det), d))
            for det in order:
                k = dets[det]
                if k in seen_keys:
                    continue
                seen_keys.add(k)
                try:
                    got = probe_and_measure(k, a.ra, a.dec)
                except Exception as e:  # noqa: BLE001
                    print("  probe failed", k.split("/")[-1],
                          str(e)[:90], flush=True)
                    got = None
                if got:
                    pts.append(got)
                    last_det = det
                    break
        waves_now, _ = bin_points(pts)
        print(f"{a.slug}: after {seq}: {len(pts)} points, "
              f"{len(waves_now)} channels", flush=True)

    waves, fluxes = bin_points(pts)
    print(f"{a.slug}: TOTAL {len(pts)} points -> {len(waves)} channels",
          flush=True)
    out = os.path.join(ROOT, "apps", "web", "cache", a.slug, "spectrum.json")
    existing = 0
    if os.path.exists(out):
        existing = len(json.load(open(out)).get("wave_um", []))
    if len(waves) >= 6 and len(waves) > existing:
        payload = {
            "target": a.name,
            "source": f"SPHEREx DR1+QR3 individual exposures via IRSA "
                      f"({len(pts)} exposures, {len(waves)} distinct "
                      f"channels)",
            "wave_um": waves,
            "flux_mjy": fluxes,
            "note": "Each point is one real SPHEREx exposure: wavelength "
                    "from that frame's spectral WCS at the target's pixel, "
                    "flux from aperture photometry (r=2 px, annulus "
                    "background), median-combined where visits repeat a "
                    "channel. SPHEREx has 102 channels in total; these are "
                    "the channels the archive's visits have actually "
                    "sampled at this position so far — the count grows as "
                    "the survey revisits the field. Zodiacal light is "
                    "modelled in the archive products, not subtracted from "
                    "Level-2 data, so read the broad shape with care.",
        }
        with open(out, "w") as f:
            json.dump(payload, f, indent=1)
        print(f"{a.slug}: WROTE spectrum.json ({len(waves)} channels)",
              flush=True)
    else:
        print(f"{a.slug}: not better than existing ({existing}); kept",
              flush=True)
    print("S3POINT_DONE", flush=True)


if __name__ == "__main__":
    main()
