# Roblox Skills

Agent skills for building Roblox games with Claude (and other models that read skills).

| Skill | What it does |
|---|---|
| [`roblox-ui-design`](skills/roblox-ui-design/SKILL.md) | Designs UI that fits the specific game instead of generic AI output, checks it, previews it on PC and phone, and builds it as real instances for StarterGui. |

## Install

Copy a skill folder into your agent's skills directory, for example:

```bash
cp -r skills/roblox-ui-design ~/.claude/skills/          # every project
cp -r skills/roblox-ui-design <project>/.claude/skills/  # one project
```

The UI skill's preview needs Python 3 with Pillow and numpy (`pip install pillow numpy`). Linting and building work without them.

## roblox-ui-design in one minute

The model writes a compact JSON spec (tokens, components, instance tree). One command checks and previews it, another exports it:

```bash
python3 skills/roblox-ui-design/scripts/rbxui check ui.json              # lint + review image
python3 skills/roblox-ui-design/scripts/rbxui check ui.json --build out  # also export
```

- **Linter**: about 50 rules for the measurable tells of machine-made UI (everything a pill, fake white "gloss" blobs, rainbow button hues, gradients multiplied into mud, one font, flat rectangles) and for Roblox pitfalls (UI under the top bar or the jump button, off-screen on phones, unreadable text, unknown properties).
- **Preview**: a renderer that approximates Roblox's GUI engine (UICorner, UIStroke, UIGradient, UIShadow, layouts, 9-slice) over a stand-in game world, on PC and phone.
- **Build**: a one-time Studio builder script, an `.rbxmx` model and a Rojo `.model.json`, all describing the same real instances.
- **No fixed look**: the skill ships no templates. Style comes from ten short genre cards plus the game's own theme.

`tools/gen_schema.py` regenerates the property schema from a Roblox API dump.
