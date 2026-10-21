"""Engraving-style bust portraits: a licensed photograph rendered as line hatching in SVG.

Tone is mapped to up to four hatch layers at different angles, with line weight
varying by darkness, inside an oval medallion. The likeness comes only from the
reference photograph; nothing is drawn freehand.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter, ImageOps

LAYERS = [  # (angle in degrees, darkness threshold, base stroke width)
    (35, 0.18, 0.55),
    (-35, 0.40, 0.55),
    (90, 0.62, 0.50),
    (8, 0.80, 0.45),
]


def tone(path, crop, width):
    img = Image.open(path).convert('L')
    if crop:
        img = img.crop(tuple(crop))
    img = img.resize((width, round(img.height * width / img.width)), Image.LANCZOS)
    img = ImageOps.autocontrast(img, cutoff=1)
    img = img.filter(ImageFilter.GaussianBlur(0.8))
    dark = 1.0 - np.asarray(img, dtype=float) / 255.0
    h, w = dark.shape
    yy, xx = np.mgrid[0:h, 0:w]
    # Oval medallion: tone fades to paper towards the rim.
    cx, cy, rx, ry = w / 2, h * 0.52, w * 0.48, h * 0.49
    r = ((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2
    fade = np.clip((1.0 - r) / 0.30, 0, 1)
    return (dark ** 1.2) * fade, (cx, cy, rx, ry)


def hatch(dark, spacing):
    h, w = dark.shape
    paths = []
    for angle, threshold, base in LAYERS:
        a = math.radians(angle)
        dx, dy = math.cos(a), math.sin(a)
        nx, ny = -dy, dx
        diag = math.hypot(w, h)
        offsets = np.arange(-diag, diag, spacing)
        steps = np.arange(-diag, diag, 0.6)
        for off in offsets:
            px = w / 2 + nx * off + dx * steps
            py = h / 2 + ny * off + dy * steps
            ok = (px >= 0) & (px < w - 1) & (py >= 0) & (py < h - 1)
            if not ok.any():
                continue
            px, py = px[ok], py[ok]
            v = dark[py.astype(int), px.astype(int)]
            on = v > threshold
            if not on.any():
                continue
            # Runs of samples above threshold become segments.
            edges = np.flatnonzero(np.diff(np.concatenate(([0], on.astype(int), [0]))))
            for s, e in zip(edges[::2], edges[1::2]):
                if e - s < 3:
                    continue
                weight = base * (0.6 + 1.2 * float(v[s:e].mean() - threshold) / (1 - threshold))
                paths.append((round(weight, 2), f'M{px[s]:.1f} {py[s]:.1f}L{px[e - 1]:.1f} {py[e - 1]:.1f}'))
    return paths


def render(path, crop, out, width=360, spacing=None):
    dark, (cx, cy, rx, ry) = tone(path, crop, width)
    h, w = dark.shape
    spacing = spacing or w / 100
    groups = {}
    for weight, d in hatch(dark, spacing):
        groups.setdefault(weight, []).append(d)
    body = ''.join(f'<path d="{"".join(ds)}" stroke-width="{wt}"/>' for wt, ds in sorted(groups.items()))
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">'
           f'<g fill="none" stroke="#1c1f24" stroke-linecap="round">{body}</g>'
           f'<ellipse cx="{cx:.1f}" cy="{cy:.1f}" rx="{rx:.1f}" ry="{ry:.1f}" fill="none" stroke="#1c1f24" stroke-width="1.2"/>'
           f'<ellipse cx="{cx:.1f}" cy="{cy:.1f}" rx="{rx + 4:.1f}" ry="{ry + 4:.1f}" fill="none" stroke="#1c1f24" stroke-width="0.5"/>'
           '</svg>')
    Path(out).write_text(svg, encoding='utf-8')
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('manifest', type=Path, help='JSON list of {id, file, crop}')
    p.add_argument('source_dir', type=Path)
    p.add_argument('out_dir', type=Path)
    a = p.parse_args()
    a.out_dir.mkdir(parents=True, exist_ok=True)
    for item in json.loads(a.manifest.read_text(encoding='utf-8')):
        print(render(a.source_dir / item['file'], item.get('crop'), a.out_dir / f'{item["id"]}.svg'))


if __name__ == '__main__':
    main()
