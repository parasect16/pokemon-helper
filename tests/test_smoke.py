"""Smoke test iniziale: verifica che il pacchetto sia importabile."""

from pokemon_helper import __version__


def test_version_string() -> None:
    """La versione deve essere una stringa non vuota."""
    assert isinstance(__version__, str)
    assert __version__
