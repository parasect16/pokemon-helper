"""Test del calcolo area gioco e scaling delle ROI."""

from __future__ import annotations

import pytest

from pokemon_helper.vision.roi import (
    GAME_ROIS,
    LAYOUT_MGBA_GB,
    LAYOUT_MGBA_GBA,
    GameLayout,
    PixelRect,
    Roi,
    compute_game_area,
    pixels_to_roi,
    roi_to_pixels,
    snap_roi_to_native,
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

    Aspect 3/2 (GBA). 1119×768 con chrome 52 → area disp. 1119×716. Se riempio
    altezza: 716 * 3/2 = 1074 pixel di larghezza → sta in 1119, letterbox
    laterale (1119-1074)/2 = 22 px per lato.
    """
    area = compute_game_area(1119, 768, LAYOUT_MGBA_GBA)
    assert area.w == 1074
    assert area.h == 716
    assert area.x == 22
    assert area.y == 52


def test_game_area_letterbox_width_limits() -> None:
    """Finestra stretta e alta → larghezza limita, letterbox verticale."""
    # 480 x 600, chrome 52 → disp 480×548. width * 2/3 = 320 altezza → sta.
    # 548-320=228 di letterbox verticale (114 sopra, 114 sotto il chrome).
    area = compute_game_area(480, 600, LAYOUT_MGBA_GBA)
    assert area.w == 480
    assert area.h == 320
    assert area.x == 0
    assert area.y == 52 + (548 - 320) // 2


def test_game_area_menu_offset_hidden() -> None:
    """Con menu nascosto (offset=0), la finestra intera è area gioco."""
    layout = GameLayout(native_width=240, native_height=160, menu_offset_top=0)
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
    assert rois.opponent_hp_bar.w > 0
    assert rois.player_name.w > 0
    assert rois.party_menu_sentinel.w > 0
    assert len(rois.team_menu.slot_areas) == len(rois.team_menu.slot_levels) == 6


# ---------------------------------------------------------------------------
# GameLayout: risoluzione nativa
# ---------------------------------------------------------------------------


def test_the_aspect_ratio_comes_from_the_native_resolution() -> None:
    assert LAYOUT_MGBA_GBA.aspect_ratio == pytest.approx(3 / 2)
    assert LAYOUT_MGBA_GB.aspect_ratio == pytest.approx(10 / 9)


def test_the_native_size_is_exposed_as_a_pair() -> None:
    assert LAYOUT_MGBA_GBA.native_size == (240, 160)


@pytest.mark.parametrize(("width", "height"), [(0, 160), (240, 0), (-240, 160)])
def test_a_layout_without_a_real_native_size_is_rejected(width: int, height: int) -> None:
    with pytest.raises(ValueError, match="native size"):
        GameLayout(native_width=width, native_height=height)


# ---------------------------------------------------------------------------
# pixels_to_roi: inversa di roi_to_pixels
# ---------------------------------------------------------------------------


_GAME_AREA = PixelRect(x=48, y=52, w=1024, h=682)


def test_pixels_to_roi_inverts_roi_to_pixels() -> None:
    """Il giro completo torna al punto di partenza, a meno dell'arrotondamento."""
    original = Roi(x=0.25, y=0.5, w=0.125, h=0.25)

    restored = pixels_to_roi(roi_to_pixels(original, _GAME_AREA), _GAME_AREA)

    assert restored.x == pytest.approx(original.x, abs=1e-3)
    assert restored.y == pytest.approx(original.y, abs=1e-3)
    assert restored.w == pytest.approx(original.w, abs=1e-3)
    assert restored.h == pytest.approx(original.h, abs=1e-3)


def test_a_rectangle_covering_the_whole_area_is_the_unit_roi() -> None:
    roi = pixels_to_roi(_GAME_AREA, _GAME_AREA)

    assert (roi.x, roi.y, roi.w, roi.h) == (0.0, 0.0, 1.0, 1.0)


def test_a_rectangle_spilling_onto_the_letterbox_is_clipped() -> None:
    """Si disegna col mouse: sbordare è normale, non è un errore."""
    spilling = PixelRect(x=_GAME_AREA.x - 100, y=_GAME_AREA.y - 40, w=200, h=80)

    roi = pixels_to_roi(spilling, _GAME_AREA)

    assert roi.x == 0.0
    assert roi.y == 0.0
    assert roi.w == pytest.approx(100 / _GAME_AREA.w)
    assert roi.h == pytest.approx(40 / _GAME_AREA.h)


def test_a_rectangle_entirely_outside_becomes_degenerate() -> None:
    outside = PixelRect(x=_GAME_AREA.x - 500, y=_GAME_AREA.y - 500, w=100, h=100)

    roi = pixels_to_roi(outside, _GAME_AREA)

    assert (roi.w, roi.h) == (0.0, 0.0)


def test_pixels_to_roi_needs_a_real_game_area() -> None:
    with pytest.raises(ValueError, match="positive size"):
        pixels_to_roi(PixelRect(x=0, y=0, w=10, h=10), PixelRect(x=0, y=0, w=0, h=100))


# ---------------------------------------------------------------------------
# snap_roi_to_native
# ---------------------------------------------------------------------------


def test_snapping_lands_on_whole_native_pixels() -> None:
    """240x160: ogni coordinata diventa un multiplo esatto di 1/240 o 1/160."""
    snapped = snap_roi_to_native(Roi(x=0.1234, y=0.4321, w=0.2, h=0.3), LAYOUT_MGBA_GBA)

    assert snapped.x * 240 == pytest.approx(round(snapped.x * 240))
    assert snapped.y * 160 == pytest.approx(round(snapped.y * 160))
    assert snapped.w * 240 == pytest.approx(round(snapped.w * 240))
    assert snapped.h * 160 == pytest.approx(round(snapped.h * 160))


def test_a_roi_already_on_the_grid_is_left_alone() -> None:
    aligned = Roi(x=40 / 240, y=48 / 160, w=64 / 240, h=64 / 160)

    assert snap_roi_to_native(aligned, LAYOUT_MGBA_GBA) == aligned


def test_snapping_keeps_at_least_one_native_pixel() -> None:
    """Un click senza trascinamento non deve produrre un rettangolo vuoto."""
    snapped = snap_roi_to_native(Roi(x=0.5, y=0.5, w=0.0, h=0.0), LAYOUT_MGBA_GBA)

    assert snapped.w == pytest.approx(1 / 240)
    assert snapped.h == pytest.approx(1 / 160)


def test_snapping_stays_inside_the_native_bounds() -> None:
    """Il bordo destro non può uscire: `Roi` rifiuterebbe x+w > 1."""
    snapped = snap_roi_to_native(Roi(x=0.999, y=0.999, w=0.001, h=0.001), LAYOUT_MGBA_GBA)

    assert snapped.x + snapped.w == pytest.approx(1.0)
    assert snapped.y + snapped.h == pytest.approx(1.0)


def test_snapping_uses_the_layout_resolution() -> None:
    """Su GB la griglia è 160x144, quindi il passo è un altro."""
    snapped = snap_roi_to_native(Roi(x=0.3, y=0.3, w=0.1, h=0.1), LAYOUT_MGBA_GB)

    assert snapped.x * 160 == pytest.approx(round(snapped.x * 160))
    assert snapped.y * 144 == pytest.approx(round(snapped.y * 144))


def test_the_shipped_rois_are_not_far_from_the_native_grid() -> None:
    """Le ROI del repo sono misurate in pixel nativi, poi arrotondate a 3 cifre.

    Lo scarto dopo lo snap deve restare sotto il pixel nativo: se crescesse,
    vorrebbe dire che qualcuno ha rimesso dentro un valore preso a occhio.
    """
    _, rois = GAME_ROIS["firered"]
    for roi in (rois.opponent_name, rois.opponent_hp_bar, rois.player_name):
        snapped = snap_roi_to_native(roi, LAYOUT_MGBA_GBA)
        assert abs(snapped.x - roi.x) * 240 < 1.0
        assert abs(snapped.y - roi.y) * 160 < 1.0
