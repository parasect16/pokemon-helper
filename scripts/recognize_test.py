"""Cattura mGBA + OCR + pHash → identifica Pokemon avversario.

Uso:
    python scripts/recognize_test.py [game]

Default `game=firered` (gen 3). Assume mGBA in combattimento.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

# Console Windows default cp1252 non gestisce simboli tipo ♀/♂ nei nomi
# (Nidoran-F/M). Forziamo UTF-8 sullo stdout per lo script diagnostico.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
else:  # pragma: no cover
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from pokemon_helper.data import PokemonRepository
from pokemon_helper.vision.capture import CaptureError, WindowCapture
from pokemon_helper.vision.ocr import OcrEngine
from pokemon_helper.vision.recognizer import Recognizer
from pokemon_helper.vision.roi import GAME_ROIS

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "pokemon.sqlite"

# Mappa gioco -> generazione per la query sul DB.
GAME_GENERATION = {
    "firered": 3,
}


def main() -> int:
    game = sys.argv[1] if len(sys.argv) > 1 else "firered"
    if game not in GAME_ROIS:
        print(f"ERROR: gioco '{game}' non supportato", file=sys.stderr)
        return 2

    layout, rois = GAME_ROIS[game]
    generation = GAME_GENERATION[game]

    capture = WindowCapture("mGBA")
    try:
        frame = capture.capture_frame(timeout_seconds=5.0)
    except (CaptureError, TimeoutError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    with PokemonRepository.open(DB_PATH) as repo:
        recognizer = Recognizer(repo, OcrEngine())
        result = recognizer.recognize_opponent(frame.image, layout, rois, generation)
        if result is None:
            print("[no result] nessun candidato trovato")
            return 1
        pokemon = repo.get_by_id(result.pokemon_id)
        name = pokemon.name_it if pokemon else f"#{result.pokemon_id}"
        print(f"[recognized] {name} (id={result.pokemon_id})")
        print(f"  source={result.source} confidence={result.confidence:.2f}")
        if result.name_score is not None:
            print(f"  name_score={result.name_score:.2f}")
        if result.sprite_distance is not None:
            print(f"  sprite_distance={result.sprite_distance}")
        print(f"  debug={result.debug}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
