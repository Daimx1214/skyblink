#!/usr/bin/env python3
"""Harvest a target's spectrum from every SPHEREx exposure the archive
holds for its position: local cache first (free), then SIA -> S3 range
fetches for the rest. Writes apps/web/cache/<slug>/spectrum.json, but ONLY
if the new spectrum has more distinct channels than the one on disk.

SIA flaps under load, so --sia-wait N keeps retrying the SIA query for up
to N minutes before giving up on the archive pass.
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pipeline import CACHE as PIPE_CACHE, cutout_url, fetch_cutout, sia_query  # noqa: E402
from spectrum_lib import (bin_points, cache_pass, frame_spectrum_point,  # noqa: E402
                          s3_pass, sia_rows_to_s3)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def ibe_pass(ra, dec, res, max_fetches, log=print):
    """Fallback when S3 key parsing finds nothing: IBE cutouts (small)."""
    rows = [r for r in res if float(r["dist_deg"]) <= 1.2]
    pts, n = [], 0
    for r in rows:
        if n >= max_fetches:
            break
        try:
            path = fetch_cutout(cutout_url(str(r["access_url"]), ra, dec, 0.05))
            n += 1
            got = frame_spectrum_point(path, ra, dec)
            if got:
                pts.append(got)
        except Exception as e:  # noqa: BLE001
            log(f"ibe pass: {str(e)[:80]}")
    log(f"ibe pass: {len(pts)} points, {n} fetched")
    return pts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", required=True)
    ap.add_argument("--ra", type=float, required=True)
    ap.add_argument("--dec", type=float, required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--max-fetches", type=int, default=200)
    ap.add_argument("--sia-wait", type=int, default=0,
                    help="minutes to keep retrying SIA")
    a = ap.parse_args()

    out = os.path.join(ROOT, "apps", "web", "cache", a.slug, "spectrum.json")
    best = [0]
    if os.path.exists(out):
        best[0] = len(json.load(open(out)).get("wave_um", []))
    print(f"{a.slug}: existing channels {best[0]}", flush=True)

    def write_if_better(points):
        waves, fluxes = bin_points(points)
        if len(waves) <= best[0] or len(waves) < 6:
            return waves
        payload = {
            "target": a.name,
            "source": f"SPHEREx DR1+QR3 individual exposures via IRSA "
                      f"({len(points)} exposures, {len(waves)} distinct channels)",
            "wave_um": waves,
            "flux_mjy": fluxes,
            "note": "Each point is one real SPHEREx exposure: wavelength from "
                    "that frame's spectral WCS at the target's pixel, flux from "
                    "aperture photometry (r=2 px, annulus background), "
                    "median-combined where visits repeat a channel. SPHEREx has "
                    "102 channels in total; these are the channels the archive's "
                    "visits have actually sampled at this position so far — the "
                    "count grows as the survey revisits the field. Zodiacal "
                    "light is modelled in the archive products, not subtracted "
                    "from Level-2 data, so read the broad shape with care.",
        }
        os.makedirs(os.path.dirname(out), exist_ok=True)
        json.dump(payload, open(out, "w"), indent=1)
        print(f"WROTE {out} channels: {len(waves)} "
              f"({waves[0]}..{waves[-1]} um)", flush=True)
        best[0] = len(waves)
        return waves

    pts = cache_pass(a.ra, a.dec)
    w0 = write_if_better(pts)
    print(f"after cache pass: {len(pts)} exposures -> {len(w0)} channels",
          flush=True)

    have_tags = set()
    for f in os.listdir(PIPE_CACHE):
        if f.startswith("s3v2_") and f.endswith(".fits"):
            have_tags.add(f[len("s3v2_"):-len(".fits")])

    res = None
    deadline = time.time() + a.sia_wait * 60
    while True:
        try:
            res = sia_query(a.ra, a.dec, 10)
            break
        except Exception as e:  # noqa: BLE001
            print(f"SIA down ({type(e).__name__}); "
                  f"{'retrying' if time.time() < deadline else 'giving up'}",
                  flush=True)
            if time.time() >= deadline:
                break
            time.sleep(45)
    if res is not None:
        print(f"SIA rows: {len(res)}", flush=True)
        rows = sia_rows_to_s3(res)
        print(f"S3-mappable rows: {len(rows)}", flush=True)
        if rows:
            pts += s3_pass(a.ra, a.dec, rows, max_fetches=a.max_fetches,
                           have_tags=have_tags)
        else:
            pts += ibe_pass(a.ra, a.dec, res, a.max_fetches)

    waves = write_if_better(pts)
    print(f"TOTAL {len(pts)} exposures -> {len(waves)} channels "
          f"({waves[0] if waves else '-'}..{waves[-1] if waves else '-'} um)",
          flush=True)


if __name__ == "__main__":
    main()
