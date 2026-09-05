"""Region-of-interest e mapping fra coord native del gioco e pixel finestra.

Modello:

- Il gioco ha una risoluzione **nativa** (es. GBA = 240×160). Le ROI sono
  espresse in coordinate **normalizzate** fra 0 e 1 relative a questa
  risoluzione: `(x, y, w, h)` con `0 <= x <= 1` etc.
- La finestra dell'emulatore aggiunge:
  - un menu bar in alto (mGBA su Windows: ~30px prima di client),
  - eventuali letterbox laterali/verticali per mantenere l'aspect ratio
    quando la finestra è ridimensionata liberamente.
- `compute_game_area(window_w, window_h, aspect, menu_offset_top)` calcola
  il rettangolo pixel-preciso occupato dal gioco all'interno del frame.
- `roi_to_pixels(roi, game_area)` scala una ROI normalizzata alle
  coordinate assolute del frame catturato.

Le ROI per gioco vivono in `GAME_ROIS`.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Roi:
    """Rettangolo normalizzato `(x, y, w, h)` con valori in `[0, 1]`."""

    x: float
    y: float
    w: float
    h: float

    def __post_init__(self) -> None:
        for name, value in (("x", self.x), ("y", self.y), ("w", self.w), ("h", self.h)):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name}={value} out of [0, 1]")
        if self.x + self.w > 1.0 + 1e-9 or self.y + self.h > 1.0 + 1e-9:
            raise ValueError(f"roi {self} exceeds native bounds")


@dataclass(frozen=True, slots=True)
class PixelRect:
    """Rettangolo intero in pixel: `(x, y, w, h)`."""

    x: int
    y: int
    w: int
    h: int

    def as_crop_box(self) -> tuple[int, int, int, int]:
        """Ritorna `(left, upper, right, lower)` per `PIL.Image.crop`."""
        return (self.x, self.y, self.x + self.w, self.y + self.h)


@dataclass(frozen=True, slots=True)
class GameLayout:
    """Descrive come è disposto il gioco dentro una finestra emulatore."""

    # Rapporto larghezza/altezza dell'area gioco (GBA = 3/2, GB/GBC = 10/9).
    aspect_ratio: float
    # Altezza in pixel del menu bar dell'emulatore (0 se nascosto).
    menu_offset_top: int = 30


# Layout comuni per uso F3.
LAYOUT_MGBA_GBA = GameLayout(aspect_ratio=240 / 160, menu_offset_top=30)
LAYOUT_MGBA_GB = GameLayout(aspect_ratio=160 / 144, menu_offset_top=30)


# ROI standard per gioco. Coordinate misurate manualmente in coordinate
# **native del gioco** normalizzate (0-1). Vanno aggiustate se emergono
# discrepanze visive nel debug.
#
# Layout schermo battaglia Rosso Fuoco (GBA 240×160):
#   - Avversario in alto: barra nome+HP in alto-sx, sprite in alto-dx.
#   - Giocatore in basso: barra nome+HP in basso-dx, sprite in basso-sx.
TEAM_SIZE = 6


@dataclass(frozen=True, slots=True)
class TeamMenuRois:
    """ROI degli slot squadra nella schermata elenco Pokemon.

    - `slot_areas`: 6 rettangoli che coprono nome + livello di ciascun slot.
    - `slot_icons`: 6 rettangoli sulle mini icone del menu (fallback quando
      l'OCR nome non trova match — es. nickname personalizzati).
    - `slot_levels`: 6 rettangoli tight sul solo indicatore di livello
      ("L.XX"). Un'OCR dedicata su un crop piccolo migliora molto la
      detection del numero rispetto a leggere l'intera area slot.
    """

    slot_areas: tuple[Roi, ...]
    slot_icons: tuple[Roi, ...]
    slot_levels: tuple[Roi, ...]

    def __post_init__(self) -> None:
        for name, coll in (
            ("slot_areas", self.slot_areas),
            ("slot_icons", self.slot_icons),
            ("slot_levels", self.slot_levels),
        ):
            if len(coll) != TEAM_SIZE:
                raise ValueError(f"team menu must define {TEAM_SIZE} {name}, got {len(coll)}")


@dataclass(frozen=True, slots=True)
class GameRois:
    """Insieme di ROI per un gioco (avversario + giocatore + menu squadra)."""

    opponent_name: Roi
    opponent_sprite: Roi
    opponent_hp_bar: Roi
    player_name: Roi
    player_sprite: Roi
    player_hp_bar: Roi
    team_menu: TeamMenuRois


ROIS_FIRERED = GameRois(
    # --- Avversario (metà alta) ---
    # Nome + livello dell'avversario (solo la riga di testo, HP escluso).
    # Misurato empiricamente su cattura 1119×768 di mGBA (game_area 1107×738,
    # menu 30px). Range approx: y_pixel 145..185, x_pixel 40..470 nel game_area.
    opponent_name=Roi(x=0.030, y=0.155, w=0.395, h=0.055),
    # Sprite avversario: metà alta destra. pHash è tollerante alle inclusioni
    # di sfondo, quindi il crop non deve essere perfettamente stretto.
    opponent_sprite=Roi(x=0.470, y=0.088, w=0.410, h=0.348),
    # Barra HP avversario: barra colorata dopo la label "PS".
    opponent_hp_bar=Roi(x=0.146, y=0.222, w=0.250, h=0.028),
    # --- Giocatore (metà bassa) ---
    # HUD del giocatore in basso-destra: riga nome+livello (esclude la barra
    # HP che vive più in basso). Posizionamento fine dopo iterazioni con la
    # cattura live: y più alta e box alto per catturare bene il testo.
    player_name=Roi(x=0.545, y=0.478, w=0.400, h=0.082),
    # Sprite posteriore del giocatore in basso-sinistra: allargato verso
    # destra rispetto alla prima calibrazione per includere la parte destra
    # dello sprite che sporgeva oltre il ROI iniziale.
    player_sprite=Roi(x=0.090, y=0.470, w=0.360, h=0.310),
    # Barra HP giocatore: barra colorata "PS ▬▬▬" (prima dei numeri assoluti).
    player_hp_bar=Roi(x=0.635, y=0.605, w=0.260, h=0.028),
    # --- Menu Pokemon ---
    # Layout Rosso Fuoco: slot 1 grande a sinistra (Pokemon "attivo"), slot 2-6
    # righe compatte a destra. Ciascun ROI comprende sia il nome sia la riga
    # del livello: `_pick_name_text` filtra la riga "L.XX" già oggi.
    team_menu=TeamMenuRois(
        slot_areas=(
            # Slot 1 (Pokemon attivo, box grande sinistra).
            Roi(x=0.160, y=0.265, w=0.215, h=0.095),
            # Slot 2 (prima riga compatta a destra: Gloom nel test).
            Roi(x=0.473, y=0.122, w=0.199, h=0.095),
            # Slot 3.
            Roi(x=0.473, y=0.265, w=0.199, h=0.095),
            # Slot 4.
            Roi(x=0.473, y=0.414, w=0.199, h=0.095),
            # Slot 5.
            Roi(x=0.473, y=0.556, w=0.199, h=0.095),
            # Slot 6 (ultima riga compatta).
            Roi(x=0.473, y=0.706, w=0.199, h=0.095),
        ),
        slot_icons=(
            # Icona slot 1 nel box attivo (in alto a sinistra del box).
            Roi(x=0.040, y=0.271, w=0.077, h=0.115),
            # Icone slot 2-6: colonna fissa a sinistra del nome.
            Roi(x=0.406, y=0.109, w=0.068, h=0.088),
            Roi(x=0.406, y=0.252, w=0.068, h=0.088),
            Roi(x=0.406, y=0.394, w=0.068, h=0.088),
            Roi(x=0.406, y=0.537, w=0.068, h=0.088),
            Roi(x=0.406, y=0.680, w=0.068, h=0.088),
        ),
        slot_levels=(
            # Slot 1 (box attivo): "L.25" sotto il nome dentro il box.
            Roi(x=0.166, y=0.346, w=0.072, h=0.055),
            # Slot 2-6: "L.XX" sotto il nome, colonna fissa a destra dell'icona.
            Roi(x=0.510, y=0.204, w=0.090, h=0.055),
            Roi(x=0.510, y=0.353, w=0.090, h=0.055),
            Roi(x=0.510, y=0.502, w=0.090, h=0.055),
            Roi(x=0.510, y=0.651, w=0.090, h=0.055),
            Roi(x=0.510, y=0.801, w=0.090, h=0.055),
        ),
    ),
)


GAME_ROIS: dict[str, tuple[GameLayout, GameRois]] = {
    "firered": (LAYOUT_MGBA_GBA, ROIS_FIRERED),
}


# ---------------------------------------------------------------------------
# Calcolo area gioco dentro finestra emulatore
# ---------------------------------------------------------------------------


def compute_game_area(window_width: int, window_height: int, layout: GameLayout) -> PixelRect:
    """Calcola il rettangolo pixel del gioco dentro il frame catturato.

    Assume:
    - Il frame include il menu bar dell'emulatore (`menu_offset_top`) in cima
      e nessun altro cromo sotto o sui lati (il titolo Windows viene già
      escluso da Windows Graphics Capture in modalità client-area).
    - L'emulatore mantiene l'aspect ratio, applicando letterbox orizzontale
      o verticale in base a quale dimensione limita.
    """
    available_h = max(1, window_height - layout.menu_offset_top)
    available_w = max(1, window_width)

    # Prova a riempire in altezza, controlla se la larghezza necessaria sta.
    width_by_height = int(round(available_h * layout.aspect_ratio))
    if width_by_height <= available_w:
        game_w = width_by_height
        game_h = available_h
        offset_x = (available_w - game_w) // 2
        offset_y = 0
    else:
        game_w = available_w
        game_h = int(round(available_w / layout.aspect_ratio))
        offset_x = 0
        offset_y = (available_h - game_h) // 2

    return PixelRect(
        x=offset_x,
        y=layout.menu_offset_top + offset_y,
        w=game_w,
        h=game_h,
    )


def roi_to_pixels(roi: Roi, game_area: PixelRect) -> PixelRect:
    """Scala una ROI normalizzata a coordinate pixel del frame catturato."""
    px = int(round(game_area.x + roi.x * game_area.w))
    py = int(round(game_area.y + roi.y * game_area.h))
    pw = int(round(roi.w * game_area.w))
    ph = int(round(roi.h * game_area.h))
    return PixelRect(x=px, y=py, w=pw, h=ph)
