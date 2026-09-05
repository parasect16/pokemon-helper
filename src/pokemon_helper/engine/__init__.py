"""Motore di combattimento: efficacia dei tipi e calcoli correlati."""

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
    "CHART_GEN1",
    "CHART_GEN2_5",
    "EffectivenessEngine",
    "TYPES_GEN1",
    "TYPES_GEN2_5",
    "best_matchup_index",
    "chart_for_generation",
    "compute_matchup",
    "types_for_generation",
]
