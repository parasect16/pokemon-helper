"""Abilità che alterano l'efficacia dei tipi.

Il profilo difensivo calcolato da `EffectivenessEngine` guarda solo i tipi, e
per un pugno di abilità questo produce una risposta *sbagliata*, non soltanto
incompleta: contro un Gengar con Levitazione il consiglio "usa Terra" manda
il giocatore a sbattere contro un'immunità. Questo modulo applica quel
secondo strato.

Le abilità coperte sono solo quelle che cambiano un moltiplicatore di tipo.
Restano fuori quelle che agiscono su danno, precisione o stato, che non hanno
posto in una tabella di efficacia.

Tre forme di effetto, che si compongono in quest'ordine:

1. **immunità** — il tipo va a 0 (Levitazione, i quattro "assorbi", ...);
2. **moltiplicatori fissi** — un tipo viene scalato (Grassospesso dimezza
   Fuoco e Ghiaccio, Pellearsa aggrava il Fuoco);
3. **modificatori sulle superefficaci** — Filtro e Solidroccia smorzano
   *qualunque* moltiplicatore sopra 1; Meraviglia azzera tutto ciò che non è
   superefficace.

Alcune abilità hanno acquisito l'immunità solo in una generazione successiva
alla propria introduzione: Parafulmine e Acquascolo, fino alla Gen 4,
redirezionavano l'attacco senza renderne immuni. `since_generation` codifica
esattamente questo, e non va confuso con la generazione in cui l'abilità è
comparsa — quel filtro vive nel repository.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Fattore applicato da Filtro e Solidroccia ai colpi superefficaci.
_SUPER_EFFECTIVE_DAMPING = 0.75


@dataclass(frozen=True, slots=True)
class AbilityEffect:
    """Come una singola abilità altera un profilo difensivo.

    Attributi:
        immune_to: tipi il cui moltiplicatore diventa 0.
        multipliers: fattori da applicare a tipi specifici.
        damps_super_effective: smorza ogni moltiplicatore sopra 1 (Filtro,
            Solidroccia).
        only_super_effective: azzera tutto ciò che non è superefficace
            (Meraviglia, cioè Shedinja).
        since_generation: generazione a partire dalla quale l'effetto vale.
            Prima di quella l'abilità esiste ma non tocca l'efficacia.
    """

    immune_to: tuple[str, ...] = ()
    multipliers: dict[str, float] = field(default_factory=dict)
    damps_super_effective: bool = False
    only_super_effective: bool = False
    since_generation: int = 3


# Chiave = `identifier` dell'abilità nel dataset, così il collegamento con
# `Ability.identifier` è diretto e non passa da traduzioni.
ABILITY_EFFECTS: dict[str, AbilityEffect] = {
    "levitate": AbilityEffect(immune_to=("ground",)),
    "volt-absorb": AbilityEffect(immune_to=("electric",)),
    "water-absorb": AbilityEffect(immune_to=("water",)),
    "flash-fire": AbilityEffect(immune_to=("fire",)),
    "motor-drive": AbilityEffect(immune_to=("electric",), since_generation=4),
    "sap-sipper": AbilityEffect(immune_to=("grass",), since_generation=5),
    # Pellearsa: immune all'Acqua, ma il Fuoco fa più male.
    "dry-skin": AbilityEffect(immune_to=("water",), multipliers={"fire": 1.25}, since_generation=4),
    # Parafulmine e Acquascolo: fino alla Gen 4 attiravano l'attacco senza
    # dare immunità. L'immunità arriva in Gen 5.
    "lightning-rod": AbilityEffect(immune_to=("electric",), since_generation=5),
    "storm-drain": AbilityEffect(immune_to=("water",), since_generation=5),
    "thick-fat": AbilityEffect(multipliers={"fire": 0.5, "ice": 0.5}),
    "heatproof": AbilityEffect(multipliers={"fire": 0.5}, since_generation=4),
    "filter": AbilityEffect(damps_super_effective=True, since_generation=4),
    "solid-rock": AbilityEffect(damps_super_effective=True, since_generation=4),
    "wonder-guard": AbilityEffect(only_super_effective=True),
}


def modifies_effectiveness(identifier: str, generation: int) -> bool:
    """Vero se l'abilità cambia il profilo difensivo in quella generazione."""
    effect = ABILITY_EFFECTS.get(identifier)
    return effect is not None and generation >= effect.since_generation


def apply_ability(profile: dict[str, float], identifier: str, generation: int) -> dict[str, float]:
    """Applica l'abilità al profilo difensivo, ritornando un nuovo dizionario.

    Un'abilità sconosciuta o non ancora efficace in quella generazione lascia
    il profilo invariato: il chiamante può invocare questa funzione senza
    controllare prima, e ottenere comunque un risultato corretto.
    """
    effect = ABILITY_EFFECTS.get(identifier)
    if effect is None or generation < effect.since_generation:
        return dict(profile)

    result = dict(profile)
    for attack_type, multiplier in result.items():
        if effect.only_super_effective and multiplier <= 1.0:
            result[attack_type] = 0.0
            continue
        if attack_type in effect.immune_to:
            result[attack_type] = 0.0
            continue
        multiplier *= effect.multipliers.get(attack_type, 1.0)
        if effect.damps_super_effective and multiplier > 1.0:
            multiplier *= _SUPER_EFFECTIVE_DAMPING
        result[attack_type] = multiplier
    return result
