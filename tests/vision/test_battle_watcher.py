"""Test di `vision.battle_watcher`.

La classe è pura — riceve booleani e stringhe, ritorna eventi — quindi tutto
è verificabile senza emulatore né PIL.
"""

from __future__ import annotations

import pytest

from pokemon_helper.vision.battle_watcher import (
    BattleEvent,
    BattleWatcher,
    signatures_differ,
)

# Firme come le produce il probe: (testo nome avversario, testo nome player).
SIG_A = ("HEEZINGL.33", "FIAHHETTA L.38")
# Stessa scena riletta: l'OCR sbaglia un carattere perché il frame trasla di
# un paio di pixel fra una cattura e l'altra. Similarità 0.93, non è un cambio.
SIG_A_NOISY = ("HEEZINGL.33", "FIAMHETTA L.38")
# Avversario diverso: similarità 0.40 sul primo lato.
SIG_B = ("GLOOHL.37", "FIAHHETTA L.38")


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


def test_combatant_change_is_detected_mid_battle() -> None:
    watcher = BattleWatcher(confirmations=2)
    _feed(watcher, 2, True, SIG_A)
    assert watcher.observe(True, SIG_B) is BattleEvent.COMBATANTS_CHANGED


def test_combatant_change_is_reported_once_per_change() -> None:
    watcher = BattleWatcher(confirmations=2)
    _feed(watcher, 2, True, SIG_A)
    watcher.observe(True, SIG_B)
    assert _feed(watcher, 2, True, SIG_B) == [None, None]


def test_change_on_the_player_side_only_is_detected() -> None:
    """Il caso che conta: cambia solo il Pokemon del giocatore.

    È l'unico segnale disponibile, perché la barra HP avversaria resta
    visibile per tutto il cambio e lo stato di battaglia non si muove. I due
    lati sono confrontati separatamente proprio per questo: in un'unica
    stringa il lato rimasto uguale diluirebbe la differenza dell'altro.
    """
    watcher = BattleWatcher(confirmations=2)
    _feed(watcher, 2, True, SIG_A)
    changed = (SIG_A[0], "ELECTRODE L.39")
    assert watcher.observe(True, changed) is BattleEvent.COMBATANTS_CHANGED


def test_ocr_noise_is_not_a_change() -> None:
    """Un carattere sbagliato dall'OCR non deve far ripartire il riconoscimento."""
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
    assert watcher.observe(True, SIG_B) is BattleEvent.COMBATANTS_CHANGED


def test_signature_is_forgotten_on_leaving() -> None:
    """Battaglia nuova con lo stesso avversario: ENTERED, non COMBATANTS_CHANGED."""
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
    ("left", "right", "min_similarity", "expected"),
    [
        (SIG_A, SIG_A, 0.75, False),
        (SIG_A, SIG_A_NOISY, 0.75, False),  # rumore OCR: 0.93
        (SIG_A, SIG_A_NOISY, 0.99, True),  # stessa coppia, soglia irrealistica
        (SIG_A, SIG_B, 0.75, True),  # avversario diverso: 0.40
        (SIG_A, ("HEEZINGL.33",), 0.75, True),  # lunghezze diverse: incomparabili
        (SIG_A, ("", SIG_A[1]), 0.75, False),  # lettura mancante: non prova nulla
        (("", ""), SIG_A, 0.75, False),
    ],
)
def test_signature_comparison(left, right, min_similarity: float, expected: bool) -> None:
    assert signatures_differ(left, right, min_similarity) is expected


def test_a_level_up_is_not_a_change() -> None:
    """Stesso Pokemon che sale di livello: nessun motivo di rifare il match."""
    watcher = BattleWatcher(confirmations=1)
    watcher.observe(True, ("HEEZINGL.33", "DUGTRIO L.38"))
    assert watcher.observe(True, ("HEEZINGL.33", "DUGTRIO L.39")) is None
