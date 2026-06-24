"""Tests de supresión de salida durante arranque."""

from __future__ import annotations

import logging
import sys

from core.startup_io import suppress_startup_output


def test_suppress_startup_output_captures_logging():
    captured: list[str] = []
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    log = logging.getLogger("test.startup")
    with suppress_startup_output(captured):
        log.info("mensaje oculto")
    assert any("mensaje oculto" in line for line in captured)


def test_restore_stdio_reopens():
    from core.startup_io import restore_stdio

    restore_stdio()
    assert hasattr(sys.stderr, "write")
    sys.stderr.write("")
