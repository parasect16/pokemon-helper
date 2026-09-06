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

Cambi storici non desumibili dai CSV (PLAN §5). veekun/pokedex non pubblica
né `pokemon_types_past` né l'equivalente per le abilità: entrambi i CSV
descrivono l'assegnazione **corrente**, e la storia va codificata a mano.

- Tipi: nel range Gen 1-5 l'unico cambio noto è la linea Magnemite, da
  Electric puro (Gen 1) a Electric/Steel (Gen 2+). Vive in
  `TYPE_HISTORY_OVERRIDES`.
- Abilità: Gengar aveva Levitazione fino alla Gen 6 e l'ha persa in Gen 7,
  quindi il CSV corrente la ometterebbe proprio dove serve. Vive in
  `ABILITY_HISTORY_OVERRIDES`.

Attenzione: questo script **ricrea il file da zero**, quindi cancella anche
`sprite_hashes`. Dopo averlo eseguito va rilanciato `build_sprite_index.py`.
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

# Cambi di abilità storici, stesso problema dei tipi: `pokemon_abilities.csv`
# descrive l'assegnazione corrente e veekun non ship quella storica.
# Struttura: species_id -> (identifier abilità in ordine di slot, ...). Qui non
# serve distinguere per generazione: gli override elencati valgono per tutte le
# generazioni in scope (1-5), dato che i cambi sono avvenuti dopo.
#
# Il caso che conta è Gengar, ed è anche il motivo per cui questa tabella
# esiste: aveva Levitazione dalla Gen 3 alla Gen 6 e l'ha persa in Gen 7. Senza
# override, in Rosso Fuoco risulterebbe senza abilità e il pannello
# continuerebbe a consigliare mosse di Terra contro un Pokemon che ne è immune
# — esattamente l'errore che questa funzionalità deve eliminare.
#
# Le altre 30 specie con Levitazione nel dataset l'hanno mantenuta, Gastly e
# Haunter compresi: è solo Gengar ad essere cambiato.
ABILITY_HISTORY_OVERRIDES: dict[int, tuple[str, ...]] = {
    94: ("levitate",),
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
        ingest_abilities(conn)
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


def ingest_abilities(conn: sqlite3.Connection) -> None:
    """Popola `abilities` e `pokemon_abilities`.

    Vengono importate solo le abilità introdotte entro `MAX_GEN`: quelle più
    recenti non possono comparire in nessun gioco in scope. Le abilità non
    esistono affatto prima della Gen 3, quindi `abilities` non contiene nulla
    di anteriore.

    `pokemon_abilities.csv` di veekun descrive l'assegnazione **corrente**,
    non quella storica — stesso limite già noto per `pokemon_types.csv`. Il
    filtro per generazione di introduzione dell'abilità copre il caso
    frequente (un'abilità di Gen 4 non è disponibile in Gen 3); i rari casi in
    cui una specie ha cambiato abilità restando la stessa abilità disponibile
    non sono ricostruibili da questi CSV.
    """
    lang_ids = _language_ids()
    names_by_lang = _ability_names_by_lang()

    ability_rows = [
        row for row in _read_csv("abilities.csv") if int(row["generation_id"]) <= MAX_GEN
    ]
    descriptions = _ability_descriptions(lang_ids)

    ability_inserts: list[tuple[int, str, str, str | None, str | None, int]] = []
    for row in ability_rows:
        ability_id = int(row["id"])
        identifier = row["identifier"]
        name_en = names_by_lang.get(lang_ids[ENGLISH_ISO], {}).get(ability_id, identifier.title())
        name_it = names_by_lang.get(lang_ids[ITALIAN_ISO], {}).get(ability_id)
        ability_inserts.append(
            (
                ability_id,
                identifier,
                name_en,
                name_it,
                descriptions.get(ability_id),
                int(row["generation_id"]),
            )
        )

    conn.executemany(
        "INSERT INTO abilities "
        "(id, identifier, name_en, name_it, description, generation_introduced) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ability_inserts,
    )

    # Solo le specie già presenti in `pokemon`, e solo le abilità importate.
    known_species = {row[0] for row in conn.execute("SELECT id FROM pokemon")}
    known_abilities = {row[0] for row in ability_inserts}
    species_by_pokemon = {
        pokemon_id: species_id
        for species_id, pokemon_id in _default_pokemon_ids_for_species(conn).items()
    }

    ability_ids_by_identifier = {row[1]: row[0] for row in ability_inserts}

    link_inserts: list[tuple[int, int, int, int]] = []
    for row in _read_csv("pokemon_abilities.csv"):
        species_id = species_by_pokemon.get(int(row["pokemon_id"]))
        ability_id = int(row["ability_id"])
        if species_id is None or species_id not in known_species:
            continue
        if ability_id not in known_abilities:
            continue
        if species_id in ABILITY_HISTORY_OVERRIDES:
            continue
        link_inserts.append((species_id, ability_id, int(row["slot"]), int(row["is_hidden"])))

    for species_id, identifiers in ABILITY_HISTORY_OVERRIDES.items():
        if species_id not in known_species:
            continue
        for slot, identifier in enumerate(identifiers, start=1):
            ability_id = ability_ids_by_identifier.get(identifier)
            if ability_id is None:
                raise KeyError(f"override references unknown ability {identifier!r}")
            link_inserts.append((species_id, ability_id, slot, 0))

    conn.executemany(
        "INSERT OR IGNORE INTO pokemon_abilities (pokemon_id, ability_id, slot, is_hidden) "
        "VALUES (?, ?, ?, ?)",
        link_inserts,
    )
    print(f"[ingest] abilities: {len(ability_inserts)} rows")
    print(f"[ingest] pokemon_abilities: {len(link_inserts)} rows")


# ---------------------------------------------------------------------------
# Helper di lettura CSV
# ---------------------------------------------------------------------------


def _read_csv(name: str) -> list[dict[str, str]]:
    """Legge un CSV di veekun come lista di dict (colonna -> valore stringa)."""
    with (CSV_DIR / name).open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _ability_descriptions(lang_ids: dict[str, int]) -> dict[int, str]:
    """Descrizione discorsiva per abilità, italiano con fallback inglese.

    La sorgente è `ability_flavor_text.csv`, cioè il testo che il gioco mostra
    davvero. `ability_prose.csv` avrebbe descrizioni più precise ma infarcite
    di markup (`[termine]{mechanic:...}`) e disponibili solo in inglese e
    tedesco.

    Di ogni abilità si prende il testo del `version_group_id` più alto: le
    riformulazioni successive sono di norma più chiare e la copertura è
    migliore sui gruppi recenti. Gli a-capo del gioco diventano spazi, perché
    il testo finisce in un tooltip che va a capo da solo.
    """
    by_lang: dict[int, dict[int, tuple[int, str]]] = {}
    for row in _read_csv("ability_flavor_text.csv"):
        lang = int(row["language_id"])
        ability_id = int(row["ability_id"])
        version_group = int(row["version_group_id"])
        best = by_lang.setdefault(lang, {}).get(ability_id)
        if best is None or version_group > best[0]:
            by_lang[lang][ability_id] = (version_group, row["flavor_text"])

    italian = by_lang.get(lang_ids[ITALIAN_ISO], {})
    english = by_lang.get(lang_ids[ENGLISH_ISO], {})
    descriptions: dict[int, str] = {}
    for ability_id in set(italian) | set(english):
        entry = italian.get(ability_id) or english.get(ability_id)
        if entry is not None:
            descriptions[ability_id] = " ".join(entry[1].split())
    return descriptions


def _ability_names_by_lang() -> dict[int, dict[int, str]]:
    """Mappa lingua -> {ability_id -> nome localizzato}."""
    by_lang: dict[int, dict[int, str]] = {}
    for row in _read_csv("ability_names.csv"):
        lang = int(row["local_language_id"])
        by_lang.setdefault(lang, {})[int(row["ability_id"])] = row["name"]
    return by_lang


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
