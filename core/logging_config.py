"""
xyz-sdr | core/logging_config.py
Logging seguro con Textual (evita StreamHandler sobre stdout inválido en Windows).
"""

from __future__ import annotations

import logging


def detach_console_logging() -> None:
    """
    Quita handlers que escriben a stdout/stderr antes de app.run().

    Textual reemplaza la consola; los StreamHandler previos provocan WinError 6.
    """
    root = logging.getLogger()
    for handler in list(root.handlers):
        if isinstance(handler, logging.StreamHandler):
            root.removeHandler(handler)
            try:
                handler.close()
            except Exception:
                pass
    if not root.handlers:
        root.addHandler(logging.NullHandler())
    logging.raiseExceptions = False
