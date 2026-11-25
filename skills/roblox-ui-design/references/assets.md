# Images: when and how

UICorner, UIStroke, UIGradient and UIShadow already cover rounded rectangles, outlines, gradients (linear, radial, conical), drop and inset shadows. Reach for an image only for what instances cannot do: textures, non-rectangular shapes, material frames, atmosphere overlays, icons. A UI must still look finished before its images are uploaded.

## Draw them

```bash
python3 <skill>/scripts/draw_assets.py list
python3 <skill>/scripts/draw_assets.py texture stripes -o ui/assets/stripes.png
python3 <skill>/scripts/draw_assets.py shape chamfer -o ui/assets/plate.png --cut 18 --border 3
python3 <skill>/scripts/draw_assets.py material wood -o ui/assets/wood.png --color "#8A5A34"
python3 <skill>/scripts/draw_assets.py overlay vignette -o ui/assets/vignette.png
python3 <skill>/scripts/draw_assets.py icon cart -o ui/assets/cart.png            # white glyph, tint with ImageColor3
python3 <skill>/scripts/draw_assets.py icon gem -o ui/assets/gem.png --style toon --color "#4FC3FF"
```

Each call prints the spec snippet to paste (with `SliceCenter` / `TileSize` filled in) and records the file in `assets/assets.json`. Put assets in an `assets/` folder beside the spec and reference them as `"Image": "asset:name"`; the preview loads them from there.

- **Textures** (noise, stripes, dots, studs, grid, scanlines, hex, checker) are white with alpha: tile them over a surface at `ImageTransparency` 0.85-0.96 and tint with `ImageColor3`. They break up flat fills and blend a panel into one material.
- **Shapes** (chamfer, chamfer2, skew, ribbon, tab, hexagon, burst, bracket) are greyscale with baked top-light, so `ImageColor3` recolours one upload for every button colour. They are 9-slice: keep `ScaleType: "Slice"` and the printed `SliceCenter`.
- **Materials** give a tile fill plus a 9-slice frame in the colour you pass.
- **Overlays**: vignette, glow, sunburst, spotlight, scrim.
- **Icons**: about 40 names. `glyph` is a flat white silhouette; `toon` is shaded and outlined in the colour you pass. Use one icon style per UI. Never use emoji as icons: they render in the platform's style and ignore your palette.

## Draw your own

When the game needs a shape or icon the list lacks, write a short script with the same helpers instead of settling for a generic one:

```python
import sys; sys.path.insert(0, "<skill>/scripts")
import draw_assets as da
from pathlib import Path
g = da.Glyph(256)                      # 0..100 vector box, supersampled
g.poly([(50, 6), (94, 50), (50, 94), (6, 50)])   # also circle, ellipse, rrect, line, arc, ring; fill=0 cuts
g.circle(50, 50, 14, fill=0)
img = da.toonify(g.mask(), da.C.parse_hex("#E8563A"), outline_px=8, pad=28)   # or da.rgba((1,1,1), g.mask()) for a glyph
da.save(img, Path("ui/assets/rune.png"), "icon", {"class": "ImageLabel", "Image": "asset:rune", "ScaleType": "Fit"})
```

`da.tile_noise(w, h, sx, sy)` gives tileable noise for custom textures; `da._shade_shape(mask, border, bevel)` makes a tintable shaded plate from any mask. Look at the result (`draw_assets.py sheet -o ui/assets/_sheet.png`) before using it. Keep images at or under 1024px and about 2x their on-screen size.

## Upload

Built instances carry a `PendingAsset` attribute until the image has an id. Record ids in `assets/assets.json` (`"id": 1234567`) and rebuild.

1. **Studio MCP**: `open_cloud_invoke` to `POST apis.roblox.com/assets/v1/assets` with the file from the user's approved upload folder (`assetType: "Image"`), or `upload_image` for files reachable by URL.
2. **Open Cloud key**: `ROBLOX_API_KEY=... python3 <skill>/scripts/upload_assets.py ui/assets --user 12345` (or `--group`). It uploads every entry without an id and writes the ids back. The key needs asset read and write.
3. **By hand**: Studio Asset Manager > Import, then copy each image id into `assets.json`.

Upload as `Image`, not `Decal`: a decal id is not an image id and will not display.
