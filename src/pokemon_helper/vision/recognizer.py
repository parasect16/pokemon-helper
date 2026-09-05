"""Orchestratore di riconoscimento del Pokemon avversario.

Combina i due segnali indipendenti prodotti dalle altre facciate del pacchetto
`vision`:

- **OCR del nome** via `OcrEngine`: legge il riquadro nome+livello, filtra il
  livello (pattern `L.XX`), passa il testo residuo a `PokemonRepository.
  find_by_fuzzy_name` per un match tollerante agli errori tipografici.
- **pHash dello sprite** via `compute_phash`: calcola il pHash del ritaglio
  sprite avversario e cerca il match più vicino via
  `PokemonRepository.find_pokemon_by_sprite_hash`.

Il risultato è un `Recognition` con id del Pokemon, confidenza combinata
(0-1) e il segnale che ha vinto. La sorgente `both` è la più affidabile:
significa che OCR e pHash convergono sullo stesso Pokemon.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from PIL import Image

from pokemon_helper.data import PokemonRepository
from pokemon_helper.vision.ocr import OcrEngine, OcrResult
from pokemon_helper.vision.roi import GameLayout, GameRois, compute_game_area, roi_to_pixels
from pokemon_helper.vision.sprite_hash import compute_icon_phash, compute_phash

# Pattern per riconoscere l'indicatore di livello: es. "L.33", "L 33", "Lv.33".
_LEVEL_PATTERN = re.compile(r"^l\.?v?\.?\s*\d+$", re.IGNORECASE)
# Pattern che ESTRAE il numero di livello (usato per popolare TeamSlot.level).
_LEVEL_EXTRACT = re.compile(r"l\.?v?\.?\s*(\d+)", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class Recognition:
    """Esito di un riconoscimento avversario."""

    pokemon_id: int
    confidence: float
    source: str  # "both" | "name" | "sprite"
    name_score: float | None = None
    sprite_distance: int | None = None
    debug: dict = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TeamRecognition:
    """Esito del riconoscimento di uno slot della squadra dal menu Pokemon.

    `pokemon_id=None` significa "nessun match affidabile" (nickname
    sconosciuto e icona non riconosciuta, oppure slot vuoto).
    `level=None` significa livello non decifrato.
    `source`: "name" (OCR nome ha matchato), "icon" (fallback icona pHash),
    o "none" (nessun match).
    """

    slot_index: int  # 0..5, ordine visivo dello schermo (0 = attivo)
    pokemon_id: int | None
    level: int | None
    confidence: float
    ocr_text: str
    source: str = "none"


class Recognizer:
    """Combina OCR + pHash per identificare il Pokemon avversario."""

    def __init__(self, repository: PokemonRepository, ocr: OcrEngine) -> None:
        self._repo = repository
        self._ocr = ocr

    def recognize_opponent(
        self,
        frame: Image.Image,
        layout: GameLayout,
        rois: GameRois,
        generation: int,
    ) -> Recognition | None:
        """Riconosce l'avversario a partire da un frame + ROI del gioco.

        Ritorna `None` se nessun segnale ha prodotto un candidato.
        """
        return self._recognize(
            frame,
            layout,
            name_roi=rois.opponent_name,
            sprite_roi=rois.opponent_sprite,
            generation=generation,
        )

    def recognize_player(
        self,
        frame: Image.Image,
        layout: GameLayout,
        rois: GameRois,
        generation: int,
    ) -> Recognition | None:
        """Riconosce il Pokemon del giocatore (back sprite + HUD basso-dx).

        Stesso schema di `recognize_opponent`: usa le ROI `player_name` e
        `player_sprite`. Il pHash cerca match sul lato `back` grazie alla
        stessa scansione — il repository restituisce comunque per pokemon_id.
        """
        return self._recognize(
            frame,
            layout,
            name_roi=rois.player_name,
            sprite_roi=rois.player_sprite,
            generation=generation,
        )

    def recognize_team(
        self,
        frame: Image.Image,
        layout: GameLayout,
        rois: GameRois,
        generation: int,
        *,
        min_similarity: float = 0.55,
        icon_max_distance: int = 18,
    ) -> list[TeamRecognition]:
        """Riconosce i 6 slot della squadra dalla schermata elenco Pokemon.

        Per ciascun slot:
        1. OCR sul riquadro nome + livello, `_pick_name_text` sceglie il testo
           e `_extract_level` prende il numero.
        2. Fuzzy match sul nome via repository.
        3. Se il fuzzy non trova nulla (probabile nickname), fallback su pHash
           dell'icona menu contro il subset `side='icon'` di `sprite_hashes`.

        Ritorna sempre 6 elementi in ordine visivo (slot 1 = Pokemon attivo).
        Un elemento con `pokemon_id is None` indica match assente da entrambi
        i canali (nickname + icona non riconosciuta o slot vuoto).
        """
        game_area = compute_game_area(frame.width, frame.height, layout)
        results: list[TeamRecognition] = []
        slot_icons = rois.team_menu.slot_icons
        slot_levels = rois.team_menu.slot_levels
        for index, slot_roi in enumerate(rois.team_menu.slot_areas):
            crop = frame.crop(roi_to_pixels(slot_roi, game_area).as_crop_box())
            ocr_lines = self._ocr.recognize(crop)
            name_text = _pick_name_text(ocr_lines)

            # OCR dedicata sul crop del livello con preprocessing forte:
            # `high_contrast=True` normalizza il testo bianco-su-blu del menu
            # in nero-su-bianco standard; `upscale=4` porta i glifi pixel
            # piccoli a dimensioni digeribili da RapidOCR.
            level_crop = frame.crop(roi_to_pixels(slot_levels[index], game_area).as_crop_box())
            level_lines = self._ocr.recognize(level_crop, upscale=4, high_contrast=True)
            level = _extract_level(level_lines) or _extract_level(ocr_lines)

            pokemon_id: int | None = None
            confidence = 0.0
            source = "none"
            if name_text:
                candidates = self._repo.find_by_fuzzy_name(
                    name_text, generation, min_similarity=min_similarity, limit=1
                )
                if candidates:
                    pokemon, score = candidates[0]
                    pokemon_id = pokemon.id
                    confidence = score
                    source = "name"

            # Fallback icona se il nome non ha prodotto nulla di affidabile.
            if pokemon_id is None:
                icon_crop = frame.crop(roi_to_pixels(slot_icons[index], game_area).as_crop_box())
                icon_phash = compute_icon_phash(icon_crop)
                icon_matches = self._repo.find_pokemon_by_sprite_hash(
                    icon_phash,
                    generation,
                    sides=("icon",),
                    max_distance=icon_max_distance,
                    limit=1,
                )
                if icon_matches:
                    best = icon_matches[0]
                    pokemon_id = best.pokemon_id
                    # Confidenza inversamente proporzionale alla distanza:
                    # 0 → 1.0, `icon_max_distance` → 0.5. Sopra soglia il match
                    # è già stato scartato da `find_pokemon_by_sprite_hash`.
                    confidence = max(0.5, 1.0 - best.distance / (icon_max_distance * 2))
                    source = "icon"

            results.append(
                TeamRecognition(
                    slot_index=index,
                    pokemon_id=pokemon_id,
                    level=level,
                    confidence=confidence,
                    ocr_text=name_text or "",
                    source=source,
                )
            )
        return results

    def _recognize(
        self,
        frame: Image.Image,
        layout: GameLayout,
        *,
        name_roi,
        sprite_roi,
        generation: int,
    ) -> Recognition | None:
        """Nucleo condiviso: OCR nome + pHash sprite → combina."""
        game_area = compute_game_area(frame.width, frame.height, layout)
        name_crop = frame.crop(roi_to_pixels(name_roi, game_area).as_crop_box())
        sprite_crop = frame.crop(roi_to_pixels(sprite_roi, game_area).as_crop_box())

        ocr_results = self._ocr.recognize(name_crop)
        candidate_text = _pick_name_text(ocr_results)
        name_matches: list[tuple[int, float]] = []
        if candidate_text:
            name_matches = [
                (pokemon.id, score)
                for pokemon, score in self._repo.find_by_fuzzy_name(
                    candidate_text, generation, min_similarity=0.55, limit=5
                )
            ]

        phash = compute_phash(sprite_crop)
        sprite_matches = self._repo.find_pokemon_by_sprite_hash(
            phash, generation, max_distance=30, limit=10
        )
        sprite_pairs: list[tuple[int, int]] = [(m.pokemon_id, m.distance) for m in sprite_matches]

        debug = {
            "ocr_text": candidate_text or "",
            "phash": phash,
        }

        return _combine(name_matches, sprite_pairs, debug)


def _pick_name_text(ocr_results: list[OcrResult]) -> str | None:
    """Sceglie la stringa candidata a nome fra i risultati OCR.

    Scarta righe che sono un puro indicatore di livello (`L.33`, `Lv.5`, ...).
    Se restano più righe, ritorna la più lunga (di solito il nome è più lungo
    del livello dopo il filtro).
    """
    filtered = [
        result
        for result in ocr_results
        if result.text and not _LEVEL_PATTERN.match(result.text.strip())
    ]
    if not filtered:
        return None
    # Pulizia soft: rimuove eventuali code non alfabetiche (simboli gender ♀/♂,
    # backslash spuri) dalla stringa scelta.
    filtered.sort(key=lambda r: len(r.text), reverse=True)
    return _strip_non_alpha_tail(filtered[0].text)


def _strip_non_alpha_tail(text: str) -> str:
    """Rimuove dalla coda i caratteri non alfabetici (simboli gender, ecc.)."""
    trimmed = text.rstrip()
    while trimmed and not trimmed[-1].isalpha():
        trimmed = trimmed[:-1]
    return trimmed


def _extract_level(ocr_lines: list[OcrResult]) -> int | None:
    """Estrae il livello (1-100) dai risultati OCR.

    Priorità:
    1. Pattern `L.XX` / `Lv.XX` (l'OCR spesso lo restituisce così).
    2. Riga con solo cifre in [1, 100].
    3. Riga di 3 cifre che inizia con `1`: probabile misread della `L` di
       `L.XX` come cifra `1`; scarta la prima cifra e riprova (es. `137` → 37).
    """
    for result in ocr_lines:
        match = _LEVEL_EXTRACT.search(result.text)
        if match:
            try:
                level = int(match.group(1))
            except ValueError:
                continue
            if 1 <= level <= 100:
                return level
    for result in ocr_lines:
        text = result.text.strip()
        if text.isdigit():
            try:
                level = int(text)
            except ValueError:
                continue
            if 1 <= level <= 100:
                return level
    # Fallback: `L.XX` letto come `1XX` (L → 1). Se la stringa è di 3 cifre
    # che iniziano per 1 (100-199), togli la prima e prova come livello 0-99.
    for result in ocr_lines:
        text = result.text.strip()
        if len(text) == 3 and text.isdigit() and text.startswith("1"):
            try:
                level = int(text[1:])
            except ValueError:
                continue
            if 1 <= level <= 100:
                return level
    return None


def _combine(
    name_matches: list[tuple[int, float]],
    sprite_matches: list[tuple[int, int]],
    debug: dict,
) -> Recognition | None:
    """Fonde i due elenchi in un unico verdetto con confidenza 0-1.

    Politica:
    - Se un Pokemon compare in entrambi i top-N: `source='both'`, confidenza
      alta (base 0.7 + boost proporzionale al fuzzy score).
    - Se solo in name_matches con score ≥ 0.75: `source='name'`, confidenza
      pari allo score.
    - Se solo in sprite_matches con distanza ≤ 12: `source='sprite'`,
      confidenza `1 - distance/32` (basso per grandi distanze).
    """
    name_map = dict(name_matches)
    sprite_map = dict(sprite_matches)

    # Intersezione: pokemon presenti in entrambi.
    both_ids = set(name_map) & set(sprite_map)
    if both_ids:
        pokemon_id = max(
            both_ids,
            key=lambda pid: (name_map[pid], -sprite_map[pid]),
        )
        name_score = name_map[pokemon_id]
        distance = sprite_map[pokemon_id]
        return Recognition(
            pokemon_id=pokemon_id,
            confidence=min(1.0, 0.7 + name_score * 0.3),
            source="both",
            name_score=name_score,
            sprite_distance=distance,
            debug=debug,
        )

    # Solo nome, se abbastanza sicuro.
    if name_matches:
        best_id, best_score = max(name_matches, key=lambda pair: pair[1])
        if best_score >= 0.75:
            return Recognition(
                pokemon_id=best_id,
                confidence=best_score,
                source="name",
                name_score=best_score,
                debug=debug,
            )

    # Solo sprite, molto conservativo perché il pHash su cattura con
    # background reale ha bias.
    if sprite_matches:
        best_id, best_distance = min(sprite_matches, key=lambda pair: pair[1])
        if best_distance <= 12:
            return Recognition(
                pokemon_id=best_id,
                confidence=max(0.0, 1.0 - best_distance / 32.0),
                source="sprite",
                sprite_distance=best_distance,
                debug=debug,
            )

    # Nessun candidato, ma restituiamo il migliore fuzzy match anche se sotto
    # soglia, per dare feedback in debug (con confidenza bassa).
    if name_matches:
        best_id, best_score = max(name_matches, key=lambda pair: pair[1])
        return Recognition(
            pokemon_id=best_id,
            confidence=best_score * 0.5,
            source="name",
            name_score=best_score,
            debug=debug,
        )
    return None
