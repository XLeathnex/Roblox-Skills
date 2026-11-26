#!/usr/bin/env python3
"""Drawing toolkit for Roblox UI art.

Two parts:

1. A library for drawing a game's own art in Python: Shape (a supersampled vector canvas), paint()
   (shading, outline, rim light), layer(), glow(), plate() (tintable 9-slice plates), lettering()
   (titles as art in any font), tile_noise(), save() (alpha-bleed + assets.json + spec snippet).
   Import it:  sys.path.insert(0, "<skill>/scripts"); import draw_assets as da

2. A small command line for generic building blocks that are the same in every game:

    python3 scripts/draw_assets.py texture stripes -o ui/assets/stripes.png
    python3 scripts/draw_assets.py overlay vignette -o ui/assets/vignette.png
    python3 scripts/draw_assets.py material wood -o ui/assets/wood.png --color "#8A5A34"
    python3 scripts/draw_assets.py batch ui/assets "texture noise" "overlay glow" "material stone"
    python3 scripts/draw_assets.py sheet -o ui/assets/_sheet.png     # contact sheet of a folder

There is deliberately no stock icon or shape catalogue. Keep each image at or under 1024x1024.
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


QUIET = False  # batch mode: one line per asset


def save(img: Image.Image, out: Path, kind: str, snippet: dict, note: str = "", **info):
    out.parent.mkdir(parents=True, exist_ok=True)
    img = alpha_bleed(img)
    img.save(out)
    record(out, kind, size=list(img.size), **info)
    if QUIET:
        keep = {k: v for k, v in snippet.items() if k in ("Image", "ScaleType", "SliceCenter", "TileSize")}
        print(f"{out.name} {img.width}x{img.height}  " + json.dumps(keep))
        return
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


def sorted_box(x0, y0, x1, y1):
    return [min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)]


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

    def curve(self, p0, p1, p2, p3=None, width=6, fill=255):
        """A stroked bezier (3 or 4 control points)."""
        self.line(bezier_points(p0, p1, p2, p3), width, fill)

    def blob(self, *controls, fill=255):
        """A filled closed shape through bezier segments: blob((p0, c, p1), (p1, c, p2), ...)."""
        pts = []
        for seg in controls:
            pts += bezier_points(*seg)
        self.poly(pts, fill)

    def mask(self) -> np.ndarray:
        return np.asarray(self.img.resize((self.size, self.size), Image.LANCZOS), dtype=np.float32) / 255


Shape = Glyph


def toonify(mask: np.ndarray, base, outline_px: float, pad: int) -> Image.Image:
    """Cartoon shading with a same-hue outline and a small hard drop. See paint() for every knob."""
    return paint(mask, base, outline_px=outline_px, lip=outline_px * 0.9, light=0.85, shade=0.75, gradient=1.25, pad=pad)


# ------------------------------------------------------------------ toolkit for bespoke art

def star_points(cx, cy, r_out, r_in, n=5, rot=-90):
    pts = []
    for i in range(n * 2):
        r = r_out if i % 2 == 0 else r_in
        a = math.radians(rot + i * 180 / n)
        pts.append((cx + math.cos(a) * r, cy + math.sin(a) * r))
    return pts


def bezier_points(p0, p1, p2, p3=None, steps=24):
    """Points along a quadratic (3 control points) or cubic (4) bezier, for Glyph.poly / Glyph.line."""
    out = []
    for i in range(steps + 1):
        t = i / steps
        if p3 is None:
            x = (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t * t * p2[0]
            y = (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t * t * p2[1]
        else:
            x = (1 - t) ** 3 * p0[0] + 3 * (1 - t) ** 2 * t * p1[0] + 3 * (1 - t) * t * t * p2[0] + t ** 3 * p3[0]
            y = (1 - t) ** 3 * p0[1] + 3 * (1 - t) ** 2 * t * p1[1] + 3 * (1 - t) * t * t * p2[1] + t ** 3 * p3[1]
        out.append((x, y))
    return out


def _blur(a: np.ndarray, r: float) -> np.ndarray:
    return np.asarray(Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8), "L").filter(ImageFilter.GaussianBlur(r)), dtype=np.float32) / 255


def paint(mask: np.ndarray, color, outline=None, outline_px: float = 0, light: float = 0.8, shade: float = 0.7,
          gradient: float = 1.2, lip: float = 0, pad: int = None) -> Image.Image:
    """Shade a silhouette mask into a finished piece of art. Every knob is optional:
    color       base colour (r, g, b) 0..1, e.g. C.parse_hex("#E8563A")
    gradient    top-to-bottom shading strength in shade() steps (0 = flat fill)
    light/shade strength 0..1 of the top rim light and bottom rim shade (0 = none)
    outline     outline colour (default: a deep shade of `color`); outline_px its width (0 = no outline)
    lip         extra pixels of outline dropped below the shape, like a hard shadow
    Returns an RGBA image padded so the outline fits. Paint parts separately and stack them with layer()."""
    h, w = mask.shape
    pad = int(outline_px + lip + 4) if pad is None else pad
    big = np.zeros((h + pad * 2, w + pad * 2), dtype=np.float32)
    big[pad:pad + h, pad:pad + w] = mask
    H, W = big.shape
    yy = np.linspace(0, 1, H, dtype=np.float32)[:, None] * np.ones((1, W), dtype=np.float32)
    top, mid, bot = (np.array(C.shade(color, s), dtype=np.float32) for s in (gradient, 0.0, -gradient * 1.1))
    y3 = yy[..., None]
    body = np.where(y3 < 0.5, top + (mid - top) * (y3 * 2), mid + (bot - mid) * ((y3 - 0.5) * 2))
    d = max(2, int(h * 0.045))
    if shade > 0:
        rim = _blur(np.clip(big - np.roll(big, -d, axis=0), 0, 1), 1.6)[..., None] * shade
        body = body * (1 - rim) + np.array(C.shade(color, -2.6), dtype=np.float32) * rim
    if light > 0:
        rim = _blur(np.clip(big - np.roll(big, d, axis=0), 0, 1), 1.0)[..., None] * light
        body = body * (1 - rim) + np.array(C.shade(color, 3.2), dtype=np.float32) * rim
    arr = np.zeros((H, W, 4), dtype=np.float32)
    if outline_px > 0:
        k = int(outline_px) * 2 + 1
        m_img = Image.fromarray((big * 255).astype(np.uint8), "L")
        om = np.asarray(m_img.filter(ImageFilter.MaxFilter(k)).filter(ImageFilter.GaussianBlur(0.8)), dtype=np.float32) / 255
        om = np.clip(om * 1.6, 0, 1)
        if lip > 0:
            om = np.maximum(om, np.roll(om, int(lip), axis=0))
        arr[..., :3] = np.array(outline if outline is not None else C.shade(color, -5.2), dtype=np.float32)
        arr[..., 3] = om
    arr[..., :3] = arr[..., :3] * (1 - big[..., None]) + body * big[..., None]
    arr[..., 3] = np.maximum(arr[..., 3], big)
    return Image.fromarray((np.clip(arr, 0, 1) * 255).astype(np.uint8), "RGBA")


def layer(*images, size=None, align="center") -> Image.Image:
    """Stack RGBA images back to front on one canvas (largest size by default, each centred)."""
    w = size[0] if size else max(i.width for i in images)
    h = size[1] if size else max(i.height for i in images)
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    for im in images:
        tmp = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        tmp.paste(im, ((w - im.width) // 2, (h - im.height) // 2))
        out = Image.alpha_composite(out, tmp)
    return out


def glow(mask: np.ndarray, color, radius: float, strength: float = 1.0) -> Image.Image:
    """A soft halo in `color` around a mask (same size as the mask; put it behind the art)."""
    return rgba(color, np.clip(_blur(mask, radius) * strength, 0, 1))


def plate(mask: np.ndarray, border: int = 3, bevel: bool = True) -> Image.Image:
    """Greyscale shaded plate from any mask, tintable with ImageColor3 (one upload, every colour)."""
    return _shade_shape(mask, border, bevel)


FONT_DIRS = [Path(__file__).resolve().parent.parent / "assets" / "fonts", Path.home() / ".cache" / "rbxui-fonts"]


def font_path(name: str) -> Path:
    """Find a .ttf for lettering: a path, a bundled preview font (e.g. "Bangers"), or a Google Fonts family
    name (e.g. "Bungee", "Rye", "Pirata One"), which is downloaded once and cached."""
    if Path(name).exists():
        return Path(name)
    key = name.replace(" ", "").lower()
    for d in FONT_DIRS:
        if d.exists():
            for f in d.glob("*.ttf"):
                if f.stem.lower() == key:
                    return f
    import urllib.parse
    import urllib.request

    cache = FONT_DIRS[1]
    cache.mkdir(parents=True, exist_ok=True)
    compact = name.replace(" ", "")
    for lic in ("ofl", "apache", "ufl"):
        for fname in (f"{compact}-Regular.ttf", f"{compact}[wght].ttf", f"{compact}-Bold.ttf", f"{compact}.ttf"):
            url = f"https://raw.githubusercontent.com/google/fonts/main/{lic}/{key}/{urllib.parse.quote(fname)}"
            try:
                data = urllib.request.urlopen(url, timeout=20).read()
            except Exception:
                continue
            out = cache / f"{compact}.ttf"
            out.write_bytes(data)
            return out
    bundled = sorted(f.stem for f in FONT_DIRS[0].glob("*.ttf"))
    raise SystemExit(f"font {name!r} not found locally or on Google Fonts. Bundled: {', '.join(bundled)}")


def lettering(text: str, font: str, size: int = 160, fill="#FFFFFF", fill_bottom=None, strokes=(), extrude: int = 0,
              extrude_color=None, arc: float = 0.0, slant: float = 0.0, highlight: float = 0.35, spacing: int = 0) -> Image.Image:
    """Draw a title as art instead of a TextLabel: any font, layered outlines, a 3D drop, an arch.
    fill / fill_bottom   top and bottom colours of the letters (hex); one colour = flat
    strokes              outlines from inside out: [("#4A2618", 10), ("#FFFFFF", 6)]
    extrude              pixels of solid depth below the letters (in extrude_color or the outer stroke colour)
    arc                  arch height in pixels (positive bows upward in the middle); slant: shear, e.g. 0.2
    highlight            strength 0..1 of a light band across the top of the letters
    Upload the PNG and show it in an ImageLabel with ScaleType Fit. Use for logos, headers, big numbers."""
    from PIL import ImageFont

    f = ImageFont.truetype(str(font_path(font)), size)
    total = sum(px for _, px in strokes)
    pad = total + extrude + int(abs(arc)) + 12
    probe = ImageDraw.Draw(Image.new("L", (8, 8)))
    widths = [probe.textlength(ch, font=f) + spacing for ch in text]
    asc, desc = f.getmetrics()
    W, H = int(sum(widths)) + pad * 2 + int(abs(slant) * size), asc + desc + pad * 2

    def text_mask(stroke_w: int) -> np.ndarray:
        img = Image.new("L", (W, H), 0)
        d = ImageDraw.Draw(img)
        x = pad + (abs(slant) * size if slant > 0 else 0)
        for ch, wd in zip(text, widths):
            d.text((x, pad), ch, font=f, fill=255, stroke_width=stroke_w, stroke_fill=255)
            x += wd
        m = np.asarray(img, dtype=np.float32) / 255
        if slant:
            rows = np.arange(H)
            shift = ((H - rows) * slant * 0.5 - H * slant * 0.25).astype(int)
            m = np.stack([np.roll(m[r], shift[r]) for r in rows])
        if arc:
            cols = np.arange(W)
            lift = (arc * (1 - ((cols - W / 2) / (W / 2)) ** 2)).astype(int)
            m = np.stack([np.roll(m[:, c], -lift[c]) for c in cols], axis=1)
        return m

    top = np.array(C.parse_hex(fill), dtype=np.float32)
    bottom = np.array(C.parse_hex(fill_bottom), dtype=np.float32) if fill_bottom else top
    face = text_mask(0)
    yy = np.clip((np.arange(H, dtype=np.float32) - pad) / max(1, asc + desc), 0, 1)[:, None, None]
    rgb = top * (1 - yy) + bottom * yy
    if highlight > 0:
        band = np.clip(face - np.roll(face, max(2, size // 22), axis=0), 0, 1)[..., None] * highlight
        rgb = rgb * (1 - band) + np.ones(3, dtype=np.float32) * band
    out = np.zeros((H, W, 4), dtype=np.float32)

    def over(col, a):
        a3 = a[..., None]
        out[..., :3] = np.asarray(col, dtype=np.float32) * a3 + out[..., :3] * (1 - a3)
        out[..., 3] = a + out[..., 3] * (1 - a)

    widths_acc, acc = [], 0
    for col, px in strokes:
        acc += px
        widths_acc.append((C.parse_hex(col), acc))
    outer_mask = text_mask(widths_acc[-1][1]) if widths_acc else face
    if extrude > 0:
        ecol = C.parse_hex(extrude_color) if extrude_color else (widths_acc[-1][0] if widths_acc else C.shade(tuple(bottom), -4))
        depth = outer_mask.copy()
        for dy in range(1, extrude + 1):
            depth = np.maximum(depth, np.roll(outer_mask, dy, axis=0))
        over(ecol, depth)
    for col, w_px in reversed(widths_acc):
        over(col, text_mask(w_px))
    out[..., :3] = rgb * face[..., None] + out[..., :3] * (1 - face[..., None])
    out[..., 3] = np.maximum(out[..., 3], face)
    img = Image.fromarray((np.clip(out, 0, 1) * 255).astype(np.uint8), "RGBA")
    box = img.getbbox()
    return img.crop(box) if box else img


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

    p = sub.add_parser("material")
    p.add_argument("kind", choices=MATERIALS)
    p.add_argument("-o", "--out", required=True, help="base path; writes <name>-fill.png and <name>-frame.png")
    p.add_argument("--color", help="base colour, e.g. #8A5A34")
    p.add_argument("--size", type=int, default=256)
    p.add_argument("--seed", type=int, default=3)

    p = sub.add_parser("sheet")
    p.add_argument("-o", "--out", required=True)
    p.add_argument("--dir")

    p = sub.add_parser("batch", help="draw several assets in one call")
    p.add_argument("dir", help="output folder, e.g. ui/assets")
    p.add_argument("items", nargs="+", help='each item is one quoted command without -o, e.g. "icon coin --style toon --color #FFC531 --name coin"')

    a = ap.parse_args(argv)
    if a.cmd == "batch":
        import shlex

        global QUIET
        QUIET = True
        for item in a.items:
            parts = shlex.split(item)
            name = None
            if "--name" in parts:
                i = parts.index("--name")
                name = parts[i + 1]
                del parts[i:i + 2]
            if len(parts) < 2:
                print(f"skipped {item!r}: expected '<texture|overlay|shape|material|icon> <kind> [options]'")
                continue
            name = name or parts[1]
            try:
                main(parts + ["-o", str(Path(a.dir) / f"{name}.png")])
            except SystemExit as e:
                print(f"failed {item!r}: {e}")
        return 0
    if a.cmd == "list":
        print("texture :", ", ".join(TEXTURES), " (tileable, white + alpha, tint with ImageColor3)")
        print("overlay :", ", ".join(OVERLAYS))
        print("material:", ", ".join(MATERIALS), " (full colour tile fill + a plain 9-slice frame)")
        print("There is no stock icon or shape set: draw this game's own art with the toolkit")
        print("(Shape, paint, layer, glow, plate, lettering) - see references/assets.md.")
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
    elif a.cmd == "sheet":
        sheet(Path(a.dir) if a.dir else out.parent, out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
