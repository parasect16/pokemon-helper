"""Calibratore visuale delle ROI: si disegnano col mouse sul frame catturato.

Finora le ROI si misuravano a mano — contando pixel su una PNG annotata, o a
occhio — e due volte è costato un bug: un rettangolo che *sembra* giusto e
legge la riga sbagliata non si distingue da uno giusto finché non si guarda
cosa ne esce l'OCR.

Il dialogo mostra il frame dell'emulatore, l'elenco dei sedici rettangoli da
definire e, per ciascuno, dove va messo. Si trascina, si aggiusta con le
frecce, si salva.

Due scelte che tolgono di mezzo gli errori tipici:

- **Snap alla griglia nativa.** mGBA rende 240x160 in una finestra qualunque,
  di solito a fattore non intero: un rettangolo tracciato col mouse cade a
  metà di un pixel del gioco. `snap_roi_to_native` lo riporta sulla griglia
  vera, che è quella su cui sono misurate tutte le ROI buone del repo.
- **Coordinate native sempre a schermo.** Il riquadro selezionato mostra
  `x, y, w, h` in pixel del gioco, non del frame: sono i numeri che si
  possono confrontare con uno screenshot e con `roi.py`.
- **Si vede cosa ci si legge dentro.** Sotto l'elenco compaiono il ritaglio
  ingrandito e il testo che ne esce: è la differenza fra un rettangolo che
  sembra giusto e uno che lo è. Entrambi i bug di calibrazione di questo repo
  sono sopravvissuti a un'ispezione visiva e sono morti alla prima lettura.

Il disegno vive in `_RoiCanvas`, che non sa nulla di calibrazione: riceve un
frame, un insieme di ROI e una selezione, ed emette il rettangolo che l'utente
ha tracciato. La logica di quali rettangoli esistano sta in
`vision.roi_targets`, quella di come si salvano in `vision.roi_store`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PIL import Image
from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QImage, QKeyEvent, QMouseEvent, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from pokemon_helper.vision.roi import (
    GameLayout,
    GameRois,
    PixelRect,
    Roi,
    compute_game_area,
    pixels_to_roi,
    roi_to_pixels,
    snap_roi_to_native,
)
from pokemon_helper.vision.roi_targets import (
    SCREEN_BATTLE,
    SCREEN_LABELS,
    SCREEN_PARTY_MENU,
    TARGETS,
    TARGETS_BY_KEY,
    get_roi,
    replace_roi,
)

# Colori del disegno. Il selezionato deve staccare dagli altri anche sopra il
# teal del menu Pokemon e il verde del campo di battaglia, che occupano quasi
# tutta la tavolozza fredda.
_COLOR_SELECTED = QColor(255, 0, 255)
_COLOR_OTHER = QColor(0, 200, 255, 140)
_COLOR_DRAG = QColor(255, 220, 0)

# Zoom in percentuale: sotto il 50% non si distingue un pixel nativo, sopra il
# 400% si vede solo la sfocatura dello scaling dell'emulatore.
_MIN_ZOOM_PERCENT = 50
_MAX_ZOOM_PERCENT = 400
_DEFAULT_ZOOM_PERCENT = 100

# Larghezza a cui puntare all'apertura. Una cattura di mGBA sta sui 1100 px e
# a 1:1 non entra in finestra insieme all'elenco: si aprirebbe già a metà,
# costringendo a scorrere prima ancora di aver capito cosa si sta guardando.
# Lo zoom fine si mette dopo, sul rettangolo che interessa.
_FIT_TARGET_WIDTH = 900

# Larghezza a cui ingrandire il ritaglio di anteprima. Un nome di Pokemon sta
# in ~46x11 pixel nativi: a dimensione naturale non ci si legge nulla, e il
# punto dell'anteprima è proprio leggere.
_PREVIEW_WIDTH = 240

# Intestazioni dei due gruppi nell'elenco dei bersagli.
_SCREEN_HEADERS = {
    SCREEN_BATTLE: "— Schermata di combattimento —",
    SCREEN_PARTY_MENU: "— Elenco Pokemon —",
}


# Firma di chi legge un ritaglio: riceve l'immagine ritagliata e la chiave del
# bersaglio, ritorna una riga da mostrare. Il "come" sta fuori dal dialogo —
# OCR per i box di testo, conteggio di pixel per la barra PS — perché sono
# tutte cose che vivono in `vision` e trascinano numpy e i modelli ONNX.
RoiReader = Callable[[Image.Image, str], str]


@dataclass(frozen=True, slots=True)
class CalibrationFrame:
    """Un frame su cui calibrare, con quel che serve per interpretarlo.

    `screen` è la schermata riconosciuta — i valori di `roi_targets` — e serve
    a dire all'utente che sta disegnando una ROI di combattimento mentre a
    video c'è l'elenco Pokemon. La classificazione la fa chi cattura, non il
    dialogo: `vision.screen_mode` tira dentro numpy, e il calibratore deve
    restare importabile anche dove gli extra `[vision]` non ci sono.
    """

    image: Image.Image
    layout: GameLayout
    screen: str = ""
    # Motivo della classificazione, quando c'è: finisce nel tooltip.
    note: str = ""


def fit_zoom_percent(frame_width: int) -> int:
    """Zoom iniziale perché il frame ci stia in larghezza, senza ingrandire."""
    if frame_width <= _FIT_TARGET_WIDTH:
        return _DEFAULT_ZOOM_PERCENT
    return max(_MIN_ZOOM_PERCENT, int(_FIT_TARGET_WIDTH / frame_width * 100))


def pil_to_qimage(image: Image.Image) -> QImage:
    """Converte un frame PIL in `QImage` RGB888.

    `QImage` non copia il buffer che riceve, quindi la copia la facciamo qui:
    senza, l'immagine punterebbe a dei byte che Python è libero di liberare
    appena la funzione ritorna, e il risultato è una finestra piena di
    spazzatura o un crash.
    """
    rgb = image.convert("RGB")
    return QImage(
        rgb.tobytes(), rgb.width, rgb.height, 3 * rgb.width, QImage.Format.Format_RGB888
    ).copy()


class _RoiCanvas(QWidget):
    """Mostra il frame e ci fa disegnare sopra un rettangolo alla volta.

    Non conosce il concetto di "calibrazione": riceve frame, ROI e selezione,
    ed emette `roiDrawn` con la chiave e il rettangolo tracciato, già agganciato
    alla griglia nativa. Chi lo usa decide cosa farne.
    """

    roiDrawn = Signal(str, object)  # chiave del bersaglio, Roi agganciata

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._pixmap = QPixmap()
        self._layout: GameLayout | None = None
        self._game_area = PixelRect(x=0, y=0, w=1, h=1)
        self._rois: GameRois | None = None
        self._selected: str | None = None
        self._zoom = _DEFAULT_ZOOM_PERCENT / 100
        self._drag_origin: QPoint | None = None
        self._drag_current: QPoint | None = None
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(False)

    # ------------------------------------------------------------- contenuto

    def set_frame(self, frame: CalibrationFrame) -> None:
        """Sostituisce il frame di riferimento e ricalcola l'area di gioco."""
        image = frame.image
        self._pixmap = QPixmap.fromImage(pil_to_qimage(image))
        self._layout = frame.layout
        self._game_area = compute_game_area(image.width, image.height, frame.layout)
        self._resize_to_zoom()

    def set_rois(self, rois: GameRois) -> None:
        self._rois = rois
        self.update()

    def set_selected(self, key: str | None) -> None:
        self._selected = key
        self.update()

    def set_zoom_percent(self, percent: int) -> None:
        self._zoom = max(_MIN_ZOOM_PERCENT, min(percent, _MAX_ZOOM_PERCENT)) / 100
        self._resize_to_zoom()

    @property
    def zoom(self) -> float:
        return self._zoom

    @property
    def game_area(self) -> PixelRect:
        return self._game_area

    # ------------------------------------------------------------ geometria

    def widget_to_frame(self, point: QPoint) -> QPoint:
        """Da coordinate del widget a pixel del frame catturato."""
        if self._zoom <= 0:
            return QPoint(0, 0)
        return QPoint(int(round(point.x() / self._zoom)), int(round(point.y() / self._zoom)))

    def frame_to_widget(self, x: int, y: int) -> QPoint:
        """Da pixel del frame a coordinate del widget."""
        return QPoint(int(round(x * self._zoom)), int(round(y * self._zoom)))

    def roi_from_drag(self, start: QPoint, end: QPoint) -> Roi:
        """Il rettangolo trascinato, in coordinate normalizzate e agganciato.

        Il trascinamento può partire da qualunque angolo: si normalizza in
        `(sinistra, alto, larghezza, altezza)` prima di convertire.
        """
        first = self.widget_to_frame(start)
        second = self.widget_to_frame(end)
        left, right = sorted((first.x(), second.x()))
        top, bottom = sorted((first.y(), second.y()))
        rect = PixelRect(x=left, y=top, w=right - left, h=bottom - top)
        roi = pixels_to_roi(rect, self._game_area)
        return snap_roi_to_native(roi, self._layout) if self._layout else roi

    # --------------------------------------------------------------- eventi

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton or self._selected is None:
            return
        self._drag_origin = event.position().toPoint()
        self._drag_current = self._drag_origin
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_origin is None:
            return
        self._drag_current = event.position().toPoint()
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._drag_origin is None or self._selected is None:
            return
        end = event.position().toPoint()
        origin, self._drag_origin = self._drag_origin, None
        self._drag_current = None
        self.roiDrawn.emit(self._selected, self.roi_from_drag(origin, end))

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Frecce: sposta di un pixel nativo. Con Shift: ridimensiona.

        È il modo in cui si sistema un rettangolo dopo averlo tracciato: col
        mouse un pixel nativo sono quattro pixel schermo, e prenderlo al
        primo colpo non succede.
        """
        deltas = {
            Qt.Key.Key_Left: (-1, 0),
            Qt.Key.Key_Right: (1, 0),
            Qt.Key.Key_Up: (0, -1),
            Qt.Key.Key_Down: (0, 1),
        }
        delta = deltas.get(Qt.Key(event.key()))
        if delta is None or self._selected is None or self._rois is None or self._layout is None:
            super().keyPressEvent(event)
            return
        resizing = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        nudged = nudge_roi(
            get_roi(self._rois, self._selected), self._layout, delta, resize=resizing
        )
        self.roiDrawn.emit(self._selected, nudged)

    # -------------------------------------------------------------- disegno

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        if self._pixmap.isNull():
            return
        painter.drawPixmap(
            QRect(0, 0, self._scaled_width(), self._scaled_height()),
            self._pixmap,
        )
        if self._rois is not None:
            for target in TARGETS:
                if target.key == self._selected:
                    continue
                self._draw_roi(painter, get_roi(self._rois, target.key), _COLOR_OTHER, width=1)
            if self._selected is not None:
                self._draw_roi(
                    painter, get_roi(self._rois, self._selected), _COLOR_SELECTED, width=2
                )
        if self._drag_origin is not None and self._drag_current is not None:
            pen = QPen(_COLOR_DRAG, 2, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawRect(QRect(self._drag_origin, self._drag_current).normalized())

    def _draw_roi(self, painter: QPainter, roi: Roi, color: QColor, *, width: int) -> None:
        rect = roi_to_pixels(roi, self._game_area)
        top_left = self.frame_to_widget(rect.x, rect.y)
        bottom_right = self.frame_to_widget(rect.x + rect.w, rect.y + rect.h)
        painter.setPen(QPen(color, width))
        painter.drawRect(QRect(top_left, bottom_right))

    # --------------------------------------------------------------- interni

    def _scaled_width(self) -> int:
        return int(round(self._pixmap.width() * self._zoom))

    def _scaled_height(self) -> int:
        return int(round(self._pixmap.height() * self._zoom))

    def _resize_to_zoom(self) -> None:
        if self._pixmap.isNull():
            return
        self.setFixedSize(self._scaled_width(), self._scaled_height())
        self.update()


def nudge_roi(roi: Roi, layout: GameLayout, delta: tuple[int, int], *, resize: bool = False) -> Roi:
    """Sposta o ridimensiona una ROI di un pixel nativo.

    `resize=False` trasla il rettangolo, `resize=True` ne muove il solo angolo
    in basso a destra. Entrambe le operazioni restano dentro i bordi nativi e
    non scendono sotto il pixel singolo: è un aggiustamento fine, non un modo
    di cancellare il rettangolo.
    """
    width, height = layout.native_size
    dx, dy = delta
    left = round(roi.x * width)
    top = round(roi.y * height)
    box_w = max(1, round(roi.w * width))
    box_h = max(1, round(roi.h * height))
    if resize:
        box_w = max(1, min(box_w + dx, width - left))
        box_h = max(1, min(box_h + dy, height - top))
    else:
        left = max(0, min(left + dx, width - box_w))
        top = max(0, min(top + dy, height - box_h))
    return Roi(x=left / width, y=top / height, w=box_w / width, h=box_h / height)


def format_native_rect(roi: Roi, layout: GameLayout) -> str:
    """Il rettangolo in pixel nativi, come lo si legge su uno screenshot."""
    width, height = layout.native_size
    return (
        f"x={round(roi.x * width)} y={round(roi.y * height)} "
        f"w={round(roi.w * width)} h={round(roi.h * height)} "
        f"(nativi {width}x{height})"
    )


class RoiCalibratorDialog(QDialog):
    """Dialogo di calibrazione: elenco dei bersagli a sinistra, frame a destra.

    Il risultato si legge con `rois()` dopo un `exec()` accettato. Il dialogo
    non salva nulla: riceve un frame, restituisce delle ROI.

    La cattura arriva da fuori come `frame_source`, una funzione che ritorna
    un `CalibrationFrame`. Così il dialogo resta costruibile in un test senza
    emulatore e senza gli extra `[vision]`; senza sorgente il pulsante
    "Cattura" è spento e si lavora sul frame iniziale.
    """

    def __init__(
        self,
        *,
        frame: CalibrationFrame,
        rois: GameRois,
        game_key: str,
        defaults: GameRois | None = None,
        frame_source: Callable[[], CalibrationFrame] | None = None,
        reader: RoiReader | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Calibrazione ROI — {game_key}")
        self._layout_info = frame.layout
        self._screen = frame.screen
        self._screen_note = frame.note
        self._rois = rois
        self._defaults = defaults if defaults is not None else rois
        self._frame_source = frame_source
        self._reader = reader
        self._image = frame.image

        self._targets_list = QListWidget()
        self._hint = QLabel()
        self._hint.setWordWrap(True)
        self._coords = QLabel()
        self._preview = QLabel()
        self._preview.setMinimumHeight(60)
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._readback = QLabel()
        self._readback.setWordWrap(True)
        self._screen_banner = QLabel()
        self._screen_banner.setWordWrap(True)
        self._canvas = _RoiCanvas()
        self._zoom = QSlider(Qt.Orientation.Horizontal)
        self._capture_button = QPushButton("Cattura la schermata a video")
        self._capture_button.setEnabled(frame_source is not None)
        self._reset_button = QPushButton("Ripristina questo rettangolo")
        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )

        self._build_ui()
        self._populate_targets()
        self._canvas.set_frame(frame)
        self._canvas.set_rois(rois)
        self._zoom.setValue(fit_zoom_percent(frame.image.width))
        self._select_first_target()
        self.resize(1200, 800)

    # ------------------------------------------------------------- pubblico

    def rois(self) -> GameRois:
        """Le ROI correnti, calibrate o no."""
        return self._rois

    def set_frame(self, frame: CalibrationFrame) -> None:
        """Sostituisce il frame mostrato, per ricatturare senza riaprire.

        I rettangoli già disegnati restano: si ricattura per passare da una
        schermata all'altra, non per ricominciare.
        """
        self._layout_info = frame.layout
        self._screen = frame.screen
        self._screen_note = frame.note
        self._image = frame.image
        self._canvas.set_frame(frame)
        self._canvas.set_rois(self._rois)
        self._refresh_screen_banner()
        key = self.selected_key()
        if key is not None:
            self._refresh_readback(key)

    def selected_key(self) -> str | None:
        item = self._targets_list.currentItem()
        return None if item is None else item.data(Qt.ItemDataRole.UserRole)

    # --------------------------------------------------------------- interni

    def _build_ui(self) -> None:
        self._targets_list.setMinimumWidth(200)
        self._targets_list.currentItemChanged.connect(lambda *_: self._on_target_changed())

        self._zoom.setRange(_MIN_ZOOM_PERCENT, _MAX_ZOOM_PERCENT)
        self._zoom.setValue(_DEFAULT_ZOOM_PERCENT)
        self._zoom.valueChanged.connect(self._canvas.set_zoom_percent)

        scroll = QScrollArea()
        scroll.setWidget(self._canvas)
        scroll.setWidgetResizable(False)

        self._canvas.roiDrawn.connect(self._on_roi_drawn)
        self._capture_button.clicked.connect(self._on_capture)
        self._reset_button.clicked.connect(self._on_reset_current)
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)

        left = QVBoxLayout()
        left.addWidget(QLabel("Rettangoli da calibrare"))
        left.addWidget(self._targets_list, stretch=1)
        left.addWidget(self._hint)
        left.addWidget(self._coords)
        left.addWidget(self._preview)
        left.addWidget(self._readback)
        left.addWidget(self._reset_button)

        right_header = QHBoxLayout()
        right_header.addWidget(self._capture_button)
        right_header.addWidget(self._screen_banner, stretch=1)

        zoom_row = QHBoxLayout()
        zoom_row.addWidget(QLabel("Zoom"))
        zoom_row.addWidget(self._zoom, stretch=1)

        right = QVBoxLayout()
        right.addLayout(right_header)
        right.addWidget(scroll, stretch=1)
        right.addLayout(zoom_row)

        body = QHBoxLayout()
        body.addLayout(left)
        body.addLayout(right, stretch=1)

        root = QVBoxLayout(self)
        root.addLayout(body, stretch=1)
        root.addWidget(self._buttons)

    def _populate_targets(self) -> None:
        """Riempie l'elenco, con un'intestazione non selezionabile per schermata."""
        current_screen: str | None = None
        for target in TARGETS:
            if target.screen != current_screen:
                current_screen = target.screen
                header = QListWidgetItem(_SCREEN_HEADERS.get(current_screen, current_screen))
                header.setFlags(Qt.ItemFlag.NoItemFlags)
                self._targets_list.addItem(header)
            item = QListWidgetItem(target.label)
            item.setData(Qt.ItemDataRole.UserRole, target.key)
            self._targets_list.addItem(item)

    def _select_first_target(self) -> None:
        for row in range(self._targets_list.count()):
            if self._targets_list.item(row).data(Qt.ItemDataRole.UserRole) is not None:
                self._targets_list.setCurrentRow(row)
                return

    def _on_target_changed(self) -> None:
        key = self.selected_key()
        self._canvas.set_selected(key)
        if key is None:
            self._hint.setText("")
            self._coords.setText("")
            return
        self._hint.setText(TARGETS_BY_KEY[key].hint)
        self._refresh_coords(key)
        self._refresh_screen_banner()
        self._refresh_readback(key)

    def _on_capture(self) -> None:
        """Rilegge la finestra dell'emulatore e mostra il nuovo frame.

        Un fallimento (emulatore chiuso, finestra non catturabile) finisce
        nella riga di stato e lascia a schermo il frame precedente: perdere
        l'immagine su cui si sta lavorando sarebbe la reazione peggiore a un
        errore transitorio.
        """
        if self._frame_source is None:
            return
        try:
            frame = self._frame_source()
        except Exception as exc:  # noqa: BLE001 — va mostrato, non propagato
            self._screen_banner.setText(f"\u26a0 Cattura fallita: {exc}")
            self._screen_banner.setToolTip(str(exc))
            return
        self.set_frame(frame)

    def _refresh_screen_banner(self) -> None:
        """Dice cosa c'è a video e se è la schermata giusta per il bersaglio.

        Disegnare una ROI di combattimento mentre a video c'è l'elenco
        Pokemon produce un rettangolo che sembra a posto e legge il vuoto: è
        il modo più rapido di rovinare una calibrazione, e questo è l'unico
        momento in cui si può dire qualcosa.
        """
        shown = SCREEN_LABELS.get(self._screen, "schermata non riconosciuta")
        key = self.selected_key()
        target = TARGETS_BY_KEY[key] if key is not None else None
        if target is not None and self._screen and target.screen != self._screen:
            expected = SCREEN_LABELS.get(target.screen, target.screen)
            self._screen_banner.setText(
                f"\u26a0 A video: {shown}. Questo rettangolo si misura su: {expected}."
            )
        else:
            self._screen_banner.setText(f"A video: {shown}.")
        self._screen_banner.setToolTip(self._screen_note)

    def _on_roi_drawn(self, key: str, roi: Roi) -> None:
        self._rois = replace_roi(self._rois, key, roi)
        self._canvas.set_rois(self._rois)
        self._refresh_coords(key)
        self._refresh_readback(key)

    def _on_reset_current(self) -> None:
        """Riporta il solo rettangolo selezionato al valore di fabbrica."""
        key = self.selected_key()
        if key is None:
            return
        self._on_roi_drawn(key, get_roi(self._defaults, key))

    def _refresh_coords(self, key: str) -> None:
        self._coords.setText(format_native_rect(get_roi(self._rois, key), self._layout_info))

    def _refresh_readback(self, key: str) -> None:
        """Mostra il ritaglio del rettangolo e cosa ci si legge dentro.

        L'anteprima è ingrandita a interpolazione nulla: i font sono pixel
        art, e qualunque levigatura renderebbe più leggibile l'anteprima di
        quanto non lo sia il ritaglio vero, che è l'opposto di ciò che serve.

        Senza un `reader` resta la sola anteprima: già quella dice se il
        rettangolo taglia il testo a metà.
        """
        crop = self._crop_for(key)
        self._preview.setPixmap(
            QPixmap.fromImage(pil_to_qimage(crop)).scaledToWidth(
                _PREVIEW_WIDTH, Qt.TransformationMode.FastTransformation
            )
        )
        if self._reader is None:
            self._readback.setText("")
            return
        try:
            self._readback.setText(self._reader(crop, key))
        except Exception as exc:  # noqa: BLE001 — una lettura fallita non chiude il dialogo
            self._readback.setText(f"\u26a0 lettura fallita: {exc}")

    def _crop_for(self, key: str) -> Image.Image:
        """Il ritaglio del frame corrente sul rettangolo indicato."""
        game_area = compute_game_area(self._image.width, self._image.height, self._layout_info)
        rect = roi_to_pixels(get_roi(self._rois, key), game_area)
        return self._image.crop(rect.as_crop_box())
