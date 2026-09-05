# CLAUDE.md — istruzioni per Claude su questo repo

Questo file descrive le convenzioni operative del progetto `pokemon-helper`.
Vale insieme a [`PLAN.md`](PLAN.md), che invece definisce obiettivi e roadmap.

## Linguaggio

- **Python 3.14** (pin in `.python-version`, `requires-python = ">=3.14"`).
- **Codice, identificatori, messaggi di log**: inglese.
- **Commenti e docstring**: italiano.
- **Documentazione (`PLAN.md`, `README.md`, questo file)**: italiano.
- **Interazione in chat**: italiano.

## Layout del pacchetto

Layout a sottopacchetti sotto `src/pokemon_helper/`:

```
src/pokemon_helper/
  engine/     motore di efficacia, calcoli sui tipi, logica di combattimento
  data/       accesso al dataset SQLite, modelli dominio (Pokemon, Type, Sprite)
  vision/     cattura schermo, OCR, perceptual hash
  ui/         overlay PySide6, hotkey globali, gestione DPI
  __main__.py entry-point CLI
```

Ogni sottopacchetto ha il proprio `__init__.py` e i propri test in `tests/<subpackage>/`.

## Commit

**Conventional Commits** con scope tra parentesi. Formato:

```
<type>(<scope>): <subject>
```

- `type`: `feat`, `fix`, `chore`, `docs`, `test`, `refactor`, `perf`, `build`, `ci`.
- `scope`: `f0`, `f1`, `f2`, `f3`, `f4`, `engine`, `data`, `vision`, `ui`, `deps`, `repo`.
- `subject`: imperativo, inglese, ≤ 72 caratteri.
- Body opzionale, spiega il **perché** quando non ovvio.

Esempi:
- `feat(f1): add gen1 type chart with historical bug edge cases`
- `test(engine): cover magnemite type change gen1→gen2`
- `chore(deps): bump ruff to 0.16`

Commit frequenti, uno per unità logica. Nessun `--no-verify` senza motivazione esplicita.

## Test

- Framework: **pytest**.
- Test obbligatori per ogni modulo di logica pura (`engine/`, `data/`).
- Test facoltativi per UI/overlay (`ui/`) e vision (`vision/`) — coprire almeno le funzioni pure (parsing, coordinate scaling, hash matching), non le chiamate a Win32/Qt.
- Casi limite obbligatori per `engine/`: eccezioni Gen 1 e tipi variabili per generazione (vedi `PLAN.md` §5).

### Coverage

Soglia minima **90%** sui pacchetti di logica pura:

- `src/pokemon_helper/engine/`
- `src/pokemon_helper/data/`

Configurata in `pyproject.toml` sotto `[tool.coverage.*]`. Sotto soglia la CI fallisce.

## Lint e formattazione

- **ruff** per lint e format (config in `pyproject.toml`).
- Regole selezionate: `E`, `F`, `I`, `UP`, `B`, `SIM`.
- Applicato automaticamente da **pre-commit** (`.pre-commit-config.yaml`).

Installazione hook una tantum:

```powershell
pre-commit install
```

Esecuzione manuale su tutto il repo:

```powershell
pre-commit run --all-files
```

## Comandi di sviluppo

Attivazione venv:

```powershell
.\.venv\Scripts\activate
```

Comandi principali:

```powershell
pytest                              # esecuzione test
pytest --cov=pokemon_helper         # test con coverage
ruff check .                        # lint
ruff format .                       # format
python -m pokemon_helper            # smoke test entry-point
```

## Dati e asset

- Il dataset generato (`data/*.sqlite`, `data/sprites/`) è **gitignored**.
- Gli script che generano il dataset stanno in `scripts/` e devono essere idempotenti.
- Riferimento dati esterni: PokeAPI dump statico (vedi `PLAN.md` §4).

## Ambiente di esecuzione

- **F0, F1**: pura logica Python, eseguibile ovunque (anche WSL).
- **F2, F3, F4**: Windows nativo obbligatorio (overlay, capture, hotkey). Vedi `PLAN.md` §3.

Le dipendenze Windows-only (`PySide6`, `windows-capture`, `rapidocr-onnxruntime`, ecc.)
vengono aggiunte al gruppo `[project.optional-dependencies].app` solo a partire da F2.

## Note per Claude

- In caso di dubbio su convenzioni, scope, scelte architetturali: **fermati e chiedi**.
- Non introdurre dipendenze runtime senza discuterle prima.
- Non aggiungere file `.md` di planning/analisi intermedi: usa il contesto della chat.
- Commit conventional puntuali durante il lavoro, non un unico commit gigante a fine sessione.
