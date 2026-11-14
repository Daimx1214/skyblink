#!/usr/bin/env python3
"""Direct S3 access to the public SPHEREx archive bucket (nasa-irsa-spherex).

IRSA's SIA/cutout services flap under load; the same Level-2 products sit in
a public S3 bucket with a transparent key layout. We only need each file's
IMAGE HDU, so files are fetched with HTTP Range requests (header walk +
one data segment) instead of downloading the full ~65 MB MEF.
"""
import os
import re
import time

import requests

BUCKET = "https://nasa-irsa-spherex.s3.amazonaws.com"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "data", "cache")
os.makedirs(CACHE, exist_ok=True)
BLOCK = 2880


def list_keys(prefix, limit=100000):
    keys, token = [], None
    while len(keys) < limit:
        url = f"{BUCKET}/?list-type=2&prefix={prefix}&max-keys=1000"
        if token:
            url += f"&continuation-token={requests.utils.quote(token, safe='')}"
        r = requests.get(url, timeout=120)
        r.raise_for_status()
        keys += re.findall(r"<Key>([^<]+)</Key>", r.text)
        m = re.search(r"<NextContinuationToken>([^<]+)</NextContinuationToken>", r.text)
        if not m or "<IsTruncated>true</IsTruncated>" not in r.text:
            break
        token = m.group(1)
    return keys


def _get_range(url, start, end):
    last = None
    for i in range(6):
        try:
            r = requests.get(url, headers={"Range": f"bytes={start}-{end}"},
                             timeout=300)
            if r.status_code in (200, 206):
                return r.content
            last = f"HTTP {r.status_code}"
        except Exception as e:  # noqa: BLE001
            last = str(e)[:100]
        time.sleep(10 * (i + 1))
    raise RuntimeError(f"range fetch failed ({last}) {url} {start}-{end}")


def _parse_header(buf):
    """Return (cards dict, header_bytes) for the FITS header starting in buf
    (buf must contain the full header; fetch more if END not present)."""
    text = buf.decode("ascii", "replace")
    cards = {}
    end = None
    for i in range(0, len(text) - 79, 80):
        card = text[i:i + 80]
        key = card[:8].strip()
        if key == "END":
            end = i + 80
            break
        if "=" in card[8:10] or card[8:9] == "=":
            val = card[10:].split("/")[0].strip().strip("'").strip()
            cards[key] = val
    if end is None:
        return None, None
    hbytes = ((end + BLOCK - 1) // BLOCK) * BLOCK
    return cards, hbytes


def _data_size(cards):
    if cards.get("XTENSION", "").strip() == "" and "NAXIS" not in cards:
        return 0
    naxis = int(cards.get("NAXIS", 0))
    if naxis == 0:
        return 0
    n = abs(int(cards.get("BITPIX", 8))) // 8
    for i in range(1, naxis + 1):
        n *= int(cards.get(f"NAXIS{i}", 0))
    n = n * int(cards.get("GCOUNT", 1)) + int(cards.get("PCOUNT", 0))
    return ((n + BLOCK - 1) // BLOCK) * BLOCK


def fetch_image_hdu(key, tag):
    """Fetch only the PRIMARY + IMAGE segments of an S3 FITS file.
    Returns a local mini-FITS path (cached)."""
    out = os.path.join(CACHE, f"s3v2_{tag}.fits")
    if os.path.exists(out) and os.path.getsize(out) > 1_000_000:
        return out
    url = f"{BUCKET}/{key}"
    segments = []
    offset = 0
    want = {"IMAGE", "WCS-WAVE"}
    got = set()
    for _ in range(12):  # walk HDUs until IMAGE + WCS-WAVE are captured
        buf = _get_range(url, offset, offset + BLOCK * 40 - 1)
        cards, hbytes = _parse_header(buf)
        while cards is None:  # header longer than the fetched window
            buf = _get_range(url, offset, offset + len(buf) + BLOCK * 40 - 1)
            cards, hbytes = _parse_header(buf)
        dsize = _data_size(cards)
        extname = cards.get("EXTNAME", "").strip()
        if extname in want:
            data = _get_range(url, offset + hbytes,
                              offset + hbytes + dsize - 1) if dsize else b""
            segments.append(buf[:hbytes] + data)
            got.add(extname)
            if got == want:
                break
            offset += hbytes + dsize
            continue
        if not segments:
            # PRIMARY (empty): keep header only.
            segments.append(buf[:hbytes])
            offset += hbytes + dsize
            continue
        # Any other extension: skip it entirely (not copied to the mini-FITS).
        offset += hbytes + dsize
    blob = b"".join(segments)
    if len(blob) < 1_000_000:
        raise RuntimeError(f"mini-FITS too small ({len(blob)} B) for {key}")
    with open(out, "wb") as f:
        f.write(blob)
    return out
