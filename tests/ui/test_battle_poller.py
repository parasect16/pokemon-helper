"""Test del collante F4 in `ui.app`: poller, worker persistente, gruppo stop.

Il poller vive sul thread GUI ma non cattura nulla: accoda al worker, che è
l'unico thread autorizzato a parlare con `windows-capture`. Qui watcher,
probe e worker sono finti, quindi niente Qt oltre al `QTimer` e niente
dipendenze `[vision]`.
"""

from __future__ import annotations

import threading
import time

import pytest

from pokemon_helper.ui.app import _BattlePoller, _HotkeyGroup, _RecognizeWorker


class _InlineWorker:
    """Worker che esegue subito: il poll finisce prima del tick successivo."""

    def __init__(self, cancelled: bool = False) -> None:
        self.submitted = 0
        self.cancelled = cancelled

    def submit(self, job) -> None:
        self.submitted += 1
        job()


class _QueueingWorker:
    """Worker che accumula i job senza eseguirli: simula un poll ancora in corso."""

    def __init__(self) -> None:
        self.jobs: list = []
        self.cancelled = False

    def submit(self, job) -> None:
        self.jobs.append(job)

    def run_next(self) -> None:
        self.jobs.pop(0)()


class _FakeWatcher:
    """`BattleWatcher` finto: restituisce eventi da una lista, conta i reset."""

    def __init__(self, events=()) -> None:
        self.events = list(events)
        self.observations: list[tuple] = []
        self.resets = 0

    def observe(self, in_battle, signature):
        self.observations.append((in_battle, signature))
        return self.events.pop(0) if self.events else None

    def reset(self) -> None:
        self.resets += 1


def _poller(worker, watcher, *, probe=None, on_event=None) -> _BattlePoller:
    return _BattlePoller(
        worker=worker,
        watcher=watcher,
        probe=probe or (lambda: (True, ("PIKACHU", "WEEZING"))),
        on_event=on_event or (lambda _event: None),
    )


# ------------------------------------------------------------------- tick


def test_a_tick_hands_the_probe_result_to_the_watcher(qapp) -> None:
    worker = _InlineWorker()
    watcher = _FakeWatcher()
    poller = _poller(worker, watcher)

    poller._tick()

    assert worker.submitted == 1
    assert watcher.observations == [(True, ("PIKACHU", "WEEZING"))]


def test_an_event_from_the_watcher_is_forwarded(qapp) -> None:
    seen: list = []
    poller = _poller(_InlineWorker(), _FakeWatcher(events=["ENTERED"]), on_event=seen.append)

    poller._tick()

    assert seen == ["ENTERED"]


def test_no_event_means_nothing_is_forwarded(qapp) -> None:
    seen: list = []
    poller = _poller(_InlineWorker(), _FakeWatcher(), on_event=seen.append)

    poller._tick()

    assert seen == []


def test_a_tick_is_skipped_while_the_previous_poll_is_still_running(qapp) -> None:
    """Un poll più lento dell'intervallo non deve accumulare una coda."""
    worker = _QueueingWorker()
    watcher = _FakeWatcher()
    poller = _poller(worker, watcher)

    poller._tick()
    poller._tick()
    poller._tick()
    assert len(worker.jobs) == 1

    worker.run_next()  # il poll finisce e libera lo slot
    poller._tick()
    assert len(worker.jobs) == 1


def test_a_failing_probe_does_not_wedge_the_poller(qapp, capsys) -> None:
    """Dopo un'eccezione il tick successivo deve ripartire, non restare busy."""

    def boom():
        raise RuntimeError("capture esplosa")

    worker = _InlineWorker()
    poller = _poller(worker, _FakeWatcher(), probe=boom)

    poller._tick()
    assert "capture esplosa" in capsys.readouterr().out

    poller._tick()
    assert worker.submitted == 2


# ------------------------------------------------------------- abilitazione


def test_enabling_resets_the_watcher_and_starts_the_timer(qapp) -> None:
    """Riaccendere l'auto a lotta in corso deve produrre comunque un ENTERED."""
    watcher = _FakeWatcher()
    poller = _poller(_InlineWorker(), watcher)

    poller.set_enabled(True)

    assert watcher.resets == 1
    assert poller._timer.isActive()


def test_disabling_stops_the_timer_without_resetting(qapp) -> None:
    watcher = _FakeWatcher()
    poller = _poller(_InlineWorker(), watcher)
    poller.set_enabled(True)

    poller.set_enabled(False)

    assert not poller._timer.isActive()
    assert watcher.resets == 1


def test_stop_halts_the_timer(qapp) -> None:
    """Firma allineata a `GlobalHotkey`: `_HotkeyGroup` ferma tutto con `.stop()`."""
    poller = _poller(_InlineWorker(), _FakeWatcher())
    poller.set_enabled(True)

    poller.stop()

    assert not poller._timer.isActive()


def test_the_poll_interval_is_configurable(qapp) -> None:
    poller = _BattlePoller(
        worker=_InlineWorker(),
        watcher=_FakeWatcher(),
        probe=lambda: (False, None),
        on_event=lambda _event: None,
        interval_ms=123,
    )
    assert poller._timer.interval() == 123


# ---------------------------------------------------------------- worker


def test_the_worker_runs_submitted_jobs_in_order() -> None:
    worker = _RecognizeWorker()
    done = threading.Event()
    order: list[int] = []

    worker.submit(lambda: order.append(1))
    worker.submit(lambda: order.append(2))
    worker.submit(done.set)
    try:
        assert done.wait(5)
        assert order == [1, 2]
    finally:
        worker.stop()


def test_a_job_that_raises_does_not_kill_the_worker(capsys) -> None:
    """Il worker è uno solo e vive quanto l'app: un job rotto non deve affondarlo."""
    worker = _RecognizeWorker()
    done = threading.Event()

    def boom() -> None:
        raise RuntimeError("job esploso")

    worker.submit(boom)
    worker.submit(done.set)
    try:
        assert done.wait(5)
        assert "job esploso" in capsys.readouterr().out
    finally:
        worker.stop()


def test_stopping_the_worker_ends_its_thread() -> None:
    worker = _RecognizeWorker()
    assert worker.stop() is True
    assert not worker._thread.is_alive()


def test_the_worker_is_not_cancelled_until_it_is_stopped() -> None:
    worker = _RecognizeWorker()
    assert worker.cancelled is False
    worker.stop()
    assert worker.cancelled is True


def test_jobs_submitted_after_the_stop_are_ignored() -> None:
    """In chiusura non c'è più nessuno a cui consegnare il risultato."""
    worker = _RecognizeWorker()
    worker.stop()

    ran = threading.Event()
    worker.submit(ran.set)

    assert not ran.wait(0.2)


def test_jobs_still_queued_when_the_stop_arrives_never_run() -> None:
    """La coda viene svuotata: quello che non è partito non deve partire."""
    worker = _RecognizeWorker()
    started = threading.Event()
    skipped = threading.Event()

    def blocking() -> None:
        """Occupa il worker finché non comincia la chiusura, come un recognize."""
        started.set()
        while not worker.cancelled:
            time.sleep(0.005)

    worker.submit(blocking)
    assert started.wait(5)
    worker.submit(skipped.set)  # accodato dietro a quello in corso

    assert worker.stop() is True
    assert not skipped.is_set()


def test_a_job_hanging_past_the_timeout_is_reported_and_abandoned(capsys) -> None:
    """Il thread è daemon: non potendolo uccidere, almeno lo si dice."""
    worker = _RecognizeWorker()
    started = threading.Event()
    release = threading.Event()

    def hanging() -> None:
        started.set()
        release.wait(10)

    worker.submit(hanging)
    assert started.wait(5)
    try:
        assert worker.stop(timeout=0.2) is False
        assert "ancora in corso" in capsys.readouterr().out
    finally:
        release.set()


def test_a_cancelled_worker_skips_the_poll_entirely(qapp) -> None:
    """Il tick può arrivare a chiusura iniziata: non deve toccare la cattura."""
    probed: list[int] = []
    poller = _poller(
        _InlineWorker(cancelled=True),
        _FakeWatcher(),
        probe=lambda: (probed.append(1), (True, None))[1],
    )

    poller._tick()

    assert probed == []
    assert not poller._busy.is_set()  # il tick successivo può ripartire


# ------------------------------------------------------------ _HotkeyGroup


class _Stoppable:
    def __init__(self, explode: bool = False) -> None:
        self.stopped = False
        self._explode = explode

    def stop(self) -> None:
        if self._explode:
            raise RuntimeError("stop fallito")
        self.stopped = True


def test_the_group_stops_everything_it_holds() -> None:
    members = [_Stoppable(), _Stoppable()]
    _HotkeyGroup(members).stop()
    assert all(m.stopped for m in members)


def test_one_failing_stop_does_not_block_the_others(capsys) -> None:
    """All'uscita conta chiudere tutto: una hotkey rotta non deve tenere aperta la cattura."""
    last = _Stoppable()
    _HotkeyGroup([_Stoppable(explode=True), last]).stop()
    assert last.stopped
    assert "stop fallito" in capsys.readouterr().out


@pytest.mark.parametrize("members", [[], [_Stoppable()]])
def test_the_group_accepts_any_number_of_members(members) -> None:
    _HotkeyGroup(members).stop()
