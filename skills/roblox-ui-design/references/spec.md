# Spec format (for the rbxui tool)

```json
{
 "meta": {"genre": "simulator", "game": "Sugar Rush Pets", "depth": "chunky", "motion": "bouncy", "direction": "..."},
 "tokens": {"c": {"brand": "#FF5FA2", "ink": "#4A2618"}, "r": {"md": 16}, "font": {"display": "FredokaOne"}},
 "components": {
  "Btn": {"params": {"text": "OK", "color": "$c.brand"},
   "node": {"class": "TextButton", "Size": [0, 200, 0, 64], "corner": "$r.md",
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
  - `gradient`: `[top, ..., bottom]` or `{colors, rotation, transparency: [..], type: "Radial"}`. A gradient multiplies the colour under it, so it supplies its own white base: do not also set `BackgroundColor3` on that node.
  - `shadow`: `{color, offset: [x, y], blur, spread, transparency, inset}` (UIShadow). Add several as `{"class": "UIShadow", ...}` children with negative `ZIndex`.
  - `padding`: `12` | `[v, h]` | `[t, r, b, l]`. `list`: `{dir: "H|V", gap, align, valign, wraps, hflex}`. `grid`: `{cell: [0, 200, 0, 240], gap: 12, max: 3}`. `aspect`, `maxText`, `minText`, `flex`.
  - `autoscale`: `"modal"` (centred panel) or `"hud"` (edge-anchored group). Design in 1080p pixels inside it; it is scaled per device.
  - `motion`: `"button"` | `"panel"`. `opens` / `closes` / `toggles`: `"PanelName"`. `startHidden`: `true`.
- **Defaults here** (unlike raw Studio): no background unless you give `BackgroundColor3`; no border; empty text; gradient runs top to bottom.
- `"extends": "design-system.json"` shares tokens and components across every screen of one game. Use it for the second screen onward.
