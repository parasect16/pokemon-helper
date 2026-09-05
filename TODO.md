# TODO — pokemon-helper

Memoria attività in corso/da fare. Aggiornare fine sessione con stato reale.

Convenzioni:
- `[ ]` = da fare
- `[~]` = in corso / parziale
- `[!]` = bloccato o limite noto (non fixabile a breve)

## In corso / parziale

- `[~]` **F3.9 — match icona menu Pokemon**
  Infra completa: schema `sprite_hashes.side='icon'`, indice Gen 1-5 da
  `PokeAPI/sprites/versions/generation-{roman}/icons`, preprocessing HSV
  color-key rimuove bg teal menu FRLG, fallback solo se OCR nome fallisce.
  **Limite**: distanze pHash/dhash ≥ 16-24 anche su match corretto →
  inaffidabile. Testato capture live FRLG.
  Prossimo: template matching diretto su icone note (per game) o pre-crop
  più aggressivo riquadro icona (rimuovere anche Pokeball sinistra).

- `[~]` **F3.10 — detection livello `L.XX` team menu**
  ROI dedicate + preprocessing `high_contrast=True` + upscale x4 su
  RapidOCR, più regex fallback `_extract_level` che gestisce `137` → 37.
  **Limite**: solo alcuni slot (Dugtrio nel test) danno il numero. Font
  pixel FRLG troppo piccolo/particolare per RapidOCR.
  Fallback: preserva livello precedente per slot, editabile via pulsante `…`.
  Prossimo: template matching per digit (10 template per game, match a
  scorrimento su ROI).

## Da fare — F4 (prossima fase)

- `[ ]` **F4.1** Template matching barra HP avversario → rileva stato "in
  combattimento". Frame refresh periodico (es. ogni 500 ms su thread worker,
  riusa `_RecognizeWorker`).
- `[ ]` **F4.2** Auto-invoke `recognize_opponent` quando template match
  detecta transizione → "in battaglia".
- `[ ]` **F4.3** Auto-clear opponent quando template match detecta
  transizione → "fuori battaglia".

## Da fare — polish / feature

- `[ ]` **Calibratore ROI visuale** (~4-6h). Dialog con canvas su screenshot,
  utente disegna rettangoli per (nome opp, sprite opp, HUD player, ecc.).
  Sblocca giochi non supportati senza toccare codice.
- `[ ]` **Supporto Pokemon Cristallo** (Gen 2 mGBA). Nuove ROI, layout GB/GBC
  (160×144, aspect 10:9), aggiungere `LAYOUT_MGBA_GB` in `_GAME_BY_GENERATION`.
- `[ ]` **Test UI** con `pytest-qt`. Coverage ora 0 su `ui/`. Focus
  `TeamPanel.replace_team`, `OpponentPanel.set_active_player`,
  `state.StateStore` (già coperto).
- `[ ]` **Screen mode detection formale**: euristica attuale (≥3 slot
  OCR-leggibili) può fallire. Meglio: OCR di elemento unico del menu (es.
  pulsante "ESCI" bottom-right) come sentinella.
- `[ ]` **Ability-based type modifiers** (Levitazione = immune a Ground,
  Assorbivolt = immune a Electric, ecc.). Estende `EffectivenessEngine` con
  secondo layer.
- `[x]` **Nickname map utente** (commit 13dd606): dialog 🏷 per associare
  nickname → species, salvato in `state.json`. Team recognize usa mappa
  prima del fuzzy match.
- `[ ]` **Auto-detect chrome mGBA**: `LAYOUT_MGBA_GBA.menu_offset_top=52`
  hardcoded per Win10 Pro DPI 100%. Su Win11 o DPI diverse cambia. Fix:
  scan prima riga teal (bg gioco) sul frame catturato per calcolare offset
  dinamicamente. ~1h.

## Da fare — infra

- `[ ]` **CI GitHub Actions**: workflow lancia `pytest --cov` + `ruff check`
  su push. Coverage floor 90% già in `pyproject.toml`, farlo failare CI.
- `[ ]` **Packaging Windows**: PyInstaller o `python -m
  build` + installer. Ora serve `pip install -e ".[dev,app,vision]"` in venv.

## Prossimo debug ROI (pianificato)

- `[ ]` **Verifica ROI battaglia + team menu su risoluzione emulatore
  odierna**. Utente disegnerà a colori 3 aree per capture di riferimento
  (nome/pokemon/livello), poi confronto con `ROIS_FIRERED`. Serve:
  - definire 3 colori distinti + visibili (proposta: `#FF00FF` magenta
    per nome, `#00FFFF` ciano per sprite/icona, `#FFFF00` giallo per
    livello);
  - script snap che accetta un PNG annotato dall'utente ed estrae
    bounding box per colore → normalizza in coord `Roi` (0..1 su game
    area);
  - confronto ROI dedotta vs corrente, produce diff patch per `roi.py`.

## Bug noti minori

- `[ ]` `data/*.png` gitignored ma alcuni script scrivono altri file
  (`data/capture-test.png`, `data/team-menu-slot-*.png`). Se compaiono altri
  artefatti da script debug, aggiungere pattern.
- `[ ]` Chiusura app durante recognize (raro): worker persistente può non
  terminare pulito. `_HotkeyGroup.stop` chiama `worker.stop()` ma job in corso
  continua fino a fine. Aggiungere check cancel/timeout.

## Note libere

- **Deps upgrade**: `rapidocr` a 3.9.2, `windows-capture` a 2.0.1 ora. Se
  aggiornano, testare recognize live.
- **Modello OCR**: RapidOCR usa PP-OCRv6_det_small + rec_small di default. Se
  serve più precisione su pixel font, provare `PP-OCRv5_server_det/rec` (più
  grandi, più lenti).
- `data/vendor/sprites/` da ~500 MB dominato da GIF animate Gen 5
  (`black-white/animated/`). Se disco stretto, sparse-checkout più selettivo
  escludendo `animated/`.
