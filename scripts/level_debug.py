"""Debug: cattura + OCR sul crop dedicato del livello per ciascun slot."""

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
    for i, level_roi in enumerate(rois.team_menu.slot_levels):
        rect = roi_to_pixels(level_roi, ga)
        crop = frame.image.crop(rect.as_crop_box())
        crop.save(PROJECT_ROOT / "data" / f"level-slot-{i + 1}.png")
        for scale in (3, 5, 8):
            for hc in (False, True):
                lines = ocr.recognize(crop, upscale=scale, high_contrast=hc)
                texts = [f"{r.text!r}@{r.confidence:.2f}" for r in lines]
                print(f"[slot {i + 1}] scale={scale} hc={hc}: {texts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
