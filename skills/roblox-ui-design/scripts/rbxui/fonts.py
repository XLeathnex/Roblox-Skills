"""Font resolution for the preview renderer and the font linter.

Roblox ships these families at rbxasset://fonts/families/<Name>.json. The
preview renders them with open-licensed TTFs bundled in assets/fonts. A family
without a bundled file falls back to the nearest look-alike so the preview
still shows the right *kind* of type; Studio always uses the real font.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

FONT_DIR = Path(__file__).resolve().parent.parent.parent / "assets" / "fonts"

WEIGHTS = {"Thin": 100, "ExtraLight": 200, "Light": 300, "Regular": 400, "Medium": 500,
           "SemiBold": 600, "Bold": 700, "ExtraBold": 800, "Heavy": 900}

# family -> weights Roblox actually ships (from the Enum.Font documentation tables)
ROBLOX_FAMILIES = {
    "AccanthisADFStd": ["Regular"], "Balthazar": ["Regular"], "Bangers": ["Regular"],
    "Creepster": ["Regular"], "DenkOne": ["Regular"], "Fondamento": ["Regular"],
    "FredokaOne": ["Regular"], "Guru": ["Regular"], "HighwayGothic": ["Regular"],
    "IndieFlower": ["Regular"], "LuckiestGuy": ["Regular"], "Michroma": ["Regular"],
    "PatrickHand": ["Regular"], "PermanentMarker": ["Regular"], "PressStart2P": ["Regular"],
    "RomanAntique": ["Regular"], "SpecialElite": ["Regular"], "Zekton": ["Regular"],
    "LegacyArial": ["Regular"],
    "ComicNeueAngular": ["Bold"],
    "AmaticSC": ["Regular", "Bold"],
    "Kalam": ["Light", "Regular", "Bold"],
    "RobotoCondensed": ["Light", "Regular", "Bold"],
    "BuilderMono": ["Light", "Regular", "Bold"],
    "Ubuntu": ["Light", "Regular", "Medium", "Bold"],
    "Arimo": ["Regular", "Medium", "SemiBold", "Bold"],
    "Merriweather": ["Light", "Regular", "Bold", "Heavy"],
    "BuilderExtended": ["Light", "Regular", "SemiBold", "Bold", "ExtraBold"],
    "Jura": ["Light", "Regular", "Medium", "SemiBold", "Bold"],
    "Roboto": ["Thin", "Light", "Regular", "Medium", "Bold", "Heavy"],
    "Oswald": ["ExtraLight", "Light", "Regular", "Medium", "SemiBold", "Bold"],
    "SourceSansPro": ["ExtraLight", "Light", "Regular", "SemiBold", "Bold", "Heavy"],
    "TitilliumWeb": ["ExtraLight", "Light", "Regular", "SemiBold", "Bold", "Heavy"],
    "Sarpanch": ["Regular", "Medium", "SemiBold", "Bold", "ExtraBold", "Heavy"],
    "JosefinSans": ["Thin", "ExtraLight", "Light", "Regular", "Medium", "SemiBold", "Bold"],
    "RobotoMono": ["Thin", "ExtraLight", "Light", "Regular", "Medium", "SemiBold", "Bold"],
    "BuilderSans": ["Thin", "ExtraLight", "Light", "Regular", "Medium", "SemiBold", "Bold", "ExtraBold"],
    "Nunito": ["ExtraLight", "Light", "Regular", "SemiBold", "Bold", "ExtraBold", "Heavy"],
    "Inconsolata": ["ExtraLight", "Light", "Regular", "Medium", "SemiBold", "Bold", "ExtraBold", "Heavy"],
    "Montserrat": ["Thin", "ExtraLight", "Light", "Regular", "Medium", "SemiBold", "Bold", "Heavy"],
    "GrenzeGotisch": list(WEIGHTS),
}

# family -> (file, variable?, forced weight or None, substitute?)
_FILES = {
    "FredokaOne": ("Fredoka.ttf", True, 700, False),
    "LuckiestGuy": ("LuckiestGuy.ttf", False, None, False),
    "Bangers": ("Bangers.ttf", False, None, False),
    "Montserrat": ("Montserrat.ttf", True, None, False),
    "Oswald": ("Oswald.ttf", True, None, False),
    "SpecialElite": ("SpecialElite.ttf", False, None, False),
    "Creepster": ("Creepster.ttf", False, None, False),
    "Michroma": ("Michroma.ttf", False, None, False),
    "PressStart2P": ("PressStart2P.ttf", False, None, False),
    "PermanentMarker": ("PermanentMarker.ttf", False, None, False),
    "Nunito": ("Nunito.ttf", True, None, False),
    "JosefinSans": ("JosefinSans.ttf", True, None, False),
    "Jura": ("Jura.ttf", True, None, False),
    "Fondamento": ("Fondamento.ttf", False, None, False),
    "GrenzeGotisch": ("GrenzeGotisch.ttf", True, None, False),
    "AmaticSC": ("AmaticSC.ttf", False, None, False),
    "TitilliumWeb": ("TitilliumWeb.ttf", False, None, False),
    "Inconsolata": ("Inconsolata.ttf", True, None, False),
    "Balthazar": ("Balthazar.ttf", False, None, False),
    # look-alikes for families we do not bundle
    "BuilderSans": ("Montserrat.ttf", True, None, True),
    "BuilderExtended": ("Montserrat.ttf", True, None, True),
    "BuilderMono": ("Inconsolata.ttf", True, None, True),
    "SourceSansPro": ("Nunito.ttf", True, None, True),
    "Roboto": ("Montserrat.ttf", True, None, True),
    "RobotoCondensed": ("Oswald.ttf", True, None, True),
    "RobotoMono": ("Inconsolata.ttf", True, None, True),
    "Arimo": ("Montserrat.ttf", True, None, True),
    "LegacyArial": ("Montserrat.ttf", True, None, True),
    "Ubuntu": ("Nunito.ttf", True, None, True),
    "HighwayGothic": ("Oswald.ttf", True, None, True),
    "Sarpanch": ("Audiowide.ttf", False, None, True),
    "Zekton": ("Jura.ttf", True, None, True),
    "Merriweather": ("PlayfairDisplay.ttf", True, None, True),
    "Guru": ("PlayfairDisplay.ttf", True, None, True),
    "AccanthisADFStd": ("PlayfairDisplay.ttf", True, None, True),
    "RomanAntique": ("Balthazar.ttf", False, None, True),
    "DenkOne": ("Fredoka.ttf", True, 600, True),
    "ComicNeueAngular": ("Fredoka.ttf", True, 500, True),
    "Kalam": ("PermanentMarker.ttf", False, None, True),
    "IndieFlower": ("PermanentMarker.ttf", False, None, True),
    "PatrickHand": ("PermanentMarker.ttf", False, None, True),
}
_FALLBACK = ("Montserrat.ttf", True, None, True)

substituted: set = set()  # families the preview could not render exactly (reported to the user)


def known_family(family: str) -> bool:
    return family in ROBLOX_FAMILIES or family.startswith("rbxassetid://") or family.startswith("rbxasset://")


def supported_weights(family: str):
    return ROBLOX_FAMILIES.get(family)


@lru_cache(maxsize=512)
def _load(file: str, size_px: int, weight: int | None):
    path = FONT_DIR / file
    font = ImageFont.truetype(str(path), size_px)
    if weight is not None:
        try:
            axes = font.get_variation_axes()
            vals = []
            for ax in axes:
                name = ax.get("name")
                name = name.decode() if isinstance(name, bytes) else str(name)
                if "eight" in name:
                    vals.append(max(ax["minimum"], min(ax["maximum"], weight)))
                else:
                    vals.append(ax.get("default", ax["minimum"]))
            font.set_variation_by_axes(vals)
        except Exception:
            pass
    return font


@lru_cache(maxsize=256)
def _line_ratio(file: str, weight: int | None) -> float:
    f = _load(file, 200, weight)
    ascent, descent = f.getmetrics()
    return 200 / max(1, ascent + descent)


def get(font: dict | None, text_size: float):
    """Return a PIL font whose *line height* is `text_size` px (that is what Roblox TextSize means)."""
    family = (font or {}).get("family", "LegacyArial")
    weight_name = (font or {}).get("weight", "Regular")
    entry = _FILES.get(family)
    if entry is None:
        entry = _FALLBACK
    file, variable, forced, substitute = entry
    if substitute or family not in _FILES:
        substituted.add(family)
    if not (FONT_DIR / file).exists():
        substituted.add(family)
        return ImageFont.load_default(size=max(6, int(text_size * 0.8)))
    weight = forced if forced is not None else (WEIGHTS.get(weight_name, 400) if variable else None)
    em = max(4, int(round(text_size * _line_ratio(file, weight))))
    return _load(file, em, weight)
