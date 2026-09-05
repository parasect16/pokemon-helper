"""OCR di testi da un ritaglio del frame catturato, via RapidOCR.

Wrapper sopra `rapidocr.RapidOCR` che:

- lazy-inizializza il motore (l'init costa ~150 ms e carica 3 modelli ONNX;
  vogliamo pagare il costo solo alla prima chiamata di `recognize`);
- accetta un `PIL.Image` e ritorna la lista di testi con confidenza;
- espone un helper `best_text()` che ritorna la stringa con confidenza più
  alta, comoda per l'uso primario "leggi il nome dell'avversario".

Modelli usati: `PP-OCRv6_det_small` + `ch_ppocr_mobile_v2.0_cls_mobile` +
`PP-OCRv6_rec_small`, scaricati e cachati dentro il pacchetto `rapidocr` al
primo utilizzo.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from PIL import Image, ImageOps

if TYPE_CHECKING:
    from rapidocr import RapidOCR


@dataclass(frozen=True, slots=True)
class OcrResult:
    """Riga di testo estratta con la sua confidenza (0-1)."""

    text: str
    confidence: float


class OcrEngine:
    """Facciata pigra sopra RapidOCR: singola istanza per app."""

    def __init__(self) -> None:
        self._engine: RapidOCR | None = None

    def _ensure_engine(self) -> RapidOCR:
        if self._engine is None:
            # Import posticipato: avvio del modulo `rapidocr` è costoso
            # (scan filesystem + download check dei modelli).
            from rapidocr import RapidOCR

            self._engine = RapidOCR()
        return self._engine

    def recognize(
        self,
        image: Image.Image,
        *,
        upscale: int = 1,
        high_contrast: bool = False,
    ) -> list[OcrResult]:
        """Riconosce tutte le righe di testo presenti in `image`.

        - `upscale` (default 1 = niente resize) ingrandisce l'immagine con
          LANCZOS prima di passarla al motore. Utile su font pixel piccoli:
          RapidOCR beneficia molto dall'input più grande.
        - `high_contrast=True` converte in grayscale + auto-contrast +
          invert (se lo sfondo è più scuro del testo). Utile per il livello
          `L.XX` bianco su blu del menu Pokemon.
        """
        rgb = image.convert("RGB")
        if high_contrast:
            gray = ImageOps.autocontrast(rgb.convert("L"))
            # Inverti se lo sfondo (mediana dei pixel) è più scuro del centro.
            arr = np.asarray(gray)
            if arr.mean() < 128:
                gray = ImageOps.invert(gray)
            rgb = gray.convert("RGB")
        if upscale > 1:
            new_size = (rgb.width * upscale, rgb.height * upscale)
            rgb = rgb.resize(new_size, Image.Resampling.LANCZOS)
        array = np.asarray(rgb)

        engine = self._ensure_engine()
        # RapidOCR 3.x ritorna un `RapidOCROutput` con attributi `txts` e
        # `scores`; le API più vecchie ritornavano una tupla o una lista di
        # liste. Gestiamo entrambe le forme.
        raw = engine(array)
        return list(_iter_results(raw))

    def best_text(self, image: Image.Image, *, upscale: int = 1) -> OcrResult | None:
        """Restituisce la riga con confidenza più alta, o `None` se vuota."""
        results = self.recognize(image, upscale=upscale)
        if not results:
            return None
        return max(results, key=lambda r: r.confidence)


def _iter_results(raw: object):
    """Normalizza l'output di RapidOCR nelle diverse versioni supportate."""
    txts = getattr(raw, "txts", None)
    scores = getattr(raw, "scores", None)
    if txts is not None:
        scores = scores if scores is not None else [1.0] * len(txts)
        for text, score in zip(txts, scores, strict=False):
            if text:
                yield OcrResult(text=str(text), confidence=float(score))
        return

    # Fallback per API più vecchia: `list[[box, text, score]]` o simile.
    if isinstance(raw, tuple):
        raw = raw[0] if raw else []
    if not raw:
        return
    for entry in raw:
        if not isinstance(entry, (list, tuple)) or len(entry) < 3:
            continue
        _box, text, score = entry[0], entry[1], entry[2]
        if text:
            yield OcrResult(text=str(text), confidence=float(score))
