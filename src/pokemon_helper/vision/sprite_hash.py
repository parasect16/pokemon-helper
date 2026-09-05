"""Calcolo del pHash da un frame catturato.

Wrapper minimale attorno a `imagehash.phash` che accetta un `PIL.Image`,
lo normalizza (RGBA → RGB su fondo bianco per evitare che il canale alpha
alteri il hash) e ritorna la stringa esadecimale di 16 caratteri usata dal
DB `sprite_hashes`.

L'immagine di input di solito proviene da `PIL.Image.crop` sul frame full;
non viene ridimensionata: `imagehash.phash` lo fa già internamente
(default a 32×32 DCT).
"""

from __future__ import annotations

import colorsys

import imagehash
from PIL import Image


def compute_phash(image: Image.Image) -> str:
    """Calcola il pHash a 64 bit di un'immagine e lo ritorna come hex string.

    Se l'immagine ha un canale alpha, viene composta su sfondo bianco: senza
    questo passaggio pixel completamente trasparenti (alpha=0) risulterebbero
    neri, spostando drasticamente il pHash rispetto agli sprite di riferimento
    indicizzati in `sprite_hashes` (che sono PNG con sfondo trasparente).
    """
    normalized = _flatten_alpha(image)
    return str(imagehash.phash(normalized))


def compute_icon_phash(image: Image.Image) -> str:
    """Hash a 64 bit pensato per le mini icone del menu Pokemon.

    Il background dei menu FRLG è un pattern teal a strisce (né uniforme né
    trasparente): senza pre-processing contamina qualunque hash. La pipeline
    qui rimuove il bg via color-key HSV **prima** dello hash, così le icone
    di riferimento (fondo trasparente → bianco) e le capture in-game si
    riducono entrambe al pokemon-only su bianco.

    Pipeline:
    1. Componi alpha su bianco (`_flatten_alpha`).
    2. Rimuovi pixel con hue nella fascia teal (bassa saturazione + luminosità
       media) sostituendoli con bianco (`_strip_teal_background`).
    3. Pad-to-square + resize 32×32 LANCZOS.
    4. `pHash` (DCT-based, più stabile del dhash per silhouette pulite).
    """
    normalized = _flatten_alpha(image)
    stripped = _strip_teal_background(normalized)
    square = _pad_to_square(stripped, background=(255, 255, 255))
    resized = square.resize((32, 32), Image.Resampling.LANCZOS)
    return str(imagehash.phash(resized))


def _pad_to_square(image: Image.Image, background: tuple[int, int, int]) -> Image.Image:
    """Ritorna l'immagine paddata a quadrato con il colore di sfondo dato."""
    width, height = image.size
    if width == height:
        return image
    side = max(width, height)
    canvas = Image.new("RGB", (side, side), background)
    canvas.paste(image, ((side - width) // 2, (side - height) // 2))
    return canvas


# Fascia hue del bg teal del menu FRLG (in unità Hue 0..1 di colorsys):
# teal puro ≈ 0.50 (180°); i pixel del pattern variano ~0.42..0.55.
_TEAL_HUE_MIN = 0.42
_TEAL_HUE_MAX = 0.60
# I pixel del pokemon hanno alta saturazione (>0.4) o luminosità estrema
# (bianchi/neri) — vengono preservati. I pixel del bg teal hanno saturazione
# media-bassa (0.15..0.55) e luminosità 0.25..0.55.
_BG_MAX_SATURATION = 0.75


def _strip_teal_background(image: Image.Image) -> Image.Image:
    """Sostituisce con bianco i pixel classificati come background teal.

    Un pixel è "bg" quando ha hue nella fascia teal e saturazione non alta
    (i colori vivaci dei pokemon superano `_BG_MAX_SATURATION` nella zona
    teal, quindi non vengono uccisi). Le icone di riferimento su fondo bianco
    non contengono pixel teal, quindi rimangono invariate.
    """
    rgb = image.convert("RGB")
    pixels = rgb.load()
    width, height = rgb.size
    for y in range(height):
        for x in range(width):
            r, g, b = pixels[x, y]
            h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
            if _TEAL_HUE_MIN <= h <= _TEAL_HUE_MAX and s <= _BG_MAX_SATURATION:
                pixels[x, y] = (255, 255, 255)
    return rgb


def _flatten_alpha(image: Image.Image) -> Image.Image:
    """Compone `image` su un fondo bianco se ha alpha; restituisce RGB."""
    if image.mode == "RGB":
        return image
    if image.mode in ("RGBA", "LA") or "transparency" in image.info:
        rgba = image.convert("RGBA")
        background = Image.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.split()[-1])
        return background
    return image.convert("RGB")
