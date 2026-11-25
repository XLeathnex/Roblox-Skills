# Depth recipes

Depth is what separates designed UI from flat rectangles, and fake depth (a white blob for "gloss") is the loudest AI tell. Every recipe below obeys one light from above and builds each edge from a shade of the surface's own colour (`shade(c, -n)`), never black or grey. Read only your `meta.depth` section. These are anatomies with knobs, not templates: change the radius, stroke, lip height, fonts and shape to fit the game.

## chunky (simulator, cartoon, casual)

A solid object you could pick up: dark outline, lit face, hard bottom lip.

```json
"Btn": {"params": {"text": "BUY", "color": "$c.go"},
 "node": {"class": "TextButton", "Size": [0, 200, 0, 66], "motion": "button", "corner": "$r.md",
  "gradient": ["shade({{color}},1.2)", "{{color}}", "shade({{color}},-0.8)"],
  "stroke": {"color": "$c.line", "thickness": 3, "mode": "Border"},
  "children": [
   {"class": "UIShadow", "name": "LipEdge", "Color": "$c.line", "Offset": [0,0,0,7], "Spread": [0,3,0,3], "ZIndex": -2},
   {"class": "UIShadow", "name": "Lip", "Color": "shade({{color}},-3)", "Offset": [0,0,0,7], "ZIndex": -1},
   {"class": "UIShadow", "name": "TopLight", "Inset": true, "Color": "#FFFFFF", "Offset": [0,0,0,3], "Transparency": 0.5, "ZIndex": -3},
   {"class": "UIShadow", "name": "BottomShade", "Inset": true, "Color": "shade({{color}},-3)", "Offset": [0,0,0,-4], "Transparency": 0.45, "ZIndex": -4},
   {"class": "TextLabel", "name": "Label", "Size": [1,0,1,0], "Text": "{{text}}", "FontFace": "$font.display", "TextSize": 30, "TextColor3": "#FFFFFF",
    "stroke": {"color": "$c.line", "thickness": 2.5},
    "children": [{"class": "UIShadow", "Mode": "Text", "Color": "$c.line", "Offset": [0,0,0,3]}]}
  ]}}
```

- **Lip**: a UIShadow with no blur, offset down 5-8px, in `shade(color,-3)`. **LipEdge** is the same offset with `Spread` equal to the stroke thickness, in the outline colour, so the outline wraps the lip too.
- **TopLight / BottomShade**: inset shadows, offset 3 down (white) and 4 up (dark). They follow the corner radius exactly. This replaces any "gloss" shape.
- **Outline** `$c.line` is one tinted dark for the whole UI (deep navy, chocolate, plum), or `shade(color,-5)` per button. Never `#000000`.
- **Panels** use the same anatomy at lower contrast: gradient 2-4% lightness apart, stroke 4, lip 8-10, radius from `$r.lg`.
- Knobs that change the personality: radius (8 = blocky, 24 = bubbly), stroke 2-5, lip 4-10, outline hue, a slight `Rotation` (-2..2) on headers and tags, a texture ImageLabel at 0.85-0.93 transparency.

## soft (roleplay, life-sim, tycoon, modern)

Paper and light: no outlines, shallow gradients, a soft shadow that lifts the card.

```json
"Card": {"node": {"class": "Frame", "corner": "$r.lg",
  "gradient": ["shade($c.surface,0.3)", "shade($c.surface,-0.3)"],
  "children": [
   {"class": "UIShadow", "name": "Lift", "Color": "shade($c.surface,-6)", "Offset": [0,0,0,8], "BlurRadius": [0,24], "Transparency": 0.72, "ZIndex": -1},
   {"class": "UIShadow", "name": "Contact", "Color": "shade($c.surface,-6)", "Offset": [0,0,0,2], "BlurRadius": [0,4], "Transparency": 0.8, "ZIndex": -2},
   {"class": "UIShadow", "name": "Edge", "Inset": true, "Color": "#FFFFFF", "Offset": [0,0,0,1], "Transparency": 0.4, "ZIndex": -3}
  ]}}
```

- Two shadows: a wide soft Lift and a tight Contact, both tinted with the surface hue, 70-85% transparent. Raise blur and offset together for more elevation; only the top layer (modal) gets the largest.
- Buttons: solid `$c.primary` with a 5-10% gradient, same Edge highlight, no lip. Secondary buttons are a tinted neutral, not a second bright colour.
- Hairline option instead of shadow: `"stroke": {"color": "shade($c.surface,-3)", "thickness": 1, "transparency": 0.5}`. Pick shadow or hairline per surface, not both everywhere.
- Text is dark ink on light surfaces (`ink($c.surface)`), no stroke.

## flat (horror, cinematic, shooter, realism)

No objects at all: type, hairlines, scrims and empty space. Depth comes from value contrast and layering.

```json
"Row": {"params": {"label": "OPTION", "value": "ON"},
 "node": {"class": "TextButton", "Size": [1,0,0,54], "motion": "button", "children": [
  {"class": "TextLabel", "name": "Label", "Size": [0.6,0,1,0], "Text": "{{label}}", "FontFace": "$font.body", "TextSize": 26, "TextColor3": "$c.text", "TextXAlignment": "Left"},
  {"class": "TextLabel", "name": "Value", "AnchorPoint": [1,0], "Position": [1,0,0,0], "Size": [0.4,0,1,0], "Text": "{{value}}", "FontFace": "$font.display", "TextSize": 24, "TextColor3": "$c.dim", "TextXAlignment": "Right"},
  {"class": "Frame", "name": "Rule", "AnchorPoint": [0,1], "Position": [0,0,1,0], "Size": [1,0,0,1], "BackgroundColor3": "$c.text", "BackgroundTransparency": 0.86}
 ]}}
```

- Put text on a **scrim**, not a box: a full-screen or edge Frame in a tinted near-black at 0.2-0.5 transparency, or with `"gradient": {"transparency": [0, 1]}` so it fades out.
- **Hairlines** are 1px Frames or strokes at 0.6-0.9 transparency. Selection is a 2-3px accent bar, a brighter text value, or an underline, never a filled pill.
- Radius 0-4. One accent colour, used for the selected item and the primary action only.
- Hierarchy is size and weight: title 2.5-3x body, small caps labels in a dim value, generous gaps.
- Atmosphere (optional images, see assets.md): vignette, 3-6% grain, a spotlight.
- HUD plates for shooters: black at 0.3-0.5 transparency, 0-4 radius, white text, team colour as a thin edge bar.

## material (fantasy, survival, medieval, pirate, western)

A physical thing: wood, stone, parchment, metal, leather. Built from two images plus instance shading.

```json
"Panel": {"node": {"class": "Frame", "children": [
  {"class": "ImageLabel", "name": "Fill", "Size": [1,0,1,0], "Image": "asset:wood-fill", "ScaleType": "Tile", "TileSize": [0,256,0,256], "corner": 12},
  {"class": "Frame", "name": "Well", "Position": [0,26,0,26], "Size": [1,-52,1,-52], "BackgroundColor3": "shade($c.wood,-4)", "BackgroundTransparency": 0.35, "corner": 6,
   "shadow": {"inset": true, "color": "shade($c.wood,-7)", "offset": [0,4], "blur": 8, "transparency": 0.3}, "slot": true},
  {"class": "ImageLabel", "name": "Frame", "Size": [1,0,1,0], "Image": "asset:wood-frame", "ScaleType": "Slice", "SliceCenter": [32,32,160,160], "ZIndex": 5}
 ]}}
```

- `python3 <skill>/scripts/draw_assets.py material wood -o assets/wood.png --color "#8A5A34"` draws the tile fill and the 9-slice frame and prints the exact snippet (wood, stone, parchment, metal, leather).
- Content sits in an inset **Well** (dark inner shadow from the top: recessed surfaces are dark on top, light at the bottom).
- Text on dark material: cream with a dark same-hue stroke. On parchment: dark brown ink, no stroke.
- Buttons are smaller plates of a second material or a chunky button in a jewel accent.
- Keep ornament in corners and headers; edges that stretch must be plain.

## Shared rules

- Outset things (buttons, cards) are light on top and dark below. Inset things (wells, input fields, bar tracks, pressed states) are the reverse.
- Nested corners: inner radius = outer radius - gap.
- Gradient ends stay within about 35 degrees of hue; `shade()` does this for you.
- Progress bars: an inset track (dark top shadow) and a fill with its own top light; never two flat rectangles.
- If UIShadow is rejected by an old Studio, a lip is a sibling Frame of the same size placed behind and offset down.
