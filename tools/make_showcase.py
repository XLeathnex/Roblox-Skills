#!/usr/bin/env python3
"""Collect showcase/<model>/<nn-style>/ui.json runs into previews, contact sheets and showcase/README.md.

    python3 tools/make_showcase.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "skills/roblox-ui-design/scripts/rbxui"))

import lint as linter  # noqa: E402
import render  # noqa: E402
import spec as S  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

import fonts  # noqa: E402

SHOW = ROOT / "showcase"
MODELS = [("haiku", "Haiku 5.5 (high)"), ("opus", "Opus 5.5 (high)")]
PROMPTS = {
    "01-simulator": "make the egg shop for my pet simulator Bubble Reef (its underwater, you hatch sea creature pets). 6 eggs, coins and pearls are the currencies, and show my balance",
    "02-tycoon": "upgrade menu for my pizza restaurant tycoon called Slice Empire. a list of upgrades (better oven, delivery scooter, more tables, hire a chef) each with a level and a price, plus the cash display on the hud with income per second",
    "03-horror": "pause menu with settings for my horror game The Lighthouse Keeper (1920s lighthouse in a storm, youre alone). resume, settings with volume brightness and mouse sensitivity, and quit to menu",
    "04-story": "dialogue box with 3 choices for my story game Last Train to Aurora (noir mystery on a 1940s night train). also the objective text at the top of the screen",
    "05-anime": "summon screen for my anime tower defense Spirit Blade Defenders. featured mythic unit banner, 1x and 10x summon buttons, my gem count, a pity counter, and a row showing the possible units with their rarities",
    "06-shooter": "in match hud for my fps Neon Strike (futuristic arena, red vs blue teams). health and armor, ammo, team scores with the timer, a kill feed and a minimap",
    "07-roleplay": "the phone menu for my roleplay game Maple Bay (cozy seaside town). home screen with apps for jobs, houses, vehicles, avatar, friends and settings, and my bank balance. plus the little hud button that opens it",
    "08-obby": "hud for my obby Tower of Sweets (candy themed tower). stage counter, timer, coins, a skip stage button, and the stage complete banner that pops up",
    "09-fantasy": "inventory and crafting screen for my viking survival game Frostheim. a 5x4 item grid with quantities and rarity, a crafting list on the right with a craft button, and health hunger and warmth bars",
    "10-scifi": "race hud for my sci fi racing game Orbital Drift. speed, position like 3/8, lap 2/3, lap time, a boost meter, and the countdown GO banner",
}


def one(folder: Path):
    spec_path = folder / "ui.json"
    if not spec_path.exists():
        return None
    try:
        spec = S.load(spec_path)
    except Exception as e:
        return {"error": str(e)}
    rep = linter.lint(spec)
    info = {"errors": rep.count("error"), "warnings": rep.count("warn"),
            "instances": sum(1 for _ in spec.root.walk()), "spec_bytes": spec_path.stat().st_size,
            "direction": spec.meta.get("direction", ""), "depth": spec.meta.get("depth", ""),
            "images": len(list((folder / "assets").glob("*.png"))) if (folder / "assets").exists() else 0}
    import layout as L
    # Show the first startHidden panel open, unless it would cover the always-visible UI (then show the start state).
    hidden = [n for n in spec.root.walk() if n.attrs.get("StartHidden")]
    show = None
    if hidden:
        L.layout_tree(spec.root, "pc", 1.0)
        show = hidden[0].name
        hx, hy, hw, hh = getattr(hidden[0], "rect", (0, 0, 0, 0))
        for n in spec.root.children:
            if n is hidden[0] or n.cls not in S.GUI_OBJECTS or n.attrs.get("StartHidden") or not hasattr(n, "rect"):
                continue
            x, y, w, h = n.rect
            if w * h > 1920 * 1080 * 0.6 or not linter._has_ink(n):
                continue
            ix, iy = min(hx + hw, x + w) - max(hx, x), min(hy + hh, y + h) - max(hy, y)
            if ix > 0 and iy > 0 and ix * iy > 0.3 * min(hw * hh, w * h):
                show = None
    L.HIDE_START_HIDDEN.update({"on": bool(hidden), "except": show})
    pc, _ = render.render(spec, "pc", 1.0)
    pc = pc.resize((1280, 720), Image.LANCZOS)
    pc.save(folder / "preview.png", optimize=True)
    phone, _ = render.render(spec, "phone", 1.0)
    phone.save(folder / "preview.phone.png", optimize=True)
    L.HIDE_START_HIDDEN.update({"on": False, "except": None})
    info["pc"] = pc
    return info


def label(draw, xy, text, size=22):
    f = fonts.get({"family": "Montserrat", "weight": "Bold"}, size)
    w = f.getlength(text)
    draw.rectangle([xy[0], xy[1], xy[0] + w + 16, xy[1] + size + 8], fill=(12, 14, 18))
    draw.text((xy[0] + 8, xy[1] + 3), text, font=f, fill=(255, 255, 255))


def main():
    rows, results = [], {}
    for style in PROMPTS:
        results[style] = {m: one(SHOW / m / style) for m, _ in MODELS}
    # contact sheets: 5 styles per sheet, Haiku left / Opus right
    styles = list(PROMPTS)
    tw, th = 960, 540
    for part in range(2):
        chunk = styles[part * 5:(part + 1) * 5]
        sheet = Image.new("RGB", (tw * 2, th * len(chunk)), (20, 22, 26))
        d = ImageDraw.Draw(sheet)
        for r, style in enumerate(chunk):
            for c, (m, mlabel) in enumerate(MODELS):
                info = results[style][m]
                if info and "pc" in info:
                    sheet.paste(info["pc"].resize((tw, th), Image.LANCZOS), (c * tw, r * th))
                label(d, (c * tw + 10, r * th + 10), f"{style[3:]} - {mlabel}")
        sheet.save(SHOW / f"contact-{part + 1}.png", optimize=True)
    out = ["# Showcase", "",
           "The same ten requests, each given to a model that had only the `roblox-ui-design` skill. No hand edits.",
           "Images are the skill's own preview renderer (PC 1920x1080 over a stand-in game world), not Roblox Studio screenshots.",
           "Each folder holds the spec the model wrote (`ui.json`), its images, and the built instances (`out/*.rbxmx`: right-click StarterGui > Insert from File).", ""]
    out += ["| Request | " + " | ".join(l for _, l in MODELS) + " |", "|---|" + "---|" * len(MODELS)]
    for style, prompt in PROMPTS.items():
        cells = []
        for m, _ in MODELS:
            info = results[style][m]
            if not info:
                cells.append("(no result)")
            elif "error" in info:
                cells.append(f"(spec error: {info['error'][:80]})")
            else:
                cells.append(f"![{m} {style}]({m}/{style}/preview.png)<br>{info['instances']} instances from a "
                             f"{info['spec_bytes'] / 1000:.1f} kB spec, {info['images']} images, "
                             f"lint {info['errors']} errors / {info['warnings']} warnings<br><sub>{info['direction']}</sub>")
        out.append(f"| **{style[3:]}**<br><sub>\"{prompt}\"</sub> | " + " | ".join(cells) + " |")
    (SHOW / "README.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    summary = {s: {m: ({k: v for k, v in i.items() if k != "pc"} if i else None) for m, i in r.items()} for s, r in results.items()}
    (SHOW / "results.json").write_text(json.dumps(summary, indent=1) + "\n")
    done = sum(1 for r in results.values() for i in r.values() if i and "pc" in i)
    print(f"{done}/20 rendered. Wrote showcase/README.md, contact-1.png, contact-2.png")


if __name__ == "__main__":
    main()
