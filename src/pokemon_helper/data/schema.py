"""Schema SQLite del dataset Pokemon.

Definisce lo schema come costante DDL e una funzione di inizializzazione.
La stessa DDL è consumata sia dallo script di build (`scripts/build_dataset.py`)
sia dai test, che creano un database in-memory con lo stesso schema.

Scelte di design:
- Modello species-level: una riga per Pokemon "base". Le forme alternative
  (Deoxys, Wormadam, ecc.) e le varianti per genere non sono modellate in
  questa fase; verranno introdotte insieme al riconoscimento sprite.
- `pokemon_types_by_gen` è denormalizzato per generazione: una riga per
  (pokemon, generazione, slot). Consente la query "quali tipi ha X in Gen G"
  senza dover applicare a runtime la logica di `past_types`.
"""

from __future__ import annotations

import sqlite3

SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS pokemon (
    id INTEGER PRIMARY KEY,
    identifier TEXT NOT NULL UNIQUE,
    name_en TEXT NOT NULL,
    name_it TEXT,
    generation_introduced INTEGER NOT NULL
        CHECK (generation_introduced BETWEEN 1 AND 5)
);

CREATE INDEX IF NOT EXISTS idx_pokemon_name_it ON pokemon(name_it);
CREATE INDEX IF NOT EXISTS idx_pokemon_name_en ON pokemon(name_en);

CREATE TABLE IF NOT EXISTS pokemon_types_by_gen (
    pokemon_id INTEGER NOT NULL,
    generation INTEGER NOT NULL CHECK (generation BETWEEN 1 AND 5),
    slot INTEGER NOT NULL CHECK (slot IN (1, 2)),
    type TEXT NOT NULL,
    PRIMARY KEY (pokemon_id, generation, slot),
    FOREIGN KEY (pokemon_id) REFERENCES pokemon(id)
);
"""


def init_schema(connection: sqlite3.Connection) -> None:
    """Applica la DDL alla connessione fornita.

    Idempotente grazie a `CREATE TABLE IF NOT EXISTS`.
    """
    connection.executescript(SCHEMA_DDL)
