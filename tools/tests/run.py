#!/usr/bin/env python3
"""Smoke tests for the roblox-ui-design tooling.   python3 tools/tests/run.py"""
import json
import subprocess
import sys
import tempfile
import xml.dom.minidom
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent.parent / "skills/roblox-ui-design"
sys.path.insert(0, str(SKILL / "scripts/rbxui"))

import export  # noqa: E402
import lint as linter  # noqa: E402
import spec as S  # noqa: E402

failures = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  ({detail})" if detail and not cond else ""))
    if not cond:
        failures.append(name)


def rules(path):
    rep = linter.lint(S.load(path))
    return rep, {i[1] for i in rep.items}


# 1. the slop fixture must trip the craft rules
rep, got = rules(HERE / "fixtures/slop_pills.json")
for rule in ("pill-everything", "fake-gloss", "hue-rainbow", "emoji-icon", "gradient-hue-jump", "diagonal-gradients",
             "one-font", "off-screen", "legacy-font-prop"):
    check(f"slop fixture triggers {rule}", rule in got, f"got {sorted(got)}")
check("slop fixture has errors", rep.count("error") > 0)

# 2. good fixtures lint without errors and export to well-formed files
for name in ("good_chunky_shop.json", "good_flat_menu.json"):
    spec = S.load(HERE / "fixtures" / name)
    rep = linter.lint(spec)
    check(f"{name}: no lint errors", rep.count("error") == 0, rep.format())
    xml.dom.minidom.parseString(export.to_rbxmx(spec)[0])
    json.loads(export.to_rojo(spec)[0])
    luau = export.to_luau(spec)[0]
    check(f"{name}: luau builder balanced", luau.count("{") == luau.count("}") and luau.count("(") == luau.count(")"))
    check(f"{name}: runtime script attached", any(n.name == "UIRuntime" for n in spec.root.walk()))

# 3. hallucinated properties and classes are reported, not crashed on
bad = {"meta": {"genre": "x", "depth": "flat", "direction": "a long enough direction sentence for the test"},
       "root": {"class": "ScreenGui", "children": [
           {"class": "Frame", "CornerRadius": 8, "BackgroundColor": "#FF0000", "Opacity": 0.5},
           {"class": "TextLabel", "Text": "hi", "TextStroke": 2, "FontFace": "NotAFont"}]}}
spec = S.from_dict(bad)
rep = linter.lint(spec)
msgs = " ".join(i[3] for i in rep.items)
check("unknown properties explained", "UICorner" in msgs and "BackgroundColor3" in msgs and "transparency" in msgs.lower())
check("unknown font reported", any(i[1] == "unknown-font" for i in rep.items))

# 4. preview renders (needs Pillow + numpy)
try:
    import render
    img, _ = render.render(S.load(HERE / "fixtures/good_chunky_shop.json"), "phone")
    check("preview renders", img.size == (844, 390))
except ImportError:
    print("skip preview (Pillow/numpy missing)")

# 5. CLI end to end
with tempfile.TemporaryDirectory() as tmp:
    r = subprocess.run([sys.executable, str(SKILL / "scripts/rbxui"), "check", str(HERE / "fixtures/good_flat_menu.json"),
                        "--image", f"{tmp}/c.png", "--build", tmp], capture_output=True, text=True)
    check("cli check --build", r.returncode == 0 and Path(tmp, "SettingsGui.rbxmx").exists(), r.stdout + r.stderr)

print("\n" + ("all passed" if not failures else f"{len(failures)} failed"))
sys.exit(1 if failures else 0)
