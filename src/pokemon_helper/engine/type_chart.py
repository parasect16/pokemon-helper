"""Tabelle di efficacia dei tipi per le generazioni 1-5.

Le tabelle sono codificate in forma sparsa: sono presenti solo le voci con
moltiplicatore diverso da 1.0. Ogni voce mancante vale 1.0 (danno neutro).

Riferimenti storici (PLAN.md §5):
- In Gen 1 i tipi Buio (dark) e Acciaio (steel) non esistono.
- In Gen 1 Spettro (ghost) contro Psico (psychic) è 0 per un bug del gioco.
- In Gen 1 Coleottero (bug) contro Veleno (poison) è 2x e viceversa.
- In Gen 1 Ghiaccio (ice) contro Fuoco (fire) è neutro; da Gen 2 diventa 0.5x.

I nomi dei tipi sono in inglese (allineati a PokeAPI). Il mapping in italiano
per l'interfaccia utente vive in un modulo separato.
"""

from __future__ import annotations

# Elenco canonico dei tipi validi in ciascun blocco di generazioni.
TYPES_GEN1: tuple[str, ...] = (
    "normal",
    "fire",
    "water",
    "electric",
    "grass",
    "ice",
    "fighting",
    "poison",
    "ground",
    "flying",
    "psychic",
    "bug",
    "rock",
    "ghost",
    "dragon",
)

TYPES_GEN2_5: tuple[str, ...] = TYPES_GEN1 + ("dark", "steel")


# Tabella Gen 2-5 (stabile per Gen 2, 3, 4, 5). Solo voci non-neutre.
# Struttura: CHART[attacker][defender] = multiplier.
CHART_GEN2_5: dict[str, dict[str, float]] = {
    "normal": {"rock": 0.5, "ghost": 0.0, "steel": 0.5},
    "fire": {
        "fire": 0.5,
        "water": 0.5,
        "grass": 2.0,
        "ice": 2.0,
        "bug": 2.0,
        "rock": 0.5,
        "dragon": 0.5,
        "steel": 2.0,
    },
    "water": {
        "fire": 2.0,
        "water": 0.5,
        "grass": 0.5,
        "ground": 2.0,
        "rock": 2.0,
        "dragon": 0.5,
    },
    "electric": {
        "water": 2.0,
        "electric": 0.5,
        "grass": 0.5,
        "ground": 0.0,
        "flying": 2.0,
        "dragon": 0.5,
    },
    "grass": {
        "fire": 0.5,
        "water": 2.0,
        "grass": 0.5,
        "poison": 0.5,
        "ground": 2.0,
        "flying": 0.5,
        "bug": 0.5,
        "rock": 2.0,
        "dragon": 0.5,
        "steel": 0.5,
    },
    "ice": {
        "fire": 0.5,
        "water": 0.5,
        "grass": 2.0,
        "ice": 0.5,
        "ground": 2.0,
        "flying": 2.0,
        "dragon": 2.0,
        "steel": 0.5,
    },
    "fighting": {
        "normal": 2.0,
        "ice": 2.0,
        "poison": 0.5,
        "flying": 0.5,
        "psychic": 0.5,
        "bug": 0.5,
        "rock": 2.0,
        "ghost": 0.0,
        "dark": 2.0,
        "steel": 2.0,
    },
    "poison": {
        "grass": 2.0,
        "poison": 0.5,
        "ground": 0.5,
        "rock": 0.5,
        "ghost": 0.5,
        "steel": 0.0,
    },
    "ground": {
        "fire": 2.0,
        "electric": 2.0,
        "grass": 0.5,
        "poison": 2.0,
        "flying": 0.0,
        "bug": 0.5,
        "rock": 2.0,
        "steel": 2.0,
    },
    "flying": {
        "electric": 0.5,
        "grass": 2.0,
        "fighting": 2.0,
        "bug": 2.0,
        "rock": 0.5,
        "steel": 0.5,
    },
    "psychic": {
        "fighting": 2.0,
        "poison": 2.0,
        "psychic": 0.5,
        "dark": 0.0,
        "steel": 0.5,
    },
    "bug": {
        "fire": 0.5,
        "grass": 2.0,
        "fighting": 0.5,
        "poison": 0.5,
        "flying": 0.5,
        "psychic": 2.0,
        "ghost": 0.5,
        "dark": 2.0,
        "steel": 0.5,
    },
    "rock": {
        "fire": 2.0,
        "ice": 2.0,
        "fighting": 0.5,
        "ground": 0.5,
        "flying": 2.0,
        "bug": 2.0,
        "steel": 0.5,
    },
    "ghost": {
        "normal": 0.0,
        "psychic": 2.0,
        "ghost": 2.0,
        "dark": 0.5,
        "steel": 0.5,
    },
    "dragon": {"dragon": 2.0, "steel": 0.5},
    "dark": {
        "fighting": 0.5,
        "psychic": 2.0,
        "ghost": 2.0,
        "dark": 0.5,
        "steel": 0.5,
    },
    "steel": {
        "fire": 0.5,
        "water": 0.5,
        "electric": 0.5,
        "ice": 2.0,
        "rock": 2.0,
        "steel": 0.5,
    },
}


# Tabella Gen 1. Deriva da CHART_GEN2_5 rimuovendo tutti i riferimenti a
# dark/steel e applicando le eccezioni storiche documentate sopra.
def _build_gen1_chart() -> dict[str, dict[str, float]]:
    """Costruisce la tabella Gen 1 a partire dalla Gen 2-5.

    Rimuove i tipi introdotti in Gen 2 (dark, steel) sia come attaccanti sia
    come difensori, poi applica le eccezioni storiche di Gen 1.
    """
    modern_types = frozenset(TYPES_GEN2_5) - frozenset(TYPES_GEN1)

    chart: dict[str, dict[str, float]] = {}
    for attacker, defenses in CHART_GEN2_5.items():
        if attacker in modern_types:
            continue
        chart[attacker] = {
            defender: mult for defender, mult in defenses.items() if defender not in modern_types
        }

    # Eccezioni Gen 1 (vedi PLAN.md §5).
    # Spettro contro Psico: il gioco applica un bug che rende la mossa a 0.
    chart.setdefault("ghost", {})["psychic"] = 0.0
    # Coleottero contro Veleno: superefficace in Gen 1, 0.5x da Gen 2.
    chart.setdefault("bug", {})["poison"] = 2.0
    # Veleno contro Coleottero: superefficace in Gen 1, neutro da Gen 2.
    chart.setdefault("poison", {})["bug"] = 2.0
    # Ghiaccio contro Fuoco: neutro in Gen 1, 0.5x da Gen 2.
    # Rimuovo la voce (assenza = 1.0) invece di scrivere 1.0 esplicito.
    chart.get("ice", {}).pop("fire", None)

    return chart


CHART_GEN1: dict[str, dict[str, float]] = _build_gen1_chart()


def types_for_generation(gen: int) -> tuple[str, ...]:
    """Restituisce la tupla dei tipi validi per la generazione data."""
    if gen == 1:
        return TYPES_GEN1
    if 2 <= gen <= 5:
        return TYPES_GEN2_5
    raise ValueError(f"unsupported generation: {gen}")


def chart_for_generation(gen: int) -> dict[str, dict[str, float]]:
    """Restituisce la tabella di efficacia per la generazione data."""
    if gen == 1:
        return CHART_GEN1
    if 2 <= gen <= 5:
        return CHART_GEN2_5
    raise ValueError(f"unsupported generation: {gen}")
