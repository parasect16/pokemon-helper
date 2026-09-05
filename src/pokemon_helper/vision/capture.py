"""Cattura di una finestra Windows come `PIL.Image`.

Sottile wrapper attorno a `windows_capture.WindowsCapture` (binding Python
di Windows Graphics Capture API). Il modello nativo è event-based (callback
per ogni frame); qui lo trasformiamo in un metodo sincrono
`capture_frame()` che:

1. Avvia la cattura sulla finestra il cui titolo contiene la substring data.
2. Attende il primo frame (con timeout).
3. Copia il buffer BGRA in RAM Python.
4. Ferma la cattura.
5. Ritorna un `PIL.Image` in modalità RGB.

Questa strategia va bene per riconoscimento su-richiesta (F3). Per uso
continuativo (F4 template-match live) potrà servire un wrapper con coda.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

from PIL import Image
from windows_capture import WindowsCapture


class CaptureError(RuntimeError):
    """Errore durante la cattura di una finestra."""


@dataclass(frozen=True, slots=True)
class CapturedFrame:
    """Frame catturato con metadati minimali."""

    image: Image.Image  # PIL RGB
    width: int
    height: int


class WindowCapture:
    """Cattura on-demand di una finestra identificata per substring del titolo."""

    def __init__(self, title_substring: str) -> None:
        """Prepara un capturer che punta a finestre il cui titolo contiene la substring.

        Non alza qui se la finestra non esiste: il fallimento arriva al primo
        `capture_frame()` (con `CaptureError` o `TimeoutError`).
        """
        self._title = title_substring

    def capture_frame(self, timeout_seconds: float = 5.0) -> CapturedFrame:
        """Cattura un singolo frame e ritorna `CapturedFrame`.

        Alza `TimeoutError` se nessun frame arriva entro `timeout_seconds`.
        Alza `CaptureError` se la sessione termina senza produrre un frame
        (es. finestra non trovata, cattura negata dal sistema).
        """
        # Contenitori per marshalling dal thread callback al chiamante.
        buffer_holder: dict[str, object] = {}
        done = threading.Event()

        # Non passiamo `draw_border`: su alcune build di Windows la Graphics
        # Capture API non supporta il toggle e alza `GraphicsCaptureError`.
        session = WindowsCapture(
            window_name=self._title,
            cursor_capture=False,
        )

        @session.event
        def on_frame_arrived(frame, capture_control) -> None:
            # `frame.frame_buffer` è una vista sul buffer nativo: va copiata
            # prima di fermare la cattura, altrimenti diventa invalida.
            bgra_copy = frame.frame_buffer.copy()
            buffer_holder["bgra"] = bgra_copy
            buffer_holder["width"] = frame.width
            buffer_holder["height"] = frame.height
            capture_control.stop()
            done.set()

        @session.event
        def on_closed() -> None:
            # Se la sessione si chiude prima del primo frame (es. finestra
            # non trovata), sblocca il chiamante impostando l'evento.
            done.set()

        try:
            session.start_free_threaded()
        except Exception as exc:
            raise CaptureError(f"impossibile avviare la cattura: {exc}") from exc

        if not done.wait(timeout_seconds):
            raise TimeoutError(
                f"nessun frame ricevuto entro {timeout_seconds}s "
                f"dalla finestra con titolo che contiene '{self._title}'"
            )

        if "bgra" not in buffer_holder:
            raise CaptureError(
                f"cattura terminata senza produrre frame — finestra con titolo "
                f"che contiene '{self._title}' non trovata o non catturabile"
            )

        bgra = buffer_holder["bgra"]  # numpy (H, W, 4)
        # windows-capture usa layout BGRA. PIL vuole RGBA per il costruttore
        # Image.fromarray in modalità RGBA. Scambio canali B ↔ R.
        rgba = bgra[..., [2, 1, 0, 3]]
        image = Image.fromarray(rgba, mode="RGBA").convert("RGB")
        return CapturedFrame(
            image=image,
            width=int(buffer_holder["width"]),
            height=int(buffer_holder["height"]),
        )
