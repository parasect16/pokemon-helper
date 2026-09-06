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
from collections import Counter
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QApplication, QDialog

from pokemon_helper.data import PokemonRepository
from pokemon_helper.ui.hotkey import DEFAULT_TOGGLE_COMBO, GlobalHotkey
from pokemon_helper.ui.nickname_dialog import NicknameDialog
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
    opponent_cleared = Signal()  # combattimento finito: svuota il pannello
    # Failures separati per far apparire il warning sul pulsante giusto.
    opponent_failed = Signal(str)  # messaggio d'errore riconoscimento avversario
    team_failed = Signal(str)  # messaggio d'errore riconoscimento squadra


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


# Intervallo fra due poll dell'auto-detect. Ogni poll apre e chiude una
# sessione di Windows Graphics Capture, e il sistema disegna un bordo attorno
# alla finestra catturata: a 500 ms lampeggiava due volte al secondo, cosa che
# dà fastidio mentre si gioca. A 1500 ms il combattimento viene rilevato entro
# ~3 s (due osservazioni concordi) e il bordo si fa molto più discreto.
POLL_INTERVAL_MS = 1500


class _BattlePoller:
    """Interroga periodicamente la finestra dell'emulatore e ne emette gli eventi.

    Il timer vive sul thread GUI ma non cattura nulla: accoda un job al
    `_RecognizeWorker`, perché `windows-capture` va usata sempre dallo stesso
    thread con l'apartment COM già inizializzato. Passare dal worker ha un
    secondo vantaggio: i poll si serializzano con i riconoscimenti manuali,
    quindi due catture non si sovrappongono mai.

    Un poll che dura più dell'intervallo non deve accodarne altri: finché il
    job precedente non ha finito, `_busy` fa saltare il tick. Meglio perdere
    un giro che accumulare una coda che non si smaltisce più.

    Le dipendenze arrivano dall'esterno (`watcher`, `probe`, `on_event`) così
    questo modulo resta importabile anche senza gli extra `[vision]`.
    """

    def __init__(
        self,
        *,
        worker: _RecognizeWorker,
        watcher,
        probe: Callable[[], tuple[bool, str | None]],
        on_event: Callable[[object], None],
        interval_ms: int = POLL_INTERVAL_MS,
    ) -> None:
        self._worker = worker
        self._watcher = watcher
        self._probe = probe
        self._on_event = on_event
        self._busy = threading.Event()
        self._timer = QTimer()
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self._tick)

    def set_enabled(self, enabled: bool) -> None:
        """Avvia o ferma il polling."""
        if enabled:
            # Reset: riattivando a combattimento già in corso vogliamo che il
            # primo poll produca comunque un ENTERED e popoli il pannello.
            self._watcher.reset()
            self._timer.start()
        else:
            self._timer.stop()

    def stop(self) -> None:
        """Ferma il timer. Firma allineata a `GlobalHotkey` per `_HotkeyGroup`."""
        self._timer.stop()

    def _tick(self) -> None:
        """Thread GUI: accoda un poll se il precedente è finito."""
        if self._busy.is_set():
            return
        self._busy.set()
        self._worker.submit(self._poll)

    def _poll(self) -> None:
        """Thread worker: cattura, classifica, emette l'eventuale evento."""
        try:
            event = self._watcher.observe(*self._probe())
            if event is not None:
                self._on_event(event)
        except Exception as exc:  # noqa: BLE001
            # `probe` assorbe già i fallimenti attesi (emulatore chiuso) e li
            # traduce in "fuori combattimento": ciò che arriva qui è un bug,
            # quindi va visto.
            print(f"[battle-poller] {exc}")
        finally:
            self._busy.clear()


# Mappa generazione -> chiave di gioco supportata dai riconoscitori.
# Per ora solo Rosso Fuoco (Gen 3, GBA). Estendibile in futuro.
_GAME_BY_GENERATION: dict[int, str] = {
    3: "firered",
}

# Confidenza minima perché un riconoscimento venga applicato allo stato.
# Vale sia per l'avversario sia per i sei slot della squadra: sotto questa
# soglia si preferisce non toccare nulla piuttosto che scrivere una specie
# sbagliata.
MIN_RECOGNITION_CONFIDENCE = 0.6


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
    # Le card avversario compaiono e spariscono: senza questo la finestra
    # cresce a inizio combattimento e resta alta e mezza vuota alla fine.
    team_panel.contentResized.connect(window.fit_height)

    def on_ability_pinned(pokemon_id: int, identifier: object) -> None:
        """Fissa o sblocca l'abilità di una specie e ridisegna il pannello."""
        if identifier is None:
            state.abilities.pop(pokemon_id, None)
        else:
            state.abilities[pokemon_id] = str(identifier)
        store.save(state)
        team_panel.apply_state(state)

    team_panel.abilityPinned.connect(on_ability_pinned)
    _wire_nickname_dialog(window, team_panel, repository, state, store)

    bridge = _HotkeyBridge()
    bridge.toggled.connect(window.toggle_visibility)
    hotkey = GlobalHotkey(DEFAULT_TOGGLE_COMBO, bridge.toggled.emit)
    hotkey.start()

    # Riconoscimento: hotkey `<ctrl>+<alt>+r`. Se le deps `[vision]` non
    # sono installate, l'app funziona lo stesso senza riconoscimento.
    recognize_hotkey = _init_recognize_hotkey(state, team_panel, repository, store)

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
    store: StateStore,
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
        from pokemon_helper.vision.battle_detector import (
            is_battle_screen,
            is_party_menu_screen,
        )
        from pokemon_helper.vision.battle_watcher import BattleEvent, BattleWatcher
        from pokemon_helper.vision.capture import CaptureError, WindowCapture
        from pokemon_helper.vision.ocr import OcrEngine
        from pokemon_helper.vision.recognizer import Recognizer
        from pokemon_helper.vision.roi import GAME_ROIS, compute_game_area, roi_to_pixels
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
    # Fine del combattimento: via l'avversario e via l'evidenziazione dello slot.
    bridge.opponent_cleared.connect(lambda: team_panel.set_opponent(None))
    bridge.opponent_cleared.connect(lambda: team_panel.set_active_player(None))
    bridge.team_updated.connect(team_panel.replace_team)
    bridge.team_updated.connect(lambda _t: team_panel.flash_team_reload_success())

    def _on_opp_fail(msg: str) -> None:
        print(f"[recognize opp] {msg}")
        team_panel.flash_opponent_reload_warning(msg)

    def _on_team_fail(msg: str) -> None:
        print(f"[recognize team] {msg}")
        team_panel.flash_team_reload_warning(msg)

    bridge.opponent_failed.connect(_on_opp_fail)
    bridge.team_failed.connect(_on_team_fail)

    min_confidence = MIN_RECOGNITION_CONFIDENCE

    def on_recognize() -> None:
        try:
            game_key = _GAME_BY_GENERATION.get(state.generation)
            if game_key is None:
                bridge.opponent_failed.emit(f"nessun gioco supportato per Gen {state.generation}")
                return
            layout, rois = GAME_ROIS[game_key]
            frame = capture.capture_frame(timeout_seconds=3.0)

            # Guard: se la barra HP avversario non ha pixel HP-colored, non
            # siamo in battaglia — non aggiornare l'avversario per evitare
            # falsi positivi (analog a `_team_snapshot_looks_like_menu`).
            in_battle, reason = is_battle_screen(frame.image, layout, rois)
            if not in_battle:
                bridge.opponent_failed.emit(
                    f"schermata combattimento non rilevata {reason} — avversario non aggiornato"
                )
                return

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
                    nickname_map=state.nicknames,
                )

            if opp is None or opp.confidence < min_confidence:
                bridge.opponent_failed.emit(
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
            bridge.opponent_failed.emit(f"cattura fallita: {exc}")
        except TimeoutError as exc:
            bridge.opponent_failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001 — feedback console, non crash app
            bridge.opponent_failed.emit(f"errore inatteso: {exc}")

    def on_recognize_team() -> None:
        try:
            game_key = _GAME_BY_GENERATION.get(state.generation)
            if game_key is None:
                bridge.team_failed.emit(f"nessun gioco supportato per Gen {state.generation}")
                return
            layout, rois = GAME_ROIS[game_key]
            frame = capture.capture_frame(timeout_seconds=3.0)
            with PokemonRepository.open(db_path) as thread_repo:
                recognizer = Recognizer(thread_repo, ocr)
                results = recognizer.recognize_team(
                    frame.image,
                    layout,
                    rois,
                    state.generation,
                    nickname_map=state.nicknames,
                )

            looks_menu, reason = _team_snapshot_looks_like_menu(results)
            if not looks_menu:
                bridge.team_failed.emit(
                    f"schermata Pokemon non rilevata {reason} — squadra non aggiornata"
                )
                return

            new_team = _apply_team_recognition(results, state.team)
            bridge.team_updated.emit(new_team)
        except CaptureError as exc:
            bridge.team_failed.emit(f"cattura fallita: {exc}")
        except TimeoutError as exc:
            bridge.team_failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001
            bridge.team_failed.emit(f"team recognize error: {exc}")

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

    def probe() -> tuple[bool | None, tuple[str, ...] | None]:
        """Un giro di osservazione: siamo in battaglia, e chi c'è in campo.

        La firma è il testo dei due riquadri nome, giocatore e avversario,
        confrontato per similarità da `BattleWatcher`. Copre entrambi i lati
        di proposito: il cambio dell'avversario si vedrebbe comunque (durante
        l'animazione il suo HUD sparisce, quindi arrivano LEFT e ENTERED),
        mentre un cambio del giocatore non muove nulla nello stato di
        battaglia e passerebbe inosservato, lasciando la card player sul
        Pokemon precedente.

        Il testo costa due chiamate OCR (~16 ms) contro la frazione di
        millisecondo di un pHash, ma il pHash qui non è utilizzabile: il
        contenuto del frame trasla di un paio di pixel fra una cattura e
        l'altra, e basta a farlo oscillare fra due valori a gioco fermo.

        Emulatore chiuso o cattura fallita valgono "fuori combattimento": è
        la lettura giusta, e fa svuotare il pannello. L'elenco Pokemon vale
        invece "non lo so", e lascia il pannello com'è.
        """
        game_key = _GAME_BY_GENERATION.get(state.generation)
        if game_key is None:
            return False, None
        layout, rois = GAME_ROIS[game_key]
        try:
            frame = capture.capture_frame(timeout_seconds=3.0).image
        except CaptureError, TimeoutError:
            return False, None
        # L'elenco Pokemon si apre *durante* la lotta per cambiare Pokemon:
        # non dice nulla sul combattimento, quindi non va letto come "finito".
        if is_party_menu_screen(frame, layout):
            return None, None
        in_battle, _ = is_battle_screen(frame, layout, rois)
        if not in_battle:
            return False, None
        game_area = compute_game_area(frame.width, frame.height, layout)
        signature = tuple(
            _first_text(ocr.recognize(frame.crop(roi_to_pixels(roi, game_area).as_crop_box())))
            for roi in (rois.opponent_name, rois.player_name)
        )
        return True, signature

    def on_battle_event(event) -> None:
        """Thread worker: reagisce a una transizione rilevata dal watcher."""
        if event is BattleEvent.LEFT:
            bridge.opponent_cleared.emit()
            return
        on_recognize()

    poller = _BattlePoller(
        worker=worker,
        watcher=BattleWatcher(),
        probe=probe,
        on_event=on_battle_event,
    )

    def on_auto_detect(enabled: bool) -> None:
        state.auto_detect = enabled
        store.save(state)
        poller.set_enabled(enabled)

    team_panel.set_auto_detect(state.auto_detect)
    team_panel.autoDetectToggled.connect(on_auto_detect)
    poller.set_enabled(state.auto_detect)

    # `capture` tiene aperta una sessione di Windows Graphics Capture: va
    # chiusa all'uscita, o il bordo attorno alla finestra resta disegnato.
    return _HotkeyGroup([hotkey, team_hotkey, poller, worker, capture])


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


def _first_text(ocr_results) -> str:
    """Primo testo OCR di un crop, o stringa vuota se non ne è uscito nessuno."""
    return ocr_results[0].text if ocr_results else ""


def _team_snapshot_looks_like_menu(results) -> tuple[bool, str]:
    """Ritorna `(True, "")` se `results` sembra la schermata menu Pokemon.

    Due heuristiche complementari:

    1. **Testo leggibile**: su una schermata non-menu, la maggior parte dei
       6 ROI slot cade su sfondo casuale e l'OCR ritorna vuoto/spurio.
       Richiediamo almeno 3 slot con testo di ≥3 caratteri.
    2. **Distintività**: sulla schermata combattimento più ROI slot possono
       cadere sul medesimo elemento UI (es. nome dell'avversario ripetuto
       sui pixel di background) e risolvere allo stesso `pokemon_id`. Sul
       menu Pokemon reale i 6 slot sono per definizione distinti o vuoti,
       quindi due o più match sullo stesso id = non menu.

    In caso di fallimento ritorna il motivo tra parentesi, usato in tooltip.
    """
    meaningful = sum(1 for r in results if r.ocr_text and len(r.ocr_text.strip()) >= 3)
    if meaningful < 3:
        return False, f"({meaningful}/6 slot leggibili)"
    matched_ids = [r.pokemon_id for r in results if r.pokemon_id is not None]
    if matched_ids:
        top_id, top_count = Counter(matched_ids).most_common(1)[0]
        if top_count > 1:
            return False, f"(id {top_id} in {top_count} slot)"
    return True, ""


def _apply_team_recognition(
    results, current_team, min_confidence: float = MIN_RECOGNITION_CONFIDENCE
) -> list:
    """Combina i risultati del recognize_team con il team corrente.

    Regole:
    - Slot con `pokemon_id` valido e confidenza sufficiente → nuovo `TeamSlot`
      (livello letto, fallback al livello esistente per lo stesso Pokemon,
      altrimenti 50).
    - Slot senza match, o con match sotto soglia, ma con testo OCR non vuoto
      (tipicamente un nickname sconosciuto): preserva lo slot corrispondente
      del team corrente.
    - Slot con OCR vuoto → slot vuoto (`None`).

    La soglia esiste perché finora un match debole veniva scritto come uno
    certo: il fallback pHash sull'icona accettava qualunque candidato entro
    `icon_max_distance` e una volta ha piazzato Banette nello slot di
    Charizard. Preservare il valore precedente è sempre preferibile a
    sovrascriverlo con una specie sbagliata, tanto più quando l'aggiornamento
    parte da solo (F4) e nessuno lo sta guardando.
    """
    current_levels: dict[int, int] = {
        slot.pokemon_id: slot.level for slot in current_team if slot is not None
    }
    new_team: list = []
    for result in results:
        if result.pokemon_id is not None and result.confidence >= min_confidence:
            level = result.level or current_levels.get(result.pokemon_id, 50)
            new_team.append(TeamSlot(pokemon_id=result.pokemon_id, level=level))
        elif result.ocr_text.strip():
            new_team.append(current_team[result.slot_index])
        else:
            new_team.append(None)
    while len(new_team) < len(current_team):
        new_team.append(None)
    return new_team[: len(current_team)]


def _wire_nickname_dialog(
    window: CompanionWindow,
    team_panel: TeamPanel,
    repository: PokemonRepository,
    state: AppState,
    store: StateStore,
) -> None:
    """Apri `NicknameDialog` quando l'utente clicca il pulsante 🏷."""

    def on_open() -> None:
        dialog = NicknameDialog(repository, state.generation, state.nicknames, parent=window)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        state.nicknames = dialog.nicknames()
        store.save(state)

    team_panel.nicknamesRequested.connect(on_open)


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
