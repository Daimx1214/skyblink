#!/usr/bin/env python3
"""Assemble the <=30s demo video from the real rendered frames.

Structure (30 s @ 30 fps = 900 frames, 1280x720):
  0-4s   title card
  4-13s  Barnard's Star blinking through its epochs (labels burned in)
  13-19s difference view (latest - earliest) with caption
  19-26s the other targets, one blink pair each
  26-30s end card
Frames are composed with PIL and piped to ffmpeg (libx264, silent).
"""
import json
import os
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "apps", "web")
W, H, FPS = 1280, 720, 30
VOID = (4, 6, 15); PANEL = (11, 17, 32); TEAL = (45, 212, 191)
VIOLET = (139, 124, 246); AMBER = (255, 200, 87); STAR = (234, 240, 255)
MIST = (159, 176, 208)

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]
MONO_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
]


def font(size, mono=False):
    for p in (MONO_CANDIDATES if mono else FONT_CANDIDATES):
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def load_set(slug):
    d = os.path.join(WEB, "cache", slug)
    with open(os.path.join(d, "manifest.json")) as f:
        man = json.load(f)
    imgs = [Image.open(os.path.join(d, fr["png"])).convert("L") for fr in man["frames"]]
    return man, imgs


def canvas():
    return Image.new("RGB", (W, H), VOID)


def centered(img, cx, cy, size):
    im = img.resize((size, size), Image.NEAREST)
    base = canvas()
    base.paste(im, (cx - size // 2, cy - size // 2))
    return base


def text(img, xy, s, size=34, color=STAR, mono=False, anchor="la"):
    d = ImageDraw.Draw(img)
    d.text(xy, s, font=font(size, mono), fill=color, anchor=anchor)
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
    text(img, (90, 260), "Five targets. One comet.", 52, STAR)
    text(img, (92, 340), "Zero simulated data.", 52, TEAL)
    text(img, (92, 460), "Team Sohan Halwa - Daim Ali & Ali Abdullah", 28, MIST)
    text(img, (92, 620), "Data: SPHEREx via IRSA - ESA Gaia - CDS SIMBAD", 20, MIST, mono=True)
    return img


def label_frame(img, title, sub):
    text(img, (40, 26), title, 34, STAR)
    text(img, (42, 72), sub, 21, AMBER, mono=True)
    return img


def diff_image(a, b):
    da = np.asarray(a).astype(np.int16); db = np.asarray(b).astype(np.int16)
    out = np.clip((db - da) * 1.6 + 128, 0, 255).astype(np.uint8)
    return Image.fromarray(out, mode="L").convert("RGB")


def build_sequence():
    seq = []  # list of PIL images (one per output frame)
    def hold(img, seconds):
        seq.extend([img] * int(seconds * FPS))
    def blink(man, imgs, seconds, title):
        per = seconds / max(len(imgs) * 2 - 1, 1)
        order = list(range(len(imgs))) + list(range(len(imgs) - 2, 0, -1))
        for i in order:
            fr = man["frames"][i]
            img = centered(imgs[i], W // 2, H // 2 + 20, 560)
            img = label_frame(img, title, f"{fr['release']} - {fr['date']} - detector {fr['detector']} - obs {fr['obs_id']}")
            seq.extend([img] * max(int(per * FPS), 4))

    hold(title_card(), 4)
    man, imgs = load_set("barnards-star")
    blink(man, imgs, 9, "Barnard's Star - the fastest-moving star")
    d = diff_image(imgs[0], imgs[-1])
    img = centered(d, W // 2, H // 2 + 20, 560)
    img = label_frame(img, "Difference view", f"{man['frames'][-1]['date']} minus {man['frames'][0]['date']} - movers leave a dipole")
    hold(img, 6)
    for slug, title in (("wise-0855", "WISE 0855 - the coldest brown dwarf"),
                        ("epsilon-indi-b", "Epsilon Indi B - brown dwarf pair"),
                        ("rw-aurigae", "RW Aurigae - a variable young star"),
                        ("r-draconis", "R Draconis - a Mira variable")):
        try:
            m2, i2 = load_set(slug)
            blink(m2, i2, 1.75, title)
        except Exception as e:
            print("skip", slug, e)
    hold(end_card(), 4)
    return seq


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "docs", "skyblink-demo.mp4")
    seq = build_sequence()
    print(f"{len(seq)} frames = {len(seq)/FPS:.1f}s")
    cmd = ["ffmpeg", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", out]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for img in seq:
        p.stdin.write(img.tobytes())
    p.stdin.close(); p.wait()
    print("wrote", out, os.path.getsize(out) // 1024, "KB")


if __name__ == "__main__":
    main()
