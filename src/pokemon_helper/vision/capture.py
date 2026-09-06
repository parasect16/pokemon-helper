"""Cattura di una finestra Windows come `PIL.Image`.

Sottile wrapper attorno a `windows_capture.WindowsCapture` (binding Python
di Windows Graphics Capture API). Il modello nativo è event-based — un
callback per ogni frame — e qui diventa il metodo sincrono `capture_frame()`.

La sessione di cattura è **persistente**: si apre alla prima richiesta e
resta viva. La versione precedente ne apriva e chiudeva una per ogni frame,
il che costava ~90 ms a cattura e faceva lampeggiare il bordo che Windows
disegna attorno alla finestra catturata — con l'auto-detect di F4 attivo,
due volte al secondo.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

# Import apparentemente fuori posto, in realtà obbligatorio qui.
#
# `imagehash.phash` fa `import scipy.fftpack` *dentro* la funzione. Se quel
# primo import avviene dopo che `windows_capture` ha inizializzato il proprio
# runtime, caricare le DLL di scipy fa segfaultare la cattura successiva: il
# processo muore senza traceback. Sequenza minima per riprodurlo:
#
#     cap.capture_frame(); imagehash.phash(img); cap.capture_frame()  # SIGSEGV
#
# Non dipende dal thread — succede anche con cattura e hash sempre sullo
# stesso worker persistente. Anticipando l'import qui, scipy è già caricato
# prima che qualunque cattura possa partire, perché per catturare bisogna per
# forza importare questo modulo. Costa ~340 ms una tantum all'import.
#
# Se un giorno `sprite_hash` smettesse di usare imagehash, questo import può
# sparire — ma va tolto verificando la sequenza qui sopra, non a occhio.
import scipy.fftpack  # noqa: F401
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
    """Cattura di una finestra tramite una sessione persistente.

    La prima versione apriva e chiudeva una sessione a ogni frame. Funzionava,
    ma costava ~90 ms per cattura e soprattutto faceva **lampeggiare** il bordo
    che Windows disegna attorno alla finestra catturata: con l'auto-detect
    attivo, due volte al secondo. Un bordo fisso si dimentica, uno che
    lampeggia no.

    Qui la sessione resta aperta e i frame arrivano di continuo sul thread
    della capture. Il callback però **non copia** ogni frame: a 150 fps su
    una finestra 1119x734 sarebbero ~490 MB/s di memcpy buttati via. Copia
    solo quando `capture_frame` lo chiede, tramite una coppia di eventi
    richiesta/risposta; l'attesa è quella di un frame, qualche millisecondo.

    La sessione viene riavviata da sola se muore, il che succede ogni volta
    che l'emulatore viene chiuso e riaperto.
    """

    def __init__(self, title_substring: str) -> None:
        """Prepara un capturer che punta a finestre col titolo dato.

        Non apre nulla: la sessione parte alla prima `capture_frame()`, così
        costruire l'oggetto resta gratuito e sicuro anche senza emulatore.
        """
        self._title = title_substring
        self._control: object | None = None
        self._requested = threading.Event()
        self._ready = threading.Event()
        self._closed = threading.Event()
        self._frame: tuple[object, int, int] | None = None
        self._lock = threading.Lock()

    def capture_frame(self, timeout_seconds: float = 5.0) -> CapturedFrame:
        """Ritorna il primo frame disponibile dopo la richiesta.

        Alza `TimeoutError` se non ne arriva nessuno entro `timeout_seconds`,
        `CaptureError` se la sessione non parte o muore senza produrre nulla.
        """
        self._ensure_session()

        self._ready.clear()
        with self._lock:
            self._frame = None
        self._requested.set()

        if not self._ready.wait(timeout_seconds):
            self._requested.clear()
            if self._closed.is_set():
                raise CaptureError(
                    f"la cattura si è chiusa senza produrre frame — finestra con "
                    f"titolo che contiene '{self._title}' non trovata o non catturabile"
                )
            raise TimeoutError(
                f"nessun frame ricevuto entro {timeout_seconds}s "
                f"dalla finestra con titolo che contiene '{self._title}'"
            )

        with self._lock:
            frame = self._frame
        if frame is None:
            # `on_closed` sblocca l'attesa senza fornire un frame: l'emulatore
            # è stato chiuso mentre la richiesta era in volo.
            raise CaptureError(
                f"la cattura si è chiusa senza produrre frame — finestra con "
                f"titolo che contiene '{self._title}' non trovata o non catturabile"
            )

        bgra, width, height = frame
        # windows-capture usa layout BGRA. PIL vuole RGBA per il costruttore
        # `Image.fromarray` in modalità RGBA: scambio canali B ↔ R.
        rgba = bgra[..., [2, 1, 0, 3]]
        image = Image.fromarray(rgba, mode="RGBA").convert("RGB")
        return CapturedFrame(image=image, width=width, height=height)

    def close(self) -> None:
        """Chiude la sessione. Sicura da chiamare più volte."""
        control, self._control = self._control, None
        self._closed.set()
        if control is None:
            return
        try:
            control.stop()
        except Exception as exc:  # noqa: BLE001 — in chiusura non c'è nulla da salvare
            print(f"[capture] errore chiudendo la sessione: {exc}")

    def stop(self) -> None:
        """Alias di `close()`.

        L'app ferma tutti i componenti di lunga durata con `.stop()`: avere
        lo stesso nome evita un caso particolare solo per la cattura.
        """
        self.close()

    # ------------------------------------------------------------------ interni

    def _ensure_session(self) -> None:
        """Avvia la sessione se non c'è, o se è morta."""
        if self._control is not None and not self._closed.is_set():
            return
        if self._control is not None:
            # Sessione morta: l'emulatore è stato chiuso. Ripulisci e riparti.
            self.close()

        self._closed.clear()
        # Non passiamo `draw_border`: su alcune build di Windows la Graphics
        # Capture API non supporta il toggle e alza `GraphicsCaptureError`.
        session = WindowsCapture(window_name=self._title, cursor_capture=False)

        @session.event
        def on_frame_arrived(frame, capture_control) -> None:  # noqa: ARG001
            # Copia solo se qualcuno ha chiesto un frame: `frame.frame_buffer`
            # è una vista sul buffer nativo, valida solo dentro il callback.
            if not self._requested.is_set():
                return
            with self._lock:
                self._frame = (frame.frame_buffer.copy(), frame.width, frame.height)
            self._requested.clear()
            self._ready.set()

        @session.event
        def on_closed() -> None:
            # Sblocca un'eventuale attesa in corso: senza questo, chiudere
            # l'emulatore durante una cattura costerebbe il timeout pieno.
            self._closed.set()
            self._ready.set()

        try:
            self._control = session.start_free_threaded()
        except Exception as exc:
            self._closed.set()
            raise CaptureError(f"impossibile avviare la cattura: {exc}") from exc
