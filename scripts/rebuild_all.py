#!/usr/bin/env python3
"""Rebuild all five target frame sets (current pipeline: north-up flip,
NaN fill, per-epoch best frame). FITS downloads are cached, so this is
mostly SIA queries + rendering. Sequential to respect IBE throttling."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pipeline import build_frames  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGETS = [
    ("barnards-star", 269.4464, 4.7671, 5.0),   # Gaia-propagated 2025.6 pos
    ("wise-0855", 133.7951, -7.2451, 3.0),
    ("epsilon-indi-b", 331.0438, -56.7828, 5.0),
    ("rw-aurigae", 76.9565, 30.4014, 5.0),
    ("r-draconis", 248.1675, 66.7550, 5.0),
]

if __name__ == "__main__":
    for slug, ra, dec, fov in TARGETS:
        out = os.path.join(ROOT, "apps", "web", "cache", slug)
        print(f"=== {slug} ===", flush=True)
        try:
            m = build_frames(ra, dec, fov, out)
            print(json.dumps({"slug": slug, "ok": m.get("ok"),
                              "frames": len(m.get("frames", []))}), flush=True)
        except Exception as e:
            print(json.dumps({"slug": slug, "ok": False, "error": str(e)[:200]}), flush=True)
    print("REBUILD_DONE", flush=True)
