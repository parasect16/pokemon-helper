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
