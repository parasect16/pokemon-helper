"""Test di `vision.level_reader`.

L'OCR è sostituito da un finto motore che restituisce testi da una coda, così
segmentazione, polarità e assemblaggio del numero sono verificabili senza
caricare i modelli ONNX né avere l'emulatore aperto.
"""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from pokemon_helper.vision.level_reader import _binarize, _segment_columns, read_level
from pokemon_helper.vision.ocr import OcrResult


class _QueueOcr:
    """Finto `OcrEngine`: consuma la coda `texts`, una voce per chiamata."""

    def __init__(self, texts: list[str]) -> None:
        self._texts = list(texts)
        self.calls = 0

    def recognize(self, image, **kwargs) -> list[OcrResult]:
        self.calls += 1
        if not self._texts:
            return []
        text = self._texts.pop(0)
        return [OcrResult(text=text, confidence=1.0)] if text else []


def _strip_image(columns: list[bool], height: int = 8, dark_text: bool = True) -> Image.Image:
    """Immagine in cui le colonne marcate `True` contengono testo.

    Il tratto occupa solo 3 righe su 8: come nei crop reali l'inchiostro deve
    restare la classe minoritaria, che è ciò su cui `_binarize` decide la
    polarità. Con `dark_text=False` la polarità è invertita (testo chiaro su
    fondo scuro), come nelle righe blu della lista squadra.
    """
    fg, bg = (0, 255) if dark_text else (255, 0)
    arr = np.full((height, len(columns)), bg, dtype=np.uint8)
    for x, inked in enumerate(columns):
        if inked:
            arr[2:5, x] = fg
    return Image.fromarray(arr, mode="L").convert("RGB")


# Due cifre da 4 colonne separate da 2 colonne vuote, più margini.
_TWO_DIGITS = [False] * 2 + [True] * 4 + [False] * 2 + [True] * 4 + [False] * 2


def test_reads_two_digits() -> None:
    ocr = _QueueOcr(["3", "8"])
    assert read_level(_strip_image(_TWO_DIGITS), ocr) == 38
    assert ocr.calls == 2


def test_reads_light_text_on_dark_background() -> None:
    """La polarità viene dedotta, non assunta: il testo è la classe minoritaria."""
    ocr = _QueueOcr(["2", "5"])
    assert read_level(_strip_image(_TWO_DIGITS, dark_text=False), ocr) == 25


def test_reads_three_digit_level() -> None:
    columns = [False] + ([True] * 4 + [False] * 2) * 3
    assert read_level(_strip_image(columns), _QueueOcr(["1", "0", "0"])) == 100


def test_status_badge_yields_none() -> None:
    """Con un'alterazione di stato il gioco disegna il badge al posto del livello."""
    columns = [False] + ([True] * 4 + [False] * 2) * 3
    assert read_level(_strip_image(columns), _QueueOcr(["V", "L", "N"])) is None


def test_unreadable_digit_yields_none() -> None:
    assert read_level(_strip_image(_TWO_DIGITS), _QueueOcr(["3", ""])) is None


def test_multi_character_reading_is_rejected() -> None:
    """Una cella deve produrre una sola cifra: `38` da una cella è un errore."""
    assert read_level(_strip_image(_TWO_DIGITS), _QueueOcr(["38", "8"])) is None


def test_blank_crop_yields_none() -> None:
    ocr = _QueueOcr(["3"])
    assert read_level(_strip_image([False] * 12), ocr) is None
    assert ocr.calls == 0


@pytest.mark.parametrize("digits", [["0", "0"], ["9", "9", "9"]])
def test_out_of_range_level_yields_none(digits: list[str]) -> None:
    columns = [False] + ([True] * 4 + [False] * 2) * len(digits)
    assert read_level(_strip_image(columns), _QueueOcr(digits)) is None


def test_narrow_ink_groups_are_ignored() -> None:
    """Colonne isolate sono rumore di scaling, non cifre."""
    columns = [False, True, False, True, False]
    assert _segment_columns(_binarize(_strip_image(columns))) == []


def test_segment_columns_finds_group_boundaries() -> None:
    assert _segment_columns(_binarize(_strip_image(_TWO_DIGITS))) == [(2, 6), (8, 12)]


def test_segment_columns_closes_a_group_at_the_right_edge() -> None:
    columns = [False] * 2 + [True] * 4
    assert _segment_columns(_binarize(_strip_image(columns))) == [(2, 6)]


def test_binarize_always_returns_dark_ink_on_white() -> None:
    for dark_text in (True, False):
        arr = np.asarray(_binarize(_strip_image(_TWO_DIGITS, dark_text=dark_text)))
        assert arr.min() == 0 and arr.max() == 255
        # 8 colonne di testo su 14, alte 3 righe su 8: inchiostro al 21%.
        assert (arr < 128).mean() == pytest.approx(8 * 3 / (14 * 8))
