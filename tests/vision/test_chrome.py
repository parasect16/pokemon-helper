"""Test della misura del chrome su frame sintetici.

I frame sono costruiti a mano perché il caso che conta — una barra del titolo
più alta della nostra — non si riproduce sulla macchina di sviluppo: è
esattamente ciò che succede su Win11 o a DPI diversa.
"""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from pokemon_helper.vision.chrome import (
    MAX_CHROME_HEIGHT,
    MIN_CHROME_HEIGHT,
    detect_chrome_height,
    resolve_layout,
)
from pokemon_helper.vision.roi import LAYOUT_MGBA_GBA, GameLayout

WIDTH = 400
HEIGHT = 300

TITLE_BAR = (242, 242, 242)
WINDOW_BORDER = (43, 43, 43)
# Prima riga del campo di battaglia FRLG su cattura reale: grigia quasi quanto
# una superficie di sistema, ma è già gioco.
PALE_FIELD = (231, 255, 231)
MENU_BAR = (214, 214, 214)
DARK_TITLE_BAR = (32, 32, 32)
GAME_TEAL = (24, 150, 144)
LETTERBOX = (0, 0, 0)


def _frame(
    *,
    title_h: int = 30,
    menu_h: int = 22,
    title_color=TITLE_BAR,
    game_color=GAME_TEAL,
    letterbox_h: int = 0,
    border_h: int = 0,
) -> Image.Image:
    """Finestra finta: bordo, barra titolo, barra menu, letterbox, gioco.

    `title_h` e `menu_h` sono contati dall'alto: il bordo mangia le prime
    `border_h` righe della barra del titolo, come nel frame vero.
    """
    arr = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
    arr[:title_h] = title_color
    arr[:border_h] = WINDOW_BORDER
    arr[title_h : title_h + menu_h] = MENU_BAR
    top = title_h + menu_h
    arr[top : top + letterbox_h] = LETTERBOX
    arr[top + letterbox_h :] = game_color
    return Image.fromarray(arr, mode="RGB")


def _with_text(image: Image.Image, row_span: tuple[int, int]) -> Image.Image:
    """Scurisce qualche pixel sparso: il testo di titolo e menu."""
    arr = np.asarray(image).copy()
    start, end = row_span
    arr[start:end, 40:120:4] = (60, 60, 60)
    return Image.fromarray(arr, mode="RGB")


def test_the_chrome_is_the_title_bar_plus_the_menu_bar() -> None:
    assert detect_chrome_height(_frame(title_h=30, menu_h=22)) == 52


def test_a_taller_title_bar_is_measured_as_such() -> None:
    """Il caso che il valore fisso sbagliava: DPI 125% porta il titolo a 37 px."""
    assert detect_chrome_height(_frame(title_h=37, menu_h=25)) == 62


def test_text_on_the_bars_does_not_break_the_measure() -> None:
    """Il titolo della finestra e le voci di menu sono pixel scuri sul grigio."""
    frame = _with_text(_frame(title_h=30, menu_h=22), (8, 44))
    assert detect_chrome_height(frame) == 52


def test_the_letterbox_below_the_chrome_is_not_counted() -> None:
    """Le bande nere di mGBA sono grigie quanto il chrome: le esclude la luminosità.

    Contarle sposterebbe in basso l'intera area di gioco, che è il bug che
    questa funzione dovrebbe evitare.
    """
    assert detect_chrome_height(_frame(title_h=30, menu_h=22, letterbox_h=20)) == 52


def test_a_frame_that_starts_with_the_game_has_no_chrome() -> None:
    assert detect_chrome_height(_frame(title_h=0, menu_h=0)) is None


def test_a_dark_title_bar_is_not_recognised() -> None:
    """Limite noto: col tema scuro si ripiega sul valore dichiarato nel layout."""
    assert detect_chrome_height(_frame(title_color=DARK_TITLE_BAR)) is None


def test_a_chrome_thinner_than_the_minimum_is_rejected() -> None:
    """Una riga chiara di bordo non è una barra del titolo."""
    assert detect_chrome_height(_frame(title_h=MIN_CHROME_HEIGHT - 4, menu_h=0)) is None


def test_a_chrome_taller_than_the_maximum_is_rejected() -> None:
    """Schermo bianco durante una transizione: non è una finestra tutta chrome."""
    frame = _frame(title_h=MAX_CHROME_HEIGHT + 10, menu_h=0)
    assert detect_chrome_height(frame) is None


def test_a_fully_neutral_frame_is_rejected() -> None:
    assert detect_chrome_height(_frame(title_h=HEIGHT, menu_h=0)) is None


def test_a_frame_shorter_than_the_minimum_chrome_is_rejected() -> None:
    tiny = Image.new("RGB", (WIDTH, MIN_CHROME_HEIGHT), TITLE_BAR)
    assert detect_chrome_height(tiny) is None


def test_a_frame_too_narrow_for_the_side_margins_is_rejected() -> None:
    """Larghezza patologica: tolti i margini non resta nulla da misurare."""
    sliver = Image.new("RGB", (4, HEIGHT), TITLE_BAR)
    assert detect_chrome_height(sliver) is None


@pytest.mark.parametrize("mode", ["RGBA", "L"])
def test_other_pixel_formats_are_accepted(mode: str) -> None:
    """`capture` consegna RGB, ma gli script di debug rileggono PNG qualsiasi."""
    frame = _frame(title_h=30, menu_h=22).convert(mode)
    detected = detect_chrome_height(frame)
    # In scala di grigi il gioco perde la saturazione che lo distingue dal
    # chrome, quindi la misura può fallire: non deve però sollevare.
    assert detected in (52, None)


# ----------------------------------------------------------- resolve_layout


def test_resolve_layout_overrides_the_declared_offset() -> None:
    resolved = resolve_layout(_frame(title_h=37, menu_h=25), LAYOUT_MGBA_GBA)
    assert resolved.menu_offset_top == 62
    assert resolved.aspect_ratio == LAYOUT_MGBA_GBA.aspect_ratio


def test_resolve_layout_keeps_the_declared_offset_when_the_measure_fails() -> None:
    resolved = resolve_layout(_frame(title_color=DARK_TITLE_BAR), LAYOUT_MGBA_GBA)
    assert resolved is LAYOUT_MGBA_GBA


def test_resolve_layout_returns_the_same_layout_when_they_agree() -> None:
    layout = GameLayout(aspect_ratio=240 / 160, menu_offset_top=52)
    assert resolve_layout(_frame(title_h=30, menu_h=22), layout) is layout


def test_the_override_is_logged_once_per_value(capsys) -> None:
    """L'auto-detect polla due volte al secondo: una riga per poll sarebbe rumore."""
    frame = _frame(title_h=40, menu_h=28)  # 68, diverso dai 52 dichiarati
    resolve_layout(frame, LAYOUT_MGBA_GBA)
    first = capsys.readouterr().out
    resolve_layout(frame, LAYOUT_MGBA_GBA)
    second = capsys.readouterr().out

    assert "68" in first
    assert second == ""


def test_the_window_border_above_the_title_bar_is_counted_as_chrome() -> None:
    """Il frame reale comincia con una riga scura di bordo, non con il titolo.

    Pretendere il grigio già dalla riga 0 faceva fallire la misura su ogni
    cattura vera: `misurato=None` su 1119x734 con chrome da 52 px.
    """
    assert detect_chrome_height(_frame(title_h=30, menu_h=22, border_h=1)) == 52


def test_a_thick_dark_band_on_top_is_not_a_border() -> None:
    """Oltre la tolleranza non è il bordo della finestra: la misura si ferma."""
    frame = _frame(title_h=30, menu_h=22, border_h=10)
    assert detect_chrome_height(frame) is None


def test_the_pale_first_row_of_the_battlefield_is_not_chrome() -> None:
    """Il campo FRLG comincia con un verde pallidissimo, distante 24 fra i canali.

    Con una soglia di neutralità larga veniva letto come chrome e la misura
    proseguiva dentro il cielo, oltre il massimo consentito.
    """
    assert detect_chrome_height(_frame(title_h=30, menu_h=22, game_color=PALE_FIELD)) == 52
