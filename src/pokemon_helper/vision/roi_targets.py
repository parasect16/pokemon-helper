"""L'elenco dei rettangoli che un gioco deve avere, e come indirizzarne uno.

`GameRois` è una struttura annidata e immutabile: comoda da leggere, scomoda
da modificare un pezzo alla volta — che è esattamente ciò che fa un
calibratore, dove l'utente ridisegna un rettangolo su sedici e gli altri
quindici devono restare dov'erano.

Qui ogni rettangolo ha una **chiave** testuale (`opponent_name`,
`team_menu.slot_levels.3`) con cui leggerlo e sostituirlo, più l'etichetta in
italiano e la schermata su cui va calibrato. La schermata serve al
calibratore per dire "questo lo disegni sull'elenco Pokemon, non qui": le ROI
di combattimento si misurano su un frame di combattimento, quelle del menu su
un frame di menu, e sbagliare schermata è il modo più veloce di produrre una
calibrazione che sembra giusta e legge il vuoto.

Il modulo è puro — solo `roi.py`, niente numpy, niente Qt — così resta
importabile ovunque e testabile senza display.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from pokemon_helper.vision.roi import TEAM_SIZE, GameRois, Roi, TeamMenuRois

# Schermata su cui un rettangolo va calibrato. I valori coincidono con quelli
# di `vision.screen_mode.ScreenMode`, ma sono ripetuti come stringhe per non
# trascinare numpy e PIL dentro un modulo che descrive solo dei nomi.
SCREEN_BATTLE = "battle"
SCREEN_PARTY_MENU = "party_menu"

# Etichette dei gruppi di slot del menu squadra: prefisso in italiano, uno
# per campo di `TeamMenuRois`.
_SLOT_GROUP_LABELS = {
    "slot_areas": "Nome slot",
    "slot_levels": "Livello slot",
}


@dataclass(frozen=True, slots=True)
class RoiTarget:
    """Un rettangolo calibrabile: come si chiama, come si mostra, dove si misura."""

    key: str
    label: str
    screen: str
    # Frase mostrata nel calibratore mentre il bersaglio è selezionato: dice
    # *cosa* inquadrare, che è l'unica cosa che l'utente non può dedurre dal
    # nome del campo.
    hint: str


TARGETS: tuple[RoiTarget, ...] = (
    RoiTarget(
        key="opponent_name",
        label="Nome avversario",
        screen=SCREEN_BATTLE,
        hint=(
            "La riga con nome e livello dell'avversario, in alto a sinistra. "
            "Solo il testo: la barra PS sta sotto."
        ),
    ),
    RoiTarget(
        key="opponent_hp_bar",
        label="Barra PS avversario",
        screen=SCREEN_BATTLE,
        hint=(
            "La barra colorata dell'avversario. Non se ne legge il valore: serve a "
            "capire che siamo in combattimento, quindi deve contenere il colore "
            "della barra e nient'altro."
        ),
    ),
    RoiTarget(
        key="player_name",
        label="Nome giocatore",
        screen=SCREEN_BATTLE,
        hint=(
            "La riga con nome e livello del tuo Pokemon, in basso a destra. "
            "È il nickname, se ne ha uno."
        ),
    ),
    RoiTarget(
        key="party_menu_sentinel",
        label="Pulsante ESCI",
        screen=SCREEN_PARTY_MENU,
        hint=(
            "Il pulsante in basso a destra dell'elenco Pokemon. È il segnale con cui "
            "l'app riconosce questa schermata."
        ),
    ),
    *(
        RoiTarget(
            key=f"team_menu.{field}.{index}",
            label=f"{_SLOT_GROUP_LABELS[field]} {index + 1}",
            screen=SCREEN_PARTY_MENU,
            hint=(
                f"Il nome del Pokemon nello slot {index + 1}"
                if field == "slot_areas"
                else f"Il solo `L.XX` dello slot {index + 1}, senza il nome"
            )
            + (" (lo slot attivo, il riquadro grande)." if index == 0 else "."),
        )
        for field in _SLOT_GROUP_LABELS
        for index in range(TEAM_SIZE)
    ),
)

TARGETS_BY_KEY: dict[str, RoiTarget] = {target.key: target for target in TARGETS}


def targets_for_screen(screen: str) -> tuple[RoiTarget, ...]:
    """I bersagli che si calibrano su una certa schermata."""
    return tuple(target for target in TARGETS if target.screen == screen)


def get_roi(rois: GameRois, key: str) -> Roi:
    """Legge il rettangolo indirizzato da `key`."""
    field, index = _parse_key(key)
    if index is None:
        return getattr(rois, field)
    return getattr(rois.team_menu, field)[index]


def replace_roi(rois: GameRois, key: str, roi: Roi) -> GameRois:
    """Ritorna una copia di `rois` con il solo rettangolo `key` sostituito."""
    field, index = _parse_key(key)
    if index is None:
        return replace(rois, **{field: roi})
    slots = list(getattr(rois.team_menu, field))
    slots[index] = roi
    team_menu = replace(rois.team_menu, **{field: tuple(slots)})
    return replace(rois, team_menu=team_menu)


def _parse_key(key: str) -> tuple[str, int | None]:
    """Scompone una chiave in `(campo, indice)`, con indice `None` se singola.

    Alza `KeyError` su una chiave che non è fra i bersagli: meglio fallire
    subito che scrivere un rettangolo in un campo inventato.
    """
    if key not in TARGETS_BY_KEY:
        raise KeyError(key)
    if not key.startswith("team_menu."):
        return key, None
    _, field, index = key.split(".")
    return field, int(index)


def _validate_team_menu_fields() -> None:
    """Le etichette dei gruppi devono coprire esattamente `TeamMenuRois`.

    Aggiungere un gruppo di slot senza etichetta lo renderebbe invisibile nel
    calibratore, e sarebbe un rettangolo che nessuno calibra più.
    """
    declared = set(_SLOT_GROUP_LABELS)
    actual = set(TeamMenuRois.__dataclass_fields__)
    if declared != actual:
        raise RuntimeError(f"team menu fields {actual} but labels cover {declared}")


_validate_team_menu_fields()
