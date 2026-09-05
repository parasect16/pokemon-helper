"""Overlay Windows senza bordi, sempre in primo piano.

`OverlayWindow` è un contenitore che riceve un `QWidget` di contenuto e lo
mostra dentro una finestra:

- frameless (`Qt.FramelessWindowHint`),
- sempre in primo piano (`Qt.WindowStaysOnTopHint`),
- senza voce nella taskbar (`Qt.Tool`),
- con sfondo traslucido (`WA_TranslucentBackground`),
- trascinabile con il tasto sinistro del mouse.

Il click-through (la finestra non intercetta il mouse, passa attraverso al
software sottostante) è implementato via Win32 impostando gli extended
window styles `WS_EX_LAYERED | WS_EX_TRANSPARENT`. Su piattaforme diverse
da Windows la chiamata è un no-op silenzioso: la finestra rimane cliccabile.

Il widget emette `positionChanged(int, int)` al rilascio del mouse dopo
un drag e `clickThroughChanged(bool)` a ogni cambio di modalità: il layer
applicativo li usa per persistere lo stato su disco.
"""

from __future__ import annotations

import ctypes
import sys

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QVBoxLayout, QWidget

# Costanti Win32 usate per il click-through via SetWindowLongW / GetWindowLongW.
_GWL_EXSTYLE = -20
_WS_EX_LAYERED = 0x00080000
_WS_EX_TRANSPARENT = 0x00000020


class OverlayWindow(QWidget):
    """Finestra overlay che ospita un widget di contenuto."""

    positionChanged = Signal(int, int)
    clickThroughChanged = Signal(bool)

    def __init__(self, content: QWidget) -> None:
        """Costruisce l'overlay attorno al widget `content` (full-bleed)."""
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(content)

        self._drag_offset: QPoint | None = None
        self._click_through: bool = False

    # ------------------------------------------------------------------ API

    def move_to(self, x: int, y: int) -> None:
        """Sposta l'overlay a coordinate assolute dello schermo."""
        self.move(x, y)

    def toggle_visibility(self) -> None:
        """Alterna visibile/nascosto. Chiamare dal thread GUI di Qt."""
        self.setVisible(not self.isVisible())

    @property
    def click_through_enabled(self) -> bool:
        return self._click_through

    def set_click_through(self, enabled: bool) -> None:
        """Attiva/disattiva il click-through (solo Windows nativo).

        Su piattaforme non-Windows la funzione registra lo stato interno ma
        non modifica il comportamento del mouse (silenzioso, per facilitare
        lo sviluppo su altri OS).
        """
        if self._click_through == enabled:
            return
        self._click_through = enabled
        if sys.platform == "win32":
            self._apply_click_through_windows(enabled)
        self.clickThroughChanged.emit(enabled)

    # ----------------------------------------------------- click-through win32

    def _apply_click_through_windows(self, enabled: bool) -> None:
        """Modifica gli extended styles Win32 per il click-through."""
        hwnd = int(self.winId())
        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        ex_style = user32.GetWindowLongW(hwnd, _GWL_EXSTYLE)
        if enabled:
            ex_style |= _WS_EX_TRANSPARENT | _WS_EX_LAYERED
        else:
            ex_style &= ~_WS_EX_TRANSPARENT
        user32.SetWindowLongW(hwnd, _GWL_EXSTYLE, ex_style)

    # ------------------------------------------------------------ drag events

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Inizio drag: memorizza offset tra puntatore e origine finestra."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Drag in corso: sposta la finestra seguendo il puntatore."""
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Fine drag: emette `positionChanged` per far persistere la posizione."""
        if event.button() == Qt.MouseButton.LeftButton and self._drag_offset is not None:
            self._drag_offset = None
            self.positionChanged.emit(self.x(), self.y())
            event.accept()
            return
        super().mouseReleaseEvent(event)
