#!/usr/bin/env python3
"""Case 1 (hero): interstellar comet 3I/ATLAS, Aug 2025 vs Dec 2025.

Route (v2, after the DataLink dead-end): IRSA's comet table
(obscore_3I_Atlas.vot) gives the comet's predicted RA/Dec per exposure.
We take its mid-August and mid-December positions and run the STANDARD
DR1/QR3 SIA pipeline at those sky positions, choosing the epoch cluster
nearest each visit. The comet is a faint, extended, low-SNR source in
SPHEREx data - the case file says so; the panels are honest archive
cutouts centred where the visitor was.
"""
import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pipeline import (sia_query, group_epochs, pick_row, cutout_url,  # noqa: E402
                      fetch_cutout, target_wcs, render_frame, stretch_pair, to_png)
from astropy.io.votable import parse  # noqa: E402
from astropy.time import Time  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FOV = 12.0


def comet_pos(table, month):
    sub = table[[d.startswith(month) for d in table["date"]]]
    r = sub[len(sub) // 2]
    return float(r["comet_ra"]), float(r["comet_dec"]), str(r["date"])[:10]


def nearest_group(groups, target_iso):
    t = date.fromisoformat(target_iso)
    def dist(g):
        return abs((date.fromisoformat(g["date"]) - t).days)
    return min(groups, key=dist)


def main():
    t = parse(os.path.join(ROOT, "data", "cache", "3iatlas.vot")).get_first_table().to_table()
    t["date"] = Time(t["t_min"], format="mjd").iso
    outdir = os.path.join(ROOT, "apps", "web", "cache", "case-3iatlas")
    os.makedirs(outdir, exist_ok=True)
    frames, arrays = [], []
    for i, month in enumerate(("2025-08", "2025-12")):
        ra, dec, visit = comet_pos(t, month)
        res = sia_query(ra, dec, FOV)
        groups = group_epochs(res)
        g = nearest_group(groups, visit)
        row = pick_row(g["rows"])
        if row is None:
            raise RuntimeError(f"no frame contains the comet position for {month}")
        url = cutout_url(str(row["access_url"]), ra, dec, FOV / 60.0)
        path = fetch_cutout(url)
        twcs, shape = target_wcs(ra, dec, FOV)
        arr, meta = render_frame(path, twcs, shape)
        arrays.append(arr)
        frames.append({
            "index": i, "release": g["release"], "date": g["date"],
            "detector": meta["detector"], "obs_id": meta["obs_id"],
            "comet_ra": round(ra, 4), "comet_dec": round(dec, 4),
            "png": f"frame_{i}.png",
        })
        print(f"{month}: comet at {ra:.4f},{dec:.4f} -> {g['release']} {g['date']} {meta['obs_id']}", flush=True)
    lo, hi = stretch_pair(arrays)
    for fr, arr in zip(frames, arrays):
        to_png(arr, lo, hi, os.path.join(outdir, fr["png"]))
    manifest = {"ok": True, "case": "3I/ATLAS",
                "note": "DR1/QR3 cutouts centred on the comet's predicted position at each visit (positions: IRSA 3I/ATLAS table). Low SNR, extended source.",
                "fov_arcmin": FOV, "frames": frames}
    with open(os.path.join(outdir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
