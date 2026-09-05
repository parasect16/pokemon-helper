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
import queue
import sys
import threading
from collections.abc import Callable
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
    """Ponte thread-safe per il riconoscimento asincrono in combattimento.

    Emette segnali distinti per l'avversario e per il Pokemon del giocatore,
    così l'update della UI avviene nel thread GUI di Qt anche se la chiamata
    originaria arriva dal thread listener di pynput.
    """

    opponent_recognized = Signal(int)  # pokemon_id avversario
    player_recognized = Signal(object)  # pokemon_id giocatore, o None
    team_updated = Signal(object)  # list[TeamSlot | None] con nuovo team
    failed = Signal(str)  # messaggio d'errore human-friendly


class _RecognizeWorker:
    """Worker thread persistente che processa job di riconoscimento serialmente.

    Motivazioni:
    - `windows-capture` (Windows Graphics Capture API) è sensibile all'apartment
      COM del thread chiamante. Usare un thread long-lived con COM già
      inizializzato evita stalli imprevedibili nei daemon thread "freschi".
    - Serializzare le richieste (hotkey + pulsante) evita concorrenze sulla
      stessa capture session e sull'inference ONNX di RapidOCR.
    """

    def __init__(self) -> None:
        self._queue: queue.Queue[Callable[[], None] | None] = queue.Queue()
        self._thread = threading.Thread(
            target=self._run,
            name="recognize-worker",
            daemon=True,
        )
        self._thread.start()

    def submit(self, job: Callable[[], None]) -> None:
        """Accoda un job. Ritorna subito; il worker lo esegue in FIFO."""
        self._queue.put(job)

    def stop(self) -> None:
        """Segnala al worker di uscire; usato all'exit dell'app."""
        self._queue.put(None)

    def _run(self) -> None:
        while True:
            job = self._queue.get()
            if job is None:
                return
            try:
                job()
            except Exception as exc:  # noqa: BLE001
                print(f"[recognize-worker] eccezione: {exc}")


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
    # Istanza singola condivisa. Warm-up eseguito in background per evitare
    # sia di stallare la GUI all'avvio sia il primo-click che paga i 150-500
    # ms di init dei modelli ONNX.
    ocr = OcrEngine()
    # Worker persistente: tutte le richieste (hotkey + pulsanti) vengono
    # accodate qui. Il warm-up è il primo job — così il thread è già in vita
    # quando arriva la prima richiesta di recognize.
    worker = _RecognizeWorker()
    worker.submit(ocr.warm_up)
    db_path = default_db_path()

    bridge = _RecognizeBridge()
    bridge.opponent_recognized.connect(team_panel.set_opponent)
    bridge.opponent_recognized.connect(lambda _pid: team_panel.flash_opponent_reload_success())
    bridge.player_recognized.connect(team_panel.set_active_player)
    bridge.team_updated.connect(team_panel.replace_team)
    bridge.team_updated.connect(lambda _t: team_panel.flash_team_reload_success())
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

            # Riconosci entrambi i lati con una singola cattura, usando
            # una connection dedicata al thread pynput. Il player in campo
            # può essere solo uno dei 6 membri della squadra: restringiamo
            # il match a quell'insieme per aumentare la precisione anche
            # con OCR imperfetta e pHash rumoroso.
            team_ids = {slot.pokemon_id for slot in state.team if slot is not None}
            with PokemonRepository.open(db_path) as thread_repo:
                recognizer = Recognizer(thread_repo, ocr)
                opp = recognizer.recognize_opponent(frame.image, layout, rois, state.generation)
                player = recognizer.recognize_player(
                    frame.image,
                    layout,
                    rois,
                    state.generation,
                    restrict_to_ids=team_ids or None,
                )

            if opp is None or opp.confidence < min_confidence:
                bridge.failed.emit(
                    "avversario non riconosciuto in modo affidabile"
                    if opp is None
                    else f"avversario: confidenza {opp.confidence:.2f} troppo bassa"
                )
            else:
                bridge.opponent_recognized.emit(opp.pokemon_id)

            # Il giocatore è opzionale: se il match non è affidabile, semplicemente
            # non evidenziamo nulla (nessun errore mostrato: la funzionalità
            # principale del recognize è l'avversario).
            if player is not None and player.confidence >= min_confidence:
                bridge.player_recognized.emit(player.pokemon_id)
            else:
                bridge.player_recognized.emit(None)
        except CaptureError as exc:
            bridge.failed.emit(f"cattura fallita: {exc}")
        except TimeoutError as exc:
            bridge.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001 — feedback console, non crash app
            bridge.failed.emit(f"errore inatteso: {exc}")

    def on_recognize_team() -> None:
        try:
            game_key = _GAME_BY_GENERATION.get(state.generation)
            if game_key is None:
                bridge.failed.emit(f"nessun gioco supportato per Gen {state.generation}")
                return
            layout, rois = GAME_ROIS[game_key]
            frame = capture.capture_frame(timeout_seconds=3.0)
            with PokemonRepository.open(db_path) as thread_repo:
                recognizer = Recognizer(thread_repo, ocr)
                results = recognizer.recognize_team(frame.image, layout, rois, state.generation)
            new_team = _apply_team_recognition(results, state.team)
            bridge.team_updated.emit(new_team)
        except CaptureError as exc:
            bridge.failed.emit(f"cattura fallita: {exc}")
        except TimeoutError as exc:
            bridge.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001
            bridge.failed.emit(f"team recognize error: {exc}")

    # Sia hotkey sia pulsanti sottopongono al medesimo worker persistente.
    # La hotkey (pynput thread) non chiama più `on_recognize` in-line: la
    # accoda al worker per uniformare l'esecuzione ed evitare re-entrancy
    # sulle risorse condivise di capture/OCR.
    hotkey = GlobalHotkey("<ctrl>+<alt>+r", lambda: worker.submit(on_recognize))
    hotkey.start()
    team_hotkey = GlobalHotkey("<ctrl>+<alt>+t", lambda: worker.submit(on_recognize_team))
    team_hotkey.start()

    team_panel.reloadOpponentRequested.connect(lambda: worker.submit(on_recognize))
    team_panel.reloadTeamRequested.connect(lambda: worker.submit(on_recognize_team))

    return _HotkeyGroup([hotkey, team_hotkey, worker])


class _HotkeyGroup:
    """Piccolo aggregatore di GlobalHotkey con un unico `.stop()`."""

    def __init__(self, hotkeys: list) -> None:
        self._hotkeys = hotkeys

    def stop(self) -> None:
        for hk in self._hotkeys:
            try:
                hk.stop()
            except Exception as exc:  # noqa: BLE001
                print(f"[hotkey] errore stop: {exc}")


def _apply_team_recognition(results, current_team) -> list:
    """Combina i risultati del recognize_team con il team corrente.

    Regole:
    - Slot con `pokemon_id` valido → nuovo `TeamSlot` (livello letto, fallback
      al livello esistente per lo stesso Pokemon, altrimenti 50).
    - Slot senza match ma con testo OCR non vuoto (tipicamente un nickname
      sconosciuto): preserva lo slot corrispondente del team corrente.
    - Slot con OCR vuoto → slot vuoto (`None`).
    """
    current_levels: dict[int, int] = {
        slot.pokemon_id: slot.level for slot in current_team if slot is not None
    }
    new_team: list = []
    for result in results:
        if result.pokemon_id is not None:
            level = result.level or current_levels.get(result.pokemon_id, 50)
            new_team.append(TeamSlot(pokemon_id=result.pokemon_id, level=level))
        elif result.ocr_text.strip():
            new_team.append(current_team[result.slot_index])
        else:
            new_team.append(None)
    while len(new_team) < len(current_team):
        new_team.append(None)
    return new_team[: len(current_team)]


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

    def on_team_replaced(_new_team) -> None:
        # `state.team` è già stato aggiornato da TeamPanel.replace_team.
        persist()

    window.positionChanged.connect(on_position)
    team_panel.generationChanged.connect(on_generation)
    team_panel.slotChanged.connect(on_slot)
    team_panel.teamReplaced.connect(on_team_replaced)
