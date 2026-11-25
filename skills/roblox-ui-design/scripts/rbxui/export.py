"""Turn a spec into real Roblox instances.

Three outputs, all describing the same instance tree:

  .luau        a one-time builder to run in Studio's command bar or through an
               MCP `execute_luau` call (Edit datamodel). It creates the instances
               under StarterGui inside one undo step. It is NOT a runtime script.
  .rbxmx       a model file: right-click StarterGui > Insert from File.
  .model.json  a Rojo model for projects that sync from disk.
"""
from __future__ import annotations

import base64
import json
import struct
from xml.sax.saxutils import escape

from spec import CLASSES, ENUMS, GUI_OBJECTS, Node, Spec, export_default

FORCED = {
    # properties always written, because Instance.new defaults are not what a designer expects
    "gui": ["BorderSizePixel", "BackgroundTransparency"],
    "text": ["Text", "TextSize"],
    "button": ["AutoButtonColor"],
    "ScreenGui": ["ZIndexBehavior", "ResetOnSpawn"],
}
WEIGHT_NUM = ENUMS["FontWeight"]


def export_props(node: Node) -> dict:
    """Ordered {property: typed value} to write for this node."""
    out = {}
    forced = []
    if node.cls in GUI_OBJECTS:
        forced += FORCED["gui"]
        if node.cls in ("TextLabel", "TextButton", "TextBox"):
            forced += FORCED["text"]
        if node.cls in ("TextButton", "ImageButton"):
            forced += FORCED["button"]
    forced += FORCED.get(node.cls, [])
    for p in forced:
        if p not in node.props:
            v = export_default(node, p)
            if v is not None:
                out[p] = v
    if node.cls == "ScreenGui" and "IgnoreGuiInset" in node.props and "ScreenInsets" not in node.props:
        out["ScreenInsets"] = "DeviceSafeInsets" if node.props["IgnoreGuiInset"] else "CoreUISafeInsets"
    for p, v in node.props.items():
        if node.cls == "ScreenGui" and p == "IgnoreGuiInset":
            continue
        out[p] = v
    return out


def prop_type(node: Node, prop: str) -> str:
    return CLASSES[node.cls]["props"][prop]["type"]


class Assets:
    """Resolves 'asset:name' image references through assets.json ({name: {"file":..., "id": 123}})."""

    def __init__(self, spec: Spec):
        self.map = {}
        self.pending = set()
        if spec.source:
            for d in (spec.source.parent / "assets", spec.source.parent):
                p = d / "assets.json"
                if p.exists():
                    try:
                        for name, info in json.loads(p.read_text()).items():
                            if isinstance(info, dict) and info.get("id"):
                                self.map[name] = f"rbxassetid://{info['id']}"
                    except Exception:
                        pass

    def resolve(self, ref: str) -> str:
        if isinstance(ref, str) and ref.startswith("asset:"):
            name = ref[6:]
            if name in self.map:
                return self.map[name]
            self.pending.add(name)
            return ""
        return ref


def font_family_url(family: str) -> str:
    if family.startswith("rbxasset"):
        return family
    return f"rbxasset://fonts/families/{family}.json"


# ------------------------------------------------------------------ Luau

def _n(v: float) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if abs(v - round(v)) < 1e-9:
        return str(int(round(v)))
    return f"{v:.4f}".rstrip("0").rstrip(".")


def _rgb(c) -> str:
    return "%d,%d,%d" % tuple(max(0, min(255, round(x * 255))) for x in c)


def _lua_str(s: str) -> str:
    if "\n" in s or len(s) > 200:
        eq = ""
        while f"]{eq}]" in s:
            eq += "="
        return f"[{eq}[\n{s}]{eq}]"
    return json.dumps(s, ensure_ascii=False)


def luau_value(v, t: str, assets: Assets) -> str:
    """Compact Luau literal. Uses the helper aliases declared in the builder header (C U D V F S Q E)."""
    if t == "bool":
        return "true" if v else "false"
    if t in ("int", "float", "double"):
        return _n(v)
    if t in ("string", "ProtectedString"):
        return _lua_str(v)
    if t == "Color3":
        return f"C({_rgb(v)})"
    if t == "UDim2":
        return f"U({_n(v[0])},{_n(v[1])},{_n(v[2])},{_n(v[3])})"
    if t == "UDim":
        return f"D({_n(v[0])},{_n(v[1])})"
    if t == "Vector2":
        return f"V({_n(v[0])},{_n(v[1])})"
    if t == "Vector3":
        return f"Vector3.new({_n(v[0])},{_n(v[1])},{_n(v[2])})"
    if t == "Rect":
        return f"Rect.new({_n(v[0])},{_n(v[1])},{_n(v[2])},{_n(v[3])})"
    if t == "ColorSequence":
        return "S(" + ", ".join(f"{_n(tt)},{_rgb(c)}" for tt, c in v) + ")"
    if t == "NumberSequence":
        return "Q(" + ", ".join(f"{_n(tt)},{_n(val)}" for tt, val in v) + ")"
    if t == "Font":
        fam = v["family"]
        italic = ",true" if v["style"] == "Italic" else ""
        if fam.startswith("rbxasset"):
            return f"Font.new({json.dumps(fam)},E.FontWeight.{v['weight']},E.FontStyle.{v['style']})"
        return f"F({json.dumps(fam)},{json.dumps(v['weight'])}{italic})"
    if t in ("ContentId", "Content"):
        return json.dumps(assets.resolve(v))
    if t.startswith("Enum:"):
        return f"E.{t[5:]}.{v}"
    raise ValueError(f"cannot export type {t}")


LUAU_HEADER = """--!nocheck
-- {name}: one-time UI builder (roblox-ui-design skill). It creates REAL instances under {where}.
-- Run it once while editing in Studio: command bar, or an MCP execute_luau call on the Edit datamodel.
-- Do not ship this file in the game. Ctrl+Z undoes the build.
local H = game:GetService("ChangeHistoryService")
local rec = H:TryBeginRecording("Build {name} UI")
local E, C, U, D, V = Enum, Color3.fromRGB, UDim2.new, UDim.new, Vector2.new
local function F(f, w, i) return Font.new("rbxasset://fonts/families/" .. f .. ".json", E.FontWeight[w], i and E.FontStyle.Italic or E.FontStyle.Normal) end
local function S(...) local a, k = {{...}}, {{}} for i = 1, #a, 4 do k[#k + 1] = ColorSequenceKeypoint.new(a[i], C(a[i + 1], a[i + 2], a[i + 3])) end return ColorSequence.new(k) end
local function Q(...) local a, k = {{...}}, {{}} for i = 1, #a, 2 do k[#k + 1] = NumberSequenceKeypoint.new(a[i], a[i + 1]) end return NumberSequence.new(k) end
local n = {{}}
local function N(class, parent, props) local o = Instance.new(class) for k, v in props do o[k] = v end o.Parent = n[parent] n[#n + 1] = o return o end
"""

LUAU_FOOTER = """local parent = {parent}
local old = parent:FindFirstChild({qname})
if old then old:Destroy() end -- replaced by this build; Ctrl+Z restores it
n[1].Parent = parent
game:GetService("Selection"):Set({{ n[1] }})
if rec then H:FinishRecording(rec, E.FinishRecordingOperation.Commit) end
print("Built {name}: " .. #n .. " instances in " .. parent:GetFullName())
"""


def to_luau(spec: Spec, parent_expr: str = 'game:GetService("StarterGui")') -> tuple:
    assets = Assets(spec)
    root = spec.root
    lines = [LUAU_HEADER.format(name=root.name, where=parent_expr).rstrip("\n")]
    counter = [0]

    def emit(node: Node, parent_idx: int):
        counter[0] += 1
        idx = counter[0]
        parts = []
        if node.name != node.cls:
            parts.append(f"Name={_lua_str(node.name)}")
        attrs = dict(node.attrs)
        for p, v in export_props(node).items():
            t = prop_type(node, p)
            if t == "Ref":
                continue
            if p == "Image" and isinstance(v, str) and v.startswith("asset:") and not assets.resolve(v):
                attrs["PendingAsset"] = v[6:]
            parts.append(f"{p}={luau_value(v, t, assets)}")
        line = f"N({json.dumps(node.cls)},{parent_idx},{{{','.join(parts)}}})"
        extra = []
        for tag in node.tags:
            extra.append(f":AddTag({json.dumps(tag)})")
        if extra or attrs:
            line = "do local o=" + line
            for tag in node.tags:
                line += f" o:AddTag({json.dumps(tag)})"
            for k, v in attrs.items():
                lit = ("true" if v else "false") if isinstance(v, bool) else (
                    _n(v) if isinstance(v, (int, float)) else _lua_str(str(v)))
                line += f" o:SetAttribute({json.dumps(k)},{lit})"
            line += " end"
        lines.append(line)
        for c in node.children:
            emit(c, idx)

    emit(root, 0)
    lines.append(LUAU_FOOTER.format(parent=parent_expr, qname=_lua_str(root.name), name=root.name))
    return "\n".join(lines), assets


# ------------------------------------------------------------------ rbxmx

def _attributes_blob(attrs: dict) -> bytes:
    out = struct.pack("<I", len(attrs))
    for k, v in attrs.items():
        kb = k.encode("utf-8")
        out += struct.pack("<I", len(kb)) + kb
        if isinstance(v, bool):
            out += b"\x03" + (b"\x01" if v else b"\x00")
        elif isinstance(v, (int, float)):
            out += b"\x06" + struct.pack("<d", float(v))
        else:
            sb = str(v).encode("utf-8")
            out += b"\x02" + struct.pack("<I", len(sb)) + sb
    return out


def _f(v: float) -> str:
    return repr(float(v)) if abs(v - round(v)) > 1e-9 else str(int(round(v)))


def xml_value(name: str, v, t: str, assets: Assets) -> str:
    q = escape(name, {'"': "&quot;"})
    if t == "bool":
        return f'<bool name="{q}">{"true" if v else "false"}</bool>'
    if t == "int":
        return f'<int name="{q}">{int(v)}</int>'
    if t == "float":
        return f'<float name="{q}">{_f(v)}</float>'
    if t == "double":
        return f'<double name="{q}">{_f(v)}</double>'
    if t == "string":
        return f'<string name="{q}">{escape(v)}</string>'
    if t == "ProtectedString":
        return f'<ProtectedString name="{q}"><![CDATA[{v.replace("]]>", "]]]]><![CDATA[>")}]]></ProtectedString>'
    if t == "Color3":
        return f'<Color3 name="{q}"><R>{_f(v[0])}</R><G>{_f(v[1])}</G><B>{_f(v[2])}</B></Color3>'
    if t == "UDim2":
        return f'<UDim2 name="{q}"><XS>{_f(v[0])}</XS><XO>{int(round(v[1]))}</XO><YS>{_f(v[2])}</YS><YO>{int(round(v[3]))}</YO></UDim2>'
    if t == "UDim":
        return f'<UDim name="{q}"><S>{_f(v[0])}</S><O>{int(round(v[1]))}</O></UDim>'
    if t == "Vector2":
        return f'<Vector2 name="{q}"><X>{_f(v[0])}</X><Y>{_f(v[1])}</Y></Vector2>'
    if t == "Vector3":
        return f'<Vector3 name="{q}"><X>{_f(v[0])}</X><Y>{_f(v[1])}</Y><Z>{_f(v[2])}</Z></Vector3>'
    if t == "Rect":
        return (f'<Rect2D name="{q}"><min><X>{_f(v[0])}</X><Y>{_f(v[1])}</Y></min>'
                f'<max><X>{_f(v[2])}</X><Y>{_f(v[3])}</Y></max></Rect2D>')
    if t == "ColorSequence":
        body = "".join(f"{_f(tt)} {_f(c[0])} {_f(c[1])} {_f(c[2])} 0 " for tt, c in v)
        return f'<ColorSequence name="{q}">{body}</ColorSequence>'
    if t == "NumberSequence":
        body = "".join(f"{_f(tt)} {_f(val)} 0 " for tt, val in v)
        return f'<NumberSequence name="{q}">{body}</NumberSequence>'
    if t == "Font":
        return (f'<Font name="{q}"><Family><url>{escape(font_family_url(v["family"]))}</url></Family>'
                f'<Weight>{WEIGHT_NUM[v["weight"]]}</Weight><Style>{v["style"]}</Style></Font>')
    if t in ("ContentId", "Content"):
        return f'<Content name="{q}"><url>{escape(assets.resolve(v))}</url></Content>'
    if t.startswith("Enum:"):
        return f'<token name="{q}">{ENUMS[t[5:]][v]}</token>'
    raise ValueError(f"cannot export type {t}")


def to_rbxmx(spec: Spec) -> tuple:
    assets = Assets(spec)
    out = ['<roblox version="4">']
    counter = [0]

    def emit(node: Node, depth: int):
        pad = "  " * depth
        ref = f"RBX{counter[0]:08X}"
        counter[0] += 1
        out.append(f'{pad}<Item class="{node.cls}" referent="{ref}">')
        out.append(f"{pad}  <Properties>")
        out.append(f'{pad}    <string name="Name">{escape(node.name)}</string>')
        attrs = dict(node.attrs)
        for p, v in export_props(node).items():
            t = prop_type(node, p)
            if t == "Ref":
                continue
            if p == "Image" and isinstance(v, str) and v.startswith("asset:") and not assets.resolve(v):
                attrs["PendingAsset"] = v[6:]
            out.append(f"{pad}    {xml_value(p, v, t, assets)}")
        if attrs:
            blob = base64.b64encode(_attributes_blob(attrs)).decode()
            out.append(f'{pad}    <BinaryString name="AttributesSerialize">{blob}</BinaryString>')
        if node.tags:
            blob = base64.b64encode("\0".join(node.tags).encode("utf-8")).decode()
            out.append(f'{pad}    <BinaryString name="Tags">{blob}</BinaryString>')
        out.append(f"{pad}  </Properties>")
        for c in node.children:
            emit(c, depth + 1)
        out.append(f"{pad}</Item>")

    emit(spec.root, 1)
    out.append("</roblox>")
    return "\n".join(out) + "\n", assets


# ------------------------------------------------------------------ Rojo .model.json

def rojo_value(v, t: str, assets: Assets):
    if t in ("bool", "int", "float", "double", "string", "ProtectedString"):
        return v
    if t == "Color3":
        return [round(x, 6) for x in v]
    if t == "UDim2":
        return {"UDim2": [[v[0], v[1]], [v[2], v[3]]]}
    if t == "UDim":
        return {"UDim": [v[0], v[1]]}
    if t == "Vector2":
        return {"Vector2": [v[0], v[1]]}
    if t == "Vector3":
        return {"Vector3": list(v)}
    if t == "Rect":
        return {"Rect": [[v[0], v[1]], [v[2], v[3]]]}
    if t == "ColorSequence":
        return {"ColorSequence": {"keypoints": [{"time": tt, "color": [round(x, 6) for x in c]} for tt, c in v]}}
    if t == "NumberSequence":
        return {"NumberSequence": {"keypoints": [{"time": tt, "value": val, "envelope": 0} for tt, val in v]}}
    if t == "Font":
        return {"Font": {"family": font_family_url(v["family"]), "weight": v["weight"], "style": v["style"]}}
    if t in ("ContentId", "Content"):
        return assets.resolve(v)
    if t.startswith("Enum:"):
        return v
    raise ValueError(f"cannot export type {t}")


def to_rojo(spec: Spec) -> tuple:
    assets = Assets(spec)

    def emit(node: Node, top: bool):
        d = {} if top else {"Name": node.name}
        d["ClassName"] = node.cls
        props = {}
        attrs = dict(node.attrs)
        for p, v in export_props(node).items():
            t = prop_type(node, p)
            if t == "Ref":
                continue
            if p == "Image" and isinstance(v, str) and v.startswith("asset:") and not assets.resolve(v):
                attrs["PendingAsset"] = v[6:]
            props[p] = rojo_value(v, t, assets)
        if node.tags:
            props["Tags"] = list(node.tags)
        if attrs:
            props["Attributes"] = attrs
        if props:
            d["Properties"] = props
        if node.children:
            d["Children"] = [emit(c, False) for c in node.children]
        return d

    return json.dumps(emit(spec.root, True), indent=2, ensure_ascii=False) + "\n", assets


def tree_text(node: Node, depth=0, limit=400) -> str:
    lines = []

    def walk(n, d):
        if len(lines) >= limit:
            return
        mods = [c.cls for c in n.children if c.cls not in GUI_OBJECTS and c.cls.startswith("UI")]
        suffix = f"  [{', '.join(mods)}]" if mods else ""
        lines.append(f"{'  ' * d}{n.name} ({n.cls}){suffix}")
        for c in n.children:
            if c.cls in GUI_OBJECTS or not c.cls.startswith("UI"):
                walk(c, d + 1)

    walk(node, depth)
    return "\n".join(lines)
