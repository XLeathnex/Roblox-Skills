# Art: draw this game's own

The best Roblox UI is mostly images: panel frames, ribbons, plaques, item art, icons, title lettering, textures. Instances (UICorner, UIStroke, UIGradient, UIShadow) give rounded rectangles with outlines, gradients and shadows; anything with more character is drawn. There is no stock icon or shape set on purpose: generic art never fits. Draw what this screen needs, at the size and shape it needs, in this game's style. Build structure from instances so the UI holds together before upload, then put the art on top.

Put PNGs in an `assets/` folder beside the spec and use `"Image": "asset:<name>"`. Look at what you drew (`python3 <skill>/scripts/draw_assets.py sheet -o ui/assets/_sheet.png`) before using it, and redraw anything weak.

## Toolkit

```python
import sys; sys.path.insert(0, "<skill>/scripts")
import draw_assets as da
from pathlib import Path
import numpy as np

s = da.Shape(256)                                   # vector canvas, coordinates 0..100, antialiased
s.poly([(50, 6), (94, 50), (50, 94), (6, 50)])      # also: circle, ellipse, rrect, line, arc, ring
s.blob(((50, 8), (96, 30), (84, 72)), ((84, 72), (50, 100), (16, 72)), ((16, 72), (4, 30), (50, 8)))  # bezier outline
s.curve((20, 60), (50, 30), (80, 60), width=6, fill=0)   # fill=0 cuts a detail out
body = da.paint(s.mask(), da.C.parse_hex("#E8563A"), outline_px=8, lip=5)   # shaded, rim-lit, outlined
halo = da.glow(np.pad(s.mask(), 24), da.C.parse_hex("#FFB14A"), radius=16)
da.save(da.layer(halo, body), Path("ui/assets/ember.png"), "art", {"Image": "asset:ember"})
```

- `da.paint(mask, color, outline=None, outline_px=0, light=0.8, shade=0.7, gradient=1.2, lip=0)`: one shaded part. Build an object from several parts (body, belly, eye, shine), each its own Shape and colour, and stack them with `da.layer(back, ..., front)`. Flat glyph: `da.rgba((1, 1, 1), mask)` then tint with `ImageColor3`.
- `da.plate(mask, border=3, bevel=True)`: a greyscale shaded plate from any silhouette (cut corners, skew, ribbon, shield). Tint with `ImageColor3` so one upload serves every colour. For a stretchable plate keep detail in the corners and set `ScaleType: "Slice"` with a `SliceCenter` inside them.
- `da.lettering(text, font, size=160, fill="#FFF", fill_bottom=None, strokes=[("#4A2618", 10)], extrude=0, arc=0, slant=0)`: a title drawn as art, with layered outlines, 3D depth and an arch that no TextLabel can do. `font` is a bundled name (Bangers, Oswald, Creepster, GrenzeGotisch, ...), any Google Fonts family (downloaded once: "Bungee", "Rye", "Pirata One", "Lilita One", "Russo One", "Cinzel Decorative"...) or a .ttf path. Use it for the screen title, logos and hero numbers; keep TextLabels for text that changes at runtime.
- `da.tile_noise(w, h, sx, sy)`: tileable noise for your own textures. `da.star_points`, `da.bezier_points` help with shapes.
- `da.save(image, path, kind, snippet)`: fixes transparent edges, records the file in `assets.json`.
- Plain Pillow and numpy work too; mix freely.

Craft notes: outline in a deep shade of the object's own hue, light from above, one highlight, shapes big and readable at 48px. Draw at about twice the on-screen size, at most 1024px. Keep one style across every image in a UI.

## Generic building blocks (command line)

Only for things that are the same in any game:

```bash
python3 <skill>/scripts/draw_assets.py batch ui/assets "texture stripes" "texture noise" "overlay vignette" "overlay sunburst" "material wood --color #8A5A34"
```

- Textures (noise, stripes, dots, studs, grid, scanlines, hex, checker): white with alpha; tile over a surface at `ImageTransparency` 0.85-0.96.
- Overlays: vignette, glow, sunburst, spotlight, scrim.
- Materials (wood, stone, parchment, metal, leather): a tile fill in your colour plus a plain frame. Treat the frame as a placeholder and draw your own with corner detail.

Each prints the spec snippet with `TileSize` / `SliceCenter` filled in.

## Upload

Built instances carry a `PendingAsset` attribute until the image has an id. Record ids in `assets/assets.json` (`"id": 1234567`) and rebuild.

1. Studio MCP: `open_cloud_invoke` to `POST apis.roblox.com/assets/v1/assets` (`assetType: "Image"`) with files from the approved upload folder.
2. Open Cloud key: `ROBLOX_API_KEY=... python3 <skill>/scripts/upload_assets.py ui/assets --user 12345` (or `--group`).
3. By hand: Studio Asset Manager > Import, then copy each image id into `assets.json`.

Upload as `Image`, not `Decal`.
