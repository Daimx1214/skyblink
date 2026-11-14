#!/usr/bin/env python3
"""Demo video v3 (<=30 s): same timeline/story as v2, composed at 1920x1080.

  0-3.5s  title card
  3.5-9s  home page (slow push-in on the hero + explorer)
  9-17s   Barnard's Star blinking through its real epochs
  17-23s  dossier page with the Gaia overlay + band chart
  23-27s  Case Files page
  27-30s  end card
Composed with PIL from real 2560x1440 screenshots + real frames, piped to
ffmpeg (H.264, CRF 16). All v2 coordinates/font sizes scaled by S = 1.5.
The Barnard frames are 97x97 native archive cutouts, shown NEAREST-neighbour
(same treatment as v2) - no detail is invented.
"""
import json
import os
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "apps", "web")
QA = os.environ.get("SB_QA", "/tmp/qa3")
W, H, FPS = 1920, 1080, 30
S = W / 1280.0  # 1.5 scale vs v2
VOID = (4, 6, 15); TEAL = (45, 212, 191); VIOLET = (139, 124, 246)
AMBER = (255, 200, 87); STAR = (234, 240, 255); MIST = (159, 176, 208)
FONT_CANDIDATES = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                   "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
MONO_CANDIDATES = ["/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"]


def sc(v):
    return int(round(v * S))


def font(size, mono=False):
    for p in (MONO_CANDIDATES if mono else FONT_CANDIDATES):
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def canvas():
    return Image.new("RGB", (W, H), VOID)


def text(img, xy, s, size=34, color=STAR, mono=False):
    ImageDraw.Draw(img).text((sc(xy[0]), sc(xy[1])), s, font=font(sc(size), mono), fill=color)
    return img


def title_card():
    img = canvas()
    text(img, (90, 240), "SkyBlink", 96, TEAL)
    text(img, (92, 350), "Watch the sky change.", 44, STAR)
    text(img, (92, 420), "Real NASA SPHEREx images, blinked across time.", 28, MIST)
    text(img, (92, 620), "NASA Space Apps Challenge 2026 - Planet X and SPHEREx", 22, VIOLET, mono=True)
    return img


def end_card():
    img = canvas()
    text(img, (90, 250), "Six pages. Five targets. One comet.", 50, STAR)
    text(img, (92, 335), "Zero simulated data.", 50, TEAL)
    text(img, (92, 450), "Team Sohan Halwa - Daim Ali & Ali Abdullah", 28, MIST)
    text(img, (92, 500), "daimx1214.github.io/skyblink", 26, AMBER, mono=True)
    text(img, (92, 620), "Data: SPHEREx via IRSA - ESA Gaia - CDS SIMBAD / Aladin", 20, MIST, mono=True)
    return img


def push_in(img, seconds, z0=1.0, z1=1.12, cx=0.5, cy=0.42):
    """Slow zoom into a screenshot, output frames (crop in source coords)."""
    iw, ih = img.size
    out = []
    n = int(seconds * FPS)
    for k in range(n):
        z = z0 + (z1 - z0) * (k / max(n - 1, 1))
        cw, ch = int(iw / z), int(ih / z)
        x0 = int(min(max(cx * iw - cw / 2, 0), iw - cw))
        y0 = int(min(max(cy * ih - ch / 2, 0), ih - ch))
        crop = img.crop((x0, y0, x0 + cw, y0 + ch)).resize((W, H), Image.LANCZOS)
        out.append(crop)
    return out


def caption(img, s):
    d = ImageDraw.Draw(img)
    d.rectangle([0, H - sc(64), W, H], fill=(4, 6, 15))
    d.text((sc(36), H - sc(48)), s, font=font(sc(26), mono=True), fill=AMBER)
    return img


def load_set(slug):
    d = os.path.join(WEB, "cache", slug)
    with open(os.path.join(d, "manifest.json")) as f:
        man = json.load(f)
    imgs = [Image.open(os.path.join(d, fr["png"])).convert("L") for fr in man["frames"]]
    return man, imgs


def blink_segment(seconds):
    man, imgs = load_set("barnards-star")
    order = list(range(len(imgs))) + list(range(len(imgs) - 2, 0, -1))
    per = max(int(seconds * FPS / len(order)), 3)
    out = []
    side = sc(560)
    for i in order:
        fr = man["frames"][i]
        base = canvas()
        im = imgs[i].resize((side, side), Image.NEAREST)
        base.paste(im, (W // 2 - side // 2, sc(60)))
        d = ImageDraw.Draw(base)
        d.text((sc(40), sc(640)), f"Barnard's Star - {fr['release']} - {fr['date']} - detector {fr['detector']}",
               font=font(sc(24), mono=True), fill=AMBER)
        out.extend([base] * per)
    return out


def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "docs", "skyblink-demo.mp4")
    seq = []
    seq.extend([title_card()] * int(3.5 * FPS))
    home = Image.open(os.path.join(QA, "p_index2.png")).convert("RGB")
    seq.extend([caption(f, "The blink explorer - real SPHEREx epochs") for f in push_in(home, 5.5)])
    seq.extend(blink_segment(7.5))
    dossier = Image.open(os.path.join(QA, "p_target2.png")).convert("RGB")
    seq.extend([caption(f, "Dossiers - Gaia overlay, band chart, quality data") for f in push_in(dossier, 5.5, cy=0.40)])
    cases = Image.open(os.path.join(QA, "p_cases.png")).convert("RGB")
    seq.extend([caption(f, "Case Files - a measured proper motion, with error bars") for f in push_in(cases, 4, cy=0.30)])
    seq.extend([end_card()] * int(3 * FPS))
    print(f"{len(seq)} frames = {len(seq)/FPS:.1f}s")
    cmd = ["ffmpeg", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "16",
           "-preset", "slow", "-movflags", "+faststart", out_path]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for img in seq:
        p.stdin.write(img.tobytes())
    p.stdin.close(); p.wait()
    print("wrote", out_path, os.path.getsize(out_path) // 1024, "KB")


if __name__ == "__main__":
    main()
