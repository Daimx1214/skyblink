#!/usr/bin/env python3
"""WISE overlay data via IRSA's Gator catalog service (the TAP service's
sibling — used when TAP is down). Same enrich.json format as fetch_wise.py:
"wise": [{"ra","dec","w1"}] with W1 < 17, brightest first, top 500."""
import io
import json
import os

import requests
from astropy.io import ascii as aascii

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "apps", "web", "cache")
TARGETS = [
    ("barnards-star", 269.4464, 4.7671, 5.0),
    ("wise-0855", 133.7951, -7.2451, 3.0),
    ("epsilon-indi-b", 331.0438, -56.7828, 5.0),
    ("rw-aurigae", 76.9565, 30.4014, 5.0),
    ("r-draconis", 248.1675, 66.7550, 5.0),
]
GATOR = "https://irsa.ipac.caltech.edu/cgi-bin/Gator/nph-query"


def wise_cone_gator(ra, dec, radius_arcsec):
    r = requests.get(GATOR, params={
        "outfmt": 1,
        "objstr": f"{ra} {dec:+.4f}",
        "spatial": "Cone",
        "radius": int(radius_arcsec),
        "catalog": "allwise_p3as_psd",
    }, timeout=120)
    r.raise_for_status()
    if "RowsRetrieved" not in r.text and "ra" not in r.text[:2000]:
        raise RuntimeError("unexpected Gator response: " + r.text[:120])
    tab = aascii.read(r.text, format="ipac")
    cols = {c.lower(): c for c in tab.colnames}
    ra_c, dec_c, w1_c = cols["ra"], cols["dec"], cols["w1mpro"]
    rows = []
    for row in tab:
        w1 = row[w1_c]
        if w1 is None or str(w1).strip() in ("", "null"):
            continue
        w1f = float(w1)
        if w1f >= 17:
            continue
        rows.append({"ra": round(float(row[ra_c]), 5),
                     "dec": round(float(row[dec_c]), 5),
                     "w1": round(w1f, 2)})
    rows.sort(key=lambda d: d["w1"])
    return rows[:500]


def main():
    for slug, ra, dec, fov in TARGETS:
        path = os.path.join(CACHE, slug, "enrich.json")
        if not os.path.exists(path):
            print(slug, "no enrich.json, skipping", flush=True)
            continue
        with open(path) as f:
            enrich = json.load(f)
        if enrich.get("wise"):
            print(slug, "wise already present:", len(enrich["wise"]), flush=True)
            continue
        radius = fov * 0.75 * 60.0  # arcsec, same coverage as fetch_wise.py
        try:
            wise = wise_cone_gator(ra, dec, radius)
        except Exception as e:  # noqa: BLE001
            print(slug, "WISE GATOR FAILED:", str(e)[:160], flush=True)
            continue
        enrich["wise"] = wise
        with open(path, "w") as f:
            json.dump(enrich, f, indent=1)
        print(slug, f"wise sources: {len(wise)}", flush=True)
    print("WISE_GATOR_DONE", flush=True)


if __name__ == "__main__":
    main()
