"""Debug: mostra output OCR completo per ciascuno slot menu Pokemon."""

from __future__ import annotations

import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from pokemon_helper.vision.capture import WindowCapture
from pokemon_helper.vision.ocr import OcrEngine
from pokemon_helper.vision.roi import GAME_ROIS, compute_game_area, roi_to_pixels

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    layout, rois = GAME_ROIS["firered"]
    cap = WindowCapture("mGBA")
    frame = cap.capture_frame()
    ga = compute_game_area(frame.width, frame.height, layout)
    ocr = OcrEngine()
    for i, slot_roi in enumerate(rois.team_menu.slot_areas):
        rect = roi_to_pixels(slot_roi, ga)
        crop = frame.image.crop(rect.as_crop_box())
        crop.save(PROJECT_ROOT / "data" / f"team-slot-{i + 1}-raw.png")
        for scale in (1, 2, 3, 4):
            results = ocr.recognize(crop, upscale=scale)
            print(f"[slot {i + 1}] scale={scale} rect=({rect.w}x{rect.h}) results:")
            for r in results:
                print(f"    text={r.text!r} conf={r.confidence:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
