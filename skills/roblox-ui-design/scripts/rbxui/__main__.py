#!/usr/bin/env python3
"""rbxui - check, preview and build Roblox UI as real instances from a compact JSON spec.

    python3 scripts/rbxui check ui.json              lint + one review image (PC, phone, close-up)
    python3 scripts/rbxui check ui.json --build out  ...and export when there are no errors
    python3 scripts/rbxui check ui.json --no-image   lint only (cheapest)
    python3 scripts/rbxui build ui.json --out out    .build.luau + .rbxmx + .model.json
    python3 scripts/rbxui storyboard ui.json         frames of the enter/leave animation sequence
    python3 scripts/rbxui tree  ui.json              instance hierarchy
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import export  # noqa: E402
import fonts  # noqa: E402
import layout as L  # noqa: E402
import lint as linter  # noqa: E402
import spec as S  # noqa: E402


def _load(path):
    try:
        return S.load(path)
    except S.SpecError as e:
        print(f"ERROR [spec] {e}")
        sys.exit(2)
    except FileNotFoundError:
        print(f"ERROR: no such file: {path}")
        sys.exit(2)


def _render_mod():
    try:
        import render
        return render
    except ImportError as e:
        print(f"note  no preview: Pillow/numpy missing ({e}). `pip install pillow numpy` to enable it.")
        return None


def _pick_zoom(spec, render, names):
    targets = []
    for name in names or []:
        targets += render.find_nodes(spec.root, name)[:1]
    if targets:
        return targets
    buttons = [n for n in spec.root.walk() if n.cls in S.BUTTON_CLASSES and getattr(n, "rect", (0, 0, 0, 0))[2] > 0]
    buttons.sort(key=lambda n: -(n.rect[2] * n.rect[3]))
    if buttons:
        return buttons[:1]
    # no buttons (a pure HUD): show the busiest small group instead
    vw = spec.root.rect[2] if hasattr(spec.root, "rect") else 1920
    groups = [n for n in spec.root.walk() if n.cls in S.GUI_OBJECTS and getattr(n, "rect", (0, 0, 0, 0))[2] > 40
              and n.rect[2] < vw * 0.45 and len(n.children) >= 3]
    groups.sort(key=lambda n: -sum(1 for _ in n.walk()))
    return groups[:1]


def review_image(spec, out: Path, zoom_names=None, backdrop=None):
    """One composite: PC render on top, phone render and a 3x close-up below. ~1280x1110."""
    render = _render_mod()
    if render is None:
        return None
    from PIL import Image, ImageDraw

    # Panels marked startHidden are closed when the game starts. PC shows that start state (unless nothing
    # else exists); the phone view opens the first such panel so both states get looked at.
    hidden = [n.name for n in spec.root.walk() if n.attrs.get("StartHidden")]
    always = any(n.cls in S.GUI_OBJECTS and not n.attrs.get("StartHidden") for n in spec.root.children)
    pc_open = None if (hidden and always) else (hidden[0] if hidden else None)
    phone_open = hidden[0] if hidden else None
    L.HIDE_START_HIDDEN.update({"on": bool(hidden), "except": pc_open})
    pc, r = render.render(spec, "pc", 1.0, backdrop)
    missing = set(r.missing_assets)
    L.HIDE_START_HIDDEN.update({"on": bool(hidden), "except": phone_open})
    phone, r2 = render.render(spec, "phone", 1.0, backdrop)
    big, r3 = render.render(spec, "pc", 3.0, backdrop, chrome=False)
    targets = _pick_zoom(spec, render, zoom_names)
    L.HIDE_START_HIDDEN.update({"on": False, "except": None})
    pc_label = "PC 1920x1080" + (" (start state)" if hidden and pc_open is None else (f" ({pc_open} open)" if pc_open else ""))
    phone_label = "phone 844x390" + (f" ({phone_open} open)" if phone_open else "")
    W = 1280
    top = pc.resize((W, 720), Image.LANCZOS)
    sheet = Image.new("RGB", (W, 720 + 390), (22, 24, 28))
    sheet.paste(top, (0, 0))
    sheet.paste(phone, (0, 720))
    zw, zh = W - 844, 390
    if targets:
        crop = render.crop_node(big, targets[0], 40)
        crop.thumbnail((zw - 12, zh - 12), Image.LANCZOS)
        sheet.paste(crop, (844 + (zw - crop.width) // 2, 720 + (zh - crop.height) // 2))
    d = ImageDraw.Draw(sheet)
    for xy, text in (((8, 694), pc_label), ((8, 1084), phone_label),
                     ((852, 1084), f"close-up: {targets[0].name}" if targets else "")):
        if text:
            d.rectangle([xy[0] - 4, xy[1] - 2, xy[0] + 8 * len(text), xy[1] + 14], fill=(0, 0, 0))
            d.text(xy, text, fill=(255, 255, 255))
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    return missing


def cmd_check(args):
    spec = _load(args.spec)
    rep = linter.lint(spec)
    print(rep.format(args.max))
    if not args.no_image:
        out = Path(args.image or Path(args.spec).with_suffix(".check.png"))
        missing = review_image(spec, out, args.zoom, args.backdrop)
        if missing is not None:
            print(f"review image: {out}  (PC, phone with thumbstick/jump/top bar, 3x close-up)")
            if missing:
                print("  no local file for: " + ", ".join(sorted(missing)) + " (drawn as IMG placeholders)")
            if fonts.substituted:
                print("  look-alike preview fonts for: " + ", ".join(sorted(fonts.substituted)))
    if args.build:
        if rep.count("error"):
            print("not built: fix the errors first.")
        else:
            _build(spec, Path(args.build), args.parent)
    return 1 if rep.count("error") else 0


def _build(spec, out: Path, parent: str):
    out.mkdir(parents=True, exist_ok=True)
    name = spec.root.name
    luau, assets = export.to_luau(spec, parent)
    (out / f"{name}.build.luau").write_text(luau, encoding="utf-8")
    (out / f"{name}.rbxmx").write_text(export.to_rbxmx(spec)[0], encoding="utf-8")
    (out / f"{name}.model.json").write_text(export.to_rojo(spec)[0], encoding="utf-8")
    count = sum(1 for _ in spec.root.walk())
    print(f"built {name}: {count} instances -> {out}/{name}.build.luau | .rbxmx | .model.json")
    if assets.pending:
        print("  images to upload, then record ids in assets.json and rebuild: " + ", ".join(sorted(assets.pending)))


def cmd_build(args):
    spec = _load(args.spec)
    rep = linter.lint(spec)
    if rep.count("error") and not args.force:
        print(rep.format(args.max))
        print("not built: fix the errors first (or --force).")
        return 1
    _build(spec, Path(args.out or (Path(args.spec).parent / "build")), args.parent)
    if rep.count("warn"):
        print(f"  {rep.count('warn')} lint warnings remain.")
    return 0


def cmd_preview(args):
    render = _render_mod()
    if render is None:
        return 3
    spec = _load(args.spec)
    if args.device not in L.DEVICES:
        print(f"unknown device {args.device!r}; choose from {', '.join(L.DEVICES)}")
        return 2
    img, r = render.render(spec, args.device, args.scale, args.backdrop, not args.no_chrome)
    out = Path(args.out or Path(args.spec).with_suffix(f".{args.device}.png"))
    if args.zoom:
        hits = render.find_nodes(spec.root, args.zoom)
        if not hits:
            print(f"no node named {args.zoom!r} on screen")
            return 2
        img = render.crop_node(img, hits[0], int(28 * args.scale))
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    print(f"wrote {out} ({img.width}x{img.height})")
    return 0


def cmd_storyboard(args):
    """Frames of the entrance sequence, so choreography can be judged without Studio."""
    render = _render_mod()
    if render is None:
        return 3
    from PIL import Image, ImageDraw

    spec = _load(args.spec)
    hidden = [n.name for n in spec.root.walk() if n.attrs.get("StartHidden")]
    panel = args.panel or (hidden[0] if hidden else None)
    L.HIDE_START_HIDDEN.update({"on": bool(hidden), "except": panel})
    end = L.timeline_end(spec.root)
    if end <= 0:
        print("no enter/leave animations in this spec (add \"enter\" / \"leave\" to nodes).")
        return 1
    if args.times:
        times = [float(x) for x in args.times.split(",")]
    else:
        n = 6
        times = [round(end * i / (n - 1) * 1.02, 2) for i in range(n)]
    fw, fh, cols = 640, 360, 3
    rows = (len(times) + cols - 1) // cols
    sheet = Image.new("RGB", (fw * cols, fh * rows), (16, 18, 22))
    d = ImageDraw.Draw(sheet)
    for i, t in enumerate(times):
        L.ANIM["t"] = t
        img, _ = render.render(spec, args.device, 1.0, args.backdrop, chrome=False)
        x, y = (i % cols) * fw, (i // cols) * fh
        sheet.paste(img.resize((fw, fh), Image.LANCZOS), (x, y))
        d.rectangle([x + 6, y + 6, x + 78, y + 24], fill=(0, 0, 0))
        d.text((x + 10, y + 9), f"t = {t:.2f}s", fill=(255, 255, 255))
    L.ANIM["t"] = None
    L.HIDE_START_HIDDEN.update({"on": False, "except": None})
    out = Path(args.out or Path(args.spec).with_suffix(".story.png"))
    sheet.save(out)
    print(f"storyboard: {out}  ({len(times)} frames, 0 to {times[-1]:.2f}s" + (f", panel {panel} opening" if panel else "") + ")")
    return 0


def cmd_tree(args):
    print(export.tree_text(_load(args.spec).root))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="rbxui", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("check", help="lint + review image (+ build)")
    p.add_argument("spec")
    p.add_argument("--no-image", action="store_true")
    p.add_argument("--image", help="where to write the review image")
    p.add_argument("--zoom", action="append", help="name of the node to show in the close-up")
    p.add_argument("--backdrop", help="day sunset night horror interior arena space forest flat-light flat-dark, or an image path")
    p.add_argument("--build", metavar="DIR", help="also export here when there are no errors")
    p.add_argument("--parent", default='game:GetService("StarterGui")')
    p.add_argument("--max", type=int, default=3, help="findings shown per rule")
    p.set_defaults(fn=cmd_check)

    p = sub.add_parser("build", help="export real instances")
    p.add_argument("spec")
    p.add_argument("--out")
    p.add_argument("--parent", default='game:GetService("StarterGui")')
    p.add_argument("--force", action="store_true")
    p.add_argument("--max", type=int, default=3)
    p.set_defaults(fn=cmd_build)

    p = sub.add_parser("preview", help="one full-size render or a named close-up")
    p.add_argument("spec")
    p.add_argument("-o", "--out")
    p.add_argument("--device", default="pc", help=", ".join(L.DEVICES))
    p.add_argument("--scale", type=float, default=1.0)
    p.add_argument("--zoom", help="crop to the node with this name")
    p.add_argument("--backdrop")
    p.add_argument("--no-chrome", action="store_true")
    p.set_defaults(fn=cmd_preview)

    p = sub.add_parser("storyboard", help="frames of the enter/leave animation sequence")
    p.add_argument("spec")
    p.add_argument("-o", "--out")
    p.add_argument("--panel", help="startHidden panel to open (default: the first)")
    p.add_argument("--times", help="comma-separated seconds, e.g. 0,0.3,0.6,1,1.5,2.2")
    p.add_argument("--device", default="pc")
    p.add_argument("--backdrop")
    p.set_defaults(fn=cmd_storyboard)

    p = sub.add_parser("tree", help="print the instance hierarchy")
    p.add_argument("spec")
    p.set_defaults(fn=cmd_tree)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
