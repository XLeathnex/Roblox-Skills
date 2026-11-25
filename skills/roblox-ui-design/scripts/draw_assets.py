#!/usr/bin/env python3
"""Draw UI image assets that Roblox instances cannot make on their own.

UICorner, UIStroke, UIGradient and UIShadow cover rounded rectangles. Everything
else a designer reaches for is an image: textures, cut-corner and skewed shapes,
ribbons, sunbursts, vignettes, material frames, and icons. This script draws
them as PNGs, records them in <out-dir>/assets.json, and prints the spec snippet
that uses each one.

    python3 scripts/draw_assets.py list
    python3 scripts/draw_assets.py texture studs  -o ui/assets/studs.png
    python3 scripts/draw_assets.py shape chamfer  -o ui/assets/plate.png --cut 18 --border 3
    python3 scripts/draw_assets.py material wood  -o ui/assets/wood.png --color "#8A5A34"
    python3 scripts/draw_assets.py icon coin      -o ui/assets/coin.png --style toon --color "#FFC531"
    python3 scripts/draw_assets.py overlay vignette -o ui/assets/vignette.png
    python3 scripts/draw_assets.py sheet -o ui/assets/contact.png      # look at everything this dir holds

White / greyscale assets are meant to be tinted with ImageColor3, so one upload
serves every colour in the palette. Keep each image at or under 1024x1024.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parent / "rbxui"))
import color as C  # noqa: E402

SS = 4  # supersampling for vector drawing


# ------------------------------------------------------------------ manifest

def record(out: Path, kind: str, **info):
    manifest = out.parent / "assets.json"
    data = {}
    if manifest.exists():
        try:
            data = json.loads(manifest.read_text())
        except Exception:
            data = {}
    entry = data.get(out.stem, {}) if isinstance(data.get(out.stem), dict) else {}
    entry.update({"file": out.name, "kind": kind, **info})
    entry.setdefault("id", None)
    data[out.stem] = entry
    manifest.write_text(json.dumps(data, indent=2) + "\n")


def save(img: Image.Image, out: Path, kind: str, snippet: dict, note: str = "", **info):
    out.parent.mkdir(parents=True, exist_ok=True)
    img = alpha_bleed(img)
    img.save(out)
    record(out, kind, size=list(img.size), **info)
    print(f"wrote {out}  ({img.width}x{img.height})")
    if note:
        print(f"  {note}")
    print("  use in a spec:")
    print("  " + json.dumps(snippet))


def alpha_bleed(img: Image.Image) -> Image.Image:
    """Copy edge colours into fully transparent pixels so scaled edges get no dark fringe in Roblox."""
    if img.mode != "RGBA":
        return img
    arr = np.asarray(img).copy()
    alpha = arr[..., 3]
    if alpha.min() > 0:
        return img
    rgb = arr[..., :3].astype(np.float32)
    known = alpha > 0
    for _ in range(12):
        if known.all():
            break
        acc = np.zeros_like(rgb)
        cnt = np.zeros(alpha.shape, dtype=np.float32)
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            k = np.roll(known, (dy, dx), axis=(0, 1))
            acc += np.roll(rgb, (dy, dx), axis=(0, 1)) * k[..., None]
            cnt += k
        new = (~known) & (cnt > 0)
        rgb[new] = acc[new] / cnt[new][:, None]
        known = known | new
    arr[..., :3] = np.clip(rgb, 0, 255).astype(np.uint8)
    return Image.fromarray(arr, "RGBA")


def rgba(color, alpha_mask: np.ndarray) -> Image.Image:
    h, w = alpha_mask.shape
    arr = np.zeros((h, w, 4), dtype=np.uint8)
    arr[..., :3] = np.asarray(C.to_rgb255(color), dtype=np.uint8)
    arr[..., 3] = np.clip(alpha_mask * 255, 0, 255).astype(np.uint8)
    return Image.fromarray(arr, "RGBA")


def tile_noise(w: int, h: int, sx: float, sy: float, seed: int = 1) -> np.ndarray:
    """Tileable smooth noise in 0..1. sx/sy are feature sizes in pixels (anisotropic when they differ)."""
    rng = np.random.default_rng(seed)
    white = rng.standard_normal((h, w))
    fy = np.fft.fftfreq(h)[:, None]
    fx = np.fft.fftfreq(w)[None, :]
    kernel = np.exp(-((fx * sx) ** 2 + (fy * sy) ** 2) * 6.0)
    out = np.fft.ifft2(np.fft.fft2(white) * kernel).real
    out -= out.min()
    out /= max(1e-9, out.max())
    return out.astype(np.float32)


# ------------------------------------------------------------------ textures

def texture(kind: str, size: int, strength: float, seed: int) -> tuple:
    """Tileable, white-with-alpha textures for low-opacity overlays."""
    s = size
    yy, xx = np.mgrid[0:s, 0:s].astype(np.float32)
    if kind == "noise":
        a = (tile_noise(s, s, 1.6, 1.6, seed) * 0.6 + tile_noise(s, s, 5, 5, seed + 1) * 0.4)
        a = np.clip((a - 0.35) * 1.9, 0, 1) * strength
        note = "Film grain. Tile it over a panel at ImageTransparency 0.9-0.97; dark tint on light UI, light tint on dark UI."
    elif kind == "stripes":
        period = s / 8
        v = ((xx + yy) % period) / period
        a = np.clip((0.5 - np.abs(v - 0.5)) * 2 * 6 - 2.0, 0, 1) * strength
        note = "Diagonal stripes. Header bands and progress bars at ImageTransparency 0.85-0.93."
    elif kind == "dots":
        period = s / 8
        cx = (xx % period) - period / 2
        cy = ((yy + (np.floor(xx / period) % 2) * period / 2) % period) - period / 2
        a = np.clip(period * 0.22 - np.hypot(cx, cy) + 0.5, 0, 1) * strength
        note = "Halftone dots. Card backs and banners at ImageTransparency 0.85-0.93."
    elif kind == "studs":
        period = s / 4
        cx = (xx % period) - period / 2
        cy = (yy % period) - period / 2
        r = period * 0.30
        d = np.hypot(cx, cy)
        disc = np.clip(r - d + 0.5, 0, 1)
        # lit from above: bright crescent on top of each stud, soft dark crescent below it
        light = disc * np.clip(-cy / r, 0, 1)
        shade = np.clip(r * 1.25 - np.hypot(cx, cy - r * 0.28) + 0.5, 0, 1) * (1 - disc)
        a_light = np.clip(disc * 0.22 + light * 0.5, 0, 1) * strength
        a_dark = shade * 0.5 * strength
        arr = np.zeros((s, s, 4), dtype=np.float32)
        tot = np.clip(a_light + a_dark, 1e-6, 1)
        arr[..., :3] = (a_light / tot)[..., None]
        arr[..., 3] = np.clip(a_light + a_dark, 0, 1)
        img = Image.fromarray((arr * 255).astype(np.uint8), "RGBA")
        return img, "Classic stud tile with baked light. Tile over a saturated fill at ImageTransparency 0.5-0.8 for the stud-UI look."
    elif kind == "grid":
        period = s / 8
        lx = np.minimum(xx % period, period - (xx % period))
        ly = np.minimum(yy % period, period - (yy % period))
        a = np.clip(1.0 - np.minimum(lx, ly), 0, 1) * strength
        note = "Blueprint grid. Sci-fi and tactical panels at ImageTransparency 0.9-0.96."
    elif kind == "scanlines":
        period = 4
        a = ((yy % period) < 1).astype(np.float32) * strength
        note = "CRT scanlines. Full-panel overlay at ImageTransparency 0.9-0.96; set ResampleMode Pixelated."
    elif kind == "hex":
        period = s / 6
        hh = period * math.sqrt(3) / 2
        row = np.floor(yy / hh)
        cx = ((xx + (row % 2) * period / 2) % period) - period / 2
        cy = (yy % hh) - hh / 2
        d = np.maximum(np.abs(cx), (np.abs(cx) * 0.5 + np.abs(cy) * 0.866))
        a = np.clip(1.2 - np.abs(d - period * 0.46), 0, 1) * strength
        note = "Hex mesh. Sci-fi panels at ImageTransparency 0.9-0.96."
    elif kind == "checker":
        period = s / 8
        a = (((np.floor(xx / period) + np.floor(yy / period)) % 2) > 0).astype(np.float32) * strength
        note = "Checker. Racing and arcade accents at ImageTransparency 0.85-0.93."
    else:
        raise SystemExit(f"unknown texture {kind!r}; choose from {', '.join(TEXTURES)}")
    return rgba((1, 1, 1), a), note


TEXTURES = ["noise", "stripes", "dots", "studs", "grid", "scanlines", "hex", "checker"]


# ------------------------------------------------------------------ overlays

def overlay(kind: str, size: int, color, rays: int) -> tuple:
    s = size
    yy, xx = np.mgrid[0:s, 0:s].astype(np.float32)
    u, v = (xx + 0.5) / s - 0.5, (yy + 0.5) / s - 0.5
    r = np.hypot(u, v) * 2
    if kind == "vignette":
        a = np.clip((np.hypot(u * 1.15, v * 1.15) * 2 - 0.55) / 0.75, 0, 1) ** 1.6
        return rgba(color or (0.02, 0.02, 0.03), a * 0.92), ("Full-screen edge darkening. One ImageLabel filling the screen in a "
                                                          "ScreenGui with ScreenInsets None, under everything else.")
    if kind == "glow":
        a = np.clip(1 - r, 0, 1) ** 2.2
        return rgba(color or (1, 1, 1), a), "Soft radial glow. Tint with ImageColor3; put behind a featured item."
    if kind == "sunburst":
        ang = np.arctan2(v, u)
        wedge = (np.cos(ang * rays) > 0).astype(np.float32)
        soft = np.clip(np.cos(ang * rays) * 6 + 0.5, 0, 1)
        a = soft * np.clip(1 - r, 0, 1) ** 0.9 * np.clip(r * 6, 0, 1)
        return rgba(color or (1, 1, 1), a * 0.9), ("Light rays. Tint and place behind a reward or featured item at "
                                                 "ImageTransparency 0.6-0.8; rotate it slowly in a script.")
    if kind == "spotlight":
        a = np.clip(1 - np.hypot(u * 1.6, (v + 0.5) * 0.9), 0, 1) ** 1.8
        return rgba(color or (1, 0.96, 0.86), a * 0.8), "Top-down light pool for cinematic menus."
    if kind == "scrim":
        a = np.clip((v + 0.5), 0, 1) ** 1.5
        return rgba(color or (0.02, 0.02, 0.03), a * 0.9), ("Bottom-up darkening behind text placed over the world "
                                                          "(dialogue, objectives). Stretch it; do not tile.")
    raise SystemExit(f"unknown overlay {kind!r}; choose from {', '.join(OVERLAYS)}")


OVERLAYS = ["vignette", "glow", "sunburst", "spotlight", "scrim"]


# ------------------------------------------------------------------ shapes (tintable, 9-slice)

def _poly_mask(w: int, h: int, pts) -> np.ndarray:
    img = Image.new("L", (w * SS, h * SS), 0)
    ImageDraw.Draw(img).polygon([(x * SS, y * SS) for x, y in pts], fill=255)
    return np.asarray(img.resize((w, h), Image.LANCZOS), dtype=np.float32) / 255


def _shade_shape(mask: np.ndarray, border: int, bevel: bool) -> Image.Image:
    """White shape with a darker border and optional baked top-light, all greyscale so ImageColor3 can tint it."""
    h, w = mask.shape
    m_img = Image.fromarray((mask * 255).astype(np.uint8), "L")
    inner = np.asarray(m_img.filter(ImageFilter.MinFilter(border * 2 + 1)), dtype=np.float32) / 255 if border > 0 else mask
    val = np.full((h, w), 0.38 if border > 0 else 1.0, dtype=np.float32)
    body = np.linspace(1.0, 0.86, h, dtype=np.float32)[:, None] * np.ones((1, w), dtype=np.float32) if bevel else np.ones((h, w), np.float32)
    if bevel:
        up = np.roll(inner, 3, axis=0)
        up[:3] = 0
        down = np.roll(inner, -4, axis=0)
        down[-4:] = 0
        top_rim = np.clip(inner - up, 0, 1)
        bottom_rim = np.clip(inner - down, 0, 1)
        body = np.clip(body + top_rim * 0.14 - bottom_rim * 0.2, 0, 1)
    val = val * (1 - inner) + body * inner
    arr = np.zeros((h, w, 4), dtype=np.uint8)
    arr[..., :3] = (np.clip(val, 0, 1) * 255).astype(np.uint8)[..., None]
    arr[..., 3] = (mask * 255).astype(np.uint8)
    return Image.fromarray(arr, "RGBA")


def shape(kind: str, w: int, h: int, cut: int, border: int, bevel: bool) -> tuple:
    if kind == "chamfer":
        c = cut
        pts = [(c, 0), (w - c, 0), (w, c), (w, h - c), (w - c, h), (c, h), (0, h - c), (0, c)]
        m = c + border + 4
        slice_center = [m, m, w - m, h - m]
        note = "Cut-corner plate (sci-fi, tactical, military). 9-slice."
    elif kind == "chamfer2":
        c = cut
        pts = [(c, 0), (w, 0), (w, h - c), (w - c, h), (0, h), (0, c)]
        m = c + border + 4
        slice_center = [m, m, w - m, h - m]
        note = "Two opposite corners cut (anime, sci-fi cards). 9-slice."
    elif kind == "skew":
        c = cut
        pts = [(c, 0), (w, 0), (w - c, h), (0, h)]
        slice_center = [c + border + 4, h // 2 - 1, w - c - border - 4, h // 2 + 1]
        note = ("Parallelogram (sport, racing, anime, action). Slices horizontally only: keep the ImageLabel "
                "at this asset's height times SliceScale.")
    elif kind == "ribbon":
        c = cut
        pts = [(0, 0), (w, 0), (w - c, h / 2), (w, h), (0, h), (c, h / 2)]
        slice_center = [c + border + 6, h // 2 - 1, w - c - border - 6, h // 2 + 1]
        note = "Notched title ribbon. Slices horizontally only."
    elif kind == "tab":
        c = cut
        pts = [(c, 0), (w - c, 0), (w, h), (0, h)]
        slice_center = [c + border + 4, h // 2 - 1, w - c - border - 4, h // 2 + 1]
        note = "Trapezoid tab / header plate. Slices horizontally only."
    elif kind == "hexagon":
        c = h / 2 * 0.58
        pts = [(c, 0), (w - c, 0), (w, h / 2), (w - c, h), (c, h), (0, h / 2)]
        slice_center = [int(c) + border + 4, h // 2 - 1, w - int(c) - border - 4, h // 2 + 1]
        note = "Hexagonal plate. Slices horizontally only."
    elif kind == "burst":
        n = 14
        pts = []
        for i in range(n * 2):
            rad = (min(w, h) / 2) * (1.0 if i % 2 == 0 else 0.84)
            a = math.pi * i / n - math.pi / 2
            pts.append((w / 2 + math.cos(a) * rad, h / 2 + math.sin(a) * rad))
        slice_center = None
        note = "Starburst seal for NEW / SALE / -50% tags. Use ScaleType Fit and rotate the label 8-12 degrees."
    elif kind == "bracket":
        t = max(2, border or 3)
        ln = cut * 2
        img = Image.new("L", (w * SS, h * SS), 0)
        d = ImageDraw.Draw(img)
        for (x0, y0, sx, sy) in ((0, 0, 1, 1), (w, 0, -1, 1), (0, h, 1, -1), (w, h, -1, -1)):
            d.rectangle(sorted_box(x0 * SS, y0 * SS, (x0 + sx * ln) * SS, (y0 + sy * t) * SS), fill=255)
            d.rectangle(sorted_box(x0 * SS, y0 * SS, (x0 + sx * t) * SS, (y0 + sy * ln) * SS), fill=255)
        mask = np.asarray(img.resize((w, h), Image.LANCZOS), dtype=np.float32) / 255
        m = ln + 2
        return rgba((1, 1, 1), mask), [m, m, w - m, h - m], "Corner brackets with a transparent centre (HUD frames, target boxes). 9-slice."
    else:
        raise SystemExit(f"unknown shape {kind!r}; choose from {', '.join(SHAPES)}")
    mask = _poly_mask(w, h, pts)
    return _shade_shape(mask, border, bevel), slice_center, note


def sorted_box(x0, y0, x1, y1):
    return [min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)]


SHAPES = ["chamfer", "chamfer2", "skew", "ribbon", "tab", "hexagon", "burst", "bracket"]


# ------------------------------------------------------------------ materials

def material(kind: str, base, size: int, seed: int) -> tuple:
    """-> (fill tile RGB, frame 9-slice RGBA, slice_center, note). Lit from the top-left."""
    s = size
    L0, C0, H0 = C.to_oklch(base)

    def ramp(v: np.ndarray, lo: float, hi: float):
        """Map 0..1 values to a hue-shifted light/dark ramp around the base colour."""
        out = np.zeros(v.shape + (3,), dtype=np.float32)
        steps = np.linspace(lo, hi, 9)
        cols = np.array([C.shade(base, st) for st in steps], dtype=np.float32)
        idx = np.clip(v, 0, 1) * (len(steps) - 1)
        i0 = np.floor(idx).astype(int).clip(0, len(steps) - 2)
        f = (idx - i0)[..., None]
        out = cols[i0] * (1 - f) + cols[i0 + 1] * f
        return out

    if kind == "wood":
        grain = tile_noise(s, s, 60, 2.2, seed) * 0.65 + tile_noise(s, s, 14, 1.2, seed + 1) * 0.35
        yy = np.mgrid[0:s, 0:s][0]
        planks = 4
        ph = s / planks
        seam = np.clip(1.6 - np.minimum(yy % ph, ph - (yy % ph)), 0, 1)
        tone = (np.floor(yy / ph) * 0.37 % 1.0) * 0.18
        v = np.clip(0.5 + (grain - 0.5) * 0.9 + tone - 0.09, 0, 1)
        fill = ramp(v, -1.6, 1.3) * (1 - seam[..., None] * 0.45)
        note = "Planks with grain."
    elif kind == "stone":
        v = tile_noise(s, s, 26, 26, seed) * 0.55 + tile_noise(s, s, 6, 6, seed + 1) * 0.3 + tile_noise(s, s, 1.4, 1.4, seed + 2) * 0.15
        fill = ramp(np.clip(0.5 + (v - 0.5) * 1.4, 0, 1), -1.3, 1.1)
        note = "Mottled stone."
    elif kind == "parchment":
        v = tile_noise(s, s, 50, 50, seed) * 0.6 + tile_noise(s, s, 9, 9, seed + 1) * 0.25 + tile_noise(s, s, 1.3, 1.3, seed + 2) * 0.15
        fill = ramp(np.clip(0.5 + (v - 0.5) * 1.1, 0, 1), -0.9, 0.8)
        note = "Aged paper."
    elif kind == "metal":
        v = tile_noise(s, s, 90, 1.1, seed) * 0.7 + tile_noise(s, s, 30, 30, seed + 1) * 0.3
        fill = ramp(np.clip(0.5 + (v - 0.5) * 0.9, 0, 1), -1.0, 1.2)
        note = "Brushed metal."
    elif kind == "leather":
        v = tile_noise(s, s, 3.2, 3.2, seed)
        cells = np.clip((v - 0.42) * 5, 0, 1)
        fill = ramp(np.clip(0.35 + cells * 0.4 + tile_noise(s, s, 40, 40, seed + 3) * 0.2, 0, 1), -1.4, 0.9)
        note = "Pebbled leather."
    else:
        raise SystemExit(f"unknown material {kind!r}; choose from {', '.join(MATERIALS)}")
    fill_img = Image.fromarray((np.clip(fill, 0, 1) * 255).astype(np.uint8), "RGB").convert("RGBA")

    # frame: a bevelled border ring with a transparent centre, 9-sliced
    fs, bw, rad = 192, 20, 14 if kind not in ("stone", "metal") else 6
    big = fs * SS
    outer = Image.new("L", (big, big), 0)
    ImageDraw.Draw(outer).rounded_rectangle([0, 0, big - 1, big - 1], radius=rad * SS, fill=255)
    inner = Image.new("L", (big, big), 0)
    ImageDraw.Draw(inner).rounded_rectangle([bw * SS, bw * SS, big - 1 - bw * SS, big - 1 - bw * SS],
                                            radius=max(2, rad - 6) * SS, fill=255)
    ring = ImageChops.subtract(outer, inner).resize((fs, fs), Image.LANCZOS)
    ring_a = np.asarray(ring, dtype=np.float32) / 255
    outer_a = np.asarray(outer.resize((fs, fs), Image.LANCZOS), dtype=np.float32) / 255
    inner_a = np.asarray(inner.resize((fs, fs), Image.LANCZOS), dtype=np.float32) / 255
    yy, xx = np.mgrid[0:fs, 0:fs].astype(np.float32)
    # distance into the ring from the outside (0) to the inside (1)
    d_out = np.minimum.reduce([xx, yy, fs - 1 - xx, fs - 1 - yy])
    t = np.clip(d_out / bw, 0, 1)
    light_dir = np.where((yy < xx) & (yy < fs - 1 - xx), 1.0, 0.0) + np.where((xx <= yy) & (xx < fs - 1 - yy), 0.6, 0.0) \
        - np.where((yy > xx) & (yy > fs - 1 - xx), 1.0, 0.0) - np.where((xx >= yy) & (xx > fs - 1 - yy), 0.6, 0.0)
    profile = np.where(t < 0.5, 1.0, -1.0) * (1 - np.abs(t - 0.5) * 1.2)
    tex = tile_noise(fs, fs, 30 if kind == "wood" else 6, 2 if kind in ("wood", "metal") else 6, seed + 9)
    v = np.clip(0.5 + light_dir * profile * 0.28 + (tex - 0.5) * 0.25, 0, 1)
    frame_rgb = ramp(v, -2.6, 1.6)
    edge_dark = np.clip(1 - d_out / 2.5, 0, 1) + np.clip(1 - np.abs(d_out - bw) / 2.0, 0, 1) * 0.8
    frame_rgb = frame_rgb * (1 - np.clip(edge_dark, 0, 1)[..., None] * 0.55)
    arr = np.zeros((fs, fs, 4), dtype=np.float32)
    arr[..., :3] = frame_rgb
    arr[..., 3] = ring_a
    if kind in ("wood", "metal"):
        img = Image.fromarray((np.clip(arr, 0, 1) * 255).astype(np.uint8), "RGBA")
        d = ImageDraw.Draw(img)
        stud = C.to_rgb255(C.shade(base, 2.2 if kind == "metal" else -3.0))
        hi = C.to_rgb255(C.shade(base, 4.0 if kind == "metal" else -1.0))
        for cx, cy in ((bw / 2, bw / 2), (fs - bw / 2, bw / 2), (bw / 2, fs - bw / 2), (fs - bw / 2, fs - bw / 2)):
            d.ellipse([cx - 4.5, cy - 4.5, cx + 4.5, cy + 4.5], fill=stud + (255,))
            d.ellipse([cx - 3.2, cy - 3.8, cx + 1.0, cy - 0.4], fill=hi + (255,))
        frame_img = img
    else:
        frame_img = Image.fromarray((np.clip(arr, 0, 1) * 255).astype(np.uint8), "RGBA")
    m = bw + 12
    return fill_img, frame_img, [m, m, fs - m, fs - m], note


MATERIALS = ["wood", "stone", "parchment", "metal", "leather"]


# ------------------------------------------------------------------ icons

class Glyph:
    """Tiny vector canvas in a 0..100 box. Draw filled shapes; cut() erases."""

    def __init__(self, size: int):
        self.size = size
        self.k = size * SS / 100
        self.img = Image.new("L", (size * SS, size * SS), 0)
        self.d = ImageDraw.Draw(self.img)

    def _p(self, pts):
        return [(x * self.k, y * self.k) for x, y in pts]

    def poly(self, pts, fill=255):
        self.d.polygon(self._p(pts), fill=fill)

    def circle(self, cx, cy, r, fill=255):
        self.d.ellipse([(cx - r) * self.k, (cy - r) * self.k, (cx + r) * self.k, (cy + r) * self.k], fill=fill)

    def ellipse(self, cx, cy, rx, ry, fill=255):
        self.d.ellipse([(cx - rx) * self.k, (cy - ry) * self.k, (cx + rx) * self.k, (cy + ry) * self.k], fill=fill)

    def rrect(self, x0, y0, x1, y1, r, fill=255):
        self.d.rounded_rectangle([x0 * self.k, y0 * self.k, x1 * self.k, y1 * self.k], radius=r * self.k, fill=fill)

    def line(self, pts, width, fill=255):
        p = self._p(pts)
        self.d.line(p, fill=fill, width=int(width * self.k), joint="curve")
        r = width * self.k / 2
        for x, y in p:
            self.d.ellipse([x - r, y - r, x + r, y + r], fill=fill)

    def arc(self, cx, cy, r, a0, a1, width, fill=255):
        pts = [(cx + math.cos(math.radians(a)) * r, cy + math.sin(math.radians(a)) * r)
               for a in np.linspace(a0, a1, 40)]
        self.line(pts, width, fill)

    def ring(self, cx, cy, r, width):
        self.circle(cx, cy, r + width / 2)
        self.circle(cx, cy, r - width / 2, fill=0)

    def mask(self) -> np.ndarray:
        return np.asarray(self.img.resize((self.size, self.size), Image.LANCZOS), dtype=np.float32) / 255


def _star(cx, cy, r_out, r_in, n=5, rot=-90):
    pts = []
    for i in range(n * 2):
        r = r_out if i % 2 == 0 else r_in
        a = math.radians(rot + i * 180 / n)
        pts.append((cx + math.cos(a) * r, cy + math.sin(a) * r))
    return pts


def _i_coin(g):
    g.circle(50, 50, 40)
    g.ring(50, 50, 29, 4.5) if False else None
    g.circle(50, 50, 31, fill=0)
    g.circle(50, 50, 26)
    g.poly(_star(50, 51, 15, 6.5), fill=0)


def _i_gem(g):
    g.poly([(26, 20), (74, 20), (92, 42), (50, 88), (8, 42)])
    for a, b in (((8, 42), (92, 42)), ((26, 20), (38, 42)), ((74, 20), (62, 42)), ((38, 42), (50, 88)), ((62, 42), (50, 88)), ((50, 20), (38, 42)), ((50, 20), (62, 42))):
        g.line([a, b], 2.6, fill=0)


def _i_star(g):
    g.poly(_star(50, 53, 44, 19))
    g.line(_star(50, 53, 44, 19) + [_star(50, 53, 44, 19)[0]], 6)


def _i_heart(g):
    g.circle(31, 37, 21)
    g.circle(69, 37, 21)
    g.poly([(11.5, 46), (88.5, 46), (50, 88)])
    g.line([(14, 49), (50, 86), (86, 49)], 5)


def _i_gear(g):
    for i in range(8):
        a = math.radians(i * 45)
        g.line([(50 + math.cos(a) * 26, 50 + math.sin(a) * 26), (50 + math.cos(a) * 40, 50 + math.sin(a) * 40)], 13)
    g.circle(50, 50, 30)
    g.circle(50, 50, 13, fill=0)


def _i_cart(g):
    g.line([(8, 20), (22, 20), (33, 62), (78, 62)], 7)
    g.poly([(24, 28), (92, 28), (82, 56), (31, 56)])
    g.circle(40, 78, 8)
    g.circle(72, 78, 8)


def _i_bag(g):
    g.arc(50, 34, 16, 180, 360, 7)
    g.rrect(16, 34, 84, 88, 12)
    g.rrect(34, 52, 66, 60, 4, fill=0)


def _i_home(g):
    g.poly([(50, 12), (92, 50), (8, 50)])
    g.line([(50, 14), (90, 50)], 5)
    g.line([(50, 14), (10, 50)], 5)
    g.rrect(20, 46, 80, 88, 5)
    g.rrect(41, 60, 59, 88, 3, fill=0)


def _i_lock(g):
    g.arc(50, 40, 18, 180, 360, 9)
    g.line([(32, 40), (32, 50)], 9)
    g.line([(68, 40), (68, 50)], 9)
    g.rrect(18, 46, 82, 90, 10)
    g.circle(50, 64, 7, fill=0)
    g.line([(50, 64), (50, 76)], 5, fill=0)


def _i_check(g):
    g.line([(16, 52), (40, 76), (84, 26)], 15)


def _i_close(g):
    g.line([(22, 22), (78, 78)], 16)
    g.line([(78, 22), (22, 78)], 16)


def _i_plus(g):
    g.line([(50, 16), (50, 84)], 17)
    g.line([(16, 50), (84, 50)], 17)


def _i_trophy(g):
    g.arc(26, 30, 14, 90, 270, 6)
    g.arc(74, 30, 14, -90, 90, 6)
    g.poly([(26, 12), (74, 12), (72, 40), (60, 56), (40, 56), (28, 40)])
    g.circle(50, 40, 22)
    g.rrect(24, 10, 76, 22, 4)
    g.rrect(45, 56, 55, 72, 2)
    g.rrect(28, 72, 72, 86, 5)


def _i_crown(g):
    g.poly([(12, 34), (32, 54), (50, 20), (68, 54), (88, 34), (80, 80), (20, 80)])
    for cx, cy in ((12, 32), (50, 18), (88, 32)):
        g.circle(cx, cy, 7)
    g.rrect(18, 72, 82, 86, 5)


def _i_bolt(g):
    g.poly([(58, 6), (20, 56), (44, 56), (36, 94), (80, 40), (54, 40)])
    g.line([(58, 8), (22, 55), (45, 55), (37, 92), (78, 41), (53, 41), (58, 8)], 4)


def _i_gift(g):
    g.rrect(14, 44, 86, 90, 7)
    g.rrect(8, 28, 92, 46, 6)
    g.rrect(44, 28, 56, 90, 0, fill=0)
    g.arc(36, 22, 10, 0, 360, 6)
    g.arc(64, 22, 10, 0, 360, 6)


def _i_clock(g):
    g.circle(50, 50, 40)
    g.circle(50, 50, 31, fill=0)
    g.line([(50, 30), (50, 50), (64, 60)], 7)


def _i_sword(g):
    g.poly([(78, 8), (92, 8), (92, 22), (42, 72), (28, 58)])
    g.line([(20, 50), (50, 80)], 9)
    g.line([(30, 70), (14, 86)], 10)
    g.circle(12, 88, 7)


def _i_shield(g):
    g.poly([(50, 8), (86, 20), (86, 50), (50, 92), (14, 50), (14, 20)])
    g.line([(50, 10), (84, 21), (84, 50), (50, 90), (16, 50), (16, 21), (50, 10)], 5)
    g.poly([(50, 24), (72, 31), (72, 50), (50, 76)], fill=0)


def _i_skull(g):
    g.circle(50, 42, 34)
    g.rrect(30, 56, 70, 88, 8)
    g.circle(36, 44, 10, fill=0)
    g.circle(64, 44, 10, fill=0)
    g.poly([(50, 54), (44, 66), (56, 66)], fill=0)
    for x in (42, 50, 58):
        g.line([(x, 78), (x, 90)], 2.6, fill=0)


def _i_key(g):
    g.ring(30, 50, 16, 10)
    g.line([(48, 50), (90, 50)], 10)
    g.line([(72, 50), (72, 66)], 9)
    g.line([(86, 50), (86, 64)], 9)


def _i_eye(g):
    g.poly([(4, 50), (26, 26), (50, 18), (74, 26), (96, 50), (74, 74), (50, 82), (26, 74)])
    g.ellipse(50, 50, 44, 30)
    g.circle(50, 50, 20, fill=0)
    g.circle(50, 50, 10)


def _i_flame(g):
    g.poly([(50, 4), (66, 30), (80, 44), (84, 62), (50, 94), (16, 62), (24, 40), (36, 46), (40, 22)])
    g.circle(50, 64, 30)
    g.poly([(50, 46), (62, 66), (50, 86), (38, 66)], fill=0)
    g.circle(50, 72, 12, fill=0)


def _i_leaf(g):
    g.poly([(88, 12), (86, 50), (62, 82), (30, 84), (16, 70), (18, 40), (50, 16)])
    g.circle(46, 54, 32)
    g.line([(12, 90), (40, 60), (70, 30)], 5, fill=0)


def _i_egg(g):
    g.ellipse(50, 56, 32, 38)
    g.ellipse(50, 42, 25, 34)
    g.line([(20, 54), (32, 46), (42, 56), (52, 46), (62, 56), (72, 46), (80, 54)], 4.5, fill=0)


def _i_paw(g):
    g.ellipse(50, 66, 24, 20)
    g.circle(34, 60, 10)
    g.circle(66, 60, 10)
    for cx, cy in ((20, 42), (40, 24), (60, 24), (80, 42)):
        g.ellipse(cx, cy, 10, 12)


def _i_pin(g):
    g.circle(50, 38, 28)
    g.poly([(26, 52), (74, 52), (50, 94)])
    g.circle(50, 38, 11, fill=0)


def _i_user(g):
    g.circle(50, 30, 20)
    g.circle(50, 86, 36)
    g.rrect(0, 88, 100, 100, 0, fill=0)


def _i_users(g):
    g.circle(70, 34, 15)
    g.circle(70, 84, 26)
    g.circle(36, 30, 19, fill=0) if False else None
    g.circle(36, 30, 18)
    g.circle(36, 86, 32)
    g.rrect(0, 88, 100, 100, 0, fill=0)


def _i_chat(g):
    g.rrect(10, 14, 90, 70, 16)
    g.poly([(26, 62), (26, 90), (50, 66)])
    for x in (32, 50, 68):
        g.circle(x, 42, 6, fill=0)


def _i_sound(g):
    g.poly([(10, 38), (30, 38), (54, 16), (54, 84), (30, 62), (10, 62)])
    g.arc(54, 50, 18, -50, 50, 7)
    g.arc(54, 50, 34, -50, 50, 7)


def _i_music(g):
    g.line([(38, 72), (38, 20), (80, 12), (80, 62)], 8)
    g.ellipse(28, 74, 14, 11)
    g.ellipse(70, 64, 14, 11)


def _i_trade(g):
    g.line([(14, 34), (78, 34)], 10)
    g.poly([(70, 14), (94, 34), (70, 54)])
    g.line([(86, 68), (22, 68)], 10)
    g.poly([(30, 48), (6, 68), (30, 88)])


def _i_menu(g):
    for y in (26, 50, 74):
        g.line([(16, 30 if False else y), (84, y)], 12)


def _i_play(g):
    g.poly([(24, 12), (88, 50), (24, 88)])
    g.line([(26, 14), (86, 50), (26, 86), (26, 14)], 6)


def _i_arrow(g):
    g.line([(14, 50), (78, 50)], 14)
    g.line([(52, 22), (82, 50), (52, 78)], 14)


def _i_info(g):
    g.circle(50, 50, 42)
    g.circle(50, 28, 7, fill=0)
    g.line([(50, 44), (50, 74)], 10, fill=0)


def _i_warn(g):
    g.poly([(50, 8), (94, 86), (6, 86)])
    g.line([(50, 12), (90, 84), (10, 84), (50, 12)], 6)
    g.line([(50, 36), (50, 60)], 9, fill=0)
    g.circle(50, 74, 5.5, fill=0)


def _i_backpack(g):
    g.arc(50, 22, 12, 180, 360, 6)
    g.rrect(18, 22, 82, 90, 16)
    g.rrect(30, 54, 70, 80, 6, fill=0)
    g.rrect(34, 58, 66, 76, 4)
    g.rrect(30, 34, 70, 42, 4, fill=0)


def _i_potion(g):
    g.rrect(40, 8, 60, 16, 3)
    g.rrect(43, 14, 57, 40, 0)
    g.circle(50, 62, 30)
    g.arc(50, 62, 20, 20, 160, 5, fill=0)


def _i_book(g):
    g.rrect(12, 14, 88, 86, 8)
    g.rrect(47, 14, 53, 86, 0, fill=0)
    for y in (32, 46, 60):
        g.line([(22, y), (40, y)], 4, fill=0)
        g.line([(60, y), (78, y)], 4, fill=0)


def _i_flag(g):
    g.line([(22, 10), (22, 92)], 8)
    g.poly([(26, 14), (84, 22), (64, 38), (84, 56), (26, 56)])


def _i_target(g):
    g.ring(50, 50, 36, 9)
    g.ring(50, 50, 18, 8)
    g.circle(50, 50, 6)


ICONS = {
    "coin": _i_coin, "gem": _i_gem, "star": _i_star, "heart": _i_heart, "gear": _i_gear, "cart": _i_cart,
    "bag": _i_bag, "backpack": _i_backpack, "home": _i_home, "lock": _i_lock, "check": _i_check,
    "close": _i_close, "plus": _i_plus, "trophy": _i_trophy, "crown": _i_crown, "bolt": _i_bolt,
    "gift": _i_gift, "clock": _i_clock, "sword": _i_sword, "shield": _i_shield, "skull": _i_skull,
    "key": _i_key, "eye": _i_eye, "flame": _i_flame, "leaf": _i_leaf, "egg": _i_egg, "paw": _i_paw,
    "pin": _i_pin, "user": _i_user, "users": _i_users, "chat": _i_chat, "sound": _i_sound,
    "music": _i_music, "trade": _i_trade, "menu": _i_menu, "play": _i_play, "arrow": _i_arrow,
    "info": _i_info, "warn": _i_warn, "potion": _i_potion, "book": _i_book, "flag": _i_flag,
    "target": _i_target,
}


def toonify(mask: np.ndarray, base, outline_px: float, pad: int) -> Image.Image:
    """Shade a silhouette like a cartoon game icon: dark same-hue outline, top-lit body, one rim light, hard drop."""
    h, w = mask.shape
    big = np.zeros((h + pad * 2, w + pad * 2), dtype=np.float32)
    big[pad : pad + h, pad : pad + w] = mask
    H, W = big.shape
    m_img = Image.fromarray((big * 255).astype(np.uint8), "L")
    k = int(outline_px) * 2 + 1
    out_mask = np.asarray(m_img.filter(ImageFilter.MaxFilter(k)).filter(ImageFilter.GaussianBlur(0.8)), dtype=np.float32) / 255
    out_mask = np.clip(out_mask * 1.6, 0, 1)
    drop = np.roll(out_mask, int(outline_px * 0.9), axis=0)
    d = max(2, int(h * 0.045))
    up = np.roll(big, d, axis=0)
    down = np.roll(big, -d, axis=0)
    blur = lambda a, r: np.asarray(Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8), "L").filter(ImageFilter.GaussianBlur(r)), dtype=np.float32) / 255
    rim_light = blur(np.clip(big - up, 0, 1), 1.0)
    rim_shade = blur(np.clip(big - down, 0, 1), 1.6)
    yy = np.linspace(0, 1, H, dtype=np.float32)[:, None] * np.ones((1, W), dtype=np.float32)
    top, mid, bot = (np.array(C.shade(base, s), dtype=np.float32) for s in (1.2, 0.0, -1.3))
    body = np.where(yy[..., None] < 0.5, top + (mid - top) * (yy[..., None] * 2), mid + (bot - mid) * ((yy[..., None] - 0.5) * 2))
    light = np.array(C.shade(base, 3.2), dtype=np.float32)
    dark = np.array(C.shade(base, -2.6), dtype=np.float32)
    body = body * (1 - rim_shade[..., None] * 0.75) + dark * rim_shade[..., None] * 0.75
    body = body * (1 - rim_light[..., None] * 0.85) + light * rim_light[..., None] * 0.85
    line = np.array(C.shade(base, -5.2), dtype=np.float32)
    arr = np.zeros((H, W, 4), dtype=np.float32)
    a_out = np.clip(np.maximum(out_mask, drop), 0, 1)
    arr[..., :3] = line
    arr[..., 3] = a_out
    arr[..., :3] = arr[..., :3] * (1 - big[..., None]) + body * big[..., None]
    arr[..., 3] = np.maximum(arr[..., 3], big)
    return Image.fromarray((np.clip(arr, 0, 1) * 255).astype(np.uint8), "RGBA")


def icon(name: str, size: int, style: str, base) -> Image.Image:
    if name not in ICONS:
        raise SystemExit(f"unknown icon {name!r}; choose from {', '.join(sorted(ICONS))}")
    inner = int(size * (0.80 if style == "toon" else 0.9))
    g = Glyph(inner)
    ICONS[name](g)
    mask = g.mask()
    pad = (size - inner) // 2
    if style == "toon":
        return toonify(mask, base, max(2.0, size * 0.035), pad)
    big = np.zeros((size, size), dtype=np.float32)
    big[pad : pad + inner, pad : pad + inner] = mask
    return rgba((1, 1, 1), big)


# ------------------------------------------------------------------ contact sheet

def sheet(directory: Path, out: Path):
    files = sorted(p for p in directory.glob("*.png") if p.name != out.name)
    if not files:
        raise SystemExit(f"no PNG files in {directory}")
    cell, cols = 200, min(6, len(files))
    rows = (len(files) + cols - 1) // cols
    img = Image.new("RGB", (cols * cell, rows * (cell + 26)), (40, 44, 52))
    d = ImageDraw.Draw(img)
    for i, f in enumerate(files):
        x, y = (i % cols) * cell, (i // cols) * (cell + 26)
        tile = Image.new("RGB", (cell, cell), (58, 64, 76) if (i + i // cols) % 2 else (210, 214, 222))
        im = Image.open(f).convert("RGBA")
        im.thumbnail((cell - 24, cell - 24), Image.LANCZOS)
        tile.paste(im, ((cell - im.width) // 2, (cell - im.height) // 2), im)
        img.paste(tile, (x, y))
        d.text((x + 6, y + cell + 6), f.stem[:28], fill=(235, 238, 244))
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    print(f"wrote {out}  ({len(files)} assets). Open it and check each asset before using it.")


# ------------------------------------------------------------------ CLI

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")

    p = sub.add_parser("texture")
    p.add_argument("kind", choices=TEXTURES)
    p.add_argument("-o", "--out", required=True)
    p.add_argument("--size", type=int, default=256)
    p.add_argument("--strength", type=float, default=1.0)
    p.add_argument("--seed", type=int, default=1)

    p = sub.add_parser("overlay")
    p.add_argument("kind", choices=OVERLAYS)
    p.add_argument("-o", "--out", required=True)
    p.add_argument("--size", type=int, default=512)
    p.add_argument("--color")
    p.add_argument("--rays", type=int, default=12)

    p = sub.add_parser("shape")
    p.add_argument("kind", choices=SHAPES)
    p.add_argument("-o", "--out", required=True)
    p.add_argument("--width", type=int, default=192)
    p.add_argument("--height", type=int, default=96)
    p.add_argument("--cut", type=int, default=18, help="corner cut / skew / notch size in px")
    p.add_argument("--border", type=int, default=3, help="baked darker border in px (0 = none)")
    p.add_argument("--flat", action="store_true", help="no baked top-light")

    p = sub.add_parser("material")
    p.add_argument("kind", choices=MATERIALS)
    p.add_argument("-o", "--out", required=True, help="base path; writes <name>-fill.png and <name>-frame.png")
    p.add_argument("--color", help="base colour, e.g. #8A5A34")
    p.add_argument("--size", type=int, default=256)
    p.add_argument("--seed", type=int, default=3)

    p = sub.add_parser("icon")
    p.add_argument("name")
    p.add_argument("-o", "--out", required=True)
    p.add_argument("--style", choices=["toon", "glyph"], default="glyph")
    p.add_argument("--color", default="#FFC531", help="toon base colour")
    p.add_argument("--size", type=int, default=256)

    p = sub.add_parser("sheet")
    p.add_argument("-o", "--out", required=True)
    p.add_argument("--dir")

    a = ap.parse_args(argv)
    if a.cmd == "list":
        print("texture :", ", ".join(TEXTURES), " (tileable, white + alpha, tint with ImageColor3)")
        print("overlay :", ", ".join(OVERLAYS))
        print("shape   :", ", ".join(SHAPES), " (greyscale, tintable, 9-slice)")
        print("material:", ", ".join(MATERIALS), " (full colour: a tile fill + a 9-slice frame)")
        print("icon    :", ", ".join(sorted(ICONS)))
        print("          --style glyph (flat white, tintable) | toon (shaded, outlined, coloured)")
        return 0
    out = Path(a.out)
    name = out.stem
    if a.cmd == "texture":
        img, note = texture(a.kind, a.size, a.strength, a.seed)
        tile = a.size // 2 if a.kind != "studs" else a.size // 2
        save(img, out, "texture", {"class": "ImageLabel", "name": name.title().replace("-", ""), "Size": [1, 0, 1, 0],
                                   "Image": f"asset:{name}", "ScaleType": "Tile", "TileSize": [0, tile, 0, tile],
                                   "ImageColor3": "#FFFFFF", "ImageTransparency": 0.9, "ZIndex": 0}, note)
    elif a.cmd == "overlay":
        col = C.parse_hex(a.color) if a.color else None
        img, note = overlay(a.kind, a.size, col, a.rays)
        save(img, out, "overlay", {"class": "ImageLabel", "name": name.title().replace("-", ""), "Size": [1, 0, 1, 0],
                                   "Image": f"asset:{name}", "ScaleType": "Stretch"}, note)
    elif a.cmd == "shape":
        img, sc, note = shape(a.kind, a.width, a.height, a.cut, a.border, not a.flat)
        snippet = {"class": "ImageLabel", "name": name.title().replace("-", ""), "Size": [0, a.width, 0, a.height],
                   "Image": f"asset:{name}", "ImageColor3": "$color.primary"}
        if sc:
            snippet.update({"ScaleType": "Slice", "SliceCenter": sc})
        else:
            snippet.update({"ScaleType": "Fit"})
        save(img, out, "shape", snippet, note + " Tint with ImageColor3.", slice=sc)
    elif a.cmd == "material":
        base = C.parse_hex(a.color) if a.color else C.parse_hex({"wood": "#8A5A34", "stone": "#7C7F86", "parchment": "#E2CFA4",
                                                                 "metal": "#6F7B88", "leather": "#6B3F2A"}[a.kind])
        fill, frame, sc, note = material(a.kind, base, a.size, a.seed)
        fill_out = out.with_name(f"{name}-fill.png")
        frame_out = out.with_name(f"{name}-frame.png")
        save(fill, fill_out, "material-fill",
             {"class": "ImageLabel", "name": "Fill", "Size": [1, 0, 1, 0], "Image": f"asset:{name}-fill",
              "ScaleType": "Tile", "TileSize": [0, a.size, 0, a.size], "corner": 10}, note)
        save(frame, frame_out, "material-frame",
             {"class": "ImageLabel", "name": "Frame", "Size": [1, 0, 1, 0], "Image": f"asset:{name}-frame",
              "ScaleType": "Slice", "SliceCenter": sc, "ZIndex": 5},
             "Bevelled border with a transparent centre. Layer it over the fill; put content between them.", slice=sc)
    elif a.cmd == "icon":
        img = icon(a.name, a.size, a.style, C.parse_hex(a.color))
        snippet = {"class": "ImageLabel", "name": a.name.title() + "Icon", "Size": [0, 48, 0, 48], "Image": f"asset:{name}",
                   "ScaleType": "Fit"}
        if a.style == "glyph":
            snippet["ImageColor3"] = "$color.ink"
        save(img, out, "icon", snippet, "Glyph icons are white: tint them with ImageColor3." if a.style == "glyph"
             else "Toon icon with a same-hue outline; do not tint it.")
    elif a.cmd == "sheet":
        sheet(Path(a.dir) if a.dir else out.parent, out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
