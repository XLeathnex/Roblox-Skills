"""Colour maths for rbxui.

Everything works on (r, g, b) float tuples in 0..1 (sRGB). Shading is done in
OKLCH so that "darker" also shifts hue toward cool and gains a little chroma,
and "lighter" shifts toward warm and loses chroma. That is what a painter does
and it is the difference between a shade that belongs to the fill and one that
looks like grey was poured on it.
"""
from __future__ import annotations

import math
import re

Color = tuple  # (r, g, b) floats 0..1

NAMED = {
    "white": "#FFFFFF",
    "black": "#000000",
}


def parse_hex(s: str) -> Color:
    s = s.strip()
    if s.lower() in NAMED:
        s = NAMED[s.lower()]
    if not s.startswith("#"):
        raise ValueError(f"not a hex colour: {s!r}")
    h = s[1:]
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6 or not re.fullmatch(r"[0-9a-fA-F]{6}", h):
        raise ValueError(f"bad hex colour: {s!r} (use #RRGGBB)")
    return tuple(int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))


def to_hex(c: Color) -> str:
    return "#" + "".join(f"{max(0, min(255, round(v * 255))):02X}" for v in c)


def to_rgb255(c: Color) -> tuple:
    return tuple(max(0, min(255, round(v * 255))) for v in c)


# ---- sRGB <-> OKLab ---------------------------------------------------------

def _lin(u: float) -> float:
    return u / 12.92 if u <= 0.04045 else ((u + 0.055) / 1.055) ** 2.4


def _gam(u: float) -> float:
    return 12.92 * u if u <= 0.0031308 else 1.055 * (max(u, 0.0) ** (1 / 2.4)) - 0.055


def to_oklab(c: Color) -> tuple:
    r, g, b = (_lin(v) for v in c)
    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l_, m_, s_ = (math.copysign(abs(v) ** (1 / 3), v) for v in (l, m, s))
    return (
        0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
        1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
        0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_,
    )


def _oklab_to_linear(L: float, a: float, b: float) -> tuple:
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b
    l, m, s = l_ ** 3, m_ ** 3, s_ ** 3
    return (
        4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
        -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
        -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s,
    )


def from_oklab(L: float, a: float, b: float) -> Color:
    return tuple(min(1.0, max(0.0, _gam(v))) for v in _oklab_to_linear(L, a, b))


def to_oklch(c: Color) -> tuple:
    L, a, b = to_oklab(c)
    return L, math.hypot(a, b), math.degrees(math.atan2(b, a)) % 360


def _in_gamut(L: float, C: float, hr: float) -> bool:
    lin = _oklab_to_linear(L, C * math.cos(hr), C * math.sin(hr))
    return all(-1e-4 <= v <= 1 + 1e-4 for v in lin)


def from_oklch(L: float, C: float, h: float) -> Color:
    """OKLCH -> sRGB, reducing chroma until the colour is in gamut."""
    L = min(1.0, max(0.0, L))
    C = max(0.0, C)
    hr = math.radians(h)
    if not _in_gamut(L, C, hr):
        lo, hi = 0.0, C
        for _ in range(20):
            mid = (lo + hi) / 2
            if _in_gamut(L, mid, hr):
                lo = mid
            else:
                hi = mid
        C = lo
    return from_oklab(L, C * math.cos(hr), C * math.sin(hr))


def _hue_toward(h: float, target: float, amount: float) -> float:
    d = ((target - h + 180) % 360) - 180
    if abs(d) <= amount:
        return target
    return (h + math.copysign(amount, d)) % 360


# ---- designer operations ----------------------------------------------------

def shade(c: Color, steps: float) -> Color:
    """Painterly shade ramp. steps<0 = shadow side, steps>0 = light side.

    One step is about 0.065 OKLab lightness. Shadows drift toward blue-violet
    and keep their chroma; lights drift toward yellow and wash out slightly.
    """
    L, C, h = to_oklch(c)
    n = abs(steps)
    if steps < 0:
        # never fall off a cliff into black: compress as we approach 0
        L2 = L - min(0.065 * n, L * (1 - 0.74 ** n))
        C2 = C * (1 + 0.03 * n) if C > 0.02 else C
        h2 = _hue_toward(h, 275, min(4.5 * n, 22)) if C > 0.02 else h
    else:
        L2 = L + min(0.065 * n, (1 - L) * (1 - 0.72 ** n))
        C2 = C * max(0.35, 1 - 0.09 * n)
        h2 = _hue_toward(h, 95, min(3.5 * n, 16)) if C > 0.02 else h
    return from_oklch(L2, C2, h2)


def darken(c: Color, amount: float) -> Color:
    L, C, h = to_oklch(c)
    return from_oklch(L - amount, C, h)


def lighten(c: Color, amount: float) -> Color:
    L, C, h = to_oklch(c)
    return from_oklch(L + amount, C, h)


def saturate(c: Color, factor: float) -> Color:
    L, C, h = to_oklch(c)
    return from_oklch(L, C * factor, h)


def hue(c: Color, degrees: float) -> Color:
    L, C, h = to_oklch(c)
    return from_oklch(L, C, (h + degrees) % 360)


def mix(a: Color, b: Color, t: float) -> Color:
    la, lb = to_oklab(a), to_oklab(b)
    return from_oklab(*(x + (y - x) * t for x, y in zip(la, lb)))


def luminance(c: Color) -> float:
    r, g, b = (_lin(v) for v in c)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: Color, b: Color) -> float:
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def ink(bg: Color) -> Color:
    """A readable text colour for `bg`: warm off-white on dark, tinted near-black on light."""
    L, C, h = to_oklch(bg)
    if luminance(bg) < 0.36:
        return from_oklch(0.97, min(C, 0.02), h)
    return from_oklch(0.22, min(C * 0.5, 0.05), h)


def chroma(c: Color) -> float:
    return to_oklch(c)[1]


def hsv(c: Color) -> tuple:
    import colorsys

    h, s, v = colorsys.rgb_to_hsv(*c)
    return h * 360, s, v


FUNCS = {
    "shade": (shade, "cn"),
    "darken": (darken, "cn"),
    "lighten": (lighten, "cn"),
    "saturate": (saturate, "cn"),
    "hue": (hue, "cn"),
    "mix": (mix, "ccn"),
    "ink": (ink, "c"),
}


class ColorExprError(ValueError):
    pass


def evaluate(expr: str, lookup) -> Color:
    """Evaluate a colour expression.

    Grammar:  expr := '#RRGGBB' | '$token.path' | func '(' arg {',' arg} ')'
    `lookup(name)` resolves a token name to another expression string.
    """
    src = expr.strip()
    pos = 0

    def ws():
        nonlocal pos
        while pos < len(src) and src[pos].isspace():
            pos += 1

    def parse(depth=0):
        nonlocal pos
        if depth > 24:
            raise ColorExprError(f"colour expression too deep (token cycle?): {expr!r}")
        ws()
        if pos >= len(src):
            raise ColorExprError(f"unexpected end of colour expression: {expr!r}")
        ch = src[pos]
        if ch == "#":
            m = re.match(r"#[0-9a-fA-F]{3,6}", src[pos:])
            if not m:
                raise ColorExprError(f"bad hex in {expr!r}")
            pos += m.end()
            return parse_hex(m.group(0))
        if ch == "$":
            m = re.match(r"\$([A-Za-z0-9_.\-]+)", src[pos:])
            if not m:
                raise ColorExprError(f"bad token reference in {expr!r}")
            pos += m.end()
            target = lookup(m.group(1))
            if isinstance(target, tuple):
                return target
            return evaluate(str(target), lookup)
        m = re.match(r"([a-zA-Z_]+)\s*\(", src[pos:])
        if m:
            name = m.group(1)
            if name not in FUNCS:
                raise ColorExprError(
                    f"unknown colour function {name!r} in {expr!r}; available: {', '.join(sorted(FUNCS))}"
                )
            fn, sig = FUNCS[name]
            pos += m.end()
            args = []
            for i, kind in enumerate(sig):
                ws()
                if kind == "c":
                    args.append(parse(depth + 1))
                else:
                    m2 = re.match(r"[-+]?\d*\.?\d+", src[pos:])
                    if not m2:
                        raise ColorExprError(f"expected a number for argument {i + 1} of {name}() in {expr!r}")
                    pos += m2.end()
                    args.append(float(m2.group(0)))
                ws()
                if i < len(sig) - 1:
                    if pos >= len(src) or src[pos] != ",":
                        raise ColorExprError(f"{name}() takes {len(sig)} arguments: {expr!r}")
                    pos += 1
            ws()
            if pos >= len(src) or src[pos] != ")":
                raise ColorExprError(f"missing ')' in {expr!r}")
            pos += 1
            return fn(*args)
        m = re.match(r"[A-Za-z]+", src[pos:])
        if m and m.group(0).lower() in NAMED:
            pos += m.end()
            return parse_hex(m.group(0))
        raise ColorExprError(f"cannot read colour {expr!r} (use '#RRGGBB', '$token' or shade($token, -2))")

    out = parse()
    ws()
    if pos != len(src):
        raise ColorExprError(f"trailing text in colour expression {expr!r}")
    return out
