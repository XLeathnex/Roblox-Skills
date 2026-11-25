#!/usr/bin/env python3
"""Regenerate skills/roblox-ui-design/scripts/rbxui/schema.json from a Roblox API dump.

    curl -sSfo Full-API-Dump.json \
      https://raw.githubusercontent.com/MaximumADHD/Roblox-Client-Tracker/roblox/Full-API-Dump.json
    python3 tools/gen_schema.py Full-API-Dump.json

The schema is what lets the linter say "TextLabel has no property 'TextStroke'"
instead of letting a hallucinated property reach Studio.
"""
import json
import sys
from pathlib import Path

CLASSES = [
    "ScreenGui", "SurfaceGui", "BillboardGui",
    "Frame", "CanvasGroup", "ScrollingFrame", "ViewportFrame", "VideoFrame",
    "TextLabel", "TextButton", "TextBox", "ImageLabel", "ImageButton",
    "UICorner", "UIStroke", "UIGradient", "UIShadow", "UIPadding", "UIScale",
    "UIListLayout", "UIGridLayout", "UIPageLayout", "UITableLayout", "UIFlexItem",
    "UIAspectRatioConstraint", "UISizeConstraint", "UITextSizeConstraint",
    "UIDragDetector", "Folder", "LocalScript", "ModuleScript", "Script",
]
# Defaults for members declared on abstract bases (the dump cannot instantiate those).
BASE_DEFAULTS = {
    "Active": "false", "AnchorPoint": "0, 0", "AutomaticSize": "None",
    "BackgroundColor3": "0.639216, 0.635294, 0.647059", "BackgroundTransparency": "0",
    "BorderColor3": "0.105882, 0.164706, 0.207843", "BorderMode": "Outline", "BorderSizePixel": "1",
    "ClipsDescendants": "false", "Interactable": "true", "LayoutOrder": "0",
    "Position": "{0, 0}, {0, 0}", "Rotation": "0", "Selectable": "false",
    "Size": "{0, 0}, {0, 0}", "SizeConstraint": "RelativeXY", "Visible": "true", "ZIndex": "1",
    "AutoLocalize": "true", "SelectionGroup": "false", "SelectionOrder": "0",
    "AutoButtonColor": "true", "Modal": "false", "Selected": "false",
    "Enabled": "true", "ResetOnSpawn": "true", "ZIndexBehavior": "Global",
    "FillDirection": "Vertical", "HorizontalAlignment": "Left", "SortOrder": "LayoutOrder",
    "VerticalAlignment": "Top",
}
SKIP_TAGS = {"Hidden", "ReadOnly", "NotScriptable", "Deprecated"}
SKIP_TYPES = {"RolloutState", "HapticEffect", "LocalizationTable", "SelectionBehavior", "FrameStyle",
              "ButtonStyle", "CFrame", "Camera", "TextDirection", "InputSink", "GuiState"}


def main():
    dump = json.load(open(sys.argv[1]))
    classes = {c["Name"]: c for c in dump["Classes"]}
    enums = {e["Name"]: e for e in dump["Enums"]}
    out = {"version": dump.get("Version"), "classes": {}, "enums": {}}
    used_enums = {"FontWeight", "FontStyle"}
    for name in CLASSES:
        if name not in classes:
            print("missing class", name)
            continue
        props = {}
        chain, c = [], classes[name]
        while c and c["Name"] != "Instance":
            chain.append(c)
            c = classes.get(c["Superclass"])
        for c in reversed(chain):
            for m in c["Members"]:
                if m["MemberType"] != "Property":
                    continue
                tags = {t for t in (m.get("Tags") or []) if isinstance(t, str)}
                if tags & SKIP_TAGS:
                    continue
                sec = m.get("Security", {})
                if isinstance(sec, dict) and sec.get("Write", "None") != "None":
                    continue
                vt = m["ValueType"]
                tname = vt["Name"]
                if tname in SKIP_TYPES:
                    continue
                if vt["Category"] == "Enum":
                    t = "Enum:" + tname
                    used_enums.add(tname)
                elif vt["Category"] == "Class":
                    t = "Ref"
                else:
                    t = tname
                default = m.get("Default")
                if default in (None, "__api_dump_class_not_creatable__"):
                    default = BASE_DEFAULTS.get(m["Name"])
                if default == "__api_dump_no_string_value__":
                    default = None
                props[m["Name"]] = {"type": t, "default": default,
                                    "save": bool(m["Serialization"]["CanSave"])}
        out["classes"][name] = {"superclass": classes[name]["Superclass"], "props": props}
    for e in sorted(used_enums):
        out["enums"][e] = {i["Name"]: i["Value"] for i in enums[e]["Items"]}
    dest = Path(__file__).resolve().parent.parent / "skills/roblox-ui-design/scripts/rbxui/schema.json"
    dest.write_text(json.dumps(out, indent=1, sort_keys=True))
    print("wrote", dest, "classes:", len(out["classes"]), "enums:", len(out["enums"]))


if __name__ == "__main__":
    main()
