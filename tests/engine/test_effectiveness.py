"""Test del motore di efficacia dei tipi.

Copre i casi limite di Gen 1 elencati in PLAN.md §5 e la logica di
moltiplicazione per difensori bi-tipo per Gen 2-5.
"""

from __future__ import annotations

import pytest

from pokemon_helper.engine import (
    TYPES_GEN1,
    TYPES_GEN2_5,
    EffectivenessEngine,
    chart_for_generation,
    types_for_generation,
)

# ---------------------------------------------------------------------------
# Costruzione del motore e validazione della generazione
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("gen", [1, 2, 3, 4, 5])
def test_engine_accepts_generations_1_to_5(gen: int) -> None:
    """Le generazioni 1-5 sono supportate: il costruttore non deve alzare."""
    engine = EffectivenessEngine(gen)
    assert engine.generation == gen


@pytest.mark.parametrize("gen", [0, 6, -1, 100])
def test_engine_rejects_generations_outside_range(gen: int) -> None:
    """Fuori dall'intervallo 1-5 il motore deve rifiutare la costruzione."""
    with pytest.raises(ValueError, match="unsupported generation"):
        EffectivenessEngine(gen)


def test_valid_types_gen1_has_15_types_no_dark_no_steel() -> None:
    """Gen 1 espone 15 tipi; dark e steel non devono esserci."""
    engine = EffectivenessEngine(1)
    assert len(engine.valid_types) == 15
    assert "dark" not in engine.valid_types
    assert "steel" not in engine.valid_types


def test_valid_types_gen2_has_17_types_with_dark_and_steel() -> None:
    """Da Gen 2 in poi ci sono 17 tipi con dark e steel."""
    engine = EffectivenessEngine(2)
    assert len(engine.valid_types) == 17
    assert "dark" in engine.valid_types
    assert "steel" in engine.valid_types


# ---------------------------------------------------------------------------
# Eccezioni storiche Gen 1 (PLAN.md §5)
# ---------------------------------------------------------------------------


def test_gen1_ghost_deals_zero_to_psychic_due_to_bug() -> None:
    """In Gen 1 spettro contro psico è 0 per il famoso bug del gioco."""
    engine = EffectivenessEngine(1)
    assert engine.offensive_multiplier("ghost", ["psychic"]) == 0.0


def test_gen1_bug_super_effective_against_poison() -> None:
    """In Gen 1 coleottero contro veleno è superefficace (2x)."""
    engine = EffectivenessEngine(1)
    assert engine.offensive_multiplier("bug", ["poison"]) == 2.0


def test_gen1_poison_super_effective_against_bug() -> None:
    """In Gen 1 veleno contro coleottero è superefficace (2x)."""
    engine = EffectivenessEngine(1)
    assert engine.offensive_multiplier("poison", ["bug"]) == 2.0


def test_gen1_ice_neutral_against_fire() -> None:
    """In Gen 1 ghiaccio contro fuoco è neutro; da Gen 2 diventa 0.5x."""
    engine = EffectivenessEngine(1)
    assert engine.offensive_multiplier("ice", ["fire"]) == 1.0


# ---------------------------------------------------------------------------
# Differenze Gen 2-5 rispetto a Gen 1
# ---------------------------------------------------------------------------


def test_gen2_ghost_super_effective_against_psychic() -> None:
    """Da Gen 2 il bug è risolto: spettro contro psico è 2x."""
    engine = EffectivenessEngine(2)
    assert engine.offensive_multiplier("ghost", ["psychic"]) == 2.0


def test_gen2_bug_not_very_effective_against_poison() -> None:
    """Da Gen 2 coleottero contro veleno è 0.5x."""
    engine = EffectivenessEngine(2)
    assert engine.offensive_multiplier("bug", ["poison"]) == 0.5


def test_gen2_poison_neutral_against_bug() -> None:
    """Da Gen 2 veleno contro coleottero è neutro (1x)."""
    engine = EffectivenessEngine(2)
    assert engine.offensive_multiplier("poison", ["bug"]) == 1.0


def test_gen2_ice_not_very_effective_against_fire() -> None:
    """Da Gen 2 ghiaccio contro fuoco è 0.5x."""
    engine = EffectivenessEngine(2)
    assert engine.offensive_multiplier("ice", ["fire"]) == 0.5


# ---------------------------------------------------------------------------
# Nuovi tipi Gen 2 (dark, steel)
# ---------------------------------------------------------------------------


def test_gen1_rejects_dark_type_in_defender() -> None:
    """dark non esiste in Gen 1: usarlo alza ValueError."""
    engine = EffectivenessEngine(1)
    with pytest.raises(ValueError, match="invalid type 'dark'"):
        engine.offensive_multiplier("psychic", ["dark"])


def test_gen1_rejects_steel_type_as_attacker() -> None:
    """steel non esiste in Gen 1: usarlo alza ValueError."""
    engine = EffectivenessEngine(1)
    with pytest.raises(ValueError, match="invalid type 'steel'"):
        engine.offensive_multiplier("steel", ["water"])


def test_gen2_steel_immune_to_poison() -> None:
    """Acciaio è immune a veleno in Gen 2-5 (0x)."""
    engine = EffectivenessEngine(2)
    assert engine.offensive_multiplier("poison", ["steel"]) == 0.0


def test_gen2_dark_immune_to_psychic() -> None:
    """Buio è immune a psico in tutte le generazioni da Gen 2."""
    engine = EffectivenessEngine(2)
    assert engine.offensive_multiplier("psychic", ["dark"]) == 0.0


# ---------------------------------------------------------------------------
# Difensori bi-tipo
# ---------------------------------------------------------------------------


def test_dual_type_double_super_effective_multiplies_to_4x() -> None:
    """fuoco contro erba/acciaio in Gen 2+: 2x * 2x = 4x."""
    engine = EffectivenessEngine(3)
    assert engine.offensive_multiplier("fire", ["grass", "steel"]) == 4.0


def test_dual_type_super_and_not_very_effective_multiplies_to_1x() -> None:
    """acqua contro erba/terra in Gen 2+: 0.5x * 2x = 1x."""
    engine = EffectivenessEngine(3)
    assert engine.offensive_multiplier("water", ["grass", "ground"]) == 1.0


def test_dual_type_double_not_very_effective_multiplies_to_025x() -> None:
    """erba contro coleottero/acciaio in Gen 2+: 0.5x * 0.5x = 0.25x."""
    engine = EffectivenessEngine(3)
    assert engine.offensive_multiplier("grass", ["bug", "steel"]) == 0.25


def test_dual_type_immunity_dominates() -> None:
    """elettro contro terra/volante: 0x * 2x = 0x (immunità vince)."""
    engine = EffectivenessEngine(3)
    assert engine.offensive_multiplier("electric", ["ground", "flying"]) == 0.0


# ---------------------------------------------------------------------------
# Profilo difensivo
# ---------------------------------------------------------------------------


def test_defensive_profile_returns_entry_for_every_type_in_generation() -> None:
    """Il profilo difensivo ha una voce per ogni tipo attaccante valido."""
    engine = EffectivenessEngine(5)
    profile = engine.defensive_profile(["water", "flying"])
    assert set(profile.keys()) == set(engine.valid_types)


def test_defensive_profile_gyarados_gen5_matches_known_multipliers() -> None:
    """Gyarados (water/flying) in Gen 5: elettro 4x è la sua debolezza iconica.

    Ice vs water/flying: 0.5 * 2 = 1x (non 2x, water resiste).
    Rock vs water/flying: 1 * 2 = 2x.
    Ground vs water/flying: immunità (flying = 0x).
    """
    engine = EffectivenessEngine(5)
    profile = engine.defensive_profile(["water", "flying"])
    assert profile["electric"] == 4.0
    assert profile["ice"] == 1.0
    assert profile["rock"] == 2.0
    assert profile["fire"] == 0.5
    assert profile["ground"] == 0.0
    assert profile["fighting"] == 0.5


def test_defensive_profile_preserves_canonical_type_order() -> None:
    """Le chiavi del profilo devono seguire l'ordine canonico dei tipi."""
    engine = EffectivenessEngine(5)
    profile = engine.defensive_profile(["normal"])
    assert tuple(profile.keys()) == engine.valid_types


# ---------------------------------------------------------------------------
# Validazione input
# ---------------------------------------------------------------------------


def test_defender_with_zero_types_is_rejected() -> None:
    """Un difensore senza tipi non è ammesso."""
    engine = EffectivenessEngine(3)
    with pytest.raises(ValueError, match="1 or 2 types"):
        engine.offensive_multiplier("fire", [])


def test_defender_with_three_types_is_rejected() -> None:
    """Un difensore con 3 tipi non è ammesso."""
    engine = EffectivenessEngine(3)
    with pytest.raises(ValueError, match="1 or 2 types"):
        engine.offensive_multiplier("fire", ["water", "grass", "steel"])


def test_invalid_move_type_is_rejected() -> None:
    """Un tipo di mossa inesistente alza ValueError."""
    engine = EffectivenessEngine(3)
    with pytest.raises(ValueError, match="invalid type 'fairy'"):
        engine.offensive_multiplier("fairy", ["water"])


# ---------------------------------------------------------------------------
# Helper del modulo type_chart
# ---------------------------------------------------------------------------


def test_types_for_generation_matches_engine() -> None:
    """`types_for_generation` deve restituire lo stesso set del motore."""
    assert types_for_generation(1) == TYPES_GEN1
    assert types_for_generation(5) == TYPES_GEN2_5


def test_types_for_generation_rejects_unsupported_gen() -> None:
    """`types_for_generation` alza per generazioni fuori intervallo."""
    with pytest.raises(ValueError, match="unsupported generation"):
        types_for_generation(6)


def test_chart_for_generation_rejects_unsupported_gen() -> None:
    """`chart_for_generation` alza per generazioni fuori intervallo."""
    with pytest.raises(ValueError, match="unsupported generation"):
        chart_for_generation(0)


def test_gen1_chart_contains_no_modern_types() -> None:
    """La tabella Gen 1 non deve avere né dark né steel, in nessuna posizione."""
    chart = chart_for_generation(1)
    assert "dark" not in chart
    assert "steel" not in chart
    for defenses in chart.values():
        assert "dark" not in defenses
        assert "steel" not in defenses


# ---------------------------------------------------------------------------
# Regressione: la tabella Gen 2-5 identica per tutte le generazioni 2..5
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("gen", [2, 3, 4, 5])
def test_gen2_to_gen5_share_same_chart_object(gen: int) -> None:
    """Da Gen 2 a Gen 5 il chart usato deve essere lo stesso oggetto."""
    engine = EffectivenessEngine(gen)
    reference = EffectivenessEngine(2)
    assert engine.valid_types == reference.valid_types
    for attacker in engine.valid_types:
        for defender in engine.valid_types:
            assert engine.offensive_multiplier(
                attacker, [defender]
            ) == reference.offensive_multiplier(attacker, [defender])
