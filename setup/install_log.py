"""Logging de sesiones del instalador en var/log/."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path

from setup.env_state import project_root

_ANSI = re.compile(r"\033\[[0-9;]*m")
_logger: logging.Logger | None = None
_log_path: Path | None = None


def strip_ansi(text: str) -> str:
    return _ANSI.sub("", text)


def get_install_logger() -> logging.Logger:
    global _logger, _log_path
    if _logger is not None:
        return _logger

    log_dir = project_root() / "var" / "log"
    log_dir.mkdir(parents=True, exist_ok=True)
    _log_path = log_dir / f"install-{datetime.now():%Y%m%d-%H%M%S}.log"

    logger = logging.getLogger("xyz-sdr.install")
    logger.handlers.clear()
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    handler = logging.FileHandler(_log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.info("=== xyz-sdr install session started ===")

    _logger = logger
    return logger


def current_log_path() -> Path | None:
    return _log_path


def log_line(message: str, *, level: int = logging.INFO) -> None:
    get_install_logger().log(level, strip_ansi(message))
