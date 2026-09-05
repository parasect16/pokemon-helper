"""Test del calcolo del matchup squadra vs avversario."""

from __future__ import annotations

import pytest

from pokemon_helper.engine import (
    EffectivenessEngine,
    best_matchup_index,
    compute_matchup,
)

# ---------------------------------------------------------------------------
# compute_matchup
# ---------------------------------------------------------------------------


def test_compute_matchup_bulbasaur_vs_charizard_gen3() -> None:
    """Bulbasaur (grass/poison) vs Charizard (fire/flying): 2x subisce, 1x max infligge."""
    engine = EffectivenessEngine(3)
    defense, offense = compute_matchup(engine, ("fire", "flying"), ("grass", "poison"))
    assert defense == 2.0  # fire vs grass/poison = 2*1
    assert offense == 1.0  # poison vs fire/flying = 1*1 (grass sarebbe 0.25)


def test_compute_matchup_squirtle_vs_charizard_gen3() -> None:
    """Squirtle (water) vs Charizard: matchup ottimo — resiste e colpisce 2x."""
    engine = EffectivenessEngine(3)
    defense, offense = compute_matchup(engine, ("fire", "flying"), ("water",))
    assert defense == 1.0  # fire vs water=0.5, flying vs water=1 → max=1
    assert offense == 2.0  # water vs fire/flying = 2*1


def test_compute_matchup_ground_vs_dual_with_immunity() -> None:
    """Se attaccante ha immunità in uno slot, quel tipo dà 0; il max tiene degli altri."""
    engine = EffectivenessEngine(3)
    # Golem (ground/rock) contro Zapdos (electric/flying).
    # Difesa: electric vs ground/rock = 0*1=0; flying vs ground/rock = 1*0.5=0.5 → max=0.5
    # Offesa: ground vs electric/flying = 2*0=0; rock vs electric/flying = 1*2=2 → max=2
    defense, offense = compute_matchup(engine, ("electric", "flying"), ("ground", "rock"))
    assert defense == 0.5
    assert offense == 2.0


def test_compute_matchup_full_immunity_defense() -> None:
    """Se lo STAB avversario è immune, la difesa vale 0 (nessun danno STAB)."""
    engine = EffectivenessEngine(3)
    # Rattata (normal) vs Gastly (ghost/poison):
    #   normal vs ghost=0, normal vs poison=1 → total 0 (normal è immune contro ghost)
    defense, offense = compute_matchup(engine, ("normal",), ("ghost", "poison"))
    assert defense == 0.0
    # Offesa: ghost vs normal=0, poison vs normal=1 → max=1
    assert offense == 1.0


def test_compute_matchup_rejects_empty_types() -> None:
    """Tipi vuoti non ammessi: caller passa Pokemon senza tipi (bug a monte)."""
    engine = EffectivenessEngine(3)
    with pytest.raises(ValueError, match="non-empty"):
        compute_matchup(engine, (), ("water",))
    with pytest.raises(ValueError, match="non-empty"):
        compute_matchup(engine, ("fire",), ())


# ---------------------------------------------------------------------------
# best_matchup_index
# ---------------------------------------------------------------------------


def test_best_matchup_index_prefers_higher_offense_lower_defense() -> None:
    """L'indice migliore è quello con score `offense - defense` massimo."""
    matchups = [
        (2.0, 1.0),  # score -1
        (1.0, 2.0),  # score +1 ← best
        (2.0, 2.0),  # score 0
    ]
    assert best_matchup_index(matchups) == 1


def test_best_matchup_index_returns_first_on_ties() -> None:
    """A parità di score, vince il primo indice (deterministico)."""
    matchups = [(1.0, 2.0), (0.5, 1.5), (1.0, 2.0)]
    # Tutti hanno score = 1.0; ci aspettiamo l'indice 0.
    assert best_matchup_index(matchups) == 0


def test_best_matchup_index_empty_returns_minus_one() -> None:
    """Sequenza vuota: -1 sentinel."""
    assert best_matchup_index([]) == -1


def test_best_matchup_index_immunity_beats_neutral() -> None:
    """Difesa 0 (immune) + offesa 2 batte defense 1 + offesa 2."""
    matchups = [(1.0, 2.0), (0.0, 2.0)]
    assert best_matchup_index(matchups) == 1
