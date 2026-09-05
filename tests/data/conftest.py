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
    connection.commit()

    repo = PokemonRepository(connection)
    try:
        yield repo
    finally:
        repo.close()
