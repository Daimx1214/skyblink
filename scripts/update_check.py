#!/usr/bin/env python3
"""Easy-updating check for SkyBlink's five pre-loaded targets.

Rebuilds each target's frame set from the live archive into a scratch
directory and diffs the observation IDs against the cached manifest:
- "new-epochs": the archive has visits the site does not show yet
- "changed":    the set differs without additions (reprocessing)
- "current":    identical
- "archive-unreachable": IRSA did not answer; nothing was touched

With --apply, changed targets are updated in apps/web/cache/<slug>/
(manifest + PNGs), their enrich.json is rebuilt for the new frames while
PRESERVING the existing Gaia and WISE lists, and the caller should then
run bundle_cache.py and re-upload. Without --apply nothing is modified.
"""
import argparse
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import enrich as enrich_mod  # noqa: E402
from pipeline import build_frames  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_CACHE = os.path.join(ROOT, "apps", "web", "cache")
WORK = os.path.join(ROOT, "data", "update-check")

TARGETS = [
    ("barnards-star", 269.4464, 4.7671, 5.0),
    ("wise-0855", 133.7951, -7.2451, 3.0),
    ("epsilon-indi-b", 331.0438, -56.7828, 5.0),
    ("rw-aurigae", 76.9565, 30.4014, 5.0),
    ("r-draconis", 248.1675, 66.7550, 5.0),
]


def enrich_frames(man):
    omap = enrich_mod.obsid_map()
    twcs, shape = enrich_mod.target_wcs(man["ra"], man["dec"],
                                         man["fov_arcmin"])
    frames = []
    for fr in man["frames"]:
        p = omap.get(fr["obs_id"])
        if not p:
            continue
        arr, _ = enrich_mod.render_frame(p, twcs, shape)
        wave = enrich_mod.DET_WAVE.get(fr["detector"])
        frames.append({
            "obs_id": fr["obs_id"],
            "clean_pct": enrich_mod.clean_pct(p),
            "band_flux": enrich_mod.aperture_flux(arr),
            "wave_um": list(wave) if wave else None,
        })
    return frames


def apply_update(slug, tmp, man):
    dest = os.path.join(WEB_CACHE, slug)
    os.makedirs(dest, exist_ok=True)
    new_pngs = {fr["png"] for fr in man["frames"]}
    for fr in man["frames"]:
        shutil.copy2(os.path.join(tmp, fr["png"]),
                     os.path.join(dest, fr["png"]))
    for f in os.listdir(dest):
        if f.startswith("frame_") and f.endswith(".png") and f not in new_pngs:
            os.remove(os.path.join(dest, f))
    with open(os.path.join(dest, "manifest.json"), "w") as fh:
        json.dump(man, fh, indent=1)
    epath = os.path.join(dest, "enrich.json")
    old = {}
    if os.path.exists(epath):
        with open(epath) as fh:
            old = json.load(fh)
    gaia = old.get("gaia") or []
    if not gaia:
        try:
            radius = (man["fov_arcmin"] / 60.0) / 2 * 1.45
            got = enrich_mod.gaia_cone(man["ra"], man["dec"], radius)
            if got:
                gaia = got
        except Exception:  # noqa: BLE001
            pass
    merged = {"frames": enrich_frames(man), "gaia": gaia}
    if old.get("wise"):
        merged["wise"] = old["wise"]
    with open(epath, "w") as fh:
        json.dump(merged, fh, indent=1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    summary = {"new_epochs": [], "changed": [], "current": [],
               "unreachable": []}
    for slug, ra, dec, fov in TARGETS:
        tmp = os.path.join(WORK, slug)
        shutil.rmtree(tmp, ignore_errors=True)
        os.makedirs(tmp, exist_ok=True)
        try:
            man = build_frames(ra, dec, fov, tmp)
        except Exception as e:  # noqa: BLE001
            print(json.dumps({"slug": slug, "status": "archive-unreachable",
                              "error": f"{type(e).__name__}: {str(e)[:120]}"}),
                  flush=True)
            summary["unreachable"].append(slug)
            continue
        new_ids = {fr["obs_id"] for fr in man.get("frames", [])}
        old_path = os.path.join(WEB_CACHE, slug, "manifest.json")
        old_ids = set()
        if os.path.exists(old_path):
            with open(old_path) as fh:
                old_ids = {fr["obs_id"]
                           for fr in json.load(fh).get("frames", [])}
        added = sorted(new_ids - old_ids)
        removed = sorted(old_ids - new_ids)
        status = ("new-epochs" if added else
                  "changed" if removed else "current")
        print(json.dumps({"slug": slug, "status": status,
                          "frames": len(new_ids), "added": added,
                          "removed": removed}), flush=True)
        summary[{"new-epochs": "new_epochs"}.get(status, status)].append(slug)
        if a.apply and status != "current":
            apply_update(slug, tmp, man)
            print(json.dumps({"slug": slug, "applied": True}), flush=True)
    print(json.dumps({"summary": summary}), flush=True)
    print("UPDATE_CHECK_DONE", flush=True)


if __name__ == "__main__":
    main()
