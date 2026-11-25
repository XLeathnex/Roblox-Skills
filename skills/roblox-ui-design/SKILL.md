---
name: roblox-ui-design
description: Design and build Roblox game UI (HUDs, shops, inventories, menus, settings, dialogs, any ScreenGui or GuiObject work) that looks made by a professional designer for that specific game instead of generic AI output, delivered as real instances in StarterGui rather than a script that builds UI at runtime. Use whenever a task creates, restyles, reviews or fixes Roblox UI, even if the user only says "make a shop", "add a menu" or "the UI looks bad".
---

# Roblox UI design

**The bar:** a screenshot of what you build should pass as a shipped, top-of-its-genre Roblox game made by a UI artist. Not "clean", not "fine": something a player would recognise as that game. If you would have produced the same screen for a different game, it is not done.

This skill gives you knowledge and optional tools. It does not give you a house style or a template, and nothing in it should hold you back from doing better than its examples.

## Three things that are not optional

1. **Real instances.** The UI is Frames, TextLabels, ImageLabels and so on living in StarterGui, named and editable in the Explorer. Never a LocalScript that builds the UI with `Instance.new` at runtime. Scripts only add behaviour.
2. **It belongs to this game.** Shape language, palette, type, materials and motion come from the game's world. Write the art direction down in one sentence before building anything.
3. **It works on a phone and a PC**, clear of the Roblox top-left buttons, the thumbstick and the jump button.

## How to work

1. **Read the game**, then set the direction: the material or world the UI is made of, its shape motif, the palette logic, the type voice, how it moves. `references/styles/<genre>.md` describes what the best games in ten genres do and how to push past the cliché (simulator, tycoon, horror, story, anime, shooter, roleplay, obby, fantasy, scifi). Use it as a starting point, not a recipe.
2. **Compose for the whole screen.** Decide the one thing the eye should hit first and make it big. A shop or inventory fills most of a phone and 60-75% of a desktop; a HUD owns its corners with confidence. Small panels floating in empty space read as a prototype.
3. **Build it rich.** Top Roblox UI is layered and largely image-based: custom panel frames, ribbons, plaques, item art, icons, textures, glows. Draw the pieces this game needs yourself in Python (`references/assets.md`) rather than settling for plain rounded rectangles and generic glyphs. Layer instances freely: backing plates, inner wells, highlights, shadows, patterns, decorative shapes that break the frame.
4. **Look at it, then make it better.** Render or screenshot, compare it honestly against the bar, and iterate on what is weakest: composition first, then depth and material, then detail. Keep going until it would pass. Stop when another pass would only move pixels.

## What makes UI read as AI slop

Avoid these because they are defaults, not choices:

- every shape a pill or the same radius; every surface a flat rectangle
- a different vivid two-colour gradient on each button; purple-to-pink anything
- a pale blob in the top half of a button pretending to be gloss (real highlights follow the shape's edge and fade)
- one font at one weight; emoji as icons; pure black outlines and shadows
- everything the same size and centred, nothing dominant; a small card in a big empty screen
- the same look regardless of genre

And the opposite failure: so much restraint that nothing has character. A simulator should be loud; a horror menu should feel like an object from its world.

`references/depth.md` shows how depth is actually constructed (lips, inset light, tinted shadows, materials). Its snippets are anatomy lessons. Do not paste them; build your own.

## Building it

Use whichever route fits the session. Both produce real instances.

- **Directly.** Write a one-time builder in Luau and run it in Studio's edit mode (an MCP `execute_luau` call on the Edit datamodel, or the command bar). It creates the instances under StarterGui inside one undo step and is then discarded; it is not a game script. Screenshot in Studio and iterate. This is the most expressive route.
- **With the spec tool** (no Studio connection, or you want a preview and checks first). Describe the instance tree in a compact JSON spec (`references/spec.md`), then:
  `python3 <skill>/scripts/rbxui check ui.json` renders it on PC and phone and lists problems;
  `python3 <skill>/scripts/rbxui check ui.json --build out/` exports a builder script, an `.rbxmx` and a Rojo model.
  The preview is an approximation of Roblox's renderer, good for judging composition, colour and overflow.

About the checker: an **ERROR** is a real problem (a property that does not exist, UI off-screen on a phone, a button under the jump control). A **WARN** is advice from a rule of thumb. Follow it when it is right and ignore it when it fights your direction; do not design to silence warnings.

`references/layout.md` covers scaling, HUD zones and phone limits. `references/fonts.md` lists the fonts Roblox ships. `references/studio.md` covers getting the build into Studio and wiring behaviour.
