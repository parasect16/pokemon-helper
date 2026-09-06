"""Fixture condivise per i test del pacchetto `data`.

Costruisce un database SQLite in-memory popolato con un piccolo insieme di
Pokemon rappresentativo dei casi che ci interessano coprire nei test:

- Bulbasaur (id 1): mono-species classico, tipi stabili nel tempo.
- Charmander (id 4): stessa storia, controllo che nulla di strano succeda.
- Magnemite (id 81): tipo diverso in Gen 1 (Electric) vs Gen 2+ (Electric/Steel).
  Case citato esplicitamente in PLAN §5.
- Magneton (id 82): stessa storia di Magnemite.
- Gastly (id 92): mono-species Gen 1 con tipi ghost/poison invariati.
- Chikorita (id 152): introdotta in Gen 2, non deve avere voci per Gen 1.

Include anche una manciata di `sprite_hashes` sintetici per esercitare la
ricerca via pHash: hash stabili, differenze note in bit conteggiabili.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator

import pytest

from pokemon_helper.data import PokemonRepository, init_schema

# (id, identifier, name_en, name_it, generation_introduced)
_POKEMON_ROWS: tuple[tuple[int, str, str, str | None, int], ...] = (
    (1, "bulbasaur", "Bulbasaur", "Bulbasaur", 1),
    (4, "charmander", "Charmander", "Charmander", 1),
    (81, "magnemite", "Magnemite", "Magnemite", 1),
    (82, "magneton", "Magneton", "Magneton", 1),
    (92, "gastly", "Gastly", "Gastly", 1),
    (152, "chikorita", "Chikorita", "Chikorita", 2),
    # Senza nome italiano: nel dataset reale capita, e il fuzzy match deve
    # cavarsela col solo nome inglese invece di sollevare.
    (129, "magikarp", "Magikarp", None, 1),
)

# Sprite hash sintetici. La coppia (pokemon_id, generation, game, side) è
# unica per rispettare la PRIMARY KEY. I valori esadecimali sono scelti per
# controllare la distanza di Hamming attesa nei test (vedi test_repository).
# `0000000000000000` = bulbasaur front red-blue (baseline)
# `0000000000000001` = bulbasaur back red-blue (Hamming 1 dal baseline)
# `ffffffffffffffff` = charmander (Hamming 64 dal baseline)
# `ffffffffffffffff` = gastly (Hamming 0 da charmander)
_SPRITE_HASH_ROWS: tuple[tuple[int, int, str, str, str, str], ...] = (
    (1, 1, "red-blue", "front", "0000000000000000", "gen1/rb/1.png"),
    (1, 1, "red-blue", "back", "0000000000000001", "gen1/rb/back/1.png"),
    (4, 1, "red-blue", "front", "ffffffffffffffff", "gen1/rb/4.png"),
    (92, 1, "red-blue", "front", "ffffffffffffffff", "gen1/rb/92.png"),
    # Uno sprite Gen 2 per verificare che il filtro per generazione funzioni.
    (1, 2, "gold", "front", "0000000000000000", "gen2/gold/1.png"),
)


# (pokemon_id, generation, slot, type). Solo generazioni in cui il Pokemon esiste.
_TYPES_ROWS: tuple[tuple[int, int, int, str], ...] = (
    # Bulbasaur: grass/poison stabile su tutte le generazioni.
    *((1, gen, 1, "grass") for gen in range(1, 6)),
    *((1, gen, 2, "poison") for gen in range(1, 6)),
    # Charmander: fire, stabile.
    *((4, gen, 1, "fire") for gen in range(1, 6)),
    # Magnemite: Electric in Gen 1, Electric/Steel da Gen 2. Caso PLAN §5.
    (81, 1, 1, "electric"),
    *((81, gen, 1, "electric") for gen in range(2, 6)),
    *((81, gen, 2, "steel") for gen in range(2, 6)),
    # Magneton: stessa storia di Magnemite.
    (82, 1, 1, "electric"),
    *((82, gen, 1, "electric") for gen in range(2, 6)),
    *((82, gen, 2, "steel") for gen in range(2, 6)),
    # Gastly: ghost/poison, stabile.
    *((92, gen, 1, "ghost") for gen in range(1, 6)),
    *((92, gen, 2, "poison") for gen in range(1, 6)),
    # Chikorita: grass, presente solo da Gen 2.
    *((152, gen, 1, "grass") for gen in range(2, 6)),
    # Magikarp: water, stabile.
    *((129, gen, 1, "water") for gen in range(1, 6)),
)


# (id, identifier, name_en, name_it, generation_introduced). Scelte per
# coprire i tre assi del filtro di `get_abilities`: introduzione tardiva,
# abilità nascosta, effetto che dipende dalla generazione.
_ABILITY_ROWS: tuple[tuple[int, str, str, str | None, str | None, int], ...] = (
    (26, "levitate", "Levitate", "Levitazione", "Immune agli attacchi di tipo Terra.", 3),
    (78, "motor-drive", "Motor Drive", "Elettrorapid", None, 4),
    (10, "volt-absorb", "Volt Absorb", None, None, 3),
    (157, "sap-sipper", "Sap Sipper", "Mangiaerba", None, 5),
)

# (pokemon_id, ability_id, slot, is_hidden).
_POKEMON_ABILITY_ROWS: tuple[tuple[int, int, int, int], ...] = (
    # Gastly: una sola abilità, disponibile da Gen 3 → mai ambigua.
    (92, 26, 1, 0),
    # Magnemite: due abilità ordinarie, la seconda introdotta solo in Gen 4.
    (81, 10, 1, 0),
    (81, 78, 2, 0),
    # Bulbasaur: solo un'abilità nascosta, quindi invisibile prima della Gen 5.
    (1, 157, 3, 1),
)


@pytest.fixture
def repository() -> Iterator[PokemonRepository]:
    """Repository su un DB SQLite in-memory precaricato coi dati di test."""
    connection = sqlite3.connect(":memory:")
    init_schema(connection)
    connection.executemany(
        "INSERT INTO pokemon (id, identifier, name_en, name_it, generation_introduced) "
        "VALUES (?, ?, ?, ?, ?)",
        _POKEMON_ROWS,
    )
    connection.executemany(
        "INSERT INTO pokemon_types_by_gen (pokemon_id, generation, slot, type) VALUES (?, ?, ?, ?)",
        _TYPES_ROWS,
    )
    connection.executemany(
        "INSERT INTO abilities "
        "(id, identifier, name_en, name_it, description, generation_introduced) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        _ABILITY_ROWS,
    )
    connection.executemany(
        "INSERT INTO pokemon_abilities (pokemon_id, ability_id, slot, is_hidden) "
        "VALUES (?, ?, ?, ?)",
        _POKEMON_ABILITY_ROWS,
    )
    connection.executemany(
        "INSERT INTO sprite_hashes "
        "(pokemon_id, generation, game, side, phash, source_path) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        _SPRITE_HASH_ROWS,
    )
    connection.commit()

    repo = PokemonRepository(connection)
    try:
        yield repo
    finally:
        repo.close()
