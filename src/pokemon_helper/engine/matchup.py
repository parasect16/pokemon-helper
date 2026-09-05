"""Calcolo del confronto (matchup) fra un membro della squadra e un avversario.

Espone due funzioni pure sopra `EffectivenessEngine`:

- `compute_matchup(engine, opp_types, team_types)`: ritorna il moltiplicatore
  massimo di danno che il membro della squadra RICEVE dagli STAB avversari
  (difesa) e quello che INFLIGGE con i propri STAB (offesa).
- `best_matchup_index(matchups)`: seleziona l'indice del membro con il
  matchup più vantaggioso (offesa - difesa massima).
"""

from __future__ import annotations

from collections.abc import Sequence

from pokemon_helper.engine.effectiveness import EffectivenessEngine


def compute_matchup(
    engine: EffectivenessEngine,
    opponent_types: Sequence[str],
    team_member_types: Sequence[str],
) -> tuple[float, float]:
    """Ritorna `(difesa, offesa)` di un membro squadra vs un avversario.

    - `difesa`: massimo moltiplicatore che il membro riceve considerando gli
      attacchi STAB dell'avversario (uno per ciascun tipo dell'avversario).
      Valore alto = il membro subisce molto danno.
    - `offesa`: massimo moltiplicatore che il membro infligge con i propri
      STAB contro l'avversario. Valore alto = il membro può colpire forte.
    """
    if not opponent_types or not team_member_types:
        raise ValueError("both opponent_types and team_member_types must be non-empty")
    team_types_list = list(team_member_types)
    opp_types_list = list(opponent_types)
    defense = max(
        engine.offensive_multiplier(attack_type, team_types_list) for attack_type in opp_types_list
    )
    offense = max(
        engine.offensive_multiplier(attack_type, opp_types_list) for attack_type in team_types_list
    )
    return defense, offense


def best_matchup_index(matchups: Sequence[tuple[float, float]]) -> int:
    """Indice del matchup più vantaggioso, o -1 se `matchups` è vuoto.

    Punteggio: `offesa - difesa`. Il primo indice a raggiungere il massimo
    vince, così il risultato è deterministico e stabile per l'ordine
    canonico della squadra.
    """
    best_index = -1
    best_score = -float("inf")
    for index, (defense, offense) in enumerate(matchups):
        score = offense - defense
        if score > best_score:
            best_score = score
            best_index = index
    return best_index
