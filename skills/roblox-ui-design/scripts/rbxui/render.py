"""Paint a laid-out spec to a PNG, approximating Roblox's GUI renderer.

Shapes are drawn from signed-distance fields, so rounded corners, strokes and
shadows are anti-aliased without supersampling. The goal is a preview faithful
enough to judge depth, colour, hierarchy and overflow before opening Studio.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

import backdrop as backdrops
import fonts
import layout as L
from spec import IMAGE_CLASSES, TEXT_CLASSES, Node, Spec, effective

F = np.float32


# ------------------------------------------------------------------ layer

class Layer:
    """Premultiplied RGBA float canvas covering [ox, ox+w) x [oy, oy+h) in screen pixels."""

    def __init__(self, ox: int, oy: int, w: int, h: int):
        self.ox, self.oy, self.w, self.h = int(ox), int(oy), max(1, int(w)), max(1, int(h))
        self.a = np.zeros((self.h, self.w, 4), dtype=F)

    def blend(self, x0: int, y0: int, rgb, alpha: np.ndarray, clip=None):
        """Source-over a patch. rgb: (3,) or (h,w,3) straight colour; alpha: (h,w) coverage 0..1."""
        h, w = alpha.shape
        ax0, ay0, ax1, ay1 = self.ox, self.oy, self.ox + self.w, self.oy + self.h
        if clip:
            ax0, ay0 = max(ax0, clip[0]), max(ay0, clip[1])
            ax1, ay1 = min(ax1, clip[2]), min(ay1, clip[3])
        sx0, sy0 = max(x0, ax0), max(y0, ay0)
        sx1, sy1 = min(x0 + w, ax1), min(y0 + h, ay1)
        if sx1 <= sx0 or sy1 <= sy0:
            return
        a = alpha[sy0 - y0 : sy1 - y0, sx0 - x0 : sx1 - x0]
        if not a.any():
            return
        rgb = np.asarray(rgb, dtype=F)
        if rgb.ndim == 3:
            rgb = rgb[sy0 - y0 : sy1 - y0, sx0 - x0 : sx1 - x0]
        dst = self.a[sy0 - self.oy : sy1 - self.oy, sx0 - self.ox : sx1 - self.ox]
        a3 = a[..., None]
        dst[..., :3] = rgb * a3 + dst[..., :3] * (1 - a3)
        dst[..., 3] = a + dst[..., 3] * (1 - a)

    def composite(self, other: "Layer", opacity: float = 1.0, mask: np.ndarray | None = None,
                  tint=None, clip=None):
        """Source-over another premultiplied layer (optionally masked/tinted)."""
        src = other.a
        if tint is not None:
            src = src.copy()
            src[..., :3] *= np.asarray(tint, dtype=F)
        if mask is not None:
            src = src * mask[..., None]
        if opacity < 1:
            src = src * F(opacity)
        ax0, ay0, ax1, ay1 = self.ox, self.oy, self.ox + self.w, self.oy + self.h
        if clip:
            ax0, ay0 = max(ax0, clip[0]), max(ay0, clip[1])
            ax1, ay1 = min(ax1, clip[2]), min(ay1, clip[3])
        sx0, sy0 = max(other.ox, ax0), max(other.oy, ay0)
        sx1, sy1 = min(other.ox + other.w, ax1), min(other.oy + other.h, ay1)
        if sx1 <= sx0 or sy1 <= sy0:
            return
        s = src[sy0 - other.oy : sy1 - other.oy, sx0 - other.ox : sx1 - other.ox]
        dst = self.a[sy0 - self.oy : sy1 - self.oy, sx0 - self.ox : sx1 - self.ox]
        dst *= 1 - s[..., 3:4]
        dst += s

    def to_image(self) -> Image.Image:
        a = self.a
        alpha = np.clip(a[..., 3:4], 1e-6, 1)
        rgb = np.clip(a[..., :3] / alpha, 0, 1)
        out = np.concatenate([rgb, np.clip(a[..., 3:4], 0, 1)], axis=-1)
        return Image.fromarray((out * 255 + 0.5).astype(np.uint8), "RGBA")

    @staticmethod
    def from_image(img: Image.Image, ox=0, oy=0) -> "Layer":
        arr = np.asarray(img.convert("RGBA"), dtype=F) / 255
        lay = Layer(ox, oy, arr.shape[1], arr.shape[0])
        lay.a[..., :3] = arr[..., :3] * arr[..., 3:4]
        lay.a[..., 3] = arr[..., 3]
        return lay


# ------------------------------------------------------------------ geometry

def sdf_box(w: int, h: int, radii, margin: int, miter: bool = False):
    """Signed distance to a w x h rounded box, sampled on a grid extended by `margin` px each side."""
    ys = np.arange(-margin, h + margin, dtype=F) + 0.5 - h / 2
    xs = np.arange(-margin, w + margin, dtype=F) + 0.5 - w / 2
    X, Y = np.meshgrid(xs, ys)
    tl, tr, br, bl = radii
    r = np.where(Y < 0, np.where(X < 0, tl, tr), np.where(X < 0, bl, br)).astype(F)
    qx = np.abs(X) - (w / 2 - r)
    qy = np.abs(Y) - (h / 2 - r)
    if miter:
        return np.maximum(qx, qy) - r
    outside = np.hypot(np.maximum(qx, 0), np.maximum(qy, 0))
    inside = np.minimum(np.maximum(qx, qy), 0)
    return outside + inside - r


def cov(d):
    """Coverage of a half-plane edge at signed distance d (negative = inside)."""
    return np.clip(0.5 - d, 0, 1)


def soft(d, blur):
    """Coverage with a gaussian-ish falloff of radius `blur` (CSS-style blur radius)."""
    if blur <= 0.75:
        return cov(d)
    sigma = blur / 2
    return 0.5 - 0.5 * np.tanh(d / (sigma * 1.25))


def _srgb_to_lin(c):
    c = np.asarray(c, dtype=F)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _lin_to_srgb(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)


def gradient_t(w: int, h: int, g: Node, margin: int = 0):
    """Per-pixel gradient parameter t for a UIGradient over a w x h box (grid extended by margin)."""
    ys = np.arange(-margin, h + margin, dtype=F) + 0.5
    xs = np.arange(-margin, w + margin, dtype=F) + 0.5
    X, Y = np.meshgrid(xs, ys)
    off = g.props.get("Offset", (0.0, 0.0))
    cx, cy = w / 2 + off[0] * w, h / 2 + off[1] * h
    rot = math.radians(g.props.get("Rotation", 0.0))
    scale = max(0.001, g.props.get("Scale", 1.0))
    kind = g.props.get("Type", "Linear")
    dx, dy = X - cx, Y - cy
    if kind == "Radial":
        t = np.hypot(dx, dy) / max(1e-6, (w + h) / 4 * scale)
    elif kind == "Elliptical":
        c, s = math.cos(rot), math.sin(rot)
        ex, ey = dx * c + dy * s, -dx * s + dy * c
        t = np.hypot(ex / max(1e-6, w / 2), ey / max(1e-6, h / 2)) / scale
    elif kind == "Conical":
        ang = (np.degrees(np.arctan2(dy, dx)) - g.props.get("Rotation", 0.0)) % 360
        t = ang / (360 * min(1.0, scale))
    else:
        c, s = math.cos(rot), math.sin(rot)
        length = max(1e-6, abs(w * c) + abs(h * s)) * scale
        t = 0.5 + (dx * c + dy * s) / length
    tile = g.props.get("TileMode", "Clamp")
    if tile == "Repeat":
        t = t % 1.0
    elif tile == "Mirror":
        t = 1 - np.abs((t % 2.0) - 1)
    return np.clip(t, 0, 1).astype(F)


def gradient_color(t, seq):
    ts = np.array([p[0] for p in seq], dtype=F)
    cols = _srgb_to_lin(np.array([p[1] for p in seq], dtype=F))
    out = np.stack([np.interp(t, ts, cols[:, i]) for i in range(3)], axis=-1)
    return _lin_to_srgb(out).astype(F)


def gradient_alpha(t, seq):
    ts = np.array([p[0] for p in seq], dtype=F)
    vs = np.array([p[1] for p in seq], dtype=F)
    return (1 - np.interp(t, ts, vs)).astype(F)


def fill_paint(base, g: Node | None, w: int, h: int, margin: int):
    """-> (rgb array or tuple, alpha multiplier array or 1.0) for a base colour under an optional UIGradient."""
    if g is None or g.props.get("Enabled") is False:
        return np.asarray(base, dtype=F), 1.0
    t = gradient_t(w, h, g, margin)
    rgb = np.asarray(base, dtype=F)
    if "Color" in g.props:
        rgb = gradient_color(t, g.props["Color"]) * rgb
    am = 1.0
    if "Transparency" in g.props:
        am = gradient_alpha(t, g.props["Transparency"])
    return rgb, am


# ------------------------------------------------------------------ renderer

class Renderer:
    def __init__(self, spec: Spec, device: str = "pc", render_scale: float = 1.0, asset_dirs=None,
                 backdrop: str | None = None, chrome: bool = True):
        self.spec = spec
        self.device = device
        self.k = render_scale
        vw, vh = L.DEVICES[device][:2]
        self.W, self.H = int(vw * render_scale), int(vh * render_scale)
        self.asset_dirs = [Path(p) for p in (asset_dirs or [])]
        if spec.source:
            self.asset_dirs += [spec.source.parent / "assets", spec.source.parent]
        self.manifest = self._load_manifest()
        self.backdrop = backdrop or spec.meta.get("backdrop") or backdrops.for_genre(spec.meta.get("genre", ""))
        self.chrome = chrome
        self.missing_assets: set = set()
        self.notes: list = []
        self._img_cache = {}

    def _load_manifest(self):
        import json

        out = {}
        for d in self.asset_dirs:
            p = d / "assets.json"
            if p.exists():
                try:
                    data = json.loads(p.read_text())
                    for name, info in data.items():
                        if isinstance(info, dict) and info.get("file"):
                            out[name] = d / info["file"]
                            if info.get("id"):
                                out[f"rbxassetid://{info['id']}"] = d / info["file"]
                except Exception:
                    pass
        return out

    # -- public -----------------------------------------------------------
    def render(self) -> Image.Image:
        root = self.spec.root
        L.layout_tree(root, self.device, self.k)
        canvas = Layer.from_image(backdrops.make(self.backdrop, self.W, self.H))
        if effective(root, "Enabled") is not False:
            clip = (0, 0, self.W, self.H)
            if root.cls in L.GUI_OBJECTS:
                self.paint(root, canvas, clip)
            else:
                self.paint_children(root, canvas, clip)
        img = canvas.to_image().convert("RGB")
        if self.chrome:
            img = backdrops.draw_chrome(img, self.device, self.k, touch=not self._screen_taken())
        return img

    def _screen_taken(self) -> bool:
        """A full-screen opaque layer (pause menu scrim) hides the touch controls behind it."""
        for n in self.spec.root.walk():
            if n.cls in L.GUI_OBJECTS and hasattr(n, "rect"):
                x, y, w, h = n.rect
                if w >= self.W * 0.95 and h >= self.H * 0.95:
                    bt = effective(n, "BackgroundTransparency")
                    if (bt is not None and bt <= 0.5) or (n.cls in IMAGE_CLASSES and effective(n, "Image")):
                        return True
        return False

    # -- images -----------------------------------------------------------
    def load_image(self, ref: str):
        if not ref:
            return None
        if ref in self._img_cache:
            return self._img_cache[ref]
        path = None
        if ref in self.manifest:
            path = self.manifest[ref]
        elif ref.startswith("asset:"):
            name = ref[6:]
            if name in self.manifest:
                path = self.manifest[name]
            else:
                for d in self.asset_dirs:
                    for cand in (d / name, d / f"{name}.png"):
                        if cand.exists():
                            path = cand
                            break
                    if path:
                        break
        elif not ref.startswith("rbx") and not ref.startswith("http"):
            for d in [Path(".")] + self.asset_dirs:
                if (d / ref).exists():
                    path = d / ref
                    break
        img = None
        if path and Path(path).exists():
            img = Image.open(path).convert("RGBA")
        else:
            self.missing_assets.add(ref)
        self._img_cache[ref] = img
        return img

    # -- painting ---------------------------------------------------------
    def paint_children(self, node: Node, layer: Layer, clip):
        kids = [c for c in L.visible_gui_children(node) if hasattr(c, "rect")]
        kids.sort(key=lambda c: effective(c, "ZIndex") or 1)
        for c in kids:
            self.paint(c, layer, clip)

    def paint(self, node: Node, layer: Layer, clip):
        if L.ANIM["t"] is not None and not getattr(node, "_anim_done", False):
            st = L.anim_state(node, L.ANIM["t"])
            if st is not None:
                self._paint_animated(node, layer, clip, st)
                return
        rot = effective(node, "Rotation") or 0.0
        if abs(rot) > 0.01:
            self._paint_rotated(node, layer, clip, rot)
            return
        if node.cls == "CanvasGroup":
            self._paint_group(node, layer, clip)
            return
        self._paint_self(node, layer, clip)
        child_clip = clip
        if effective(node, "ClipsDescendants") or node.cls == "ScrollingFrame":
            x, y, w, h = self._irect(node)
            child_clip = (max(clip[0], x), max(clip[1], y), min(clip[2], x + w), min(clip[3], y + h))
        self.paint_children(node, layer, child_clip)
        if node.cls == "ScrollingFrame":
            self._paint_scrollbar(node, layer, clip)

    def _irect(self, node: Node):
        x, y, w, h = node.rect
        x0, y0 = int(round(x)), int(round(y))
        return x0, y0, max(0, int(round(x + w)) - x0), max(0, int(round(y + h)) - y0)

    def _subtree_bounds(self, node: Node, margin: int = 64):
        xs0, ys0, xs1, ys1 = [], [], [], []
        for n in node.walk():
            if hasattr(n, "rect") and n.cls in L.GUI_OBJECTS:
                x, y, w, h = n.rect
                xs0.append(x), ys0.append(y), xs1.append(x + w), ys1.append(y + h)
        m = int(margin * self.k)
        return int(min(xs0)) - m, int(min(ys0)) - m, int(max(xs1)) + m + 1, int(max(ys1)) + m + 1

    def _paint_animated(self, node: Node, layer: Layer, clip, st: dict):
        """One frame of an enter/leave animation: offset, scale, rotation, opacity, unroll."""
        if st["gone"] or st["alpha"] <= 0.01 or st["scale"] <= 0.01 or (st["reveal"] and st["reveal_frac"] <= 0.005):
            return
        bx0, by0, bx1, by1 = self._subtree_bounds(node, 48)
        if (bx1 - bx0) * (by1 - by0) > 60_000_000:
            return
        tmp = Layer(bx0, by0, bx1 - bx0, by1 - by0)
        node._anim_done = True
        try:
            self.paint(node, tmp, (bx0, by0, bx1, by1))
        finally:
            node._anim_done = False
        x, y, w, h = node.rect
        if st["reveal"] and st["reveal_frac"] < 0.995:
            rx0, ry0 = int(x) - bx0, int(y) - by0
            if st["reveal"] == "down":
                cut = ry0 + int(h * st["reveal_frac"])
                tmp.a[max(0, cut):, :, :] = 0
            else:
                cut = rx0 + int(w * st["reveal_frac"])
                tmp.a[:, max(0, cut):, :] = 0
        img = Image.fromarray((np.clip(tmp.a, 0, 1) * 255 + 0.5).astype(np.uint8), "RGBA")
        cx, cy = x + w / 2 - bx0, y + h / 2 - by0
        if abs(st["scale"] - 1) > 0.005:
            nw, nh = max(1, int(img.width * st["scale"])), max(1, int(img.height * st["scale"]))
            scaled = img.resize((nw, nh), Image.BICUBIC)
            out = Image.new("RGBA", img.size, (0, 0, 0, 0))
            out.paste(scaled, (int(cx - cx * st["scale"]), int(cy - cy * st["scale"])))
            img = out
        if abs(st["rot"]) > 0.05:
            img = img.rotate(-st["rot"], resample=Image.BICUBIC, center=(cx, cy))
        tmp.a = np.asarray(img, dtype=F) / 255
        unit = node.parent.px if node.parent is not None and hasattr(node.parent, "px") else self.k
        tmp.ox += int(round(st["dx"] * unit))
        tmp.oy += int(round(st["dy"] * unit))
        layer.composite(tmp, opacity=st["alpha"], clip=clip)

    def _paint_rotated(self, node: Node, layer: Layer, clip, rot: float):
        bx0, by0, bx1, by1 = self._subtree_bounds(node)
        tmp = Layer(bx0, by0, bx1 - bx0, by1 - by0)
        saved = node.props.get("Rotation")
        node.props["Rotation"] = 0.0
        try:
            self.paint(node, tmp, (bx0, by0, bx1, by1))
        finally:
            if saved is None:
                node.props.pop("Rotation", None)
            else:
                node.props["Rotation"] = saved
        x, y, w, h = node.rect
        cx, cy = x + w / 2 - bx0, y + h / 2 - by0
        img = Image.fromarray((np.clip(tmp.a, 0, 1) * 255 + 0.5).astype(np.uint8), "RGBA")
        # premultiplied data rotates correctly with bicubic resampling
        img = img.rotate(-rot, resample=Image.BICUBIC, center=(cx, cy))
        tmp.a = np.asarray(img, dtype=F) / 255
        layer.composite(tmp, clip=clip)

    def _paint_group(self, node: Node, layer: Layer, clip):
        x, y, w, h = self._irect(node)
        if w <= 0 or h <= 0:
            return
        tmp = Layer(x, y, w, h)
        self._paint_self(node, tmp, (x, y, x + w, y + h), strokes=False, shadows=False, use_gradient=False)
        self.paint_children(node, tmp, (x, y, x + w, y + h))
        radii = L.corner_radii(node, w, h, node.px)
        mask = cov(sdf_box(w, h, radii, 0))
        g = node.child("UIGradient")
        tint = effective(node, "GroupColor3") or (1, 1, 1)
        opacity = 1 - (effective(node, "GroupTransparency") or 0.0)
        if g is not None:
            rgb, am = fill_paint((1, 1, 1), g, w, h, 0)
            if isinstance(am, np.ndarray):
                mask = mask * am
            if rgb.ndim == 3:
                tmp.a[..., :3] *= rgb
        self._paint_shadows(node, layer, clip, inset=False)
        layer.composite(tmp, opacity=opacity, mask=mask, tint=tint, clip=clip)
        self._paint_strokes(node, layer, clip)

    def _paint_self(self, node: Node, layer: Layer, clip, strokes=True, shadows=True, use_gradient=True):
        x, y, w, h = self._irect(node)
        if w <= 0 or h <= 0:
            if node.cls in TEXT_CLASSES:
                self._paint_text(node, layer, clip)
            return
        px = node.px
        radii = L.corner_radii(node, w, h, px)
        grad = node.child("UIGradient") if use_gradient else None
        if shadows:
            self._paint_shadows(node, layer, clip, inset=False)
        bt = effective(node, "BackgroundTransparency")
        if bt is None:
            bt = 1.0
        d0 = None
        if bt < 1:
            d0 = sdf_box(w, h, radii, 0)
            rgb, am = fill_paint(effective(node, "BackgroundColor3"), grad, w, h, 0)
            layer.blend(x, y, rgb, cov(d0) * am * (1 - bt), clip)
        if node.cls in IMAGE_CLASSES:
            self._paint_image(node, layer, clip, radii, grad)
        if node.cls == "ViewportFrame":
            self._paint_placeholder(node, layer, clip, radii, "3D")
        if shadows:
            self._paint_shadows(node, layer, clip, inset=True)
        if node.cls in TEXT_CLASSES:
            self._paint_text(node, layer, clip)
        bs = effective(node, "BorderSizePixel") or 0
        if bs > 0:
            m = int(bs * px) + 2
            d = sdf_box(w, h, (0, 0, 0, 0), m, miter=True)
            band = cov(d - bs * px) * cov(-d)
            layer.blend(x - m, y - m, effective(node, "BorderColor3") or (0.1, 0.16, 0.2), band, clip)
        if strokes:
            self._paint_strokes(node, layer, clip)

    def _paint_strokes(self, node: Node, layer: Layer, clip):
        strokes = [s for s in node.children_of("UIStroke") if s.props.get("Enabled") is not False]
        is_text = node.cls in TEXT_CLASSES
        border = [s for s in strokes if not is_text or s.props.get("ApplyStrokeMode", "Contextual") == "Border"]
        if not border:
            return
        x, y, w, h = self._irect(node)
        if w <= 0 or h <= 0:
            return
        px = node.px
        radii = L.corner_radii(node, w, h, px)
        short = min(w, h)
        for s in sorted(border, key=lambda s: s.props.get("ZIndex", 1)):
            th = s.props.get("Thickness", 1.0)
            th = th * short if s.props.get("StrokeSizingMode") == "ScaledSize" else th * px
            if th <= 0:
                continue
            off_u = s.props.get("BorderOffset", (0.0, 0.0))
            off = off_u[0] * short + off_u[1] * px
            pos = s.props.get("BorderStrokePosition", "Outer")
            lo, hi = {"Outer": (0.0, th), "Center": (-th / 2, th / 2), "Inner": (-th, 0.0)}[pos]
            lo, hi = lo + off, hi + off
            m = int(max(hi, 0)) + 2
            miter = s.props.get("LineJoinMode", "Round") != "Round" and max(radii) < 0.5
            d = sdf_box(w, h, radii, m, miter=miter)
            band = cov(d - hi) * cov(lo - d)
            g = s.child("UIGradient")
            rgb, am = fill_paint(s.props.get("Color", (0, 0, 0)), g, w, h, m)
            layer.blend(x - m, y - m, rgb, band * am * (1 - s.props.get("Transparency", 0.0)), clip)

    def _paint_shadows(self, node: Node, layer: Layer, clip, inset: bool):
        shadows = [s for s in node.children_of("UIShadow")
                   if s.props.get("Enabled") is not False and s.props.get("Mode", "Shape") == "Shape"
                   and bool(s.props.get("Inset", False)) == inset]
        if not shadows:
            return
        x, y, w, h = self._irect(node)
        if w <= 0 or h <= 0:
            return
        px = node.px
        radii = L.corner_radii(node, w, h, px)
        short = min(w, h)
        for s in sorted(shadows, key=lambda s: s.props.get("ZIndex", -1)):
            bu = s.props.get("BlurRadius", (0.0, 0.0))
            blur = max(0.0, bu[0] * short + bu[1] * px)
            o = s.props.get("Offset", (0, 0, 0, 0))
            ox, oy = o[0] * w + o[1] * px, o[2] * h + o[3] * px
            sp = s.props.get("Spread", (0, 0, 0, 0))
            spx, spy = sp[0] * w + sp[1] * px, sp[2] * h + sp[3] * px
            spread = (spx + spy) / 2
            alpha_mul = 1 - s.props.get("Transparency", 0.0)
            g = s.child("UIGradient")
            if inset:
                d = sdf_box(w, h, radii, 0)
                # shadow caster = everything outside the shape, shifted by the offset and grown by spread
                ys = np.arange(h, dtype=F) + 0.5 - h / 2 - oy
                xs = np.arange(w, dtype=F) + 0.5 - w / 2 - ox
                d_shift = _sdf_at(xs, ys, w, h, radii)
                a = (1 - soft(d_shift + spread, blur)) * cov(d)
                rgb, am = fill_paint(s.props.get("Color", (0, 0, 0)), g, w, h, 0)
                layer.blend(x, y, rgb, a * am * alpha_mul, clip)
            else:
                m = int(blur * 1.6 + abs(spread) + max(abs(ox), abs(oy))) + 3
                ys = np.arange(-m, h + m, dtype=F) + 0.5 - h / 2 - oy
                xs = np.arange(-m, w + m, dtype=F) + 0.5 - w / 2 - ox
                d_shift = _sdf_at(xs, ys, w, h, radii)
                a = soft(d_shift - spread, blur)
                if s.props.get("ShowBehindParent") is False:
                    a = a * (1 - cov(sdf_box(w, h, radii, m)))
                rgb, am = fill_paint(s.props.get("Color", (0, 0, 0)), g, w, h, m)
                layer.blend(x - m, y - m, rgb, a * am * alpha_mul, clip)

    def _paint_placeholder(self, node: Node, layer: Layer, clip, radii, label: str):
        x, y, w, h = self._irect(node)
        d = sdf_box(w, h, radii, 0)
        yy, xx = np.mgrid[0:h, 0:w]
        hatch = (((xx + yy) // max(4, int(6 * self.k))) % 2).astype(F)
        rgb = np.stack([0.55 + 0.1 * hatch] * 3, axis=-1) * np.array([1.0, 0.45, 0.85], dtype=F)
        layer.blend(x, y, rgb, cov(d) * 0.55, clip)
        try:
            f = fonts.get({"family": "Montserrat", "weight": "Bold"}, max(9, min(h * 0.3, 14 * self.k)))
            img = Image.new("L", (w, h), 0)
            ImageDraw.Draw(img).text((w / 2, h / 2), label, font=f, fill=255, anchor="mm")
            layer.blend(x, y, (1, 1, 1), np.asarray(img, dtype=F) / 255, clip)
        except Exception:
            pass

    def _paint_image(self, node: Node, layer: Layer, clip, radii, grad):
        ref = effective(node, "Image") or effective(node, "ImageContent") or ""
        if not ref:
            return
        x, y, w, h = self._irect(node)
        img = self.load_image(ref)
        if img is None:
            self._paint_placeholder(node, layer, clip, radii, "IMG")
            return
        px = node.px
        ro = effective(node, "ImageRectOffset") or (0, 0)
        rs = effective(node, "ImageRectSize") or (0, 0)
        if rs[0] > 0 and rs[1] > 0:
            img = img.crop((int(ro[0]), int(ro[1]), int(ro[0] + rs[0]), int(ro[1] + rs[1])))
        mode = effective(node, "ScaleType") or "Stretch"
        resample = Image.NEAREST if effective(node, "ResampleMode") == "Pixelated" else Image.LANCZOS
        out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        iw, ih = img.size
        if mode == "Stretch":
            out = img.resize((w, h), resample)
        elif mode in ("Fit", "Crop"):
            r = min(w / iw, h / ih) if mode == "Fit" else max(w / iw, h / ih)
            nw, nh = max(1, int(round(iw * r))), max(1, int(round(ih * r)))
            im2 = img.resize((nw, nh), resample)
            out.paste(im2, ((w - nw) // 2, (h - nh) // 2))
        elif mode == "Tile":
            ts = effective(node, "TileSize") or (1, 0, 1, 0)
            tw = max(1, int(round(ts[0] * w + ts[1] * px)))
            th = max(1, int(round(ts[2] * h + ts[3] * px)))
            tile = img.resize((tw, th), resample)
            for ty in range(0, h, th):
                for tx in range(0, w, tw):
                    out.paste(tile, (tx, ty))
        elif mode == "Slice":
            out = _nine_slice(img, w, h, effective(node, "SliceCenter") or (0, 0, 0, 0),
                              (effective(node, "SliceScale") or 1.0) * px, resample)
        arr = np.asarray(out, dtype=F) / 255
        rgb, am = fill_paint(effective(node, "ImageColor3") or (1, 1, 1), grad, w, h, 0)
        a = arr[..., 3] * (1 - (effective(node, "ImageTransparency") or 0.0)) * am
        if max(radii) > 0:
            a = a * cov(sdf_box(w, h, radii, 0))
        layer.blend(x, y, arr[..., :3] * rgb, a, clip)

    def _paint_scrollbar(self, node: Node, layer: Layer, clip):
        x, y, w, h = self._irect(node)
        canvas = getattr(node, "canvas", (w, h))
        th = int((effective(node, "ScrollBarThickness") or 0) * node.px)
        if th <= 0 or canvas[1] <= h + 1:
            return
        frac = h / canvas[1]
        bar_h = max(int(th * 2), int(h * frac))
        a = np.full((bar_h, th), 1 - (effective(node, "ScrollBarImageTransparency") or 0.0), dtype=F)
        layer.blend(x + w - th, y, effective(node, "ScrollBarImageColor3") or (1, 1, 1), a, clip)

    def _paint_text(self, node: Node, layer: Layer, clip):
        x, y, w, h = node.rect
        px = node.px
        pl, pt, pr, pb = L.padding(node, w, h, px)
        tx, ty, tw, th = x + pl, y + pt, max(0.0, w - pl - pr), max(0.0, h - pt - pb)
        if not L.plain_text(node).strip():
            placeholder = effective(node, "PlaceholderText") if node.cls == "TextBox" else None
            if not placeholder:
                return
        tl = L.text_layout(node, tw, th, px)
        font, lines, lh = tl["font"], tl["lines"], tl["line_h"]
        color = effective(node, "TextColor3") or (0.1, 0.16, 0.2)
        if node.cls == "TextBox" and not any(l.strip() for l in lines):
            lines = [effective(node, "PlaceholderText")]
            color = effective(node, "PlaceholderColor3") or (0.5, 0.5, 0.5)
        if (effective(node, "TextTruncate") or "None") != "None" and lines:
            maxl = max(1, int(th // max(lh, 1))) if th > 0 else 1
            if len(lines) > maxl:
                lines = lines[:maxl]
                lines[-1] = lines[-1].rstrip() + "…"
            last = lines[-1]
            while font.getlength(last) > tw and len(last) > 1:
                last = last[:-2].rstrip() + "…"
            lines[-1] = last
        xa = {"Left": 0.0, "Center": 0.5, "Right": 1.0}[effective(node, "TextXAlignment") or "Center"]
        ya = {"Top": 0.0, "Center": 0.5, "Bottom": 1.0}[effective(node, "TextYAlignment") or "Center"]
        block_h = lh * len(lines)
        widths = [font.getlength(l) for l in lines]
        max_w = max(widths) if widths else 0

        text_strokes = [s for s in node.children_of("UIStroke")
                        if s.props.get("Enabled") is not False and s.props.get("ApplyStrokeMode", "Contextual") == "Contextual"]
        stroke_px = 0.0
        stroke = text_strokes[0] if text_strokes else None
        if stroke:
            stroke_px = stroke.props.get("Thickness", 1.0)
            stroke_px = stroke_px * tl["size"] if stroke.props.get("StrokeSizingMode") == "ScaledSize" else stroke_px * px
        legacy_t = effective(node, "TextStrokeTransparency")
        legacy = legacy_t is not None and legacy_t < 1 and not stroke
        text_shadows = [s for s in node.children_of("UIShadow")
                        if s.props.get("Enabled") is not False and s.props.get("Mode", "Shape") == "Text"]
        shadow_extent = 0.0
        for s in text_shadows:
            bu = s.props.get("BlurRadius", (0.0, 0.0))
            o = s.props.get("Offset", (0, 0, 0, 0))
            shadow_extent = max(shadow_extent, bu[0] * min(w, h) + bu[1] * px + abs(o[1] * px) + abs(o[3] * px))

        m = int(stroke_px + shadow_extent * 2 + 4 * self.k) + 2
        bx0 = int(math.floor(min(tx, tx + (tw - max_w) * xa))) - m
        by0 = int(math.floor(min(ty, ty + (th - block_h) * ya))) - m
        bx1 = int(math.ceil(max(tx + tw, tx + (tw - max_w) * xa + max_w))) + m
        by1 = int(math.ceil(max(ty + th, ty + (th - block_h) * ya + block_h))) + m
        bw, bh = bx1 - bx0, by1 - by0
        if bw <= 0 or bh <= 0 or bw * bh > 40_000_000:
            return
        # Small text is drawn 3x larger and scaled down: at tiny pixel sizes hinting rounds each glyph
        # advance to whole pixels and opens random gaps inside words.
        ss = 3 if tl["size"] < 30 else 1
        draw_font = fonts.get(tl["face"], tl["size"] * ss) if ss > 1 else font
        ascent, descent = draw_font.getmetrics()
        base_scale = tl["size"] * ss / max(1, ascent + descent)
        if ss > 1:
            widths = [draw_font.getlength(l) / ss for l in lines]

        def mask(stroke_w: float):
            img = Image.new("L", (bw * ss, bh * ss), 0)
            dr = ImageDraw.Draw(img)
            for i, (line, lw) in enumerate(zip(lines, widths)):
                lx = tx + (tw - lw) * xa - bx0
                top = ty + (th - block_h) * ya + i * lh - by0
                baseline = top * ss + (lh - tl["size"]) * ss / 2 + ascent * base_scale
                dr.text((lx * ss, baseline), line, font=draw_font, fill=255, anchor="ls",
                        stroke_width=int(round(stroke_w * ss)), stroke_fill=255)
            if ss > 1:
                img = img.resize((bw, bh), Image.LANCZOS)
            return np.asarray(img, dtype=F) / 255

        fill_mask = mask(0)
        tt = effective(node, "TextTransparency") or 0.0
        grad = node.child("UIGradient")
        gx, gy, gw, gh = self._irect(node)

        def paint_for(base, g):
            if g is None or gw <= 0 or gh <= 0:
                return np.asarray(base, dtype=F), 1.0
            # gradient spans the label's box; sample it on the text patch grid
            t_full = _gradient_on_patch(g, gw, gh, bx0 - gx, by0 - gy, bw, bh)
            rgb = np.asarray(base, dtype=F)
            if "Color" in g.props:
                rgb = gradient_color(t_full, g.props["Color"]) * rgb
            am = gradient_alpha(t_full, g.props["Transparency"]) if "Transparency" in g.props else 1.0
            return rgb, am

        for s in sorted(text_shadows, key=lambda s: s.props.get("ZIndex", -1)):
            bu = s.props.get("BlurRadius", (0.0, 0.0))
            blur = max(0.0, bu[0] * min(w, h) + bu[1] * px)
            o = s.props.get("Offset", (0, 0, 0, 0))
            ox, oy = int(round(o[0] * w + o[1] * px)), int(round(o[2] * h + o[3] * px))
            base_mask = mask(stroke_px) if stroke_px >= 1 else fill_mask
            sm = base_mask
            if blur > 0.75:
                sm = np.asarray(Image.fromarray((base_mask * 255).astype(np.uint8), "L").filter(
                    ImageFilter.GaussianBlur(blur / 2)), dtype=F) / 255
            rgb, am = paint_for(s.props.get("Color", (0, 0, 0)), s.child("UIGradient"))
            layer.blend(bx0 + ox, by0 + oy, rgb, sm * am * (1 - s.props.get("Transparency", 0.0)), clip)
        if stroke and stroke_px >= 0.5:
            sm = mask(max(1.0, stroke_px))
            rgb, am = paint_for(stroke.props.get("Color", (0, 0, 0)), stroke.child("UIGradient"))
            layer.blend(bx0, by0, rgb, sm * am * (1 - stroke.props.get("Transparency", 0.0)), clip)
        elif legacy:
            sm = mask(max(1.0, px))
            layer.blend(bx0, by0, effective(node, "TextStrokeColor3") or (0, 0, 0), sm * (1 - legacy_t), clip)
        if tt < 1:
            rgb, am = paint_for(color, grad)
            layer.blend(bx0, by0, rgb, fill_mask * am * (1 - tt), clip)
        if not tl["fits"] and not effective(node, "TextScaled"):
            self.notes.append((node.path, f"text {effective(node, 'Text')!r} overflows its box "
                               f"({tl['width'] / self.k:.0f}x{tl['height'] / self.k:.0f} in "
                               f"{tw / self.k:.0f}x{th / self.k:.0f}) on {self.device}"))


def _sdf_at(xs, ys, w, h, radii):
    X, Y = np.meshgrid(xs, ys)
    tl, tr, br, bl = radii
    r = np.where(Y < 0, np.where(X < 0, tl, tr), np.where(X < 0, bl, br)).astype(F)
    qx = np.abs(X) - (w / 2 - r)
    qy = np.abs(Y) - (h / 2 - r)
    return np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0) - r


def _gradient_on_patch(g: Node, w: int, h: int, px0: int, py0: int, pw: int, ph: int):
    """gradient_t for a w x h box, sampled on a patch at offset (px0, py0) of size pw x ph."""
    ys = np.arange(py0, py0 + ph, dtype=F) + 0.5
    xs = np.arange(px0, px0 + pw, dtype=F) + 0.5
    X, Y = np.meshgrid(xs, ys)
    off = g.props.get("Offset", (0.0, 0.0))
    cx, cy = w / 2 + off[0] * w, h / 2 + off[1] * h
    rot = math.radians(g.props.get("Rotation", 0.0))
    scale = max(0.001, g.props.get("Scale", 1.0))
    kind = g.props.get("Type", "Linear")
    dx, dy = X - cx, Y - cy
    if kind == "Radial":
        t = np.hypot(dx, dy) / max(1e-6, (w + h) / 4 * scale)
    elif kind == "Elliptical":
        t = np.hypot(dx / max(1e-6, w / 2), dy / max(1e-6, h / 2)) / scale
    else:
        c, s = math.cos(rot), math.sin(rot)
        t = 0.5 + (dx * c + dy * s) / (max(1e-6, abs(w * c) + abs(h * s)) * scale)
    return np.clip(t, 0, 1).astype(F)


def _nine_slice(img: Image.Image, w: int, h: int, center, scale: float, resample):
    iw, ih = img.size
    x0, y0, x1, y1 = (int(v) for v in center)
    if x1 <= x0 or y1 <= y0:
        return img.resize((w, h), resample)
    l, t, r, b = x0, y0, iw - x1, ih - y1
    dl, dt, dr, db = (max(0, int(round(v * scale))) for v in (l, t, r, b))
    if dl + dr > w:
        f = w / max(1, dl + dr)
        dl, dr = int(dl * f), w - int(dl * f)
    if dt + db > h:
        f = h / max(1, dt + db)
        dt, db = int(dt * f), h - int(dt * f)
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sx = [(0, x0, 0, dl), (x0, x1, dl, w - dr), (x1, iw, w - dr, w)]
    sy = [(0, y0, 0, dt), (y0, y1, dt, h - db), (y1, ih, h - db, h)]
    for (sx0, sx1, dx0, dx1) in sx:
        for (sy0, sy1, dy0, dy1) in sy:
            if sx1 <= sx0 or sy1 <= sy0 or dx1 <= dx0 or dy1 <= dy0:
                continue
            piece = img.crop((sx0, sy0, sx1, sy1)).resize((dx1 - dx0, dy1 - dy0), resample)
            out.paste(piece, (dx0, dy0))
    return out


# ------------------------------------------------------------------ public helpers

def find_nodes(root: Node, name: str):
    return [n for n in root.walk() if n.name == name and hasattr(n, "rect")]


def render(spec: Spec, device="pc", scale=1.0, backdrop=None, chrome=True, asset_dirs=None):
    r = Renderer(spec, device, scale, asset_dirs, backdrop, chrome)
    img = r.render()
    return img, r


def crop_node(img: Image.Image, node: Node, margin: int = 24):
    x, y, w, h = node.rect
    box = (max(0, int(x) - margin), max(0, int(y) - margin),
           min(img.width, int(x + w) + margin), min(img.height, int(y + h) + margin))
    return img.crop(box)
