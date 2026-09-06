"""Test delle funzioni pure di `vision.recognizer`.

Copre il match dei nickname utente, che è l'unico stadio del riconoscimento
a non dipendere né da OCR né dal database: `_match_nickname` lavora solo su
stringhe, quindi è testabile senza frame né SQLite.
"""

from __future__ import annotations

import pytest

from pokemon_helper.vision.recognizer import _id_allowed, _match_nickname

# Charizard = 6, Pikachu = 25, Gloom = 44.
NICKNAMES = {"FIAMMETTA": 6, "SPARKY": 25}


def test_exact_match_wins_with_full_score() -> None:
    assert _match_nickname("FIAMMETTA", NICKNAMES, min_similarity=1.0) == (6, 1.0)


def test_exact_match_is_case_and_space_insensitive() -> None:
    assert _match_nickname("  fiammetta ", NICKNAMES, min_similarity=1.0) == (6, 1.0)


def test_ocr_misread_matches_via_fuzzy() -> None:
    """Il caso reale: RapidOCR legge `M` come `H` sul font pixel FRLG."""
    match = _match_nickname("FIAHHETTA", NICKNAMES)
    assert match is not None
    pokemon_id, score = match
    assert pokemon_id == 6
    assert 0.72 <= score < 1.0


def test_ocr_misread_is_rejected_by_exact_stage() -> None:
    """Lo stadio esatto non deve assorbire i misread: è compito del fuzzy."""
    assert _match_nickname("FIAHHETTA", NICKNAMES, min_similarity=1.0) is None


def test_unrelated_text_below_threshold_returns_none() -> None:
    assert _match_nickname("DUGTRIO", NICKNAMES) is None


def test_best_of_several_candidates_wins() -> None:
    nicknames = {"SPARKY": 25, "SPARKIE": 26}
    match = _match_nickname("SPARKIE", nicknames)
    assert match == (26, 1.0)


def test_tie_is_deterministic_by_nickname_order() -> None:
    """Due nickname equidistanti: vince il primo in ordine alfabetico."""
    nicknames = {"BOB": 1, "ROB": 2}
    first = _match_nickname("XOB", nicknames, min_similarity=0.6)
    second = _match_nickname("XOB", nicknames, min_similarity=0.6)
    assert first == second == (1, pytest.approx(2 / 3))


@pytest.mark.parametrize("text", ["", "   "])
def test_empty_text_returns_none(text: str) -> None:
    assert _match_nickname(text, NICKNAMES) is None


@pytest.mark.parametrize("mapping", [None, {}])
def test_empty_map_returns_none(mapping: dict[str, int] | None) -> None:
    assert _match_nickname("FIAMMETTA", mapping) is None


def test_id_allowed_without_filter() -> None:
    assert _id_allowed(6, None) is True


def test_id_allowed_with_filter() -> None:
    assert _id_allowed(6, {6, 25}) is True
    assert _id_allowed(44, {6, 25}) is False
