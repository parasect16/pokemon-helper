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
    # Chrome totale in cima alla finestra: title bar Windows + menu bar mGBA.
    # `windows-capture` in modalità default cattura l'INTERA finestra (non
    # solo il client area) su Win10/11, quindi va sottratto il titolo (~30 px
    # a DPI 100%, 37 a 125%) più il menu bar mGBA (~25 px). Misurato 52 px
    # sulla macchina di sviluppo dell'utente (Win10 Pro 10.0.19045).
    # TODO: auto-detect chrome via scansione riga teal iniziale sul frame.
    menu_offset_top: int = 52


# Layout comuni per uso F3.
LAYOUT_MGBA_GBA = GameLayout(aspect_ratio=240 / 160, menu_offset_top=52)
LAYOUT_MGBA_GB = GameLayout(aspect_ratio=160 / 144, menu_offset_top=52)


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

    - `slot_areas`: 6 rettangoli tight sul solo nome di ciascun slot. Fino
      alla ricalibrazione F3.14 coprivano anche la riga del livello; ora no,
      e `slot_levels` è l'unica sorgente per il numero.
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


# Tutte le ROI di combattimento qui sotto sono state calibrate su cattura
# 1119×768 quando `menu_offset_top` valeva ancora 30 px invece dei 52 reali.
# La `game_area` usata come riferimento era quindi sbagliata (1107×738 a y=30
# invece di 1074×716 a y=52) e le coordinate normalizzate ne hanno assorbito
# l'errore: dopo il fix del chrome ogni box è finito ~20 px troppo in basso.
# Il caso peggiore era `opponent_name`, alto appena 38 px, che tagliava a metà
# il nome dell'avversario e leggeva la barra PS ("AECFAT\"S..").
#
# I valori attuali sono le vecchie coordinate riproiettate sulla `game_area`
# vera: pixel_frame ricostruiti col chrome sbagliato, poi rinormalizzati con
# quello giusto. Sono quindi indipendenti dalla dimensione della finestra —
# non lo erano prima, perché incorporavano un offset in pixel assoluti.
ROIS_FIRERED = GameRois(
    # --- Avversario (metà alta) ---
    # Nome + livello dell'avversario (solo la riga di testo, HP escluso).
    # `h` allargato da 0.057 a 0.065: con il box stretto l'OCR leggeva
    # "HEEZIHGL.33" (0.97), con questo "HEEZINGL.33" (1.00).
    opponent_name=Roi(x=0.016, y=0.129, w=0.407, h=0.065),
    # Sprite avversario: metà alta destra. pHash è tollerante alle inclusioni
    # di sfondo, quindi il crop non deve essere perfettamente stretto.
    opponent_sprite=Roi(x=0.469, y=0.060, w=0.423, h=0.359),
    # Barra HP avversario: barra colorata dopo la label "PS".
    opponent_hp_bar=Roi(x=0.135, y=0.198, w=0.258, h=0.029),
    # --- Giocatore (metà bassa) ---
    # HUD del giocatore in basso-destra: riga nome+livello (esclude la barra
    # HP che vive più in basso). Box alto, quindi tollerava lo sfasamento del
    # chrome anche prima di questa correzione.
    player_name=Roi(x=0.546, y=0.462, w=0.412, h=0.085),
    # Sprite posteriore del giocatore in basso-sinistra: allargato verso
    # destra rispetto alla prima calibrazione per includere la parte destra
    # dello sprite che sporgeva oltre il ROI iniziale.
    player_sprite=Roi(x=0.077, y=0.454, w=0.371, h=0.320),
    # Barra HP giocatore: barra colorata "PS ▬▬▬" (prima dei numeri assoluti).
    player_hp_bar=Roi(x=0.639, y=0.593, w=0.268, h=0.029),
    # --- Menu Pokemon ---
    # Layout Rosso Fuoco: slot 0 grande a sinistra (Pokemon "attivo"), slot 1-5
    # righe compatte a destra. `slot_areas` è tight sul nome, `slot_levels`
    # sul solo "L.XX": i due box non si sovrappongono.
    # Coord estratte via `scripts/extract_roi_from_annotated.py` da immagine
    # annotata a mano dall'utente (magenta=nome, ciano=icona, giallo=livello).
    team_menu=TeamMenuRois(
        slot_areas=(
            Roi(x=0.126, y=0.225, w=0.193, h=0.069),  # slot 0 (attivo, box sx)
            Roi(x=0.484, y=0.088, w=0.217, h=0.050),  # slot 1 (col dx)
            Roi(x=0.486, y=0.241, w=0.218, h=0.050),
            Roi(x=0.489, y=0.389, w=0.216, h=0.050),
            Roi(x=0.489, y=0.540, w=0.216, h=0.050),
            Roi(x=0.486, y=0.690, w=0.217, h=0.050),  # slot 5
        ),
        slot_icons=(
            Roi(x=0.014, y=0.215, w=0.105, h=0.126),  # slot 0 (attivo)
            Roi(x=0.354, y=0.063, w=0.122, h=0.134),  # slot 1
            Roi(x=0.354, y=0.215, w=0.124, h=0.134),
            Roi(x=0.356, y=0.369, w=0.126, h=0.134),
            Roi(x=0.356, y=0.516, w=0.126, h=0.134),
            Roi(x=0.352, y=0.669, w=0.126, h=0.134),  # slot 5
        ),
        slot_levels=(
            Roi(x=0.197, y=0.299, w=0.062, h=0.045),  # slot 0 (attivo)
            Roi(x=0.563, y=0.147, w=0.062, h=0.053),  # slot 1
            Roi(x=0.563, y=0.297, w=0.062, h=0.053),
            Roi(x=0.563, y=0.445, w=0.062, h=0.053),
            Roi(x=0.563, y=0.596, w=0.062, h=0.053),
            Roi(x=0.564, y=0.747, w=0.062, h=0.053),  # slot 5
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
