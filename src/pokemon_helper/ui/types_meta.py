"""Metadata di presentazione per i tipi Pokemon.

Contiene i due mapping usati nella UI:

- `TYPE_LABELS_IT`: nome canonico inglese -> nome italiano da mostrare.
- `TYPE_COLORS`: nome canonico inglese -> colore HEX di background.

I nomi inglesi (`fire`, `ghost`, ecc.) restano l'identificatore canonico in
tutto il codice: questo modulo li traduce solo al momento del rendering.
"""

from __future__ import annotations

TYPE_LABELS_IT: dict[str, str] = {
    "normal": "Normale",
    "fire": "Fuoco",
    "water": "Acqua",
    "electric": "Elettro",
    "grass": "Erba",
    "ice": "Ghiaccio",
    "fighting": "Lotta",
    "poison": "Veleno",
    "ground": "Terra",
    "flying": "Volante",
    "psychic": "Psico",
    "bug": "Coleottero",
    "rock": "Roccia",
    "ghost": "Spettro",
    "dragon": "Drago",
    "dark": "Buio",
    "steel": "Acciaio",
}

# Palette allineata alla convenzione grafica classica dei giochi Pokemon.
TYPE_COLORS: dict[str, str] = {
    "normal": "#A8A878",
    "fire": "#F08030",
    "water": "#6890F0",
    "electric": "#F8D030",
    "grass": "#78C850",
    "ice": "#98D8D8",
    "fighting": "#C03028",
    "poison": "#A040A0",
    "ground": "#E0C068",
    "flying": "#A890F0",
    "psychic": "#F85888",
    "bug": "#A8B820",
    "rock": "#B8A038",
    "ghost": "#705898",
    "dragon": "#7038F8",
    "dark": "#705848",
    "steel": "#B8B8D0",
}


def label_it(type_name: str) -> str:
    """Nome italiano del tipo; fallback all'input capitalizzato se ignoto."""
    return TYPE_LABELS_IT.get(type_name, type_name.title())


def color_for(type_name: str) -> str:
    """Colore HEX associato al tipo; fallback a grigio neutro se ignoto."""
    return TYPE_COLORS.get(type_name, "#888888")
