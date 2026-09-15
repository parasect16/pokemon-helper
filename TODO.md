# TODO — pokemon-helper

Memoria attività in corso/da fare. Aggiornare fine sessione con stato reale.

Convenzioni:
- `[ ]` = da fare
- `[~]` = in corso / parziale
- `[!]` = bloccato o limite noto (non fixabile a breve)

## In corso / parziale

- `[x]` **F3.9 — match icona menu Pokemon: rimosso.**
  L'infra c'era tutta (schema `sprite_hashes.side='icon'`, indice Gen 1-5,
  color-key HSV sul teal del menu), ma i numeri non tornavano: confidenza
  `1 - distanza/18` contro distanze reali 16-24 anche sul match giusto, cioè
  ≤ 0.11 contro la soglia di 0.60 con cui la squadra viene scritta. Non era
  inaffidabile, era **inerte**: non poteva cambiare nulla in nessun caso.
  Tolti il fallback, le 6 ROI `slot_icons` e gli script `icon_debug.py` /
  `icon_compare.py`. Le righe `side='icon'` restano nel DB (costano solo
  disco) e `build_sprite_index.py` continua a scriverle: rifare l'indice
  costa un clone da 500 MB, non vale il risparmio.

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

- `[x]` **ROI `player_sprite`** ricalibrata misurando i pixel su cattura
  1119x734, non a occhio: arrivava a y nativa 124, dentro il box messaggi che
  comincia a 112, e partiva 30 px a sinistra dello sprite. Ora è lo slot 64x64
  in cui la Gen 3 disegna gli sprite posteriori (x 40-104, y 48-112), la
  stessa inquadratura delle reference indicizzate.
  `player_hp_bar` era stata ricalibrata nella stessa tornata ed è poi stata
  **rimossa**: nessun codice la leggeva, solo l'overlay diagnostico la
  disegnava. Era un rettangolo da tarare per ogni gioco nuovo, a vuoto.

- `[x]` **pHash sprite in battaglia: rimosso.** La cattura ha campo e cielo
  dietro il Pokemon, le reference indicizzate stanno su bianco: la specie
  corretta non entrava nei primi 3 a nessun offset di ROI (Weezing a distanza
  20-24 mentre specie sbagliate stanno a 14-16). Lato avversario la soglia 12
  non veniva mai raggiunta, quindi era solo costo. Lato giocatore era peggio:
  col match ristretto ai 6 di squadra, a OCR muta `_combine` cadeva sul ramo
  solo-sprite e ritornava la **distanza minima** con confidenza 0.70, sopra la
  soglia di applicazione — cioè evidenziava con sicurezza lo slot sbagliato.
  Tolte anche le ROI `opponent_sprite` e `player_sprite`.
  Per recuperare il canale servirebbe segmentare il soggetto dallo sfondo
  prima del hash (il fondo di battaglia è a bande di colore piatte, quindi un
  flood-fill dai bordi è plausibile), e rifare le due ROI.
  Nota: `PokemonRepository.find_pokemon_by_sprite_hash` è rimasta senza
  chiamanti di produzione. Tenuta apposta — è la query che servirebbe al
  ritorno del canale, ed è coperta dai test di `data/`.

- `[ ]` **PS del giocatore via OCR** (idea, non pianificata). Oggi nessun
  valore PS viene letto: `opponent_hp_bar` serve solo a `screen_mode` per
  riconoscere la schermata di combattimento, e la ROI `player_hp_bar` è stata
  rimossa perché non aveva nessun consumatore. Se un giorno servono i PS,
  leggere i **numeri** ("112/112") con l'OCR e non la lunghezza della barra:
  la barra dà una frazione approssimata e va tarata sui colori di ogni gioco,
  i numeri danno il valore esatto con lo stesso motore già in uso. Solo lato
  giocatore — di quelli avversari il gioco non mostra le cifre. Serve una ROI
  nuova sui numeri PS dell'HUD (y nativa 95-99 in FRLG, misurata quando
  `player_hp_bar` ci cadeva sopra per errore).

- `[~]` **Calibratore ROI visuale** (~7h stimate, 16 rettangoli da disegnare).
  Dialog con canvas su screenshot, utente disegna i rettangoli. Sblocca giochi
  non supportati senza toccare codice.
  - `[x]` **1.1 persistenza** — `vision/roi_store.py`: JSON per gioco in
    `%APPDATA%\pokemon-helper
ois\<gioco>.json`, `RoiStore` load/save/clear,
    `resolve_rois(game)` = default del repo + override utente. Lettura
    tutto-o-niente: un file rotto o con un rettangolo fuori range torna ai
    default con un avviso, perché applicarne metà darebbe ROI che non sono né
    quelle dell'utente né quelle del repo. 25 test.
  - `[x]` **1.2 chiamanti** — `ui.app` e gli otto script di debug passano da
    `resolve_rois` invece di leggere `GAME_ROIS`. In `app` il risultato è in
    cache per sessione: il poll F4 gira due volte al secondo e non deve
    rileggere il disco a ogni giro (il calibratore invaliderà la cache).
  - `[ ]` **1.3 dialog di disegno** — canvas, rubber-band, snap alla griglia
    nativa 240x160, zoom, nudge con le frecce.
  - `[ ]` **1.4 cattura per gruppo** — le ROI di battaglia si calibrano su un
    frame di battaglia, quelle del menu su un frame di menu; `classify_screen`
    dice quale delle due si sta guardando.
  - `[ ]` **1.5 read-back dal vivo** — per ogni rettangolo disegnato, cosa ci
    legge l'OCR. È la parte che ripaga: i due bug di calibrazione passati non
    erano rettangoli storti a vedersi, erano rettangoli che leggevano altro.
  - `[ ]` **1.6 salva / ripristina / esporta** — export di uno snippet Python
    per `roi.py`, così una calibrazione buona può diventare il default del
    repo invece di restare su una macchina.
  - `[ ]` **1.7 aggancio UI + docs**.
- `[ ]` **Supporto Pokemon Cristallo** (Gen 2 mGBA). Nuove ROI, layout GB/GBC
  (160×144, aspect 10:9), aggiungere `LAYOUT_MGBA_GB` in `_GAME_BY_GENERATION`.
- `[x]` **Test UI** con `pytest-qt`. Coverage `ui/` da 0 a 65%: pannelli,
  finestra, dialoghi, poller F4 e worker persistente. I widget si costruiscono
  davvero su piattaforma `offscreen`. Restano scoperti `run()` (assembla l'app
  intera) e `hotkey.py` (pynput). Un bug trovato scrivendoli: aprendo `…` su
  uno slot già assegnato la ricerca era pre-compilata ma la lista no, e un OK
  immediato riassegnava lo slot al primo Pokemon dell'elenco.
- `[x]` **Screen mode detection formale**. `vision/screen_mode.py` (ex
  `battle_detector`) ha un'unica porta d'ingresso, `classify_screen`, che
  ritorna `BATTLE` / `PARTY_MENU` / `OTHER` più il motivo per il tooltip.
  La sentinella è il pulsante `ESCI` in basso a destra dell'elenco Pokemon:
  ROI misurata per colore su due catture live di dimensioni diverse, che
  danno lo stesso rettangolo normalizzato a meno di 0.001. OCR: `ESCI` a
  0.98 sul menu, spazzatura dal box messaggi sui frame di battaglia.
  Costa un'OCR, quindi è opt-in (`ocr=`): il poll F4 gira due volte al
  secondo e si ferma al colore. L'euristica ≥3 slot resta come seconda
  linea — guarda cosa è stato letto, non un rettangolo, e fallisce per
  cause diverse.

- `[x]` **Nickname map utente** (commit 13dd606): dialog 🏷 per associare
  nickname → species, salvato in `state.json`. Team recognize usa mappa
  prima del fuzzy match.
- `[x]` **Auto-detect chrome mGBA** (`vision/chrome.py`). Il chrome si misura
  sul frame: titolo e menu bar sono righe grigie e chiare, le schermate di
  gioco sono sature. Il nero è escluso di proposito — è anche il colore delle
  bande di letterbox, e contarle sposterebbe l'area di gioco. Fallback al
  valore dichiarato nel layout quando la misura non convince (tema scuro,
  schermo bianco in transizione). Usato da `on_recognize`, `on_recognize_team`
  e `probe`.
  **Verificato sul vivo**: 52 px, identico al valore misurato a mano. La
  prima cattura però dava `None`, e ha scoperto due assunzioni sbagliate: il
  frame comincia col bordo della finestra (una riga scura, non la barra del
  titolo) e la prima riga del campo FRLG è `(231, 255, 231)`, distanza fra
  canali esattamente 24, che passava per grigia.

## Da fare — infra


- `[ ]` **Packaging Windows**: PyInstaller o `python -m
  build` + installer. Ora serve `pip install -e ".[dev,app,vision]"` in venv.

## Prossimo debug ROI (pianificato)

- `[ ]` **Verifica ROI battaglia + team menu su risoluzione emulatore
  odierna**. Utente disegnerà a colori 3 aree per capture di riferimento
  (nome/pokemon/livello), poi confronto con `ROIS_FIRERED`. Serve:
  - definire 2 colori distinti + visibili (`#FF00FF` magenta per nome,
    `#FFFF00` giallo per livello; il ciano delle icone è decaduto con il
    fallback pHash);
  - script snap che accetta un PNG annotato dall'utente ed estrae
    bounding box per colore → normalizza in coord `Roi` (0..1 su game
    area);
  - confronto ROI dedotta vs corrente, produce diff patch per `roi.py`.

## Bug noti minori

- `[ ]` `data/*.png` gitignored ma alcuni script scrivono altri file
  (`data/capture-test.png`, `data/team-menu-slot-*.png`). Se compaiono altri
  artefatti da script debug, aggiungere pattern.
- `[x]` Chiusura app durante recognize. `_RecognizeWorker.stop()` ora svuota
  la coda, rifiuta le submit successive, espone `cancelled` (controllato dai
  job di recognize e dal poll fra una fase e l'altra) e aspetta il thread con
  timeout, stampando se scade. La cattura si chiude **prima** del worker: la
  sua `close()` sblocca subito una `capture_frame` in attesa invece di
  lasciarla scadere a 3 s. Perché regga, `close()` è diventata definitiva —
  prima era indistinguibile dalla sessione che muore con l'emulatore, caso
  che riapre apposta, quindi un job in volo ne avviava una nuova uscendo.

## Note libere

- **Deps upgrade**: `rapidocr` a 3.9.2, `windows-capture` a 2.0.1 ora. Se
  aggiornano, testare recognize live.
- **Modello OCR**: RapidOCR usa PP-OCRv6_det_small + rec_small di default. Se
  serve più precisione su pixel font, provare `PP-OCRv5_server_det/rec` (più
  grandi, più lenti).
- `data/vendor/sprites/` da ~500 MB dominato da GIF animate Gen 5
  (`black-white/animated/`). Se disco stretto, sparse-checkout più selettivo
  escludendo `animated/`.
