#!/usr/bin/env python3
"""Top up the Barnard spectrum from the star's other known visits.

The five blink epochs in the site manifest are five separate visits; at
each visit's sequence, every channel file of every detector is a candidate
spectral point. Merges with points from the already-cached W35/W40 files.
"""
import glob
import json
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harvest_spectrum import collect  # noqa: E402
from s3fetch import fetch_image_hdu, list_keys  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "apps", "web", "cache", "barnards-star", "spectrum.json")

VISITS = [  # (pointing, seq, trees in preference order)
    ("2026W12_1A", 311, ("dr1", "qr3")),
    ("2026W19_1A", 46, ("dr1", "qr3")),
    ("2026W34_2A", 233, ("qr3", "dr1")),
    ("2025W40_1A", 441, ("dr1",)),
]


def main():
    cached = [p for p in glob.glob(os.path.join(ROOT, "data", "cache", "s3v2_*.fits"))
              if "2025W35_1A" in p or "2025W40_1A" in p or "diag444" in p]
    print(f"re-collecting from {len(cached)} cached visit files")
    pts = collect(sorted(cached))
    print(f"base points: {len(pts)}", flush=True)
    have = {os.path.basename(p) for p in glob.glob(
        os.path.join(ROOT, "data", "cache", "s3v2_*.fits"))}
    for pointing, seq, trees in VISITS:
        keys = []
        for tree in trees:
            keys = [k for k in list_keys(f"{tree}/level2/{pointing}/")
                    if f"_{seq:04d}_" in k and k.endswith(".fits")]
            if keys:
                print(f"{pointing} seq {seq}: {len(keys)} files in {tree}")
                break
        for k in sorted(keys):
            tag = re.search(r"level2_(.+)_spx", k).group(1)
            if f"s3v2_{tag}.fits" in have:
                continue
            try:
                pts += collect([fetch_image_hdu(k, tag)])
            except Exception as e:  # noqa: BLE001
                print("  fetch fail", tag, str(e)[:60], flush=True)
        print(f"after {pointing}: {len(pts)} points", flush=True)
    if len(pts) < 12:
        raise SystemExit(f"too few points: {len(pts)}")
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
        "source": f"SPHEREx DR1/QR3 individual exposures via the IRSA S3 archive "
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
    print("WROTE", OUT, "channels:", len(waves), "span:", waves[0], "-", waves[-1])


if __name__ == "__main__":
    main()
