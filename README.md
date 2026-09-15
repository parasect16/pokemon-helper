# pokemon-helper

Assistente da scrivania per le lotte Pokemon su emulatore, per Windows. Tiene
accanto all'emulatore una finestra sempre in primo piano che dice **quali tipi
sono efficaci** contro il Pokemon che hai davanti, tenendo conto anche delle
abilità che cambiano le debolezze (contro un Gengar con Levitazione, Terra è
`0×` e non `2×`).

La squadra si può scrivere a mano, oppure farla leggere all'app dallo schermo
dell'emulatore.

> **Beta.** Tutto ciò che è calcolo — tipi, efficacia, abilità — vale per le
> generazioni 1-5. Il **riconoscimento dallo schermo** è invece tarato su una
> sola combinazione: **mGBA** con **Pokemon Rosso Fuoco in italiano**. Con altri
> giochi o altri emulatori l'app parte lo stesso e la squadra si compila a mano;
> per farla leggere davvero serve ricalibrare (c'è un pulsante apposta, vedi
> [Se qualcosa non funziona](#se-qualcosa-non-funziona)).

---

## Cosa fa

- **Squadra e efficacia** — sei slot con nome e livello, generazione
  selezionabile, e per il Pokemon avversario la tabella di debolezze,
  resistenze e immunità.
- **Riconosce l'avversario** (`Ctrl+Alt+R`) leggendo il nome dalla schermata di
  combattimento, e in parallelo il tuo Pokemon in campo.
- **Riconosce la squadra** (`Ctrl+Alt+T`) dalla schermata dell'elenco Pokemon:
  sei nomi e sei livelli in un colpo solo.
- **Si aggiorna da sola** (casella `Auto`, spenta di default): segue l'inizio
  della lotta, la fine, e i cambi di Pokemon da entrambe le parti.
- **Nickname** — se hai rinominato i tuoi Pokemon, li associ alla specie una
  volta e l'app li riconosce (pulsante `🏷`).
- **Calibratore** — se le aree di lettura non sono allineate alla tua finestra,
  le ridisegni col mouse invece di modificare il codice (pulsante `▣`).

## Cosa serve

| | |
|---|---|
| **Windows 10 o 11** | nativo, non WSL: l'app usa finestre, cattura schermo e hotkey di Windows |
| **Python 3.14** | da [python.org](https://www.python.org/downloads/), spuntando *Add Python to PATH* |
| **Git** | serve **solo** a scaricare i dati dei Pokemon, una volta sola |
| **mGBA** | solo se vuoi il riconoscimento dallo schermo |

Spazio su disco, per farsi un'idea prima di cominciare: **~1,2 GB** di
librerie Python (Qt e i modelli OCR pesano), **~45 MB** di dati dei Pokemon, e
altri **~500 MB** solo se vuoi anche le immagini (passo opzionale, vedi sotto).

## Installazione

### 1. Prendi i file

Se hai Git:

```powershell
git clone -b beta https://github.com/parasect16/pokemon-helper.git
cd pokemon-helper
```

Altrimenti dalla pagina del progetto scegli il ramo **`beta`** dal menu a
tendina in alto a sinistra (il pulsante che di solito dice `main`), poi
**Code → Download ZIP**; estrai la cartella e aprila con PowerShell (tasto
destro dentro la cartella → *Apri nel terminale*).

> Il ramo `beta` è quello con le novità descritte qui. `main` è più indietro:
> se scarichi lo ZIP senza cambiare ramo, non trovi né il calibratore né il
> resto.

### 2. Prepara l'ambiente

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\activate
pip install -e ".[dev,app,vision]"
```

Il prompt deve mostrare `(.venv)` all'inizio della riga: significa che stai
usando l'ambiente appena creato. Se chiudi il terminale, la volta dopo ridai
solo `.\.venv\Scripts\activate`.

### 3. Scarica i dati dei Pokemon

```powershell
python scripts/build_dataset.py
```

Scarica il dump di [veekun/pokedex](https://github.com/veekun/pokedex) (~15 MB
compressi, ~41 MB su disco) e ne ricava `data/pokemon.sqlite`: specie, tipi per
generazione, abilità. Senza questo file l'app non parte.

**Passo opzionale** — le immagini dei Pokemon nel pannello:

```powershell
python scripts/build_sprite_index.py
```

Scarica gli sprite da [PokeAPI/sprites](https://github.com/PokeAPI/sprites), ed
è il pezzo grosso: **~500 MB**. Se lo salti l'app funziona identica, tipi e
riconoscimento compresi: al posto delle immagini vedrai la scritta
*(sprite mancante)*.

> Se un giorno rilanci `build_dataset.py`, rilancia **anche**
> `build_sprite_index.py`: il primo ricostruisce il database da zero e porta
> via anche le immagini indicizzate.

### 4. Avvia

```powershell
python -m pokemon_helper
```

## Come si usa

| Comando | Cosa fa |
|---|---|
| `Ctrl+Alt+P` | mostra / nasconde la finestra |
| `Ctrl+Alt+R` — pulsante `⚔ Avversario` | legge l'avversario dalla schermata di combattimento |
| `Ctrl+Alt+T` — pulsante `⟳ Squadra` | legge i sei Pokemon dalla schermata dell'elenco |
| casella `Auto` | tiene d'occhio l'emulatore e aggiorna da sola (cattura la finestra due volte al secondo finché è attiva) |
| `🏷` | associa i tuoi nickname alle specie |
| `▣` | calibra le aree di lettura sulla tua finestra |
| `…` su uno slot | scegli il Pokemon a mano |

I pulsanti di lettura danno un riscontro: **✓ verde** se ha funzionato,
**⚠ giallo** se no, con il motivo nel tooltip (passaci sopra il mouse).

## Se qualcosa non funziona

**«ERROR: dataset non trovato»** all'avvio — manca il passo 3, lancia
`python scripts/build_dataset.py`.

**Il riconoscimento dice «cattura fallita»** — mGBA dev'essere aperto, con una
finestra visibile e non ridotta a icona. L'app cerca una finestra il cui titolo
contenga `mGBA`.

**Dice «schermata combattimento non rilevata»** o **«schermata Pokemon non
rilevata»** — sei su una schermata diversa da quella che quel pulsante si
aspetta, oppure le aree di lettura non sono allineate alla tua finestra.

**Legge il Pokemon sbagliato, o non legge niente** — apri il calibratore (`▣`).
Mostra la finestra dell'emulatore con sopra i rettangoli da cui l'app legge:
selezioni quello storto, lo ridisegni col mouse e **sotto vedi subito cosa ci
legge dentro** (`testo: "WEEZING" a 1.00`). Le frecce spostano di un pixel del
gioco, Shift+frecce ridimensionano. Alla chiusura la calibrazione viene salvata
e vale da subito.

**Il livello di un Pokemon non viene letto** — succede quando è avvelenato,
paralizzato o addormentato: il gioco disegna il badge di stato al posto del
livello. L'app tiene il valore precedente; puoi correggerlo a mano con `…`.

## Dove finiscono i tuoi dati

Tutto sotto `%APPDATA%\pokemon-helper\`:

- `state.json` — squadra, generazione, posizione della finestra, nickname;
- `rois\<gioco>.json` — la calibrazione, se l'hai fatta. Cancellarlo riporta ai
  valori di fabbrica.

Niente di tutto questo lascia il tuo computer: l'app non fa richieste di rete.
Gli unici scaricamenti sono quelli dei due script dei dati, che lanci tu; i
modelli usati per leggere il testo arrivano già dentro le librerie installate
al passo 2.

## Per chi vuole metterci mano

```powershell
pytest -q                    # suite completa
pytest --cov                 # con la soglia di copertura
ruff check .                 # lint
ruff format .                # formattazione
pre-commit install           # una volta sola: attiva i controlli pre-commit
```

Struttura:

```
src/pokemon_helper/
  engine/    efficacia dei tipi e abilità
  data/      database SQLite e modelli di dominio
  vision/    cattura schermo, OCR, calibrazione delle aree di lettura
  ui/        finestra Qt, hotkey, stato persistente
scripts/     costruzione del dataset e strumenti diagnostici
tests/       pytest
```

Documenti: [`PLAN.md`](PLAN.md) per obiettivi e decisioni,
[`HANDOFF.md`](HANDOFF.md) per lo stato attuale nel dettaglio,
[`TODO.md`](TODO.md) per quel che manca, [`CLAUDE.md`](CLAUDE.md) per le
convenzioni del repo.
