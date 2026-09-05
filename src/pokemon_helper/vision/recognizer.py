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
from pokemon_helper.vision.sprite_hash import compute_phash

# Pattern per riconoscere l'indicatore di livello: es. "L.33", "L 33", "Lv.33".
_LEVEL_PATTERN = re.compile(r"^l\.?v?\.?\s*\d+$", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class Recognition:
    """Esito di un riconoscimento avversario."""

    pokemon_id: int
    confidence: float
    source: str  # "both" | "name" | "sprite"
    name_score: float | None = None
    sprite_distance: int | None = None
    debug: dict = field(default_factory=dict)


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
        game_area = compute_game_area(frame.width, frame.height, layout)
        name_crop = frame.crop(roi_to_pixels(rois.opponent_name, game_area).as_crop_box())
        sprite_crop = frame.crop(roi_to_pixels(rois.opponent_sprite, game_area).as_crop_box())

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
