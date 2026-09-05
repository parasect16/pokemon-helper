"""Entry point Qt che assembla tutti i componenti F2.

Responsabilità:
- caricare lo stato persistente (`StateStore`);
- aprire il repository SQLite;
- costruire `TeamPanel` e infilarlo in un `OverlayWindow`;
- collegare i segnali della UI al salvataggio dello stato;
- registrare la hotkey globale (`GlobalHotkey`) per il toggle di visibilità;
- avviare il loop Qt.

Modalità smoke: se la variabile d'ambiente `POKEMON_HELPER_SMOKE=1` è
impostata, l'app si chiude automaticamente dopo ~2 secondi. Utile per
verificare che la UI parta senza errori senza richiedere interazione.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QApplication

from pokemon_helper.data import PokemonRepository
from pokemon_helper.ui.hotkey import DEFAULT_TOGGLE_COMBO, GlobalHotkey
from pokemon_helper.ui.overlay import OverlayWindow
from pokemon_helper.ui.state import (
    AppState,
    StateStore,
    TeamSlot,
    default_state_path,
)
from pokemon_helper.ui.team_panel import TeamPanel


class _HotkeyBridge(QObject):
    """QObject che espone un segnale, emesso dal thread pynput.

    Serve per marshallare l'invocazione della hotkey dal thread di ascolto di
    pynput al thread GUI di Qt: connessione cross-thread di un `Signal`
    forza automaticamente `Qt.QueuedConnection`.
    """

    toggled = Signal()


def default_db_path() -> Path:
    """Path atteso del database SQLite: `<cwd>/data/pokemon.sqlite`."""
    return Path.cwd() / "data" / "pokemon.sqlite"


def run() -> int:
    """Punto d'ingresso: avvia l'applicazione. Ritorna l'exit code di Qt."""
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("pokemon-helper")
    # NB: la finestra ha flag `Qt.Tool` che Qt esclude dal conteggio di
    # `quitOnLastWindowClosed`. Chiediamo quindi un quit esplicito nel
    # wiring dei segnali di chiusura invece di affidarci al default.
    app.setQuitOnLastWindowClosed(False)

    db_path = default_db_path()
    if not db_path.exists():
        print(
            f"ERROR: dataset non trovato in {db_path}\nEsegui: python scripts/build_dataset.py",
            file=sys.stderr,
        )
        return 2

    store = StateStore(default_state_path())
    state = store.load()
    repository = PokemonRepository.open(db_path)

    team_panel = TeamPanel(repository, state)
    overlay = OverlayWindow(team_panel)

    _restore_geometry(app, overlay, state)
    overlay.show()
    # Il click-through va applicato dopo `show()` per avere un winId valido.
    if state.click_through:
        overlay.set_click_through(True)

    _wire_persistence(overlay, team_panel, state, store, app)

    bridge = _HotkeyBridge()
    bridge.toggled.connect(overlay.hotkey_toggle)
    hotkey = GlobalHotkey(DEFAULT_TOGGLE_COMBO, bridge.toggled.emit)
    hotkey.start()

    app.aboutToQuit.connect(hotkey.stop)
    app.aboutToQuit.connect(repository.close)

    if os.environ.get("POKEMON_HELPER_SMOKE") == "1":
        # Modalità smoke: chiudi dopo 2 secondi senza input utente.
        QTimer.singleShot(2000, app.quit)

    return app.exec()


# ---------------------------------------------------------------------------
# Helper interni
# ---------------------------------------------------------------------------


def _restore_geometry(app: QApplication, overlay: OverlayWindow, state: AppState) -> None:
    """Posiziona la finestra: coordinate salvate o angolo alto-destra."""
    if state.overlay_x is not None and state.overlay_y is not None:
        overlay.move_to(state.overlay_x, state.overlay_y)
        return
    screen = app.primaryScreen()
    if screen is None:
        return
    geometry = screen.availableGeometry()
    overlay.move_to(geometry.right() - 380, geometry.top() + 40)


def _wire_persistence(
    overlay: OverlayWindow,
    team_panel: TeamPanel,
    state: AppState,
    store: StateStore,
    app: QApplication,
) -> None:
    """Collega i segnali della UI alla scrittura su disco e al quit."""

    def persist() -> None:
        store.save(state)

    def on_position(x: int, y: int) -> None:
        state.overlay_x = x
        state.overlay_y = y
        persist()

    def on_generation(_gen: int) -> None:
        # state.generation è già stato aggiornato da TeamPanel.
        persist()

    def on_slot(_index: int, _slot: TeamSlot | None) -> None:
        # state.team è già stato aggiornato da TeamPanel.
        persist()

    def on_checkbox_toggled(enabled: bool) -> None:
        # Sorgente: click utente sulla checkbox in header. Applica all'overlay;
        # sarà `overlay.clickThroughChanged` a occuparsi di persistere.
        overlay.set_click_through(enabled)

    def on_click_through_changed(enabled: bool) -> None:
        # Sorgente unica di verità: l'overlay emette dopo qualsiasi cambio
        # (checkbox utente o hotkey). Sincronizza checkbox + salva stato.
        team_panel.sync_click_through(enabled)
        state.click_through = enabled
        persist()

    def on_close() -> None:
        # `Qt.Tool` non conta per quitOnLastWindowClosed: chiediamo quit esplicito.
        overlay.close()
        app.quit()

    overlay.positionChanged.connect(on_position)
    overlay.clickThroughChanged.connect(on_click_through_changed)
    team_panel.generationChanged.connect(on_generation)
    team_panel.slotChanged.connect(on_slot)
    team_panel.clickThroughToggled.connect(on_checkbox_toggled)
    team_panel.closeRequested.connect(on_close)
