"""
xyz-sdr | core/startup_io.py
Suprime stderr y logging durante el arranque (splash).

No tocar stdout/fd 1: Textual captura stdout al crear la App.
"""

from __future__ import annotations

import logging
import os
import sys
from contextlib import contextmanager
from typing import Iterator

_LOG_FORMAT = logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    "%H:%M:%S",
)


def restore_stdio() -> None:
    """Re-sincroniza sys.stdout/stderr con los fds 1/2 (Textual en Windows)."""
    try:
        sys.stdout = os.fdopen(
            1, "w", encoding="utf-8", errors="replace", buffering=1, closefd=False
        )
    except Exception:
        sys.stdout = sys.__stdout__
    try:
        sys.stderr = os.fdopen(
            2, "w", encoding="utf-8", errors="replace", buffering=1, closefd=False
        )
    except Exception:
        sys.stderr = sys.__stderr__


@contextmanager
def suppress_soapy_probe_output() -> Iterator[None]:
    """
    Silencia stdout y stderr durante enumerate Soapy (UHD/VOLK en Pothos).
    Usar solo tras imprimir la UI del instalador; no durante splash/TUI.
    """
    saved_stdout_fd = os.dup(1)
    saved_stderr_fd = os.dup(2)
    devnull_fd = os.open(os.devnull, os.O_WRONLY)

    try:
        os.dup2(devnull_fd, 1)
        os.dup2(devnull_fd, 2)
        yield
    finally:
        os.dup2(saved_stdout_fd, 1)
        os.dup2(saved_stderr_fd, 2)
        os.close(saved_stdout_fd)
        os.close(saved_stderr_fd)
        os.close(devnull_fd)
        restore_stdio()


@contextmanager
def suppress_startup_output(
    captured: list[str] | None = None,
) -> Iterator[None]:
    """
    Silencia stderr (Soapy/VOLK) y logging de consola.
    stdout queda intacto para splash y Textual.
    """
    saved_stderr_fd = os.dup(2)
    devnull_fd = os.open(os.devnull, os.O_WRONLY)

    root = logging.getLogger()
    old_level = root.level

    capture_handler: logging.Handler | None = None
    if captured is not None:
        capture_handler = logging.Handler()
        capture_handler.setFormatter(_LOG_FORMAT)

        def _emit(record: logging.LogRecord) -> None:
            captured.append(capture_handler.format(record))

        capture_handler.emit = _emit  # type: ignore[method-assign]
        root.addHandler(capture_handler)

    removed_handlers: list[logging.Handler] = []
    for handler in list(root.handlers):
        if handler is capture_handler:
            continue
        if isinstance(handler, logging.StreamHandler):
            removed_handlers.append(handler)
            root.removeHandler(handler)

    try:
        os.dup2(devnull_fd, 2)
        yield
    finally:
        os.dup2(saved_stderr_fd, 2)
        os.close(saved_stderr_fd)
        os.close(devnull_fd)

        restore_stdio()

        if capture_handler is not None:
            root.removeHandler(capture_handler)

        # No re-añadir StreamHandlers aquí: main.py llama detach_console_logging()
        # antes de app.run() y re-añadirlos dejaría fds inválidos en Windows.
        for handler in removed_handlers:
            if not isinstance(handler, logging.StreamHandler):
                root.addHandler(handler)

        root.setLevel(old_level)
