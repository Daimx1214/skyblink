#!/usr/bin/env python3
"""Spectrum points from each dossier frame's own scan sequence.

Survey geometry (measured Nov 15): a pointing tiles the sky in strips —
a target is covered by essentially ONE sequence per pointing (its
dossier frame's sequence), which contributes that detector's 4 channel
groups at the wavelengths the LVF assigns to the target's pixel. Probing
the anchor sequence of every dossier frame therefore harvests all the
channels that pointing visit sampled at the position.
"""
import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from s3fetch import cached_listing  # noqa: E402
from spectrum_lib import bin_points, cache_pass  # noqa: E402
from spectrum_s3walk import probe, write_spectrum  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", required=True)
    ap.add_argument("--ra", type=float, required=True)
    ap.add_argument("--dec", type=float, required=True)
    ap.add_argument("--name", required=True)
    a = ap.parse_args()

    man = json.load(open(os.path.join(
        ROOT, "apps", "web", "cache", a.slug, "manifest.json")))
    pts = list(cache_pass(a.ra, a.dec, log=lambda *x: None))
    print(f"{a.slug}: cache points {len(pts)}", flush=True)
    for fr in man["frames"]:
        oid = fr["obs_id"]
        parts = oid.split("_")
        pointing, seq_i = "_".join(parts[:2]), int(parts[3])
        seq_stem = oid.rsplit("_", 1)[0]
        keys = None
        for t in ("dr1", "qr3"):
            try:
                cand = cached_listing(t, pointing)
            except Exception:  # noqa: BLE001
                continue
            if any(f"/level2_{seq_stem}_" in k for k in cand):
                keys = cand
                break
        if keys is None:
            print(f"{a.slug}: no listing {pointing}", flush=True)
            continue
        files = [k for k in keys if f"/level2_{seq_stem}_" in k]
        got = []
        with ThreadPoolExecutor(max_workers=6) as ex:
            for r in ex.map(lambda k: probe(k, a.ra, a.dec), files):
                if r:
                    got.append(r)
        pts.extend(got)
        print(f"{a.slug}: {seq_stem}: +{len(got)} points "
              f"(total {len(pts)}, channels {len(bin_points(pts)[0])})",
              flush=True)
    waves = write_spectrum(a.slug, a.name, pts)
    print(f"{a.slug}: FINAL {len(pts)} points, {len(waves)} channels",
          flush=True)
    print("ANCHORS_DONE", flush=True)


if __name__ == "__main__":
    main()
