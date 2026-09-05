"""Test del calcolo area gioco e scaling delle ROI."""

from __future__ import annotations

import pytest

from pokemon_helper.vision.roi import (
    GAME_ROIS,
    LAYOUT_MGBA_GBA,
    GameLayout,
    PixelRect,
    Roi,
    compute_game_area,
    roi_to_pixels,
)

# ---------------------------------------------------------------------------
# Validazione dataclass Roi
# ---------------------------------------------------------------------------


def test_roi_accepts_valid_normalized_bounds() -> None:
    """Valori dentro [0, 1] e somma ≤ 1 sono ammessi."""
    roi = Roi(x=0.1, y=0.2, w=0.5, h=0.3)
    assert roi.x == 0.1


@pytest.mark.parametrize(
    ("x", "y", "w", "h"),
    [(-0.1, 0, 0.5, 0.5), (0, 0, 1.1, 0.5), (0, 0, 0.5, -0.5)],
)
def test_roi_rejects_out_of_range_values(x: float, y: float, w: float, h: float) -> None:
    """Fuori [0, 1] la ROI alza subito."""
    with pytest.raises(ValueError, match="out of"):
        Roi(x=x, y=y, w=w, h=h)


def test_roi_rejects_exceeding_native_bounds() -> None:
    """Somma x+w o y+h > 1 non è ammessa."""
    with pytest.raises(ValueError, match="exceeds native bounds"):
        Roi(x=0.6, y=0.0, w=0.6, h=0.5)


# ---------------------------------------------------------------------------
# compute_game_area
# ---------------------------------------------------------------------------


def test_game_area_letterbox_height_limits() -> None:
    """Finestra molto larga → altezza limita, letterbox laterale centrato.

    Aspect 3/2 (GBA). 1119×768 con menu 30 → area disp. 1119×738. Se riempio
    altezza: 738 * 3/2 = 1107 pixel di larghezza → sta in 1119, letterbox
    laterale (1119-1107)/2 = 6 px per lato.
    """
    area = compute_game_area(1119, 768, LAYOUT_MGBA_GBA)
    assert area.w == 1107
    assert area.h == 738
    assert area.x == 6
    assert area.y == 30


def test_game_area_letterbox_width_limits() -> None:
    """Finestra stretta e alta → larghezza limita, letterbox verticale."""
    # 480 x 600, menu 30 → disp 480×570. width * 2/3 = 320 altezza → sta in 570.
    # Ma se width limita: 480 * 2/3 = 320 di altezza. 570-320=250 di letterbox
    # verticale (125 sopra, 125 sotto il menu).
    area = compute_game_area(480, 600, LAYOUT_MGBA_GBA)
    assert area.w == 480
    assert area.h == 320
    assert area.x == 0
    assert area.y == 30 + (570 - 320) // 2


def test_game_area_menu_offset_hidden() -> None:
    """Con menu nascosto (offset=0), la finestra intera è area gioco."""
    layout = GameLayout(aspect_ratio=240 / 160, menu_offset_top=0)
    area = compute_game_area(240 * 4, 160 * 4, layout)
    assert area == PixelRect(x=0, y=0, w=960, h=640)


# ---------------------------------------------------------------------------
# roi_to_pixels
# ---------------------------------------------------------------------------


def test_roi_to_pixels_maps_full_bounds() -> None:
    """ROI (0, 0, 1, 1) copre l'intera area gioco."""
    area = PixelRect(x=10, y=30, w=1000, h=500)
    full = Roi(x=0, y=0, w=1, h=1)
    assert roi_to_pixels(full, area) == area


def test_roi_to_pixels_maps_quadrant() -> None:
    """Quadrante top-left: ROI (0, 0, 0.5, 0.5) → metà larghezza e altezza."""
    area = PixelRect(x=100, y=200, w=800, h=400)
    quad = Roi(x=0, y=0, w=0.5, h=0.5)
    result = roi_to_pixels(quad, area)
    assert result == PixelRect(x=100, y=200, w=400, h=200)


def test_roi_to_pixels_maps_offset_region() -> None:
    """ROI centrale mantiene offset dell'area gioco."""
    area = PixelRect(x=6, y=30, w=1107, h=738)
    center = Roi(x=0.25, y=0.25, w=0.5, h=0.5)
    result = roi_to_pixels(center, area)
    # x = 6 + 0.25 * 1107 = 6 + 277 = 283
    assert result.x == 283
    assert result.y == 30 + int(round(0.25 * 738))
    assert result.w == int(round(0.5 * 1107))
    assert result.h == int(round(0.5 * 738))


def test_pixel_rect_as_crop_box_returns_pillow_format() -> None:
    """`as_crop_box` restituisce `(left, upper, right, lower)` per PIL."""
    rect = PixelRect(x=10, y=20, w=100, h=50)
    assert rect.as_crop_box() == (10, 20, 110, 70)


# ---------------------------------------------------------------------------
# GAME_ROIS registry
# ---------------------------------------------------------------------------


def test_game_rois_registry_contains_firered() -> None:
    """Il registry esposto pubblicamente deve includere `firered`."""
    layout, rois = GAME_ROIS["firered"]
    assert layout.aspect_ratio == pytest.approx(240 / 160)
    assert rois.opponent_name.w > 0
    assert rois.opponent_sprite.w > 0
    assert rois.opponent_hp_bar.w > 0
