"""Smoke test manuale della cattura finestra.

Uso:
    python scripts/capture_test.py [title_substring]

Se `title_substring` non è passato usa "mGBA". Salva il frame catturato in
`data/capture-test.png` e stampa dimensioni.
"""

from __future__ import annotations

import sys
from pathlib import Path

from pokemon_helper.vision.capture import CaptureError, WindowCapture


def main() -> int:
    title = sys.argv[1] if len(sys.argv) > 1 else "mGBA"
    print(f"[capture] target: '{title}'")
    capture = WindowCapture(title)
    try:
        frame = capture.capture_frame(timeout_seconds=5.0)
    except (CaptureError, TimeoutError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    out = Path(__file__).resolve().parent.parent / "data" / "capture-test.png"
    frame.image.save(out)
    print(f"[ok] {frame.width}x{frame.height} salvato in {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
