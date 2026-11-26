# Fonts Roblox ships

Write `"FontFace": "Family"` or `"Family:Weight"`. Pick one display face (titles, buttons, numbers) and one body face (labels, descriptions). The display face carries the game's voice; choose it from the world, not from habit. Weights: Thin, ExtraLight, Light, Regular, Medium, SemiBold, Bold, ExtraBold, Heavy.

| Voice | Families (weights) |
|---|---|
| Bubbly, cartoon | FredokaOne, LuckiestGuy, DenkOne, ComicNeueAngular (Bold), Nunito (ExtraLight-Heavy) |
| Comic, action, shout | Bangers, LuckiestGuy, PermanentMarker |
| Clean modern | Montserrat (Thin-Heavy), BuilderSans (Thin-ExtraBold), Nunito, Ubuntu, Arimo |
| Condensed, sporty, tactical | Oswald (ExtraLight-Bold), RobotoCondensed (Light, Regular, Bold), TitilliumWeb, Sarpanch (Regular-Heavy), BuilderExtended |
| Sci-fi, tech | Michroma, Jura (Light-Bold), Zekton, Sarpanch, RobotoMono, Inconsolata, BuilderMono |
| Horror, typewriter, distressed | SpecialElite, Creepster (sparingly: it reads as costume), PermanentMarker |
| Old-world, fantasy, serif | Fondamento, GrenzeGotisch (Thin-Heavy), Balthazar, Merriweather (Light, Regular, Bold, Heavy), Guru, AccanthisADFStd, RomanAntique |
| Handwritten, cosy | Kalam (Light, Regular, Bold), PatrickHand, IndieFlower, AmaticSC (Regular, Bold) |
| Retro pixel | PressStart2P (small sizes, `ResampleMode` irrelevant; keep text short) |

- **FredokaOne and LuckiestGuy are worn out.** They are on every generic simulator, so players read them as a template. Avoid them unless the user's game already uses them.
- **Titles should be lettering, not a font choice.** Draw the screen title, logo and hero numbers as images with `da.lettering()` (assets.md): any Google Fonts family, layered outlines, depth, an arch. That is where a UI gets a voice no other game has.
- For live text (numbers, names, descriptions) choose a built-in face that echoes the lettering and is not the obvious one: Bangers or Sarpanch instead of LuckiestGuy; Nunito:ExtraBold, DenkOne or TitilliumWeb:Bold instead of FredokaOne.
- Good pairings: LuckiestGuy + Nunito:Bold; Bangers + Montserrat:SemiBold; Oswald:Bold + RobotoCondensed; Michroma + Jura:Medium; SpecialElite + RobotoCondensed:Light; GrenzeGotisch:Bold + Merriweather; Fondamento + Balthazar; Montserrat:Heavy + Montserrat:Medium.
- Type scale: 3-4 sizes with clear jumps, e.g. 18 / 24 / 32 / 48 at 1080p. Title at least 2x body.
- Roblox has no letter-spacing. For tracked-out caps, use a wide face (Michroma, BuilderExtended) or put spaces between letters in short labels.
- Creator Store fonts work as `"FontFace": "rbxassetid://ID:Bold"`.
