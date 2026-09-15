"""Cosa si legge dentro un rettangolo: la verifica che chiude la calibrazione.

Un rettangolo si giudica da quello che ci si legge dentro, non da come appare
sul frame. Entrambi i bug di calibrazione di questo repo erano invisibili a
occhio: `opponent_name` tagliato a metà sembrava a posto e leggeva la barra
PS (`AECFAT"S..`), `player_hp_bar` sembrava sulla barra e stava sui numeri.
Un'occhiata all'OCR li avrebbe smascherati subito.

`describe_crop` è la riga che il calibratore mostra sotto l'anteprima. Cambia
per tipo di bersaglio, perché cambia cosa deve esserci dentro:

- la barra PS dell'avversario non contiene testo ma colore, e il numero che
  conta è quanti pixel di colore-HP ci cadono dentro — è il segnale con cui
  `screen_mode` decide se siamo in combattimento;
- i riquadri del livello passano dal lettore cifra per cifra, lo stesso che
  usa il riconoscimento vero, quindi la riga dice il livello e non il testo
  grezzo;
- tutto il resto è testo, e la riga riporta quello che l'OCR ne ha tirato
  fuori con la sua confidenza.

Vive in `vision` e non in `ui` perché tira dentro numpy e i modelli ONNX: il
dialogo lo riceve come funzione iniettata e resta importabile senza.
"""

from __future__ import annotations

import numpy as np
from PIL import Image

from pokemon_helper.vision.level_reader import read_level
from pokemon_helper.vision.ocr import OcrEngine
from pokemon_helper.vision.screen_mode import MIN_HP_PIXELS, count_hp_bar_pixels

# Prefisso delle chiavi dei riquadri livello, che si leggono cifra per cifra.
_LEVEL_KEY_PREFIX = "team_menu.slot_levels."
# Chiave della barra PS avversario, l'unico bersaglio che non contiene testo.
_HP_BAR_KEY = "opponent_hp_bar"


def describe_crop(crop: Image.Image, key: str, ocr: OcrEngine) -> str:
    """Una riga in italiano su cosa contiene il ritaglio."""
    if key == _HP_BAR_KEY:
        return _describe_hp_bar(crop)
    if key.startswith(_LEVEL_KEY_PREFIX):
        return _describe_level(crop, ocr)
    return _describe_text(crop, ocr)


def make_reader(ocr: OcrEngine):
    """Lega un `OcrEngine` a `describe_crop`, per passarlo al calibratore."""

    def reader(crop: Image.Image, key: str) -> str:
        return describe_crop(crop, key, ocr)

    return reader


def _describe_hp_bar(crop: Image.Image) -> str:
    """Quanti pixel colore-HP cadono nel rettangolo, e se bastano.

    La soglia è la stessa che usa `screen_mode`: sotto, la schermata non viene
    riconosciuta come combattimento e il riconoscimento dell'avversario non
    parte nemmeno.
    """
    count = count_hp_bar_pixels(np.asarray(crop.convert("RGB")))
    if count >= MIN_HP_PIXELS:
        return f"pixel colore-PS: {count} (sufficienti)"
    return f"pixel colore-PS: {count} (troppo pochi, ne servono {MIN_HP_PIXELS})"


def _describe_level(crop: Image.Image, ocr: OcrEngine) -> str:
    """Il livello letto cifra per cifra, come lo leggerà il riconoscimento."""
    level = read_level(crop, ocr)
    if level is None:
        return "livello non riconosciuto (o il Pokemon ha un'alterazione di stato)"
    return f"livello letto: {level}"


def _describe_text(crop: Image.Image, ocr: OcrEngine) -> str:
    """Il testo che l'OCR estrae dal ritaglio, con la confidenza."""
    results = ocr.recognize(crop)
    if not results:
        return "nessun testo letto"
    best = max(results, key=lambda result: result.confidence)
    extra = f" (+{len(results) - 1} altre righe)" if len(results) > 1 else ""
    return f'testo: "{best.text}" a {best.confidence:.2f}{extra}'
