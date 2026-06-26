"""Tests del hilo dedicado a I/O Soapy."""

from __future__ import annotations

import threading
import time
from unittest.mock import patch

import pytest

from core.sdr_io import on_sdr_io_thread, run_sdr_io, shutdown_sdr_io


def test_run_sdr_io_executes_on_dedicated_thread():
    seen: list[int] = []

    def _record():
        seen.append(threading.get_ident())
        return on_sdr_io_thread()

    assert run_sdr_io(_record) is True
    assert len(seen) == 1


def test_run_sdr_io_inline_when_already_on_sdr_thread():
    results: list[bool] = []

    def _nested():
        results.append(on_sdr_io_thread())
        results.append(run_sdr_io(on_sdr_io_thread))

    run_sdr_io(_nested)
    assert results == [True, True]


def test_run_sdr_io_timeout_raises_timeout_error_and_logs():
    """When the future times out, run_sdr_io must raise TimeoutError
    and emit a forensic breadcrumb via core.session_log."""
    import concurrent.futures as cf
    import core.sdr_io as sdr_io_mod

    real_executor = sdr_io_mod._ensure_executor()

    class _FakeFuture:
        def result(self, timeout=None):
            # project targets py3.9 where concurrent.futures.TimeoutError is
            # its own class (not aliased to builtin TimeoutError).
            raise cf.TimeoutError()

    with patch.object(real_executor, "submit", return_value=_FakeFuture()):
        with patch("core.session_log.log_breadcrumb") as log_bc:
            with pytest.raises(TimeoutError, match="SDR I/O operation timed out"):
                run_sdr_io(lambda: None)
            log_bc.assert_called_once()


def test_shutdown_sdr_io_resets_executor_and_thread_id():
    """shutdown_sdr_io closes the executor and clears the thread tracking."""
    import core.sdr_io as sdr_io_mod

    # Force initialisation.
    run_sdr_io(lambda: None)
    assert sdr_io_mod._executor is not None
    assert sdr_io_mod._sdr_io_thread_id is not None

    shutdown_sdr_io()
    # After shutdown the executor is reset and the thread id cleared.
    assert sdr_io_mod._executor is None
    assert sdr_io_mod._sdr_io_thread_id is None
    # Subsequent call lazy-reinitialises and reports False on the test thread.
    assert on_sdr_io_thread() is False
