# Pokémon Helper — Piano di progetto

Documento di handoff. Redatto in una sessione WSL, destinato a proseguire in una sessione Claude Code su Windows nativo.

## 1. Obiettivo

Tool desktop per Windows che assiste il giocatore durante una partita Pokémon in esecuzione in un emulatore, tramite un overlay sempre in primo piano.

Funzionalità richieste:

1. Riconoscimento di un Pokémon a partire dal nome o dall'immagine.
2. Squadra del giocatore sempre visibile a schermo.
3. Durante il combattimento, per la generazione specifica in uso, visualizzazione di debolezze e punti di forza della squadra rispetto al Pokémon avversario.

## 2. Decisioni già prese

| Ambito | Decisione |
|---|---|
| Sorgente immagine | Emulatore in esecuzione in una finestra Windows |
| Generazioni supportate al primo rilascio | Gen 1-5 (sprite 2D) |
| Piattaforma di esecuzione | Windows nativo (non WSL) |
| Linguaggio | Python 3.12 |

## 3. Perché Windows nativo e non WSL

Il componente di overlay e cattura schermo deve girare come processo Windows nativo. Le ragioni sono vincolanti, non preferenze:

- WSLg esegue le applicazioni grafiche Linux in una sessione RDP virtuale isolata. Una finestra Linux non può essere posizionata sempre in primo piano sopra le applicazioni Windows.
- Dal lato Linux non è accessibile né Windows Graphics Capture né DXGI Desktop Duplication. Non è quindi possibile catturare la finestra dell'emulatore.
- Non sono disponibili gli stili di finestra Windows necessari (`WS_EX_LAYERED`, `WS_EX_TRANSPARENT` per il click-through) né le hotkey globali né la gestione del DPI per-monitor.

Suddivisione del lavoro:

- **Logica pura** (dataset, tabella dei tipi, calcolo dell'efficacia, test): Python puro, eseguibile ovunque. Può essere sviluppata anche da WSL.
- **Applicazione** (overlay, cattura, OCR, hotkey): processo Windows nativo.

### Collocazione del repository

Spostare il repository su filesystem Windows, ad esempio `C:\dev\pokemon-helper`. Da WSL resta accessibile su `/mnt/c/dev/pokemon-helper`.

Da evitare l'ambiente virtuale Python su percorso `\\wsl$\...`: è lento e i binari Windows compilati non funzionano correttamente da lì.

Comandi di migrazione, da eseguire su Windows (PowerShell):

```powershell
git clone \\wsl$\<distro>\git\pokemon-helper C:\dev\pokemon-helper
cd C:\dev\pokemon-helper
py -3.12 -m venv .venv
.\.venv\Scripts\activate
```

## 4. Stack tecnico

| Componente | Scelta | Motivazione |
|---|---|---|
| Interfaccia overlay | PySide6 (Qt 6), finestra frameless con `WindowStaysOnTopHint` e `WA_TranslucentBackground` | Stesso linguaggio della logica di visione artificiale, gestione DPI matura |
| Cattura schermo | `windows-capture` (binding di Windows Graphics Capture) | Cattura per singola finestra, funziona con finestre accelerate in Direct3D e in fullscreen borderless. `mss` e le API GDI non catturano correttamente le finestre degli emulatori |
| OCR del nome | RapidOCR su ONNX Runtime | Completamente offline, veloce, non richiede l'installazione separata di Tesseract |
| Riconoscimento sprite | Perceptual hash (pHash) confrontato con un database di sprite precalcolato | Gli sprite sono asset fissi e deterministici: il confronto per hash è esatto e richiede circa un millisecondo. Una rete neurale sarebbe sovradimensionata |
| Dati Pokémon | Dump locale di PokeAPI in SQLite | Funziona offline, nessun limite di frequenza sulle richieste |

## 5. Note sui dati

### Tabelle dei tipi

Per le generazioni 1-5 servono **due** tabelle distinte, non una:

- **Gen 1**: i tipi Buio e Acciaio non esistono. Spettro non ha effetto su Psico (bug storico del gioco). Coleottero contro Veleno è superefficace. Veleno contro Coleottero è superefficace. Ghiaccio contro Fuoco è neutro.
- **Gen 2-5**: tabella unica e stabile per tutte e quattro le generazioni. Introdotti Buio e Acciaio. Acciaio resiste a Spettro e a Buio. Ghiaccio contro Fuoco diventa non molto efficace.

Il tipo Folletto arriva in Gen 6 e la resistenza di Acciaio a Spettro e Buio viene rimossa nella stessa generazione. Fuori perimetro per il primo rilascio, ma la struttura dati deve restare estendibile per generazione.

### Tipi dei Pokémon variabili per generazione

I tipi di un Pokémon non sono costanti nel tempo. Esempio: Magnemite e Magneton sono di tipo Elettro in Gen 1 e diventano Elettro/Acciaio dalla Gen 2. La chiave del dataset deve essere la coppia `(pokemon_id, generazione)`, non il solo `pokemon_id`.

### Sprite

- Servono gli sprite **frontali** (Pokémon avversario) e **posteriori** (Pokémon del giocatore).
- Gli sprite variano per generazione e talvolta per versione all'interno della stessa generazione.
- Le varianti cromatiche richiedono hash separati.
- Dalla Gen 4 esistono forme differenziate per genere per alcune specie.
- In Gen 5 gli sprite sono animati: calcolare più hash per Pokémon, uno per fotogramma campionato, e accettare la corrispondenza più vicina.

### Risoluzioni native

Le regioni di interesse vanno definite in coordinate native del gioco e riscalate in base alla dimensione effettiva della finestra dell'emulatore, che l'utente può ridimensionare liberamente.

- Game Boy e Game Boy Color: 160x144
- Game Boy Advance: 240x160
- Nintendo DS: 256x192 per schermo, due schermi

## 6. Fasi di sviluppo

L'ordine è pensato per produrre qualcosa di utilizzabile alla fase F2, senza dipendere dalla visione artificiale.

### F0 — Dataset

Costruire il dump offline: pokedex con identificativi, nomi in italiano e inglese, tipi per generazione, sprite per generazione, tabelle dei tipi per generazione. Nessuna dipendenza da Windows: sviluppabile in WSL.

Suddivisione operativa in due sotto-fasi indipendenti:

- **F0.1 — dati tabulari (fatto)**. Fonte: `veekun/pokedex` clonato in shallow mode. Costruisce `data/pokemon.sqlite` con specie, nomi IT/EN, tipi per generazione. Le eccezioni storiche di tipo che veekun non esporta in CSV (linea Magnemite in Gen 1) vivono in `TYPE_HISTORY_OVERRIDES` dentro `scripts/build_dataset.py`.
- **F0.2 — sprite + perceptual hash (fatto)**. Il repo `veekun/pokedex` **non** ship gli sprite (contiene solo CSV), quindi si è passati direttamente al clone `--filter=blob:none --sparse` di `PokeAPI/sprites` limitato a `sprites/pokemon/versions/generation-{i..v}/`. Il vendoring finale occupa circa 500 MB su disco (~250 MB sono le GIF animate di Gen 5 che al momento non vengono indicizzate). Lo script `scripts/build_sprite_index.py` calcola il pHash a 64 bit di ogni sprite front/back per i giochi principali di ciascuna generazione e popola la tabella `sprite_hashes` in `data/pokemon.sqlite`. Il repository espone `find_pokemon_by_sprite_hash(query, gen, max_distance, limit)` per il match runtime via distanza di Hamming, deduplicando la miglior corrispondenza per Pokemon. Nessuna dipendenza a runtime dai binari Windows: `[vision]` extras (`Pillow`, `imagehash`) sono cross-platform.

### F1 — Motore di efficacia (fatto)

Input: tipi dell'attaccante, tipi del difensore, generazione. Output: moltiplicatore offensivo per ciascun tipo di mossa e vulnerabilità difensive del difensore. Implementato in `pokemon_helper/engine/` con `EffectivenessEngine`, `compute_matchup` (difesa/offesa per squadra vs avversario) e `best_matchup_index`. Coverage 100% con casi limite Gen 1 + tipi variabili per generazione.

### F2 — Overlay Windows con inserimento manuale (fatto, evoluto a "companion window")

Inizialmente pensato come overlay traslucido sempre in primo piano; refactorizzato in una **companion window** con chrome nativo Windows dopo il primo giro d'uso: title bar/min/close di sistema, drag nativo, voce in taskbar, `WindowStaysOnTopHint` mantenuto. Il click-through è stato rimosso (non era utile in pratica).

Ogni slot della squadra conserva l'id del Pokemon e il livello (1-100). La generazione di riferimento è selezionabile via dropdown. Persistenza dello stato in `%APPDATA%\pokemon-helper\state.json`. Hotkey globali gestite con `pynput`:
- `Ctrl+Alt+P`: mostra/nasconde/ripristina la finestra.
- `Ctrl+Alt+R`: cattura schermo mGBA + riconoscimento avversario + Pokemon del giocatore (F3.7).
- `Ctrl+Alt+T`: cattura schermo mGBA + riconoscimento intera squadra dal menu Pokemon (F3.8).

`OpponentPanel` mostra due card affiancate (player attivo | avversario) quando entrambi i Pokemon in campo sono noti: ciascuna card ha sprite front dal Pokedex, nome, tipi e lista di efficacia difensiva (Debolezze / Resistenze / Immune, tipi con moltiplicatore 1× esclusi). Placeholder "Combattimento non in corso" quando manca l'avversario, "Player in campo sconosciuto" quando manca il player.

Il pannello espone due pulsanti sopra il selettore Gen — `⟳ Squadra` e `⚔ Avversario` — equivalenti alle hotkey. Feedback visuale su ciascun pulsante: ✓ verde per 10 s in caso di successo, ⚠ giallo (con tooltip col motivo) per 10 s in caso di fallimento. Lo slot squadra corrispondente al Pokemon in campo viene evidenziato.

### F3 — Riconoscimento (in corso, stato dettagliato)

Cattura della finestra dell'emulatore (mGBA su Rosso Fuoco come primo target), ritaglio delle regioni di interesse, OCR del nome via RapidOCR e pHash dello sprite via `imagehash`, con punteggio di confidenza combinato. Le ROI sono hardcoded per gioco in `pokemon_helper/vision/roi.py` (`GAME_ROIS['firered']`), non ancora calibrabili via UI.

Sotto-fasi:

- **F3.1 (fatto)** — Wrapper `WindowCapture` su `windows-capture` (Windows Graphics Capture API): trasforma l'API event-based in una chiamata sincrona `capture_frame()` che ritorna un `PIL.Image`.
- **F3.2 (fatto)** — Sistema ROI con coordinate normalizzate (0-1) rispetto alla risoluzione nativa del gioco, `compute_game_area` per gestire menu bar mGBA + letterbox aspect-ratio, `roi_to_pixels` per lo scaling. Default per Rosso Fuoco misurati empiricamente.
- **F3.3 (fatto)** — pHash del ritaglio sprite, con `_flatten_alpha` per neutralizzare il canale alpha e allineare capture su sfondo bianco alle reference indicizzate.
- **F3.4 (fatto)** — OCR via `rapidocr>=3.9` + `onnxruntime` (il vecchio `rapidocr-onnxruntime` non ha wheel per Py 3.14). `OcrEngine` fa lazy-init dei modelli e ora accetta `upscale` e `high_contrast` per aiutare i font pixel.
- **F3.5 (fatto)** — `Recognizer` orchestrator: OCR fuzzy match sul nome + pHash sprite; se convergono restituisce sorgente `both` con confidenza alta, altrimenti si affida al segnale più forte.
- **F3.6 (fatto)** — Wiring nell'overlay via hotkey `Ctrl+Alt+R`; il callback pynput apre una connessione SQLite dedicata (thread-safety) e marshalla il risultato al thread GUI di Qt.
- **F3.7 (fatto)** — Riconoscimento anche del Pokemon del giocatore (ROI dedicate per HUD + back sprite), evidenziazione dello slot in `TeamPanel`. Same hotkey della F3.6 riconosce entrambi i lati.
- **F3.8 (fatto)** — Riconoscimento intera squadra dal menu Pokemon con `Ctrl+Alt+T`: OCR per ciascuno dei 6 slot, fuzzy match, `_apply_team_recognition` sovrascrive `state.team` preservando gli slot con nickname sconosciuti. Test live: 5/6 Pokemon con nome default riconosciuti correttamente al primo tentativo.
- **F3.9 (in corso, best-effort)** — Fallback pHash su icona menu quando OCR nome fallisce (utile per Pokemon con nickname personalizzato). Schema `sprite_hashes.side` esteso ad accettare `icon`, indice popolato da `PokeAPI/sprites/versions/generation-{roman}/icons/`. Preprocessing HSV color-key rimuove il pattern teal del menu FRLG prima del hash. Al momento le distanze restano alte (≥18-24 anche per il match corretto): il match icon non è affidabile e va valutato se investire in template matching per game.
- **F3.10 (risolto)** — Detection del livello `L.XX` sui font pixel FRLG. La causa non era il modello OCR ma la scala: mGBA rende 240×160 dentro una finestra qualsiasi (1023×682 = 4.26x, non un multiplo intero), quindi ogni pixel del font diventa 4 o 5 pixel schermo e i bordi sfumano in grigio. Sulla stringa intera RapidOCR tirava a indovinare — stesso crop, `28` / `L.30` / `38` al variare di pochi pixel di ROI. `vision/level_reader.py` scompone il problema: binarizza scegliendo la polarità in base a quale classe è minoritaria, segmenta le colonne di inchiostro contigue (il font è a larghezza fissa, le cifre non si toccano mai), e riconosce **una cifra alla volta** ingrandita e con margine bianco attorno. Il margine è l'ingrediente decisivo: senza, le stesse cifre uscivano a confidenza 0.26-0.55 e con valori sbagliati; con, tutte a 1.00. Nessun atlante di glifi necessario. Un Pokemon con alterazione di stato non mostra il livello (il gioco disegna il badge al suo posto): la segmentazione trova lettere, nessuna cifra passa e il livello resta ignoto, che `_apply_team_recognition` già gestisce preservando il valore precedente.
- **F3.11 (fatto)** — Il player attivo in campo può essere solo uno dei 6 membri della squadra: `Recognizer.recognize_player` accetta `restrict_to_ids` per filtrare i candidati fuzzy + pHash a quell'insieme, con soglie più permissive quando ristretto. L'app passa sempre il set derivato da `state.team`.
- **F3.12 (fatto)** — Guardia anti-sovrascrittura sul recognize squadra: se meno di 3/6 slot hanno OCR text di lunghezza ≥ 3, la squadra corrente **non** viene sovrascritta (siamo probabilmente fuori dalla schermata elenco Pokemon). Il pulsante ⟳ Squadra riceve un flash ⚠ giallo per 10 s con il motivo in tooltip.
- **F3.13 (fatto)** — Riprogettazione grafica di `OpponentPanel`: due card affiancate con sprite Pokedex, tipi e tabella efficacia colorata + pulsanti reload in header. Renderer badge condivisi in `ui.types_meta` (`render_type_badge`, `render_type_badges`, `text_color_for` per contrasto testo automatico).
- **F3.14 (fatto)** — Calibrazione ROI da PNG annotato: `scripts/extract_roi_from_annotated.py` estrae bbox per colore (magenta=nome, ciano=icona, giallo=livello) dal PNG di riferimento dell'utente, con auto-detect del game area basato sul contenuto non-black/non-white. `team_menu_debug.py` unificato ora dumpa overlay tricolore + OCR per slot + verdetto `recognize_team` per iterazione veloce. Fix collaterale del `LAYOUT_MGBA_GBA.menu_offset_top` da 30 a 52 px (chrome mGBA reale = title bar 30 + menu 22, non solo menu 30): tutte le ROI erano shiftate ~22 px verso l'alto → nomi/livelli tagliati.
- **F3.15 (fatto)** — Guardia anti-falso-positivo sul recognize avversario: nuovo `vision.battle_detector.is_battle_screen` ispeziona la ROI `opponent_hp_bar` e conta pixel HP-colored (verde/giallo/rosso). Sotto MIN_HP_PIXELS=20 la schermata non è considerata battaglia e `on_recognize` aborta prima di lanciare OCR+pHash. Feedback ⚠ giallo sul pulsante ⚔ Avversario. Analog al guard team menu (heuristica `_team_snapshot_looks_like_menu` rinforzata: rifiuta se lo stesso pokemon_id compare in ≥2 slot).
- **F3.16 (fatto)** — Mappa nickname utente in `AppState.nicknames` (dict OCR text → pokemon_id). `Recognizer.recognize_team` accetta `nickname_map` opzionale: se il testo OCR uppercased è in mappa, override immediato con confidenza 1.0 e `source="nickname"`. UI dialog `NicknameDialog` accessibile dal pulsante 🏷 nella toolbar di `TeamPanel`: tabella nickname | species con aggiungi/rimuovi. Persistito in `state.json`. Risolve nickname custom che il fuzzy match non riconosce (es. "FIAMMETTA" → Charizard).
- **F3.17 (fatto)** — OCR senza modello di detection. Ogni crop passato a RapidOCR viene da una ROI già stretta sul testo, quindi far localizzare di nuovo il testo era lavoro sprecato *e* inaffidabile: sulla schermata squadra il detector non trovava nulla per `GLOOM`, il nome più corto, e lo slot veniva azzerato in silenzio. `OcrEngine.recognize` ora ha `detect=False` di default, con la pipeline completa come fallback se il solo riconoscitore non produce nulla (copre la ROI disallineata). Misurato sugli stessi sei crop: 4723 ms → 51 ms (93x) e più accurato (`FHERGCITE` 0.56 → `EHEGGCUTE` 0.89). Nota: RapidOCR ricorda i flag `use_det`/`use_cls` tra una chiamata e l'altra, quindi vanno passati espliciti ogni volta.
- **F3.18 (fatto)** — Mappa nickname anche sul player e ROI di combattimento riproiettate. Il fuzzy sui nickname sostituisce il lookup esatto (l'utente non può digitare il misread dell'OCR) ed è consultato anche da `recognize_player`, perché l'HUD di battaglia mostra il nickname e non la specie. Le ROI battaglia erano state calibrate col chrome a 30 px invece di 52: le coordinate normalizzate avevano assorbito l'errore e dopo il fix ogni box era ~20 px troppo in basso — `opponent_name`, alto 38 px, tagliava il nome e leggeva la barra PS. Riproiettate sulla game area vera, l'OCR passa da `AECFAT"S..` (0.33) a `WEEZINGL.33` (1.00).
- **F3.19 (fatto)** — Lettura del livello cifra per cifra, vedi F3.10.


### F4 — Rilevamento automatico del combattimento (fatto)

Il pannello si aggiorna da solo, senza premere hotkey. `vision/battle_watcher.py` tiene la memoria fra un frame e l'altro e traduce le osservazioni in transizioni — `ENTERED`, `LEFT`, `COMBATANTS_CHANGED` — mentre `ui.app._BattlePoller` fa girare il ciclo. Nessun template matching: `is_battle_screen` (F3.15) bastava già.

Sotto-fasi:

- **F4.1 (fatto)** — Polling periodico ogni 1500 ms. Il `QTimer` vive sul thread GUI ma non cattura: accoda un job al `_RecognizeWorker` esistente, perché `windows-capture` va usata sempre dallo stesso thread con l'apartment COM inizializzato. Effetto collaterale utile: i poll si serializzano con i riconoscimenti manuali, quindi due catture non si sovrappongono. Un poll più lento dell'intervallo salta il tick successivo invece di accumulare coda.
- **F4.2 (fatto)** — `ENTERED` e `COMBATANTS_CHANGED` invocano `on_recognize`. L'isteresi a 2 osservazioni concordi evita i rimbalzi sulle dissolvenze e dà tempo agli sprite di finire di comparire prima che parta l'OCR.
- **F4.3 (fatto)** — `LEFT` svuota il pannello e toglie l'evidenziazione dello slot attivo.
- **F4.4 (fatto)** — Interruttore "Auto" in toolbar, spento di default e persistito in `state.json`. Mentre è attivo l'app cattura la finestra dell'emulatore, e quella resta una scelta dell'utente. Riattivandolo a lotta in corso il watcher si resetta, così viene comunque emesso `ENTERED`.
- **F4.5 (fatto)** — Firma testuale per rilevare i cambi di Pokemon in campo. La prima versione confrontava il pHash dei riquadri nome: falsi positivi in continuazione, perché fra una cattura e l'altra il frame trasla di un paio di pixel e il pHash è invariante alla scala ma non alla traslazione (4 falsi positivi in 20 s a gioco fermo). Ora la firma è il testo OCR dei due riquadri nome, confrontati per similarità lato per lato: stesso nome riletto 0.91-0.96 anche con un carattere sbagliato, Pokemon diversi 0.40-0.46, soglia a 0.75. Un semplice aumento di livello sta a 0.92 e correttamente non conta come cambio. Copre entrambi i lati perché il cambio dell'avversario si vedrebbe comunque (il suo HUD sparisce durante l'animazione, quindi `LEFT` + `ENTERED`), mentre un cambio del giocatore non muove nulla nello stato di battaglia.
- **F4.6 (fatto)** — Terza osservazione `None` = "non lo so", che mantiene lo stato. La produce `is_party_menu_screen`, che riconosce l'elenco Pokemon dallo sfondo teal (47% dell'area di gioco contro 0.1% in combattimento). Senza, aprire l'elenco per cambiare Pokemon svuotava il pannello a metà lotta.

## 7. Punti aperti

- Emulatori da supportare per primi. Candidati: mGBA per Game Boy, Game Boy Color e Game Boy Advance; melonDS o DeSmuME per Nintendo DS. **Attuale**: solo mGBA con Rosso Fuoco (Gen 3 GBA).
- Lingua del gioco per l'OCR: la lingua dell'interfaccia del gioco determina il dizionario di nomi da usare per il confronto. **Attuale**: fuzzy match su nomi IT + EN a prescindere dalla lingua del gioco.
- Gestione delle abilità che modificano l'efficacia dei tipi, ad esempio Levitazione o Assorbivolt. Ora è il punto aperto più rilevante per la correttezza: il calcolo guarda solo i tipi, quindi su un Gengar con Levitazione il tool consiglia una mossa di Terra e sbaglia. È l'unico caso in cui la risposta è errata anziché soltanto incompleta.
- **Match icona menu**: pHash/dhash non raggiungono distanze basse anche con color-key HSV. Alternative: template matching su icone note, o accettare che il fallback icona resti un weak signal.
- **Calibrazione ROI visuale**: le ROI attuali sono hardcoded per FRLG a scala mGBA con menu bar visibile. Un calibratore drag-a-rettangolo permetterebbe di supportare altri giochi/scaling con meno codice. Parzialmente coperto da `scripts/extract_roi_from_annotated.py` (offline via PNG annotato).
- **Chrome mGBA hardcoded**: `LAYOUT_MGBA_GBA.menu_offset_top = 52` misurato sulla macchina utente (Win10 Pro DPI 100%). Su altre DPI/Windows 11 il valore può differire. Da auto-detect via scansione della prima riga teal del frame catturato. Nota: è l'unica costante in pixel assoluti del sistema ROI — tutto il resto è normalizzato e quindi indipendente dalla dimensione della finestra. Quando è cambiata da 30 a 52 ha sfasato di ~20 px tutte le ROI battaglia, calibrate prima del fix; sono state riproiettate sulla game area vera (commit `1f85b1e`).
