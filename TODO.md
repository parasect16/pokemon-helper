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

- `[x]` **F3.10 — detection livello `L.XX` team menu** (commit `ebc7a58`).
  Risolto senza template matching. `vision/level_reader.py` binarizza,
  segmenta le colonne di inchiostro (una per cifra: font a larghezza fissa,
  cifre mai attaccate) e legge **una cifra alla volta** ingrandita e con
  margine bianco attorno. Il margine è ciò che ha risolto: senza, confidenza
  0.26-0.55 e valori sbagliati; con, 1.00 su tutte le cifre.
  La causa non era il modello OCR ma la scala non intera di mGBA (4.26x),
  che sfuma i bordi del font pixel in grigio.
  Vincolo di gioco: con un'alterazione di stato il livello **non è
  visualizzato** (badge di stato al suo posto) — `read_level` ritorna `None`
  e lo slot conserva il livello precedente.

## Fatto — F4

- `[x]` **F4 completa** (commit `265a4d1`, `00ec1b7`, `bb6c875`). Interruttore
  "Auto" in toolbar, spento di default. `BattleWatcher` + `_BattlePoller`,
  poll ogni 1500 ms sul worker esistente. Nessun template matching servito:
  `is_battle_screen` bastava. Dettaglio delle sotto-fasi in `PLAN.md` §6.
  Verificato sul vivo: ingresso, uscita, cambio Pokemon da entrambi i lati,
  elenco Pokemon aperto a metà lotta.

- `[x]` **Sessione di cattura persistente** (commit `9835e35`). Il bordo
  disegnato da Windows è fisso invece di lampeggiare a ogni poll. Il callback
  copia il buffer solo su richiesta: copiarli tutti sarebbe stato ~490 MB/s
  di memcpy a 150 fps. Cattura da ~90 ms a ~9 ms, poll F4 completo ~45 ms,
  intervallo riportato a 750 ms. La sessione si riavvia da sola quando
  l'emulatore viene chiuso e riaperto — verificato sul vivo.

- `[x]` **Abilità che modificano l'efficacia** (commit `62795e1`, `c8f7635`,
  `dfdd893`). Tabelle `abilities` e `pokemon_abilities`, layer
  `engine/abilities.py`, selettore e tooltip sulle card. Candidato unico
  applicato in automatico, ambiguità segnalata solo se cambia il verdetto.

- `[x]` **Coverage gate** (commit `6c2357c`). `engine/` e `data/` al 100%.
  Il progetto non ha CI e non ne avrà, quindi il floor è applicato dall'hook
  pre-commit `pytest --cov`: la suite gira in meno di un secondo, quindi il
  costo per commit è trascurabile. Un floor in un file di config non applica
  nulla da solo — è già sceso a 84.79% una volta senza che nessuno se ne
  accorgesse.

## Da fare — polish / feature

- `[ ]` **ROI `player_sprite` e `player_hp_bar` ancora storte**. La
  riproiezione di `1f85b1e` ha corretto la componente chrome, ma la
  calibrazione originale di queste due era sbagliata di suo: nell'overlay
  `player_sprite` taglia la testa dello sprite e include il box messaggi,
  `player_hp_bar` cade sotto la barra verde sopra i numeri PS. Nessun codice
  usa `player_hp_bar` oggi (solo `roi_debug.py` la disegna), quindi è
  innocua; `player_sprite` degrada solo il canale pHash, che in battaglia è
  già inutilizzabile (voce sotto).

- `[!]` **pHash sprite inutilizzabile in battaglia**. La cattura ha campo e
  cielo dietro il Pokemon, le reference indicizzate stanno su bianco: la
  specie corretta non entra nei primi 3 a nessun offset di ROI (Weezing a
  distanza 20-24 mentre specie sbagliate stanno a 14-16). Il verdetto regge
  interamente sul nome. Per recuperare il canale servirebbe segmentare il
  soggetto dallo sfondo prima del hash (il fondo di battaglia è a bande di
  colore piatte, quindi un flood-fill dai bordi è plausibile).

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

- `[x]` **Nickname map utente** (commit 13dd606): dialog 🏷 per associare
  nickname → species, salvato in `state.json`. Team recognize usa mappa
  prima del fuzzy match.
- `[ ]` **Auto-detect chrome mGBA**: `LAYOUT_MGBA_GBA.menu_offset_top=52`
  hardcoded per Win10 Pro DPI 100%. Su Win11 o DPI diverse cambia. Fix:
  scan prima riga teal (bg gioco) sul frame catturato per calcolare offset
  dinamicamente. ~1h.

## Da fare — infra


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
