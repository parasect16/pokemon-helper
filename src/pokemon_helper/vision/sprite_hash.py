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

    Sceglie `dhash` invece di `phash`: la difference-hash misura variazioni
    fra pixel adiacenti (edge structure) invece della componente DCT globale,
    e per icone piccole con leggere variazioni di background/animazione dà
    match più affidabili nei nostri test.

    Pipeline:
    1. Componi eventuale alpha su sfondo bianco.
    2. Pad-to-square (bordo bianco) per rispettare l'aspect ratio.
    3. Resize a 32×32 con LANCZOS.
    4. `dhash` (implementato da imagehash) su questa base.

    Le icone di riferimento (~32×32 quadrate) e i crop catturati dal menu
    (~75×88 in FireRed) vengono così normalizzati alla stessa forma prima
    del hashing.
    """
    normalized = _flatten_alpha(image)
    square = _pad_to_square(normalized, background=(255, 255, 255))
    resized = square.resize((32, 32), Image.Resampling.LANCZOS)
    return str(imagehash.dhash(resized))


def _pad_to_square(image: Image.Image, background: tuple[int, int, int]) -> Image.Image:
    """Ritorna l'immagine paddata a quadrato con il colore di sfondo dato."""
    width, height = image.size
    if width == height:
        return image
    side = max(width, height)
    canvas = Image.new("RGB", (side, side), background)
    canvas.paste(image, ((side - width) // 2, (side - height) // 2))
    return canvas


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
