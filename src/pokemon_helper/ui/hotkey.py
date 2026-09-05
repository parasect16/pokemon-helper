"""Registrazione di una hotkey globale di sistema.

Sottile wrapper attorno a `pynput.keyboard.GlobalHotKeys`. Il callback viene
invocato sul thread interno di pynput, non su quello principale di Qt: se il
callback deve modificare la UI, il chiamante deve accodare l'operazione sul
thread GUI (per esempio emettendo una `Signal` di un QObject vivente sul
thread principale, oppure via `QMetaObject.invokeMethod`).

Formato della combinazione — sintassi pynput. Esempi:
    "<ctrl>+<alt>+p"
    "<ctrl>+<shift>+h"

Nota: pynput su Windows non richiede privilegi di amministratore per hotkey
globali; su alcune distribuzioni Linux (X11) può richiedere invece i
permessi di accesso agli eventi di input.
"""

from __future__ import annotations

from collections.abc import Callable

from pynput import keyboard

DEFAULT_TOGGLE_COMBO: str = "<ctrl>+<alt>+p"


class GlobalHotkey:
    """Wrapper per una singola hotkey globale con lifecycle esplicito.

    Uso tipico:

        hk = GlobalHotkey("<ctrl>+<alt>+p", on_toggle_overlay)
        hk.start()
        ...
        hk.stop()
    """

    def __init__(self, combo: str, callback: Callable[[], None]) -> None:
        self._combo = combo
        self._callback = callback
        self._listener: keyboard.GlobalHotKeys | None = None

    @property
    def is_running(self) -> bool:
        """True se la hotkey è attualmente registrata."""
        return self._listener is not None

    def start(self) -> None:
        """Attiva la hotkey. No-op se già attiva."""
        if self._listener is not None:
            return
        self._listener = keyboard.GlobalHotKeys({self._combo: self._callback})
        self._listener.start()

    def stop(self) -> None:
        """Disattiva la hotkey e rilascia il thread di ascolto."""
        if self._listener is None:
            return
        self._listener.stop()
        self._listener = None
