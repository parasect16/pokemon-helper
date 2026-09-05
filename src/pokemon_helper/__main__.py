"""Entry point CLI: `python -m pokemon_helper` avvia l'overlay Qt."""

from __future__ import annotations

from pokemon_helper import __version__


def main() -> int:
    """Avvia l'overlay; degrada con un messaggio se PySide6 non è installato."""
    try:
        from pokemon_helper.ui.app import run
    except ImportError as exc:
        print(f"pokemon-helper {__version__}")
        print(f"dipendenze UI mancanti: {exc}")
        print("installa con: pip install -e '.[app]'")
        return 1
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
