"""Test del calibratore ROI.

Il mouse non viene simulato: quello che conta è la catena
`coordinate widget → pixel frame → ROI normalizzata agganciata alla griglia`,
esposta da `_RoiCanvas.roi_from_drag`, più il fatto che il dialogo sostituisca
un solo rettangolo alla volta. Il trascinamento vero è tre righe di Qt sopra
quella catena.
"""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image
from PySide6.QtCore import QPoint, Qt

from pokemon_helper.ui.roi_calibrator import (
    RoiCalibratorDialog,
    fit_zoom_percent,
    format_native_rect,
    nudge_roi,
    pil_to_qimage,
)
from pokemon_helper.vision.roi import (
    LAYOUT_MGBA_GBA,
    ROIS_FIRERED,
    Roi,
    compute_game_area,
    roi_to_pixels,
)
from pokemon_helper.vision.roi_targets import TARGETS, get_roi

LAYOUT = LAYOUT_MGBA_GBA
# Cattura tipica di mGBA a finestra media: chrome 52 px, niente letterbox
# laterale a questa proporzione.
FRAME_SIZE = (1119, 734)


@pytest.fixture
def frame() -> Image.Image:
    """Frame finto ma delle dimensioni giuste: la geometria è ciò che conta."""
    arr = np.full((FRAME_SIZE[1], FRAME_SIZE[0], 3), (40, 80, 120), dtype=np.uint8)
    return Image.fromarray(arr, mode="RGB")


@pytest.fixture
def dialog(qtbot, frame) -> RoiCalibratorDialog:
    widget = RoiCalibratorDialog(
        frame=frame,
        layout=LAYOUT,
        rois=ROIS_FIRERED,
        game_key="firered",
    )
    qtbot.addWidget(widget)
    return widget


def _game_area():
    return compute_game_area(FRAME_SIZE[0], FRAME_SIZE[1], LAYOUT)


# --------------------------------------------------------------- conversione


def test_a_pil_frame_becomes_a_qimage_of_the_same_size(frame) -> None:
    image = pil_to_qimage(frame)

    assert (image.width(), image.height()) == FRAME_SIZE
    assert not image.isNull()


def test_the_qimage_owns_its_pixels(frame) -> None:
    """Senza la copia, i byte del PIL spariscono e resta spazzatura."""
    image = pil_to_qimage(frame)

    assert image.pixelColor(10, 10).getRgb()[:3] == (40, 80, 120)


# ------------------------------------------------------------------ disegno


def test_a_drag_over_a_known_rectangle_reproduces_it(dialog) -> None:
    """Ridisegnare una ROI esistente deve restituire (quasi) la stessa ROI.

    Il giro completo passa da normalizzata a pixel frame e ritorno, quindi lo
    scarto ammesso è il pixel nativo — che è anche la precisione con cui le
    ROI del repo sono scritte.
    """
    original = ROIS_FIRERED.opponent_name
    rect = roi_to_pixels(original, _game_area())
    canvas = dialog._canvas

    drawn = canvas.roi_from_drag(
        canvas.frame_to_widget(rect.x, rect.y),
        canvas.frame_to_widget(rect.x + rect.w, rect.y + rect.h),
    )

    assert drawn.x == pytest.approx(original.x, abs=1 / 240)
    assert drawn.y == pytest.approx(original.y, abs=1 / 160)
    assert drawn.w == pytest.approx(original.w, abs=1 / 240)
    assert drawn.h == pytest.approx(original.h, abs=1 / 160)


def test_a_drag_lands_on_the_native_grid(dialog) -> None:
    canvas = dialog._canvas
    canvas.set_zoom_percent(100)

    drawn = canvas.roi_from_drag(QPoint(300, 200), QPoint(437, 261))

    assert drawn.x * 240 == pytest.approx(round(drawn.x * 240))
    assert drawn.h * 160 == pytest.approx(round(drawn.h * 160))


def test_dragging_backwards_gives_the_same_rectangle(dialog) -> None:
    """Si può partire dall'angolo in basso a destra: capita, e deve funzionare."""
    canvas = dialog._canvas
    canvas.set_zoom_percent(100)
    start, end = QPoint(300, 200), QPoint(437, 261)

    assert canvas.roi_from_drag(start, end) == canvas.roi_from_drag(end, start)


def test_a_click_without_a_drag_still_gives_one_native_pixel(dialog) -> None:
    canvas = dialog._canvas
    canvas.set_zoom_percent(100)

    drawn = canvas.roi_from_drag(QPoint(300, 200), QPoint(300, 200))

    assert drawn.w == pytest.approx(1 / 240)
    assert drawn.h == pytest.approx(1 / 160)


def test_zoom_does_not_move_the_rectangle(dialog) -> None:
    """A zoom doppio lo stesso punto del frame sta al doppio delle coordinate."""
    canvas = dialog._canvas
    canvas.set_zoom_percent(100)
    at_100 = canvas.roi_from_drag(QPoint(300, 200), QPoint(400, 260))

    canvas.set_zoom_percent(200)
    at_200 = canvas.roi_from_drag(QPoint(600, 400), QPoint(800, 520))

    assert at_200 == at_100


def test_the_canvas_resizes_with_the_zoom(dialog) -> None:
    canvas = dialog._canvas
    canvas.set_zoom_percent(200)

    assert canvas.width() == FRAME_SIZE[0] * 2
    assert canvas.height() == FRAME_SIZE[1] * 2


def test_the_zoom_is_clamped_to_the_usable_range(dialog) -> None:
    canvas = dialog._canvas

    canvas.set_zoom_percent(10_000)
    assert canvas.zoom == pytest.approx(4.0)

    canvas.set_zoom_percent(1)
    assert canvas.zoom == pytest.approx(0.5)


# -------------------------------------------------------------------- nudge


def test_a_nudge_moves_one_native_pixel() -> None:
    roi = Roi(x=40 / 240, y=48 / 160, w=64 / 240, h=64 / 160)

    moved = nudge_roi(roi, LAYOUT, (1, 0))

    assert moved.x * 240 == pytest.approx(41)
    assert moved.w * 240 == pytest.approx(64)


def test_a_shifted_nudge_resizes_instead_of_moving() -> None:
    roi = Roi(x=40 / 240, y=48 / 160, w=64 / 240, h=64 / 160)

    resized = nudge_roi(roi, LAYOUT, (0, 1), resize=True)

    assert resized.y * 160 == pytest.approx(48)
    assert resized.h * 160 == pytest.approx(65)


def test_a_nudge_stops_at_the_border() -> None:
    roi = Roi(x=0.0, y=0.0, w=10 / 240, h=10 / 160)

    assert nudge_roi(roi, LAYOUT, (-1, -1)) == roi


def test_a_resize_never_goes_below_one_pixel() -> None:
    roi = Roi(x=0.5, y=0.5, w=1 / 240, h=1 / 160)

    shrunk = nudge_roi(roi, LAYOUT, (-1, -1), resize=True)

    assert shrunk.w == pytest.approx(1 / 240)
    assert shrunk.h == pytest.approx(1 / 160)


def test_the_arrow_keys_nudge_the_selected_rectangle(dialog, qtbot) -> None:
    dialog._canvas.set_selected("opponent_name")
    before = get_roi(dialog.rois(), "opponent_name")

    qtbot.keyClick(dialog._canvas, Qt.Key.Key_Right)

    after = get_roi(dialog.rois(), "opponent_name")
    assert after.x * 240 == pytest.approx(round(before.x * 240) + 1)


def test_an_unrelated_key_changes_nothing(dialog, qtbot) -> None:
    dialog._canvas.set_selected("opponent_name")
    before = dialog.rois()

    qtbot.keyClick(dialog._canvas, Qt.Key.Key_A)

    assert dialog.rois() == before


# ------------------------------------------------------------------- dialogo


def test_every_target_is_listed_under_its_screen(dialog) -> None:
    """Sedici bersagli più le due intestazioni di gruppo."""
    listed = [
        dialog._targets_list.item(row).data(Qt.ItemDataRole.UserRole)
        for row in range(dialog._targets_list.count())
    ]

    assert [key for key in listed if key is not None] == [target.key for target in TARGETS]
    assert listed.count(None) == 2


def test_the_first_real_target_is_selected_on_open(dialog) -> None:
    assert dialog.selected_key() == TARGETS[0].key


def test_selecting_a_target_shows_its_hint(dialog) -> None:
    dialog._targets_list.setCurrentRow(2)  # prima intestazione, poi due bersagli

    assert dialog._hint.text()
    assert dialog._coords.text().startswith("x=")


def test_drawing_replaces_only_the_selected_rectangle(dialog) -> None:
    drawn = Roi(x=0.25, y=0.25, w=0.1, h=0.1)

    dialog._on_roi_drawn("team_menu.slot_levels.2", drawn)

    assert get_roi(dialog.rois(), "team_menu.slot_levels.2") == drawn
    assert get_roi(dialog.rois(), "team_menu.slot_levels.3") == get_roi(
        ROIS_FIRERED, "team_menu.slot_levels.3"
    )
    assert dialog.rois().opponent_name == ROIS_FIRERED.opponent_name


def test_reset_puts_back_the_factory_rectangle(dialog) -> None:
    dialog._targets_list.setCurrentRow(1)
    key = dialog.selected_key()
    dialog._on_roi_drawn(key, Roi(x=0.25, y=0.25, w=0.1, h=0.1))

    dialog._reset_button.click()

    assert get_roi(dialog.rois(), key) == get_roi(ROIS_FIRERED, key)


def test_reset_uses_the_defaults_it_was_given(qtbot, frame) -> None:
    """Con una calibrazione già salvata, `Ripristina` torna ai valori del repo."""
    saved = RoiCalibratorDialog(
        frame=frame,
        layout=LAYOUT,
        rois=ROIS_FIRERED,
        game_key="firered",
        defaults=ROIS_FIRERED,
    )
    qtbot.addWidget(saved)
    saved._targets_list.setCurrentRow(1)
    key = saved.selected_key()
    saved._on_roi_drawn(key, Roi(x=0.9, y=0.9, w=0.05, h=0.05))

    saved._on_reset_current()

    assert get_roi(saved.rois(), key) == get_roi(ROIS_FIRERED, key)


def test_a_new_frame_keeps_the_rectangles(dialog, frame) -> None:
    """Ricatturare per passare all'altra schermata non azzera il lavoro fatto."""
    dialog._on_roi_drawn("opponent_name", Roi(x=0.25, y=0.25, w=0.1, h=0.1))

    dialog.set_frame(frame, LAYOUT)

    assert get_roi(dialog.rois(), "opponent_name") == Roi(x=0.25, y=0.25, w=0.1, h=0.1)


# ------------------------------------------------------------------ coordinate


def test_the_coordinates_are_shown_in_native_pixels() -> None:
    roi = Roi(x=40 / 240, y=48 / 160, w=64 / 240, h=64 / 160)

    assert format_native_rect(roi, LAYOUT) == "x=40 y=48 w=64 h=64 (nativi 240x160)"


def test_a_wide_frame_opens_scaled_down_to_fit() -> None:
    """1119 px a 1:1 non entrano in finestra accanto all'elenco."""
    assert fit_zoom_percent(1119) == 80


def test_a_small_frame_opens_at_one_to_one() -> None:
    assert fit_zoom_percent(640) == 100


def test_the_fit_never_goes_below_the_minimum_zoom() -> None:
    """Sotto il 50% un pixel nativo sparisce: meglio scorrere che non vedere."""
    assert fit_zoom_percent(10_000) == 50


def test_the_dialog_opens_already_fitted(dialog) -> None:
    assert dialog._canvas.zoom == pytest.approx(0.8)
