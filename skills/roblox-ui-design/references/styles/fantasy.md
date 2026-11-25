# Fantasy / medieval / survival / crafting / pirate / western

Hand-made objects from the world: wood, iron, parchment, stone, leather. `depth: material`, `motion: snappy`. Minimalist fantasy (soulslike, roguelike) uses `depth: flat` with thin serif type and hairline ornaments instead.

- **Panels**: a tiled material fill plus a 9-slice frame (see depth.md, material). Content in an inset well. Corner brackets, nails or rope only at corners and headers.
- **Colour**: low-to-mid saturation earth tones (browns, tans, moss, slate, muted gold) with one jewel accent (ruby, emerald, sapphire) for the primary action and magic.
- **Type**: a period display face for headers (Fondamento, GrenzeGotisch, Balthazar) and a readable serif or plain sans for body. Dark brown ink on parchment; cream with a dark stroke on wood or stone.
- **Inventory**: a grid of square slots that look recessed (inset dark top shadow), quantity bottom-right, rarity as a tinted inner edge, hover lifts the slot.
- **Crafting**: recipe list left, detail and "Craft" button right, ingredient chips that turn red when missing.
- **HUD**: health, hunger and stamina bars bottom-left or bottom-centre above a numbered hotbar; bars are inset tracks with a lit fill; a small compass or day-night dial top-centre.
- **Buttons**: plates of a second material (iron on wood, wax seal on parchment) with a lip.

**Make it this game's**: choose the two materials from the setting (viking = pine and hammered iron, desert tomb = sandstone and lapis, pirate = weathered teak and brass) and pass the base colour to `draw_assets.py material`. Add one motif (runes, knotwork, rivets) and repeat it.
