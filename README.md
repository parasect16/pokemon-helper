# pokemon-helper

Windows overlay assistant for Pokemon emulators (Gen 1-5).

See [`PLAN.md`](PLAN.md) for goals, scope, and phased roadmap.

## Requirements

- Windows 10/11 (native, not WSL — see PLAN §3)
- Python 3.14

## Setup

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\activate
pip install -e ".[dev]"
```

## Layout

```
src/pokemon_helper/     package code
tests/                  pytest suite
data/                   generated dataset (gitignored)
scripts/                one-shot maintenance scripts (dataset build, etc.)
PLAN.md                 project plan and decisions
```

## Development phases

- **F0** dataset (pokedex, types-by-gen, sprites, type charts)
- **F1** effectiveness engine (pure Python, testable in WSL)
- **F2** overlay + manual team entry (Windows-only)
- **F3** recognition (OCR + pHash)
- **F4** auto battle detection
