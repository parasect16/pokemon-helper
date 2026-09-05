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

-- pHash degli sprite dei Pokemon per (generazione, gioco, lato).
-- Il pHash è memorizzato come stringa esadecimale di 16 caratteri
-- (64 bit dell'algoritmo pHash di imagehash). L'unicità è garantita a
-- livello di combinazione (specie, gen, gioco, lato). Le corrispondenze
-- a runtime avvengono via Hamming distance, calcolata lato Python.
CREATE TABLE IF NOT EXISTS sprite_hashes (
    pokemon_id INTEGER NOT NULL,
    generation INTEGER NOT NULL CHECK (generation BETWEEN 1 AND 5),
    game TEXT NOT NULL,
    -- 'front'/'back' = sprite completo in battaglia; 'icon' = mini sprite
    -- del menu Pokemon (32x32 tipico) usato per il match della squadra.
    side TEXT NOT NULL CHECK (side IN ('front', 'back', 'icon')),
    phash TEXT NOT NULL,
    source_path TEXT NOT NULL,
    PRIMARY KEY (pokemon_id, generation, game, side),
    FOREIGN KEY (pokemon_id) REFERENCES pokemon(id)
);

CREATE INDEX IF NOT EXISTS idx_sprite_hashes_gen ON sprite_hashes(generation);
"""


def init_schema(connection: sqlite3.Connection) -> None:
    """Applica la DDL alla connessione fornita.

    Idempotente grazie a `CREATE TABLE IF NOT EXISTS`.
    """
    connection.executescript(SCHEMA_DDL)
