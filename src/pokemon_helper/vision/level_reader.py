"""Lettura del livello (`L.XX`) dai font pixel dell'emulatore.

Passare l'intero riquadro del livello a RapidOCR non funziona: mGBA scala il
gioco 240×160 dentro una finestra qualsiasi (oggi 1023×682, cioè 4.26x, non
un multiplo intero), quindi ogni pixel del font diventa 4 o 5 pixel schermo e
i bordi si fondono in grigio. Su una stringa di due cifre il modello tira a
indovinare: sullo stesso identico crop ha prodotto `28`, `L.30` e `38` al
variare di pochi pixel di ROI.

La lettura qui è in tre passi:

1. **binarizza** il crop scegliendo la polarità in base a quale classe è in
   minoranza — il testo è sempre meno esteso dello sfondo, sia bianco su blu
   (righe della lista) sia scuro su chiaro (slot attivo);
2. **segmenta per colonne** di inchiostro contigue: il font è a larghezza
   fissa e le cifre non si toccano mai, quindi i gruppi coincidono con le
   cifre (verificato su tutti e 6 gli slot, colonne sempre alle stesse
   coordinate);
3. **riconosce una cifra alla volta**, ingrandita e con un margine bianco
   attorno. Il margine è la parte che conta: senza, le stesse cifre uscivano
   con confidenza 0.26-0.55 e valori sbagliati; con, tutte a 1.00.

Un Pokemon con alterazione di stato (veleno, paralisi, ...) non mostra il
livello: il gioco disegna il badge di stato al suo posto. In quel caso la
segmentazione trova le lettere del badge, nessuna cifra viene riconosciuta e
la funzione ritorna `None`, che il chiamante tratta come "livello ignoto".
"""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageOps

from pokemon_helper.vision.ocr import OcrEngine

# Un gruppo di colonne più stretto di così è rumore, non una cifra.
_MIN_DIGIT_COLUMNS = 3
# Ingrandimento e margine applicati alla singola cifra prima dell'OCR.
_DIGIT_UPSCALE = 16
_DIGIT_PADDING = 4
# Un livello valido nei giochi Gen 1-5.
_MIN_LEVEL, _MAX_LEVEL = 1, 100


def read_level(image: Image.Image, ocr: OcrEngine) -> int | None:
    """Legge il livello dal ritaglio della ROI livello.

    Ritorna `None` se non si riconoscono cifre (slot vuoto, badge di stato al
    posto del livello, ROI disallineata) o se il numero è fuori da 1-100.
    """
    binary = _binarize(image)
    digits = []
    for left, right in _segment_columns(binary):
        text = _read_digit(binary.crop((left, 0, right, binary.height)), ocr)
        if text is None:
            return None
        digits.append(text)
    if not digits:
        return None
    level = int("".join(digits))
    return level if _MIN_LEVEL <= level <= _MAX_LEVEL else None


def _binarize(image: Image.Image) -> Image.Image:
    """Porta il crop a nero-su-bianco, qualunque sia la polarità originale.

    La soglia divide in due classi; teniamo come inchiostro quella meno
    numerosa, perché il testo copre sempre meno area dello sfondo.
    """
    gray = np.asarray(ImageOps.autocontrast(image.convert("L")))
    bright = gray > 160
    # `bright` come inchiostro se il chiaro è minoranza, altrimenti il suo negato.
    ink = bright if bright.mean() <= 0.5 else ~bright
    return Image.fromarray(np.where(ink, 0, 255).astype(np.uint8))


def _segment_columns(binary: Image.Image) -> list[tuple[int, int]]:
    """Trova i gruppi di colonne contigue che contengono inchiostro.

    Ritorna coppie `(inizio, fine)` in coordinate colonna, una per cifra.
    """
    has_ink = (np.asarray(binary) < 128).any(axis=0)
    groups: list[tuple[int, int]] = []
    start: int | None = None
    for column, inked in enumerate(has_ink):
        if inked and start is None:
            start = column
        elif not inked and start is not None:
            if column - start >= _MIN_DIGIT_COLUMNS:
                groups.append((start, column))
            start = None
    if start is not None and len(has_ink) - start >= _MIN_DIGIT_COLUMNS:
        groups.append((start, len(has_ink)))
    return groups


def _read_digit(cell: Image.Image, ocr: OcrEngine) -> str | None:
    """Riconosce una singola cifra, ingrandita e circondata da margine bianco."""
    scaled = cell.resize((cell.width * _DIGIT_UPSCALE, cell.height * _DIGIT_UPSCALE), Image.NEAREST)
    margin = _DIGIT_PADDING * _DIGIT_UPSCALE
    canvas = Image.new("L", (scaled.width + margin, scaled.height + margin), 255)
    canvas.paste(scaled, (margin // 2, margin // 2))

    results = ocr.recognize(canvas.convert("RGB"), detect=False)
    if not results:
        return None
    text = results[0].text.strip()
    return text if len(text) == 1 and text.isdigit() else None
