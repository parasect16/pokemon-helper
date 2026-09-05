"""Estrae ROI dal PNG annotato a mano dall'utente.

L'immagine di input è uno screenshot client-area dell'emulatore su cui
l'utente ha disegnato rettangoli di tre colori distinti:

- **magenta** `(255,   0, 255)` = riquadro nome Pokemon
- **ciano**   `(  0, 255, 255)` = icona Pokemon (mini sprite menu)
- **giallo**  `(255, 255,   0)` = riquadro livello `L.XX`

Il flusso:

1. Segmenta l'immagine per ciascun colore (soglie RGB asimmetriche con
   tolleranza per gestire l'antialiasing dei bordi).
2. Trova le componenti connesse (`scipy.ndimage.label`) e calcola il
   bounding box di ciascuna.
3. Ordina i 6 bbox in ordine FRLG: slot 0 = riquadro attivo in colonna
   sinistra (più grande), slot 1-5 = colonna destra dall'alto in basso.
4. Normalizza i bbox in coordinate `Roi` (0..1) relative al game area.
5. Stampa il confronto vs `ROIS_FIRERED.team_menu` per revisione manuale.

Uso:
    python scripts/extract_roi_from_annotated.py data/roi-annotated-team.png

Precondizione: lo screenshot NON deve includere il menu bar mGBA
(assumiamo cattura client-area). Se invece include il menu, passare
`--menu-offset 30`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

# Rende importabile `pokemon_helper` senza `pip install -e .` in questo venv.
_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from pokemon_helper.vision.roi import (  # noqa: E402
    ROIS_FIRERED,
    GameLayout,
    PixelRect,
    Roi,
    compute_game_area,
)

# Colori target: (nome_semantico, RGB, etichetta_italiana).
COLORS: dict[str, tuple[tuple[int, int, int], str]] = {
    "name": ((255, 0, 255), "magenta"),
    "icon": ((0, 255, 255), "ciano"),
    "level": ((255, 255, 0), "giallo"),
}

# Tolleranza per canale RGB. Bordi antialiased possono avere pixel con canali
# saturi non a 255 (es. 220) e canale spento non a 0 (es. 30). 40 restringe
# rispetto a UI Pokemon (barra HP gialla ha G~200, teal menu B~200) senza
# perdere il core del bordo user.
TOLERANCE = 40

# Numero atteso di rettangoli per colore (6 slot squadra).
EXPECTED_COUNT = 6
# Filtro dimensionale: componenti con lato più piccolo sotto N pixel = rumore.
MIN_SIDE_PIXELS = 15
# Spessore del tratto disegnato a mano (px per lato) da rimuovere dal bbox
# per avvicinarsi al rettangolo interno che l'utente intendeva marcare.
STROKE_INSET = 2


def _mask_for_color(arr: np.ndarray, target: tuple[int, int, int]) -> np.ndarray:
    """Maschera booleana dei pixel vicini a `target` per canale."""
    high = 255 - TOLERANCE
    low = TOLERANCE
    checks: list[np.ndarray] = []
    for chan_idx, tval in enumerate(target):
        chan = arr[..., chan_idx]
        # Canale saturo (>=200 nel target) → richiedi >= high.
        # Canale spento (<50 nel target) → richiedi <= low.
        if tval >= 200:
            checks.append(chan >= high)
        else:
            checks.append(chan <= low)
    return checks[0] & checks[1] & checks[2]


def _find_bboxes(mask: np.ndarray) -> list[PixelRect]:
    """Bounding box (`PixelRect`) di ogni componente connessa della maschera.

    Applica una dilatazione 5x5 prima del labeling per fondere pixel
    isolati adiacenti dovuti ad antialiasing dei bordi (un rettangolo
    disegnato a mano può altrimenti apparire come 4 segmenti disconnessi).
    Le bbox restituite sono comunque calcolate sui pixel originari, non
    su quelli dilatati, per accuracy.
    """
    # Closing (dilate + erode) chiude i piccoli gap dell'antialiasing senza
    # fondere box adiacenti. `iterations=1` con struttura 3x3 di default =
    # kernel effettivo 3x3, che colma buchi ≤ 1 px ma preserva gap ≥ 3 px.
    closed = ndimage.binary_closing(mask, iterations=1)
    labeled, num = ndimage.label(closed)
    candidates: list[tuple[int, PixelRect]] = []  # (pixel_count, bbox)
    for label_id in range(1, num + 1):
        component = labeled == label_id
        original_pixels = component & mask
        ys, xs = np.where(original_pixels)
        if len(xs) == 0:
            continue
        x0, x1 = int(xs.min()), int(xs.max())
        y0, y1 = int(ys.min()), int(ys.max())
        # Inset dello spessore del tratto: il bbox tocca il bordo esterno
        # dello stroke user (~2-3 px), ma il contenuto vero è dentro. Restringi
        # di STROKE_INSET pixel per lato per approssimare il rettangolo
        # interno che l'utente intendeva marcare.
        x0 += STROKE_INSET
        y0 += STROKE_INSET
        x1 -= STROKE_INSET
        y1 -= STROKE_INSET
        w, h = x1 - x0 + 1, y1 - y0 + 1
        if min(w, h) < MIN_SIDE_PIXELS:
            continue
        candidates.append((int(len(xs)), PixelRect(x=x0, y=y0, w=w, h=h)))
    # Prendi le EXPECTED_COUNT componenti con più pixel di outline: bordi user
    # sono continui e producono ordini di grandezza più pixel di eventuali
    # macchie sparse (colori simili nell'UI di gioco che superano la soglia).
    candidates.sort(key=lambda pair: pair[0], reverse=True)
    return [box for _, box in candidates[:EXPECTED_COUNT]]


def _sort_slots_firered(boxes: list[PixelRect], image_width: int) -> list[PixelRect]:
    """Ordina i 6 bbox in ordine slot FRLG.

    FRLG mostra il Pokemon attivo (slot 0) in un riquadro grande a sinistra e
    gli altri 5 slot allineati in una colonna a destra dall'alto in basso.
    Discriminante robusto: il box con x minima è lo slot 0, purché gli altri
    5 siano clusterati fra loro entro `image_width * 0.15`.
    """
    if len(boxes) != 6:
        raise RuntimeError(f"trovati {len(boxes)} box, atteso 6")
    sorted_by_x = sorted(boxes, key=lambda b: b.x)
    active = sorted_by_x[0]
    others = sorted_by_x[1:]
    xs = [b.x for b in others]
    if max(xs) - min(xs) > image_width * 0.15:
        raise RuntimeError(f"5 slot dx non clusterati: x range = {min(xs)}..{max(xs)}")
    if others[0].x - active.x < image_width * 0.1:
        raise RuntimeError(
            f"slot attivo non ben separato dal cluster dx: dx = {others[0].x - active.x}"
        )
    others.sort(key=lambda b: b.y)
    return [active, *others]


def _bbox_to_roi(box: PixelRect, game_area: PixelRect) -> Roi:
    """Normalizza il bbox pixel in `Roi` (0..1) sul game area."""
    return Roi(
        x=(box.x - game_area.x) / game_area.w,
        y=(box.y - game_area.y) / game_area.h,
        w=box.w / game_area.w,
        h=box.h / game_area.h,
    )


def _fmt_roi(roi: Roi) -> str:
    return f"Roi(x={roi.x:.3f}, y={roi.y:.3f}, w={roi.w:.3f}, h={roi.h:.3f})"


def _diff_pct(a: float, b: float) -> str:
    """Percentuale di scostamento relativo, formattata."""
    if a == 0:
        return "∞" if b != 0 else "0"
    return f"{(b - a) / a * 100:+.1f}%"


def main() -> None:
    parser = argparse.ArgumentParser(description="Estrae ROI da PNG annotato.")
    parser.add_argument("path", type=Path, help="PNG annotato (magenta/ciano/giallo).")
    parser.add_argument(
        "--menu-offset",
        type=int,
        default=0,
        help="Altezza menu bar in pixel (0 se cattura client-area).",
    )
    args = parser.parse_args()

    img = Image.open(args.path).convert("RGBA")
    arr = np.array(img)
    print(f"immagine: {img.width}x{img.height} px, menu_offset={args.menu_offset}")

    layout = GameLayout(aspect_ratio=240 / 160, menu_offset_top=args.menu_offset)
    game_area = compute_game_area(img.width, img.height, layout)
    print(f"game area: x={game_area.x} y={game_area.y} w={game_area.w} h={game_area.h}\n")

    current: dict[str, tuple[Roi, ...]] = {
        "name": ROIS_FIRERED.team_menu.slot_areas,
        "icon": ROIS_FIRERED.team_menu.slot_icons,
        "level": ROIS_FIRERED.team_menu.slot_levels,
    }

    extracted: dict[str, list[Roi]] = {}

    for key, (color, italian) in COLORS.items():
        mask = _mask_for_color(arr, color)
        boxes = _find_bboxes(mask)
        print(f"=== {key.upper()} ({italian}) — {len(boxes)} componenti trovate ===")
        try:
            boxes = _sort_slots_firered(boxes, img.width)
        except RuntimeError as exc:
            print(f"  errore: {exc}\n")
            continue
        rois: list[Roi] = []
        for i, (box, cur_roi) in enumerate(zip(boxes, current[key], strict=True)):
            new_roi = _bbox_to_roi(box, game_area)
            rois.append(new_roi)
            print(f"slot {i}: pixel=(x={box.x} y={box.y} w={box.w} h={box.h})")
            print(f"  attuale: {_fmt_roi(cur_roi)}")
            print(f"  nuovo:   {_fmt_roi(new_roi)}")
            print(
                f"  delta:   dx={_diff_pct(cur_roi.x, new_roi.x)} "
                f"dy={_diff_pct(cur_roi.y, new_roi.y)} "
                f"dw={_diff_pct(cur_roi.w, new_roi.w)} "
                f"dh={_diff_pct(cur_roi.h, new_roi.h)}"
            )
        extracted[key] = rois
        print()

    # Blocco copy-paste pronto per `roi.py`.
    if len(extracted) == 3:
        print("=" * 72)
        print("Snippet pronto per src/pokemon_helper/vision/roi.py (team_menu):")
        print("=" * 72)
        print("team_menu=TeamMenuRois(")
        groups = (
            ("name", "slot_areas"),
            ("icon", "slot_icons"),
            ("level", "slot_levels"),
        )
        for group, label in groups:
            print(f"    {label}=(")
            for i, roi in enumerate(extracted[group]):
                comment = "slot attivo" if i == 0 else f"slot {i}"
                coords = f"x={roi.x:.3f}, y={roi.y:.3f}, w={roi.w:.3f}, h={roi.h:.3f}"
                print(f"        Roi({coords}),  # {comment}")
            print("    ),")
        print("),")


if __name__ == "__main__":
    main()
