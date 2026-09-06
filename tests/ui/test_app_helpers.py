"""Test per gli helper puri di `pokemon_helper.ui.app`.

Focus sulle heuristiche che decidono se una snapshot di `recognize_team`
proviene davvero dal menu Pokemon o da un'altra schermata (combattimento,
mondo, ecc.). Non tocchiamo Qt né worker: gli helper sono funzioni pure.
"""

from __future__ import annotations

from dataclasses import dataclass

from pokemon_helper.ui.app import _apply_team_recognition, _team_snapshot_looks_like_menu
from pokemon_helper.ui.state import TeamSlot


@dataclass(frozen=True, slots=True)
class _FakeResult:
    """Stand-in per `TeamRecognition` che espone solo i campi usati."""

    slot_index: int
    pokemon_id: int | None
    ocr_text: str = ""
    confidence: float = 1.0
    level: int | None = None


def _r(
    index: int,
    pokemon_id: int | None = None,
    ocr_text: str = "",
    confidence: float = 1.0,
    level: int | None = None,
) -> _FakeResult:
    """Shorthand per costruire un fake result."""
    return _FakeResult(
        slot_index=index,
        pokemon_id=pokemon_id,
        ocr_text=ocr_text,
        confidence=confidence,
        level=level,
    )


def test_snapshot_menu_all_slots_readable_and_distinct() -> None:
    """Sei match distinti = classica schermata team menu → OK."""
    results = [
        _r(0, pokemon_id=25, ocr_text="Pikachu"),
        _r(1, pokemon_id=6, ocr_text="Charizard"),
        _r(2, pokemon_id=9, ocr_text="Blastoise"),
        _r(3, pokemon_id=3, ocr_text="Venusaur"),
        _r(4, pokemon_id=143, ocr_text="Snorlax"),
        _r(5, pokemon_id=94, ocr_text="Gengar"),
    ]
    ok, reason = _team_snapshot_looks_like_menu(results)
    assert ok is True
    assert reason == ""


def test_snapshot_menu_partially_filled_ok() -> None:
    """Tre slot pieni + tre vuoti (squadra parziale) = comunque menu."""
    results = [
        _r(0, pokemon_id=25, ocr_text="Pikachu"),
        _r(1, pokemon_id=6, ocr_text="Charizard"),
        _r(2, pokemon_id=9, ocr_text="Blastoise"),
        _r(3, pokemon_id=None, ocr_text=""),
        _r(4, pokemon_id=None, ocr_text=""),
        _r(5, pokemon_id=None, ocr_text=""),
    ]
    ok, _ = _team_snapshot_looks_like_menu(results)
    assert ok is True


def test_snapshot_rejects_too_few_readable_slots() -> None:
    """Meno di 3 slot con testo ≥3 char = non siamo sul menu."""
    results = [
        _r(0, pokemon_id=None, ocr_text=""),
        _r(1, pokemon_id=None, ocr_text="a"),  # troppo corto
        _r(2, pokemon_id=None, ocr_text="ok"),  # <3 char
        _r(3, pokemon_id=None, ocr_text=""),
        _r(4, pokemon_id=None, ocr_text=""),
        _r(5, pokemon_id=None, ocr_text=""),
    ]
    ok, reason = _team_snapshot_looks_like_menu(results)
    assert ok is False
    assert "0/6" in reason


def test_snapshot_rejects_repeated_pokemon_id() -> None:
    """Stesso pokemon_id su ≥2 slot = schermata non-menu (bug utente).

    Sulla schermata di combattimento le ROI slot cadono sui pixel del nome
    dell'avversario, e fuzzy_match risolve tutti allo stesso id (es. #1
    Bulbasaur = primo dell'elenco). Deve essere rifiutato per evitare la
    sovrascrittura distruttiva del team.
    """
    results = [
        _r(0, pokemon_id=1, ocr_text="Bulbasaur"),
        _r(1, pokemon_id=1, ocr_text="Bulbasaur"),
        _r(2, pokemon_id=1, ocr_text="Bulbasaur"),
        _r(3, pokemon_id=1, ocr_text="Bulbasaur"),
        _r(4, pokemon_id=None, ocr_text=""),
        _r(5, pokemon_id=None, ocr_text=""),
    ]
    ok, reason = _team_snapshot_looks_like_menu(results)
    assert ok is False
    assert "id 1" in reason
    assert "4 slot" in reason


def test_snapshot_rejects_partial_repeat() -> None:
    """Anche due slot con stesso id devono far scattare il guard."""
    results = [
        _r(0, pokemon_id=25, ocr_text="Pikachu"),
        _r(1, pokemon_id=25, ocr_text="Pikachu"),
        _r(2, pokemon_id=6, ocr_text="Charizard"),
        _r(3, pokemon_id=None, ocr_text=""),
        _r(4, pokemon_id=None, ocr_text=""),
        _r(5, pokemon_id=None, ocr_text=""),
    ]
    ok, reason = _team_snapshot_looks_like_menu(results)
    assert ok is False
    assert "id 25" in reason


def test_snapshot_accepts_no_matches_but_enough_ocr() -> None:
    """Testo leggibile ma nessun match id (tutti nickname sconosciuti) = OK.

    Sul menu Pokemon reale con nickname custom, il fuzzy match potrebbe
    fallire su tutti i 6 slot. `_apply_team_recognition` preserverà lo stato
    corrente per gli slot non matchati; qui il guard deve lasciar passare
    perché il presupposto "siamo sul menu" resta valido.
    """
    results = [
        _r(0, pokemon_id=None, ocr_text="Sparky"),
        _r(1, pokemon_id=None, ocr_text="Flame"),
        _r(2, pokemon_id=None, ocr_text="Hydro"),
        _r(3, pokemon_id=None, ocr_text="Leaf"),
        _r(4, pokemon_id=None, ocr_text="Ghost"),
        _r(5, pokemon_id=None, ocr_text="Rock"),
    ]
    ok, reason = _team_snapshot_looks_like_menu(results)
    assert ok is True
    assert reason == ""


# --------------------------------------------------------------- apply team


def _team(*pairs):
    """Squadra corrente da coppie `(pokemon_id, level)`, `None` per slot vuoto."""
    return [None if p is None else TeamSlot(pokemon_id=p[0], level=p[1]) for p in pairs]


def _six(result):
    """Snapshot di sei slot con `result` in posizione 0 e il resto vuoto."""
    return [result] + [_r(i) for i in range(1, 6)]


def test_confident_match_overwrites_the_slot() -> None:
    new = _apply_team_recognition(
        _six(_r(0, pokemon_id=6, ocr_text="CHARIZARD", confidence=0.9, level=38)),
        _team((25, 10), None, None, None, None, None),
    )
    assert new[0] == TeamSlot(pokemon_id=6, level=38)


def test_weak_match_preserves_the_previous_slot() -> None:
    """Sotto soglia non si scrive: meglio il valore vecchio di una specie sbagliata.

    È il caso del fallback icona che aveva piazzato Banette al posto di
    Charizard.
    """
    new = _apply_team_recognition(
        _six(_r(0, pokemon_id=354, ocr_text="FIAHHETTA", confidence=0.5)),
        _team((6, 38), None, None, None, None, None),
    )
    assert new[0] == TeamSlot(pokemon_id=6, level=38)


def test_match_exactly_at_the_threshold_is_applied() -> None:
    new = _apply_team_recognition(
        _six(_r(0, pokemon_id=6, ocr_text="CHARIZARD", confidence=0.6, level=38)),
        _team(None, None, None, None, None, None),
    )
    assert new[0] == TeamSlot(pokemon_id=6, level=38)


def test_weak_match_without_previous_slot_leaves_it_empty() -> None:
    new = _apply_team_recognition(
        _six(_r(0, pokemon_id=354, ocr_text="FIAHHETTA", confidence=0.2)),
        _team(None, None, None, None, None, None),
    )
    assert new[0] is None


def test_missing_level_falls_back_to_the_level_of_the_same_pokemon() -> None:
    """Con alterazione di stato il livello non è leggibile: si tiene il vecchio."""
    new = _apply_team_recognition(
        _six(_r(0, pokemon_id=6, ocr_text="CHARIZARD", confidence=0.9, level=None)),
        _team((6, 38), None, None, None, None, None),
    )
    assert new[0] == TeamSlot(pokemon_id=6, level=38)


def test_missing_level_for_an_unknown_pokemon_defaults_to_fifty() -> None:
    new = _apply_team_recognition(
        _six(_r(0, pokemon_id=6, ocr_text="CHARIZARD", confidence=0.9, level=None)),
        _team(None, None, None, None, None, None),
    )
    assert new[0] == TeamSlot(pokemon_id=6, level=50)


def test_empty_ocr_clears_the_slot() -> None:
    new = _apply_team_recognition(
        _six(_r(0, ocr_text="")),
        _team((6, 38), None, None, None, None, None),
    )
    assert new[0] is None


def test_custom_threshold_is_honoured() -> None:
    results = _six(_r(0, pokemon_id=6, ocr_text="CHARIZARD", confidence=0.5, level=38))
    current = _team(None, None, None, None, None, None)
    assert _apply_team_recognition(results, current, min_confidence=0.4)[0] is not None
    assert _apply_team_recognition(results, current, min_confidence=0.9)[0] is None
