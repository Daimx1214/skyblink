#!/usr/bin/env python3
"""Spectrum at a target position from the SPHEREx DR1 all-sky spectral cube
on the public S3 bucket (dr1/hips5_cube/.../Npix<ipix>_cube.fits).

The cube route needs no IRSA query service: one HEALPix order-5 cube file
holds all 102 channels at every position it covers. We Range-fetch only the
target's pixel column (102 planes x a 3-row strip), take the 3x3 median per
plane, and convert MJy/sr to mJy with the cube pixel's solid angle — the
same conversion the exposure-based spectra use. Writes
apps/web/cache/<slug>/spectrum.json in the site's schema.
"""
import io
import json
import os
import sys

import numpy as np
import requests
from astropy.io import fits
from astropy_healpix import HEALPix
import astropy.units as u

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_CACHE = os.path.join(ROOT, "apps", "web", "cache")
BUCKET = "https://nasa-irsa-spherex.s3.amazonaws.com"
CUBE_PREFIX = "dr1/hips5_cube/hips_20261026/Norder5"
TARGETS = [
    ("barnards-star", "Barnard's Star", 269.4464, 4.7671),
    ("wise-0855", "WISE 0855", 133.7951, -7.2451),
    ("epsilon-indi-b", "Epsilon Indi B", 331.0438, -56.7828),
    ("rw-aurigae", "RW Aurigae", 76.9565, 30.4014),
    ("r-draconis", "R Draconis", 248.1675, 66.7550),
]
S = requests.Session()


def get_range(url, a, b):
    r = S.get(url, headers={"Range": f"bytes={a}-{b}"}, timeout=90)
    r.raise_for_status()
    return r.content


def open_extension(header_bytes, raw):
    """Open a lone extension (RAW header bytes + data) as a one-HDU FITS.
    Raw bytes, never re-serialized: astropy header round-trips can mangle
    TDIM/CONTINUE cards that wcslib's -TAB machinery depends on."""
    _ph = fits.Header()
    _ph["SIMPLE"] = True
    _ph["BITPIX"] = 8
    _ph["NAXIS"] = 0
    _ph["EXTEND"] = True
    prim = _ph.tostring(sep="", endcard=True, padding=False)
    prim += " " * ((2880 - len(prim) % 2880) % 2880)
    blob = prim.encode("ascii") + header_bytes + raw
    blob += b"\x00" * ((2880 - len(blob) % 2880) % 2880)
    return fits.open(io.BytesIO(blob))


def read_header(url, pos):
    buf = b""
    while True:
        buf += get_range(url, pos + len(buf), pos + len(buf) + 2879)
        for i in range(0, len(buf) - 79, 80):
            if buf[i:i + 8] == b"END     ":
                total = ((i // 2880) + 1) * 2880
                return fits.Header.fromstring(buf[:total].decode("ascii"),
                                              sep=""), total
        if len(buf) > 2880 * 40:
            raise RuntimeError("header too long")


def walk(url):
    """Return {extname: (header, data_start, data_size)} for all HDUs."""
    out = {}
    pos = 0
    for _ in range(8):
        try:
            hdr, hlen = read_header(url, pos)
        except Exception:
            break  # past the last HDU
        naxis = hdr.get("NAXIS", 0)
        if hdr.get("XTENSION", "").strip() == "BINTABLE":
            dsize = hdr["NAXIS1"] * hdr["NAXIS2"]
        else:
            dsize = abs(hdr.get("BITPIX", 8)) // 8
            n = 1
            for i in range(1, naxis + 1):
                n *= hdr.get(f"NAXIS{i}", 0)
            dsize *= n if naxis else 0
        name = hdr.get("EXTNAME", "PRIMARY")
        out[name] = (hdr, pos + hlen, dsize, pos)
        pos += hlen + ((dsize + 2879) // 2880) * 2880
        if naxis == 0 and name != "PRIMARY":
            break
    return out


def cube_spectrum(slug, name, ra, dec):
    hp = HEALPix(nside=32, order="nested")
    ipix = int(hp.lonlat_to_healpix(ra * u.deg, dec * u.deg))
    d = (ipix // 10000) * 10000
    url = f"{BUCKET}/{CUBE_PREFIX}/Dir{d}/Npix{ipix}_cube.fits"
    hdus = walk(url)
    ihdr, istart, _, _ = hdus["IMAGE"]
    nhdr, nstart, _, _ = hdus["NHITS"]
    from astropy.wcs import WCS
    # The -TAB spectral axis needs its lookup table attached: fetch the
    # WCS-WAVE extension (header + data) and offer it as the WCS file obj.
    _wh, _wd, _ws, _whs = hdus["WCS-WAVE"]
    raw = get_range(url, _wd, _wd + _ws - 1)
    whdr_raw = get_range(url, _whs, _wd - 1)
    with open_extension(whdr_raw, raw) as _f:
        w = WCS(ihdr, fobj=_f)
        x_f, y_f, _z = w.world_to_pixel_values(ra, dec, 1.0)
    x, y = int(round(float(x_f))), int(round(float(y_f)))
    print(f"{slug}: ipix {ipix} pixel ({x}, {y})", flush=True)
    # Wavelength per plane from the SPECTRAL_CHANNELS table.
    thdr, tstart, tsize, _ths = hdus["SPECTRAL_CHANNELS"]
    raw = get_range(url, tstart, tstart + tsize - 1)
    thdr_raw = get_range(url, _ths, tstart - 1)
    with open_extension(thdr_raw, raw) as f:
        tab = f[1].data
        cols = [c.lower() for c in tab.names]
        wcol = next(c for c in tab.names
                    if "wave" in c.lower() and "err" not in c.lower()
                    and "width" not in c.lower() and "bw" not in c.lower())
        waves = np.array([float(v) for v in tab[wcol]])
    print(f"{slug}: wavelength column {wcol}: {len(waves)} rows, "
          f"{waves.min():.3f}..{waves.max():.3f} um", flush=True)
    nx = ihdr["NAXIS1"]
    row_bytes = nx * 4
    pixscale = float(np.sqrt(4 * np.pi / (12 * 32 ** 2 * nx ** 2))
                     * (180 / np.pi) * 3600)
    waves_out, flux_out, hits_out = [], [], []
    for lam in range(102):
        base = istart + ((lam * nx + (y - 1)) * nx) * 4
        strip = get_range(url, base, base + 3 * row_bytes - 1)
        a = np.frombuffer(strip, dtype=">f4").reshape(3, nx)
        patch = a[:, x - 1:x + 2]
        vals = patch[np.isfinite(patch)]
        nbase = nstart + ((lam * nx + (y - 1)) * nx) * 4
        nstrip = get_range(url, nbase, nbase + 3 * row_bytes - 1)
        na = np.frombuffer(nstrip, dtype=">i4").reshape(3, nx)
        nvals = na[:, x - 1:x + 2]
        hits = int(np.median(nvals)) if nvals.size else 0
        if vals.size < 5 or hits <= 0:
            continue
        mjy_sr = float(np.median(vals))
        flux = mjy_sr * 23.5045 * pixscale ** 2 / 1000.0
        waves_out.append(round(float(waves[lam]), 3))
        flux_out.append(round(flux, 3))
        hits_out.append(hits)
    print(f"{slug}: {len(waves_out)} channels with signal, "
          f"hits median {int(np.median(hits_out)) if hits_out else 0}",
          flush=True)
    return {
        "target": name,
        "source": ("SPHEREx DR1 all-sky spectral cube via IRSA S3 "
                   f"({len(waves_out)} of 102 channels with signal at this "
                   "position)"),
        "wave_um": waves_out,
        "flux_mjy": flux_out,
        "note": ("Sampled from the DR1 spectral cube (DOI 10.26131/IRSA679): "
                 "the 3x3-pixel median surface brightness at the target "
                 "position in each channel, converted with the cube pixel "
                 "solid angle (12.9 arcsec pixels). The cube stacks DR1 "
                 "visits only; channels 50-51 are the blank dichroic gap."),
    }


def main():
    only = sys.argv[1:] or None
    for slug, name, ra, dec in TARGETS:
        if only and slug not in only:
            continue
        try:
            sp = cube_spectrum(slug, name, ra, dec)
        except Exception as e:  # noqa: BLE001
            print(slug, "CUBE SPECTRUM FAILED:", str(e)[:200], flush=True)
            continue
        if len(sp["wave_um"]) < 6:
            print(slug, "too few channels, not publishing", flush=True)
            continue
        out = os.path.join(WEB_CACHE, slug, "spectrum.json")
        if slug == "barnards-star":
            out = os.path.join(WEB_CACHE, slug, "spectrum-cube.json")
            print(slug, "written to spectrum-cube.json for comparison",
                  flush=True)
        with open(out, "w") as f:
            json.dump(sp, f, indent=1)
        print(slug, "->", out, flush=True)
    print("CUBE_SPECTRUM_DONE", flush=True)


if __name__ == "__main__":
    main()
