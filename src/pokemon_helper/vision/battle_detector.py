"""Heuristiche per classificare un frame FRLG a colpo d'occhio.

Approccio: ispeziona la ROI della barra HP dell'avversario. Sulla schermata
di battaglia questa ROI contiene pixel saturi verdi/gialli/rossi (i colori
della barra HP). Su qualunque altra schermata (mondo overworld, menu
Pokemon, dialogo NPC, schermata titolo) la stessa area contiene sfondo di
tutt'altro tipo — sabbia/erba/teal menu/blu dialogo.

Non richiede né modelli ML né template: contamento di pixel per canale con
soglie sature. Il costo è trascurabile (~1 ms su un crop di 300x8 px).
"""

from __future__ import annotations

import numpy as np
from PIL import Image

from pokemon_helper.vision.roi import GameLayout, GameRois, compute_game_area, roi_to_pixels

# Numero minimo di pixel "colore HP" nel crop della barra HP avversario per
# considerare valida la schermata di battaglia. Una barra HP piena copre
# ~200-300 px del crop tipico; una ROI leggermente disallineata ne mostra
# comunque decine. 20 lascia margine per casi con HP quasi vuoto (barra
# rossa corta) o ROI un po' spostata rispetto alla calibrazione.
MIN_HP_PIXELS = 20

# Frazione di pixel teal oltre la quale il frame è la schermata elenco Pokemon.
# Misurato: 47% sul menu, 0.1% in combattimento.
MIN_TEAL_FRACTION = 0.20


def is_battle_screen(frame: Image.Image, layout: GameLayout, rois: GameRois) -> tuple[bool, str]:
    """Ritorna `(True, "")` se il frame sembra la schermata di combattimento.

    Altrimenti `(False, reason)` con motivazione da mostrare in tooltip.
    Il check si basa esclusivamente sui colori della ROI `opponent_hp_bar`.
    """
    game_area = compute_game_area(frame.width, frame.height, layout)
    hp_crop = frame.crop(roi_to_pixels(rois.opponent_hp_bar, game_area).as_crop_box())
    hp_pixels = _count_hp_bar_pixels(np.asarray(hp_crop.convert("RGB")))
    if hp_pixels < MIN_HP_PIXELS:
        return False, f"({hp_pixels} px barra HP avversario rilevati)"
    return True, ""


def is_party_menu_screen(frame: Image.Image, layout: GameLayout) -> bool:
    """Vero se il frame è la schermata elenco Pokemon.

    Serve a distinguerla da "combattimento finito": aprire l'elenco durante
    una lotta è un'azione normale — è così che si cambia Pokemon — ma la
    barra HP avversaria sparisce, quindi `is_battle_screen` direbbe di no e
    il pannello si svuoterebbe a metà combattimento.

    Il riconoscimento è per colore: lo sfondo del menu è un motivo teal che
    copre quasi metà schermo, colore che nelle schermate di gioco non compare
    quasi mai. Misurato su cattura live: 47% dei pixel nel menu contro 0.1%
    in combattimento, quindi la soglia sta larghissima in mezzo.
    """
    game_area = compute_game_area(frame.width, frame.height, layout)
    crop = frame.crop(
        (game_area.x, game_area.y, game_area.x + game_area.w, game_area.y + game_area.h)
    )
    return _teal_fraction(np.asarray(crop.convert("RGB"))) >= MIN_TEAL_FRACTION


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
