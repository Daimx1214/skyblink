#!/usr/bin/env python3
"""Fill the two IRSA-blocked data products straight from the S3 archive:
  1. Barnard's Star spectrum  -> apps/web/cache/barnards-star/spectrum.json
  2. 3I/ATLAS case frames     -> apps/web/cache/case-3iatlas/{frame_*.png,manifest.json}
Both reuse the project's own photometry/rendering code; only the transport
changes (public S3 bucket + HTTP Range fetches of the IMAGE HDU).
"""
import json
import os
import re
import sys

import numpy as np
from astropy.io.votable import parse
from astropy.time import Time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from comet_case import FOV, comet_pos  # noqa: E402
from pipeline import render_frame, stretch_pair, target_wcs, to_png  # noqa: E402
from s3fetch import fetch_image_hdu, list_keys  # noqa: E402
from spectrum import frame_spectrum_point  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_CACHE = os.path.join(ROOT, "apps", "web", "cache")
RA, DEC = 269.4464, 4.7671


def find_key(tree, pointing, did):
    keys = list_keys(f"{tree}/level2/{pointing}/")
    for k in keys:
        if f"_{did}_spx" in k:
            return k
    return None


# ---------------- spectrum ----------------
def spectrum_job():
    out = os.path.join(WEB_CACHE, "barnards-star", "spectrum.json")
    if os.path.exists(out):
        print("spectrum: already done"); return
    pts = []
    for pointing, pref_seq in (("2025W35_1A", 444), ("2025W40_1A", 441)):
        keys = [k for k in list_keys(f"dr1/level2/{pointing}/")
                if k.endswith(".fits")]
        by_seq = {}
        for k in keys:
            m = re.search(r"_(\d{4})_(\d+)D(\d)_spx", k)
            if m:
                by_seq.setdefault(int(m.group(1)), []).append(k)
        seqs = sorted(by_seq, key=lambda s: abs(s - pref_seq))
        print(f"{pointing}: {len(keys)} files, {len(seqs)} sequences")
        tried = 0
        for seq in seqs[:14]:
            for k in sorted(by_seq[seq]):
                if len(pts) >= 26 or tried >= 130:
                    break
                tried += 1
                tag = re.search(r"level2_(.+)_spx", k).group(1)
                try:
                    path = fetch_image_hdu(k, tag)
                    got = frame_spectrum_point(path)
                except Exception as e:  # noqa: BLE001
                    print(f"  {tag}: {type(e).__name__} {str(e)[:60]}", flush=True)
                    continue
                if got:
                    pts.append(got)
                    print(f"  {tag}: {got[0]:.3f} um {got[1]:.1f} mJy", flush=True)
            if len(pts) >= 26 or tried >= 130:
                break
        print(f"{pointing}: points so far {len(pts)} after {tried} files")
    print(f"spectrum points: {len(pts)}")
    if len(pts) < 12:
        raise SystemExit("spectrum: too few points")
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
    json.dump(payload, open(out, "w"), indent=1)
    print("spectrum: wrote", out, "channels:", len(waves))


# ---------------- comet ----------------
def comet_job():
    outdir = os.path.join(WEB_CACHE, "case-3iatlas")
    man_path = os.path.join(outdir, "manifest.json")
    if os.path.exists(man_path):
        print("comet: already done"); return
    os.makedirs(outdir, exist_ok=True)
    t = parse(os.path.join(ROOT, "data", "cache", "3iatlas.vot")) \
        .get_first_table().to_table()
    t["date"] = Time(t["t_min"], format="mjd").iso
    frames, arrays = [], []
    for i, (month, trees, release) in enumerate((
            ("2025-08", ("dr1", "qr2"), "DR1"),
            ("2025-12", ("qr3", "qr2"), "QR3"))):
        sub = t[[str(d).startswith(month) for d in t["date"]]]
        dra = (np.asarray(sub["s_ra"]) - np.asarray(sub["comet_ra"])) \
            * np.cos(np.deg2rad(np.asarray(sub["comet_dec"])))
        ddec = np.asarray(sub["s_dec"]) - np.asarray(sub["comet_dec"])
        dist = np.hypot(dra, ddec)
        det = np.array([int(str(x)[1:]) for x in sub["spherex_detector"]])
        # comet must sit well inside the frame; prefer long-wave detectors
        score = dist - 0.02 * np.isin(det, (5, 6, 4))
        j = int(np.argmin(score))
        row = sub[j]
        ra, dec = float(row["comet_ra"]), float(row["comet_dec"])
        did = str(row["obs_creator_did"])
        pointing = "_".join(did.split("_")[:2])
        key = None
        for tree in trees:
            key = find_key(tree, pointing, did)
            if key:
                break
        if not key:
            raise RuntimeError(f"comet {month}: {did} not found in S3 trees {trees}")
        path = fetch_image_hdu(key, did)
        twcs, shape = target_wcs(ra, dec, FOV)
        arr, meta = render_frame(path, twcs, shape)
        arrays.append(arr)
        frames.append({
            "index": i, "release": release, "date": str(row["date"])[:10],
            "detector": meta["detector"], "obs_id": meta["obs_id"],
            "comet_ra": round(ra, 4), "comet_dec": round(dec, 4),
            "png": f"frame_{i}.png",
        })
        print(f"comet {month}: {did} -> {key.split('/')[-1]}", flush=True)
    lo, hi = stretch_pair(arrays)
    for fr, arr in zip(frames, arrays):
        to_png(arr, lo, hi, os.path.join(outdir, fr["png"]))
    manifest = {"ok": True, "case": "3I/ATLAS",
                "note": "DR1/QR3 frames centred on the comet's predicted position at each visit (positions: IRSA 3I/ATLAS table). Low SNR, extended source.",
                "fov_arcmin": FOV, "frames": frames}
    with open(man_path, "w") as f:
        json.dump(manifest, f, indent=2)
    print("comet: wrote manifest", frames)


if __name__ == "__main__":
    for job in (spectrum_job, comet_job):
        try:
            job()
        except SystemExit as e:
            print(job.__name__, "exit:", e)
        except Exception as e:  # noqa: BLE001
            print(job.__name__, "FAILED:", type(e).__name__, str(e)[:200])
    print("S3_JOBS_DONE")
