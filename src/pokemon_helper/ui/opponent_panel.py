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

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from pokemon_helper.data import PokemonRepository
from pokemon_helper.engine import EffectivenessEngine
from pokemon_helper.ui.state import AppState
from pokemon_helper.ui.types_meta import color_for, label_it, text_color_for

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

        types_label = QLabel(_render_type_badges(types), card)
        types_label.setTextFormat(Qt.TextFormat.RichText)
        types_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(types_label)

        eff_label = QLabel(_render_effectiveness_html(types, generation), card)
        eff_label.setTextFormat(Qt.TextFormat.RichText)
        eff_label.setWordWrap(True)
        # Font size intrinseco al widget: l'HTML può alzarlo ulteriormente
        # dentro le tabelle. 12 px come baseline garantisce leggibilità.
        eff_label.setStyleSheet("font-size: 12px;")
        layout.addWidget(eff_label)
        layout.addStretch(1)
        return card

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


def _separator(parent: QWidget) -> QFrame:
    line = QFrame(parent)
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFixedHeight(1)
    line.setStyleSheet("background-color: #4a4a5f;")
    return line


def _render_type_badge(type_name: str, *, font_size_px: int = 12) -> str:
    """Badge HTML per un tipo con testo scelto per contrasto sul bg colorato."""
    bg = color_for(type_name)
    fg = text_color_for(bg)
    return (
        f"<span style='background:{bg}; color:{fg}; padding:2px 8px; "
        f"border-radius:6px; font-size:{font_size_px}px; font-weight:bold;'>"
        f"{label_it(type_name)}</span>"
    )


def _render_type_badges(types: tuple[str, ...]) -> str:
    """Badge dei tipi per l'intestazione del Pokemon."""
    return "".join(f"<span style='margin-right:3px;'>{_render_type_badge(t)}</span>" for t in types)


def _render_effectiveness_html(defender_types: tuple[str, ...], generation: int) -> str:
    """Efficacia difensiva a colonna: una riga per tipo (badge + moltiplicatore).

    Struttura: sezioni "Debolezze" / "Resistenze" / "Immune" ognuna con una
    `<table>` HTML che allinea il badge del tipo a sinistra e il
    moltiplicatore a destra. Il testo del badge è nero o bianco in base alla
    luminanza del colore di sfondo (Elettro/Terra/Roccia diventano leggibili).
    I tipi con 1× vengono esclusi.
    """
    engine = EffectivenessEngine(generation)
    profile = engine.defensive_profile(list(defender_types))

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
            badge = _render_type_badge(type_name)
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
