#!/usr/bin/env python3
"""Harvest the Barnard spectrum from already-cached S3 mini-FITS files
(no downloads), then top up with targeted fetches only if coverage is thin."""
import glob
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from s3fetch import fetch_image_hdu, list_keys  # noqa: E402
from spectrum import frame_spectrum_point  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "apps", "web", "cache", "barnards-star", "spectrum.json")


def collect(paths):
    pts = []
    for p in paths:
        try:
            got = frame_spectrum_point(p)
        except Exception:  # noqa: BLE001
            got = None
        if got:
            pts.append(got)
            print(f"  {os.path.basename(p)}: {got[0]:.3f} um {got[1]:.1f} mJy",
                  flush=True)
    return pts


def main():
    cached = sorted(glob.glob(os.path.join(ROOT, "data", "cache", "s3v2_*.fits")))
    print(f"cached files: {len(cached)}")
    pts = collect(cached)
    print(f"points from cache: {len(pts)}")
    # top-up: neighbouring sequences of both visits, detectors unrestricted
    if len(pts) < 16:
        import re
        for pointing, seqs in (("2025W35_1A", (443, 445, 442, 446)),
                               ("2025W40_1A", (440, 442, 439, 443))):
            keys = [k for k in list_keys(f"dr1/level2/{pointing}/")
                    if k.endswith(".fits")]
            for seq in seqs:
                want = [k for k in keys if f"_{seq:04d}_" in k]
                have = {os.path.basename(p) for p in cached}
                for k in want:
                    tag = re.search(r"level2_(.+)_spx", k).group(1)
                    if f"s3v2_{tag}.fits" in have:
                        continue
                    try:
                        pts += collect([fetch_image_hdu(k, tag)])
                    except Exception as e:  # noqa: BLE001
                        print("  fetch fail", tag, str(e)[:60], flush=True)
                print(f"{pointing} seq {seq}: total points {len(pts)}", flush=True)
                if len(pts) >= 22:
                    break
            if len(pts) >= 22:
                break
    if len(pts) < 12:
        raise SystemExit(f"still too few points: {len(pts)}")
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
        "source": f"SPHEREx DR1 individual exposures via the IRSA S3 archive "
                  f"({len(pts)} exposures, {len(waves)} distinct channels)",
        "wave_um": waves,
        "flux_mjy": fluxes,
        "note": "Each point is one real SPHEREx exposure: wavelength from that "
                "frame's spectral WCS at the star's pixel, flux from aperture "
                "photometry (r=2 px, annulus background), median-combined where "
                "visits repeat a channel. Zodiacal light is modelled in the "
                "archive products, not subtracted from Level-2 data, so read "
                "the broad shape with care and the absorption structure as real.",
    }
    json.dump(payload, open(OUT, "w"), indent=1)
    print("WROTE", OUT, "channels:", len(waves), "span:",
          waves[0], "-", waves[-1], "um")


if __name__ == "__main__":
    main()
