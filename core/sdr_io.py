"""
xyz-sdr | core/sdr_io.py
Serializa operaciones nativas SoapySDR en un único hilo (plugins no son thread-safe).
"""

from __future__ import annotations

import concurrent.futures
import threading
from typing import Callable, TypeVar

T = TypeVar("T")

_executor: concurrent.futures.ThreadPoolExecutor | None = None
_sdr_io_thread_id: int | None = None
_executor_lock = threading.Lock()


def _ensure_executor() -> concurrent.futures.ThreadPoolExecutor:
    global _executor, _sdr_io_thread_id
    with _executor_lock:
        if _executor is None:
            _executor = concurrent.futures.ThreadPoolExecutor(
                max_workers=1,
                thread_name_prefix="sdr-io",
            )

            def _init_thread_id() -> None:
                global _sdr_io_thread_id
                _sdr_io_thread_id = threading.get_ident()

            _executor.submit(_init_thread_id).result(timeout=5.0)
        return _executor


def on_sdr_io_thread() -> bool:
    """True si el hilo actual es el dedicado a I/O Soapy."""
    return _sdr_io_thread_id is not None and threading.get_ident() == _sdr_io_thread_id


def run_sdr_io(func: Callable[..., T], /, *args, timeout: float = 120.0, **kwargs) -> T:
    """
    Ejecuta *func* en el hilo sdr-io (o inline si ya estamos ahí).

    Raises:
        TimeoutError: si la operación supera el límite (p. ej. readStream bloqueado).
    """
    if on_sdr_io_thread():
        return func(*args, **kwargs)

    executor = _ensure_executor()
    future = executor.submit(func, *args, **kwargs)
    try:
        return future.result(timeout=timeout)
    except concurrent.futures.TimeoutError as exc:
        try:
            from core.session_log import log_breadcrumb

            log_breadcrumb(f"sdr_io timeout func={getattr(func, '__name__', func)!r}")
        except ImportError:
            pass
        raise TimeoutError("SDR I/O operation timed out") from exc


def shutdown_sdr_io() -> None:
    """Cierra el executor (tests / cierre limpio)."""
    global _executor, _sdr_io_thread_id
    with _executor_lock:
        if _executor is not None:
            _executor.shutdown(wait=False, cancel_futures=True)
            _executor = None
            _sdr_io_thread_id = None
