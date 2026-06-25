"""
xyz-sdr | core/logging_config.py
Logging seguro con Textual (evita StreamHandler sobre stdout inválido en Windows).
"""

from __future__ import annotations

import logging

_SESSION_LOGGER = "xyz-sdr.session"


def detach_console_logging() -> None:
    """
    Quita handlers que escriben a stdout/stderr antes de app.run().

    Textual reemplaza la consola; los StreamHandler previos provocan WinError 6.
    Conserva FileHandler de sesión (var/log/xyz-sdr-*.log).
    """
    root = logging.getLogger()
    for handler in list(root.handlers):
        if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
            root.removeHandler(handler)
            try:
                handler.close()
            except Exception:
                pass
    if not root.handlers:
        root.addHandler(logging.NullHandler())
    logging.raiseExceptions = False


def preserve_session_file_handler() -> None:
    """Re-adjuntar logger de sesión al root si hace falta propagación."""
    session = logging.getLogger(_SESSION_LOGGER)
    if session.handlers:
        session.propagate = False

