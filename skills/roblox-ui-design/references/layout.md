# Layout

## Sizing

Design in 1080p pixels (offsets) inside a group marked `autoscale`. The bundled UIRuntime script scales each group by `(screenHeight / 1080) ^ 0.4`, so a phone gets about 0.66x instead of 0.36x and stays tappable.

- `"autoscale": "hud"`: an edge-anchored group. Anchor it with scale + anchor point (`"AnchorPoint": [0, 0.5], "Position": [0, 16, 0.5, 0]`), size it in offsets.
- `"autoscale": "modal"`: a centred panel. Draw it at any convenient size in landscape proportions (for example 1200x680); it is scaled to fill about 94% of a phone's safe area and about 76% of a desktop's, so it is always a substantial part of the screen. Because a phone is small, keep body text at least 1/22 of the panel's height and scroll long lists instead of shrinking them.
- Full-screen layers (scrims, vignettes) use scale `[1,0,1,0]` and no autoscale. A ScreenGui that must cover the notch and top bar sets `"ScreenInsets": "None"`.
- Sizes at 1080p: buttons 60px tall or more (primary 64-76); HUD side buttons and hotbar slots 76-92 square with 44-56 icons; bars 320-440 wide and 24-32 tall; HUD text 22 or larger. Anything smaller is unreadable on a phone.
- A phone in landscape is only about 590 design-pixels tall and 1270 wide after scaling. Give every HUD group its own corner or edge and keep a left or right edge stack under about 300px tall, or groups that look far apart at 1080p will collide (the linter checks this).

## HUD zones

```
[Roblox menu+chat]      currency / objective / timer        [leaderboard]
 side menu (left,                                            offers, event,
 35-60% height)             keep the centre clear            quest tracker
 [thumbstick]            hotbar / ability bar                   [jump]
```

- Never place buttons over the top-left 124x58 (Roblox buttons), the bottom-left thumbstick or the bottom-right jump button on touch devices; the linter checks this on a phone.
- Side menu: a column or 2-wide grid of 4-6 square buttons, left edge, vertically centred or slightly above.
- Currency: top-centre or top-right just under the top bar, or stacked above the side menu.
- Hotbar and health: bottom-centre, between the thumb zones. Action buttons on touch cluster above and left of jump.
- 16px minimum from any screen edge.

## Structure

- One ScreenGui per concern (HUD, Shop, Settings) or one ScreenGui with named panels; panels are `"motion": "panel"` and usually `"startHidden": true`.
- Use `list` and `grid` for anything repeated; hand-placed rows drift. Spacing from a small scale (4, 8, 12, 16, 24, 32).
- Scrolling: `{"class": "ScrollingFrame", "CanvasSize": [0,0,0,0], "AutomaticCanvasSize": "Y", "ScrollBarThickness": 6, ...}`. UICorner and UIGradient do not work on a ScrollingFrame: style a parent Frame and keep the ScrollingFrame transparent inside it.
- `ClipsDescendants` clips to the rectangle, not the rounded corners. Use `"class": "CanvasGroup"` when children must be clipped to a rounded shape (and for whole-panel fades).
- Text: fixed `TextSize` from your type scale. Use `TextScaled` only with `maxText` for content of unknown length (player names, numbers).
- A modal's anatomy: title (largest text), content, exactly one primary button, a close button on the top-right corner.
