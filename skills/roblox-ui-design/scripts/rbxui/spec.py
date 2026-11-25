"""Load a UI spec (JSON) into a tree of typed Roblox instances.

A spec is a JSON description of real Roblox instances. PascalCase keys are real
Roblox properties (checked against the engine API schema). lowercase keys are
sugar that expands into real child instances (UICorner, UIStroke, ...).

Pipeline:  raw JSON -> extends merge -> component expansion -> token resolution
           -> sugar expansion -> typed Node tree.
"""
from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import color as colorlib

HERE = Path(__file__).resolve().parent
SKILL_ROOT = HERE.parent.parent

SCHEMA = json.loads((HERE / "schema.json").read_text())
CLASSES = SCHEMA["classes"]
ENUMS = SCHEMA["enums"]

TEXT_CLASSES = {"TextLabel", "TextButton", "TextBox"}
IMAGE_CLASSES = {"ImageLabel", "ImageButton"}
BUTTON_CLASSES = {"TextButton", "ImageButton"}
GUI_OBJECTS = {
    "Frame", "CanvasGroup", "ScrollingFrame", "ViewportFrame", "VideoFrame",
    "TextLabel", "TextButton", "TextBox", "ImageLabel", "ImageButton",
}
LAYER_COLLECTORS = {"ScreenGui", "SurfaceGui", "BillboardGui"}

# Enum.Font legacy names -> (family, weight, style)
LEGACY_FONTS = {
    "Legacy": ("LegacyArial", "Regular", "Normal"),
    "Arial": ("Arimo", "Regular", "Normal"),
    "ArialBold": ("Arimo", "Bold", "Normal"),
    "SourceSans": ("SourceSansPro", "Regular", "Normal"),
    "SourceSansBold": ("SourceSansPro", "Bold", "Normal"),
    "SourceSansSemibold": ("SourceSansPro", "SemiBold", "Normal"),
    "SourceSansLight": ("SourceSansPro", "Light", "Normal"),
    "SourceSansItalic": ("SourceSansPro", "Regular", "Italic"),
    "Gotham": ("Montserrat", "Regular", "Normal"),
    "GothamMedium": ("Montserrat", "Medium", "Normal"),
    "GothamBold": ("Montserrat", "Bold", "Normal"),
    "GothamBlack": ("Montserrat", "Heavy", "Normal"),
    "BuilderSans": ("BuilderSans", "Regular", "Normal"),
    "BuilderSansMedium": ("BuilderSans", "Medium", "Normal"),
    "BuilderSansBold": ("BuilderSans", "Bold", "Normal"),
    "BuilderSansExtraBold": ("BuilderSans", "ExtraBold", "Normal"),
    "RobotoMono": ("RobotoMono", "Regular", "Normal"),
    "Code": ("Inconsolata", "Regular", "Normal"),
    "Highway": ("HighwayGothic", "Regular", "Normal"),
    "SciFi": ("Zekton", "Regular", "Normal"),
    "Arcade": ("PressStart2P", "Regular", "Normal"),
    "Fantasy": ("Balthazar", "Regular", "Normal"),
    "Antique": ("RomanAntique", "Regular", "Normal"),
    "Cartoon": ("ComicNeueAngular", "Regular", "Normal"),
    "Bodoni": ("AccanthisADFStd", "Regular", "Normal"),
    "Garamond": ("Guru", "Regular", "Normal"),
    "NunitoBold": ("Nunito", "Bold", "Normal"),
    "JosefinSansBold": ("JosefinSans", "Bold", "Normal"),
    "OswaldBold": ("Oswald", "Bold", "Normal"),
    "TitilliumWebBold": ("TitilliumWeb", "Bold", "Normal"),
}

SUGAR_KEYS = {
    "corner", "stroke", "strokes", "gradient", "shadow", "padding", "aspect", "list", "grid",
    "scale", "maxText", "minText", "sizeLimit", "flex", "tags", "attrs", "sourceFile",
    "autoscale", "motion", "opens", "closes", "toggles", "startHidden",
}
RUNTIME_ATTRS = {"autoscale": "AutoScale", "motion": "Motion", "opens": "Opens", "closes": "Closes",
                 "toggles": "Toggles", "startHidden": "StartHidden"}
RUNTIME_SCRIPT = SKILL_ROOT / "assets" / "runtime" / "UIRuntime.client.luau"
MOTION_STYLES = ("bouncy", "snappy", "calm")
RESERVED = {"class", "name", "children", "use", "slot", "if"}


class SpecError(Exception):
    """A problem in the spec that the author has to fix."""

    def __init__(self, path: str, message: str):
        super().__init__(f"{path}: {message}")
        self.path = path
        self.message = message


@dataclass
class Node:
    cls: str
    name: str
    props: dict = field(default_factory=dict)
    children: list = field(default_factory=list)
    tags: list = field(default_factory=list)
    attrs: dict = field(default_factory=dict)
    path: str = ""
    explicit: set = field(default_factory=set)  # property names the author actually wrote
    parent: "Node | None" = None

    def child(self, cls: str):
        for c in self.children:
            if c.cls == cls:
                return c
        return None

    def children_of(self, cls: str):
        return [c for c in self.children if c.cls == cls]

    def get(self, prop: str, default=None):
        return self.props.get(prop, default)

    def walk(self):
        yield self
        for c in self.children:
            yield from c.walk()

    @property
    def is_gui(self):
        return self.cls in GUI_OBJECTS


@dataclass
class Spec:
    root: Node
    meta: dict
    tokens: dict
    raw: dict
    source: Path | None
    problems: list  # (severity, path, rule, message) raised while loading
    components_used: dict


# ---------------------------------------------------------------- JSON loading

def _strip_comments(text: str) -> str:
    """Allow // line comments and trailing commas: models write them constantly."""
    out, i, n, in_str = [], 0, len(text), False
    while i < n:
        ch = text[i]
        if in_str:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 1
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
            out.append(ch)
        elif ch == "/" and text[i : i + 2] == "//":
            while i < n and text[i] != "\n":
                i += 1
            continue
        elif ch == "/" and text[i : i + 2] == "/*":
            j = text.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue
        else:
            out.append(ch)
        i += 1
    cleaned = "".join(out)
    return re.sub(r",(\s*[}\]])", r"\1", cleaned)


def load_json(path: Path) -> dict:
    text = Path(path).read_text(encoding="utf-8")
    try:
        return json.loads(_strip_comments(text))
    except json.JSONDecodeError as e:
        raise SpecError(str(path), f"not valid JSON (line {e.lineno}, column {e.colno}): {e.msg}")


def _deep_merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


# ---------------------------------------------------------------- tokens

class Tokens:
    def __init__(self, data: dict):
        self.data = data

    def lookup(self, name: str, path: str = "tokens"):
        cur = self.data
        for part in name.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                known = ", ".join(sorted(self.flat())[:40])
                raise SpecError(path, f"unknown token ${name}. Defined tokens: {known}")
        return cur

    def flat(self, d=None, prefix=""):
        d = self.data if d is None else d
        out = []
        for k, v in d.items():
            if k.startswith("_"):
                continue
            if isinstance(v, dict):
                out += self.flat(v, prefix + k + ".")
            else:
                out.append(prefix + k)
        return out

    def resolve(self, value, path: str, depth=0):
        """Replace whole-string '$token' references by the token value (any JSON type)."""
        if depth > 24:
            raise SpecError(path, "token reference cycle")
        if isinstance(value, str):
            m = re.fullmatch(r"\$([A-Za-z0-9_.\-]+)", value.strip())
            if m:
                return self.resolve(self.lookup(m.group(1), path), path, depth + 1)
            return value
        if isinstance(value, list):
            return [self.resolve(v, path, depth + 1) for v in value]
        if isinstance(value, dict):
            return {k: self.resolve(v, path, depth + 1) for k, v in value.items()}
        return value

    def color(self, value, path: str):
        if isinstance(value, (list, tuple)) and len(value) == 3 and all(isinstance(v, (int, float)) for v in value):
            if any(v > 1 for v in value):
                return tuple(v / 255 for v in value)
            return tuple(float(v) for v in value)
        if not isinstance(value, str):
            raise SpecError(path, f"expected a colour ('#RRGGBB', '$token' or shade($token,-2)), got {value!r}")
        try:
            return colorlib.evaluate(value, lambda n: self._color_token(n, path))
        except colorlib.ColorExprError as e:
            raise SpecError(path, str(e))
        except ValueError as e:
            raise SpecError(path, str(e))

    def _color_token(self, name: str, path: str):
        v = self.lookup(name, path)
        if isinstance(v, (list, tuple)):
            return self.color(v, path)
        if not isinstance(v, str):
            raise SpecError(path, f"token ${name} is not a colour (it is {v!r})")
        return v


# ---------------------------------------------------------------- components

_PARAM = re.compile(r"\{\{\s*([A-Za-z0-9_]+)\s*\}\}")


def _subst(value, params: dict, path: str):
    if isinstance(value, str):
        m = _PARAM.fullmatch(value.strip())
        if m:
            key = m.group(1)
            if key not in params:
                raise SpecError(path, f"component uses undefined parameter {{{{{key}}}}}")
            return copy.deepcopy(params[key])

        def rep(mm):
            key = mm.group(1)
            if key not in params:
                raise SpecError(path, f"component uses undefined parameter {{{{{key}}}}}")
            v = params[key]
            if isinstance(v, bool):
                return "true" if v else "false"
            return str(v)

        return _PARAM.sub(rep, value)
    if isinstance(value, list):
        return [_subst(v, params, path) for v in value]
    if isinstance(value, dict):
        return {k: _subst(v, params, path) for k, v in value.items()}
    return value


def _falsy(v) -> bool:
    return v in (None, False, "", 0, "false", "False", "none", "None") or v == []


def _expand_components(raw, components: dict, path: str, used: dict, depth=0):
    """Return a list of plain nodes (a node may vanish through `if`)."""
    if not isinstance(raw, dict):
        raise SpecError(path, f"a node must be a JSON object, got {type(raw).__name__}")
    if depth > 16:
        raise SpecError(path, "components nested too deeply (does a component use itself?)")
    if "if" in raw and _falsy(raw["if"]):
        return []
    if "use" in raw:
        cname = raw["use"]
        if cname not in components:
            raise SpecError(path, f"unknown component {cname!r}. Available: {', '.join(sorted(components)) or '(none)'}")
        used[cname] = used.get(cname, 0) + 1
        cdef = components[cname]
        declared = dict(cdef.get("params", {}))
        template = cdef["node"] if "node" in cdef else {k: v for k, v in cdef.items() if k not in ("params", "doc")}
        params = dict(declared)
        overrides, extra_children = {}, []
        for k, v in raw.items():
            if k in ("use", "if"):
                continue
            if k == "children":
                extra_children = v
            elif k in declared:
                params[k] = v
            else:
                overrides[k] = v
        node = _subst(copy.deepcopy(template), params, f"{path}<{cname}>")
        for k, v in overrides.items():
            if k in RESERVED or k in SUGAR_KEYS or (k[:1].isupper()):
                node[k] = v
            else:
                raise SpecError(
                    path,
                    f"{k!r} is not a parameter of component {cname!r} "
                    f"(parameters: {', '.join(sorted(declared)) or 'none'}) and not a Roblox property",
                )
        if extra_children:
            slot = _find_slot(node) or node
            slot.setdefault("children", [])
            slot["children"] = list(slot["children"]) + list(extra_children)
        node.setdefault("name", raw.get("name", cname))
        return _expand_components(node, components, path, used, depth + 1)
    out = {k: v for k, v in raw.items() if k != "children"}
    kids = []
    for i, ch in enumerate(raw.get("children", []) or []):
        label = ch.get("name") or ch.get("use") or ch.get("class") or "?" if isinstance(ch, dict) else "?"
        kids += _expand_components(ch, components, f"{path}/{label}[{i}]", used, depth)
    out["children"] = kids
    return [out]


def _find_slot(node: dict):
    if node.get("slot"):
        return node
    for ch in node.get("children", []) or []:
        if isinstance(ch, dict):
            found = _find_slot(ch)
            if found:
                return found
    return None


# ---------------------------------------------------------------- value typing

def _num(v, path):
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise SpecError(path, f"expected a number, got {v!r}")
    return float(v)


def _numbers_from_string(s: str):
    return [float(x) for x in re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", s)]


def parse_udim2(v, path):
    if isinstance(v, str):
        v = _numbers_from_string(v)
    if isinstance(v, dict):
        if "scale" in v or "offset" in v:
            sc, of = v.get("scale", [0, 0]), v.get("offset", [0, 0])
            return (float(sc[0]), float(of[0]), float(sc[1]), float(of[1]))
        if "X" in v and "Y" in v:
            x, y = parse_udim(v["X"], path), parse_udim(v["Y"], path)
            return (x[0], x[1], y[0], y[1])
    if isinstance(v, (list, tuple)):
        if len(v) == 4 and all(isinstance(x, (int, float)) for x in v):
            return tuple(float(x) for x in v)
        if len(v) == 2 and all(isinstance(x, (list, tuple)) and len(x) == 2 for x in v):
            return (float(v[0][0]), float(v[0][1]), float(v[1][0]), float(v[1][1]))
    raise SpecError(path, f"expected UDim2 as [scaleX, offsetX, scaleY, offsetY], got {v!r}")


def parse_udim(v, path):
    if isinstance(v, str):
        v = _numbers_from_string(v)
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return (0.0, float(v))
    if isinstance(v, (list, tuple)) and len(v) == 2:
        return (float(v[0]), float(v[1]))
    raise SpecError(path, f"expected UDim as [scale, offset] (or a plain pixel number), got {v!r}")


def parse_vec2(v, path):
    if isinstance(v, str):
        v = _numbers_from_string(v)
    if isinstance(v, (list, tuple)) and len(v) == 2:
        return (float(v[0]), float(v[1]))
    raise SpecError(path, f"expected Vector2 as [x, y], got {v!r}")


def parse_vec3(v, path):
    if isinstance(v, (list, tuple)) and len(v) == 3:
        return tuple(float(x) for x in v)
    raise SpecError(path, f"expected Vector3 as [x, y, z], got {v!r}")


def parse_rect(v, path):
    if isinstance(v, (list, tuple)) and len(v) == 4:
        return tuple(float(x) for x in v)
    raise SpecError(path, f"expected Rect as [minX, minY, maxX, maxY], got {v!r}")


def parse_enum(v, enum_name, path):
    items = ENUMS[enum_name]
    if isinstance(v, str):
        name = v.split(".")[-1]
        if name in items:
            return name
        for k in items:
            if k.lower() == name.lower():
                return k
    elif isinstance(v, (int, float)) and not isinstance(v, bool):
        for k, val in items.items():
            if val == int(v):
                return k
    raise SpecError(path, f"{v!r} is not a valid Enum.{enum_name}; choose one of: {', '.join(items)}")


def parse_font(v, path):
    """-> {'family': str, 'weight': FontWeight name, 'style': 'Normal'|'Italic'}"""
    fam, weight, style = None, "Regular", "Normal"
    if isinstance(v, dict):
        fam = v.get("family") or v.get("Family")
        weight = v.get("weight", v.get("Weight", "Regular"))
        style = v.get("style", v.get("Style", "Normal"))
    elif isinstance(v, (list, tuple)) and v:
        fam = v[0]
        if len(v) > 1:
            weight = v[1]
        if len(v) > 2:
            style = v[2]
    elif isinstance(v, str):
        s = v.strip()
        if s.startswith("Enum.Font."):
            s = s[len("Enum.Font."):]
        if s.startswith("rbxasset") or s.startswith("rbxassetid"):
            m = re.match(r"(rbxassetid://\d+|rbxasset://[^:]+?\.json)(?::(\w+))?(?::(\w+))?$", s)
            if not m:
                raise SpecError(path, f"cannot read font {v!r}")
            fam, weight, style = m.group(1), m.group(2) or "Regular", m.group(3) or "Normal"
        else:
            parts = re.split(r"[:\s]+", s)
            fam = parts[0]
            if len(parts) > 1:
                weight = parts[1]
            if len(parts) > 2:
                style = parts[2]
            if len(parts) == 1 and fam in LEGACY_FONTS:
                fam, weight, style = LEGACY_FONTS[fam]
    if not fam or not isinstance(fam, str):
        raise SpecError(path, f"expected a font like 'FredokaOne' or 'Montserrat:Bold', got {v!r}")
    m = re.fullmatch(r"rbxasset://fonts/families/(\w+)\.json", fam)
    if m:
        fam = m.group(1)
    if isinstance(weight, (int, float)):
        weight = next((k for k, val in ENUMS["FontWeight"].items() if val == int(weight)), None)
    wmap = {k.lower(): k for k in ENUMS["FontWeight"]}
    wmap.update({"black": "Heavy", "normal": "Regular", "semibold": "SemiBold", "extrabold": "ExtraBold",
                 "extralight": "ExtraLight", "italic": "Regular"})
    if isinstance(weight, str) and weight.lower() == "italic":
        style = "Italic"
    w = wmap.get(str(weight).lower())
    if not w:
        raise SpecError(path, f"unknown font weight {weight!r}; use one of {', '.join(ENUMS['FontWeight'])}")
    st = "Italic" if str(style).lower() == "italic" else "Normal"
    return {"family": fam, "weight": w, "style": st}


def parse_color_sequence(v, tokens: Tokens, path):
    """-> [(t, (r,g,b)), ...] sorted, starting at 0 and ending at 1."""
    if isinstance(v, str):
        v = [v, v]
    if not isinstance(v, (list, tuple)) or not v:
        raise SpecError(path, f"expected a list of colours for a ColorSequence, got {v!r}")
    pts = []
    if all(isinstance(x, (list, tuple)) and len(x) == 2 and isinstance(x[0], (int, float)) for x in v):
        for t, c in v:
            pts.append((float(t), tokens.color(c, path)))
    else:
        n = len(v)
        if n == 1:
            v, n = [v[0], v[0]], 2
        for i, c in enumerate(v):
            pts.append((i / (n - 1), tokens.color(c, path)))
    pts.sort(key=lambda p: p[0])
    if pts[0][0] > 0:
        pts.insert(0, (0.0, pts[0][1]))
    if pts[-1][0] < 1:
        pts.append((1.0, pts[-1][1]))
    if len(pts) > 20:
        raise SpecError(path, "a ColorSequence can hold at most 20 keypoints")
    return pts


def parse_number_sequence(v, path):
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        v = [v, v]
    if not isinstance(v, (list, tuple)) or not v:
        raise SpecError(path, f"expected a list of numbers for a NumberSequence, got {v!r}")
    pts = []
    if all(isinstance(x, (list, tuple)) and len(x) == 2 for x in v):
        pts = [(float(t), float(val)) for t, val in v]
    else:
        n = len(v)
        if n == 1:
            v, n = [v[0], v[0]], 2
        pts = [(i / (n - 1), float(x)) for i, x in enumerate(v)]
    pts.sort(key=lambda p: p[0])
    if pts[0][0] > 0:
        pts.insert(0, (0.0, pts[0][1]))
    if pts[-1][0] < 1:
        pts.append((1.0, pts[-1][1]))
    return pts


def coerce(value, type_name: str, tokens: Tokens, path: str):
    if type_name == "bool":
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.lower() in ("true", "false"):
            return value.lower() == "true"
        raise SpecError(path, f"expected true/false, got {value!r}")
    if type_name == "int":
        return int(round(_num(value, path)))
    if type_name in ("float", "double"):
        return _num(value, path)
    if type_name in ("string", "ProtectedString"):
        if not isinstance(value, str):
            return json.dumps(value) if not isinstance(value, (int, float)) else str(value)
        return value
    if type_name == "Color3":
        return tokens.color(value, path)
    if type_name == "UDim2":
        return parse_udim2(value, path)
    if type_name == "UDim":
        return parse_udim(value, path)
    if type_name == "Vector2":
        return parse_vec2(value, path)
    if type_name == "Vector3":
        return parse_vec3(value, path)
    if type_name == "Rect":
        return parse_rect(value, path)
    if type_name == "ColorSequence":
        return parse_color_sequence(value, tokens, path)
    if type_name == "NumberSequence":
        return parse_number_sequence(value, path)
    if type_name == "Font":
        return parse_font(value, path)
    if type_name in ("ContentId", "Content"):
        if not isinstance(value, str):
            raise SpecError(path, f"expected an image string ('rbxassetid://123' or 'asset:name'), got {value!r}")
        return value
    if type_name.startswith("Enum:"):
        return parse_enum(value, type_name[5:], path)
    if type_name == "Ref":
        raise SpecError(path, "instance references cannot be set from a spec; wire them in a script")
    raise SpecError(path, f"unsupported property type {type_name}")


# ---------------------------------------------------------------- sugar

def _px_udim(v, path):
    return list(parse_udim(v, path))


def _sugar_children(cls: str, key: str, value, path: str, has_text: bool = True) -> list:
    """Expand one lowercase sugar key into raw child instance dicts."""
    p = f"{path}.{key}"
    if key == "corner":
        if isinstance(value, dict):
            names = {"tl": "TopLeftRadius", "tr": "TopRightRadius", "bl": "BottomLeftRadius", "br": "BottomRightRadius"}
            out = {"class": "UICorner"}
            for k, v in value.items():
                if k not in names:
                    raise SpecError(p, f"corner object keys are tl/tr/bl/br, got {k!r}")
                out[names[k]] = _px_udim(v, p)
            for full in names.values():
                out.setdefault(full, [0, 0])
            return [out]
        if value == "pill":
            value = [1, 0]
        return [{"class": "UICorner", "CornerRadius": _px_udim(value, p)}]
    if key in ("stroke", "strokes"):
        items = value if isinstance(value, list) else [value]
        out = []
        for it in items:
            if not isinstance(it, dict):
                raise SpecError(p, "stroke must be an object like {\"color\": \"#123\", \"thickness\": 3}")
            m = {"color": "Color", "thickness": "Thickness", "transparency": "Transparency", "mode": "ApplyStrokeMode",
                 "join": "LineJoinMode", "position": "BorderStrokePosition", "sizing": "StrokeSizingMode",
                 "offset": "BorderOffset", "z": "ZIndex"}
            node = {"class": "UIStroke", "children": []}
            for k, v in it.items():
                if k == "gradient":
                    node["children"] += _sugar_children("UIStroke", "gradient", v, p)
                elif k in m:
                    node[m[k]] = v
                elif k[:1].isupper():
                    node[k] = v
                else:
                    raise SpecError(p, f"unknown stroke key {k!r}; use {', '.join(m)}, gradient")
            if cls not in TEXT_CLASSES or not has_text:
                node.setdefault("ApplyStrokeMode", "Border")
            out.append(node)
        return out
    if key == "gradient":
        if isinstance(value, list):
            value = {"colors": value}
        if not isinstance(value, dict):
            raise SpecError(p, "gradient must be a list of colours or an object {colors, rotation, transparency}")
        m = {"colors": "Color", "color": "Color", "rotation": "Rotation", "transparency": "Transparency",
             "offset": "Offset", "type": "Type", "scale": "Scale", "tile": "TileMode"}
        node = {"class": "UIGradient"}
        for k, v in value.items():
            if k in m:
                node[m[k]] = v
            elif k[:1].isupper():
                node[k] = v
            else:
                raise SpecError(p, f"unknown gradient key {k!r}; use {', '.join(m)}")
        node.setdefault("Rotation", 90)
        return [node]
    if key == "shadow":
        if not isinstance(value, dict):
            raise SpecError(p, "shadow must be an object {color, blur, offset, spread, transparency, inset}")
        m = {"color": "Color", "blur": "BlurRadius", "transparency": "Transparency", "inset": "Inset", "mode": "Mode",
             "behind": "ShowBehindParent", "z": "ZIndex"}
        node = {"class": "UIShadow"}
        for k, v in value.items():
            if k == "offset":
                node["Offset"] = [0, v[0], 0, v[1]] if isinstance(v, list) and len(v) == 2 else v
            elif k == "spread":
                node["Spread"] = [0, v, 0, v] if isinstance(v, (int, float)) else v
            elif k in m:
                node[m[k]] = v
            elif k[:1].isupper():
                node[k] = v
            else:
                raise SpecError(p, f"unknown shadow key {k!r}")
        return [node]
    if key == "padding":
        if isinstance(value, dict):
            m = {"top": "PaddingTop", "bottom": "PaddingBottom", "left": "PaddingLeft", "right": "PaddingRight"}
            node = {"class": "UIPadding"}
            for k, v in value.items():
                if k not in m:
                    raise SpecError(p, "padding object keys are top/bottom/left/right")
                node[m[k]] = _px_udim(v, p)
            return [node]
        if isinstance(value, (int, float)):
            t = r = b = l = value
        elif isinstance(value, list) and len(value) == 2:
            t = b = value[0]
            l = r = value[1]
        elif isinstance(value, list) and len(value) == 4:
            t, r, b, l = value
        else:
            raise SpecError(p, "padding is a number, [vertical, horizontal] or [top, right, bottom, left]")
        return [{"class": "UIPadding", "PaddingTop": _px_udim(t, p), "PaddingRight": _px_udim(r, p),
                 "PaddingBottom": _px_udim(b, p), "PaddingLeft": _px_udim(l, p)}]
    if key == "aspect":
        if isinstance(value, dict):
            node = {"class": "UIAspectRatioConstraint"}
            m = {"ratio": "AspectRatio", "type": "AspectType", "axis": "DominantAxis"}
            for k, v in value.items():
                node[m.get(k, k)] = v
            return [node]
        return [{"class": "UIAspectRatioConstraint", "AspectRatio": value}]
    if key == "list":
        if not isinstance(value, dict):
            raise SpecError(p, "list must be an object like {\"dir\": \"H\", \"gap\": 8, \"align\": \"Center\"}")
        m = {"gap": "Padding", "align": "HorizontalAlignment", "valign": "VerticalAlignment", "wraps": "Wraps",
             "hflex": "HorizontalFlex", "vflex": "VerticalFlex", "sort": "SortOrder", "line": "ItemLineAlignment"}
        node = {"class": "UIListLayout"}
        for k, v in value.items():
            if k == "dir":
                d = str(v).lower()
                node["FillDirection"] = "Horizontal" if d in ("h", "horizontal", "row", "x") else "Vertical"
            elif k in m:
                node[m[k]] = v
            elif k[:1].isupper():
                node[k] = v
            else:
                raise SpecError(p, f"unknown list key {k!r}; use dir, {', '.join(m)}")
        node.setdefault("SortOrder", "LayoutOrder")
        return [node]
    if key == "grid":
        if not isinstance(value, dict):
            raise SpecError(p, "grid must be an object like {\"cell\": [0,120,0,140], \"gap\": 10}")
        m = {"cell": "CellSize", "max": "FillDirectionMaxCells", "align": "HorizontalAlignment",
             "valign": "VerticalAlignment", "sort": "SortOrder", "start": "StartCorner"}
        node = {"class": "UIGridLayout"}
        for k, v in value.items():
            if k == "gap":
                node["CellPadding"] = [0, v, 0, v] if isinstance(v, (int, float)) else v
            elif k == "dir":
                d = str(v).lower()
                node["FillDirection"] = "Horizontal" if d in ("h", "horizontal", "row", "x") else "Vertical"
            elif k in m:
                node[m[k]] = v
            elif k[:1].isupper():
                node[k] = v
            else:
                raise SpecError(p, f"unknown grid key {k!r}; use cell, gap, dir, {', '.join(m)}")
        node.setdefault("SortOrder", "LayoutOrder")
        return [node]
    if key == "scale":
        return [{"class": "UIScale", "Scale": value}]
    if key == "sizeLimit":
        node = {"class": "UISizeConstraint"}
        if "min" in value:
            node["MinSize"] = value["min"]
        if "max" in value:
            node["MaxSize"] = value["max"]
        return [node]
    if key == "flex":
        if isinstance(value, dict):
            node = {"class": "UIFlexItem"}
            m = {"mode": "FlexMode", "grow": "GrowRatio", "shrink": "ShrinkRatio", "line": "ItemLineAlignment"}
            for k, v in value.items():
                node[m.get(k, k)] = v
            return [node]
        return [{"class": "UIFlexItem", "FlexMode": value}]
    raise SpecError(p, f"unknown sugar key {key!r}")


# ---------------------------------------------------------------- build tree

def _build(raw: dict, tokens: Tokens, path: str, base_dir: Path | None, problems: list, parent=None) -> Node:
    cls = raw.get("class")
    if not cls:
        raise SpecError(path, "node has no \"class\" (e.g. \"class\": \"Frame\") and no \"use\"")
    if cls not in CLASSES:
        hint = ""
        low = {c.lower(): c for c in CLASSES}
        if cls.lower() in low:
            hint = f" Did you mean {low[cls.lower()]!r}?"
        raise SpecError(path, f"unknown class {cls!r}.{hint} Supported: {', '.join(sorted(CLASSES))}")
    name = raw.get("name") or cls
    node = Node(cls=cls, name=str(name), path=path, parent=parent)
    schema_props = CLASSES[cls]["props"]
    sugar_children, text_limits = [], {}

    for key, value in raw.items():
        if key in RESERVED or key.startswith("_"):
            continue
        ppath = f"{path}.{key}"
        try:
            value = tokens.resolve(value, ppath)
            if key in SUGAR_KEYS:
                if key == "tags":
                    node.tags = [str(t) for t in (value if isinstance(value, list) else [value])]
                elif key == "attrs":
                    if not isinstance(value, dict):
                        raise SpecError(ppath, "attrs must be an object of name -> string/number/bool")
                    node.attrs = dict(value)
                elif key in ("maxText", "minText"):
                    text_limits[key] = value
                elif key in RUNTIME_ATTRS:
                    if cls not in GUI_OBJECTS:
                        raise SpecError(ppath, f"{key!r} only applies to GuiObjects, not {cls}")
                    if key == "autoscale":
                        if value not in ("hud", "modal"):
                            raise SpecError(ppath, "autoscale must be \"hud\" (scale with the screen) or \"modal\" (also shrink to fit)")
                        if any(isinstance(c, dict) and c.get("class") == "UIScale" for c in raw.get("children", []) or []) or "scale" in raw:
                            raise SpecError(ppath, "autoscale adds its own UIScale; remove the other UIScale/scale on this node")
                        sugar_children.append({"class": "UIScale", "name": "AutoScale", "Scale": 1})
                    elif key == "motion":
                        if value not in ("button", "panel"):
                            raise SpecError(ppath, "motion must be \"button\" (hover/press feedback) or \"panel\" (animated open/close)")
                    elif key == "startHidden":
                        if not isinstance(value, bool):
                            raise SpecError(ppath, "startHidden must be true or false")
                        if not value:
                            continue
                    elif not isinstance(value, str):
                        raise SpecError(ppath, f"{key} takes the name of a panel in this ScreenGui")
                    node.attrs[RUNTIME_ATTRS[key]] = value
                elif key == "sourceFile":
                    src = (base_dir or Path(".")) / str(value)
                    if not src.exists():
                        raise SpecError(ppath, f"file not found: {src}")
                    node.props["Source"] = src.read_text(encoding="utf-8")
                    node.explicit.add("Source")
                else:
                    if cls not in GUI_OBJECTS and not (cls == "UIStroke" and key == "gradient"):
                        raise SpecError(ppath, f"{key!r} sugar only applies to GuiObjects, not {cls}")
                    has_text = bool(str(raw.get("Text", "")).strip())
                    sugar_children += _sugar_children(cls, key, value, path, has_text)
                continue
            if key == "Font" and cls in TEXT_CLASSES:
                node.props["FontFace"] = parse_font(value, ppath)
                node.explicit.add("FontFace")
                problems.append(("warn", path, "legacy-font-prop",
                                 "\"Font\" is the legacy enum property; write \"FontFace\": \"Family:Weight\" instead."))
                continue
            if key not in schema_props:
                raise SpecError(ppath, _unknown_prop_message(cls, key))
            node.props[key] = coerce(value, schema_props[key]["type"], tokens, ppath)
            node.explicit.add(key)
        except SpecError as e:
            problems.append(("error", e.path, "spec", e.message))

    if text_limits:
        c = {"class": "UITextSizeConstraint"}
        if "maxText" in text_limits:
            c["MaxTextSize"] = text_limits["maxText"]
        if "minText" in text_limits:
            c["MinTextSize"] = text_limits["minText"]
        sugar_children.append(c)

    kids = sugar_children + list(raw.get("children", []) or [])
    for i, ch in enumerate(kids):
        label = (ch.get("name") or ch.get("class") or "?") if isinstance(ch, dict) else "?"
        cpath = f"{path}/{label}"
        try:
            if not isinstance(ch, dict):
                raise SpecError(cpath, "child must be a JSON object")
            node.children.append(_build(ch, tokens, cpath, base_dir, problems, node))
        except SpecError as e:
            problems.append(("error", e.path, "spec", e.message))
    return node


COMMON_MISTAKES = {
    "CornerRadius": "CornerRadius belongs to a UICorner child. Write \"corner\": 12 on the node.",
    "Thickness": "Thickness belongs to a UIStroke child. Write \"stroke\": {\"color\": ..., \"thickness\": 3}.",
    "TextStroke": "Use \"stroke\": {...} on the text node (a UIStroke), or TextStrokeColor3 + TextStrokeTransparency.",
    "Color": "This class has no \"Color\". Use BackgroundColor3, TextColor3 or ImageColor3.",
    "BackgroundColor": "The property is BackgroundColor3.",
    "TextColor": "The property is TextColor3.",
    "ImageColor": "The property is ImageColor3.",
    "Transparency": "Use BackgroundTransparency / TextTransparency / ImageTransparency (or GroupTransparency on a CanvasGroup).",
    "Padding": "Padding belongs to UIPadding / UIListLayout. Write \"padding\": 12 or \"list\": {\"gap\": 8}.",
    "Gradient": "Write \"gradient\": [\"#top\", \"#bottom\"] (expands to a UIGradient child).",
    "Opacity": "Roblox uses transparency (0 = solid, 1 = invisible), not opacity.",
    "Image": "Only ImageLabel / ImageButton have Image.",
    "Text": "Only TextLabel / TextButton / TextBox have Text.",
    "BorderRadius": "Roblox has no BorderRadius. Write \"corner\": 12.",
    "FontSize": "Use TextSize (a number of pixels).",
    "FontWeight": "Weight is part of FontFace: \"FontFace\": \"Montserrat:Bold\".",
    "Scale": "Scale belongs to a UIScale child. Write \"scale\": 1.",
    "AspectRatio": "AspectRatio belongs to UIAspectRatioConstraint. Write \"aspect\": 1.5.",
}


def _unknown_prop_message(cls: str, key: str) -> str:
    props = CLASSES[cls]["props"]
    if key in COMMON_MISTAKES and key not in props:
        return f"{cls} has no property {key!r}. {COMMON_MISTAKES[key]}"
    if key[:1].islower():
        return (f"unknown key {key!r}. Lowercase keys are sugar ({', '.join(sorted(SUGAR_KEYS))}); "
                f"Roblox properties are PascalCase.")
    import difflib

    close = difflib.get_close_matches(key, list(props), n=3, cutoff=0.6)
    hint = f" Did you mean {', '.join(close)}?" if close else ""
    return f"{cls} has no property {key!r}.{hint}"


def load(path) -> Spec:
    path = Path(path)
    raw = load_json(path)
    return from_dict(raw, path)


def from_dict(raw: dict, source: Path | None = None) -> Spec:
    if not isinstance(raw, dict):
        raise SpecError("spec", "top level must be a JSON object with \"meta\", \"tokens\" and \"root\"")
    problems = []
    tokens_data, components = {}, {}
    # "extends": a design-system file (tokens + components) shared by every screen of one game
    bases = raw.get("extends")
    if bases:
        for base in ([bases] if isinstance(bases, str) else bases):
            base_path = (source.parent / base) if source else Path(base)
            if not base_path.exists():
                raise SpecError("extends", f"file not found: {base_path}")
            data = load_json(base_path)
            tokens_data = _deep_merge(tokens_data, data.get("tokens", {}) or {})
            components.update(data.get("components", {}) or {})
            for k, v in (data.get("meta", {}) or {}).items():
                raw.setdefault("meta", {}).setdefault(k, v)
    tokens_data = _deep_merge(tokens_data, raw.get("tokens", {}) or {})
    components.update(raw.get("components", {}) or {})
    tokens = Tokens(tokens_data)

    if "root" not in raw:
        raise SpecError("spec", "missing \"root\" (the ScreenGui node)")
    used = {}
    roots = _expand_components(raw["root"], components, "root", used)
    if not roots:
        raise SpecError("root", "root node was removed by an \"if\"")
    root = _build(roots[0], tokens, roots[0].get("name") or roots[0].get("class") or "root",
                  source.parent if source else None, problems)
    meta = raw.get("meta", {}) or {}
    _attach_runtime(root, meta, problems)
    return Spec(root=root, meta=meta, tokens=tokens_data, raw=raw, source=source,
                problems=problems, components_used=used)


def _attach_runtime(root: Node, meta: dict, problems: list):
    """Add the UIRuntime LocalScript when the tree uses autoscale / motion / opens / closes / toggles."""
    uses = [n for n in root.walk() if any(a in n.attrs for a in RUNTIME_ATTRS.values())]
    if not uses or root.cls != "ScreenGui":
        return
    names = {n.name for n in root.walk()}
    for n in uses:
        for a in ("Opens", "Closes", "Toggles"):
            target = n.attrs.get(a)
            if target and target not in names:
                problems.append(("error", n.path, "dangling-target",
                                 f"{a.lower()}: \"{target}\" but no instance in this ScreenGui has that name."))
    style = str(meta.get("motion", "")).lower()
    if style not in MOTION_STYLES:
        style = {"chunky": "bouncy", "soft": "snappy", "material": "snappy", "flat": "calm"}.get(
            str(meta.get("depth", "")).lower(), "snappy")
    root.attrs.setdefault("MotionStyle", style)
    if any(c.cls == "LocalScript" and c.name == "UIRuntime" for c in root.children):
        return
    src = RUNTIME_SCRIPT.read_text(encoding="utf-8") if RUNTIME_SCRIPT.exists() else "-- UIRuntime source missing"
    script = Node(cls="LocalScript", name="UIRuntime", path=f"{root.path}/UIRuntime", parent=root)
    script.props["Source"] = src
    script.explicit.add("Source")
    root.children.append(script)


# ---------------------------------------------------------------- effective values

def effective(node: Node, prop: str):
    """Value a property will have in Studio after export (explicit value, else our export default)."""
    if prop in node.props:
        return node.props[prop]
    return export_default(node, prop)


def export_default(node: Node, prop: str):
    """Defaults this tool writes when the author leaves a property out.

    They differ from Instance.new defaults in three places, on purpose:
    no 1px legacy border, no grey background unless a colour was given, no 'Label' text.
    """
    cls = node.cls
    if cls in GUI_OBJECTS:
        if prop == "BorderSizePixel":
            return 0
        if prop == "BackgroundTransparency":
            return 0.0 if "BackgroundColor3" in node.explicit else 1.0
        if prop == "BackgroundColor3":
            return (1.0, 1.0, 1.0)
        if prop == "Text" and cls in TEXT_CLASSES:
            return ""
        if prop == "TextSize" and cls in TEXT_CLASSES:
            return 14.0
        if prop == "AutoButtonColor" and cls in BUTTON_CLASSES:
            return False
    if cls == "ScreenGui":
        if prop == "ZIndexBehavior":
            return "Sibling"
        if prop == "ResetOnSpawn":
            return False
    info = CLASSES[cls]["props"].get(prop)
    if not info or info["default"] is None:
        return None
    return _parse_default(info["type"], info["default"])


def _parse_default(type_name: str, s: str):
    if type_name == "bool":
        return s == "true"
    if type_name == "int":
        return int(float(s))
    if type_name in ("float", "double"):
        return float(s)
    if type_name in ("string", "ProtectedString", "ContentId", "Content"):
        return s
    nums = _numbers_from_string(s)
    if type_name == "Color3":
        return tuple(nums[:3])
    if type_name == "UDim2":
        return tuple(nums[:4])
    if type_name == "UDim":
        return tuple(nums[:2])
    if type_name == "Vector2":
        return tuple(nums[:2])
    if type_name == "Vector3":
        return tuple(nums[:3])
    if type_name == "Rect":
        return tuple(nums[:4])
    if type_name == "ColorSequence":
        pts = [(nums[i], tuple(nums[i + 1 : i + 4])) for i in range(0, len(nums) - 4, 5)]
        return pts or [(0.0, (1, 1, 1)), (1.0, (1, 1, 1))]
    if type_name == "NumberSequence":
        pts = [(nums[i], nums[i + 1]) for i in range(0, len(nums) - 2, 3)]
        return pts or [(0.0, 0.0), (1.0, 0.0)]
    if type_name.startswith("Enum:"):
        return s
    return None
