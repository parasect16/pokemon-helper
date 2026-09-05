"""Diagnostica completa del menu Pokemon: overlay ROI + crop + OCR live.

Uso:
    python scripts/team_menu_debug.py [game]

Cattura mGBA (menu Pokemon aperto) e per ogni slot:

- ritaglia le tre ROI: `slot_areas` (nome), `slot_icons` (icona), `slot_levels`
  (livello);
- salva i crop come `data/team-slot-N-{name,icon,level}.png`;
- esegue OCR sul crop nome e sul crop livello (con `high_contrast=True` +
  `upscale=4` come nel recognizer reale);
- esegue `recognize_team` completo e stampa il verdetto per slot.

Overlay unico `data/team-menu-overlay.png` disegna tutte e 3 le ROI per
slot in colori distinti (magenta=nome, ciano=icona, giallo=livello) —
comodo per vedere a colpo d'occhio se le ROI sono allineate al capture
reale con la risoluzione corrente dell'emulatore.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
else:  # pragma: no cover
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from PIL import ImageDraw

from pokemon_helper.data import PokemonRepository
from pokemon_helper.vision.capture import CaptureError, WindowCapture
from pokemon_helper.vision.ocr import OcrEngine
from pokemon_helper.vision.recognizer import Recognizer
from pokemon_helper.vision.roi import GAME_ROIS, PixelRect, compute_game_area, roi_to_pixels

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "pokemon.sqlite"
OUT_DIR = PROJECT_ROOT / "data"

GAME_GENERATION = {"firered": 3}

# Colori overlay (RGB): allineati al PNG annotato dell'utente per confronto.
COLOR_NAME = "magenta"
COLOR_ICON = "cyan"
COLOR_LEVEL = "yellow"


def _draw_rect(draw: ImageDraw.ImageDraw, rect: PixelRect, color: str) -> None:
    draw.rectangle(
        (rect.x, rect.y, rect.x + rect.w, rect.y + rect.h),
        outline=color,
        width=2,
    )


def _dump_ocr(
    ocr: OcrEngine,
    crop,
    label: str,
    *,
    upscale: int = 1,
    high_contrast: bool = False,
) -> None:
    results = ocr.recognize(crop, upscale=upscale, high_contrast=high_contrast)
    if not results:
        print(f"    {label}: (nessuna riga OCR)")
        return
    for r in results:
        print(f"    {label}: text={r.text!r} conf={r.confidence:.3f}")


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

    ga = compute_game_area(frame.width, frame.height, layout)
    print(f"frame: {frame.width}x{frame.height}  game_area: x={ga.x} y={ga.y} w={ga.w} h={ga.h}\n")

    overlay = frame.image.copy()
    draw = ImageDraw.Draw(overlay)

    ocr = OcrEngine()

    tm = rois.team_menu
    for i in range(len(tm.slot_areas)):
        name_rect = roi_to_pixels(tm.slot_areas[i], ga)
        icon_rect = roi_to_pixels(tm.slot_icons[i], ga)
        level_rect = roi_to_pixels(tm.slot_levels[i], ga)

        name_crop = frame.image.crop(name_rect.as_crop_box())
        icon_crop = frame.image.crop(icon_rect.as_crop_box())
        level_crop = frame.image.crop(level_rect.as_crop_box())

        name_crop.save(OUT_DIR / f"team-slot-{i}-name.png")
        icon_crop.save(OUT_DIR / f"team-slot-{i}-icon.png")
        level_crop.save(OUT_DIR / f"team-slot-{i}-level.png")

        _draw_rect(draw, name_rect, COLOR_NAME)
        _draw_rect(draw, icon_rect, COLOR_ICON)
        _draw_rect(draw, level_rect, COLOR_LEVEL)

        print(f"[slot {i}]")
        print(f"    name  rect=({name_rect.x},{name_rect.y}, {name_rect.w}x{name_rect.h})")
        print(f"    icon  rect=({icon_rect.x},{icon_rect.y}, {icon_rect.w}x{icon_rect.h})")
        print(f"    level rect=({level_rect.x},{level_rect.y}, {level_rect.w}x{level_rect.h})")
        _dump_ocr(ocr, name_crop, "OCR name ")
        _dump_ocr(ocr, level_crop, "OCR level", upscale=4, high_contrast=True)

    overlay.save(OUT_DIR / "team-menu-overlay.png")
    print(f"\n[overlay] {OUT_DIR / 'team-menu-overlay.png'}")

    # Recognize completo per verdetto per slot.
    print("\n=== recognize_team output ===")
    with PokemonRepository.open(DB_PATH) as repo:
        recognizer = Recognizer(repo, ocr)
        results = recognizer.recognize_team(frame.image, layout, rois, generation)
        for res in results:
            name = "-"
            if res.pokemon_id is not None:
                pokemon = repo.get_by_id(res.pokemon_id)
                name = pokemon.name_it if pokemon else f"#{res.pokemon_id}"
            print(
                f"[slot {res.slot_index}] name={name!r:20} level={res.level} "
                f"conf={res.confidence:.2f} src={res.source} ocr={res.ocr_text!r}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
