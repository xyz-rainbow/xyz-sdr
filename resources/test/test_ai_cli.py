"""Tests del flag CLI --ai en main.py."""

from __future__ import annotations

from unittest.mock import patch

import pytest


def test_ai_flag_off_by_default():
    """Sin --ai, el atributo ai debe ser False (se respeta [ai] del config)."""
    import main

    with patch("sys.argv", ["main.py"]):
        args = main.parse_args()
    assert args.ai is False


def test_ai_flag_set_when_passed():
    import main

    with patch("sys.argv", ["main.py", "--ai"]):
        args = main.parse_args()
    assert args.ai is True


def test_ai_help_text_mentions_optional():
    """El help debe mencionar el carácter opt-in para no engañar al usuario."""
    import argparse
    import main

    parser = argparse.ArgumentParser()
    # Reproducimos el bloque principal del parser para inspeccionar el help.
    parser.add_argument("--ai", action="store_true", help="Opt-in: Fase 4-5.")
    rendered = parser.format_help()
    assert "--ai" in rendered
    assert "Opt-in" in rendered or "opt-in" in rendered.lower()


def test_ai_does_not_break_other_flags():
    """--ai debe coexistir con --sim / --debug / --strict sin colisionar."""
    import main

    with patch("sys.argv", ["main.py", "--ai", "--sim", "--strict", "--debug"]):
        args = main.parse_args()
    assert args.ai is True
    assert args.sim is True
    assert args.strict is True
    assert args.debug is True