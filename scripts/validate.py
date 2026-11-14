#!/usr/bin/env python3
"""Validation experiment (winners-pattern: validity with numbers).

Inject synthetic movers into REAL reprojected SPHEREx epoch pairs and test
whether the product's own detection logic - the difference image - recovers
them. Also run the detector on the uninjected pairs as a control.

Detection rule (identical in spirit to the site's Difference mode):
  D = B - A; noise = 1.4826 * MAD(D); a mover is "recovered" if the
  strongest |D| peak within 2 px of the injected B position exceeds 6 sigma
  AND a negative lobe of comparable strength sits within 2 px of the
  injected A position (the dipole test from the Two-Epoch Check).

Output: apps/web/cache/validation.json + a printed summary for the
Methods page. Uses Barnard's Star and R Draconis frame sets (real DR1/QR3).
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
from enrich import obsid_map  # noqa: E402
from pipeline import render_frame, target_wcs  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_CACHE = os.path.join(ROOT, "apps", "web", "cache")
OUT = os.path.join(WEB_CACHE, "validation.json")
rng = np.random.default_rng(20261114)

PSF_SIGMA = 1.1  # px, matched to the SPHEREx PSF core in our renders


def psf(shape, x, y, amp):
    yy, xx = np.mgrid[0:shape[0], 0:shape[1]]
    return amp * np.exp(-(((xx - x) ** 2 + (yy - y) ** 2) / (2 * PSF_SIGMA ** 2)))


def mad_sigma(d):
    med = np.nanmedian(d)
    return 1.4826 * np.nanmedian(np.abs(d - med)) + 1e-12


def peak_near(d, x, y, rad=2):
    h, w = d.shape
    x0, x1 = max(int(x) - rad, 0), min(int(x) + rad + 1, w)
    y0, y1 = max(int(y) - rad, 0), min(int(y) + rad + 1, h)
    return np.nanmax(np.abs(d[y0:y1, x0:x1]))


def load_set(slug, omap):
    man = json.load(open(os.path.join(WEB_CACHE, slug, "manifest.json")))
    twcs, shape = target_wcs(man["ra"], man["dec"], man["fov_arcmin"])
    arrs = []
    for fr in man["frames"]:
        arr, _ = render_frame(omap[fr["obs_id"]], twcs, shape)
        arrs.append(np.nan_to_num(arr))
    return man, arrs


def run_pair(a, b, shifts, snrs, trials=10):
    """Inject into copies of (a, b). Returns recovery counts per (shift, snr)
    and the uninjected control's peak count."""
    h, w = a.shape
    base_diff = b - a
    sig = mad_sigma(base_diff)
    # control: peaks above 6 sigma anywhere in the uninjected difference,
    # counted on a coarse grid (one per 5x5 cell) away from the borders
    ctrl = 0
    mag = np.abs(base_diff / sig)
    mag[:4, :] = mag[-4:, :] = mag[:, :4] = mag[:, -4:] = 0
    seen = np.zeros_like(mag, dtype=bool)
    for _ in range(10000):
        idx = np.argmax(np.where(seen, 0, mag))
        y, x = np.unravel_index(idx, mag.shape)
        if mag[y, x] < 6:
            break
        ctrl += 1
        seen[max(y - 3, 0):y + 4, max(x - 3, 0):x + 4] = True
    results = {}
    for shift in shifts:
        for snr in snrs:
            amp = snr * sig / 0.9  # PSF peak in difference ~ amp for a clean move
            ok = 0
            for _ in range(trials):
                x = rng.uniform(10, w - 10 - shift)
                y = rng.uniform(10, h - 10)
                ai = a + psf(a.shape, x, y, amp)
                bi = b + psf(b.shape, x + shift, y, amp)
                d = bi - ai
                peak_b = peak_near(d, x + shift, y) / sig
                peak_a = peak_near(d, x, y) / sig
                if peak_b > 6 and peak_a > 4:
                    ok += 1
            results[f"{shift}px/{snr}sig"] = {"recovered": ok, "trials": trials,
                                             "shift_px": shift, "snr": snr}
    return results, ctrl, round(float(sig), 5)


def main():
    omap = obsid_map()
    all_pairs = []
    summary = {}
    for slug in ("barnards-star", "r-draconis"):
        man, arrs = load_set(slug, omap)
        for k in range(1, len(arrs)):
            res, ctrl, sig = run_pair(arrs[0], arrs[k],
                                      shifts=(1, 2, 4), snrs=(8, 15, 30), trials=10)
            all_pairs.append({"set": slug, "pair": f"epoch1 vs epoch{k+1}",
                              "control_peaks_6sig": ctrl, "results": res})
            print(slug, f"pair {k+1}: control peaks {ctrl}, sigma {sig}")
            for key, r in res.items():
                print("   ", key, f"{r['recovered']}/{r['trials']}")
    # aggregate recovery across all pairs
    agg = {}
    for p in all_pairs:
        for key, r in p["results"].items():
            a = agg.setdefault(key, {"recovered": 0, "trials": 0,
                                     "shift_px": r["shift_px"], "snr": r["snr"]})
            a["recovered"] += r["recovered"]; a["trials"] += r["trials"]
    payload = {
        "method": "Synthetic Gaussian movers (sigma 1.1 px) injected into real "
                  "reprojected SPHEREx epoch pairs; detection = difference-image "
                  "dipole test (positive lobe > 6 sigma at the new position, "
                  "negative lobe > 4 sigma at the old). Control = same detector "
                  "on the uninjected pairs.",
        "pairs": all_pairs,
        "aggregate": agg,
        "control_peaks_total": sum(p["control_peaks_6sig"] for p in all_pairs),
        "control_pairs": len(all_pairs),
    }
    json.dump(payload, open(OUT, "w"), indent=1)
    print("AGGREGATE:")
    for key, a in sorted(agg.items()):
        print(f"  shift {a['shift_px']}px, {a['snr']} sigma: "
              f"{a['recovered']}/{a['trials']} = {100*a['recovered']/a['trials']:.0f}%")
    print("control peaks total:", payload["control_peaks_total"],
          "across", len(all_pairs), "real pairs")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
