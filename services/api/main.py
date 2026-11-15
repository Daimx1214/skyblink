#!/usr/bin/env python3
"""SkyBlink live backend (FastAPI).

Endpoints
  GET /api/health                 -> {"ok": true}
  GET /api/resolve?q=<name>       -> SIMBAD name resolution {name, ra, dec}
  GET /api/frames?ra&dec&fov&det  -> blink manifest for ANY coordinates;
                                     frames are rendered on first request by
                                     scripts/pipeline.py and cached on disk.
  GET /api/file/<key>/<png>       -> a rendered frame PNG

The judged paths (five official targets, hero case) are ALSO committed as a
static cache in apps/web/cache, so the demo never depends on this service
being awake.
"""
import hashlib
import json
import os
import sys

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from pipeline import build_frames  # noqa: E402

LIVE_CACHE = os.environ.get("SKYBLINK_CACHE_DIR") or os.path.join(ROOT, "data", "live-cache")
try:
    os.makedirs(LIVE_CACHE, exist_ok=True)
except OSError:  # read-only host (e.g. Vercel): fall back to /tmp
    LIVE_CACHE = "/tmp/skyblink-live-cache"
    os.makedirs(LIVE_CACHE, exist_ok=True)

app = FastAPI(title="SkyBlink API", version="0.1")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"],
                   allow_headers=["*"])


@app.get("/api/health")
def health():
    return {"ok": True, "service": "skyblink-api"}


@app.get("/api/resolve")
def resolve(q: str = Query(..., min_length=2)):
    # Primary: SIMBAD via astroquery. Fallback: the CDS Sesame name resolver.
    # (On 2026-11-15 SIMBAD's TAP capabilities endpoint returned 404 while
    # Sesame stayed reachable via a mirror — a name lookup should not die
    # with one service.) Both return J2000 coordinates.
    try:
        from astroquery.simbad import Simbad
        sim = Simbad()
        sim.add_votable_fields("ra", "dec")
        res = sim.query_object(q)
        if res is not None and len(res) > 0:
            row = res[0]
            return {"name": q, "ra": float(row["ra"]), "dec": float(row["dec"]),
                    "source": "SIMBAD"}
    except Exception:
        pass
    try:
        import re
        import urllib.parse
        import urllib.request
        url = ("https://cds.unistra.fr/cgi-bin/nph-sesame/-oxp/~S?"
               + urllib.parse.quote(q))
        req = urllib.request.Request(url, headers={"User-Agent": "skyblink-api"})
        with urllib.request.urlopen(req, timeout=20) as r:
            xml = r.read().decode("utf-8", "replace")
        ra = re.search(r"<jradeg>([\d.\-]+)</jradeg>", xml)
        dec = re.search(r"<jdedeg>([\d.\-]+)</jdedeg>", xml)
        if ra and dec:
            return {"name": q, "ra": float(ra.group(1)),
                    "dec": float(dec.group(1)), "source": "Sesame (CDS)"}
        raise HTTPException(404, "object not found in SIMBAD or Sesame")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"name lookup failed: {str(e)[:120]}")


@app.get("/api/frames")
def frames(ra: float, dec: float, fov: float = 5.0, det: int = 2):
    if not (-90 <= dec <= 90 and 0 <= ra < 360 and 1 <= fov <= 30):
        raise HTTPException(422, "coordinates or FoV out of range")
    key = hashlib.sha256(f"{ra:.4f},{dec:.4f},{fov},{det}".encode()).hexdigest()[:16]
    outdir = os.path.join(LIVE_CACHE, key)
    man_path = os.path.join(outdir, "manifest.json")
    if os.path.exists(man_path):
        with open(man_path) as f:
            man = json.load(f)
    else:
        man = build_frames(ra, dec, fov, outdir, detector=det)
        if not man.get("ok"):
            raise HTTPException(404, man.get("reason", "no frames"))
    for fr in man["frames"]:
        fr["png"] = f"/api/file/{key}/{fr['png']}"
    man["cache_key"] = key
    return man


@app.get("/api/file/{key}/{name}")
def file(key: str, name: str):
    path = os.path.join(LIVE_CACHE, key, os.path.basename(name))
    if not os.path.exists(path):
        raise HTTPException(404, "no such frame")
    return FileResponse(path, media_type="image/png")
