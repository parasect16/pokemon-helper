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
