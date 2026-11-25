"""Design and engineering lint for a UI spec.

Two kinds of rules:
  * engine rules  - things that are simply wrong in Roblox (unknown property,
                    gradient multiplied into a coloured base, UI under the top bar)
  * craft rules   - the measurable tells of generic machine-made UI (every shape
                    a pill, one font, a white blob pretending to be gloss, a
                    rainbow of button hues, flat rectangles with no light logic)

Craft rules read `meta.depth` so that a deliberately flat horror menu is not
told to add bevels, and a chunky simulator panel is not told to remove them.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict

import backdrop as backdrops
import color as C
import fonts
import layout as L
from spec import (BUTTON_CLASSES, GUI_OBJECTS, IMAGE_CLASSES, TEXT_CLASSES, Node, Spec, effective)

DEPTH_STYLES = ("flat", "soft", "chunky", "material")
DEFAULT_NAMES = set(GUI_OBJECTS) | {"UICorner", "UIStroke", "UIGradient"}
GENERIC_FONTS = {"LegacyArial", "SourceSansPro", "Arimo", "Roboto"}

_EMOJI = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF\U00002B00-\U00002BFF\U0000FE0F\U0001F000-\U0001F2FF]"
)


class Report:
    def __init__(self):
        self.items = []  # (severity, rule, path, message, fix)

    def add(self, severity, rule, path, message, fix=""):
        self.items.append((severity, rule, path, message, fix))

    def error(self, *a, **k):
        self.add("error", *a, **k)

    def warn(self, *a, **k):
        self.add("warn", *a, **k)

    def note(self, *a, **k):
        self.add("note", *a, **k)

    def count(self, severity):
        return sum(1 for i in self.items if i[0] == severity)

    def format(self, max_per_rule: int = 3) -> str:
        if not self.items:
            return "lint: clean (0 errors, 0 warnings)"
        order = {"error": 0, "warn": 1, "note": 2}
        by_rule = defaultdict(list)
        for it in self.items:
            by_rule[(order[it[0]], it[0], it[1])].append(it)
        lines = []
        for key in sorted(by_rule):
            _, sev, rule = key
            group = by_rule[key]
            label = {"error": "ERROR", "warn": "WARN", "note": "note"}[sev]
            msgs = {it[3] for it in group}
            if len(msgs) == 1:
                paths = []
                for it in group:
                    if it[2] not in paths:
                        paths.append(it[2])
                where = ", ".join(paths[:max_per_rule]) + (f" +{len(paths) - max_per_rule} more" if len(paths) > max_per_rule else "")
                times = f" x{len(group)}" if len(group) > 1 else ""
                lines.append(f"{label} {rule}{times} @ {where}: {group[0][3]}")
            else:
                for it in group[:max_per_rule]:
                    lines.append(f"{label} {rule} @ {it[2]}: {it[3]}")
                if len(group) > max_per_rule:
                    lines.append(f"  (+{len(group) - max_per_rule} more {rule})")
            fix = next((it[4] for it in group if it[4]), "")
            if fix:
                lines.append(f"  fix: {fix}")
        lines.append(f"lint: {self.count('error')} errors, {self.count('warn')} warnings, {self.count('note')} notes")
        return "\n".join(lines)


# ------------------------------------------------------------------ helpers

def _avg_seq(seq):
    if not seq:
        return (1.0, 1.0, 1.0)
    acc, total = [0.0, 0.0, 0.0], 0.0
    for (t0, c0), (t1, c1) in zip(seq, seq[1:]):
        wgt = max(0.0, t1 - t0)
        for i in range(3):
            acc[i] += (c0[i] + c1[i]) / 2 * wgt
        total += wgt
    if total <= 0:
        return tuple(seq[0][1])
    return tuple(a / total for a in acc)


def _avg_num(seq):
    if not seq:
        return 0.0
    acc, total = 0.0, 0.0
    for (t0, v0), (t1, v1) in zip(seq, seq[1:]):
        acc += (v0 + v1) / 2 * (t1 - t0)
        total += t1 - t0
    return acc / total if total > 0 else seq[0][1]


def bg_alpha(node: Node) -> float:
    if node.cls not in GUI_OBJECTS:
        return 0.0
    a = 1 - (effective(node, "BackgroundTransparency") if effective(node, "BackgroundTransparency") is not None else 1.0)
    g = node.child("UIGradient")
    if g and "Transparency" in g.props:
        a *= 1 - _avg_num(g.props["Transparency"])
    return max(0.0, a)


def fill_color(node: Node):
    """Average visible background colour of a node (gradient applied), or None if it has no fill."""
    if bg_alpha(node) < 0.05:
        return None
    base = effective(node, "BackgroundColor3") or (1, 1, 1)
    g = node.child("UIGradient")
    if g and "Color" in g.props:
        avg = _avg_seq(g.props["Color"])
        return tuple(b * a for b, a in zip(base, avg))
    return tuple(base)


def has_rect(n):
    return hasattr(n, "rect") and n.rect[2] > 0 and n.rect[3] > 0


def _covers(outer: Node, inner: Node) -> bool:
    if not has_rect(outer) or not has_rect(inner):
        return False
    ox, oy, ow, oh = outer.rect
    x, y, w, h = inner.rect
    return ox <= x + 2 and oy <= y + 2 and ox + ow >= x + w - 2 and oy + oh >= y + h - 2


def backdrop_for(node: Node):
    """(colour, opacity, owner) of what is painted behind `node`: the nearest filled ancestor, or an
    earlier sibling of it (a scrim, a panel plate) that covers the node."""
    cur = node
    while cur is not None:
        if cur.cls in GUI_OBJECTS:
            c = fill_color(cur)
            if c is not None and bg_alpha(cur) >= 0.35:
                return c, bg_alpha(cur), cur
            if cur.cls in IMAGE_CLASSES and (effective(cur, "Image") or "") and cur is not node:
                return None, 0.6, cur
        parent = cur.parent
        if parent is not None:
            z = effective(cur, "ZIndex") or 1 if cur.cls in GUI_OBJECTS else 1
            idx = parent.children.index(cur)
            for i, sib in enumerate(parent.children):
                if sib is cur or sib.cls not in GUI_OBJECTS or effective(sib, "Visible") is False:
                    continue
                sz = effective(sib, "ZIndex") or 1
                if not (sz < z or (sz == z and i < idx)) or not _covers(sib, node):
                    continue
                c = fill_color(sib)
                if c is not None and bg_alpha(sib) >= 0.35:
                    return c, bg_alpha(sib), sib
                if sib.cls in IMAGE_CLASSES and (effective(sib, "Image") or ""):
                    return None, 0.6, sib
        cur = parent
    return None, 0.0, None


def in_modal(node: Node) -> bool:
    """True when the node lives in a panel that takes over the screen (touch controls are not in play)."""
    cur = node
    while cur is not None:
        if cur.attrs.get("AutoScale") == "modal" or cur.attrs.get("Motion") == "panel":
            return True
        cur = cur.parent
    return False


def is_pill(node: Node) -> bool:
    if not has_rect(node) or not node.child("UICorner"):
        return False
    _, _, w, h = node.rect
    r = max(L.corner_radii(node, w, h, node.px))
    return r >= min(w, h) / 2 - 0.75 and min(w, h) >= 4


def hue_bucket(c):
    Lc, ch, h = C.to_oklch(c)
    if ch < 0.07:
        return None
    return int(((h + 15) % 360) // 30)


def _name(n: Node):
    return n.path


# ------------------------------------------------------------------ rules

def lint(spec: Spec, devices=("pc", "phone")) -> Report:
    rep = Report()
    for sev, path, rule, msg in spec.problems:
        rep.add(sev, rule, path, msg)
    root = spec.root
    meta = spec.meta or {}
    depth = str(meta.get("depth", "")).lower()

    _rule_meta(spec, rep)
    if root.cls not in ("ScreenGui", "SurfaceGui", "BillboardGui"):
        rep.error("root-class", root.path, f"root is a {root.cls}; a UI must start with a ScreenGui "
                  "(or SurfaceGui/BillboardGui for in-world UI).",
                  "Wrap the tree in {\"class\": \"ScreenGui\", \"name\": \"...\", \"children\": [...]}.")
    if root.props.get("ZIndexBehavior") == "Global":
        rep.error("zindex-global", root.path, "ZIndexBehavior is Global. CanvasGroup, and sane layering, need Sibling.",
                  "Remove the property (this tool writes Sibling) or set \"ZIndexBehavior\": \"Sibling\".")

    nodes = list(root.walk())
    safe_rules = [
        (_rule_fonts, (spec, nodes, rep)),
        (_rule_gradients, (nodes, rep, depth)),
        (_rule_strokes_shadows, (nodes, rep, depth)),
        (_rule_colors, (spec, nodes, rep, depth)),
        (_rule_emoji, (nodes, rep)),
        (_rule_engine_misc, (nodes, rep)),
        (_rule_naming, (nodes, rep)),
    ]
    for fn, args in safe_rules:
        _safe(fn, rep, *args)

    for i, dev in enumerate(devices):
        try:
            L.layout_tree(root, dev, 1.0)
        except Exception as e:  # pragma: no cover - layout must not kill lint
            rep.note("internal", root.path, f"layout failed on {dev}: {e}")
            continue
        _safe(_rule_screen_fit, rep, root, nodes, rep, dev)
        _safe(_rule_text_sizes, rep, nodes, rep, dev)
        if i == 0:
            _safe(_rule_shapes, rep, nodes, rep, depth)
            _safe(_rule_fake_gloss, rep, nodes, rep)
            _safe(_rule_depth, rep, nodes, rep, depth)
            _safe(_rule_contrast, rep, nodes, rep)
            _safe(_rule_spacing, rep, nodes, rep)
    L.layout_tree(root, devices[0], 1.0)
    return rep


def _safe(fn, rep, *args):
    try:
        fn(*args)
    except Exception as e:  # pragma: no cover
        rep.note("internal", fn.__name__, f"rule crashed ({type(e).__name__}: {e}); report this.")


def _rule_meta(spec: Spec, rep: Report):
    meta = spec.meta or {}
    if not str(meta.get("genre", "")).strip():
        rep.error("no-genre", "meta", "meta.genre is missing. The style has to come from the game.",
                  "Add \"meta\": {\"genre\": \"...\", \"direction\": \"...\", \"depth\": \"flat|soft|chunky|material\"}.")
    direction = str(meta.get("direction", "")).strip()
    if len(direction) < 24:
        rep.error("no-direction", "meta", "meta.direction is missing or too short. Write the one-sentence art direction "
                  "first: world/material, shape motif, palette logic, type voice.",
                  "Example: \"Deep-sea salvage: riveted teal steel plates, chamfered corners, brass accents, stencil caps\".")
    if str(meta.get("depth", "")).lower() not in DEPTH_STYLES:
        rep.error("no-depth-style", "meta", "meta.depth must be one of flat, soft, chunky, material. It tells the linter "
                  "(and you) how light and thickness work in this UI.",
                  "flat = type and hairlines (horror, cinematic, FPS). soft = gentle gradients and shadows (roleplay, "
                  "tycoon). chunky = outlines, bottom lips, bold type (simulator). material = textured 9-slice (fantasy).")
    raw_root = spec.raw.get("root", {})
    literals = set()

    def walk(v):
        if isinstance(v, str):
            for m in re.findall(r"#[0-9a-fA-F]{6}\b", v):
                literals.add(m.upper())
        elif isinstance(v, list):
            for x in v:
                walk(x)
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)

    walk(raw_root)
    walk(spec.raw.get("components", {}))
    literals -= {"#FFFFFF"}
    if len(literals) > 5:
        rep.warn("no-tokens", "root", f"{len(literals)} hard-coded hex colours in the tree "
                 f"({', '.join(sorted(literals)[:6])}...). Ad-hoc colours are how a UI drifts apart.",
                 "Put the palette in \"tokens\" and reference it: \"$color.primary\", shade($color.primary, -2).")


def _rule_fonts(spec, nodes, rep: Report):
    text_nodes = [n for n in nodes if n.cls in TEXT_CLASSES and (effective(n, "Text") or "").strip()]
    if not text_nodes:
        return
    fams, faces = Counter(), Counter()
    for n in text_nodes:
        face = n.props.get("FontFace")
        if not face:
            rep.error("no-font", _name(n), "text has no FontFace, so Studio will use the legacy default font.",
                      "Set \"FontFace\": \"Family:Weight\" from your type tokens.")
            continue
        fam = face["family"]
        if not fonts.known_family(fam):
            rep.error("unknown-font", _name(n), f"{fam!r} is not a font Roblox ships.",
                      "Use a built-in family (references/fonts.md) or a Creator Store font as rbxassetid://ID.")
            continue
        sup = fonts.supported_weights(fam)
        if sup and face["weight"] not in sup:
            rep.warn("font-weight", _name(n), f"{fam} has no {face['weight']} weight (it ships {', '.join(sup)}); "
                     "Roblox will substitute the nearest.", "Pick a weight the family ships.")
        fams[fam] += 1
        faces[(fam, face["weight"])] += 1
    if not fams:
        return
    for fam in fams:
        if fam in GENERIC_FONTS:
            rep.warn("generic-font", "typography", f"{fam} is a default-looking face; it reads as \"nobody chose the type\".",
                     "Choose a display face that belongs to this game's world, plus one quiet body face.")
    if len(text_nodes) >= 5 and len(faces) == 1:
        rep.warn("one-font", "typography", f"all {len(text_nodes)} text nodes use {next(iter(faces))[0]} at one weight. "
                 "Hierarchy needs contrast in face or weight.",
                 "Use a display face for titles/buttons/numbers and a second face or weight for body and labels.")
    if len(fams) > 3:
        rep.warn("too-many-fonts", "typography", f"{len(fams)} font families ({', '.join(fams)}).",
                 "Two families is the norm: one display, one body.")


def _rule_text_sizes(nodes, rep: Report, dev: str):
    sizes = []
    for n in nodes:
        if n.cls not in TEXT_CLASSES or not has_rect(n) or not (effective(n, "Text") or "").strip():
            continue
        x, y, w, h = n.rect
        pl, pt, pr, pb = L.padding(n, w, h, n.px)
        tl = L.text_layout(n, max(1, w - pl - pr), max(1, h - pt - pb), n.px)
        sizes.append((tl["size"], n, tl))
        if tl["size"] < 9:
            rep.error("text-tiny", _name(n), f"text renders at {tl['size']:.0f}px on {dev}; below 9px is unreadable.",
                      "Give the label more room, raise TextSize, or raise minText.")
        elif tl["size"] < 11.5 and dev != "pc":
            rep.warn("text-small", _name(n), f"text renders at {tl['size']:.0f}px on {dev}.",
                     "Phones need about 12px or more for anything a player has to read.")
        if not tl["fits"] and not effective(n, "TextScaled") and "X" not in (effective(n, "AutomaticSize") or "None") \
                and (effective(n, "TextTruncate") or "None") == "None":
            rep.warn("text-overflow", _name(n), f"\"{L.plain_text(n)[:28]}\" needs {tl['width']:.0f}x{tl['height']:.0f}px but "
                     f"its box is {w - pl - pr:.0f}x{h - pt - pb:.0f}px on {dev}.",
                     "Widen the box, wrap the text, shorten it, or use TextScaled with maxText.")
        if effective(n, "TextScaled") and not n.child("UITextSizeConstraint"):
            if dev == "pc":
                rep.warn("textscaled-unbounded", _name(n), "TextScaled with no size limit: every label ends up a different size.",
                         "Add \"maxText\": <your type-scale size> (and usually \"minText\": 10).")
    if dev == "pc" and len(sizes) >= 4:
        vals = sorted({round(s[0]) for s in sizes})
        if vals[-1] / max(1, vals[0]) < 1.5:
            rep.warn("flat-type-scale", "typography", f"text sizes run only from {vals[0]}px to {vals[-1]}px; nothing reads as a headline.",
                     "Make the title at least 2x the body size; use 3-4 sizes with clear jumps.")
        if len(vals) > 7:
            rep.warn("type-scale-sprawl", "typography", f"{len(vals)} different text sizes ({', '.join(map(str, vals))}).",
                     "Snap every label to a 4-step type scale defined in tokens.")


def _rule_gradients(nodes, rep: Report, depth: str):
    diagonal, total = [], 0
    for n in nodes:
        if n.cls != "UIGradient" or n.props.get("Enabled") is False:
            continue
        owner = n.parent
        total += 1
        seq = n.props.get("Color")
        if owner is not None and owner.cls in GUI_OBJECTS and seq:
            bases = []
            if bg_alpha_raw(owner) > 0.05:
                bases.append(("BackgroundColor3", effective(owner, "BackgroundColor3") or (1, 1, 1)))
            if owner.cls in IMAGE_CLASSES and (effective(owner, "Image") or ""):
                bases = [("ImageColor3", effective(owner, "ImageColor3") or (1, 1, 1))]
            if owner.cls in TEXT_CLASSES and (effective(owner, "Text") or "").strip():
                bases.append(("TextColor3", effective(owner, "TextColor3") or (0.1, 0.16, 0.2)))
            varied = any(C.to_oklab(a[1])[0] != C.to_oklab(b[1])[0] or a[1] != b[1] for a, b in zip(seq, seq[1:]))
            for prop, base in bases:
                if varied and min(base) < 0.92:
                    rep.error("gradient-on-colour", _name(owner),
                              f"UIGradient colours are multiplied by {prop}, which is not white here, so the result is "
                              "darker and muddier than the colours you wrote.",
                              f"Set {prop} to #FFFFFF and put the real colours in the gradient.")
            if owner.cls in TEXT_CLASSES and (effective(owner, "Text") or "").strip() and bg_alpha_raw(owner) > 0.05:
                rep.warn("gradient-hits-text-and-bg", _name(owner), "a UIGradient on a text object tints both its text and "
                         "its background.", "Put the label in a child TextLabel with its own colour.")
        if seq:
            if len(seq) > 6:
                rep.warn("gradient-stops", _name(owner or n), f"{len(seq)} colour stops; more than 6 costs performance and rarely helps.", "")
            c0, c1 = seq[0][1], seq[-1][1]
            l0, ch0, h0 = C.to_oklch(c0)
            l1, ch1, h1 = C.to_oklch(c1)
            if ch0 > 0.08 and ch1 > 0.08:
                dh = abs(((h0 - h1 + 180) % 360) - 180)
                limit = 50 if len(seq) <= 2 else 110
                if dh > limit:
                    rep.warn("gradient-hue-jump", _name(owner or n),
                             f"gradient jumps {dh:.0f} degrees of hue ({C.to_hex(c0)} to {C.to_hex(c1)}). Two far-apart saturated "
                             "colours blend through a grey dead zone, and it is the signature AI gradient.",
                             "Keep both ends within about 35 degrees (use shade($c, 1) to shade($c, -1)), or add a hand-picked middle stop.")
            dl = abs(l0 - l1)
            if dl > 0.34 and depth in ("flat", "soft") and "Transparency" not in n.props:
                rep.warn("gradient-too-strong", _name(owner or n), f"gradient spans {dl * 100:.0f}% lightness; it reads as a banner, not a surface.",
                         "For flat/soft styles keep the ends 5-15% apart.")
        rot = n.props.get("Rotation", 0.0) % 360
        if n.props.get("Type", "Linear") == "Linear" and seq and (rot % 90) > 5 and (rot % 90) < 85:
            diagonal.append(n)
    if len(diagonal) >= 3 and len(diagonal) >= total * 0.5:
        rep.warn("diagonal-gradients", "gradients", f"{len(diagonal)} of {total} gradients are diagonal. Light comes from above: "
                 "surfaces shade top-to-bottom.", "Use rotation 90 for surfaces; keep diagonals for one deliberate shine or banner.")


def bg_alpha_raw(node: Node) -> float:
    bt = effective(node, "BackgroundTransparency")
    return 1 - (bt if bt is not None else 1.0)


def _rule_strokes_shadows(nodes, rep: Report, depth: str):
    strokes = [n for n in nodes if n.cls == "UIStroke" and n.props.get("Enabled") is not False]
    shadows = [n for n in nodes if n.cls == "UIShadow" and n.props.get("Enabled") is not False]
    if len(strokes) > 300:
        rep.warn("stroke-count", "strokes", f"{len(strokes)} UIStrokes; Roblox recommends staying under about 300 on screen.", "")
    if len(shadows) > 100:
        rep.warn("shadow-count", "shadows", f"{len(shadows)} UIShadows; Roblox recommends at most about 100 on screen.", "")
    border_thick = Counter()
    for s in strokes:
        owner = s.parent
        is_text = owner is not None and owner.cls in TEXT_CLASSES and s.props.get("ApplyStrokeMode", "Contextual") == "Contextual"
        col = s.props.get("Color", (0, 0, 0))
        if not is_text and s.props.get("StrokeSizingMode") != "ScaledSize":
            border_thick[round(s.props.get("Thickness", 1.0), 1)] += 1
        if max(col) < 0.02 and s.props.get("Transparency", 0.0) < 0.5:
            rep.warn("pure-black", _name(owner or s), "stroke is pure #000000. Pure black flattens whatever it touches.",
                     "Use the darkest shade of the fill's own hue: shade($fill, -4), or a tinted near-black token.")
        if owner is not None and not is_text:
            fc = fill_color(owner)
            if fc is not None and C.luminance(col) > C.luminance(fc) + 0.25 and s.props.get("BorderStrokePosition", "Outer") == "Outer" \
                    and s.props.get("Transparency", 0.0) < 0.6 and depth in ("chunky", "soft"):
                rep.warn("light-outline", _name(owner), "outer stroke is lighter than the fill. Light outlines look like a sticker cut-out.",
                         "Outer strokes go darker than the fill; put light edges inside (inset UIShadow or an Inner stroke).")
        if owner is not None and owner.cls in TEXT_CLASSES and is_text and not (effective(owner, "Text") or "").strip() \
                and bg_alpha(owner) > 0.2:
            rep.warn("stroke-on-empty-text", _name(owner), "this UIStroke is in Contextual mode on a text object with no text, so it "
                     "outlines nothing. (On TextLabel/TextButton, a stroke outlines the glyphs, not the box.)",
                     "Set \"mode\": \"Border\" on the stroke to outline the box.")
        by_z = Counter()
        if owner is not None:
            for sib in owner.children_of("UIStroke"):
                if sib.props.get("ApplyStrokeMode", "Contextual") == s.props.get("ApplyStrokeMode", "Contextual"):
                    by_z[sib.props.get("ZIndex", 1)] += 1
            if any(v > 1 for v in by_z.values()) and s is owner.children_of("UIStroke")[0]:
                rep.warn("stroke-zindex", _name(owner), "sibling UIStrokes share a ZIndex, so their draw order is undefined.",
                         "Give each stroke its own \"z\".")
            if owner.cls in TEXT_CLASSES:
                ctx = [x for x in owner.children_of("UIStroke") if x.props.get("ApplyStrokeMode", "Contextual") == "Contextual"]
                if len(ctx) > 1 and s is ctx[0]:
                    rep.error("two-text-strokes", _name(owner), "a text object supports only one Contextual (text) stroke.",
                              "For a double outline, stack a second TextLabel behind, or use a text-mode UIShadow.")
    if len(border_thick) > 3:
        rep.warn("stroke-weights", "strokes", f"{len(border_thick)} different border thicknesses "
                 f"({', '.join(str(k) for k in sorted(border_thick))}).",
                 "Define a 2-3 step stroke scale in tokens (e.g. panel 4, button 3, chip 2) and use only those.")
    up, sideways = 0, set()
    soft_grey = Counter()
    for s in shadows:
        if s.props.get("ZIndex", -1) >= 0:
            rep.error("shadow-zindex", _name(s.parent or s), "UIShadow.ZIndex must be negative.", "Use \"z\": -1, -2, ...")
        if s.props.get("Inset") or s.props.get("Mode") == "Text":
            continue
        o = s.props.get("Offset", (0, 0, 0, 0))
        oy, ox = o[3] + o[2] * 50, o[1] + o[0] * 50
        if oy < -0.5:
            up += 1
        if abs(ox) > 0.5:
            sideways.add(1 if ox > 0 else -1)
        col = s.props.get("Color", (0, 0, 0))
        blur = s.props.get("BlurRadius", (0.0, 0.0))
        if max(col) < 0.02 and s.props.get("Transparency", 0.0) < 0.55:
            rep.warn("pure-black", _name(s.parent or s), "drop shadow is near-opaque pure black.",
                     "Tint the shadow with the hue behind it and keep soft shadows 70-85% transparent; hard lips use shade($fill, -3).")
        if blur[1] >= 10 and C.chroma(col) < 0.03:
            soft_grey[(round(blur[1]), round(s.props.get("Transparency", 0.0), 2))] += 1
        if blur[1] >= 16 and C.chroma(col) > 0.12 and s.props.get("Transparency", 0.0) < 0.6:
            soft_grey["glow"] += 1
    if up:
        rep.warn("light-direction", "shadows", f"{up} drop shadow(s) are offset upward. One light, from above: shadows fall down.",
                 "Use a positive Y offset for every drop shadow and lip.")
    if len(sideways) > 1:
        rep.warn("light-direction", "shadows", "drop shadows fall both left and right.", "Pick one light direction for the whole UI.")
    if soft_grey.get("glow", 0) > 2:
        rep.warn("glow-everywhere", "shadows", f"{soft_grey['glow']} saturated glows. A glow means something only if it is rare.",
                 "Keep one glow for the single most important thing on screen.")
    same = [v for k, v in soft_grey.items() if k != "glow"]
    if same and max(same) >= 6:
        rep.note("identical-soft-shadows", "shadows", f"{max(same)} elements carry the same soft grey shadow (the SaaS-card look).",
                 "Vary elevation by role, or drop shadows from repeated cards and let the panel carry depth.")


def _visible_shapes(nodes):
    out = []
    for n in nodes:
        if n.cls in GUI_OBJECTS and has_rect(n) and bg_alpha(n) >= 0.25:
            out.append(n)
    return out


def _rule_shapes(nodes, rep: Report, depth: str):
    shapes = [n for n in _visible_shapes(nodes) if n.rect[2] >= 28 and n.rect[3] >= 20]
    rounded = [n for n in shapes if n.child("UICorner")]
    pills = [n for n in rounded if is_pill(n) and n.rect[2] > n.rect[3] * 1.25]
    big_pills = [n for n in pills if n.rect[3] >= 34]
    if len(big_pills) >= 3 and len(big_pills) >= 0.4 * len(shapes):
        rep.warn("pill-everything", "shapes", f"{len(big_pills)} of {len(shapes)} shapes are full pills "
                 f"(e.g. {', '.join(n.name for n in big_pills[:3])}). Pills on everything is the most recognisable AI-UI tell.",
                 "Use a radius scale by role (chip/pill for tags and toggles only; buttons 10-16; cards 14-20; panels 20-28), "
                 "or a non-round motif (chamfer, skew, squared) if it suits the world.")
    for n in pills:
        if n.rect[3] >= 120:
            rep.warn("giant-pill", _name(n), f"a {n.rect[2]:.0f}x{n.rect[3]:.0f} container is a full pill; content will collide with the curve.",
                     "Give containers an offset radius from the radius scale.")
    if len(rounded) >= 5:
        radii = Counter()
        for n in rounded:
            r = round(max(L.corner_radii(n, n.rect[2], n.rect[3], n.px)))
            radii[r] += 1
        heights = [min(n.rect[2], n.rect[3]) for n in rounded]
        if len(radii) == 1 and max(heights) / max(1.0, min(heights)) >= 3.5:
            rep.warn("one-radius", "shapes", f"every rounded shape uses radius {next(iter(radii))}px, from {min(heights):.0f}px chips to "
                     f"{max(heights):.0f}px panels. Shape stops saying what a thing is.",
                     "Define 3 radii in tokens (small/medium/large) and assign them by role.")
        if len(radii) > 5:
            rep.warn("radius-sprawl", "shapes", f"{len(radii)} different corner radii ({', '.join(map(str, sorted(radii)))}).",
                     "Snap to a 3-4 step radius scale in tokens.")
    # concentric corners: inner radius should be outer radius minus the gap
    for n in rounded:
        p = n.parent
        if p is None or p.cls not in GUI_OBJECTS or not p.child("UICorner") or not has_rect(p) or bg_alpha(p) < 0.25:
            continue
        px0, py0, pw, ph = p.rect
        x, y, w, h = n.rect
        gaps = [x - px0, y - py0, (px0 + pw) - (x + w), (py0 + ph) - (y + h)]
        near = [g for g in gaps if -1 <= g <= 28]
        if len(near) < 2:
            continue
        gap = max(0.0, min(near))
        outer = max(L.corner_radii(p, pw, ph, p.px))
        inner = max(L.corner_radii(n, w, h, n.px))
        expected = max(0.0, outer - gap)
        if outer >= 8 and inner >= outer and 2 <= gap <= 14 and not is_pill(p):
            rep.warn("corners-not-concentric", _name(n), "a rounded shape sits just inside another with the same or a larger radius, "
                     "so the gap bulges at the corners.",
                     f"inner radius = outer radius - gap (here about {expected:.0f}px).")


def _rule_fake_gloss(nodes, rep: Report):
    for n in nodes:
        if n.cls not in ("Frame", "ImageLabel") or not has_rect(n) or n.parent is None or not has_rect(n.parent):
            continue
        p = n.parent
        if p.cls not in GUI_OBJECTS or bg_alpha(p) < 0.25:
            continue
        col = effective(n, "BackgroundColor3") or (1, 1, 1)
        bt = effective(n, "BackgroundTransparency")
        bt = 1.0 if bt is None else bt
        if not (min(col) > 0.9 and 0.2 <= bt <= 0.95):
            continue
        if any(c.cls in GUI_OBJECTS for c in n.children):
            continue
        g = n.child("UIGradient")
        fades = bool(g and "Transparency" in g.props and
                     max(v for _, v in g.props["Transparency"]) - min(v for _, v in g.props["Transparency"]) > 0.3)
        px0, py0, pw, ph = p.rect
        x, y, w, h = n.rect
        top_half = (y + h / 2) < (py0 + ph * 0.5) and h < ph * 0.62
        inset_x = (x - px0) > 2 and ((px0 + pw) - (x + w)) > 2
        fills = abs(w - pw) < 2 and abs(x - px0) < 2
        if top_half and not fades and (inset_x or (fills and n.child("UICorner"))):
            rep.error("fake-gloss", _name(n),
                      "semi-transparent white blob floating in the top half of its parent: the fake-gloss tell (hard lower edge, "
                      "uniform alpha, curve that ignores the parent). Looks pasted on at full size.",
                      "Delete it. Lit top edge = inset UIShadow {\"class\":\"UIShadow\",\"Inset\":true,\"Color\":\"#FFFFFF\","
                      "\"Offset\":[0,0,0,3],\"Transparency\":0.6,\"ZIndex\":-2}. Real gloss = full-size child with the parent's "
                      "radius and a transparency gradient fading out by mid-height.")


def _rule_depth(nodes, rep: Report, depth: str):
    shapes = [n for n in _visible_shapes(nodes) if n.rect[2] >= 40 and n.rect[3] >= 28 and bg_alpha(n) >= 0.5]
    if len(shapes) < 3:
        return

    def treated(n):
        return bool(n.child("UIGradient") or n.child("UIStroke") or n.child("UIShadow")
                    or (n.cls in IMAGE_CLASSES and effective(n, "Image")))

    bare = [n for n in shapes if not treated(n)]
    buttons = [n for n in nodes if n.cls in BUTTON_CLASSES and has_rect(n)]
    if depth in ("chunky", "soft", "material") and len(bare) > 0.6 * len(shapes):
        rep.warn("flat-rectangles", "depth", f"{len(bare)} of {len(shapes)} filled shapes have no gradient, stroke, shadow or texture "
                 f"(e.g. {', '.join(n.name for n in bare[:3])}), but meta.depth is \"{depth}\".",
                 "One light from above: lighter top, darker bottom, a same-hue edge. See references/depth.md.")
    if depth == "chunky":
        lipless = []
        for b in buttons:
            host = b if bg_alpha(b) > 0.3 else next((c for c in b.children if c.cls in GUI_OBJECTS and bg_alpha(c) > 0.3), None)
            if host is None:
                continue
            hard = any(s.cls == "UIShadow" and not s.props.get("Inset") and s.props.get("BlurRadius", (0, 0))[1] <= 2
                       and s.props.get("Offset", (0, 0, 0, 0))[3] >= 2 for s in host.children)
            lip_frame = b.parent is not None and any(
                sib is not b and sib.cls == "Frame" and has_rect(sib) and abs(sib.rect[2] - host.rect[2]) < 6
                and 1 < (sib.rect[1] + sib.rect[3]) - (host.rect[1] + host.rect[3]) < 16 for sib in b.parent.children)
            if not hard and not lip_frame and host.rect[3] >= 30:
                lipless.append(b)
        if buttons and len(lipless) >= max(2, 0.6 * len(buttons)):
            rep.warn("no-button-lip", "depth", f"{len(lipless)} of {len(buttons)} buttons have no bottom lip, yet depth is \"chunky\".",
                     "A chunky button stands on a hard, darker bottom edge: UIShadow with blur 0, offset [0, 4-6], colour shade($fill, -3).")
    if depth == "flat":
        heavy = [n for n in nodes if n.cls == "UIShadow" and not n.props.get("Inset") and n.props.get("Mode", "Shape") == "Shape"
                 and n.props.get("BlurRadius", (0, 0))[1] <= 2 and n.props.get("Offset", (0, 0, 0, 0))[3] >= 3]
        if len(heavy) >= 2:
            rep.warn("lip-in-flat-style", "depth", f"{len(heavy)} hard bottom lips in a UI declared \"flat\".",
                     "Flat styles get depth from type, hairlines, scrims and spacing. Either remove the lips or change meta.depth.")
        thick = [n for n in nodes if n.cls == "UIStroke" and n.props.get("Thickness", 1) >= 3 and n.parent is not None
                 and n.parent.cls not in TEXT_CLASSES]
        if len(thick) >= 3:
            rep.warn("thick-stroke-in-flat-style", "depth", f"{len(thick)} borders are 3px or thicker in a UI declared \"flat\".",
                     "Flat styles use 1-2px hairlines, often translucent.")


def _rule_colors(spec, nodes, rep: Report, depth: str):
    buckets = defaultdict(list)
    for n in nodes:
        if n.cls not in GUI_OBJECTS:
            continue
        fc = fill_color(n)
        if fc is None:
            continue
        b = hue_bucket(fc)
        Lc, ch, _ = C.to_oklch(fc)
        if b is not None and ch > 0.11:
            buckets[b].append(n)
        if max(fc) < 0.012 and bg_alpha(n) > 0.9:
            rep.warn("pure-black", _name(n), "fill is pure #000000.",
                     "Use a near-black tinted toward the palette (e.g. #0E1016, #14110F); it sits in the scene instead of punching a hole.")
    # merge neighbouring buckets (30 degree bins) into hue families
    fams = []
    for b in sorted(buckets):
        if fams and (b - fams[-1][-1]) <= 1:
            fams[-1].append(b)
        else:
            fams.append([b])
    if len(fams) >= 2 and fams[0][0] == 0 and fams[-1][-1] == 11:
        fams[0] = fams.pop() + fams[0]
    if len(fams) >= 5:
        names = [buckets[f[0]][0].name for f in fams]
        rep.warn("hue-rainbow", "colour", f"{len(fams)} unrelated saturated hues are used as fills ({', '.join(names[:6])}...). "
                 "A different colour on every element is decoration, not a colour system.",
                 "One dominant hue family, one or two accents, tinted neutrals. Colour by function: e.g. green = buy/confirm, "
                 "red = close/danger, gold = premium, and nothing else gets those hues. (Rarity ladders are the one exception.)")
    sat_area = area = 0.0
    for n in nodes:
        if n.cls in GUI_OBJECTS and has_rect(n):
            fc = fill_color(n)
            if fc is None:
                continue
            a = n.rect[2] * n.rect[3] * bg_alpha(n)
            h, s, v = C.hsv(fc)
            area += a
            if s > 0.8 and v > 0.85:
                sat_area += a
    if area > 0 and sat_area / area > 0.55 and depth != "chunky":
        rep.warn("saturation-overload", "colour", f"{sat_area / area * 100:.0f}% of the filled area is at near-maximum saturation.",
                 "Let neutrals carry 60%+ of the surface so the saturated action colour has something to stand out from.")
    elif area > 0 and sat_area / area > 0.8:
        rep.warn("saturation-overload", "colour", f"{sat_area / area * 100:.0f}% of the filled area is at near-maximum saturation.",
                 "Even loud simulator UI rests on a calmer panel body; give the eye one neutral surface.")


def _rule_contrast(nodes, rep: Report):
    for n in nodes:
        if n.cls not in TEXT_CLASSES or not has_rect(n) or not (effective(n, "Text") or "").strip():
            continue
        if (effective(n, "TextTransparency") or 0) > 0.6:
            continue
        col = effective(n, "TextColor3") or (0.1, 0.16, 0.2)
        g = n.child("UIGradient")
        if g and "Color" in g.props:
            col = tuple(a * b for a, b in zip(col, _avg_seq(g.props["Color"])))
        stroke = next((s for s in n.children_of("UIStroke") if s.props.get("ApplyStrokeMode", "Contextual") == "Contextual"
                       and s.props.get("Transparency", 0) < 0.6 and s.props.get("Thickness", 1) >= 1), None)
        tshadow = next((s for s in n.children_of("UIShadow") if s.props.get("Mode") == "Text"), None)
        legacy = (effective(n, "TextStrokeTransparency") or 1) < 0.7
        behind, opacity, owner = backdrop_for(n)
        size = effective(n, "TextSize") or 14
        if behind is None or opacity < 0.6:
            if not (stroke or tshadow or legacy):
                rep.warn("text-over-world", _name(n), "text sits directly over the 3D world with no outline, shadow or scrim. "
                         "It will vanish against some part of every map.",
                         "Add a text stroke/shadow, or put a dark gradient scrim behind it.")
            continue
        cr = C.contrast(col, behind)
        need = 3.0 if size >= 22 else 4.5
        if cr < need:
            if stroke and C.contrast(col, stroke.props.get("Color", (0, 0, 0))) >= 3.0:
                continue
            rep.warn("low-contrast", _name(n), f"text {C.to_hex(col)} on {C.to_hex(behind)} has contrast {cr:.1f}:1 (needs {need}:1).",
                     "Use ink($background) for a readable same-family text colour, or add a dark same-hue stroke.")


def _rule_spacing(nodes, rep: Report):
    for n in nodes:
        if n.cls not in TEXT_CLASSES or not has_rect(n) or not (effective(n, "Text") or "").strip():
            continue
        behind, opacity, owner = backdrop_for(n)
        if owner is None or not has_rect(owner) or owner.rect[2] < 40:
            continue
        x, y, w, h = n.rect
        pl, pt, pr, pb = L.padding(n, w, h, n.px)
        tl = L.text_layout(n, max(1, w - pl - pr), max(1, h - pt - pb), n.px)
        xa = {"Left": 0.0, "Center": 0.5, "Right": 1.0}[effective(n, "TextXAlignment") or "Center"]
        tx0 = x + pl + (w - pl - pr - tl["width"]) * xa
        tx1 = tx0 + tl["width"]
        ox, oy, ow, oh = owner.rect
        left_gap, right_gap = tx0 - ox, (ox + ow) - tx1
        limit = 5 if ow < 160 else 8
        if min(left_gap, right_gap) < limit and tl["width"] < ow * 1.2:
            side = "left" if left_gap < right_gap else "right"
            rep.warn("text-touches-edge", _name(n), f"text is {min(left_gap, right_gap):.0f}px from the {side} edge of {owner.name}.",
                     "Give every container padding from the spacing scale (8-16px in cards, 16-24px in panels).")


def _rule_screen_fit(root, nodes, rep: Report, dev: str):
    vw, vh, topbar, safe, touch = L.DEVICES[dev]
    tops = [n for n in L.visible_gui_children(root)] if root.cls not in GUI_OBJECTS else [root]
    full_bleed = (effective(root, "ScreenInsets") or "CoreUISafeInsets") == "None"
    for n in nodes:
        if n.cls not in GUI_OBJECTS or not has_rect(n):
            continue
        x, y, w, h = n.rect
        is_top = n in tops
        if is_top:
            over_x = max(0, -x) + max(0, x + w - vw)
            over_y = max(0, -y) + max(0, y + h - vh)
            if (over_x > 4 or over_y > 4) and not (full_bleed and w >= vw - 2 and h >= vh - 2) and w * h > 400:
                size = effective(n, "Size") or (0, 0, 0, 0)
                offset_only = size[0] == 0 or size[2] == 0
                rep.error("off-screen", _name(n), f"on {dev} ({vw}x{vh}) this is {w:.0f}x{h:.0f}px and overflows the screen by "
                          f"{over_x:.0f}px horizontally, {over_y:.0f}px vertically."
                          + (" It is sized in pixels, so it does not shrink on small screens." if offset_only else ""),
                          "Add \"autoscale\": \"modal\" to a centred panel (or \"hud\" to an edge-anchored HUD group): you design in "
                          "1080p pixels and it is scaled per device.")
        if n.cls in BUTTON_CLASSES and touch:
            if min(w, h) < 36 and w * h > 0:
                rep.warn("touch-target", _name(n), f"button is under 36px on {dev} (smallest side); thumbs need about 44px.",
                         "Enlarge it, or wrap the visual in a larger transparent button.")
            for (zx0, zy0, zx1, zy1), why in backdrops.keep_clear_zones(dev):
                ix = min(x + w, zx1) - max(x, zx0)
                iy = min(y + h, zy1) - max(y, zy0)
                if "top bar" not in why and in_modal(n):
                    continue
                if ix > 6 and iy > 6:
                    rep.error("blocked-control", _name(n), f"on {dev} this button overlaps the {why}.",
                              "Move it: side menus sit left-middle (35-60% height), action buttons cluster above/left of jump, currency goes top-centre or top-right.")
        elif n.cls in BUTTON_CLASSES and not touch:
            for (zx0, zy0, zx1, zy1), why in backdrops.keep_clear_zones(dev):
                if min(x + w, zx1) - max(x, zx0) > 6 and min(y + h, zy1) - max(y, zy0) > 6:
                    rep.error("blocked-control", _name(n), f"on {dev} this button overlaps the {why}.",
                              "Keep the top-left 124x58px clear, or leave ScreenInsets at CoreUISafeInsets.")


def _rule_emoji(nodes, rep: Report):
    hits = [n for n in nodes if n.cls in TEXT_CLASSES and _EMOJI.search(effective(n, "Text") or "")]
    for n in hits[:6]:
        rep.warn("emoji-icon", _name(n), f"emoji in \"{(effective(n, 'Text') or '')[:20]}\". Emoji render in the platform's own style, "
                 "ignore your palette and stroke, and are the cheapest possible icon.",
                 "Use an ImageLabel icon (scripts/draw_assets.py icon <name>, or an uploaded asset). See references/assets.md.")


def _rule_engine_misc(nodes, rep: Report):
    for n in nodes:
        if n.cls == "ScrollingFrame":
            if "CanvasSize" not in n.explicit and "AutomaticCanvasSize" not in n.explicit:
                rep.warn("scroll-canvas", _name(n), "ScrollingFrame keeps the default CanvasSize of 2x its height, and children with "
                         "scale sizes are measured against that canvas.",
                         "Set \"CanvasSize\": [0,0,0,0] and \"AutomaticCanvasSize\": \"Y\".")
            if n.child("UICorner"):
                rep.warn("scroll-corner", _name(n), "UICorner does not round a ScrollingFrame.",
                         "Round a parent Frame and put a transparent ScrollingFrame inside it.")
            if n.child("UIGradient"):
                rep.warn("scroll-gradient", _name(n), "UIGradient is not supported on ScrollingFrame.", "Put the gradient on a parent Frame.")
        if n.cls in GUI_OBJECTS and n.cls != "CanvasGroup" and effective(n, "ClipsDescendants") and n.child("UICorner") \
                and any(c.cls in GUI_OBJECTS for c in n.children):
            rep.note("clip-not-rounded", _name(n), "ClipsDescendants clips to the rectangle, not to the rounded corners.",
                     "If children reach the corners, make this a CanvasGroup (it clips to its UICorner).")
        if n.attrs.get("Motion") == "button" and nodes[0].attrs.get("MotionStyle") != "calm" and n.parent is not None and (
                n.parent.child("UIListLayout") or n.parent.child("UIGridLayout")):
            rep.warn("motion-in-layout", _name(n), "a hover-scaled button is a direct child of a list/grid, so scaling it will "
                     "push its neighbours around.",
                     "Wrap it: a fixed-size Frame holder in the layout, with the button inside at Size [1,0,1,0].")
        if n.cls == "TextBox" and n.child("UIGradient"):
            rep.warn("textbox-gradient", _name(n), "UIGradient is not supported on TextBox.", "Put the gradient on a parent Frame.")
        if n.cls in IMAGE_CLASSES:
            ref = effective(n, "Image") or ""
            if ref.startswith("http"):
                rep.error("image-url", _name(n), "Roblox cannot load images from web URLs.", "Upload the image and use rbxassetid://ID, or asset:name while designing.")
            if effective(n, "ScaleType") == "Slice" and "SliceCenter" not in n.explicit:
                rep.error("slice-center", _name(n), "ScaleType Slice without SliceCenter stretches the whole image.",
                          "Set SliceCenter to [left, top, right, bottom] in source-image pixels (draw_assets.py prints it).")
        if n.cls in BUTTON_CLASSES and n.props.get("AutoButtonColor") is True and (n.child("UIGradient") is not None):
            rep.note("auto-button-color", _name(n), "AutoButtonColor darkens the base colour and fights custom hover tweens.", "Leave it off (the default here).")
        if n.cls in TEXT_CLASSES and (effective(n, "TextStrokeTransparency") or 1) < 1 and n.child("UIGradient"):
            rep.warn("legacy-stroke-gradient", _name(n), "legacy TextStroke combined with a UIGradient renders badly.", "Use a UIStroke (\"stroke\": {...}).")


def _rule_naming(nodes, rep: Report):
    containers = [n for n in nodes if n.cls in GUI_OBJECTS]
    if len(containers) < 6:
        return
    default = [n for n in containers if n.name in DEFAULT_NAMES]
    if len(default) > 0.5 * len(containers):
        rep.warn("default-names", "naming", f"{len(default)} of {len(containers)} GUI objects still have their class name. "
                 "This is real UI a person will open in the Explorer and wire scripts to.",
                 "Name every object for what it is: Panel, Header, BuyButton, PriceLabel, ItemGrid.")
