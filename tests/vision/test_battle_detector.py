"""Test dell'heuristica `is_battle_screen`.

Costruiamo frame sintetici con la ROI `opponent_hp_bar` riempita di colori
noti (HP verde/giallo/rosso vs sfondo neutro) per verificare che il detector
distingua correttamente battaglia da non-battaglia.
"""

from __future__ import annotations

import numpy as np
from PIL import Image

from pokemon_helper.vision.battle_detector import (
    MIN_HP_PIXELS,
    is_battle_screen,
)
from pokemon_helper.vision.roi import GAME_ROIS, compute_game_area, roi_to_pixels

LAYOUT, ROIS = GAME_ROIS["firered"]


def _blank_frame(color: tuple[int, int, int] = (60, 190, 200)) -> Image.Image:
    """Frame 1100x717 riempito di teal (bg tipico menu Pokemon).

    Corrisponde a un capture client-area di mGBA FRLG a scala tipica.
    Il colore di default (teal) NON è HP-colored, quindi `is_battle_screen`
    ritorna False su questo frame nudo.
    """
    arr = np.full((717, 1100, 3), color, dtype=np.uint8)
    return Image.fromarray(arr, mode="RGB")


def _paint_hp_bar(frame: Image.Image, color: tuple[int, int, int]) -> Image.Image:
    """Riempi la ROI `opponent_hp_bar` col colore fornito, in-place su una copia."""
    arr = np.array(frame)
    game_area = compute_game_area(frame.width, frame.height, LAYOUT)
    px = roi_to_pixels(ROIS.opponent_hp_bar, game_area)
    arr[px.y : px.y + px.h, px.x : px.x + px.w] = color
    return Image.fromarray(arr, mode="RGB")


def test_rejects_blank_teal_frame() -> None:
    """Frame teal (menu Pokemon senza HP) → non battaglia."""
    ok, reason = is_battle_screen(_blank_frame(), LAYOUT, ROIS)
    assert ok is False
    assert "0" in reason  # zero pixel HP rilevati


def test_accepts_green_hp_bar() -> None:
    """HP bar dipinta di verde brillante → battaglia."""
    frame = _paint_hp_bar(_blank_frame(), color=(50, 220, 100))
    ok, reason = is_battle_screen(frame, LAYOUT, ROIS)
    assert ok is True
    assert reason == ""


def test_accepts_yellow_hp_bar() -> None:
    """HP bar giallo (HP 20-50%) → battaglia."""
    frame = _paint_hp_bar(_blank_frame(), color=(240, 220, 40))
    ok, _ = is_battle_screen(frame, LAYOUT, ROIS)
    assert ok is True


def test_accepts_red_hp_bar() -> None:
    """HP bar rosso (HP < 20%) → battaglia."""
    frame = _paint_hp_bar(_blank_frame(), color=(220, 40, 40))
    ok, _ = is_battle_screen(frame, LAYOUT, ROIS)
    assert ok is True


def test_rejects_menu_blue_bg() -> None:
    """Blu del menu dialogo (~ (100, 130, 210)) NON è HP-colored."""
    frame = _paint_hp_bar(_blank_frame(), color=(100, 130, 210))
    ok, reason = is_battle_screen(frame, LAYOUT, ROIS)
    assert ok is False
    assert "0" in reason


def test_rejects_grass_overworld() -> None:
    """Verde erba overworld (~(80, 160, 80)) sotto la soglia G>=180 → non HP."""
    frame = _paint_hp_bar(_blank_frame(), color=(80, 160, 80))
    ok, _ = is_battle_screen(frame, LAYOUT, ROIS)
    assert ok is False


def test_threshold_boundary_behavior() -> None:
    """Meno di `MIN_HP_PIXELS` pixel HP-colored → non battaglia.

    Dipingiamo solo N pixel HP verdi in mezzo a un frame teal.
    """
    frame = _blank_frame()
    arr = np.array(frame)
    game_area = compute_game_area(frame.width, frame.height, LAYOUT)
    px = roi_to_pixels(ROIS.opponent_hp_bar, game_area)
    # Dipingi esattamente MIN_HP_PIXELS - 1 pixel verdi = sotto soglia.
    for i in range(MIN_HP_PIXELS - 1):
        arr[px.y, px.x + i] = (50, 220, 100)
    frame_below = Image.fromarray(arr, mode="RGB")
    ok, _ = is_battle_screen(frame_below, LAYOUT, ROIS)
    assert ok is False

    # Dipingi MIN_HP_PIXELS pixel = raggiunge soglia.
    arr[px.y, px.x + MIN_HP_PIXELS - 1] = (50, 220, 100)
    frame_at = Image.fromarray(arr, mode="RGB")
    ok, _ = is_battle_screen(frame_at, LAYOUT, ROIS)
    assert ok is True
