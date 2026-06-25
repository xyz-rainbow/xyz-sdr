"""
xyz-sdr | core/session_log.py
Log de sesión persistente (sobrevive a crashes si el handler hace flush).
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from core.runtime_paths import project_root

_SESSION_LOGGER = "xyz-sdr.session"
_handler: logging.Handler | None = None
_log_path: Path | None = None


class _FlushingFileHandler(logging.FileHandler):
    """FileHandler que hace flush tras cada registro."""

    def emit(self, record: logging.LogRecord) -> None:
        super().emit(record)
        self.flush()


def start_session_log() -> Path | None:
    """Inicia log de sesión en var/log/xyz-sdr-{timestamp}.log."""
    global _handler, _log_path
    if _handler is not None:
        return _log_path

    log_dir = project_root() / "var" / "log"
    log_dir.mkdir(parents=True, exist_ok=True)
    _log_path = log_dir / f"xyz-sdr-{datetime.now():%Y%m%d-%H%M%S}.log"

    logger = logging.getLogger(_SESSION_LOGGER)
    logger.handlers.clear()
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    _handler = _FlushingFileHandler(_log_path, encoding="utf-8", delay=False)
    _handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", "%H:%M:%S")
    )
    logger.addHandler(_handler)
    logger.info("=== xyz-sdr session started ===")
    _handler.flush()
    return _log_path


def get_session_log_path() -> Path | None:
    return _log_path


def get_session_logger() -> logging.Logger:
    return logging.getLogger(_SESSION_LOGGER)


def log_breadcrumb(message: str, *, level: int = logging.INFO) -> None:
    """Registra un hito de operación nativa / arranque."""
    logger = get_session_logger()
    if not logger.handlers:
        return
    logger.log(level, "[breadcrumb] %s", message)
    for handler in logger.handlers:
        try:
            handler.flush()
        except Exception:
            pass


def close_session_log() -> None:
    global _handler, _log_path
    logger = get_session_logger()
    if _handler is not None:
        logger.info("=== xyz-sdr session ended ===")
        try:
            _handler.flush()
            _handler.close()
        except Exception:
            pass
        logger.removeHandler(_handler)
        _handler = None


def tail_session_log(max_lines: int = 25) -> list[str]:
    """Devuelve las últimas líneas del log de sesión activo o más reciente."""
    path = _log_path
    if path is None or not path.is_file():
        log_dir = project_root() / "var" / "log"
        if log_dir.is_dir():
            candidates = sorted(log_dir.glob("xyz-sdr-*.log"), key=lambda p: p.stat().st_mtime)
            path = candidates[-1] if candidates else None
    if path is None or not path.is_file():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    return lines[-max_lines:] if max_lines > 0 else lines
