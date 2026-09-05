"""Test per gli helper puri di `pokemon_helper.ui.app`.

Focus sulle heuristiche che decidono se una snapshot di `recognize_team`
proviene davvero dal menu Pokemon o da un'altra schermata (combattimento,
mondo, ecc.). Non tocchiamo Qt né worker: gli helper sono funzioni pure.
"""

from __future__ import annotations

from dataclasses import dataclass

from pokemon_helper.ui.app import _team_snapshot_looks_like_menu


@dataclass(frozen=True, slots=True)
class _FakeResult:
    """Stand-in per `TeamRecognition` che espone solo i campi usati."""

    slot_index: int
    pokemon_id: int | None
    ocr_text: str = ""


def _r(index: int, pokemon_id: int | None = None, ocr_text: str = "") -> _FakeResult:
    """Shorthand per costruire un fake result."""
    return _FakeResult(slot_index=index, pokemon_id=pokemon_id, ocr_text=ocr_text)


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
