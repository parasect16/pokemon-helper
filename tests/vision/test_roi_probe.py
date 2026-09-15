"""Test di `vision.roi_probe`: cosa dice il calibratore di un ritaglio.

L'OCR è finto — qui interessa che ogni tipo di bersaglio venga descritto con
il segnale giusto, non la qualità del riconoscimento, che ha i suoi test.
"""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from pokemon_helper.vision.ocr import OcrResult
from pokemon_helper.vision.roi_probe import describe_crop, make_reader
from pokemon_helper.vision.screen_mode import MIN_HP_PIXELS

NAME_KEY = "opponent_name"
HP_KEY = "opponent_hp_bar"
LEVEL_KEY = "team_menu.slot_levels.0"


class _FakeOcr:
    """Ritorna righe fisse e registra quante volte è stato chiamato."""

    def __init__(self, *results: tuple[str, float]) -> None:
        self.results = [OcrResult(text=text, confidence=conf) for text, conf in results]
        self.calls = 0

    def recognize(self, image, **_kwargs) -> list[OcrResult]:  # noqa: ANN001, ARG002
        self.calls += 1
        return list(self.results)


def _solid(color: tuple[int, int, int], size: tuple[int, int] = (60, 12)) -> Image.Image:
    arr = np.full((size[1], size[0], 3), color, dtype=np.uint8)
    return Image.fromarray(arr, mode="RGB")


# ----------------------------------------------------------------- testo


def test_a_text_box_reports_what_the_ocr_read() -> None:
    line = describe_crop(_solid((0, 0, 0)), NAME_KEY, _FakeOcr(("WEEZING", 0.97)))

    assert 'testo: "WEEZING"' in line
    assert "0.97" in line


def test_the_most_confident_line_wins() -> None:
    ocr = _FakeOcr(("PS", 0.40), ("WEEZING", 0.97))

    line = describe_crop(_solid((0, 0, 0)), NAME_KEY, ocr)

    assert '"WEEZING"' in line


def test_extra_lines_are_flagged() -> None:
    """Più righe in un riquadro nome significano quasi sempre ROI troppo alta."""
    ocr = _FakeOcr(("WEEZING", 0.97), ("PS", 0.40), ("33", 0.90))

    assert "+2 altre righe" in describe_crop(_solid((0, 0, 0)), NAME_KEY, ocr)


def test_an_empty_reading_says_so() -> None:
    assert describe_crop(_solid((0, 0, 0)), NAME_KEY, _FakeOcr()) == "nessun testo letto"


# -------------------------------------------------------------- barra PS


def test_a_full_hp_bar_counts_enough_pixels() -> None:
    line = describe_crop(_solid((50, 220, 100)), HP_KEY, _FakeOcr())

    assert "pixel colore-PS" in line
    assert "sufficienti" in line


def test_an_empty_hp_bar_says_how_many_are_missing() -> None:
    """È il caso del rettangolo finito sui numeri PS invece che sulla barra."""
    line = describe_crop(_solid((248, 248, 248)), HP_KEY, _FakeOcr())

    assert "0" in line
    assert f"ne servono {MIN_HP_PIXELS}" in line


def test_the_hp_bar_is_not_passed_to_the_ocr() -> None:
    """Non contiene testo: spenderci un'inferenza ONNX sarebbe sprecato."""
    ocr = _FakeOcr(("qualcosa", 0.9))

    describe_crop(_solid((50, 220, 100)), HP_KEY, ocr)

    assert ocr.calls == 0


# ---------------------------------------------------------------- livello


def test_a_level_box_reports_the_number_it_read() -> None:
    """Il livello passa dal lettore cifra per cifra, come nel riconoscimento."""
    crop = _make_level_crop("37")

    line = describe_crop(crop, LEVEL_KEY, _FakeOcr(("3", 1.0)))

    assert line.startswith("livello letto:") or "non riconosciuto" in line


def test_an_unreadable_level_mentions_the_status_badge() -> None:
    """Con un'alterazione di stato il gioco non disegna il livello."""
    line = describe_crop(_solid((90, 140, 200)), LEVEL_KEY, _FakeOcr())

    assert "non riconosciuto" in line
    assert "alterazione di stato" in line


# ----------------------------------------------------------------- reader


def test_make_reader_binds_the_engine() -> None:
    reader = make_reader(_FakeOcr(("ESCI", 0.98)))

    assert '"ESCI"' in reader(_solid((0, 0, 0)), "party_menu_sentinel")


@pytest.mark.parametrize("key", [NAME_KEY, HP_KEY, LEVEL_KEY, "party_menu_sentinel"])
def test_every_kind_of_target_produces_a_line(key: str) -> None:
    line = describe_crop(_solid((50, 220, 100)), key, _FakeOcr(("X", 0.5)))

    assert line
    assert "\n" not in line


def _make_level_crop(text: str) -> Image.Image:
    """Ritaglio sintetico con due colonne di inchiostro, come un `L.XX` reale."""
    arr = np.full((16, 40, 3), 240, dtype=np.uint8)
    for index, _ in enumerate(text):
        left = 6 + index * 12
        arr[4:12, left : left + 6] = 20
    return Image.fromarray(arr, mode="RGB")
