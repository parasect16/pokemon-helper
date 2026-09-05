"""Test del repository dei Pokemon."""

from __future__ import annotations

import sqlite3

import pytest

from pokemon_helper.data import Pokemon, PokemonRepository, SpriteMatch

# ---------------------------------------------------------------------------
# get_by_id
# ---------------------------------------------------------------------------


def test_get_by_id_returns_pokemon_for_known_id(repository: PokemonRepository) -> None:
    """Un id noto deve restituire il Pokemon corrispondente."""
    result = repository.get_by_id(1)
    assert result == Pokemon(
        id=1,
        identifier="bulbasaur",
        name_en="Bulbasaur",
        name_it="Bulbasaur",
        generation_introduced=1,
    )


def test_get_by_id_returns_none_for_unknown_id(repository: PokemonRepository) -> None:
    """Un id inesistente deve restituire None, non alzare."""
    assert repository.get_by_id(9999) is None


# ---------------------------------------------------------------------------
# find_by_name
# ---------------------------------------------------------------------------


def test_find_by_name_matches_italian_case_insensitive(
    repository: PokemonRepository,
) -> None:
    """La ricerca per nome italiano deve essere case-insensitive."""
    results = repository.find_by_name("magnemite", lang="it")
    assert len(results) == 1
    assert results[0].id == 81


def test_find_by_name_matches_english(repository: PokemonRepository) -> None:
    """Con lang='en' la ricerca avviene sulla colonna inglese."""
    results = repository.find_by_name("Charmander", lang="en")
    assert len(results) == 1
    assert results[0].identifier == "charmander"


def test_find_by_name_returns_empty_for_unknown_name(
    repository: PokemonRepository,
) -> None:
    """Un nome inesistente restituisce lista vuota."""
    assert repository.find_by_name("Mewtwo", lang="it") == []


def test_find_by_name_rejects_unsupported_language(
    repository: PokemonRepository,
) -> None:
    """Una lingua non supportata alza ValueError."""
    with pytest.raises(ValueError, match="unsupported language 'de'"):
        repository.find_by_name("Bulbasaur", lang="de")


# ---------------------------------------------------------------------------
# get_types — inclusi i casi Gen 1→Gen 2 di PLAN §5
# ---------------------------------------------------------------------------


def test_get_types_magnemite_gen1_is_electric_only(repository: PokemonRepository) -> None:
    """Magnemite in Gen 1 è mono-tipo Electric (PLAN §5)."""
    assert repository.get_types(81, 1) == ("electric",)


def test_get_types_magnemite_gen2_adds_steel(repository: PokemonRepository) -> None:
    """Da Gen 2 Magnemite diventa Electric/Steel (PLAN §5)."""
    assert repository.get_types(81, 2) == ("electric", "steel")


@pytest.mark.parametrize("gen", [3, 4, 5])
def test_get_types_magnemite_stable_from_gen2(repository: PokemonRepository, gen: int) -> None:
    """Da Gen 2 in poi il tipo di Magnemite non cambia più."""
    assert repository.get_types(81, gen) == ("electric", "steel")


def test_get_types_magneton_gen1_is_electric_only(repository: PokemonRepository) -> None:
    """Anche Magneton segue lo stesso pattern di Magnemite."""
    assert repository.get_types(82, 1) == ("electric",)


def test_get_types_gastly_stable_across_generations(
    repository: PokemonRepository,
) -> None:
    """Gastly mantiene ghost/poison in tutte le generazioni."""
    for gen in range(1, 6):
        assert repository.get_types(92, gen) == ("ghost", "poison")


def test_get_types_returns_slot_order(repository: PokemonRepository) -> None:
    """L'ordine della tupla deve rispettare lo slot (primo tipo prima)."""
    types = repository.get_types(1, 3)
    assert types == ("grass", "poison")


def test_get_types_empty_for_pokemon_not_yet_introduced(
    repository: PokemonRepository,
) -> None:
    """Chikorita è Gen 2: chiedere i suoi tipi in Gen 1 restituisce tupla vuota."""
    assert repository.get_types(152, 1) == ()


def test_get_types_empty_for_unknown_pokemon(repository: PokemonRepository) -> None:
    """Un id inesistente restituisce tupla vuota (non alza)."""
    assert repository.get_types(9999, 3) == ()


def test_get_types_rejects_unsupported_generation(
    repository: PokemonRepository,
) -> None:
    """Generazione fuori intervallo 1-5 alza ValueError."""
    with pytest.raises(ValueError, match="unsupported generation"):
        repository.get_types(1, 6)


# ---------------------------------------------------------------------------
# list_by_generation
# ---------------------------------------------------------------------------


def test_list_by_generation_gen1_excludes_chikorita(repository: PokemonRepository) -> None:
    """La lista in Gen 1 non deve contenere Pokemon introdotti da Gen 2."""
    ids = {p.id for p in repository.list_by_generation(1)}
    assert 152 not in ids
    assert 1 in ids


def test_list_by_generation_gen2_includes_chikorita(repository: PokemonRepository) -> None:
    """Da Gen 2 Chikorita compare nella lista."""
    ids = {p.id for p in repository.list_by_generation(2)}
    assert 152 in ids


def test_list_by_generation_orders_by_id(repository: PokemonRepository) -> None:
    """La lista deve essere ordinata per id crescente."""
    ids = [p.id for p in repository.list_by_generation(5)]
    assert ids == sorted(ids)


def test_list_by_generation_rejects_out_of_range(repository: PokemonRepository) -> None:
    """Generazione fuori intervallo alza ValueError."""
    with pytest.raises(ValueError, match="unsupported generation"):
        repository.list_by_generation(0)


# ---------------------------------------------------------------------------
# Costruzione, context manager, gestione connessione
# ---------------------------------------------------------------------------


def test_repository_open_creates_working_repo(tmp_path) -> None:
    """`PokemonRepository.open` deve creare un repo funzionante da un file."""
    from pokemon_helper.data import init_schema

    db_file = tmp_path / "test.sqlite"
    conn = sqlite3.connect(db_file)
    init_schema(conn)
    conn.execute(
        "INSERT INTO pokemon (id, identifier, name_en, name_it, generation_introduced) "
        "VALUES (?, ?, ?, ?, ?)",
        (1, "bulbasaur", "Bulbasaur", "Bulbasaur", 1),
    )
    conn.commit()
    conn.close()

    with PokemonRepository.open(db_file) as repo:
        result = repo.get_by_id(1)
        assert result is not None
        assert result.identifier == "bulbasaur"


def test_init_schema_is_idempotent() -> None:
    """Applicare la DDL due volte non deve alzare (CREATE TABLE IF NOT EXISTS)."""
    from pokemon_helper.data import init_schema

    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    init_schema(conn)
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    conn.close()
    names = {t[0] for t in tables}
    assert "pokemon" in names
    assert "pokemon_types_by_gen" in names
    assert "sprite_hashes" in names


# ---------------------------------------------------------------------------
# find_pokemon_by_sprite_hash
# ---------------------------------------------------------------------------


def test_find_by_sprite_hash_exact_match(repository: PokemonRepository) -> None:
    """Hash identico a Bulbasaur Gen 1 front deve dare distanza 0."""
    matches = repository.find_pokemon_by_sprite_hash("0000000000000000", generation=1)
    assert matches
    top = matches[0]
    assert isinstance(top, SpriteMatch)
    assert top.pokemon_id == 1
    assert top.distance == 0


def test_find_by_sprite_hash_dedupes_best_per_pokemon(
    repository: PokemonRepository,
) -> None:
    """Per Bulbasaur ci sono due sprite Gen 1 (front dist 0, back dist 1).

    Il risultato deve contenere una sola riga per Bulbasaur con la migliore
    distanza (0), scegliendo front rispetto a back.
    """
    matches = repository.find_pokemon_by_sprite_hash("0000000000000000", generation=1)
    bulba_matches = [m for m in matches if m.pokemon_id == 1]
    assert len(bulba_matches) == 1
    assert bulba_matches[0].side == "front"
    assert bulba_matches[0].distance == 0


def test_find_by_sprite_hash_tolerates_small_hamming(
    repository: PokemonRepository,
) -> None:
    """Query con 1 bit di differenza rispetto a Bulbasaur back → dist 1."""
    # 1 bit flippato rispetto a "0000000000000001" (Bulbasaur back)
    matches = repository.find_pokemon_by_sprite_hash("0000000000000003", generation=1)
    top = matches[0]
    assert top.pokemon_id == 1
    assert top.distance in (1, 2)


def test_find_by_sprite_hash_max_distance_filters(
    repository: PokemonRepository,
) -> None:
    """Con max_distance basso, sprite molto diversi non compaiono."""
    # Query = tutti 0. Charmander/Gastly hanno tutti F (distanza 64).
    matches = repository.find_pokemon_by_sprite_hash(
        "0000000000000000", generation=1, max_distance=2
    )
    ids = {m.pokemon_id for m in matches}
    assert 4 not in ids  # Charmander troppo distante
    assert 92 not in ids  # Gastly troppo distante
    assert 1 in ids


def test_find_by_sprite_hash_filters_by_generation(
    repository: PokemonRepository,
) -> None:
    """Cambiando generazione, la scansione ignora sprite di altre gen."""
    # Bulbasaur ha hash "0000000000000000" sia in Gen 1 sia in Gen 2, ma
    # Charmander e Gastly hanno voci solo in Gen 1. In Gen 2 la ricerca
    # restituisce solo Bulbasaur.
    matches = repository.find_pokemon_by_sprite_hash("0000000000000000", generation=2)
    ids = {m.pokemon_id for m in matches}
    assert ids == {1}


def test_find_by_sprite_hash_rejects_wrong_hash_length(
    repository: PokemonRepository,
) -> None:
    """Un hash non di 16 caratteri esadecimali è un bug del chiamante."""
    with pytest.raises(ValueError, match="16 hex characters"):
        repository.find_pokemon_by_sprite_hash("deadbeef", generation=1)


def test_find_by_sprite_hash_rejects_unsupported_generation(
    repository: PokemonRepository,
) -> None:
    """Generazione fuori 1-5 alza ValueError."""
    with pytest.raises(ValueError, match="unsupported generation"):
        repository.find_pokemon_by_sprite_hash("0" * 16, generation=6)


def test_find_by_sprite_hash_limit_caps_results(repository: PokemonRepository) -> None:
    """`limit` limita il numero di Pokemon restituiti."""
    # Con max_distance=64 tutti i pokemon della gen matchano; limit=1 lascia uno.
    matches = repository.find_pokemon_by_sprite_hash(
        "0000000000000000", generation=1, max_distance=64, limit=1
    )
    assert len(matches) == 1
