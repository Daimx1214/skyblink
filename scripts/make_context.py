#!/usr/bin/env python3
"""Wide context render per target from its own best real SPHEREx exposure.

For each bundled target: pick the manifest frame whose exposure centre is
closest to the target, reproject that real Level-2 exposure onto a
1-degree-wide TAN view centred on the target (same asinh stretch family as
the blink frames), mark the target with a gold ring and outline the
5-arcmin blink field, and save apps/web/cache/<slug>/context.jpg.
"""
import json
import sys
from pathlib import Path

import numpy as np
from astropy.io import fits
from astropy.wcs import WCS
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from pipeline import render_frame  # noqa: E402

CACHE = ROOT / "data" / "cache"
WEB_CACHE = ROOT / "apps" / "web" / "cache"
W, H = 1200, 740
FOV_W_DEG = 1.0


def obsid_index():
    idx = {}
    for p in CACHE.glob("*.fits"):
        try:
            hdr = fits.getheader(p, "IMAGE")
        except Exception:
            continue
        oid = str(hdr.get("OBSID", "")).strip()
        if oid:
            idx.setdefault(oid, []).append(p)
    return idx


def target_wcs(ra, dec):
    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    w.wcs.cunit = ["deg", "deg"]
    w.wcs.crpix = [W / 2 + 0.5, H / 2 + 0.5]
    w.wcs.crval = [ra, dec]
    w.wcs.cdelt = [-FOV_W_DEG / W, (FOV_W_DEG * H / W) / H]
    return w


def main():
    idx = obsid_index()
    print(f"cache exposures indexed: {len(idx)}")
    for mpath in sorted(WEB_CACHE.glob("*/manifest.json")):
        slug = mpath.parent.name
        man = json.loads(mpath.read_text())
        if "ra" not in man or "dec" not in man:
            print(f"{slug}: no fixed ra/dec (moving target) — skipped")
            continue
        # Any cached exposure that covers the target works for context:
        # probe every indexed file on a coarse grid, keep the best coverage.
        small_w = WCS(naxis=2)
        tw = target_wcs(man["ra"], man["dec"])
        small_w.wcs.ctype = tw.wcs.ctype
        small_w.wcs.cunit = tw.wcs.cunit
        small_w.wcs.crpix = [75.5, 46.5]
        small_w.wcs.crval = tw.wcs.crval
        small_w.wcs.cdelt = [-FOV_W_DEG / 150, (FOV_W_DEG * H / W) / 92]
        best, best_cov, best_meta = None, 0.0, None
        for oid, paths in idx.items():
            for src in paths:
                try:
                    a2, m2 = render_frame(str(src), small_w, (92, 150))
                except Exception:
                    continue
                cov = float(np.isfinite(a2).mean())
                if cov > best_cov:
                    best, best_cov, best_meta = src, cov, m2
        if best is None or best_cov < 0.6:
            # S3 fallback: fetch the dossier's closest frame straight from
            # the public bucket (listing by pointing; stem = obs_id + D<n>).
            import s3fetch
            frame0 = min(man["frames"],
                         key=lambda f: f.get("center_dist_deg",
                                             f.get("centre_distance_deg", 9)))
            oid = frame0["obs_id"]
            pointing = "_".join(oid.split("_")[:2])
            got = None
            for tree in ("dr1", "qr3"):
                try:
                    keys = s3fetch.cached_listing(tree, pointing)
                except Exception:
                    continue
                key = next((k for k in keys
                            if ("/level2_" + oid + "D") in k
                            and k.endswith(".fits")), None)
                if key:
                    try:
                        got = s3fetch.fetch_image_hdu(key, oid)
                    except Exception:
                        got = None
                    if got:
                        break
            if got:
                arr, meta = render_frame(got, target_wcs(man["ra"], man["dec"]),
                                         (H, W))
                if float(np.isfinite(arr).mean()) > 0.6:
                    frame = frame0
                    print(f"{slug}: S3-fetched obs {oid}")
                else:
                    print(f"{slug}: S3 fetch did not cover — skipped")
                    continue
            else:
                print(f"{slug}: no coverage, S3 fetch failed — skipped")
                continue
        frame = {"obs_id": best_meta["obs_id"],
                 "center_dist_deg": round(0.0, 3)}
        arr, meta = render_frame(str(best), tw, (H, W))
        print(f"{slug}: using obs {best_meta['obs_id']} "
              f"coverage {best_cov:.2f}")
        lo = float(np.nanpercentile(arr, 40))
        hi = float(np.nanpercentile(arr, 99.7))
        arr = np.where(np.isfinite(arr), arr, lo)[::-1, :]
        x = np.clip((arr - lo) / max(hi - lo, 1e-12), 0, 1)
        x = np.arcsinh(x * 12.0) / np.arcsinh(12.0)
        img = Image.fromarray((x * 255).astype(np.uint8), mode="L").convert("RGB")
        d = ImageDraw.Draw(img)
        cx, cy = W / 2, H / 2
        d.ellipse([cx - 17, cy - 17, cx + 17, cy + 17], outline=(255, 200, 87), width=3)
        bw = (5 / 60) * W / FOV_W_DEG / 2
        bh = (5 / 60) * H / (FOV_W_DEG * H / W) / 2
        d.rectangle([cx - bw, cy - bh, cx + bw, cy + bh], outline=(45, 212, 191), width=2)
        out = mpath.parent / "context.jpg"
        img.save(out, quality=88)
        print(f"{slug}: obs {frame['obs_id']} dist {frame['center_dist_deg']}deg "
              f"-> {out.name} ({out.stat().st_size//1024} KB)")


if __name__ == "__main__":
    main()
