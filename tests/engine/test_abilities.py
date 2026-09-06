"""Test di `engine.abilities`.

I profili difensivi qui sono costruiti a mano, non presi da
`EffectivenessEngine`: così i test dicono cosa fa l'abilità e non ripetono
la tabella dei tipi, già coperta altrove.
"""

from __future__ import annotations

import pytest

from pokemon_helper.engine.abilities import (
    ABILITY_EFFECTS,
    apply_ability,
    modifies_effectiveness,
)

# Profilo di comodo: un difensore con una debolezza, una resistenza e neutri.
BASE = {"ground": 2.0, "fire": 2.0, "ice": 2.0, "water": 1.0, "grass": 0.5, "electric": 2.0}


def test_levitate_grants_ground_immunity() -> None:
    """Il caso simbolo: contro un Gengar con Levitazione, Terra non serve."""
    assert apply_ability(BASE, "levitate", 3)["ground"] == 0.0


def test_levitate_leaves_other_types_untouched() -> None:
    result = apply_ability(BASE, "levitate", 3)
    assert result["fire"] == 2.0
    assert result["grass"] == 0.5


def test_the_input_profile_is_not_mutated() -> None:
    apply_ability(BASE, "levitate", 3)
    assert BASE["ground"] == 2.0


@pytest.mark.parametrize(
    ("identifier", "immune_type"),
    [
        ("volt-absorb", "electric"),
        ("water-absorb", "water"),
        ("flash-fire", "fire"),
    ],
)
def test_absorbing_abilities_zero_their_type(identifier: str, immune_type: str) -> None:
    assert apply_ability(BASE, identifier, 3)[immune_type] == 0.0


def test_thick_fat_halves_fire_and_ice() -> None:
    result = apply_ability(BASE, "thick-fat", 3)
    assert result["fire"] == 1.0
    assert result["ice"] == 1.0
    assert result["ground"] == 2.0


def test_dry_skin_trades_water_immunity_for_extra_fire_damage() -> None:
    result = apply_ability(BASE, "dry-skin", 4)
    assert result["water"] == 0.0
    assert result["fire"] == 2.5


def test_filter_damps_only_super_effective_types() -> None:
    result = apply_ability(BASE, "filter", 4)
    assert result["ground"] == 1.5  # 2.0 * 0.75
    assert result["water"] == 1.0  # neutro, invariato
    assert result["grass"] == 0.5  # resistenza, invariata


def test_wonder_guard_zeroes_everything_but_super_effective() -> None:
    result = apply_ability(BASE, "wonder-guard", 3)
    assert result["ground"] == 2.0
    assert result["water"] == 0.0
    assert result["grass"] == 0.0


# --- effetti che dipendono dalla generazione ---


def test_lightning_rod_does_not_grant_immunity_before_gen5() -> None:
    """Fino alla Gen 4 attirava l'attacco senza renderne immuni."""
    assert apply_ability(BASE, "lightning-rod", 4)["electric"] == 2.0


def test_lightning_rod_grants_immunity_from_gen5() -> None:
    assert apply_ability(BASE, "lightning-rod", 5)["electric"] == 0.0


def test_storm_drain_follows_the_same_rule() -> None:
    assert apply_ability(BASE, "storm-drain", 4)["water"] == 1.0
    assert apply_ability(BASE, "storm-drain", 5)["water"] == 0.0


def test_an_ability_before_its_generation_changes_nothing() -> None:
    assert apply_ability(BASE, "sap-sipper", 4) == BASE


# --- casi limite ---


def test_an_unknown_ability_changes_nothing() -> None:
    assert apply_ability(BASE, "overgrow", 5) == BASE


def test_an_empty_profile_stays_empty() -> None:
    assert apply_ability({}, "levitate", 5) == {}


def test_immunity_wins_over_a_multiplier_on_the_same_type() -> None:
    """Pellearsa: l'Acqua va a zero, non viene scalata."""
    assert apply_ability({"water": 4.0}, "dry-skin", 5)["water"] == 0.0


def test_a_type_already_immune_stays_immune() -> None:
    assert apply_ability({"ground": 0.0}, "levitate", 5)["ground"] == 0.0


@pytest.mark.parametrize(
    ("identifier", "generation", "expected"),
    [
        ("levitate", 3, True),
        # Il default `since_generation=3` codifica che prima le abilità non
        # esistevano: nessun effetto in Gen 1 e 2, senza casi speciali.
        ("levitate", 2, False),
        ("lightning-rod", 4, False),
        ("lightning-rod", 5, True),
        ("overgrow", 5, False),
    ],
)
def test_modifies_effectiveness(identifier: str, generation: int, expected: bool) -> None:
    assert modifies_effectiveness(identifier, generation) is expected


def test_every_declared_effect_actually_does_something() -> None:
    """Una entry senza effetti sarebbe rumore nella tabella."""
    for identifier, effect in ABILITY_EFFECTS.items():
        has_effect = bool(
            effect.immune_to
            or effect.multipliers
            or effect.damps_super_effective
            or effect.only_super_effective
        )
        assert has_effect, f"{identifier} non modifica nulla"
