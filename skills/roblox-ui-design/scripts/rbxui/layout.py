"""Roblox GUI layout: UDim2 sizing, anchors, padding, constraints, list/grid layouts, UIScale.

This mirrors the engine closely enough that a preview shows the same overlaps,
overflow and scaling problems Studio would. Results are stored on each node as
`node.rect = (x, y, w, h)` (absolute pixels) and `node.px` (pixel multiplier
from UIScale ancestors and the render scale).
"""
from __future__ import annotations

import re

import fonts
from spec import GUI_OBJECTS, TEXT_CLASSES, Node, effective

DEVICES = {
    # name: (width, height, topbar, (left, top, right, bottom) device safe insets, touch)
    "pc": (1920, 1080, 58, (0, 0, 0, 0), False),
    "laptop": (1366, 768, 58, (0, 0, 0, 0), False),
    "tablet": (1180, 820, 58, (0, 0, 0, 20), True),
    "phone": (844, 390, 58, (47, 0, 47, 21), True),
    "small-phone": (667, 375, 58, (0, 0, 0, 0), True),
}


HIDE_START_HIDDEN = {"on": False, "except": None}
ANIM = {"t": None}  # None = settled (every entrance finished, everything that leaves has left)


def _num(d: dict, key: str, default: float) -> float:
    try:
        return float(d.get(key, default))
    except (TypeError, ValueError):
        return default


def _pair(d: dict, key: str):
    try:
        x, y = str(d.get(key, "0,0")).split(",")
        return float(x), float(y)
    except ValueError:
        return 0.0, 0.0


def ease_out(kind: str, p: float) -> float:
    import math

    p = max(0.0, min(1.0, p))
    if kind == "Linear":
        return p
    if kind == "Sine":
        return math.sin(p * math.pi / 2)
    if kind == "Quad":
        return 1 - (1 - p) ** 2
    if kind == "Cubic":
        return 1 - (1 - p) ** 3
    if kind in ("Quint", "Exponential"):
        return 1 - (1 - p) ** 5
    if kind == "Elastic":
        return 1 if p in (0.0, 1.0) and p else (0 if p == 0 else 2 ** (-10 * p) * math.sin((p * 10 - 0.75) * (2 * math.pi / 3)) + 1)
    if kind == "Bounce":
        n, d = 7.5625, 2.75
        if p < 1 / d:
            return n * p * p
        if p < 2 / d:
            p -= 1.5 / d
            return n * p * p + 0.75
        if p < 2.5 / d:
            p -= 2.25 / d
            return n * p * p + 0.9375
        p -= 2.625 / d
        return n * p * p + 0.984375
    c1, c3 = 1.70158, 2.70158  # Back
    return 1 + c3 * (p - 1) ** 3 + c1 * (p - 1) ** 2


def anim_state(node: Node, t):
    """Where an animated node is at time t (seconds after its panel opens). None when it is at rest.
    -> dict(dx, dy, rot, scale, alpha, reveal, reveal_frac, gone)"""
    from spec import parse_anim

    enter = parse_anim(node.attrs.get("AnimEnter"))
    leave = parse_anim(node.attrs.get("AnimLeave"))
    if not enter and not leave:
        return None
    st = {"dx": 0.0, "dy": 0.0, "rot": 0.0, "scale": 1.0, "alpha": 1.0, "reveal": None, "reveal_frac": 1.0, "gone": False}
    if t is None:
        st["gone"] = bool(leave)
        return st if leave else None
    if enter:
        delay, dur = _num(enter, "delay", 0), max(0.01, _num(enter, "dur", 0.45))
        p = (t - delay) / dur
        e = ease_out(enter.get("ease", "Back"), p) if p > 0 else 0.0
        fx, fy = _pair(enter, "from")
        st["dx"], st["dy"] = fx * (1 - e), fy * (1 - e)
        st["rot"] = _num(enter, "rot", 0) * (1 - e)
        s0 = _num(enter, "scale", 1)
        st["scale"] = s0 + (1 - s0) * e
        if enter.get("fade") == "true":
            st["alpha"] = max(0.0, min(1.0, (t - delay) / (dur * 0.6)))
        if enter.get("reveal"):
            st["reveal"], st["reveal_frac"] = enter["reveal"], max(0.0, min(1.0, e))
    if leave:
        at, dur = _num(leave, "at", 1), max(0.01, _num(leave, "dur", 0.5))
        q = max(0.0, min(1.0, (t - at) / dur))
        q2 = q * q
        tx, ty = _pair(leave, "to")
        st["dx"] += tx * q2
        st["dy"] += ty * q2
        st["rot"] += _num(leave, "rot", 0) * q2
        st["scale"] *= 1 + (_num(leave, "scale", 1) - 1) * q2
        if leave.get("fade") == "true":
            st["alpha"] *= 1 - q
        st["gone"] = q >= 1
    return st


def timeline_end(root: Node) -> float:
    from spec import parse_anim

    end = 0.0
    for n in root.walk():
        e, l = parse_anim(n.attrs.get("AnimEnter")), parse_anim(n.attrs.get("AnimLeave"))
        if e:
            end = max(end, _num(e, "delay", 0) + _num(e, "dur", 0.45))
        if l:
            end = max(end, _num(l, "at", 1) + _num(l, "dur", 0.5))
    return end


def visible_gui_children(node: Node):
    out = []
    for c in node.children:
        if c.cls not in GUI_OBJECTS or effective(c, "Visible") is False:
            continue
        if HIDE_START_HIDDEN["on"] and c.attrs.get("StartHidden") and c.name != HIDE_START_HIDDEN["except"]:
            continue
        if "AnimLeave" in c.attrs:
            st = anim_state(c, ANIM["t"])
            if st and st["gone"]:
                continue  # a prop that has flown off; it no longer takes part in layout or checks
        out.append(c)
    return out


def _udim(u, basis, px):
    return u[0] * basis + u[1] * px


def corner_radii(node: Node, w: float, h: float, px: float):
    """(tl, tr, br, bl) in pixels, clamped the way the engine clamps them."""
    c = node.child("UICorner")
    if not c:
        return (0.0, 0.0, 0.0, 0.0)
    short = min(w, h)
    per = [c.props.get(k) for k in ("TopLeftRadius", "TopRightRadius", "BottomRightRadius", "BottomLeftRadius")]
    base = c.props.get("CornerRadius")
    if base is None and all(p is None for p in per):
        base = (0.0, 8.0)
    out = []
    for p in per:
        u = p if p is not None else (base if base is not None else (0.0, 0.0))
        out.append(max(0.0, min(short / 2, u[0] * short + u[1] * px)))
    return tuple(out)


def padding(node: Node, w: float, h: float, px: float):
    """(left, top, right, bottom) in pixels."""
    p = node.child("UIPadding")
    if not p:
        return (0.0, 0.0, 0.0, 0.0)
    g = lambda k, basis: _udim(p.props.get(k, (0.0, 0.0)), basis, px)
    return (g("PaddingLeft", w), g("PaddingTop", h), g("PaddingRight", w), g("PaddingBottom", h))


# ------------------------------------------------------------------ text metrics

_TAG = re.compile(r"<[^>]+>")


def plain_text(node: Node) -> str:
    t = effective(node, "Text") or ""
    if effective(node, "RichText"):
        t = re.sub(r"<br\s*/?>", "\n", t)
        t = _TAG.sub("", t)
        for a, b in (("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&apos;", "'"), ("&amp;", "&")):
            t = t.replace(a, b)
    return t


def wrap_lines(text: str, font, max_w: float, wrap: bool):
    lines = []
    for para in text.split("\n"):
        if not wrap or max_w <= 0:
            lines.append(para)
            continue
        words = para.split(" ")
        cur = ""
        for word in words:
            trial = word if not cur else cur + " " + word
            if font.getlength(trial) <= max_w or not cur:
                cur = trial
            else:
                lines.append(cur)
                cur = word
        lines.append(cur)
    return lines


def text_layout(node: Node, w: float, h: float, px: float):
    """Resolve font size (TextScaled aware) and wrapped lines for a text node.

    Returns dict(font, size, lines, line_h, width, height, fits).
    """
    text = plain_text(node)
    face = effective(node, "FontFace") or {"family": "LegacyArial", "weight": "Regular", "style": "Normal"}
    line_mult = effective(node, "LineHeight") or 1.0
    scaled = bool(effective(node, "TextScaled"))
    wrapped = bool(effective(node, "TextWrapped")) or scaled
    cons = node.child("UITextSizeConstraint")
    max_size = (cons.props.get("MaxTextSize", 100) if cons else 100) * px
    min_size = (cons.props.get("MinTextSize", 1) if cons else 1) * px

    def at(size):
        f = fonts.get(face, size)
        lines = wrap_lines(text, f, w, wrapped)
        lh = size * line_mult
        width = max((f.getlength(l) for l in lines), default=0.0)
        return f, lines, lh, width, lh * len(lines)

    if scaled:
        hi = min(max_size, 100 * px, max(h, 1))
        lo = min(min_size, hi)
        best = lo
        for _ in range(12):
            mid = (lo + hi) / 2
            f, lines, lh, width, height = at(mid)
            if width <= w + 0.5 and height <= h + 0.5:
                best, lo = mid, mid
            else:
                hi = mid
        size = max(1.0, best)
    else:
        size = float(effective(node, "TextSize") or 14) * px
    f, lines, lh, width, height = at(size)
    return {"font": f, "size": size, "lines": lines, "line_h": lh, "width": width, "height": height,
            "fits": width <= w + 1 and height <= h + 1, "face": face}


# ------------------------------------------------------------------ measuring

CTX = {"vh": 1080.0, "avail": (1920.0, 1022.0), "k": 1.0}


def auto_scale_base(viewport_h: float) -> float:
    """The UIRuntime rule: UI authored at 1080p shrinks slower than the screen does, so phones stay tappable."""
    return max(0.55, min(1.5, (viewport_h / 1080.0) ** 0.4))


def modal_fill(viewport_h: float) -> float:
    """Share of the safe area a modal should occupy: most of a phone, about three quarters of a desktop."""
    t = max(0.0, min(1.0, (viewport_h - 500.0) / 500.0))
    return 0.94 - 0.18 * t


def _own_scale(node: Node) -> float:
    mode = node.attrs.get("AutoScale")
    if mode:
        s = auto_scale_base(CTX["vh"])
        if mode == "modal":
            sx, ox, sy, oy = effective(node, "Size") or (0, 0, 0, 0)
            aw, ah = CTX["avail"]
            fill = modal_fill(CTX["vh"])
            fits = []
            if sx == 0 and ox > 0:
                fits.append(fill * aw / ox)
            if sy == 0 and oy > 0:
                fits.append(fill * ah / oy)
            if fits:
                s = min(min(fits), 2.0)  # a modal grows or shrinks to fill the screen, whatever size it was drawn at
        return s
    s = node.child("UIScale")
    return float(s.props.get("Scale", 1.0)) if s else 1.0


def measure(node: Node, pw: float, ph: float, ppx: float):
    """Size of `node` inside a parent content box of pw x ph. -> (w, h, px)."""
    us = _own_scale(node)
    px = ppx * us
    sx, ox, sy, oy = effective(node, "Size") or (0, 0, 0, 0)
    sc = effective(node, "SizeConstraint") or "RelativeXY"
    bw, bh = pw, ph
    if sc == "RelativeXX":
        bh = pw
    elif sc == "RelativeYY":
        bw = ph
    w = (bw * sx + ox * ppx) * us
    h = (bh * sy + oy * ppx) * us
    w, h = max(0.0, w), max(0.0, h)
    auto = effective(node, "AutomaticSize") or "None"
    if auto != "None":
        ew, eh = content_extent(node, w, h, px, auto)
        if "X" in auto:
            w = max(w, ew)
        if "Y" in auto:
            h = max(h, eh)
    w, h = _constrain(node, w, h, px)
    return w, h, px


def _constrain(node: Node, w: float, h: float, px: float):
    sc = node.child("UISizeConstraint")
    if sc:
        mn = sc.props.get("MinSize", (0.0, 0.0))
        mx = sc.props.get("MaxSize", (float("inf"), float("inf")))
        w = max(mn[0] * px, min(mx[0] * px if mx[0] != float("inf") else w, w))
        h = max(mn[1] * px, min(mx[1] * px if mx[1] != float("inf") else h, h))
    ar = node.child("UIAspectRatioConstraint")
    if ar:
        r = max(1e-4, float(ar.props.get("AspectRatio", 1.0)))
        kind = ar.props.get("AspectType", "FitWithinMaxSize")
        axis = ar.props.get("DominantAxis", "Width")
        if kind == "ScaleWithParentSize":
            if axis == "Width":
                h = w / r
            else:
                w = h * r
        else:
            if h <= 0 or w / max(h, 1e-6) > r:
                w = h * r
            else:
                h = w / r
    return w, h


def content_extent(node: Node, w: float, h: float, px: float, auto: str):
    pl, pt, pr, pb = padding(node, w, h, px)
    ew = eh = 0.0
    if node.cls in TEXT_CLASSES:
        avail_w = (w - pl - pr) if ("X" not in auto and w > 0) else 1e9
        saved = node.props.get("TextScaled")
        tl = text_layout(node, avail_w, 1e9, px) if not saved else text_layout(node, max(w - pl - pr, 1), max(h - pt - pb, 1), px)
        ew, eh = tl["width"], tl["height"]
    for child, x, y, cw, ch, _ in arrange(node, w, h, px):
        ew = max(ew, x + cw - pl)
        eh = max(eh, y + ch - pt)
    return ew + pl + pr, eh + pt + pb


# ------------------------------------------------------------------ arranging

def _sorted_for_layout(children, layout_node):
    order = layout_node.props.get("SortOrder", "LayoutOrder")
    if order == "Name":
        return sorted(children, key=lambda c: c.name)
    return sorted(children, key=lambda c: effective(c, "LayoutOrder") or 0)


def content_box(node: Node, w: float, h: float, px: float):
    """(x, y, w, h) of the area children are laid out in, relative to the node's top-left."""
    pl, pt, pr, pb = padding(node, w, h, px)
    cw, ch = w, h
    if node.cls == "ScrollingFrame":
        cs = effective(node, "CanvasSize") or (0, 0, 2, 0)
        auto = effective(node, "AutomaticCanvasSize") or "None"
        if "X" not in auto:
            cw = max(w, cs[0] * w + cs[1] * px)
        if "Y" not in auto:
            ch = max(h, cs[2] * h + cs[3] * px)
    return pl, pt, max(0.0, cw - pl - pr), max(0.0, ch - pt - pb)


def arrange(node: Node, w: float, h: float, px: float):
    """Place the GuiObject children of `node`. -> [(child, x, y, w, h, px)] relative to node top-left."""
    kids = visible_gui_children(node)
    if not kids:
        return []
    bx, by, bw, bh = content_box(node, w, h, px)
    grid = node.child("UIGridLayout")
    lst = node.child("UIListLayout")
    if grid:
        return _arrange_grid(node, grid, kids, bx, by, bw, bh, px)
    if lst:
        return _arrange_list(node, lst, kids, bx, by, bw, bh, px)
    out = []
    for c in kids:
        cw, ch, cpx = measure(c, bw, bh, px)
        psx, pox, psy, poy = effective(c, "Position") or (0, 0, 0, 0)
        ax, ay = effective(c, "AnchorPoint") or (0, 0)
        x = bx + bw * psx + pox * px - ax * cw
        y = by + bh * psy + poy * px - ay * ch
        out.append((c, x, y, cw, ch, cpx))
    return out


def _flex_mode(child: Node):
    f = child.child("UIFlexItem")
    if not f:
        return "None", 0.0, 0.0
    mode = f.props.get("FlexMode", "None")
    grow, shrink = f.props.get("GrowRatio", 0.0), f.props.get("ShrinkRatio", 0.0)
    if mode == "Fill":
        return mode, 1.0, 1.0
    if mode == "Grow":
        return mode, 1.0, 0.0
    if mode == "Shrink":
        return mode, 0.0, 1.0
    if mode == "Custom":
        return mode, grow, shrink
    return "None", 0.0, 0.0


def _arrange_list(node, lst, kids, bx, by, bw, bh, px):
    horizontal = lst.props.get("FillDirection", "Vertical") == "Horizontal"
    kids = _sorted_for_layout(kids, lst)
    pad_u = lst.props.get("Padding", (0.0, 0.0))
    main_size, cross_size = (bw, bh) if horizontal else (bh, bw)
    gap = pad_u[0] * main_size + pad_u[1] * px
    main_flex = lst.props.get("HorizontalFlex" if horizontal else "VerticalFlex", "None")
    cross_flex = lst.props.get("VerticalFlex" if horizontal else "HorizontalFlex", "None")
    halign = lst.props.get("HorizontalAlignment", "Left")
    valign = lst.props.get("VerticalAlignment", "Top")
    main_align = {"Left": 0.0, "Center": 0.5, "Right": 1.0, "Top": 0.0, "Bottom": 1.0}[halign if horizontal else valign]
    cross_align = {"Left": 0.0, "Center": 0.5, "Right": 1.0, "Top": 0.0, "Bottom": 1.0}[valign if horizontal else halign]
    line_align = lst.props.get("ItemLineAlignment", "Automatic")
    wraps = bool(lst.props.get("Wraps", False))

    items = []
    for c in kids:
        cw, ch, cpx = measure(c, bw, bh, px)
        items.append([c, cw, ch, cpx])

    lines, cur, used = [], [], 0.0
    for it in items:
        m = it[1] if horizontal else it[2]
        need = m if not cur else used + gap + m
        if wraps and cur and need > main_size + 0.5:
            lines.append(cur)
            cur, used = [it], m
        else:
            cur.append(it)
            used = need
    if cur:
        lines.append(cur)

    out = []
    line_cross_sizes = [max((it[2] if horizontal else it[1]) for it in line) for line in lines]
    total_cross = sum(line_cross_sizes) + gap * (len(lines) - 1)
    if len(lines) == 1 and not wraps:
        cross_cursor = 0.0
    else:
        cross_cursor = (cross_size - total_cross) * cross_align
    for line, line_cross in zip(lines, line_cross_sizes):
        mains = [(it[1] if horizontal else it[2]) for it in line]
        n = len(line)
        free = main_size - sum(mains) - gap * (n - 1)
        ratios = []
        for it in line:
            _, g, s = _flex_mode(it[0])
            if main_flex == "Fill":
                g, s = max(g, 1.0), max(s, 1.0)
            ratios.append((g, s))
        if free > 0 and sum(r[0] for r in ratios) > 0:
            tot = sum(r[0] for r in ratios)
            mains = [m + free * r[0] / tot for m, r in zip(mains, ratios)]
            free = 0.0
        elif free < 0 and sum(r[1] for r in ratios) > 0:
            tot = sum(r[1] for r in ratios)
            mains = [max(0.0, m + free * r[1] / tot) for m, r in zip(mains, ratios)]
            free = 0.0
        spacing, start = gap, free * main_align
        if free > 0 and main_flex == "SpaceBetween" and n > 1:
            spacing, start = gap + free / (n - 1), 0.0
        elif free > 0 and main_flex == "SpaceAround":
            spacing, start = gap + free / n, free / n / 2
        elif free > 0 and main_flex == "SpaceEvenly":
            spacing, start = gap + free / (n + 1), free / (n + 1)
        cursor = start
        for it, m in zip(line, mains):
            c, cw, ch, cpx = it
            cross = ch if horizontal else cw
            stretch = cross_flex == "Fill" or line_align == "Stretch"
            fi = c.child("UIFlexItem")
            if fi and fi.props.get("ItemLineAlignment", "Automatic") == "Stretch":
                stretch = True
            if len(lines) == 1 and not wraps:
                space = cross_size
                if stretch:
                    cross = space
                cpos = (space - cross) * cross_align
            else:
                if stretch:
                    cross = line_cross
                la = {"Start": 0.0, "Center": 0.5, "End": 1.0}.get(line_align, cross_align)
                cpos = cross_cursor + (line_cross - cross) * la
            if horizontal:
                out.append((c, bx + cursor, by + cpos, m, cross, cpx))
            else:
                out.append((c, bx + cpos, by + cursor, cross, m, cpx))
            cursor += m + spacing
        cross_cursor += line_cross + gap
    return out


def _arrange_grid(node, grid, kids, bx, by, bw, bh, px):
    kids = _sorted_for_layout(kids, grid)
    cs = grid.props.get("CellSize", (0, 100, 0, 100))
    cp = grid.props.get("CellPadding", (0, 5, 0, 5))
    cw = cs[0] * bw + cs[1] * px
    ch = cs[2] * bh + cs[3] * px
    gx = cp[0] * bw + cp[1] * px
    gy = cp[2] * bh + cp[3] * px
    ar = grid.child("UIAspectRatioConstraint")
    if ar:
        r = max(1e-4, ar.props.get("AspectRatio", 1.0))
        if ar.props.get("DominantAxis", "Width") == "Width":
            ch = cw / r
        else:
            cw = ch * r
    horizontal = grid.props.get("FillDirection", "Horizontal") == "Horizontal"
    max_cells = int(grid.props.get("FillDirectionMaxCells", 0) or 0)
    if horizontal:
        per = max(1, int((bw + gx + 0.5) // max(1e-6, cw + gx)))
    else:
        per = max(1, int((bh + gy + 0.5) // max(1e-6, ch + gy)))
    if max_cells > 0:
        per = min(per, max_cells)
    n = len(kids)
    lines = (n + per - 1) // per
    cols, rows = (min(per, n), lines) if horizontal else (lines, min(per, n))
    tw = cols * cw + (cols - 1) * gx
    th = rows * ch + (rows - 1) * gy
    ha = {"Left": 0.0, "Center": 0.5, "Right": 1.0}[grid.props.get("HorizontalAlignment", "Left")]
    va = {"Top": 0.0, "Center": 0.5, "Bottom": 1.0}[grid.props.get("VerticalAlignment", "Top")]
    ox = bx + (bw - tw) * ha
    oy = by + (bh - th) * va
    out = []
    for i, c in enumerate(kids):
        if horizontal:
            col, row = i % per, i // per
        else:
            row, col = i % per, i // per
        out.append((c, ox + col * (cw + gx), oy + row * (ch + gy), cw, ch, px * _own_scale(c)))
    return out


# ------------------------------------------------------------------ placing

def place(node: Node, x: float, y: float, w: float, h: float, px: float):
    node.rect = (x, y, w, h)
    node.px = px
    for child, cx, cy, cw, ch, cpx in arrange(node, w, h, px):
        place(child, x + cx, y + cy, cw, ch, cpx)
    if node.cls == "ScrollingFrame":
        ext_w = ext_h = 0.0
        for c in visible_gui_children(node):
            r = c.rect
            ext_w = max(ext_w, r[0] + r[2] - x)
            ext_h = max(ext_h, r[1] + r[3] - y)
        pl, pt, pr, pb = padding(node, w, h, px)
        node.canvas = (max(w, ext_w + pr), max(h, ext_h + pb))


def screen_rect(root: Node, device: str, render_scale: float = 1.0):
    """Area a ScreenGui lays its children out in, honouring ScreenInsets."""
    vw, vh, topbar, safe, _ = DEVICES[device]
    insets = effective(root, "ScreenInsets") or "CoreUISafeInsets"
    if root.props.get("IgnoreGuiInset") is True and "ScreenInsets" not in root.explicit:
        insets = "DeviceSafeInsets"
    l, t, r, b = safe
    if insets == "None":
        x0, y0, x1, y1 = 0, 0, vw, vh
    elif insets == "DeviceSafeInsets":
        x0, y0, x1, y1 = l, t, vw - r, vh - b
    elif insets == "TopbarSafeInsets":
        x0, y0, x1, y1 = l + 132, 0, vw - r - 12, topbar
    else:
        x0, y0, x1, y1 = l, max(t, topbar), vw - r, vh - b
    k = render_scale
    return (x0 * k, y0 * k, (x1 - x0) * k, (y1 - y0) * k)


def layout_tree(root: Node, device: str = "pc", render_scale: float = 1.0):
    vw, vh = DEVICES[device][:2]
    if root.cls in ("ScreenGui",):
        x, y, w, h = screen_rect(root, device, render_scale)
    elif root.cls in ("SurfaceGui", "BillboardGui"):
        x, y, w, h = 0, 0, vw * render_scale, vh * render_scale
    else:
        x, y, w, h = 0, 0, vw * render_scale, vh * render_scale
    root.rect = (x, y, w, h)
    root.px = render_scale
    CTX["vh"] = float(vh)
    CTX["avail"] = (w / render_scale, h / render_scale)
    if root.cls in GUI_OBJECTS:
        cw, ch, cpx = measure(root, w, h, render_scale)
        place(root, x, y, cw, ch, cpx)
    else:
        for child, cx, cy, cw, ch, cpx in arrange(root, w, h, render_scale):
            place(child, x + cx, y + cy, cw, ch, cpx)
    return root
