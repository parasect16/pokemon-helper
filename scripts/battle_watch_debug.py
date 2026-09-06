"""Osserva mGBA e stampa gli eventi di battaglia rilevati (F4).

Riproduce senza GUI ciò che fa `_BattlePoller`: cattura a intervalli
regolari, classifica il frame con `is_battle_screen`, calcola la firma del
nome avversario e passa il tutto a `BattleWatcher`.

Uso:
    python scripts/battle_watch_debug.py [secondi] [intervallo_ms]

Default: 30 secondi a 500 ms. Entra e esci da un combattimento, cambia
Pokemon o fallo cambiare all'avversario, e verifica che compaiano ENTERED, LEFT e
COMBATANTS_CHANGED nei momenti giusti.
"""

from __future__ import annotations

import io
import sys
import time
from pathlib import Path

# I nomi con ♀/♂ non passano dalla console cp1252 di Windows.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
else:  # pragma: no cover
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pokemon_helper.vision.battle_detector import is_battle_screen  # noqa: E402
from pokemon_helper.vision.battle_watcher import BattleWatcher  # noqa: E402
from pokemon_helper.vision.capture import CaptureError, WindowCapture  # noqa: E402
from pokemon_helper.vision.ocr import OcrEngine  # noqa: E402
from pokemon_helper.vision.roi import (  # noqa: E402
    GAME_ROIS,
    compute_game_area,
    roi_to_pixels,
)

GAME = "firered"


def main() -> int:
    duration = float(sys.argv[1]) if len(sys.argv) > 1 else 30.0
    interval = (float(sys.argv[2]) if len(sys.argv) > 2 else 500.0) / 1000.0

    layout, rois = GAME_ROIS[GAME]
    capture = WindowCapture("mGBA")
    watcher = BattleWatcher()
    ocr = OcrEngine()
    ocr.warm_up()

    print(f"osservo per {duration:.0f}s ogni {interval * 1000:.0f}ms — Ctrl+C per fermare")
    deadline = time.monotonic() + duration
    polls = 0
    while time.monotonic() < deadline:
        started = time.monotonic()
        in_battle, signature = _probe(capture, ocr, layout, rois)
        event = watcher.observe(in_battle, signature)
        polls += 1
        if event is not None:
            stamp = time.strftime("%H:%M:%S")
            print(f"[{stamp}] {event.name:19} firma={signature or '-'}")
        elapsed = time.monotonic() - started
        time.sleep(max(0.0, interval - elapsed))

    print(f"\n{polls} poll, stato finale: {'in battaglia' if watcher.in_battle else 'fuori'}")
    return 0


def _probe(capture: WindowCapture, ocr: OcrEngine, layout, rois) -> tuple[bool, tuple | None]:
    """Come `_BattlePoller.probe`: stato di battaglia + testo dei due nomi."""
    try:
        frame = capture.capture_frame(timeout_seconds=3.0).image
    except CaptureError, TimeoutError:
        return False, None
    in_battle, _ = is_battle_screen(frame, layout, rois)
    if not in_battle:
        return False, None
    game_area = compute_game_area(frame.width, frame.height, layout)
    signature = tuple(
        _first_text(ocr.recognize(frame.crop(roi_to_pixels(roi, game_area).as_crop_box())))
        for roi in (rois.opponent_name, rois.player_name)
    )
    return True, signature


def _first_text(results) -> str:
    return results[0].text if results else ""


if __name__ == "__main__":
    raise SystemExit(main())
