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
    CalibrationFrame,
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
from pokemon_helper.vision.roi_targets import (
    SCREEN_BATTLE,
    SCREEN_PARTY_MENU,
    TARGETS,
    get_roi,
)

LAYOUT = LAYOUT_MGBA_GBA
# Cattura tipica di mGBA a finestra media: chrome 52 px, niente letterbox
# laterale a questa proporzione.
FRAME_SIZE = (1119, 734)


@pytest.fixture
def image() -> Image.Image:
    """Frame finto ma delle dimensioni giuste: la geometria è ciò che conta."""
    arr = np.full((FRAME_SIZE[1], FRAME_SIZE[0], 3), (40, 80, 120), dtype=np.uint8)
    return Image.fromarray(arr, mode="RGB")


@pytest.fixture
def frame(image) -> CalibrationFrame:
    return CalibrationFrame(image=image, layout=LAYOUT, screen=SCREEN_BATTLE)


@pytest.fixture
def dialog(qtbot, frame) -> RoiCalibratorDialog:
    widget = RoiCalibratorDialog(frame=frame, rois=ROIS_FIRERED, game_key="firered")
    qtbot.addWidget(widget)
    return widget


def _game_area():
    return compute_game_area(FRAME_SIZE[0], FRAME_SIZE[1], LAYOUT)


# --------------------------------------------------------------- conversione


def test_a_pil_frame_becomes_a_qimage_of_the_same_size(image) -> None:
    converted = pil_to_qimage(image)

    assert (converted.width(), converted.height()) == FRAME_SIZE
    assert not converted.isNull()


def test_the_qimage_owns_its_pixels(image) -> None:
    """Senza la copia, i byte del PIL spariscono e resta spazzatura."""
    converted = pil_to_qimage(image)

    assert converted.pixelColor(10, 10).getRgb()[:3] == (40, 80, 120)


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

    dialog.set_frame(frame)

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


# ------------------------------------------------------------------ cattura


def test_without_a_source_the_capture_button_is_off(dialog) -> None:
    """Un dialogo costruito su un frame e basta non ha nulla da ricatturare."""
    assert not dialog._capture_button.isEnabled()


def test_capturing_replaces_the_frame_and_keeps_the_work(qtbot, image, frame) -> None:
    menu_frame = CalibrationFrame(image=image, layout=LAYOUT, screen=SCREEN_PARTY_MENU)
    dialog = RoiCalibratorDialog(
        frame=frame,
        rois=ROIS_FIRERED,
        game_key="firered",
        frame_source=lambda: menu_frame,
    )
    qtbot.addWidget(dialog)
    dialog._on_roi_drawn("opponent_name", Roi(x=0.25, y=0.25, w=0.1, h=0.1))

    dialog._capture_button.click()

    assert "elenco Pokemon" in dialog._screen_banner.text()
    assert get_roi(dialog.rois(), "opponent_name") == Roi(x=0.25, y=0.25, w=0.1, h=0.1)


def test_a_failed_capture_is_reported_and_keeps_the_old_frame(qtbot, frame) -> None:
    """Emulatore chiuso a metà calibrazione: si dice, non si perde il frame."""

    def boom() -> CalibrationFrame:
        raise RuntimeError("finestra mGBA non trovata")

    dialog = RoiCalibratorDialog(
        frame=frame, rois=ROIS_FIRERED, game_key="firered", frame_source=boom
    )
    qtbot.addWidget(dialog)

    dialog._capture_button.click()

    assert "Cattura fallita" in dialog._screen_banner.text()
    assert "mGBA" in dialog._screen_banner.toolTip()
    assert dialog._canvas.game_area.w > 0


# ------------------------------------------------------------------- banner


def test_the_banner_says_which_screen_is_on_display(dialog) -> None:
    assert dialog._screen_banner.text() == "A video: schermata di combattimento."


def test_the_banner_warns_when_the_target_belongs_elsewhere(dialog) -> None:
    """A video c'è il combattimento e si sta per disegnare una ROI del menu."""
    _select_key(dialog, "party_menu_sentinel")

    text = dialog._screen_banner.text()
    assert text.startswith("⚠")
    assert "elenco Pokemon" in text


def test_the_banner_stops_warning_on_a_matching_target(dialog) -> None:
    _select_key(dialog, "party_menu_sentinel")
    _select_key(dialog, "opponent_name")

    assert not dialog._screen_banner.text().startswith("⚠")


def test_an_unrecognised_screen_is_said_plainly(qtbot, image) -> None:
    """Overworld o transizione: nessun avviso, ma nemmeno una finta certezza."""
    unknown = CalibrationFrame(image=image, layout=LAYOUT, screen="other", note="(0 px barra HP)")
    dialog = RoiCalibratorDialog(frame=unknown, rois=ROIS_FIRERED, game_key="firered")
    qtbot.addWidget(dialog)

    assert "schermata non riconosciuta" in dialog._screen_banner.text()
    assert dialog._screen_banner.toolTip() == "(0 px barra HP)"


def _select_key(dialog: RoiCalibratorDialog, key: str) -> None:
    """Seleziona il bersaglio con quella chiave nell'elenco."""
    for row in range(dialog._targets_list.count()):
        if dialog._targets_list.item(row).data(Qt.ItemDataRole.UserRole) == key:
            dialog._targets_list.setCurrentRow(row)
            return
    raise AssertionError(f"bersaglio {key} non in elenco")


# ----------------------------------------------------------------- lettura


def test_the_preview_shows_the_crop_of_the_selected_rectangle(dialog) -> None:
    """Il ritaglio ingrandito: già da solo dice se il box taglia il testo."""
    pixmap = dialog._preview.pixmap()

    assert pixmap is not None
    assert not pixmap.isNull()
    assert pixmap.width() == 240


def test_the_preview_follows_the_selection(dialog) -> None:
    first = dialog._preview.pixmap().size()

    _select_key(dialog, "opponent_hp_bar")

    assert dialog._preview.pixmap().size() != first


def test_without_a_reader_there_is_no_text(dialog) -> None:
    assert dialog._readback.text() == ""


def test_the_reader_gets_the_crop_and_the_key(qtbot, frame) -> None:
    seen: list = []

    def reader(crop, key):
        seen.append((crop.size, key))
        return f"letto su {key}"

    dialog = RoiCalibratorDialog(frame=frame, rois=ROIS_FIRERED, game_key="firered", reader=reader)
    qtbot.addWidget(dialog)

    assert dialog._readback.text() == "letto su opponent_name"
    assert seen[-1][1] == "opponent_name"
    assert seen[-1][0][0] > 0


def test_the_reading_refreshes_after_a_draw(qtbot, frame) -> None:
    """È il ciclo che serve: disegni, leggi, correggi."""
    sizes: list = []

    def reader(crop, key):  # noqa: ARG001
        sizes.append(crop.size)
        return f"{crop.size[0]}x{crop.size[1]}"

    dialog = RoiCalibratorDialog(frame=frame, rois=ROIS_FIRERED, game_key="firered", reader=reader)
    qtbot.addWidget(dialog)
    before = dialog._readback.text()

    dialog._on_roi_drawn("opponent_name", Roi(x=0.1, y=0.1, w=0.5, h=0.5))

    assert dialog._readback.text() != before
    assert len(sizes) >= 2


def test_a_reader_that_blows_up_does_not_close_the_dialog(qtbot, frame) -> None:
    """Un crop degenere o un modello che si lamenta non devono buttare via il lavoro."""

    def reader(crop, key):  # noqa: ARG001
        raise RuntimeError("modello non caricato")

    dialog = RoiCalibratorDialog(frame=frame, rois=ROIS_FIRERED, game_key="firered", reader=reader)
    qtbot.addWidget(dialog)

    assert "lettura fallita" in dialog._readback.text()
    assert "modello non caricato" in dialog._readback.text()


def test_capturing_a_new_frame_re_reads_the_selected_rectangle(qtbot, image, frame) -> None:
    """Dopo la ricattura il testo mostrato deve venire dal frame nuovo."""
    calls: list = []

    def reader(crop, key):  # noqa: ARG001
        calls.append(key)
        return f"lettura {len(calls)}"

    other = CalibrationFrame(image=image, layout=LAYOUT, screen=SCREEN_PARTY_MENU)
    dialog = RoiCalibratorDialog(
        frame=frame,
        rois=ROIS_FIRERED,
        game_key="firered",
        reader=reader,
        frame_source=lambda: other,
    )
    qtbot.addWidget(dialog)
    before = dialog._readback.text()

    dialog._capture_button.click()

    assert dialog._readback.text() != before


# ------------------------------------------------------- ripristino ed export


def test_reset_all_puts_every_rectangle_back(dialog) -> None:
    dialog._on_roi_drawn("opponent_name", Roi(x=0.25, y=0.25, w=0.1, h=0.1))
    dialog._on_roi_drawn("team_menu.slot_levels.2", Roi(x=0.3, y=0.3, w=0.1, h=0.1))

    dialog._reset_all_button.click()

    assert dialog.rois() == ROIS_FIRERED
    assert "default" in dialog._status.text()


def test_reset_all_keeps_the_panel_in_sync(dialog) -> None:
    """Coordinate e anteprima devono seguire, o mostrerebbero il rettangolo vecchio."""
    dialog._on_roi_drawn("opponent_name", Roi(x=0.25, y=0.25, w=0.5, h=0.5))
    wide = dialog._preview.pixmap().size()

    dialog._reset_all_button.click()

    assert dialog._preview.pixmap().size() != wide
    assert dialog._coords.text() == format_native_rect(ROIS_FIRERED.opponent_name, LAYOUT)


def test_the_snippet_reflects_what_was_drawn(dialog) -> None:
    dialog._on_roi_drawn("opponent_name", Roi(x=0.25, y=0.25, w=0.1, h=0.1))

    snippet = dialog.snippet()

    assert "ROIS_FIRERED = GameRois(" in snippet
    assert "opponent_name=Roi(x=0.250, y=0.250, w=0.100, h=0.100)" in snippet


def test_copying_the_snippet_reports_it(dialog) -> None:
    dialog._copy_button.click()

    assert "appunti" in dialog._status.text()
