"""Cattura mGBA + ritaglia ROI per gioco e salva i crop separatamente.

Uso:
    python scripts/roi_debug.py [game]

Default `game=firered`. Salva:
    data/capture-test.png            frame completo
    data/roi-<game>-name.png         nome avversario
    data/roi-<game>-sprite.png       sprite avversario
    data/roi-<game>-hp.png           barra HP avversario
    data/roi-<game>-overlay.png      frame originale con rettangoli disegnati
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
        print(
            f"ERROR: gioco '{game}' non supportato. Disponibili: {sorted(GAME_ROIS)}",
            file=sys.stderr,
        )
        return 2

    layout, rois = GAME_ROIS[game]

    capture = WindowCapture("mGBA")
    try:
        frame = capture.capture_frame(timeout_seconds=5.0)
    except (CaptureError, TimeoutError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    out_dir = Path(__file__).resolve().parent.parent / "data"
    frame.image.save(out_dir / "capture-test.png")
    print(f"[frame] {frame.width}x{frame.height}")

    game_area = compute_game_area(frame.width, frame.height, layout)
    print(f"[game_area] x={game_area.x} y={game_area.y} w={game_area.w} h={game_area.h}")

    overlay = frame.image.copy()
    draw = ImageDraw.Draw(overlay)
    # Rettangolo area gioco (verde) per sanity check letterbox.
    draw.rectangle(
        (
            game_area.x,
            game_area.y,
            game_area.x + game_area.w,
            game_area.y + game_area.h,
        ),
        outline="lime",
        width=2,
    )

    labels = (
        ("name", rois.opponent_name, "yellow"),
        ("sprite", rois.opponent_sprite, "red"),
        ("hp", rois.opponent_hp_bar, "cyan"),
    )
    for label, roi, color in labels:
        rect = roi_to_pixels(roi, game_area)
        crop = frame.image.crop(rect.as_crop_box())
        crop.save(out_dir / f"roi-{game}-{label}.png")
        draw.rectangle(
            (rect.x, rect.y, rect.x + rect.w, rect.y + rect.h),
            outline=color,
            width=2,
        )
        print(
            f"[roi:{label}] pixel x={rect.x} y={rect.y} w={rect.w} h={rect.h} "
            f"-> {rect.w}x{rect.h} salvato"
        )

    overlay.save(out_dir / f"roi-{game}-overlay.png")
    print(f"[overlay] salvato in {out_dir / f'roi-{game}-overlay.png'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
