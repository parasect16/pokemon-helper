"""Modelli di dominio del dataset Pokemon."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Pokemon:
    """Rappresentazione a livello di specie di un Pokemon.

    Non modella le forme alternative (Deoxys, Wormadam, varianti per genere):
    verranno introdotte quando servirà distinguerle nel riconoscimento sprite.

    Attributi:
        id: identificatore numerico stabile (allineato a PokeAPI / Pokedex Nazionale).
        identifier: slug in inglese, minuscolo, es. "bulbasaur".
        name_en: nome in inglese formattato per display, es. "Bulbasaur".
        name_it: nome in italiano, se disponibile nel dataset upstream.
        generation_introduced: generazione in cui il Pokemon è stato introdotto (1..5).
    """

    id: int
    identifier: str
    name_en: str
    name_it: str | None
    generation_introduced: int


@dataclass(frozen=True, slots=True)
class Ability:
    """Abilità di un Pokemon, disponibile in una data generazione.

    Attributi:
        id: identificatore numerico allineato al Pokedex.
        identifier: slug in inglese, es. "levitate". È la chiave con cui
            `engine.abilities` decide se e come modificare l'efficacia.
        name_en: nome in inglese formattato per display.
        name_it: nome in italiano, se disponibile nel dataset upstream.
        slot: 1 o 2 per le abilità ordinarie, 3 per la nascosta.
        is_hidden: abilità nascosta, esistente solo dalla Gen 5.
    """

    id: int
    identifier: str
    name_en: str
    name_it: str | None
    slot: int
    is_hidden: bool

    @property
    def display_name(self) -> str:
        """Nome da mostrare: italiano se c'è, altrimenti inglese."""
        return self.name_it or self.name_en


@dataclass(frozen=True, slots=True)
class SpriteMatch:
    """Corrispondenza fra uno sprite catturato e un Pokemon indicizzato.

    Prodotto da `PokemonRepository.find_pokemon_by_sprite_hash`.
    L'istanza contiene il pokemon più prossimo per un singolo (game, side)
    con la sua distanza di Hamming rispetto al pHash query.

    Attributi:
        pokemon_id: id della specie associata allo sprite indicizzato.
        generation: generazione del gioco a cui appartiene lo sprite.
        game: identificativo del gioco (es. "red-blue", "black-white").
        side: "front" o "back".
        distance: distanza di Hamming (0-64) fra query e hash indicizzato.
        phash: hash indicizzato in forma esadecimale (16 caratteri).
    """

    pokemon_id: int
    generation: int
    game: str
    side: str
    distance: int
    phash: str
