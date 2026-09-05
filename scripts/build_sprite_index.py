"""Popola la tabella `sprite_hashes` con il pHash di ogni sprite Gen 1-5.

Passi:
1. Se `data/vendor/sprites/` non esiste, esegue uno sparse clone di
   `PokeAPI/sprites` limitato ai path `sprites/pokemon/versions/generation-{i..v}/`
   (~500 MB su disco — la maggior parte è composta da GIF animate di Gen 5).
2. Apre il DB esistente `data/pokemon.sqlite` (deve essere già stato costruito
   con `scripts/build_dataset.py`; le foreign key su `pokemon.id` puntano lì).
3. Applica lo schema (idempotente), svuota `sprite_hashes` per la ricostruzione,
   scandisce le directory dei giochi principali per ogni generazione, calcola
   il pHash di ciascun PNG e inserisce una riga per ogni combinazione
   (pokemon_id, generation, game, side).

Uso:
    python scripts/build_sprite_index.py

Requisiti:
- `git` nel PATH.
- Deps `[vision]`: `Pillow`, `imagehash`. Installare con
  `pip install -e ".[dev,app,vision]"` prima di lanciare lo script.
- Il DB `data/pokemon.sqlite` prodotto da `build_dataset.py`.

Sono considerati solo gli sprite dei giochi principali di ciascuna generazione;
GIF animate, varianti shiny, per-genere, in scala di grigi e "icons"/"box" sono
esclusi in questa iterazione — verranno reintrodotti se il match runtime lo
richiederà.
"""

from __future__ import annotations

import sqlite3
import subprocess
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path

import imagehash
from PIL import Image, UnidentifiedImageError

from pokemon_helper.data import init_schema

# ---------------------------------------------------------------------------
# Paths e mappe
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "pokemon.sqlite"

SPRITES_REPO_URL = "https://github.com/PokeAPI/sprites.git"
SPRITES_VENDOR_DIR = PROJECT_ROOT / "data" / "vendor" / "sprites"
SPRITES_ROOT = SPRITES_VENDOR_DIR / "sprites" / "pokemon" / "versions"

# Solo giochi "principali" per generazione. Skip:
# - red-green-japan (release JP, ridondante con red-blue per il nostro scopo)
# - icons/ (sprite ridotti box)
GAMES_BY_GENERATION: dict[int, tuple[str, ...]] = {
    1: ("red-blue", "yellow"),
    2: ("gold", "silver", "crystal"),
    3: ("ruby-sapphire", "emerald", "firered-leafgreen"),
    4: ("diamond-pearl", "platinum", "heartgold-soulsilver"),
    5: ("black-white",),
}

MAX_SPECIES_ID = 649  # Ultimo Pokemon Gen 5 (Genesect).


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> int:
    """Vendoring degli sprite + indicizzazione pHash in `sprite_hashes`."""
    ensure_sprite_vendor()
    if not DB_PATH.exists():
        print(
            f"ERROR: DB {DB_PATH} non presente. Esegui prima `python scripts/build_dataset.py`.",
            file=sys.stderr,
        )
        return 2
    known_ids = _load_known_species_ids()
    if not known_ids:
        print("ERROR: nessuna specie trovata nel DB.", file=sys.stderr)
        return 2

    conn = sqlite3.connect(DB_PATH)
    try:
        init_schema(conn)
        # Ricostruzione totale della tabella: rende lo script idempotente
        # e ci risparmia il tracking degli aggiornamenti/delete.
        conn.execute("DELETE FROM sprite_hashes")

        inserted = 0
        for row in _iter_sprite_rows(known_ids):
            conn.execute(
                "INSERT OR REPLACE INTO sprite_hashes "
                "(pokemon_id, generation, game, side, phash, source_path) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                row,
            )
            inserted += 1
            if inserted % 500 == 0:
                print(f"[progress] {inserted} rows...")
        conn.commit()
        print(f"[done] wrote {inserted} sprite_hashes rows to {DB_PATH}")
    finally:
        conn.close()
    return 0


# ---------------------------------------------------------------------------
# Vendoring
# ---------------------------------------------------------------------------


def ensure_sprite_vendor() -> None:
    """Sparse clone di `PokeAPI/sprites` filtrato alle directory Gen 1-5.

    Idempotente: se la directory `SPRITES_ROOT` esiste già, non fa nulla.
    """
    if SPRITES_ROOT.exists():
        print(f"[skip] sprite vendor già presente in {SPRITES_VENDOR_DIR}")
        return

    print(f"[clone] {SPRITES_REPO_URL} -> {SPRITES_VENDOR_DIR}")
    SPRITES_VENDOR_DIR.parent.mkdir(parents=True, exist_ok=True)
    # `--filter=blob:none` scarica solo tree/commit; `--sparse` inizializza in
    # modalità sparse checkout (solo file di root disponibili subito).
    subprocess.run(
        [
            "git",
            "clone",
            "--filter=blob:none",
            "--sparse",
            SPRITES_REPO_URL,
            str(SPRITES_VENDOR_DIR),
        ],
        check=True,
    )
    # Espandi la sparse checkout ai path che ci interessano.
    subprocess.run(
        [
            "git",
            "-C",
            str(SPRITES_VENDOR_DIR),
            "sparse-checkout",
            "set",
            *[
                f"sprites/pokemon/versions/generation-{roman}"
                for roman in ("i", "ii", "iii", "iv", "v")
            ],
        ],
        check=True,
    )
    if not SPRITES_ROOT.exists():
        raise RuntimeError(
            f"expected sprite tree {SPRITES_ROOT} not found after sparse checkout; "
            "upstream layout may have changed"
        )


# ---------------------------------------------------------------------------
# Iterazione + hashing
# ---------------------------------------------------------------------------


def _iter_sprite_rows(
    known_species: frozenset[int],
) -> Iterator[tuple[int, int, str, str, str, str]]:
    """Yield `(pokemon_id, generation, game, side, phash, source_path)`.

    - Front sprites: PNG diretti nella dir del gioco (`{id}.png`).
    - Back sprites: PNG dentro `back/` (`back/{id}.png`).
    - Skip file con id fuori range noto (forme alternative, id > 9999, ecc.).
    - Skip file non decodificabili come immagine.
    """
    _generation_to_roman = {1: "i", 2: "ii", 3: "iii", 4: "iv", 5: "v"}

    for generation, games in GAMES_BY_GENERATION.items():
        gen_dir = SPRITES_ROOT / f"generation-{_generation_to_roman[generation]}"
        for game in games:
            game_dir = gen_dir / game
            if not game_dir.is_dir():
                print(f"[warn] {game_dir} mancante; salto")
                continue
            for side, base_dir in (("front", game_dir), ("back", game_dir / "back")):
                if not base_dir.is_dir():
                    continue
                for png_path in _iter_png_children(base_dir):
                    try:
                        pokemon_id = int(png_path.stem)
                    except ValueError:
                        continue
                    if pokemon_id not in known_species:
                        continue
                    phash = _compute_phash(png_path)
                    if phash is None:
                        continue
                    relative = png_path.relative_to(SPRITES_VENDOR_DIR).as_posix()
                    yield (pokemon_id, generation, game, side, phash, relative)


def _iter_png_children(directory: Path) -> Iterable[Path]:
    """Elenca solo i PNG figli diretti (non ricorsivo)."""
    for entry in directory.iterdir():
        if entry.is_file() and entry.suffix.lower() == ".png":
            yield entry


def _compute_phash(path: Path) -> str | None:
    """Calcola il pHash di un'immagine come stringa esadecimale di 16 caratteri.

    Ritorna `None` se il file non è un'immagine valida; l'errore viene
    stampato ma non alza (uno sprite corrotto non deve fermare l'ingest).
    """
    try:
        with Image.open(path) as image:
            image.load()
            return str(imagehash.phash(image))
    except (OSError, UnidentifiedImageError) as exc:
        print(f"[warn] impossibile decodificare {path.name}: {exc}")
        return None


def _load_known_species_ids() -> frozenset[int]:
    """Legge dal DB tutti gli id di specie noti."""
    conn = sqlite3.connect(DB_PATH)
    try:
        rows = conn.execute("SELECT id FROM pokemon").fetchall()
    finally:
        conn.close()
    return frozenset(int(row[0]) for row in rows if int(row[0]) <= MAX_SPECIES_ID)


if __name__ == "__main__":
    sys.exit(main())
