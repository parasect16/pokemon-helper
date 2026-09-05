"""Accesso in lettura al dataset SQLite dei Pokemon.

Espone `PokemonRepository`, una thin-wrapper attorno a `sqlite3.Connection`
che restituisce oggetti di dominio (`Pokemon`) invece di righe grezze.

Il repository è pensato per essere costruito una volta (dall'UI o dal main)
e passato ai componenti che ne hanno bisogno. Le query sono di lettura pura:
la costruzione del database è compito di `scripts/build_dataset.py`.
"""

from __future__ import annotations

import sqlite3
from difflib import SequenceMatcher
from pathlib import Path

from pokemon_helper.data.models import Pokemon, SpriteMatch

# Lingue accettate da `find_by_name`. Estendibile in futuro (es. "de", "fr").
_SUPPORTED_LANGUAGES: frozenset[str] = frozenset({"it", "en"})


class PokemonRepository:
    """Repository di sola lettura sopra un database SQLite del Pokedex.

    L'istanza gestisce una singola `sqlite3.Connection`. Non è thread-safe:
    se serve accesso concorrente, apri connessioni separate per thread.
    """

    def __init__(self, connection: sqlite3.Connection) -> None:
        """Costruisce il repository sopra una connessione già aperta.

        Configura la `row_factory` a `sqlite3.Row` per abilitare l'accesso
        alle colonne per nome nelle funzioni di mapping.
        """
        self._conn = connection
        self._conn.row_factory = sqlite3.Row

    @classmethod
    def open(cls, db_path: Path | str) -> PokemonRepository:
        """Apre una connessione al file SQLite e restituisce il repository.

        Il chiamante è responsabile di invocare `close()` (o usare `with`).
        """
        connection = sqlite3.connect(db_path)
        return cls(connection)

    def close(self) -> None:
        """Chiude la connessione sottostante."""
        self._conn.close()

    def __enter__(self) -> PokemonRepository:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def get_by_id(self, pokemon_id: int) -> Pokemon | None:
        """Restituisce il Pokemon con l'id dato, o `None` se non presente."""
        row = self._conn.execute(
            "SELECT id, identifier, name_en, name_it, generation_introduced "
            "FROM pokemon WHERE id = ?",
            (pokemon_id,),
        ).fetchone()
        return _row_to_pokemon(row) if row is not None else None

    def find_by_name(self, name: str, *, lang: str = "it") -> list[Pokemon]:
        """Cerca Pokemon per nome esatto (case-insensitive) nella lingua data.

        `lang` accetta "it" o "en". Ritorna lista ordinata per id.
        Match esatto sulla colonna corrispondente; per ricerca fuzzy usare
        un layer superiore (verrà aggiunto quando l'UI lo richiederà).
        """
        if lang not in _SUPPORTED_LANGUAGES:
            raise ValueError(
                f"unsupported language {lang!r}; expected one of {sorted(_SUPPORTED_LANGUAGES)}"
            )
        # Colonna scelta staticamente da un allow-list: nessun rischio SQL injection.
        column = "name_it" if lang == "it" else "name_en"
        rows = self._conn.execute(
            f"SELECT id, identifier, name_en, name_it, generation_introduced "
            f"FROM pokemon WHERE {column} = ? COLLATE NOCASE "
            f"ORDER BY id",
            (name,),
        ).fetchall()
        return [_row_to_pokemon(row) for row in rows]

    def get_types(self, pokemon_id: int, generation: int) -> tuple[str, ...]:
        """Restituisce i tipi del Pokemon nella generazione data, ordinati per slot.

        Tupla vuota se il Pokemon non ha voci per quella generazione (per esempio
        perché introdotto in una generazione successiva).
        """
        if not 1 <= generation <= 5:
            raise ValueError(f"unsupported generation: {generation}")
        rows = self._conn.execute(
            "SELECT type FROM pokemon_types_by_gen "
            "WHERE pokemon_id = ? AND generation = ? "
            "ORDER BY slot",
            (pokemon_id, generation),
        ).fetchall()
        return tuple(row["type"] for row in rows)

    def list_by_generation(self, generation: int) -> list[Pokemon]:
        """Elenca i Pokemon introdotti fino alla generazione data (incluso).

        Utile per popolare selezioni nell'UI (es. dropdown "scegli Pokemon").
        """
        if not 1 <= generation <= 5:
            raise ValueError(f"unsupported generation: {generation}")
        rows = self._conn.execute(
            "SELECT id, identifier, name_en, name_it, generation_introduced "
            "FROM pokemon WHERE generation_introduced <= ? "
            "ORDER BY id",
            (generation,),
        ).fetchall()
        return [_row_to_pokemon(row) for row in rows]

    def find_by_fuzzy_name(
        self,
        query: str,
        generation: int,
        *,
        min_similarity: float = 0.6,
        limit: int = 5,
    ) -> list[tuple[Pokemon, float]]:
        """Cerca Pokemon per nome tollerante agli errori tipografici (OCR).

        Score = max(similarity_it, similarity_en) via `difflib.SequenceMatcher`.
        Filtra i Pokemon introdotti fino alla generazione data e restituisce
        i top `limit` con score ≥ `min_similarity`, ordinati per score decrescente.

        Progettato per raffinare l'output di RapidOCR (che tipicamente sbaglia
        1-2 caratteri su nomi Pokemon con font pixel).
        """
        if not 1 <= generation <= 5:
            raise ValueError(f"unsupported generation: {generation}")
        needle = query.strip().lower()
        if not needle:
            return []

        candidates = self.list_by_generation(generation)
        scored: list[tuple[Pokemon, float]] = []
        for pokemon in candidates:
            names = [pokemon.name_en.lower()]
            if pokemon.name_it:
                names.append(pokemon.name_it.lower())
            score = max(SequenceMatcher(None, needle, name).ratio() for name in names)
            if score >= min_similarity:
                scored.append((pokemon, score))

        scored.sort(key=lambda item: (-item[1], item[0].id))
        return scored[:limit]

    def get_sprite_source_path(
        self,
        pokemon_id: int,
        generation: int,
        *,
        side: str = "front",
        preferred_game: str | None = None,
    ) -> str | None:
        """Restituisce il path relativo (dentro `data/vendor/sprites/`) di uno
        sprite indicizzato, o `None` se il DB non ne ha nessuno per quella
        combinazione.

        Preferisce `preferred_game` se passato; altrimenti restituisce il
        primo match qualsiasi per (pokemon, generazione, side).
        """
        if preferred_game is not None:
            row = self._conn.execute(
                "SELECT source_path FROM sprite_hashes "
                "WHERE pokemon_id = ? AND generation = ? AND side = ? AND game = ? "
                "LIMIT 1",
                (pokemon_id, generation, side, preferred_game),
            ).fetchone()
            if row is not None:
                return str(row["source_path"])
        row = self._conn.execute(
            "SELECT source_path FROM sprite_hashes "
            "WHERE pokemon_id = ? AND generation = ? AND side = ? "
            "LIMIT 1",
            (pokemon_id, generation, side),
        ).fetchone()
        return str(row["source_path"]) if row is not None else None

    def find_pokemon_by_sprite_hash(
        self,
        query_phash: str,
        generation: int,
        *,
        sides: tuple[str, ...] | None = None,
        max_distance: int = 12,
        limit: int = 5,
    ) -> list[SpriteMatch]:
        """Cerca lo sprite indicizzato più simile al pHash fornito.

        La ricerca è ristretta agli sprite della generazione indicata e (se
        `sides` è passato) ai lati richiesti — `('icon',)` per il match sulle
        mini icone del menu Pokemon, `('front', 'back')` per gli sprite di
        combattimento. `None` significa "tutti i lati".

        Per ogni sprite calcola la distanza di Hamming rispetto a
        `query_phash`; scarta i risultati oltre `max_distance` e restituisce
        fino a `limit` Pokemon distinti ordinati per distanza crescente
        (best-per-Pokemon).
        """
        if not 1 <= generation <= 5:
            raise ValueError(f"unsupported generation: {generation}")
        if len(query_phash) != 16:
            raise ValueError(f"query_phash must be 16 hex characters, got {len(query_phash)}")
        query_int = int(query_phash, 16)

        query = (
            "SELECT pokemon_id, generation, game, side, phash "
            "FROM sprite_hashes WHERE generation = ?"
        )
        params: list = [generation]
        if sides:
            placeholders = ",".join("?" for _ in sides)
            query += f" AND side IN ({placeholders})"
            params.extend(sides)
        rows = self._conn.execute(query, params).fetchall()

        # Migliore corrispondenza per pokemon (dedupe multi-game/side).
        best_by_pokemon: dict[int, SpriteMatch] = {}
        for row in rows:
            distance = _hamming(query_int, int(row["phash"], 16))
            if distance > max_distance:
                continue
            existing = best_by_pokemon.get(row["pokemon_id"])
            if existing is not None and existing.distance <= distance:
                continue
            best_by_pokemon[row["pokemon_id"]] = SpriteMatch(
                pokemon_id=row["pokemon_id"],
                generation=row["generation"],
                game=row["game"],
                side=row["side"],
                distance=distance,
                phash=row["phash"],
            )

        ranked = sorted(
            best_by_pokemon.values(),
            key=lambda match: (match.distance, match.pokemon_id),
        )
        return ranked[:limit]


def _row_to_pokemon(row: sqlite3.Row) -> Pokemon:
    """Converte una `sqlite3.Row` in un `Pokemon` di dominio."""
    return Pokemon(
        id=row["id"],
        identifier=row["identifier"],
        name_en=row["name_en"],
        name_it=row["name_it"],
        generation_introduced=row["generation_introduced"],
    )


def _hamming(a: int, b: int) -> int:
    """Distanza di Hamming fra due interi (numero di bit differenti)."""
    return (a ^ b).bit_count()
