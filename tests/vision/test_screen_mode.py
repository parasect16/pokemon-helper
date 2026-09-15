"""Test di `classify_screen`, la porta d'ingresso della classificazione.

Costruiamo frame sintetici riempiendo le ROI di colori noti — la barra HP
avversario coi colori HP, l'area gioco col teal del menu Pokemon — e
verifichiamo che il verdetto sia quello atteso. La sentinella testuale usa
un finto `OcrEngine` che ritorna la stringa che vogliamo: qui interessa la
politica di decisione, non la qualità del riconoscimento OCR.
"""

from __future__ import annotations

import numpy as np
from PIL import Image

from pokemon_helper.vision.ocr import OcrResult
from pokemon_helper.vision.roi import GAME_ROIS, compute_game_area, roi_to_pixels
from pokemon_helper.vision.screen_mode import (
    MIN_HP_PIXELS,
    ScreenMode,
    classify_screen,
)

LAYOUT, ROIS = GAME_ROIS["firered"]

# Grigio neutro: né HP-colored né teal. Sfondo di partenza dei casi negativi.
_NEUTRAL = (180, 180, 180)
# Teal dello sfondo dell'elenco Pokemon.
_TEAL = (32, 152, 152)


class _FakeOcr:
    """`OcrEngine` finto: ritorna sempre la stessa riga di testo."""

    def __init__(self, text: str, confidence: float = 0.98) -> None:
        self._results = [OcrResult(text=text, confidence=confidence)] if text else []

    def recognize(self, image, **_kwargs) -> list[OcrResult]:  # noqa: ANN001, ARG002
        return self._results


def _blank_frame(color: tuple[int, int, int] = _TEAL) -> Image.Image:
    """Frame 1100x717 riempito di un colore unico.

    Corrisponde a un capture client-area di mGBA FRLG a scala tipica.
    """
    arr = np.full((717, 1100, 3), color, dtype=np.uint8)
    return Image.fromarray(arr, mode="RGB")


def _paint_roi(frame: Image.Image, roi, color: tuple[int, int, int]) -> Image.Image:
    """Riempi una ROI del colore fornito, su una copia del frame."""
    arr = np.array(frame)
    game_area = compute_game_area(frame.width, frame.height, LAYOUT)
    px = roi_to_pixels(roi, game_area)
    arr[px.y : px.y + px.h, px.x : px.x + px.w] = color
    return Image.fromarray(arr, mode="RGB")


def _party_menu_frame() -> Image.Image:
    """Frame con l'area gioco tutta teal: l'elenco Pokemon visto dal colore."""
    frame = _blank_frame(_NEUTRAL)
    game_area = compute_game_area(frame.width, frame.height, LAYOUT)
    teal = Image.new("RGB", (game_area.w, game_area.h), _TEAL)
    frame.paste(teal, (game_area.x, game_area.y))
    return frame


# ---------------------------------------------------------------------------
# Battaglia
# ---------------------------------------------------------------------------


def test_green_hp_bar_is_a_battle() -> None:
    """HP bar dipinta di verde brillante → battaglia."""
    frame = _paint_roi(_blank_frame(), ROIS.opponent_hp_bar, (50, 220, 100))
    verdict = classify_screen(frame, LAYOUT, ROIS)
    assert verdict.mode is ScreenMode.BATTLE
    assert verdict.reason == ""


def test_yellow_hp_bar_is_a_battle() -> None:
    """HP bar giallo (HP 20-50%) → battaglia."""
    frame = _paint_roi(_blank_frame(), ROIS.opponent_hp_bar, (240, 220, 40))
    assert classify_screen(frame, LAYOUT, ROIS).mode is ScreenMode.BATTLE


def test_red_hp_bar_is_a_battle() -> None:
    """HP bar rosso (HP < 20%) → battaglia."""
    frame = _paint_roi(_blank_frame(), ROIS.opponent_hp_bar, (220, 40, 40))
    assert classify_screen(frame, LAYOUT, ROIS).mode is ScreenMode.BATTLE


def test_the_battle_check_wins_over_the_teal_background() -> None:
    """Una barra HP su fondo teal resta battaglia: il colore HP ha priorità."""
    frame = _paint_roi(_party_menu_frame(), ROIS.opponent_hp_bar, (50, 220, 100))
    assert classify_screen(frame, LAYOUT, ROIS).mode is ScreenMode.BATTLE


def test_dialog_blue_is_not_hp_coloured() -> None:
    """Blu del menu dialogo (~(100, 130, 210)) NON è HP-colored."""
    frame = _paint_roi(_blank_frame(_NEUTRAL), ROIS.opponent_hp_bar, (100, 130, 210))
    verdict = classify_screen(frame, LAYOUT, ROIS)
    assert verdict.mode is ScreenMode.OTHER
    assert "0 px" in verdict.reason


def test_overworld_grass_is_not_hp_coloured() -> None:
    """Verde erba overworld (~(80, 160, 80)) sotto la soglia G>=180 → non HP."""
    frame = _paint_roi(_blank_frame(_NEUTRAL), ROIS.opponent_hp_bar, (80, 160, 80))
    assert classify_screen(frame, LAYOUT, ROIS).mode is ScreenMode.OTHER


def test_hp_pixel_threshold_boundary() -> None:
    """Sotto `MIN_HP_PIXELS` non è battaglia; esattamente a soglia sì."""
    frame = _blank_frame(_NEUTRAL)
    arr = np.array(frame)
    game_area = compute_game_area(frame.width, frame.height, LAYOUT)
    px = roi_to_pixels(ROIS.opponent_hp_bar, game_area)
    for i in range(MIN_HP_PIXELS - 1):
        arr[px.y, px.x + i] = (50, 220, 100)
    below = Image.fromarray(arr, mode="RGB")
    assert classify_screen(below, LAYOUT, ROIS).mode is ScreenMode.OTHER

    arr[px.y, px.x + MIN_HP_PIXELS - 1] = (50, 220, 100)
    at_threshold = Image.fromarray(arr, mode="RGB")
    assert classify_screen(at_threshold, LAYOUT, ROIS).mode is ScreenMode.BATTLE


# ---------------------------------------------------------------------------
# Elenco Pokemon
# ---------------------------------------------------------------------------


def test_teal_background_alone_is_enough_without_an_ocr() -> None:
    """Senza `ocr` il verdetto si ferma al colore: è il percorso del poll F4."""
    verdict = classify_screen(_party_menu_frame(), LAYOUT, ROIS)
    assert verdict.mode is ScreenMode.PARTY_MENU
    assert verdict.reason == ""


def test_battle_background_is_not_a_party_menu() -> None:
    """Erba e cielo sono verdi e azzurri, ma non poveri di rosso come il teal."""
    frame = _blank_frame(_NEUTRAL)
    game_area = compute_game_area(frame.width, frame.height, LAYOUT)
    grass = Image.new("RGB", (game_area.w, game_area.h), (168, 216, 168))
    frame.paste(grass, (game_area.x, game_area.y))
    assert classify_screen(frame, LAYOUT, ROIS).mode is ScreenMode.OTHER


def test_a_teal_patch_below_the_threshold_is_not_a_party_menu() -> None:
    """Un elemento teal isolato non basta: deve coprire buona parte dello schermo."""
    frame = _blank_frame(_NEUTRAL)
    game_area = compute_game_area(frame.width, frame.height, LAYOUT)
    patch = Image.new("RGB", (game_area.w // 10, game_area.h // 2), _TEAL)
    frame.paste(patch, (game_area.x, game_area.y))
    verdict = classify_screen(frame, LAYOUT, ROIS)
    assert verdict.mode is ScreenMode.OTHER
    assert "teal" in verdict.reason


# ---------------------------------------------------------------------------
# Sentinella "ESCI"
# ---------------------------------------------------------------------------


def test_the_sentinel_confirms_the_party_menu() -> None:
    """Fondo teal + pulsante `ESCI` letto → elenco Pokemon."""
    verdict = classify_screen(_party_menu_frame(), LAYOUT, ROIS, ocr=_FakeOcr("ESCI"))
    assert verdict.mode is ScreenMode.PARTY_MENU


def test_the_sentinel_tolerates_one_wrong_character() -> None:
    """`E5CI` viene dall'OCR sul font pixel: ratio 0.75, sopra soglia."""
    verdict = classify_screen(_party_menu_frame(), LAYOUT, ROIS, ocr=_FakeOcr("E5CI"))
    assert verdict.mode is ScreenMode.PARTY_MENU


def test_the_sentinel_ignores_case_and_padding() -> None:
    """Il confronto normalizza spazi e maiuscole prima del fuzzy."""
    verdict = classify_screen(_party_menu_frame(), LAYOUT, ROIS, ocr=_FakeOcr("  esci "))
    assert verdict.mode is ScreenMode.PARTY_MENU


def test_a_teal_screen_without_the_sentinel_is_rejected() -> None:
    """Fondo teal ma nessun `ESCI`: è un'altra schermata, non l'elenco.

    È il caso che l'euristica a posteriori sui risultati OCR non copriva —
    il motivo per cui la sentinella esiste.
    """
    verdict = classify_screen(_party_menu_frame(), LAYOUT, ROIS, ocr=_FakeOcr("IGA"))
    assert verdict.mode is ScreenMode.OTHER
    assert "ESCI" in verdict.reason
    assert "IGA" in verdict.reason


def test_an_empty_ocr_reading_is_not_a_sentinel() -> None:
    """Nessuna riga letta nel rettangolo → verdetto negativo, non un dubbio."""
    verdict = classify_screen(_party_menu_frame(), LAYOUT, ROIS, ocr=_FakeOcr(""))
    assert verdict.mode is ScreenMode.OTHER


def test_the_sentinel_reading_picks_the_most_confident_line() -> None:
    """Con più righe nel rettangolo vince quella con confidenza più alta."""

    class _MultiLineOcr:
        def recognize(self, image, **_kwargs):  # noqa: ANN001, ARG002
            return [
                OcrResult(text="PS", confidence=0.41),
                OcrResult(text="ESCI", confidence=0.97),
            ]

    verdict = classify_screen(_party_menu_frame(), LAYOUT, ROIS, ocr=_MultiLineOcr())
    assert verdict.mode is ScreenMode.PARTY_MENU


# ---------------------------------------------------------------------------
# Etichette
# ---------------------------------------------------------------------------


def test_every_mode_has_an_italian_label() -> None:
    """`ScreenMode.label` alimenta i messaggi della UI: nessun buco."""
    for mode in ScreenMode:
        assert mode.label
        assert mode.label != mode.value
