#!/usr/bin/env python3
"""Fetch NASA WISE (AllWISE) catalogue sources for each target field and
store them in apps/web/cache/<slug>/enrich.json as "wise":
[{ra, dec, w1}] — J2000 positions at the WISE epoch (~2010), brightest
first. Primary: IRSA TAP. Fallback: VizieR TAP. Mirrors enrich.py's Gaia
fetch so the site can draw a WISE overlay next to the Gaia one.
"""
import csv
import io
import json
import os
import sys
import time

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "apps", "web", "cache")

TARGETS = [
    ("barnards-star", 269.4464, 4.7671, 5.0),
    ("wise-0855", 133.7951, -7.2451, 3.0),
    ("epsilon-indi-b", 331.0438, -56.7828, 5.0),
    ("rw-aurigae", 76.9565, 30.4014, 5.0),
    ("r-draconis", 248.1675, 66.7550, 5.0),
]

IRSA_TAP = "https://irsa.ipac.caltech.edu/TAP/sync"
VIZIER_TAP = "https://tapvizier.u-strasbg.fr/TAPVizieR/tap/sync"


def _tap_csv(url, adql, timeout=120):
    r = requests.get(url, params={"REQUEST": "doQuery", "LANG": "ADQL",
                                  "FORMAT": "csv", "QUERY": adql},
                     timeout=timeout)
    r.raise_for_status()
    rows = list(csv.DictReader(io.StringIO(r.text)))
    if rows and any("QUERY_STATUS" in (v or "") for row in rows
                    for v in row.values()):
        raise RuntimeError("TAP error status")
    return rows


def wise_cone(ra, dec, radius_deg):
    adql_irsa = (
        "SELECT TOP 500 raj2000, dej2000, w1mpro FROM allwise_p3as_psd "
        f"WHERE CONTAINS(POINT('ICRS', raj2000, dej2000), "
        f"CIRCLE('ICRS', {ra}, {dec}, {radius_deg})) = 1 "
        "AND w1mpro IS NOT NULL AND w1mpro < 17 ORDER BY w1mpro ASC")
    last = None
    for attempt in range(3):
        try:
            rows = _tap_csv(IRSA_TAP, adql_irsa)
            return [{"ra": round(float(r["raj2000"]), 5),
                     "dec": round(float(r["dej2000"]), 5),
                     "w1": round(float(r["w1mpro"]), 2)} for r in rows]
        except Exception as e:  # noqa: BLE001
            last = e
            print(f"  IRSA TAP attempt {attempt + 1}: {str(e)[:100]}",
                  flush=True)
            time.sleep(15 * (attempt + 1))
    adql_viz = (
        'SELECT TOP 500 RAJ2000, DEJ2000, W1mag FROM "II/328/allwise" '
        f"WHERE CONTAINS(POINT('ICRS', RAJ2000, DEJ2000), "
        f"CIRCLE('ICRS', {ra}, {dec}, {radius_deg})) = 1 "
        "AND W1mag < 17 ORDER BY W1mag ASC")
    rows = _tap_csv(VIZIER_TAP, adql_viz)
    return [{"ra": round(float(r["RAJ2000"]), 5),
             "dec": round(float(r["DEJ2000"]), 5),
             "w1": round(float(r["W1mag"]), 2)} for r in rows
            if r.get("W1mag")]


def main():
    for slug, ra, dec, fov in TARGETS:
        path = os.path.join(CACHE, slug, "enrich.json")
        if not os.path.exists(path):
            print(slug, "no enrich.json, skipping", flush=True)
            continue
        with open(path) as f:
            enrich = json.load(f)
        if enrich.get("wise"):
            print(slug, "wise already present:", len(enrich["wise"]),
                  flush=True)
            continue
        radius = (fov * 0.75) / 60.0  # cover the square frame + margin
        try:
            wise = wise_cone(ra, dec, radius)
        except Exception as e:  # noqa: BLE001
            print(slug, "WISE FAILED:", str(e)[:140], flush=True)
            continue
        enrich["wise"] = wise
        with open(path, "w") as f:
            json.dump(enrich, f, indent=1)
        print(slug, f"wise sources: {len(wise)}", flush=True)
    print("WISE_DONE", flush=True)


if __name__ == "__main__":
    main()
