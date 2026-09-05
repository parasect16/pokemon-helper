"""Costruisce `data/pokemon.sqlite` a partire dal dump di veekun/pokedex.

Comportamento:
1. Se `data/vendor/pokedex/` non esiste, esegue un shallow clone (~15 MB) di
   veekun/pokedex. Se esiste, lo riusa (idempotente).
2. Legge i CSV rilevanti (specie, nomi, tipi correnti) e ricostruisce
   ex-novo il database SQLite target (drop del file esistente + init schema
   + insert).

Uso:
    python scripts/build_dataset.py

Requisiti: `git` disponibile nel PATH, ~30 MB liberi.

Cambi di tipo storici (PLAN §5). veekun/pokedex non pubblica in CSV una
tabella `pokemon_types_past`: la storia dei cambi di tipo va codificata a
mano. Nel range Gen 1-5 l'unico cambio noto è la linea Magnemite, che
passa da Electric puro (Gen 1) a Electric/Steel (Gen 2+). Le eccezioni
vivono in `TYPE_HISTORY_OVERRIDES`; se ne emergono altre vanno aggiunte lì.
"""

from __future__ import annotations

import csv
import sqlite3
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

from pokemon_helper.data import init_schema

# ---------------------------------------------------------------------------
# Costanti di configurazione
# ---------------------------------------------------------------------------

REPO_URL = "https://github.com/veekun/pokedex.git"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VENDOR_DIR = PROJECT_ROOT / "data" / "vendor" / "pokedex"
CSV_DIR = VENDOR_DIR / "pokedex" / "data" / "csv"
DB_PATH = PROJECT_ROOT / "data" / "pokemon.sqlite"

MAX_GEN = 5
ITALIAN_ISO = "it"
ENGLISH_ISO = "en"


# Cambi di tipo storici non desumibili dai CSV veekun (vedi docstring modulo).
# Struttura: species_id -> {generation: ((slot, type_identifier), ...)}.
# Per una data specie in una data generazione, se qui c'è un override, si usa
# quello al posto dei tipi correnti letti da pokemon_types.csv.
TYPE_HISTORY_OVERRIDES: dict[int, dict[int, tuple[tuple[int, str], ...]]] = {
    # Magnemite: Electric puro in Gen 1, diventa Electric/Steel da Gen 2.
    81: {1: ((1, "electric"),)},
    # Magneton: stessa storia della sua pre-evoluzione.
    82: {1: ((1, "electric"),)},
}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> int:
    """Punto d'ingresso: garantisce la presenza del vendor e ricostruisce il DB."""
    ensure_vendor_clone()
    build_database()
    return 0


# ---------------------------------------------------------------------------
# Vendoring del dump veekun
# ---------------------------------------------------------------------------


def ensure_vendor_clone() -> None:
    """Effettua uno shallow clone di veekun/pokedex se non ancora presente.

    L'operazione è idempotente: se `CSV_DIR` esiste, non viene fatto nulla.
    Se il clone fallisce, l'errore viene propagato al chiamante.
    """
    if CSV_DIR.exists():
        print(f"[skip] vendor already present at {VENDOR_DIR}")
        return

    print(f"[clone] {REPO_URL} -> {VENDOR_DIR}")
    VENDOR_DIR.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "clone", "--depth=1", REPO_URL, str(VENDOR_DIR)],
        check=True,
    )
    if not CSV_DIR.exists():
        raise RuntimeError(
            f"expected CSV directory {CSV_DIR} not found after clone; "
            "upstream layout may have changed"
        )


# ---------------------------------------------------------------------------
# Costruzione del database
# ---------------------------------------------------------------------------


def build_database() -> None:
    """Ricostruisce il DB SQLite. Sovrascrive un eventuale file esistente."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(DB_PATH)
    try:
        init_schema(conn)
        ingest_pokemon(conn)
        ingest_types_by_gen(conn)
        conn.commit()
    finally:
        conn.close()
    print(f"[done] wrote {DB_PATH}")


def ingest_pokemon(conn: sqlite3.Connection) -> None:
    """Popola la tabella `pokemon` con le specie di Gen 1-5.

    Usa `pokemon_species` come base (una riga per specie) e arricchisce con
    il nome italiano da `pokemon_species_names` quando disponibile.
    """
    lang_ids = _language_ids()

    species_rows = [
        row for row in _read_csv("pokemon_species.csv") if 1 <= int(row["generation_id"]) <= MAX_GEN
    ]

    names_by_lang = _species_names_by_lang()

    inserts: list[tuple[int, str, str, str | None, int]] = []
    for row in species_rows:
        species_id = int(row["id"])
        identifier = row["identifier"]
        # Nome inglese: usa il nome ufficiale, con fallback all'identifier
        # capitalizzato se il record non esiste (non dovrebbe capitare).
        name_en = names_by_lang.get(lang_ids[ENGLISH_ISO], {}).get(species_id, identifier.title())
        name_it = names_by_lang.get(lang_ids[ITALIAN_ISO], {}).get(species_id)
        inserts.append((species_id, identifier, name_en, name_it, int(row["generation_id"])))

    conn.executemany(
        "INSERT INTO pokemon (id, identifier, name_en, name_it, generation_introduced) "
        "VALUES (?, ?, ?, ?, ?)",
        inserts,
    )
    print(f"[ingest] pokemon: {len(inserts)} rows")


def ingest_types_by_gen(conn: sqlite3.Connection) -> None:
    """Popola `pokemon_types_by_gen` per ogni specie e generazione applicabile.

    Base: `pokemon_types.csv` restituisce i tipi correnti (Gen 5 nel contesto
    di questo dataset, dato che l'ultima generazione in scope è la V).
    Correzione: per ciascuna generazione, se `TYPE_HISTORY_OVERRIDES` ha una
    entry per (species, gen), quella sovrascrive i tipi correnti.

    Solo la specie di default viene considerata (Deoxys / Wormadam / ecc.
    saranno modellati quando servirà distinguerne le forme).
    """
    types_map = {int(row["id"]): row["identifier"] for row in _read_csv("types.csv")}

    default_pokemon_by_species = _default_pokemon_ids_for_species(conn)
    current_types = _current_types_by_pokemon(types_map)

    inserts: list[tuple[int, int, int, str]] = []
    for species_id, pokemon_id in default_pokemon_by_species.items():
        introduced = _generation_introduced(conn, species_id)
        for gen in range(introduced, MAX_GEN + 1):
            for slot, type_name in _types_in_generation(
                species_id, gen, current_types.get(pokemon_id, [])
            ):
                inserts.append((species_id, gen, slot, type_name))

    conn.executemany(
        "INSERT INTO pokemon_types_by_gen (pokemon_id, generation, slot, type) VALUES (?, ?, ?, ?)",
        inserts,
    )
    print(f"[ingest] pokemon_types_by_gen: {len(inserts)} rows")


# ---------------------------------------------------------------------------
# Helper di lettura CSV
# ---------------------------------------------------------------------------


def _read_csv(name: str) -> list[dict[str, str]]:
    """Legge un CSV di veekun come lista di dict (colonna -> valore stringa)."""
    with (CSV_DIR / name).open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _language_ids() -> dict[str, int]:
    """Mappa iso639 -> id per le lingue di interesse (it, en)."""
    languages = _read_csv("languages.csv")
    result: dict[str, int] = {}
    for row in languages:
        identifier = row["identifier"]
        if identifier in {ITALIAN_ISO, ENGLISH_ISO}:
            result[identifier] = int(row["id"])
    missing = {ITALIAN_ISO, ENGLISH_ISO} - result.keys()
    if missing:
        raise RuntimeError(f"missing language rows for: {sorted(missing)}")
    return result


def _species_names_by_lang() -> dict[int, dict[int, str]]:
    """Restituisce `{lang_id: {species_id: display_name}}`."""
    result: dict[int, dict[int, str]] = defaultdict(dict)
    for row in _read_csv("pokemon_species_names.csv"):
        lang_id = int(row["local_language_id"])
        species_id = int(row["pokemon_species_id"])
        result[lang_id][species_id] = row["name"]
    return result


def _default_pokemon_ids_for_species(
    conn: sqlite3.Connection,
) -> dict[int, int]:
    """Per ogni specie in `pokemon`, ritorna l'id della sua forma di default.

    In veekun `pokemon` contiene sia forme base sia varianti (Deoxys, ecc.).
    `is_default = 1` identifica la forma canonica, quella che vogliamo usare
    per associare tipi e sprite alla specie.
    """
    known_species: set[int] = {row[0] for row in conn.execute("SELECT id FROM pokemon")}
    result: dict[int, int] = {}
    for row in _read_csv("pokemon.csv"):
        if int(row["is_default"]) != 1:
            continue
        species_id = int(row["species_id"])
        if species_id in known_species:
            result[species_id] = int(row["id"])
    return result


def _current_types_by_pokemon(
    types_map: dict[int, str],
) -> dict[int, list[tuple[int, str]]]:
    """`{pokemon_id: [(slot, type_identifier), ...]}` dai tipi correnti."""
    result: dict[int, list[tuple[int, str]]] = defaultdict(list)
    for row in _read_csv("pokemon_types.csv"):
        pid = int(row["pokemon_id"])
        result[pid].append((int(row["slot"]), types_map[int(row["type_id"])]))
    return result


def _generation_introduced(conn: sqlite3.Connection, species_id: int) -> int:
    """Ritorna la generazione di introduzione di una specie dal DB corrente."""
    row = conn.execute(
        "SELECT generation_introduced FROM pokemon WHERE id = ?",
        (species_id,),
    ).fetchone()
    return int(row[0])


def _types_in_generation(
    species_id: int,
    generation: int,
    current_types: list[tuple[int, str]],
) -> list[tuple[int, str]]:
    """Restituisce i tipi di una specie in una generazione data.

    Se in `TYPE_HISTORY_OVERRIDES` esiste una entry per (species, generation),
    la usa; altrimenti restituisce i tipi correnti (assunti costanti nel
    range Gen 1-5 salvo le eccezioni codificate a mano).
    """
    override = TYPE_HISTORY_OVERRIDES.get(species_id, {}).get(generation)
    if override is not None:
        return sorted(override, key=lambda pair: pair[0])
    return sorted(current_types, key=lambda pair: pair[0])


if __name__ == "__main__":
    sys.exit(main())
