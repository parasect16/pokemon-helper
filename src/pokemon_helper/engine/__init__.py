"""Motore di combattimento: efficacia dei tipi e calcoli correlati."""

from pokemon_helper.engine.abilities import (
    ABILITY_EFFECTS,
    AbilityEffect,
    apply_ability,
    modifies_effectiveness,
)
from pokemon_helper.engine.effectiveness import EffectivenessEngine
from pokemon_helper.engine.matchup import best_matchup_index, compute_matchup
from pokemon_helper.engine.type_chart import (
    CHART_GEN1,
    CHART_GEN2_5,
    TYPES_GEN1,
    TYPES_GEN2_5,
    chart_for_generation,
    types_for_generation,
)

__all__ = [
    "ABILITY_EFFECTS",
    "AbilityEffect",
    "CHART_GEN1",
    "CHART_GEN2_5",
    "EffectivenessEngine",
    "TYPES_GEN1",
    "TYPES_GEN2_5",
    "apply_ability",
    "best_matchup_index",
    "chart_for_generation",
    "compute_matchup",
    "modifies_effectiveness",
    "types_for_generation",
]
