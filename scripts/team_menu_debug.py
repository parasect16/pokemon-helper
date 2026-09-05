"""Cattura mGBA + disegna ROI del menu Pokemon per ispezione visuale.

Uso:
    python scripts/team_menu_debug.py [game]

Salva:
    data/team-menu-overlay.png     frame con 6 rettangoli slot
    data/team-menu-slot-N.png      crop di ciascuno slot (N=1..6)
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import ImageDraw

from pokemon_helper.vision.capture import CaptureError, WindowCapture
from pokemon_helper.vision.roi import GAME_ROIS, compute_game_area, roi_to_pixels


def main() -> int:
    game = sys.argv[1] if len(sys.argv) > 1 else "firered"
    if game not in GAME_ROIS:
        print(f"ERROR: gioco '{game}' non supportato", file=sys.stderr)
        return 2

    layout, rois = GAME_ROIS[game]

    capture = WindowCapture("mGBA")
    try:
        frame = capture.capture_frame(timeout_seconds=5.0)
    except (CaptureError, TimeoutError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    out_dir = Path(__file__).resolve().parent.parent / "data"
    game_area = compute_game_area(frame.width, frame.height, layout)

    overlay = frame.image.copy()
    draw = ImageDraw.Draw(overlay)

    colors = ("red", "orange", "yellow", "lime", "cyan", "magenta")
    for index, roi in enumerate(rois.team_menu.slot_areas):
        rect = roi_to_pixels(roi, game_area)
        crop = frame.image.crop(rect.as_crop_box())
        crop.save(out_dir / f"team-menu-slot-{index + 1}.png")
        draw.rectangle(
            (rect.x, rect.y, rect.x + rect.w, rect.y + rect.h),
            outline=colors[index],
            width=2,
        )
        print(
            f"[slot {index + 1}] rect=({rect.x},{rect.y},{rect.w}x{rect.h}) color={colors[index]}"
        )

    overlay.save(out_dir / "team-menu-overlay.png")
    print(f"[done] overlay salvato in {out_dir / 'team-menu-overlay.png'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
