#!/usr/bin/env python3
"""SkyBlink proof step 1: SIA discovery against IRSA for one target.

Queries the DR1 + QR3 SIA collections around a position and prints the
observation rows (release, obs id, date, detector/bandpass, access URL).
This is the exact route the tutorial notebooks document:
  Irsa.query_sia(pos=(coord, radius), collection=[...])
"""
import sys
from astropy.coordinates import SkyCoord
import astropy.units as u
from astroquery.ipac.irsa import Irsa

COLLECTIONS = ["spherex_dr1", "spherex_dr1_deep", "spherex_qr3", "spherex_qr3_deep"]


def main(ra: float, dec: float, radius_arcmin: float = 6.0):
    coord = SkyCoord(ra, dec, unit="deg")
    print(f"Querying SIA at RA={ra} Dec={dec} r={radius_arcmin}' ...", flush=True)
    res = Irsa.query_sia(pos=(coord, radius_arcmin * u.arcmin), collection=COLLECTIONS)
    print(f"Rows returned: {len(res)}")
    if len(res) == 0:
        return
    cols = [c for c in ("obs_collection", "obs_id", "t_min", "t_max",
                        "energy_bandpassname", "access_url") if c in res.colnames]
    print("Columns used:", cols)
    print("All columns:", res.colnames)
    show = res[cols] if cols else res
    show.sort("t_min")
    for row in show:
        print(" | ".join(str(row[c]) for c in cols))
    # epoch span summary
    if "t_min" in res.colnames:
        print(f"\nEpoch span (MJD): {min(res['t_min']):.2f} .. {max(res['t_min']):.2f}")


if __name__ == "__main__":
    ra = float(sys.argv[1]) if len(sys.argv) > 1 else 269.4521   # Barnard's Star
    dec = float(sys.argv[2]) if len(sys.argv) > 2 else 4.6934
    main(ra, dec)
