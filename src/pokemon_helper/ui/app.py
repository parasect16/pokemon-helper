"""Entry point Qt che assembla tutti i componenti F2.

Responsabilità:
- caricare lo stato persistente (`StateStore`);
- aprire il repository SQLite;
- costruire `TeamPanel` e infilarlo in una `CompanionWindow`;
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
from pokemon_helper.ui.overlay import CompanionWindow
from pokemon_helper.ui.state import AppState, StateStore, TeamSlot, default_state_path
from pokemon_helper.ui.team_panel import TeamPanel


class _HotkeyBridge(QObject):
    """QObject che espone un segnale, emesso dal thread pynput.

    Serve per marshallare l'invocazione della hotkey dal thread di ascolto di
    pynput al thread GUI di Qt: connessione cross-thread di un `Signal`
    forza automaticamente `Qt.QueuedConnection`.
    """

    toggled = Signal()


class _RecognizeBridge(QObject):
    """Ponte thread-safe per il riconoscimento asincrono dell'avversario.

    L'esito del riconoscimento (successo o fallimento) viene emesso come
    Signal, così l'update della UI avviene nel thread GUI di Qt anche se
    la chiamata originaria arriva dal thread listener di pynput.
    """

    recognized = Signal(int)  # pokemon_id
    failed = Signal(str)  # messaggio d'errore human-friendly


# Mappa generazione -> chiave di gioco supportata dai riconoscitori.
# Per ora solo Rosso Fuoco (Gen 3, GBA). Estendibile in futuro.
_GAME_BY_GENERATION: dict[int, str] = {
    3: "firered",
}


def default_db_path() -> Path:
    """Path atteso del database SQLite: `<cwd>/data/pokemon.sqlite`."""
    return Path.cwd() / "data" / "pokemon.sqlite"


def run() -> int:
    """Punto d'ingresso: avvia l'applicazione. Ritorna l'exit code di Qt."""
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("pokemon-helper")
    # Con chrome nativo la finestra ha entry in taskbar: quando l'utente
    # preme la X di sistema, `quitOnLastWindowClosed` si prende cura del quit.
    app.setQuitOnLastWindowClosed(True)

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
    window = CompanionWindow(team_panel)

    _restore_geometry(app, window, state)
    window.show()

    _wire_persistence(window, team_panel, state, store)

    bridge = _HotkeyBridge()
    bridge.toggled.connect(window.toggle_visibility)
    hotkey = GlobalHotkey(DEFAULT_TOGGLE_COMBO, bridge.toggled.emit)
    hotkey.start()

    # Riconoscimento: hotkey `<ctrl>+<alt>+r`. Se le deps `[vision]` non
    # sono installate, l'app funziona lo stesso senza riconoscimento.
    recognize_hotkey = _init_recognize_hotkey(state, team_panel, repository)

    if os.environ.get("POKEMON_HELPER_SMOKE") == "1":
        # Modalità smoke: chiudi dopo 2 secondi senza input utente.
        QTimer.singleShot(2000, app.quit)

    # Cleanup dopo che il loop principale è terminato: eseguire dentro
    # aboutToQuit poteva deadlockare con il thread listener di pynput
    # durante lo shutdown di Qt su Windows.
    try:
        return app.exec()
    finally:
        hotkey.stop()
        if recognize_hotkey is not None:
            recognize_hotkey.stop()
        repository.close()


# ---------------------------------------------------------------------------
# Helper interni
# ---------------------------------------------------------------------------


def _restore_geometry(app: QApplication, window: CompanionWindow, state: AppState) -> None:
    """Posiziona la finestra: coordinate salvate o angolo alto-destra."""
    if state.overlay_x is not None and state.overlay_y is not None:
        window.move_to(state.overlay_x, state.overlay_y)
        return
    screen = app.primaryScreen()
    if screen is None:
        return
    geometry = screen.availableGeometry()
    window.move_to(geometry.right() - 380, geometry.top() + 40)


def _init_recognize_hotkey(
    state: AppState,
    team_panel: TeamPanel,
    repository: PokemonRepository,  # noqa: ARG001 — riservato per future estensioni
) -> GlobalHotkey | None:
    """Registra la hotkey `<ctrl>+<alt>+r` per il riconoscimento avversario.

    Ritorna `None` se le dipendenze `[vision]` non sono installate (in tal
    caso l'app funziona senza riconoscimento). Il callback della hotkey gira
    sul thread pynput: cattura il frame, esegue il recognizer e comunica il
    risultato al thread GUI via `_RecognizeBridge` (Signal cross-thread).

    Nota threading: `sqlite3.Connection` di default rifiuta l'uso cross-thread
    (`check_same_thread=True`). La `repository` principale è nata sul thread
    GUI, quindi qui apriamo una connessione dedicata per ogni chiamata di
    recognize (overhead ~1 ms). Zero contesa con il thread GUI, zero rischio.
    """
    try:
        from pokemon_helper.vision.capture import CaptureError, WindowCapture
        from pokemon_helper.vision.ocr import OcrEngine
        from pokemon_helper.vision.recognizer import Recognizer
        from pokemon_helper.vision.roi import GAME_ROIS
    except ImportError as exc:
        print(f"[vision] deps non installate, riconoscimento disabilitato: {exc}")
        return None

    capture = WindowCapture("mGBA")
    ocr = OcrEngine()  # istanza singola condivisa: init pesante una volta sola.
    db_path = default_db_path()

    bridge = _RecognizeBridge()
    bridge.recognized.connect(team_panel.set_opponent)
    bridge.failed.connect(lambda msg: print(f"[recognize] {msg}"))

    min_confidence = 0.6

    def on_recognize() -> None:
        try:
            game_key = _GAME_BY_GENERATION.get(state.generation)
            if game_key is None:
                bridge.failed.emit(f"nessun gioco supportato per Gen {state.generation}")
                return
            layout, rois = GAME_ROIS[game_key]
            frame = capture.capture_frame(timeout_seconds=3.0)
            # Connection dedicata al thread pynput.
            with PokemonRepository.open(db_path) as thread_repo:
                recognizer = Recognizer(thread_repo, ocr)
                result = recognizer.recognize_opponent(frame.image, layout, rois, state.generation)
            if result is None or result.confidence < min_confidence:
                bridge.failed.emit(
                    "nessun match affidabile"
                    if result is None
                    else f"confidenza troppo bassa: {result.confidence:.2f}"
                )
                return
            bridge.recognized.emit(result.pokemon_id)
        except CaptureError as exc:
            bridge.failed.emit(f"cattura fallita: {exc}")
        except TimeoutError as exc:
            bridge.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001 — feedback console, non crash app
            bridge.failed.emit(f"errore inatteso: {exc}")

    hotkey = GlobalHotkey("<ctrl>+<alt>+r", on_recognize)
    hotkey.start()
    return hotkey


def _wire_persistence(
    window: CompanionWindow,
    team_panel: TeamPanel,
    state: AppState,
    store: StateStore,
) -> None:
    """Collega i segnali della UI alla scrittura su disco dello stato."""

    def persist() -> None:
        store.save(state)

    def on_position(x: int, y: int) -> None:
        state.overlay_x = x
        state.overlay_y = y
        persist()

    def on_generation(_gen: int) -> None:
        # `state.generation` è già stato aggiornato da TeamPanel.
        persist()

    def on_slot(_index: int, _slot: TeamSlot | None) -> None:
        # `state.team` è già stato aggiornato da TeamPanel.
        persist()

    window.positionChanged.connect(on_position)
    team_panel.generationChanged.connect(on_generation)
    team_panel.slotChanged.connect(on_slot)
