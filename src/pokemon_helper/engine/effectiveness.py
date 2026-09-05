"""Motore di calcolo dell'efficacia dei tipi per Gen 1-5.

Espone `EffectivenessEngine`: dato un numero di generazione, calcola il
moltiplicatore offensivo di una mossa contro un difensore mono o bi-tipo e
il profilo difensivo completo (moltiplicatore per ogni tipo di attaccante).
"""

from __future__ import annotations

from collections.abc import Sequence

from pokemon_helper.engine.type_chart import chart_for_generation, types_for_generation


class EffectivenessEngine:
    """Calcolatore di efficacia dei tipi per una generazione specifica.

    L'istanza è immutabile e vincolata a una singola generazione: creane una
    diversa per generazioni diverse. I metodi non hanno side effect.
    """

    def __init__(self, gen: int) -> None:
        """Inizializza il motore per la generazione `gen` (1-5)."""
        # Delego la validazione a `types_for_generation`, che alza `ValueError`
        # per generazioni fuori intervallo. La chiamata popola anche il set di
        # tipi accettati usato da `_validate_type`.
        self._types: tuple[str, ...] = types_for_generation(gen)
        self._chart: dict[str, dict[str, float]] = chart_for_generation(gen)
        self._valid_types: frozenset[str] = frozenset(self._types)
        self._gen: int = gen

    @property
    def generation(self) -> int:
        """Generazione a cui il motore è vincolato."""
        return self._gen

    @property
    def valid_types(self) -> tuple[str, ...]:
        """Elenco ordinato dei tipi validi in questa generazione."""
        return self._types

    def offensive_multiplier(self, move_type: str, defender_types: Sequence[str]) -> float:
        """Restituisce il moltiplicatore totale di `move_type` sul difensore.

        Per un difensore bi-tipo i due moltiplicatori si moltiplicano fra loro
        (es. fuoco su erba/acciaio in Gen 2+: 2 * 2 = 4). Se anche uno solo dei
        due moltiplicatori è 0, il totale è 0 (immunità).
        """
        self._validate_type(move_type)
        self._validate_defender_types(defender_types)

        multiplier = 1.0
        move_row = self._chart.get(move_type, {})
        for defender_type in defender_types:
            multiplier *= move_row.get(defender_type, 1.0)
        return multiplier

    def defensive_profile(self, defender_types: Sequence[str]) -> dict[str, float]:
        """Profilo difensivo: per ogni tipo di attaccante, il moltiplicatore.

        L'ordine delle chiavi rispecchia l'ordine canonico dei tipi della
        generazione (utile per un rendering deterministico in UI).
        """
        self._validate_defender_types(defender_types)
        return {
            attacker: self.offensive_multiplier(attacker, defender_types)
            for attacker in self._types
        }

    def _validate_type(self, type_name: str) -> None:
        """Verifica che `type_name` sia valido nella generazione corrente."""
        if type_name not in self._valid_types:
            raise ValueError(
                f"invalid type {type_name!r} for generation {self._gen}; "
                f"valid types: {sorted(self._valid_types)}"
            )

    def _validate_defender_types(self, defender_types: Sequence[str]) -> None:
        """Verifica cardinalità e appartenenza dei tipi del difensore.

        Un Pokemon ha sempre 1 o 2 tipi: rifiuto tuple vuote o con più di 2
        elementi per intercettare presto errori di input dei chiamanti.
        """
        count = len(defender_types)
        if count < 1 or count > 2:
            raise ValueError(
                f"defender must have 1 or 2 types, got {count}: {list(defender_types)}"
            )
        for defender_type in defender_types:
            self._validate_type(defender_type)
