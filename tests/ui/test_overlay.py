"""Test di `ui.overlay.CompanionWindow`.

La finestra fa tre cose osservabili: si ridimensiona sull'ingombro del
contenuto quando le card avversario compaiono o spariscono, alterna la
visibilità dalla hotkey globale, e annuncia la propria posizione perché
l'app layer la persista.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from pokemon_helper.ui import overlay as overlay_module
from pokemon_helper.ui.overlay import CompanionWindow


class _FakeTimer:
    """`QTimer` finto: `fit_height` differisce di un giro di event loop."""

    def __init__(self) -> None:
        self.calls: list[tuple[int, object]] = []

    def singleShot(self, msec, callback) -> None:  # noqa: N802 — firma di Qt
        self.calls.append((msec, callback))

    def fire_all(self) -> None:
        calls, self.calls = self.calls, []
        for _msec, callback in calls:
            callback()


class _Content(QWidget):
    """Contenuto ad altezza variabile: simula le card che vanno e vengono."""

    def __init__(self) -> None:
        super().__init__()
        self._layout = QVBoxLayout(self)
        self._extra: QLabel | None = None

    def grow(self) -> None:
        self._extra = QLabel("x" * 10, self)
        self._extra.setFixedHeight(200)
        self._layout.addWidget(self._extra)

    def shrink(self) -> None:
        if self._extra is not None:
            self._layout.removeWidget(self._extra)
            self._extra.setParent(None)
            self._extra = None


@pytest.fixture
def fake_timer(monkeypatch) -> _FakeTimer:
    timer = _FakeTimer()
    monkeypatch.setattr(overlay_module, "QTimer", timer)
    return timer


@pytest.fixture
def window(qtbot) -> CompanionWindow:
    win = CompanionWindow(_Content())
    qtbot.addWidget(win)
    return win


def test_fit_height_is_deferred_by_one_event_loop_turn(window, fake_timer) -> None:
    """Chiamato in presa diretta leggerebbe un sizeHint del layout vecchio."""
    window.fit_height()
    assert [msec for msec, _cb in fake_timer.calls] == [0]


def test_fit_height_shrinks_back_when_the_content_shrinks(window, fake_timer) -> None:
    """Qt allarga la finestra da solo ma non la restringe: è il motivo del metodo."""
    content = window.centralWidget()
    window.resize(320, 200)

    content.grow()
    window.fit_height()
    fake_timer.fire_all()
    grown = window.height()
    assert grown > 200

    content.shrink()
    window.fit_height()
    fake_timer.fire_all()
    assert window.height() < grown


def test_fit_height_leaves_the_width_alone(window, fake_timer) -> None:
    window.resize(345, 200)
    window.centralWidget().grow()
    window.fit_height()
    fake_timer.fire_all()
    assert window.width() == 345


def test_fit_height_survives_a_window_without_content(qtbot, fake_timer) -> None:
    win = CompanionWindow(QWidget())
    qtbot.addWidget(win)
    win.setCentralWidget(None)
    win.fit_height()
    fake_timer.fire_all()  # non deve sollevare


def test_toggle_visibility_hides_a_visible_window(window, qtbot) -> None:
    window.show()
    qtbot.waitExposed(window)
    window.toggle_visibility()
    assert not window.isVisible()


def test_toggle_visibility_shows_a_hidden_window(window) -> None:
    window.hide()
    window.toggle_visibility()
    assert window.isVisible()


def test_toggle_visibility_restores_a_minimized_window(window) -> None:
    """Minimizzata conta come "da mostrare": altrimenti la hotkey la nasconderebbe."""
    window.show()
    window.showMinimized()
    window.toggle_visibility()
    assert window.isVisible()
    assert not window.isMinimized()


def test_moving_the_window_announces_the_new_position(window, qtbot, qapp) -> None:
    window.show()
    qtbot.waitExposed(window)
    seen: list[tuple[int, int]] = []
    window.positionChanged.connect(lambda x, y: seen.append((x, y)))

    window.move(120, 80)
    qapp.processEvents()
    assert seen[-1] == (120, 80)


def test_the_same_position_is_announced_only_once(window, qtbot, qapp) -> None:
    """`moveEvent` arriva a raffica durante il drag: salvare ogni volta è inutile."""
    window.show()
    qtbot.waitExposed(window)
    seen: list[tuple[int, int]] = []
    window.positionChanged.connect(lambda x, y: seen.append((x, y)))

    window.move(140, 90)
    qapp.processEvents()
    window.move(140, 90)
    qapp.processEvents()
    assert seen.count((140, 90)) == 1


def test_move_to_places_the_window_at_absolute_coordinates(window) -> None:
    window.move_to(200, 150)
    assert (window.x(), window.y()) == (200, 150)
