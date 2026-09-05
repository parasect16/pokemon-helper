"""Cattura mGBA (menu Pokemon aperto) + riconosce i 6 slot squadra.

Uso:
    python scripts/recognize_team_test.py [game]

Default `game=firered`.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

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

GAME_GENERATION = {"firered": 3}


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
        results = recognizer.recognize_team(frame.image, layout, rois, generation)
        for res in results:
            name = "-"
            if res.pokemon_id is not None:
                pokemon = repo.get_by_id(res.pokemon_id)
                name = pokemon.name_it if pokemon else f"#{res.pokemon_id}"
            print(
                f"[slot {res.slot_index + 1}] name={name!r:20} level={res.level} "
                f"conf={res.confidence:.2f} src={res.source} ocr={res.ocr_text!r}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
