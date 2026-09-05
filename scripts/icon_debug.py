"""Debug: cattura mGBA + calcola pHash per ciascuna icona menu + top match."""

from __future__ import annotations

import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from pokemon_helper.data import PokemonRepository
from pokemon_helper.vision.capture import WindowCapture
from pokemon_helper.vision.roi import GAME_ROIS, compute_game_area, roi_to_pixels
from pokemon_helper.vision.sprite_hash import compute_icon_phash

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    layout, rois = GAME_ROIS["firered"]
    cap = WindowCapture("mGBA")
    frame = cap.capture_frame()
    ga = compute_game_area(frame.width, frame.height, layout)

    with PokemonRepository.open(PROJECT_ROOT / "data" / "pokemon.sqlite") as repo:
        for i, icon_roi in enumerate(rois.team_menu.slot_icons):
            rect = roi_to_pixels(icon_roi, ga)
            crop = frame.image.crop(rect.as_crop_box())
            crop.save(PROJECT_ROOT / "data" / f"icon-slot-{i + 1}.png")
            phash = compute_icon_phash(crop)
            matches = repo.find_pokemon_by_sprite_hash(
                phash, 3, sides=("icon",), max_distance=64, limit=10
            )
            print(f"slot {i + 1} icon phash={phash}")
            for m in matches:
                p = repo.get_by_id(m.pokemon_id)
                name = p.name_en if p else "?"
                print(f"  {m.pokemon_id:>3} {name:<15} dist={m.distance}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
