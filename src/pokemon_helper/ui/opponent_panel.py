"""Sezione avversario del pannello overlay.

Layout in due colonne quando entrambi i Pokemon sono noti:

    ┌─────────────────┬─────────────────┐
    │ [icona player]  │ [icona opp]     │
    │ Nome            │ Nome            │
    │ [type badges]   │ [type badges]   │
    │ Debolezze:      │ Debolezze:      │
    │  ...            │  ...            │
    │ Resistenze:     │ Resistenze:     │
    │  ...            │  ...            │
    │ Immunità:       │ Immunità:       │
    │  ...            │  ...            │
    └─────────────────┴─────────────────┘

Ogni colonna copre un Pokemon con: icona sprite front dal Pokedex, nome,
tipi e la lista di efficacia difensiva (per ciascun tipo di attaccante, il
moltiplicatore ricevuto — vengono esclusi i valori neutri 1×).

Placeholder alternativi:

- Nessun avversario: "Combattimento non in corso".
- Avversario impostato ma player attivo sconosciuto: suggerimento a fare
  un recognize battaglia via `Ctrl+Alt+R` / pulsante "⚔ Avversario".
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from pokemon_helper.data import PokemonRepository
from pokemon_helper.engine import EffectivenessEngine
from pokemon_helper.engine.abilities import apply_ability, modifies_effectiveness
from pokemon_helper.ui.state import AppState
from pokemon_helper.ui.types_meta import render_type_badge, render_type_badges

SPRITES_ROOT = Path(__file__).resolve().parents[3] / "data" / "vendor" / "sprites"


def format_multiplier(value: float) -> str:
    """Formatta un moltiplicatore in forma compatta per la tabella."""
    if value == 0:
        return "0×"
    if value == 0.25:
        return "¼×"
    if value == 0.5:
        return "½×"
    if value == 1:
        return "1×"
    if value == 2:
        return "2×"
    if value == 4:
        return "4×"
    return f"{value:g}×"


class OpponentPanel(QWidget):
    """Sezione con placeholder + eventualmente due card (player + avversario)."""

    # (pokemon_id, identifier | None): l'utente ha fissato o sbloccato l'abilità.
    abilityPinned = Signal(int, object)

    def __init__(self, repository: PokemonRepository, state: AppState) -> None:
        super().__init__()
        self._repo = repository
        self._state = state
        self._opponent_id: int | None = None
        self._active_player_id: int | None = None
        self._content: QWidget | None = None

        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(0, 6, 0, 0)
        self._outer.setSpacing(0)

        self._refresh()

    # -------------------------------------------------------- public API

    def set_opponent(self, pokemon_id: int | None) -> None:
        if self._opponent_id == pokemon_id:
            return
        self._opponent_id = pokemon_id
        self._refresh()

    def set_active_player(self, pokemon_id: int | None) -> None:
        if self._active_player_id == pokemon_id:
            return
        self._active_player_id = pokemon_id
        self._refresh()

    def apply_state(self, state: AppState) -> None:
        self._state = state
        self._refresh()

    # ----------------------------------------------------------- rendering

    def _refresh(self) -> None:
        if self._content is not None:
            self._outer.removeWidget(self._content)
            self._content.deleteLater()
            self._content = None

        if self._opponent_id is None:
            self._content = self._build_placeholder("Combattimento non in corso")
        elif self._active_player_id is None:
            self._content = self._build_placeholder(
                "Player in campo sconosciuto — usa Ctrl+Alt+R o ⚔ Avversario"
            )
        else:
            self._content = self._build_battle() or self._build_placeholder(
                "Dati incompleti per il match"
            )
        self._outer.addWidget(self._content)

    def _build_placeholder(self, message: str) -> QWidget:
        widget = QWidget(self)
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        layout.addWidget(_separator(widget))

        label = QLabel(message, widget)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        label.setStyleSheet("color: #7a7a8a; font-style: italic; padding: 6px;")
        layout.addWidget(label)
        return widget

    def _build_battle(self) -> QWidget | None:
        """Costruisce le due card (player + avversario) affiancate."""
        assert self._opponent_id is not None
        assert self._active_player_id is not None
        player = self._repo.get_by_id(self._active_player_id)
        opponent = self._repo.get_by_id(self._opponent_id)
        if player is None or opponent is None:
            return None
        gen = self._state.generation
        player_types = self._repo.get_types(player.id, gen)
        opp_types = self._repo.get_types(opponent.id, gen)
        if not player_types or not opp_types:
            return None

        widget = QWidget(self)
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        layout.addWidget(_separator(widget))

        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(self._build_pokemon_card(widget, player, player_types, gen))
        row.addWidget(self._build_pokemon_card(widget, opponent, opp_types, gen))
        layout.addLayout(row)
        return widget

    def _build_pokemon_card(
        self, parent: QWidget, pokemon, types: tuple[str, ...], generation: int
    ) -> QWidget:
        card = QFrame(parent)
        card.setFrameShape(QFrame.Shape.StyledPanel)
        card.setStyleSheet("QFrame { background-color: rgba(255,255,255,15); border-radius: 6px; }")
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        icon_label = QLabel(card)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setFixedHeight(96)
        pixmap = self._load_sprite_pixmap(pokemon.id, generation)
        if pixmap is not None:
            icon_label.setPixmap(pixmap)
        else:
            icon_label.setText("(sprite mancante)")
            icon_label.setStyleSheet("color: #7a7a8a; font-style: italic;")
        layout.addWidget(icon_label)

        name_label = QLabel(pokemon.name_it or pokemon.name_en, card)
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_font = name_label.font()
        name_font.setBold(True)
        name_label.setFont(name_font)
        layout.addWidget(name_label)

        types_label = QLabel(render_type_badges(types), card)
        types_label.setTextFormat(Qt.TextFormat.RichText)
        types_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(types_label)

        applied, candidates = resolve_ability(
            self._repo.get_abilities(pokemon.id, generation),
            self._state.abilities.get(pokemon.id),
        )
        if candidates:
            layout.addWidget(self._build_ability_row(card, pokemon.id, applied, candidates))

        eff_label = QLabel(_render_effectiveness_html(types, generation, applied), card)
        eff_label.setTextFormat(Qt.TextFormat.RichText)
        eff_label.setWordWrap(True)
        # Font size intrinseco al widget: l'HTML può alzarlo ulteriormente
        # dentro le tabelle. 12 px come baseline garantisce leggibilità.
        eff_label.setStyleSheet("font-size: 12px;")
        layout.addWidget(eff_label)
        layout.addStretch(1)
        return card

    def _build_ability_row(
        self, parent: QWidget, pokemon_id: int, applied: str | None, candidates: list
    ) -> QWidget:
        """Riga abilità: etichetta se è certa, menu a tendina se è ambigua."""
        generation = self._state.generation
        if len(candidates) == 1:
            ability = candidates[0]
            label = QLabel(f"Abilità: {ability.display_name}", parent)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet("color: #d6d6e2; font-size: 12px;")
            if ability.description:
                label.setToolTip(ability.description)
            return label

        box = QComboBox(parent)
        box.addItem("Abilità: ?", None)
        for ability in candidates:
            box.addItem(ability.display_name, ability.identifier)
            # Tooltip per voce: leggendo il menu si capisce cosa fa ciascuna
            # senza doverla prima scegliere.
            if ability.description:
                box.setItemData(box.count() - 1, ability.description, Qt.ItemDataRole.ToolTipRole)
        box.setCurrentIndex(
            next(
                (i for i in range(box.count()) if box.itemData(i) == applied),
                0,
            )
        )
        box.setStyleSheet("font-size: 12px;")
        # Segnala che il profilo mostrato può essere sbagliato: senza questo
        # l'utente non ha modo di sapere che una delle abilità possibili
        # cambierebbe il verdetto.
        unknown = uncertain_abilities(applied, candidates, generation)
        if unknown:
            names = ", ".join(a.display_name for a in unknown)
            box.setStyleSheet("font-size: 12px; border: 1px solid #e0c060;")
            box.setItemData(
                0,
                f"Non applicata: cambierebbero l'efficacia {names}",
                Qt.ItemDataRole.ToolTipRole,
            )
        _sync_combo_tooltip(box)
        box.currentIndexChanged.connect(lambda _index, widget=box: _sync_combo_tooltip(widget))
        box.currentIndexChanged.connect(
            lambda index, pid=pokemon_id, widget=box: self.abilityPinned.emit(
                pid, widget.itemData(index)
            )
        )
        return box

    def _load_sprite_pixmap(self, pokemon_id: int, generation: int) -> QPixmap | None:
        """Carica lo sprite front come `QPixmap`, se disponibile su disco."""
        # Prima prova con il gioco tipico della gen (FRLG per Gen 3), altrimenti
        # ripiega sul primo path indicizzato.
        preferred_game = _preferred_game(generation)
        source = self._repo.get_sprite_source_path(
            pokemon_id, generation, side="front", preferred_game=preferred_game
        )
        if source is None:
            return None
        path = SPRITES_ROOT / source
        if not path.exists():
            return None
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            return None
        # Scala mantenendo aspect, sprite Pokemon sono piccoli (~64-96 px).
        return pixmap.scaledToHeight(96, Qt.TransformationMode.SmoothTransformation)


# ---------------------------------------------------------------------------
# Helper di rendering
# ---------------------------------------------------------------------------


def _sync_combo_tooltip(box: QComboBox) -> None:
    """Porta il tooltip della voce selezionata sul widget chiuso.

    Qt mostra i tooltip per voce solo a menu aperto: senza questo, passare il
    mouse sul menu chiuso non direbbe nulla, che è proprio il caso d'uso.
    """
    box.setToolTip(box.itemData(box.currentIndex(), Qt.ItemDataRole.ToolTipRole) or "")


def resolve_ability(candidates: list, pinned: str | None) -> tuple[str | None, list]:
    """Decide quale abilità applicare, e cosa resta incerto.

    Ritorna `(identifier applicato, candidati ancora possibili)`:

    - un solo candidato → è certa, si applica senza chiedere nulla;
    - scelta fissata dall'utente e ancora fra i candidati → si applica quella;
    - più candidati e nessuna scelta → non si applica niente, e la lista
      restituita serve a segnalare l'incertezza.

    Una scelta fissata che non compare fra i candidati viene ignorata: succede
    cambiando generazione, dove l'abilità può non essere disponibile.
    """
    if not candidates:
        return None, []
    identifiers = [ability.identifier for ability in candidates]
    if pinned is not None and pinned in identifiers:
        return pinned, candidates
    if len(candidates) == 1:
        return identifiers[0], candidates
    return None, candidates


def uncertain_abilities(applied: str | None, candidates: list, generation: int) -> list:
    """Candidati che cambierebbero l'efficacia ma non sono stati applicati.

    Se la lista non è vuota, il profilo mostrato può essere sbagliato e va
    segnalato: è la differenza fra "non lo so" e "so che non conta".
    """
    if applied is not None:
        return []
    return [a for a in candidates if modifies_effectiveness(a.identifier, generation)]


def _separator(parent: QWidget) -> QFrame:
    line = QFrame(parent)
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFixedHeight(1)
    line.setStyleSheet("background-color: #4a4a5f;")
    return line


def _render_effectiveness_html(
    defender_types: tuple[str, ...], generation: int, ability: str | None = None
) -> str:
    """Efficacia difensiva a colonna: una riga per tipo (badge + moltiplicatore).

    Struttura: sezioni "Debolezze" / "Resistenze" / "Immune" ognuna con una
    `<table>` HTML che allinea il badge del tipo a sinistra e il
    moltiplicatore a destra. Il testo del badge è nero o bianco in base alla
    luminanza del colore di sfondo (Elettro/Terra/Roccia diventano leggibili).
    I tipi con 1× vengono esclusi.
    """
    engine = EffectivenessEngine(generation)
    profile = engine.defensive_profile(list(defender_types))
    if ability is not None:
        profile = apply_ability(profile, ability, generation)

    weak = sorted(
        ((t, m) for t, m in profile.items() if m > 1),
        key=lambda pair: (-pair[1], pair[0]),
    )
    resist = sorted(
        ((t, m) for t, m in profile.items() if 0 < m < 1),
        key=lambda pair: (pair[1], pair[0]),
    )
    immune = sorted(((t, m) for t, m in profile.items() if m == 0), key=lambda p: p[0])

    def _render_group(label: str, entries: list[tuple[str, float]]) -> str | None:
        if not entries:
            return None
        rows: list[str] = []
        for type_name, mult in entries:
            badge = render_type_badge(type_name)
            mult_text = format_multiplier(mult)
            rows.append(
                "<tr>"
                f"<td style='padding:2px 6px 2px 0;'>{badge}</td>"
                "<td style='padding:2px 0; color:#EAEAEA; font-weight:bold; "
                f"font-size:12px;'>{mult_text}</td>"
                "</tr>"
            )
        table = (
            "<table style='border-collapse:collapse; margin-left:4px;'>"
            + "".join(rows)
            + "</table>"
        )
        return (
            "<div style='margin-top:6px; color:#EAEAEA; font-weight:bold; "
            f"font-size:12px;'>{label}</div>{table}"
        )

    sections: list[str] = []
    for label, entries in (
        ("Debolezze", weak),
        ("Resistenze", resist),
        ("Immune", immune),
    ):
        rendered = _render_group(label, entries)
        if rendered is not None:
            sections.append(rendered)

    if not sections:
        return "<i style='color:#aaa; font-size:11px;'>Nessuna interazione non-neutra</i>"
    return "".join(sections)


def _preferred_game(generation: int) -> str | None:
    """Gioco preferito per lo sprite front di una generazione (best-effort)."""
    return {
        1: "red-blue",
        2: "crystal",
        3: "firered-leafgreen",
        4: "heartgold-soulsilver",
        5: "black-white",
    }.get(generation)
