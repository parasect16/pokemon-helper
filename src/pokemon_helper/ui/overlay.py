"""Finestra companion Windows: chrome nativo, sempre in primo piano.

`CompanionWindow` è una `QMainWindow` con chrome di sistema (barra del
titolo, pulsanti minimize / close standard, drag nativo, voce in taskbar).
Rimane sempre sopra le altre finestre grazie a `Qt.WindowStaysOnTopHint`
per accompagnare il gioco senza sovrapporsi.

Emette:
- `positionChanged(int, int)` a ogni cambio di posizione (persistito su
  disco dal layer app).
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMoveEvent
from PySide6.QtWidgets import QMainWindow, QWidget


class CompanionWindow(QMainWindow):
    """Finestra "companion" sempre in primo piano con chrome nativo."""

    positionChanged = Signal(int, int)

    def __init__(self, content: QWidget) -> None:
        """Costruisce la finestra attorno al widget di contenuto."""
        super().__init__()
        self.setWindowTitle("pokemon-helper")
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setCentralWidget(content)
        # `moveEvent` viene chiamato di frequente durante il drag: teniamo
        # traccia della posizione base per evitare emissioni ripetute al
        # primo show / restore.
        self._last_emitted: tuple[int, int] | None = None

    def move_to(self, x: int, y: int) -> None:
        """Sposta la finestra a coordinate assolute dello schermo."""
        self.move(x, y)

    def toggle_visibility(self) -> None:
        """Alterna la visibilità della finestra (nasconde o mostra ripristinando).

        Se minimizzata, `show()` la riporta allo stato precedente.
        """
        if self.isVisible() and not self.isMinimized():
            self.hide()
            return
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def moveEvent(self, event: QMoveEvent) -> None:
        """Emette `positionChanged` per persistere la nuova posizione."""
        super().moveEvent(event)
        new_pos = (self.x(), self.y())
        if new_pos != self._last_emitted:
            self._last_emitted = new_pos
            self.positionChanged.emit(*new_pos)
