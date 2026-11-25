---
name: roblox-ui-design
description: Design and build Roblox game UI (HUDs, shops, inventories, menus, settings, dialogs, any ScreenGui or GuiObject work) that looks made by a professional designer for that specific game instead of generic AI output, delivered as real instances in StarterGui rather than a script that builds UI at runtime. Use whenever a task creates, restyles, reviews or fixes Roblox UI, even if the user only says "make a shop", "add a menu" or "the UI looks bad".
---

# Roblox UI design

Three rules decide whether UI reads as designed or as AI slop:

1. **It belongs to this game.** Shape, colour, type and motion come from the game's world, not from a default. A shop that could be dropped into any other game unchanged has no direction yet.
2. **One system.** A handful of colours, radii, stroke weights and text sizes, defined once as tokens and reused. One light from above: lit top edges, shaded bottoms, shadows falling down.
3. **Real instances.** You write a compact JSON spec; the tool turns it into Frames, TextLabels, UICorners etc. that live in StarterGui and can be edited in the Explorer. Scripts only add behaviour.

## Workflow

1. **Read the game.** Name, genre, setting, materials, mood. If the project already has UI, reuse its fonts and colours. Open ONE style card: `references/styles/<genre>.md` (simulator, tycoon, horror, story, anime, shooter, roleplay, obby, fantasy, scifi).
2. **Write `meta`.** `genre`, `depth` (flat | soft | chunky | material), `motion` (calm | snappy | bouncy) and `direction`: one sentence built from this game's own nouns, naming the material, the shape motif, the palette logic and the type voice. Example: "Candy factory: hard-candy buttons on cream wafer panels, chocolate outlines instead of black, bubbly type, mint means buy".
3. **Tokens, then components, then the tree.** Build the hero component first (the main button or row), following your depth style's recipe in `references/depth.md`, then derive everything else from the same tokens.
4. **Check.** `python3 <skill>/scripts/rbxui check ui.json`. Fix every ERROR. Fix each WARN or decide it is intended. Use `--no-image` while fixing; open the review image once lint is clean and judge it with the list below.
5. **Build and deliver.** `python3 <skill>/scripts/rbxui check ui.json --build out/`, then get it into Studio with `references/studio.md`.

Stay cheap: read only the references the task needs, never re-read one, and look at the image at most twice.

## Spec format

```json
{
 "meta": {"genre": "simulator", "game": "Sugar Rush Pets", "depth": "chunky", "motion": "bouncy", "direction": "..."},
 "tokens": {"c": {"brand": "#FF5FA2", "ink": "#4A2618"}, "r": {"md": 16}, "font": {"display": "FredokaOne"}},
 "components": {
  "Btn": {"params": {"text": "OK", "color": "$c.brand"},
   "node": {"class": "TextButton", "Size": [0, 200, 0, 64], "BackgroundColor3": "#FFFFFF", "corner": "$r.md",
            "gradient": ["shade({{color}},1)", "shade({{color}},-1)"],
            "children": [{"class": "TextLabel", "Size": [1, 0, 1, 0], "Text": "{{text}}", "FontFace": "$font.display", "TextSize": 28, "TextColor3": "#FFFFFF"}]}}
 },
 "root": {"class": "ScreenGui", "name": "ShopGui", "children": [
   {"class": "Frame", "name": "ShopPanel", "autoscale": "modal", "AnchorPoint": [0.5, 0.5], "Position": [0.5, 0, 0.5, 0], "Size": [0, 820, 0, 470],
    "children": [{"use": "Btn", "name": "BuyButton", "Position": [0, 40, 1, -90], "text": "BUY", "color": "$c.brand"}]}
 ]}
}
```

- **Node**: `class`, `name`, Roblox properties in PascalCase, sugar in lowercase, `children`. Or `{"use": "Component", ...params, ...property overrides}`. `"if": "{{param}}"` drops a node when the param is false or empty. Name every object for what it is.
- **Values**: UDim2 `[xScale, xOffset, yScale, yOffset]`; UDim `[scale, offset]` or a pixel number; Vector2 `[x, y]`; enums by name; font `"Family"` or `"Family:Weight"`; image `"rbxassetid://ID"` or `"asset:name"` (a PNG in `assets/` beside the spec).
- **Colour**: `"#RRGGBB"`, `"$c.brand"`, or an expression: `shade(c, n)` moves n steps lighter (+) or darker (-) with a painterly hue shift, `mix(a, b, 0.5)`, `ink(bg)` gives readable text for a background, `lighten/darken(c, 0.1)`, `saturate(c, 0.8)`, `hue(c, 20)`. Derive shades from tokens; do not invent new hexes.
- **Sugar** (each becomes a real child instance):
  - `corner`: `12` | `[scale, offset]` | `{"tl":..,"tr":..,"bl":..,"br":..}`
  - `stroke`: `{color, thickness, transparency, position: "Inner|Center|Outer", mode: "Border|Contextual", gradient}`; `strokes`: a list. On text with content a stroke outlines the glyphs.
  - `gradient`: `[top, ..., bottom]` or `{colors, rotation, transparency: [..], type: "Radial"}`. Gradients MULTIPLY the base colour, so put `"BackgroundColor3": "#FFFFFF"` under one.
  - `shadow`: `{color, offset: [x, y], blur, spread, transparency, inset}` (UIShadow). Add several as `{"class": "UIShadow", ...}` children with negative `ZIndex`.
  - `padding`: `12` | `[v, h]` | `[t, r, b, l]`. `list`: `{dir: "H|V", gap, align, valign, wraps, hflex}`. `grid`: `{cell: [..], gap, max}`. `aspect`, `maxText`, `minText`, `flex`.
  - `autoscale`: `"modal"` (centred panel) or `"hud"` (edge-anchored group). Design in 1080p pixels inside it; it is scaled per device.
  - `motion`: `"button"` | `"panel"`. `opens` / `closes` / `toggles`: `"PanelName"`. `startHidden`: `true`.
- **Defaults here** (unlike raw Studio): no background unless you give `BackgroundColor3`; no border; empty text; gradient runs top to bottom.
- `"extends": "design-system.json"` shares tokens and components across every screen of one game. Use it for the second screen onward.

## Judge the review image

The linter measures. These it cannot, so look for them:

- **Belonging**: would a player recognise this game from the UI alone? If not, the direction is too generic; push the material and motif further.
- **One focal point**: the primary action is the largest, most saturated thing. Everything else is quieter.
- **Rhythm**: shared left edges, equal gaps, text never crowding an edge.
- **Close-up**: highlights follow the shape and fade, edges are darker shades of their own fill, nothing looks pasted on.
- **Restraint**: remove one decoration before you ship.

## References

- `references/styles/<genre>.md`: the visual language of one genre and how to make it this game's own. Read one.
- `references/depth.md`: construction recipes for flat, soft, chunky and material surfaces. Read your depth style's section.
- `references/layout.md`: HUD zones, phone limits, modal sizing, scrolling lists and grids.
- `references/fonts.md`: the fonts Roblox ships, by voice.
- `references/assets.md`: drawing textures, shapes and icons in Python; uploading them.
- `references/studio.md`: getting the build into Studio, wiring buttons and panels, game-script hooks.
