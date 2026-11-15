#!/usr/bin/env python3
"""SkyBlink live backend (FastAPI).

Endpoints
  GET /api/health                 -> {"ok": true}
  GET /api/resolve?q=<name>       -> Sesame/SIMBAD name resolution {name, ra, dec}
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
    # Primary: the CDS Sesame name resolver (one fast HTTP GET). Fallback:
    # SIMBAD via astroquery. Order swapped 2026-11-15 evening: measured live,
    # Sesame answers real and bogus names in ~5 s, while SIMBAD's success
    # path took ~89 s for a real name the same evening, far beyond the front
    # end's 20 s budget. Each leg is capped at 8 s, so the worst case stays
    # inside that budget. Both return J2000 coordinates.
    sesame_error = None
    try:
        import re
        import urllib.parse
        import urllib.request
        url = ("https://cds.unistra.fr/cgi-bin/nph-sesame/-oxp/~S?"
               + urllib.parse.quote(q))
        req = urllib.request.Request(url, headers={"User-Agent": "skyblink-api"})
        with urllib.request.urlopen(req, timeout=8) as r:
            xml = r.read().decode("utf-8", "replace")
        ra = re.search(r"<jradeg>([\d.\-]+)</jradeg>", xml)
        dec = re.search(r"<jdedeg>([\d.\-]+)</jdedeg>", xml)
        if ra and dec:
            return {"name": q, "ra": float(ra.group(1)),
                    "dec": float(dec.group(1)), "source": "Sesame (CDS)"}
    except Exception as e:
        sesame_error = e
    try:
        from astroquery.simbad import Simbad
        sim = Simbad()
        sim.TIMEOUT = 8  # seconds; the front end gives the lookup 20 s in total
        sim.add_votable_fields("ra", "dec")
        res = sim.query_object(q)
        if res is not None and len(res) > 0:
            row = res[0]
            return {"name": q, "ra": float(row["ra"]), "dec": float(row["dec"]),
                    "source": "SIMBAD"}
    except Exception:
        pass
    if sesame_error is not None:
        raise HTTPException(502, f"name lookup failed: {str(sesame_error)[:120]}")
    raise HTTPException(404, "object not found in SIMBAD or Sesame")


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
        try:
            man = build_frames(ra, dec, fov, outdir, detector=det)
        except Exception as e:  # upstream archive (IRSA) outage etc.
            raise HTTPException(502, f"archive query failed: {type(e).__name__}: {str(e)[:160]}")
        if not man.get("ok"):
            raise HTTPException(404, man.get("reason", "no frames"))
    for fr in man["frames"]:
        fr["png"] = f"/api/file/{key}/{fr['png']}"
    man["cache_key"] = key
    return man


@app.get("/api/spectrum")
def spectrum(ra: float, dec: float):
    """On-the-fly spectrum: aperture photometry at the position in every
    archive exposure covering it, median-binned by channel. Budget-capped
    (40 fetches / ~4 min) so a serverless invocation stays within limits;
    'complete' says whether the whole archive set was sampled."""
    if not (-90 <= dec <= 90 and 0 <= ra < 360):
        raise HTTPException(422, "coordinates out of range")
    key = hashlib.sha256(f"spec,{ra:.4f},{dec:.4f}".encode()).hexdigest()[:16]
    path = os.path.join(LIVE_CACHE, f"spectrum-{key}.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    from pipeline import sia_query
    from spectrum_lib import bin_points, frame_spectrum_point, s3_pass, sia_rows_to_s3
    try:
        res = sia_query(ra, dec, 10)
    except Exception as e:  # upstream archive outage etc.
        raise HTTPException(502, f"archive query failed: {type(e).__name__}: {str(e)[:160]}")
    rows = sia_rows_to_s3(res)
    pts = []
    if rows:
        pts = s3_pass(ra, dec, rows, max_fetches=40, deadline_s=240,
                      log=lambda m: None)
        complete = len(rows) <= 40
    else:
        from pipeline import cutout_url, fetch_cutout
        n = 0
        for r in res:
            if float(r["dist_deg"]) > 1.2 or n >= 40:
                continue
            try:
                p = fetch_cutout(cutout_url(str(r["access_url"]), ra, dec, 0.05))
                n += 1
                got = frame_spectrum_point(p, ra, dec)
                if got:
                    pts.append(got)
            except Exception:  # noqa: BLE001
                continue
        complete = n < 40
    waves, fluxes = bin_points(pts)
    if len(waves) < 6:
        raise HTTPException(404, "too few spectral channels sampled at this position")
    payload = {"ok": True, "ra": ra, "dec": dec, "wave_um": waves,
               "flux_mjy": fluxes, "exposures": len(pts),
               "channels": len(waves), "complete": complete}
    try:
        with open(path, "w") as f:
            json.dump(payload, f)
    except OSError:
        pass
    return payload


@app.get("/api/file/{key}/{name}")
def file(key: str, name: str):
    path = os.path.join(LIVE_CACHE, key, os.path.basename(name))
    if not os.path.exists(path):
        raise HTTPException(404, "no such frame")
    return FileResponse(path, media_type="image/png")
