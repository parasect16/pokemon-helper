"""Debug: cattura battaglia + isola il crop del nome player + OCR + verdetto.

Uso: mGBA in combattimento → esegui questo script.

Salva:
    data/player-crop-name.png
    data/player-overlay.png       frame con la ROI evidenziata
"""

from __future__ import annotations

import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from PIL import ImageDraw

from pokemon_helper.data import PokemonRepository
from pokemon_helper.vision.capture import WindowCapture
from pokemon_helper.vision.ocr import OcrEngine
from pokemon_helper.vision.recognizer import Recognizer
from pokemon_helper.vision.roi import compute_game_area, roi_to_pixels
from pokemon_helper.vision.roi_store import resolve_rois

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "pokemon.sqlite"


def main() -> int:
    layout, rois = resolve_rois("firered")
    cap = WindowCapture("mGBA")
    frame = cap.capture_frame()
    ga = compute_game_area(frame.width, frame.height, layout)
    print(f"[frame] {frame.width}x{frame.height} game_area=({ga.x},{ga.y},{ga.w}x{ga.h})")

    name_rect = roi_to_pixels(rois.player_name, ga)
    name_crop = frame.image.crop(name_rect.as_crop_box())
    name_crop.save(PROJECT_ROOT / "data" / "player-crop-name.png")
    print(f"[name-roi] {name_rect.w}x{name_rect.h} @ ({name_rect.x},{name_rect.y})")

    overlay = frame.image.copy()
    draw = ImageDraw.Draw(overlay)
    draw.rectangle(
        (name_rect.x, name_rect.y, name_rect.x + name_rect.w, name_rect.y + name_rect.h),
        outline="orange",
        width=2,
    )
    overlay.save(PROJECT_ROOT / "data" / "player-overlay.png")

    ocr = OcrEngine()
    ocr_lines = ocr.recognize(name_crop)
    print(f"[ocr-name] {[(r.text, round(r.confidence, 2)) for r in ocr_lines]}")

    # Simula il vincolo "player in campo = uno dei 6 di squadra" leggendo
    # lo stato persistito. Se non c'è team salvato, fa recognize sull'intero
    # dataset (come prima).
    from pokemon_helper.ui.state import StateStore, default_state_path

    state = StateStore(default_state_path()).load()
    team_ids = {slot.pokemon_id for slot in state.team if slot is not None}
    print(f"[team-restrict] ids={sorted(team_ids) or 'nessuno (dataset intero)'}")
    print(f"[nickname-map] {state.nicknames or 'vuota'}")

    with PokemonRepository.open(DB_PATH) as repo:
        recognizer = Recognizer(repo, ocr)
        result = recognizer.recognize_player(
            frame.image,
            layout,
            rois,
            3,
            restrict_to_ids=team_ids or None,
            nickname_map=state.nicknames,
        )
        if result is None:
            print("[recognize-player] NESSUN RISULTATO")
        else:
            p = repo.get_by_id(result.pokemon_id)
            print(
                f"[recognize-player] id={result.pokemon_id} "
                f"({p.name_it if p else '?'}) "
                f"conf={result.confidence:.2f} name_score={result.name_score:.2f}"
            )
            print(f"  debug={result.debug}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
