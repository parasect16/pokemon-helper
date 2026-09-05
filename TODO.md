# TODO — pokemon-helper

Memoria intermedia delle attività in corso o da fare. Aggiornare a fine
sessione con lo stato reale.

Convenzioni:
- `[ ]` = da fare
- `[~]` = in corso / parziale
- `[!]` = bloccato o limitazione nota (non fixabile a breve)

## In corso / parziale

- `[~]` **F3.9 — match icona menu Pokemon**
  Infrastruttura completa: schema `sprite_hashes.side='icon'`, indice
  Gen 1-5 popolato da `PokeAPI/sprites/versions/generation-{roman}/icons`,
  preprocessing HSV color-key per rimuovere il bg teal del menu FRLG,
  fallback usato solo se OCR nome fallisce.
  **Limite**: distanze pHash/dhash restano ≥ 16-24 anche per il match
  corretto → non affidabile. Testato con capture live FRLG.
  Prossimo tentativo: template matching diretto sulle icone note (per
  game) o pre-crop più aggressivo del riquadro icona (rimuovere anche
  la Pokeball a sinistra).

- `[~]` **F3.10 — detection livello `L.XX` team menu**
  ROI dedicate + preprocessing `high_contrast=True` + upscale x4 su
  RapidOCR, più regex fallback `_extract_level` che gestisce `137` → 37.
  **Limite**: solo alcuni slot (Dugtrio nel test) restituiscono il
  numero. Font pixel FRLG troppo piccolo/particolare per RapidOCR.
  Fallback attuale: preserva livello precedente per lo slot, editabile
  via pulsante `…`.
  Prossimo tentativo: template matching per digit (10 template per game,
  match a scorrimento su ROI).

## Da fare — F4 (prossima fase)

- `[ ]` **F4.1** Template matching sulla barra HP dell'avversario per
  rilevare lo stato "in combattimento". Frame refresh periodico (es.
  ogni 500 ms su thread worker, riusa `_RecognizeWorker`).
- `[ ]` **F4.2** Auto-invoke di `recognize_opponent` quando il
  template match detecta transizione verso "in battaglia".
- `[ ]` **F4.3** Auto-clear opponent quando il template match detecta
  transizione verso "fuori battaglia".

## Da fare — polish / feature

- `[ ]` **Calibratore ROI visuale** (~4-6h). Dialog con canvas su
  screenshot, l'utente disegna rettangoli per (nome opp, sprite opp,
  HUD player, ecc.). Sblocca giochi non ancora supportati senza toccare
  il codice.
- `[ ]` **Supporto Pokemon Cristallo** (Gen 2 mGBA). Nuove ROI, layout
  GB/GBC (160×144, aspect 10:9), aggiungere `LAYOUT_MGBA_GB` in
  `_GAME_BY_GENERATION`.
- `[ ]` **Test UI** con `pytest-qt`. Coverage attualmente 0 su `ui/`.
  Focus su `TeamPanel.replace_team`, `OpponentPanel.set_active_player`,
  `state.StateStore` (già coperto).
- `[ ]` **Screen mode detection formale**: heuristica attuale (≥3 slot
  OCR-leggibili) potrebbe fallire. Migliore: OCR di un elemento unico
  del menu (es. "ESCI" pulsante bottom-right) come sentinella.
- `[ ]` **Ability-based type modifiers** (Levitazione = immune a
  Ground, Assorbivolt = immune a Electric, ecc.). Extends
  `EffectivenessEngine` con un secondo layer.
- `[ ]` **Nickname map utente**: dialog per associare manualmente
  nickname → species, salvato in `state.json`. Il team recognize
  userebbe questa mappa quando OCR legge un nickname noto.

## Da fare — infra

- `[ ]` **CI GitHub Actions**: workflow che lancia `pytest --cov` +
  `ruff check` su push. Coverage floor 90% già configurato in
  `pyproject.toml`, farlo failare CI.
- `[ ]` **Packaging Windows**: PyInstaller o `python -m
  build` + installer. Attualmente serve `pip install -e ".[dev,app,vision]"`
  in un venv.

## Bug noti minori

- `[ ]` `data/*.png` gitignored ma alcuni script scrivono altri file
  (`data/capture-test.png`, `data/team-menu-slot-*.png`). Se compaiono
  altri artefatti dagli script debug, aggiungere pattern.
- `[ ]` Chiusura app durante recognize (raro): il worker persistente
  potrebbe non terminare pulitamente. `_HotkeyGroup.stop` chiama
  `worker.stop()` ma il job in corso continua finché non finisce.
  Aggiungere un check di cancel/timeout.

## Note libere

- **Deps upgrade**: `rapidocr` è a 3.9.2 e `windows-capture` a 2.0.1
  al momento. Se aggiornano, testare recognize live.
- **Modello OCR**: RapidOCR usa PP-OCRv6_det_small + rec_small di
  default. Se serve maggior precisione sui pixel font, potrebbe valere
  la pena provare `PP-OCRv5_server_det/rec` (più grandi, più lenti).
- Il `data/vendor/sprites/` da ~500 MB è dominato dalle GIF animate di
  Gen 5 (`black-white/animated/`). Se disco stretto, si può fare
  sparse-checkout più selettivo escludendo `animated/`.
