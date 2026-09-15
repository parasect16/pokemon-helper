"""Misura del chrome in cima alla finestra dell'emulatore.

`windows-capture` restituisce l'intera finestra, non la sola client area:
sopra il gioco ci sono la barra del titolo di Windows e la barra dei menu di
mGBA. `GameLayout.menu_offset_top` dice quanto vale quella fascia, ed era un
numero fisso (52 px) misurato a mano sulla macchina di sviluppo — Win10 Pro a
DPI 100%. Su Win11, o a DPI diversa, la barra del titolo cambia altezza e ogni
ROI finisce fuori posto senza che nulla lo segnali.

Qui la fascia viene misurata sul frame stesso. Il criterio è che il chrome è
**grigio**: barra del titolo e barra dei menu sono superfici di sistema, quindi
righe in cui i tre canali coincidono quasi ovunque e la luminosità è alta. Le
schermate del gioco no — cielo, erba, teal del menu Pokemon, blu dei dialoghi
sono tutte sature. Si scende dall'alto finché le righe restano grigie e chiare,
e la prima che non lo è segna l'inizio del gioco.

La fascia non parte dalla riga 0: il frame comincia con il bordo della
finestra, che è scuro. Le prime righe non grigie sono quindi tollerate, entro
`MAX_LEADING_BORDER`, e contate comunque come chrome — quel che serve è dove
il gioco *comincia*, non dove comincia la barra del titolo.

Limiti noti, entrambi risolti ripiegando sul valore dichiarato nel layout:

- **Tema scuro**: con una barra del titolo quasi nera il vincolo di luminosità
  non passa e la misura fallisce. È voluto: il nero è anche il colore delle
  bande di letterbox che mGBA disegna sopra e sotto il gioco quando la finestra
  è più alta del necessario, e accettarlo significherebbe scambiare le bande
  per chrome e spostare l'area di gioco.
- **Frame quasi bianco**: durante le transizioni di combattimento lo schermo
  lampeggia. Una schermata tutta chiara verrebbe letta come chrome infinito,
  quindi una fascia più alta di `MAX_CHROME_HEIGHT` viene rifiutata.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np
from PIL import Image

from pokemon_helper.vision.roi import GameLayout

# Una finestra ha sempre almeno una barra del titolo: sotto questa soglia la
# misura è un artefatto (es. una riga nera di bordo).
MIN_CHROME_HEIGHT = 16
# Titolo + menu bar valgono ~52 px a DPI 100% e crescono con la scala; oltre
# questo si sta misurando qualcos'altro (uno schermo bianco, tipicamente).
MAX_CHROME_HEIGHT = 120
# Distanza massima fra canale più alto e più basso perché un pixel sia grigio.
# Le superfici di sistema non sono perfettamente neutre (l'accento colora
# leggermente alcuni temi), quindi la soglia non è a zero — ma resta stretta:
# la prima riga del campo di battaglia FRLG è un verde pallidissimo
# `(231, 255, 231)`, distanza 24, e con una soglia più larga passerebbe per
# chrome portandosi dietro tutta la fascia di cielo sopra il campo.
MAX_CHANNEL_SPREAD = 12
# Luminosità minima: esclude le bande nere di letterbox, che sarebbero grigie
# a tutti gli effetti.
MIN_BRIGHTNESS = 100
# Frazione di pixel grigi perché la riga conti come chrome. Non è 1.0 perché
# il testo del titolo e le voci di menu sono pixel scuri in mezzo al grigio.
MIN_NEUTRAL_FRACTION = 0.8
# Frazione di larghezza ignorata sui due lati: bordi della finestra e angoli
# arrotondati di Win11, che nel frame arrivano trasparenti e quindi neri.
SIDE_MARGIN_FRACTION = 0.1
# Righe non grigie tollerate prima dell'inizio del chrome. Il frame di Windows
# Graphics Capture comincia con il bordo della finestra: sulla macchina di
# sviluppo è una riga scura `(43, 43, 43)`, e pretendere il grigio già dalla
# riga 0 faceva fallire la misura su ogni cattura reale.
MAX_LEADING_BORDER = 4

# Valori già segnalati, per non ripetere la riga di log a ogni poll (due volte
# al secondo con l'auto-detect acceso).
_logged: set[tuple[int, int]] = set()


def detect_chrome_height(image: Image.Image) -> int | None:
    """Altezza in pixel della fascia di chrome in cima al frame.

    Ritorna `None` quando la misura non è attendibile: nessuna riga grigia in
    cima, fascia troppo sottile o troppo alta. Il chiamante ripiega sul valore
    dichiarato nel layout.
    """
    arr = np.asarray(image.convert("RGB"))
    height, width = arr.shape[:2]
    limit = min(MAX_CHROME_HEIGHT + 1, height)
    if limit <= MIN_CHROME_HEIGHT:
        return None

    margin = int(width * SIDE_MARGIN_FRACTION)
    band = arr[:limit, margin : width - margin].astype(np.int16)
    if band.shape[1] == 0:
        return None

    spread = band.max(axis=2) - band.min(axis=2)
    brightness = band.mean(axis=2)
    neutral = (spread <= MAX_CHANNEL_SPREAD) & (brightness >= MIN_BRIGHTNESS)
    is_chrome = neutral.mean(axis=1) >= MIN_NEUTRAL_FRACTION

    if not is_chrome.any():
        return None
    # `argmax` trova il primo `True`: l'inizio della barra del titolo, appena
    # sotto il bordo della finestra.
    start = int(np.argmax(is_chrome))
    if start > MAX_LEADING_BORDER:
        # Troppe righe non grigie in cima: non è un bordo, non stiamo
        # guardando una finestra con chrome.
        return None

    rest = is_chrome[start:]
    if rest.all():
        # Chrome fin dove abbiamo guardato: o è uno schermo tutto chiaro, o
        # non è una finestra emulatore. In entrambi i casi non si misura.
        return None

    # `argmin` trova il primo `False`, cioè la prima riga già del gioco. Il
    # bordo iniziale fa parte del chrome quanto la barra del titolo, quindi
    # l'offset è assoluto e non relativo a `start`.
    detected = start + int(np.argmin(rest))
    if detected < MIN_CHROME_HEIGHT:
        return None
    return detected


def resolve_layout(image: Image.Image, layout: GameLayout) -> GameLayout:
    """Layout con `menu_offset_top` misurato sul frame, se possibile.

    Ritorna il layout invariato quando la misura fallisce o coincide con il
    valore dichiarato, così i chiamanti possono usarla sempre.
    """
    detected = detect_chrome_height(image)
    if detected is None or detected == layout.menu_offset_top:
        return layout
    key = (layout.menu_offset_top, detected)
    if key not in _logged:
        _logged.add(key)
        print(
            f"[chrome] offset misurato {detected} px invece dei {layout.menu_offset_top} dichiarati"
        )
    return replace(layout, menu_offset_top=detected)
