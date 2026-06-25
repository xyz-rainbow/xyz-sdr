"""Tests del hilo dedicado a I/O Soapy."""

from __future__ import annotations

import threading

from core.sdr_io import on_sdr_io_thread, run_sdr_io


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
