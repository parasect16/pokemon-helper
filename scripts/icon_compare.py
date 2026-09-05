"""Confronta capture-post-color-key vs reference per un pokemon specifico."""

from __future__ import annotations

from pathlib import Path

import imagehash
from PIL import Image

from pokemon_helper.vision.sprite_hash import (
    _flatten_alpha,
    _pad_to_square,
    _strip_teal_background,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Slot -> expected species id
EXPECTED = {1: 102, 2: 44, 3: 51, 4: 6, 5: 101, 6: 18}


def main() -> int:
    for slot, pid in EXPECTED.items():
        capture = Image.open(PROJECT_ROOT / "data" / f"icon-slot-{slot}.png")
        cap_stripped = _strip_teal_background(_flatten_alpha(capture))
        cap_square = _pad_to_square(cap_stripped, background=(255, 255, 255))
        cap_final = cap_square.resize((32, 32), Image.Resampling.LANCZOS)
        cap_final.save(PROJECT_ROOT / "data" / f"icon-slot-{slot}-cleaned.png")

        ref_path = (
            PROJECT_ROOT
            / "data/vendor/sprites/sprites/pokemon/versions/generation-iii/icons"
            / f"{pid}.png"
        )
        if not ref_path.exists():
            print(f"[slot {slot}] reference {ref_path} missing")
            continue
        ref = Image.open(ref_path)
        ref_flat = _flatten_alpha(ref)
        ref_stripped = _strip_teal_background(ref_flat)
        ref_square = _pad_to_square(ref_stripped, background=(255, 255, 255))
        ref_final = ref_square.resize((32, 32), Image.Resampling.LANCZOS)
        ref_final.save(PROJECT_ROOT / "data" / f"ref-{pid}-cleaned.png")

        cap_hash = imagehash.phash(cap_final)
        ref_hash = imagehash.phash(ref_final)
        distance = cap_hash - ref_hash
        print(f"[slot {slot}] species={pid} cap={cap_hash} ref={ref_hash} dist={distance}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
