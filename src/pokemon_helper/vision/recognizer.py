"""Orchestratore di riconoscimento del Pokemon avversario.

Il segnale è uno solo: l'**OCR del nome** via `OcrEngine`. Legge il riquadro
nome+livello, filtra il livello (pattern `L.XX`) e passa il testo residuo a
`PokemonRepository.find_by_fuzzy_name` per un match tollerante agli errori
tipografici, con la mappa nickname dell'utente a coprire i Pokemon rinominati.

C'era un secondo canale, il pHash dello sprite, e non funzionava. In
combattimento la cattura ha campo e cielo dietro il Pokemon mentre le
reference indicizzate stanno su bianco: misurato sul vivo, la specie giusta
stava a distanza 20-24 e specie sbagliate a 14-16, quindi non entrava nei
primi tre a nessun offset di ROI. Lato avversario non superava mai la soglia
e costava soltanto; lato giocatore, dove il match gira ristretto ai sei della
squadra, c'era di peggio — a OCR muta il verdetto usciva dal ramo solo-sprite
con confidenza 0.70, sopra la soglia di applicazione, scegliendo la distanza
minima, cioè quasi sempre la specie sbagliata.

Per riabilitarlo servirebbe segmentare il soggetto dallo sfondo prima di
hashare (i fondali di battaglia sono a bande piatte, un flood-fill dai bordi
è plausibile). Finché non succede, hashare quel rettangolo è rumore.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from PIL import Image

from pokemon_helper.data import PokemonRepository
from pokemon_helper.vision.level_reader import read_level
from pokemon_helper.vision.ocr import OcrEngine, OcrResult
from pokemon_helper.vision.roi import GameLayout, GameRois, compute_game_area, roi_to_pixels

# Pattern per riconoscere l'indicatore di livello: es. "L.33", "L 33", "Lv.33".
_LEVEL_PATTERN = re.compile(r"^l\.?v?\.?\s*\d+$", re.IGNORECASE)
# Indicatore di livello in coda a un nome, con o senza separatore: senza il
# modello di detection RapidOCR restituisce nome e livello in un'unica riga.
_LEVEL_SUFFIX = re.compile(r"[\s\W_]*l\.?v?\.?\s*\d{1,3}\s*$", re.IGNORECASE)
# Pattern che ESTRAE il numero di livello (usato per popolare TeamSlot.level).
_LEVEL_EXTRACT = re.compile(r"l\.?v?\.?\s*(\d+)", re.IGNORECASE)
# Soglia di similarita per il match fuzzy sui nickname utente. L'OCR sui font
# pixel sbaglia 1-2 caratteri (es. "FIAMMETTA" letto "FIAHHETTA", ratio 0.89),
# quindi il lookup esatto sulla mappa non basta.
_NICKNAME_MIN_SIMILARITY = 0.72

# Sopra questo score il fuzzy sul nome vale come verdetto pieno; sotto, il
# candidato viene restituito con confidenza dimezzata e sta a chi chiama
# decidere se applicarlo.
_NAME_CONFIDENCE_THRESHOLD = 0.75

# Pavimento di confidenza quando il match gira ristretto a un insieme noto.
_RESTRICTED_CONFIDENCE_FLOOR = 0.7

# Cifre che l'OCR produce al posto di lettere sui font pixel. Applicata solo
# come secondo tentativo, quando il testo grezzo non ha prodotto match: i nomi
# con cifra legittima (Porygon2) matchano al primo giro e non passano di qui.
_OCR_DIGIT_TO_LETTER = str.maketrans({"0": "O", "1": "I", "2": "Z", "5": "S", "8": "B"})


@dataclass(frozen=True, slots=True)
class Recognition:
    """Esito di un riconoscimento avversario o del Pokemon in campo."""

    pokemon_id: int
    confidence: float
    # Punteggio del fuzzy match sul nome che ha prodotto il verdetto. Unico
    # segnale rimasto, quindi è sempre valorizzato.
    name_score: float
    debug: dict = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TeamRecognition:
    """Esito del riconoscimento di uno slot della squadra dal menu Pokemon.

    `pokemon_id=None` significa "nessun match affidabile" (nickname
    sconosciuto, oppure slot vuoto).
    `level=None` significa livello non decifrato.
    `source`: "name" (fuzzy sul nome di specie), "nickname" (mappa utente),
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
            generation=generation,
        )

    def recognize_player(
        self,
        frame: Image.Image,
        layout: GameLayout,
        rois: GameRois,
        generation: int,
        *,
        restrict_to_ids: set[int] | None = None,
        nickname_map: dict[str, int] | None = None,
    ) -> Recognition | None:
        """Riconosce il Pokemon del giocatore (back sprite + HUD basso-dx).

        `restrict_to_ids`: se passato, il fuzzy match sul nome viene filtrato
        a quel set. Utile per vincolare il player attivo ai soli 6 membri
        della squadra, che è quello che deve essere per definizione.

        `nickname_map`: l'HUD del giocatore mostra il nickname, non il nome
        di specie, quindi il fuzzy sui nomi di specie fallisce su ogni
        Pokemon rinominato. L'avversario non ha bisogno della mappa: gli
        allenatori non danno nickname ai propri Pokemon.
        """
        return self._recognize(
            frame,
            layout,
            name_roi=rois.player_name,
            generation=generation,
            restrict_to_ids=restrict_to_ids,
            nickname_map=nickname_map,
        )

    def recognize_team(
        self,
        frame: Image.Image,
        layout: GameLayout,
        rois: GameRois,
        generation: int,
        *,
        min_similarity: float = 0.55,
        nickname_map: dict[str, int] | None = None,
    ) -> list[TeamRecognition]:
        """Riconosce i 6 slot della squadra dalla schermata elenco Pokemon.

        Per ciascun slot:
        1. OCR sul riquadro nome + livello, `_pick_name_text` sceglie il testo
           e `_extract_level` prende il numero.
        2. Se il testo OCR (uppercase) è in `nickname_map`, usa direttamente
           il `pokemon_id` mappato con confidenza 1.0 (source='nickname').
        3. Altrimenti fuzzy match sul nome via repository.

        `nickname_map` mappa testo OCR normalizzato uppercase → `pokemon_id`.
        Serve per gestire nickname custom del giocatore (es. "FIAMMETTA" =
        Charizard) senza dover cambiare nome nel gioco.

        Ritorna sempre 6 elementi in ordine visivo (slot 1 = Pokemon attivo).
        Un elemento con `pokemon_id is None` indica nickname non mappato e
        fuzzy fallito, oppure slot vuoto.
        """
        game_area = compute_game_area(frame.width, frame.height, layout)
        results: list[TeamRecognition] = []
        slot_levels = rois.team_menu.slot_levels
        for index, slot_roi in enumerate(rois.team_menu.slot_areas):
            crop = frame.crop(roi_to_pixels(slot_roi, game_area).as_crop_box())
            ocr_lines = self._ocr.recognize(crop)
            name_text = _pick_name_text(ocr_lines)

            # `read_level` segmenta il crop e legge una cifra alla volta: sui
            # font pixel scalati a fattore non intero è l'unico modo che dà
            # letture stabili (vedi `level_reader`). Il vecchio percorso, OCR
            # sull'intera stringa, resta come fallback.
            level_crop = frame.crop(roi_to_pixels(slot_levels[index], game_area).as_crop_box())
            level = read_level(level_crop, self._ocr)
            if level is None:
                level_lines = self._ocr.recognize(level_crop, upscale=4, high_contrast=True)
                level = _extract_level(level_lines) or _extract_level(ocr_lines)

            pokemon_id: int | None = None
            confidence = 0.0
            source = "none"
            # Stadio 1: nickname esatto. Ha priorita su tutto: se l'utente ha
            # mappato quella stringa, l'intento e' esplicito.
            exact = _match_nickname(name_text or "", nickname_map, min_similarity=1.0)
            if exact is not None:
                pokemon_id, confidence = exact
                source = "nickname"
            # Stadio 2: fuzzy sul nome di specie (il caso comune, nome default).
            if pokemon_id is None and name_text:
                candidates = _fuzzy_species(
                    self._repo, name_text, generation, min_similarity=min_similarity, limit=1
                )
                if candidates:
                    pokemon_id, confidence = candidates[0]
                    source = "name"
            # Stadio 3: fuzzy sul nickname, che subentra solo se la specie non
            # ha prodotto un match forte (vedi `_apply_nickname_fallback`).
            if source != "nickname":
                current = [(pokemon_id, confidence)] if pokemon_id is not None else []
                matches, from_nickname = _apply_nickname_fallback(
                    current, name_text or "", nickname_map
                )
                if from_nickname:
                    pokemon_id, confidence = matches[0]
                    source = "nickname"

            # Qui finiva il fallback pHash sull'icona del menu. La sua
            # confidenza era `1 - distanza/18` e le distanze reali stavano fra
            # 16 e 24 anche sul match giusto: 0.11 nel migliore dei casi,
            # contro la soglia di 0.60 con cui la squadra viene scritta. Non
            # poteva cambiare nulla, e costava sei pHash a lettura più sei
            # rettangoli da calibrare per ogni gioco nuovo.

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
        generation: int,
        restrict_to_ids: set[int] | None = None,
        nickname_map: dict[str, int] | None = None,
    ) -> Recognition | None:
        """Nucleo condiviso: OCR del riquadro nome → miglior specie.

        `restrict_to_ids`: filtro post-query sui candidati, per limitare il
        risultato a un insieme di specie noto (es. i 6 membri della squadra
        corrente). Quando c'è, il fuzzy parte da una soglia più bassa e con
        più candidati: il dominio è piccolo e noto, quindi il miglior match
        è quasi per forza quello giusto anche con uno score assoluto basso.

        `nickname_map`: se il testo OCR corrisponde a un nickname mappato, il
        match entra in `name_matches` come se venisse dal fuzzy sui nomi.
        """
        game_area = compute_game_area(frame.width, frame.height, layout)
        name_crop = frame.crop(roi_to_pixels(name_roi, game_area).as_crop_box())

        ocr_results = self._ocr.recognize(name_crop)
        candidate_text = _pick_name_text(ocr_results)
        name_matches: list[tuple[int, float]] = []
        # Stessi tre stadi di `recognize_team`: nickname esatto, fuzzy specie,
        # fuzzy nickname.
        exact_nick = _match_nickname(candidate_text or "", nickname_map, min_similarity=1.0)
        if exact_nick is not None and _id_allowed(exact_nick[0], restrict_to_ids):
            name_matches = [exact_nick]
        if not name_matches and candidate_text:
            fuzzy_limit = 20 if restrict_to_ids else 5
            fuzzy_min = 0.35 if restrict_to_ids else 0.55
            name_matches = [
                (pokemon_id, score)
                for pokemon_id, score in _fuzzy_species(
                    self._repo,
                    candidate_text,
                    generation,
                    min_similarity=fuzzy_min,
                    limit=fuzzy_limit,
                )
                if _id_allowed(pokemon_id, restrict_to_ids)
            ]
        name_matches, _ = _apply_nickname_fallback(
            name_matches, candidate_text or "", nickname_map, restrict_to_ids
        )

        debug = {
            "ocr_text": candidate_text or "",
            "restrict_to_ids": sorted(restrict_to_ids) if restrict_to_ids else None,
        }
        return _best_match(name_matches, debug, restricted=restrict_to_ids is not None)


def _fuzzy_species(
    repo: PokemonRepository,
    text: str,
    generation: int,
    *,
    min_similarity: float,
    limit: int,
) -> list[tuple[int, float]]:
    """Fuzzy match sui nomi di specie, con un secondo giro sulle cifre OCR.

    Primo tentativo sul testo grezzo. Se non produce nulla, riprova sul testo
    con le cifre rimappate a lettere (`_OCR_DIGIT_TO_LETTER`): i nomi Pokemon
    di Gen 1-5 sono quasi sempre alfabetici, quindi una cifra nel mezzo è di
    norma un errore dell'OCR. Il secondo giro parte solo dopo il fallimento
    del primo per non danneggiare i nomi con cifra vera (Porygon2).
    """
    matches = [
        (pokemon.id, score)
        for pokemon, score in repo.find_by_fuzzy_name(
            text, generation, min_similarity=min_similarity, limit=limit
        )
    ]
    if matches:
        return matches
    normalized = text.translate(_OCR_DIGIT_TO_LETTER)
    if normalized == text:
        return []
    return [
        (pokemon.id, score)
        for pokemon, score in repo.find_by_fuzzy_name(
            normalized, generation, min_similarity=min_similarity, limit=limit
        )
    ]


def _id_allowed(pokemon_id: int, restrict_to_ids: set[int] | None) -> bool:
    """Vero se `pokemon_id` è ammesso dal filtro (nessun filtro = tutto ammesso)."""
    return restrict_to_ids is None or pokemon_id in restrict_to_ids


def _apply_nickname_fallback(
    name_matches: list[tuple[int, float]],
    text: str,
    nickname_map: dict[str, int] | None,
    restrict_to_ids: set[int] | None = None,
) -> tuple[list[tuple[int, float]], bool]:
    """Sostituisce un match di specie debole con un match nickname migliore.

    La specie resta il primo stadio: se ha prodotto un match forte (score >=
    `_NICKNAME_MIN_SIMILARITY`) vince e il nickname non viene nemmeno provato,
    così uno slot con nome di specie leggibile non può essere rubato da un
    nickname simile in mappa.

    Sotto quella soglia però non c'è un vero match da proteggere: sull'HUD di
    combattimento il fuzzy gira ristretto ai 6 della squadra con soglia 0.35,
    dove `FIAHHETTA` (nickname di Charizard) agganciava `Pidgeot` a 0.375 e
    impediva al nickname, che scora 0.78, di essere considerato.

    Ritorna `(match, sostituito_da_nickname)`.
    """
    best = max((score for _, score in name_matches), default=0.0)
    if best >= _NICKNAME_MIN_SIMILARITY:
        return name_matches, False
    nickname = _match_nickname(text, nickname_map)
    if nickname is None or nickname[1] <= best or not _id_allowed(nickname[0], restrict_to_ids):
        return name_matches, False
    return [nickname], True


def _match_nickname(
    text: str,
    nickname_map: dict[str, int] | None,
    *,
    min_similarity: float = _NICKNAME_MIN_SIMILARITY,
) -> tuple[int, float] | None:
    """Cerca `text` fra le chiavi di `nickname_map`, tollerando errori OCR.

    Ritorna `(pokemon_id, score)` del miglior match con score >=
    `min_similarity`, altrimenti `None`. Con `min_similarity=1.0` il
    comportamento degenera nel lookup esatto (ratio 1.0 = stringhe uguali),
    usato come primo stadio prima del fuzzy sui nomi di specie.

    A parita di score vince il nickname alfabeticamente minore, per rendere
    l'esito deterministico.
    """
    if not text or not nickname_map:
        return None
    needle = text.strip().upper()
    if not needle:
        return None
    best: tuple[int, float] | None = None
    for nickname, pokemon_id in sorted(nickname_map.items()):
        score = SequenceMatcher(None, needle, nickname.strip().upper()).ratio()
        if score >= min_similarity and (best is None or score > best[1]):
            best = (pokemon_id, score)
    return best


def _pick_name_text(ocr_results: list[OcrResult]) -> str | None:
    """Sceglie la stringa candidata a nome fra i risultati OCR.

    Scarta righe che sono un puro indicatore di livello (`L.33`, `Lv.5`, ...).
    Se restano più righe, ritorna la più lunga (di solito il nome è più lungo
    del livello dopo il filtro).

    Sul HUD di combattimento nome e livello stanno sulla stessa riga e il
    riconoscitore, senza il modello di detection a separarli, li restituisce
    fusi (`HEEZINGL.33`). `_strip_level_suffix` taglia la coda `L.XX` prima
    della pulizia finale.
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
    return _strip_non_alpha_tail(_strip_level_suffix(filtered[0].text))


def _strip_level_suffix(text: str) -> str:
    """Rimuove l'indicatore di livello attaccato in coda al nome.

    `HEEZINGL.33` → `HEEZING`, `FIAMHETTASL.38` → `FIAMHETTAS`. Se togliendolo
    non resta nulla il testo viene lasciato intatto: era un livello isolato,
    non un nome con la coda.
    """
    stripped = _LEVEL_SUFFIX.sub("", text.strip())
    return stripped if stripped.strip() else text


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


def _best_match(
    name_matches: list[tuple[int, float]],
    debug: dict,
    *,
    restricted: bool = False,
) -> Recognition | None:
    """Sceglie il candidato migliore e ne traduce lo score in confidenza.

    Con `restricted=True` il dominio è un piccolo insieme noto — tipicamente
    i sei della squadra — quindi il miglior match è quasi per forza quello
    giusto e la confidenza ha un pavimento: uno score basso lì dentro dice
    "l'OCR ha letto male", non "potrebbe essere un altro Pokemon".

    Senza restrizione la confidenza è lo score stesso sopra 0.75, dimezzato
    sotto: il candidato viene comunque restituito, ma con un numero che
    `ui.app` confronta con la propria soglia prima di scriverlo da qualche
    parte.
    """
    if not name_matches:
        return None
    best_id, best_score = max(name_matches, key=lambda pair: pair[1])
    if restricted:
        confidence = max(_RESTRICTED_CONFIDENCE_FLOOR, best_score)
    else:
        confidence = best_score if best_score >= _NAME_CONFIDENCE_THRESHOLD else best_score * 0.5
    return Recognition(
        pokemon_id=best_id,
        confidence=confidence,
        name_score=best_score,
        debug=debug,
    )
