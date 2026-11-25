"""Stand-in game worlds to preview UI over, plus the Roblox chrome a HUD has to avoid.

UI is never seen on a blank canvas: it sits over a moving 3D scene, under the
Roblox top bar, and on phones next to the thumbstick and jump button. Previewing
over a plausible scene is what reveals unreadable text and blocked controls.
"""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

KINDS = ["day", "sunset", "night", "horror", "interior", "arena", "space", "forest", "flat-light", "flat-dark"]

_GENRE = {
    "simulator": "day", "clicker": "day", "pet": "day", "tycoon": "day", "obby": "day", "party": "day",
    "roleplay": "day", "social": "day", "life": "day", "brainrot": "day",
    "horror": "horror", "story": "interior", "narrative": "interior", "cinematic": "interior",
    "fps": "arena", "shooter": "arena", "milsim": "arena", "pvp": "arena", "fighting": "arena",
    "anime": "sunset", "rpg": "forest", "fantasy": "forest", "survival": "forest", "medieval": "forest",
    "scifi": "space", "sci-fi": "space", "cyberpunk": "night", "racing": "sunset", "sports": "arena",
    "tower": "day", "gacha": "sunset",
}


def for_genre(genre: str) -> str:
    g = (genre or "").lower()
    for key, kind in _GENRE.items():
        if key in g:
            return kind
    return "day"


def _vgrad(w, h, stops):
    """stops: [(t, (r,g,b)), ...] top->bottom, 0..255."""
    ts = np.array([s[0] for s in stops], dtype=np.float32)
    cols = np.array([s[1] for s in stops], dtype=np.float32)
    t = np.linspace(0, 1, h, dtype=np.float32)
    col = np.stack([np.interp(t, ts, cols[:, i]) for i in range(3)], axis=-1)
    return np.repeat(col[:, None, :], w, axis=1)


_SCENES = {
    #            sky stops                                              ground near/far            block colours                      fog
    "day": ([(0, (86, 160, 236)), (0.55, (176, 216, 248))], ((92, 168, 84), (132, 196, 120)),
            [(214, 86, 74), (240, 196, 84), (120, 132, 150), (250, 250, 250)], (190, 222, 248)),
    "sunset": ([(0, (58, 44, 110)), (0.3, (214, 96, 110)), (0.55, (255, 190, 120))], ((92, 70, 96), (190, 120, 110)),
               [(70, 50, 90), (120, 64, 92), (44, 36, 70)], (255, 176, 130)),
    "night": ([(0, (8, 10, 28)), (0.55, (30, 34, 78))], ((16, 18, 34), (36, 40, 74)),
              [(20, 22, 40), (255, 84, 180), (60, 220, 240), (30, 30, 54)], (40, 44, 90)),
    "horror": ([(0, (4, 5, 7)), (0.55, (18, 20, 22))], ((8, 8, 9), (26, 26, 26)),
               [(14, 14, 15), (22, 20, 18), (10, 10, 12)], (20, 21, 22)),
    "interior": ([(0, (38, 34, 40)), (0.55, (92, 80, 76))], ((54, 44, 40), (104, 86, 74)),
                 [(70, 58, 54), (120, 98, 80), (50, 44, 48)], (110, 96, 88)),
    "arena": ([(0, (96, 110, 128)), (0.55, (176, 186, 198))], ((84, 90, 98), (140, 146, 154)),
              [(70, 76, 86), (196, 92, 60), (60, 100, 150), (110, 116, 126)], (170, 180, 192)),
    "space": ([(0, (4, 6, 18)), (0.55, (16, 24, 56))], ((14, 18, 30), (34, 44, 74)),
              [(30, 40, 66), (60, 200, 230), (22, 28, 46)], (24, 34, 70)),
    "forest": ([(0, (110, 150, 150)), (0.55, (190, 210, 170))], ((52, 86, 50), (104, 140, 84)),
               [(40, 70, 44), (88, 62, 44), (60, 100, 60), (120, 110, 100)], (170, 196, 160)),
}


def make(kind: str, w: int, h: int) -> Image.Image:
    if kind and kind not in KINDS:
        try:
            return Image.open(kind).convert("RGB").resize((w, h), Image.LANCZOS).convert("RGBA")
        except Exception:
            kind = "day"
    if kind == "flat-light":
        return Image.new("RGBA", (w, h), (214, 218, 224, 255))
    if kind == "flat-dark":
        return Image.new("RGBA", (w, h), (24, 26, 30, 255))
    sky, (g_near, g_far), blocks, fog = _SCENES.get(kind, _SCENES["day"])
    horizon = int(h * 0.56)
    arr = _vgrad(w, h, sky + [(1.0, sky[-1][1])])
    ground = _vgrad(w, h - horizon, [(0, g_far), (1, g_near)])
    arr[horizon:] = ground
    img = Image.fromarray(arr.astype(np.uint8), "RGB")
    d = ImageDraw.Draw(img, "RGBA")
    rng = np.random.default_rng(7)
    # perspective studs/grid on the ground
    cx = w * 0.5
    line = tuple(int(c * 0.86) for c in g_near) + (70,)
    for i in range(-14, 15):
        d.line([(cx + i * w * 0.02, horizon), (cx + i * w * 0.24, h)], fill=line, width=max(1, w // 900))
    for j in range(1, 12):
        y = horizon + (h - horizon) * (j / 11) ** 2.2
        d.line([(0, y), (w, y)], fill=line, width=max(1, w // 900))
    # far silhouettes
    for i in range(18):
        bw = int(w * rng.uniform(0.03, 0.09))
        bh = int(h * rng.uniform(0.04, 0.22))
        bx = int(rng.uniform(-0.05, 1.0) * w)
        col = blocks[i % len(blocks)]
        mixed = tuple(int(c * 0.55 + f * 0.45) for c, f in zip(col, fog))
        d.rectangle([bx, horizon - bh, bx + bw, horizon], fill=mixed + (255,))
        d.rectangle([bx, horizon - bh, bx + bw, horizon - bh + max(2, bh // 14)],
                    fill=tuple(min(255, int(c * 1.12)) for c in mixed) + (255,))
    # near blocks with a lit top and shaded side
    for i in range(7):
        bw = int(w * rng.uniform(0.07, 0.16))
        bh = int(h * rng.uniform(0.12, 0.34))
        bx = int(rng.uniform(-0.05, 0.95) * w)
        by = int(horizon + (h - horizon) * rng.uniform(0.08, 0.5))
        col = blocks[(i * 2 + 1) % len(blocks)]
        side = tuple(int(c * 0.72) for c in col)
        top = tuple(min(255, int(c * 1.14)) for c in col)
        d.rectangle([bx, by - bh, bx + bw, by], fill=col + (255,))
        d.polygon([(bx + bw, by - bh), (bx + bw + bw * 0.18, by - bh - bh * 0.06),
                   (bx + bw + bw * 0.18, by - bh * 0.06), (bx + bw, by)], fill=side + (255,))
        d.polygon([(bx, by - bh), (bx + bw * 0.18, by - bh - bh * 0.06),
                   (bx + bw + bw * 0.18, by - bh - bh * 0.06), (bx + bw, by - bh)], fill=top + (255,))
    if kind in ("night", "space"):
        for _ in range(160):
            sx, sy = int(rng.uniform(0, w)), int(rng.uniform(0, horizon * 0.9))
            d.point((sx, sy), fill=(255, 255, 255, int(rng.uniform(60, 220))))
    if kind == "horror":
        # a weak light pool so the scene is not uniformly black
        glow = Image.new("L", (w, h), 0)
        ImageDraw.Draw(glow).ellipse([w * 0.3, h * 0.25, w * 0.7, h * 0.95], fill=70)
        glow = glow.filter(ImageFilter.GaussianBlur(w * 0.08))
        warm = Image.new("RGB", (w, h), (96, 82, 60))
        img = Image.composite(warm, img, glow)
    img = img.filter(ImageFilter.GaussianBlur(max(0.6, w / 1600)))
    return img.convert("RGBA")


def draw_chrome(img: Image.Image, device: str, k: float = 1.0, touch: bool = True) -> Image.Image:
    """Overlay the Roblox top-bar buttons and, on touch devices, the default thumbstick and jump button."""
    import layout as L

    vw, vh, topbar, safe, is_touch = L.DEVICES[device]
    touch = touch and is_touch
    over = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    s = lambda v: int(round(v * k))
    left = safe[0]
    # Roblox menu + chat buttons (44 px inside the 58 px top bar)
    for i in range(2):
        x0 = left + 12 + i * 52
        d.rounded_rectangle([s(x0), s(7), s(x0 + 44), s(51)], radius=s(22), fill=(18, 20, 24, 150))
        d.ellipse([s(x0 + 15), s(22), s(x0 + 29), s(36)], outline=(255, 255, 255, 190), width=max(1, s(2)))
    if touch:
        phone = min(vw, vh) <= 500
        jump = 70 if phone else 120
        jx, jy = (vw - 95, vh - 90) if phone else (vw - 170, vh - 210)
        d.ellipse([s(jx), s(jy), s(jx + jump), s(jy + jump)], fill=(255, 255, 255, 46),
                  outline=(255, 255, 255, 120), width=max(1, s(2)))
        ring = 74 if phone else 148
        tx, ty = (66, vh - 56 - ring) if phone else (132, vh - 112 - ring)
        d.ellipse([s(tx), s(ty), s(tx + ring), s(ty + ring)], fill=(255, 255, 255, 30),
                  outline=(255, 255, 255, 110), width=max(1, s(2)))
        d.ellipse([s(tx + ring * 0.3), s(ty + ring * 0.3), s(tx + ring * 0.7), s(ty + ring * 0.7)],
                  fill=(255, 255, 255, 70))
    return Image.alpha_composite(img.convert("RGBA"), over).convert("RGB")


def keep_clear_zones(device: str):
    """Rectangles (x0, y0, x1, y1) in device pixels that game UI must not cover, with a reason."""
    import layout as L

    vw, vh, topbar, safe, touch = L.DEVICES[device]
    zones = [((safe[0], 0, safe[0] + 124, topbar), "Roblox menu/chat buttons (top-left of the top bar)")]
    if touch:
        phone = min(vw, vh) <= 500
        if phone:
            zones.append(((vw - 110, vh - 110, vw, vh), "default jump button (bottom-right)"))
            zones.append(((40, vh - 150, 190, vh), "default thumbstick (bottom-left)"))
        else:
            zones.append(((vw - 190, vh - 230, vw - 30, vh - 70), "default jump button (bottom-right)"))
            zones.append(((100, vh - 290, 310, vh - 80), "default thumbstick (bottom-left)"))
    return zones
