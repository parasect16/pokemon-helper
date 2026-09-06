"""Test di `vision.battle_watcher`.

La classe è pura — riceve booleani e stringhe, ritorna eventi — quindi tutto
è verificabile senza emulatore né PIL.
"""

from __future__ import annotations

import pytest

from pokemon_helper.vision.battle_watcher import (
    BattleEvent,
    BattleWatcher,
    signature_differs,
)

# Firme a 16 cifre esadecimali, come i pHash a 64 bit prodotti da `compute_phash`.
SIG_A = "ffffffffffffffff"
SIG_A_NOISY = "ffffffffffffff00"  # 8 bit di differenza: stesso Pokemon
SIG_B = "0000000000000000"  # 64 bit di differenza: altro Pokemon


def _feed(watcher: BattleWatcher, count: int, in_battle: bool, signature: str | None = None):
    """Ripete la stessa osservazione `count` volte, ritorna gli eventi emessi."""
    return [watcher.observe(in_battle, signature) for _ in range(count)]


def test_entering_requires_the_configured_confirmations() -> None:
    watcher = BattleWatcher(confirmations=2)
    assert watcher.observe(True, SIG_A) is None
    assert watcher.observe(True, SIG_A) is BattleEvent.ENTERED
    assert watcher.in_battle is True


def test_entering_is_reported_once() -> None:
    watcher = BattleWatcher(confirmations=2)
    _feed(watcher, 2, True, SIG_A)
    assert _feed(watcher, 3, True, SIG_A) == [None, None, None]


def test_leaving_requires_confirmations_too() -> None:
    watcher = BattleWatcher(confirmations=2)
    _feed(watcher, 2, True, SIG_A)
    assert watcher.observe(False) is None
    assert watcher.observe(False) is BattleEvent.LEFT
    assert watcher.in_battle is False


def test_single_stray_frame_does_not_flip_the_state() -> None:
    """Una dissolvenza fa sparire la barra HP per un frame: va ignorata."""
    watcher = BattleWatcher(confirmations=2)
    _feed(watcher, 2, True, SIG_A)
    assert watcher.observe(False) is None  # frame anomalo
    assert watcher.observe(True, SIG_A) is None  # tornati come prima
    assert watcher.in_battle is True


def test_alternating_observations_never_settle() -> None:
    watcher = BattleWatcher(confirmations=2)
    events = [watcher.observe(i % 2 == 0, SIG_A) for i in range(10)]
    assert events == [None] * 10
    assert watcher.in_battle is False


def test_opponent_change_is_detected_mid_battle() -> None:
    watcher = BattleWatcher(confirmations=2)
    _feed(watcher, 2, True, SIG_A)
    assert watcher.observe(True, SIG_B) is BattleEvent.OPPONENT_CHANGED


def test_opponent_change_is_reported_once_per_change() -> None:
    watcher = BattleWatcher(confirmations=2)
    _feed(watcher, 2, True, SIG_A)
    watcher.observe(True, SIG_B)
    assert _feed(watcher, 2, True, SIG_B) == [None, None]


def test_signature_noise_is_not_a_change() -> None:
    """Sullo stesso nome la firma oscilla per l'anti-aliasing della scala."""
    watcher = BattleWatcher(confirmations=2)
    _feed(watcher, 2, True, SIG_A)
    assert watcher.observe(True, SIG_A_NOISY) is None


def test_missing_signature_is_ignored_mid_battle() -> None:
    watcher = BattleWatcher(confirmations=2)
    _feed(watcher, 2, True, SIG_A)
    assert watcher.observe(True, None) is None
    assert watcher.observe(True, SIG_A) is None


def test_first_signature_of_a_battle_is_adopted_silently() -> None:
    """Se all'ingresso la firma non era disponibile, la prima utile non è un cambio."""
    watcher = BattleWatcher(confirmations=1)
    assert watcher.observe(True, None) is BattleEvent.ENTERED
    assert watcher.observe(True, SIG_A) is None
    assert watcher.observe(True, SIG_B) is BattleEvent.OPPONENT_CHANGED


def test_signature_is_forgotten_on_leaving() -> None:
    """Battaglia nuova con lo stesso avversario: ENTERED, non OPPONENT_CHANGED."""
    watcher = BattleWatcher(confirmations=1)
    watcher.observe(True, SIG_A)
    watcher.observe(False)
    assert watcher.observe(True, SIG_A) is BattleEvent.ENTERED


def test_reset_forgets_an_ongoing_battle() -> None:
    """Riattivando l'auto-detect a lotta in corso deve riemettere ENTERED."""
    watcher = BattleWatcher(confirmations=1)
    watcher.observe(True, SIG_A)
    watcher.reset()
    assert watcher.in_battle is False
    assert watcher.observe(True, SIG_A) is BattleEvent.ENTERED


def test_reset_clears_a_pending_transition() -> None:
    watcher = BattleWatcher(confirmations=2)
    watcher.observe(True, SIG_A)
    watcher.reset()
    assert watcher.observe(True, SIG_A) is None


def test_confirmations_must_be_positive() -> None:
    with pytest.raises(ValueError, match="confirmations"):
        BattleWatcher(confirmations=0)


def test_single_confirmation_reacts_immediately() -> None:
    watcher = BattleWatcher(confirmations=1)
    assert watcher.observe(True, SIG_A) is BattleEvent.ENTERED
    assert watcher.observe(False) is BattleEvent.LEFT


@pytest.mark.parametrize(
    ("left", "right", "max_distance", "expected"),
    [
        (SIG_A, SIG_A, 12, False),
        (SIG_A, SIG_A_NOISY, 12, False),  # 8 bit
        (SIG_A, SIG_A_NOISY, 4, True),  # stessa coppia, soglia più stretta
        (SIG_A, SIG_B, 12, True),  # 64 bit
        ("ff", "ffff", 12, True),  # lunghezze diverse: incomparabili
    ],
)
def test_signature_distance(left: str, right: str, max_distance: int, expected: bool) -> None:
    assert signature_differs(left, right, max_distance) is expected
