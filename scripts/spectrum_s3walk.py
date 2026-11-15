#!/usr/bin/env python3
"""Full spectrum harvest from S3 by walking a pointing's scan sequences.

A SPHEREx pointing scans a sky strip sequence by sequence; a fixed target
is imaged by a contiguous run of sequences, in several detectors and at
many wavelengths (the LVF wavelength at the target's pixel changes as the
scan steps). Starting from the sequence of a known dossier frame, walk
outward in both directions until the coverage run ends, probing each
file cheaply (celestial WCS only) and measuring covering files with the
exact aperture math of spectrum_lib.frame_spectrum_point.

Points are checkpointed to data/s3walk-<slug>.json as they arrive, and a
spectrum.json (site schema) is written whenever the binned channel count
improves on the existing file.
"""
import argparse
import io
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.wcs import WCS

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s3fetch  # noqa: E402
from s3fetch import BUCKET, cached_listing  # noqa: E402
from spectrum_cube import open_extension  # noqa: E402
from spectrum_lib import bin_points, cache_pass  # noqa: E402
from spectrum_s3point import fetch_header  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def probe(key, ra, dec):
    """(wave, flux) if this exposure covers the position, else None.
    Cheap path: IMAGE header + celestial WCS only; the WCS-WAVE table and
    image rows are fetched solely for covering files."""
    url = f"{BUCKET}/{key}"
    cards, hbytes, raw = fetch_header(url, 0)  # PRIMARY (empty)
    offset = hbytes + s3fetch._data_size(cards)
    cards, hbytes, iraw = fetch_header(url, offset)
    if cards.get("EXTNAME", "").strip() != "IMAGE":
        # walk forward until IMAGE
        for _ in range(4):
            offset += hbytes + s3fetch._data_size(cards)
            cards, hbytes, iraw = fetch_header(url, offset)
            if cards.get("EXTNAME", "").strip() == "IMAGE":
                break
        else:
            return None
    istart = offset + hbytes
    hdr = fits.Header.fromstring(iraw.decode("ascii"), sep="")
    wcel = WCS(hdr, naxis=2)
    px, py = wcel.world_to_pixel(SkyCoord(ra, dec, unit="deg"))
    px, py = float(px), float(py)
    wdt, hgt = int(cards["NAXIS1"]), int(cards["NAXIS2"])
    if not (8 < px < wdt - 8 and 8 < py < hgt - 8):
        return None
    # covering: fetch WCS-WAVE for the wavelength at the pixel
    offset = istart + s3fetch._data_size(cards)
    wave = None
    for _ in range(8):
        c2, hb2, raw2 = fetch_header(url, offset)
        ds2 = s3fetch._data_size(c2)
        if c2.get("EXTNAME", "").strip() == "WCS-WAVE":
            data = s3fetch._get_range(url, offset + hb2,
                                      offset + hb2 + ds2 - 1)
            with open_extension(raw2, data) as hdul:
                ww = WCS(hdr, fobj=hdul, key="W")
                world = ww.pixel_to_world(px, py)
                cands = (world if isinstance(world, (list, tuple))
                         else [world])
                for x in cands:
                    spec = getattr(x, "spectral", None)
                    if spec is not None:
                        wave = float(np.ravel(spec.to(u.um).value)[0])
                        break
                    try:
                        wave = float(np.ravel(x.to(u.um).value)[0])
                        break
                    except Exception:  # noqa: BLE001
                        continue
            break
        offset += hb2 + ds2
    if wave is None or not (0.7 < wave < 5.2):
        return None
    cd = wcel.proj_plane_pixel_scales()
    factor = 23.5045 * float(cd[0].to(u.arcsec).value) ** 2 / 1000.0
    row0 = int(np.floor(py)) - 8
    row_bytes = wdt * 4
    buf = s3fetch._get_range(url, istart + row0 * row_bytes,
                             istart + (row0 + 17) * row_bytes - 1)
    data = np.frombuffer(buf, dtype=">f4").astype(np.float64).reshape(
        17, wdt)
    yy, xx = np.mgrid[0:17, 0:wdt]
    r2 = (xx - px) ** 2 + (yy - (py - row0)) ** 2
    ap = r2 <= 2.0 ** 2
    ann = (r2 > 5.0 ** 2) & (r2 <= 8.0 ** 2)
    bg = np.nanmedian(data[ann])
    flux = float(np.nansum((data - bg)[ap]) * factor)
    return wave, flux


def write_spectrum(slug, name, pts):
    waves, fluxes = bin_points(pts)
    out = os.path.join(ROOT, "apps", "web", "cache", slug, "spectrum.json")
    existing = 0
    if os.path.exists(out):
        existing = len(json.load(open(out)).get("wave_um", []))
    if len(waves) >= 6 and len(waves) > existing:
        payload = {
            "target": name,
            "source": f"SPHEREx DR1+QR3 individual exposures via IRSA "
                      f"({len(pts)} exposures, {len(waves)} distinct "
                      f"channels)",
            "wave_um": waves,
            "flux_mjy": fluxes,
            "note": "Each point is one real SPHEREx exposure: wavelength "
                    "from that frame's spectral WCS at the target's pixel, "
                    "flux from aperture photometry (r=2 px, annulus "
                    "background), median-combined where visits repeat a "
                    "channel. SPHEREx has 102 channels in total; these are "
                    "the channels the archive's visits have actually "
                    "sampled at this position so far — the count grows as "
                    "the survey revisits the field. Zodiacal light is "
                    "modelled in the archive products, not subtracted from "
                    "Level-2 data, so read the broad shape with care.",
        }
        with open(out, "w") as f:
            json.dump(payload, f, indent=1)
        print(f"{slug}: spectrum.json -> {len(waves)} channels",
              flush=True)
    return waves


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", required=True)
    ap.add_argument("--ra", type=float, required=True)
    ap.add_argument("--dec", type=float, required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--max-away", type=int, default=260)
    a = ap.parse_args()

    man = json.load(open(os.path.join(
        ROOT, "apps", "web", "cache", a.slug, "manifest.json")))
    frames = man["frames"]
    ckpt_path = os.path.join(ROOT, "data", f"s3walk-{a.slug}.json")
    pts = [tuple(p) for p in json.load(open(ckpt_path))] \
        if os.path.exists(ckpt_path) else []
    if not pts:
        pts = list(cache_pass(a.ra, a.dec, log=lambda *x: None))
    done_seqs = set()
    print(f"{a.slug}: start points {len(pts)}", flush=True)

    def save_ckpt():
        with open(ckpt_path, "w") as f:
            json.dump(pts, f)

    for fr in frames:
        oid = fr["obs_id"]
        parts = oid.split("_")
        pointing = "_".join(parts[:2])
        anchor_seq = int(parts[3])
        tree = None
        keys = None
        for t in ("dr1", "qr3"):
            try:
                cand = cached_listing(t, pointing)
            except Exception:  # noqa: BLE001
                continue
            if any(f"/level2_{oid.rsplit('_', 1)[0]}_" in k for k in cand):
                tree, keys = t, cand
                break
        if keys is None:
            print(f"{a.slug}: no listing for {pointing}", flush=True)
            continue
        seq_files = {}
        for k in keys:
            fn = k.split("/")[-1]
            if not fn.startswith(f"level2_{pointing}_"):
                continue
            stem = fn[len("level2_"):].split("_spx")[0]
            sp = stem.split("_")
            try:
                seq_i, tail = int(sp[2]), sp[3]
                ch_s, det_s = tail.split("D")
                ch_i, det_i = int(ch_s), int(det_s)
            except Exception:  # noqa: BLE001
                continue
            seq_files.setdefault(seq_i, {})[(ch_i, det_i)] = k
        print(f"{a.slug}: {pointing} ({tree}): {len(seq_files)} sequences, "
              f"anchor {anchor_seq}", flush=True)
        last_det = fr["detector"]
        empty_run = 0
        order = [anchor_seq] + [anchor_seq + d for d in range(1, a.max_away)]
        order += [anchor_seq - d for d in range(1, a.max_away)]
        for seq_i in order:
            if seq_i in done_seqs or seq_i not in seq_files:
                continue
            done_seqs.add(seq_i)
            files = seq_files[seq_i]
            cand = sorted(files.items(),
                          key=lambda kv: (abs(kv[0][1] - last_det),
                                          kv[0][0]))
            found = []
            with ThreadPoolExecutor(max_workers=4) as ex:
                futs = {ex.submit(probe, k, a.ra, a.dec): det
                        for (ch, det), k in cand}
                for fut, det in futs.items():
                    try:
                        got = fut.result()
                    except Exception:  # noqa: BLE001
                        got = None
                    if got:
                        found.append(got)
                        last_det = det
            if found:
                pts.extend(found)
                empty_run = 0
                save_ckpt()
                w, _ = bin_points(pts), None
                print(f"{a.slug}: seq {seq_i}: +{len(found)} pts "
                      f"(total {len(pts)}, channels "
                      f"{len(bin_points(pts)[0])})", flush=True)
            else:
                empty_run += 1
                if empty_run >= 14 and seq_i != anchor_seq:
                    # coverage run over in this direction; the order list
                    # visits +d then -d, so reset between directions
                    if seq_i > anchor_seq and anchor_seq - 1 in done_seqs:
                        break
                    if seq_i > anchor_seq:
                        empty_run = 0
        write_spectrum(a.slug, a.name, pts)
    waves = write_spectrum(a.slug, a.name, pts)
    print(f"{a.slug}: FINAL {len(pts)} points, {len(waves)} channels",
          flush=True)
    print("S3WALK_DONE", flush=True)


if __name__ == "__main__":
    main()
