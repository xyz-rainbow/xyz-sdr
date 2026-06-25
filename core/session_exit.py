"""
xyz-sdr | core/session_exit.py
Marcador de salida de sesión (Python → run.ps1).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from core.runtime_paths import project_root

_MARKER_NAME = ".last-session.json"
_written = False


def _marker_path() -> Path:
    return project_root() / "var" / "log" / _MARKER_NAME


def write_exit_marker(
    kind: str,
    *,
    log_path: str | Path | None = None,
    detail: str = "",
    exit_code: int | None = None,
) -> None:
    """Escribe var/log/.last-session.json (una vez por sesión)."""
    global _written
    payload = {
        "kind": kind,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "log_path": str(log_path) if log_path else "",
        "detail": detail,
        "exit_code": exit_code,
    }
    path = _marker_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    _written = True


def read_exit_marker() -> dict | None:
    path = _marker_path()
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def clear_exit_marker() -> None:
    global _written
    path = _marker_path()
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
    _written = False


def marker_was_written() -> bool:
    return _written


def register_abnormal_atexit() -> None:
    """Si la sesión termina sin marker, registra salida anormal."""
    import atexit

    def _on_exit() -> None:
        if not _written:
            from core.session_log import get_session_log_path

            write_exit_marker(
                "abnormal",
                log_path=get_session_log_path(),
                detail="Process exited without explicit marker (possible native crash)",
            )

    atexit.register(_on_exit)
