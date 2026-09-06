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

from PySide6.QtCore import Qt, QTimer, Signal
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

    def fit_height(self) -> None:
        """Riporta l'altezza a quella richiesta dal contenuto, larghezza invariata.

        Qt allarga la finestra quando il contenuto cresce (le card avversario
        che compaiono a inizio combattimento) ma non la restringe quando il
        contenuto torna piccolo. Senza questo, uscendo dal combattimento resta
        una finestra alta e mezza vuota.

        Il ridimensionamento è differito di un giro di event loop: chiamato
        subito dopo il cambio di contenuto leggerebbe un `sizeHint` calcolato
        sul layout non ancora aggiornato.
        """
        QTimer.singleShot(0, self._apply_fit_height)

    def _apply_fit_height(self) -> None:
        content = self.centralWidget()
        if content is not None:
            content.updateGeometry()
        self.resize(self.width(), self.sizeHint().height())

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
