"""Classificazione della schermata mostrata dall'emulatore.

Porta d'ingresso unica: `classify_screen`, che guarda un frame e dice se è
la schermata di combattimento, l'elenco Pokemon, o nessuna delle due. Prima
questa domanda era sparsa fra due funzioni indipendenti e un'euristica a
posteriori in `ui.app`, e ogni chiamante ricomponeva il verdetto a modo suo.

I segnali usati, in ordine di costo:

1. **Barra HP avversario** (colore, ~1 ms). Sulla schermata di battaglia la
   ROI contiene pixel saturi verdi/gialli/rossi. Su qualunque altra
   schermata contiene sfondo di tutt'altro tipo — sabbia, erba, teal del
   menu, blu del box dialogo.
2. **Sfondo teal** (colore, ~2 ms). Lo sfondo dell'elenco Pokemon è un
   motivo teal che copre quasi metà schermo, colore che nelle schermate di
   gioco non compare quasi mai: misurato 47% dei pixel nel menu contro 0.1%
   in combattimento.
3. **Sentinella `ESCI`** (OCR, ~8 ms). Il pulsante in basso a destra
   dell'elenco Pokemon. È l'unico segnale che guarda *cosa c'è scritto*
   invece del colore, ed è quello che distingue l'elenco Pokemon da una
   qualunque altra schermata a fondo teal. Letto solo se gli serve un
   `OcrEngine`: i chiamanti che non possono permetterselo (il poll di F4,
   due volte al secondo) lo omettono e si fermano al colore.

Nessun modello ML, nessun template: conteggi di pixel per canale più una
singola riga OCR su un rettangolo di 150x56 px.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from enum import Enum
from typing import TYPE_CHECKING

import numpy as np
from PIL import Image

from pokemon_helper.vision.roi import (
    GameLayout,
    GameRois,
    PixelRect,
    compute_game_area,
    roi_to_pixels,
)

if TYPE_CHECKING:
    from pokemon_helper.vision.ocr import OcrEngine

# Numero minimo di pixel "colore HP" nel crop della barra HP avversario per
# considerare valida la schermata di battaglia. Una barra HP piena copre
# ~200-300 px del crop tipico; una ROI leggermente disallineata ne mostra
# comunque decine. 20 lascia margine per casi con HP quasi vuoto (barra
# rossa corta) o ROI un po' spostata rispetto alla calibrazione.
MIN_HP_PIXELS = 20

# Frazione di pixel teal oltre la quale il frame è la schermata elenco Pokemon.
# Misurato: 47% sul menu, 0.1% in combattimento.
MIN_TEAL_FRACTION = 0.20

# Testo atteso nel pulsante in basso a destra dell'elenco Pokemon (FRLG
# italiano). Vale sia fuori dal combattimento sia con l'elenco aperto a metà
# lotta per cambiare Pokemon: verificato in gioco, l'etichetta non cambia.
PARTY_MENU_SENTINEL_LABELS = ("ESCI",)

# Soglia di similarità per accettare la lettura della sentinella. L'OCR legge
# "ESCI" con confidenza 0.98 su cattura live, ma è un font pixel scalato a
# fattore non intero: 0.6 assorbe un carattere sbagliato su quattro senza
# avvicinarsi al rumore che esce dalle altre schermate ("IGA" sul frame di
# battaglia, ratio 0.29).
MIN_SENTINEL_SIMILARITY = 0.6


class ScreenMode(Enum):
    """Schermata riconosciuta in un frame dell'emulatore."""

    # Combattimento in corso: l'HUD dell'avversario è a schermo.
    BATTLE = "battle"
    # Elenco dei sei Pokemon in squadra (dal menu o aperto durante la lotta).
    PARTY_MENU = "party_menu"
    # Tutto il resto: overworld, dialoghi, schermata titolo, transizioni.
    OTHER = "other"

    @property
    def label(self) -> str:
        """Descrizione in italiano, per i messaggi mostrati all'utente."""
        return _SCREEN_LABELS[self]


_SCREEN_LABELS = {
    ScreenMode.BATTLE: "combattimento in corso",
    ScreenMode.PARTY_MENU: "elenco Pokemon aperto",
    ScreenMode.OTHER: "schermata non riconosciuta",
}


@dataclass(frozen=True, slots=True)
class ScreenVerdict:
    """Esito della classificazione, con la motivazione per il tooltip."""

    mode: ScreenMode
    # Vuota quando il verdetto è positivo; altrimenti descrive quali segnali
    # sono mancati, nella forma usata dai messaggi di errore della UI. Un
    # chiamante che attendeva un'altra schermata e trova la stringa vuota usa
    # `mode.label` al suo posto: il verdetto è positivo, ma non per lui.
    reason: str = ""


def classify_screen(
    frame: Image.Image,
    layout: GameLayout,
    rois: GameRois,
    *,
    ocr: OcrEngine | None = None,
) -> ScreenVerdict:
    """Classifica il frame come battaglia, elenco Pokemon o altro.

    `ocr` abilita la sentinella testuale sul pulsante `ESCI`. Senza, un frame
    a fondo teal viene dato per elenco Pokemon sul solo colore — che è quello
    che serve al poll di F4, dove il costo di un'OCR ogni 750 ms non si
    giustifica e un falso positivo costa solo un giro di "non lo so".

    La battaglia viene controllata per prima: è il caso comune, ed è il
    segnale che costa meno.
    """
    game_area = compute_game_area(frame.width, frame.height, layout)

    hp_pixels = _count_hp_bar_pixels(
        np.asarray(
            frame.crop(roi_to_pixels(rois.opponent_hp_bar, game_area).as_crop_box()).convert("RGB")
        )
    )
    if hp_pixels >= MIN_HP_PIXELS:
        return ScreenVerdict(ScreenMode.BATTLE)

    teal = _teal_fraction(
        np.asarray(
            frame.crop(
                (game_area.x, game_area.y, game_area.x + game_area.w, game_area.y + game_area.h)
            ).convert("RGB")
        )
    )
    if teal < MIN_TEAL_FRACTION:
        return ScreenVerdict(
            ScreenMode.OTHER,
            f"({hp_pixels} px barra HP avversario, {teal:.0%} di sfondo teal)",
        )

    if ocr is None:
        return ScreenVerdict(ScreenMode.PARTY_MENU)

    sentinel = _read_sentinel(frame, game_area, rois, ocr)
    if _sentinel_matches(sentinel):
        return ScreenVerdict(ScreenMode.PARTY_MENU)
    return ScreenVerdict(
        ScreenMode.OTHER,
        f"(sfondo teal ma nessun pulsante {PARTY_MENU_SENTINEL_LABELS[0]}: letto {sentinel!r})",
    )


def _read_sentinel(frame: Image.Image, game_area: PixelRect, rois: GameRois, ocr: OcrEngine) -> str:
    """Legge il pulsante sentinella dell'elenco Pokemon.

    Ritorna la riga di testo con la confidenza più alta, o stringa vuota se
    l'OCR non ha prodotto nulla — che è già di per sé un verdetto negativo.
    """
    crop = frame.crop(roi_to_pixels(rois.party_menu_sentinel, game_area).as_crop_box())
    results = ocr.recognize(crop)
    if not results:
        return ""
    return max(results, key=lambda result: result.confidence).text


def _sentinel_matches(text: str) -> bool:
    """Vero se `text` è una delle etichette attese, a meno di errori OCR."""
    needle = text.strip().upper()
    if not needle:
        return False
    return any(
        SequenceMatcher(None, needle, label).ratio() >= MIN_SENTINEL_SIMILARITY
        for label in PARTY_MENU_SENTINEL_LABELS
    )


def _teal_fraction(arr: np.ndarray) -> float:
    """Frazione di pixel col teal di sfondo del menu Pokemon.

    Teal = verde e blu entrambi alti e vicini fra loro, rosso nettamente più
    basso di entrambi. Il vincolo sul rosso è ciò che esclude l'erba
    dell'overworld, verde ma non povera di rosso.
    """
    r = arr[..., 0].astype(int)
    g = arr[..., 1].astype(int)
    b = arr[..., 2].astype(int)
    teal = (g > 90) & (b > 90) & (abs(g - b) < 60) & (r < g - 50) & (r < b - 40)
    return float(teal.mean())


def _count_hp_bar_pixels(arr: np.ndarray) -> int:
    """Conta i pixel dell'array RGB che matchano i colori della barra HP.

    La barra HP FRLG usa 3 stati:
    - verde brillante (HP > 50%): tipico ``(0-100, 200-255, 50-150)``
    - giallo (HP 20-50%): ``(200-255, 200-255, 0-100)``
    - rosso (HP < 20%): ``(200-255, 0-100, 0-100)``

    Le soglie sono asimmetriche per canale e generose sul range basso perché
    l'anti-aliasing dei pixel di bordo ammorbidisce leggermente i valori.
    """
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    green = (g >= 180) & (r <= 130) & (b <= 160)
    yellow = (r >= 200) & (g >= 180) & (b <= 120)
    red = (r >= 180) & (g <= 100) & (b <= 100)
    return int((green | yellow | red).sum())
