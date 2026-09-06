"""Test delle funzioni pure di `vision.recognizer`.

Copre il match dei nickname utente, che è l'unico stadio del riconoscimento
a non dipendere né da OCR né dal database: `_match_nickname` lavora solo su
stringhe, quindi è testabile senza frame né SQLite.
"""

from __future__ import annotations

import pytest

from pokemon_helper.vision.recognizer import _fuzzy_species, _id_allowed, _match_nickname

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


class _FakeRepo:
    """Repo minimo: risponde solo a `find_by_fuzzy_name` da un dizionario."""

    def __init__(self, by_query: dict[str, list[tuple[int, float]]]) -> None:
        self._by_query = by_query
        self.queries: list[str] = []

    def find_by_fuzzy_name(self, query, generation, *, min_similarity, limit):
        self.queries.append(query)
        return [(_FakePokemon(pid), score) for pid, score in self._by_query.get(query, [])]


class _FakePokemon:
    def __init__(self, pokemon_id: int) -> None:
        self.id = pokemon_id


def _fuzzy(repo, text):
    return _fuzzy_species(repo, text, 3, min_similarity=0.55, limit=1)


def test_raw_text_matches_without_second_pass() -> None:
    repo = _FakeRepo({"GLOOH": [(44, 0.8)]})
    assert _fuzzy(repo, "GLOOH") == [(44, 0.8)]
    assert repo.queries == ["GLOOH"]


def test_digit_normalization_runs_only_after_a_miss() -> None:
    """`P1DGEOT` non matcha grezzo; il secondo giro prova `PIDGEOT`."""
    repo = _FakeRepo({"PIDGEOT": [(18, 0.9)]})
    assert _fuzzy(repo, "P1DGEOT") == [(18, 0.9)]
    assert repo.queries == ["P1DGEOT", "PIDGEOT"]


def test_legit_digit_name_is_not_rewritten() -> None:
    """Porygon2 matcha al primo giro, quindi la rimappatura non lo tocca."""
    repo = _FakeRepo({"PORYGON2": [(233, 1.0)]})
    assert _fuzzy(repo, "PORYGON2") == [(233, 1.0)]
    assert repo.queries == ["PORYGON2"]


def test_no_second_pass_when_text_has_no_digits() -> None:
    repo = _FakeRepo({})
    assert _fuzzy(repo, "ZZZZZ") == []
    assert repo.queries == ["ZZZZZ"]


def test_second_pass_can_also_miss() -> None:
    repo = _FakeRepo({})
    assert _fuzzy(repo, "ZZ1ZZ") == []
    assert repo.queries == ["ZZ1ZZ", "ZZIZZ"]
