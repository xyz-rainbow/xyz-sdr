"""Tests de preflight RX SDRplay (parser / subproceso mockeado)."""

from __future__ import annotations

from core.sdrplay_preflight import (
    parse_stream_probe_output,
    preflight_status_label,
    run_preflight,
    run_preflight_best,
)


def test_parse_stream_probe_output_ok():
    out = "STEP:bootstrap\nSTEP:readStream ret=4096\nOK\n"
    result = parse_stream_probe_output(out, 0, path="minimal")
    assert result.ok
    assert result.path == "minimal"
    assert not result.segfault
    assert result.last_step == "readStream ret=4096"


def test_parse_stream_probe_output_segfault():
    out = "STEP:setSampleRate\n"
    result = parse_stream_probe_output(out, -1073741819, path="legacy")
    assert not result.ok
    assert result.segfault
    assert result.last_step == "setSampleRate"


def test_preflight_status_label():
    from core.sdrplay_preflight import PreflightResult

    assert preflight_status_label(PreflightResult(True, "minimal", False, "done", "")) == "OK"
    assert preflight_status_label(PreflightResult(False, "legacy", True, "open", "crash")) == "SEGFAULT"
    assert preflight_status_label(PreflightResult(False, "legacy", False, "timeout", "slow")) == "FAIL"
    assert preflight_status_label(None) == "SKIP"


def test_preflight_user_message_not_segfault_for_no_device():
    from core.sdrplay_preflight import PreflightResult, preflight_user_message

    result = PreflightResult(
        ok=False,
        path="legacy",
        segfault=False,
        last_step="bootstrap",
        detail="ERR no available RSP devices found",
    )
    msg = preflight_user_message(result)
    assert "crashea" not in msg.lower()
    assert "RSP no disponible" in msg or "SDRuno" in msg


def test_skipped_preflight_when_device_open(monkeypatch):
    """Simula dispositivo ya abierto en padre: no subprocess preflight."""
    from types import SimpleNamespace

    from core.sdrplay_preflight import run_preflight_best

    calls: list[str] = []

    def _fake_best(*_a, **_k):
        calls.append("run")
        raise AssertionError("should not run subprocess preflight")

    monkeypatch.setattr("core.sdrplay_preflight.run_preflight_best", _fake_best)

    device = SimpleNamespace(
        is_simulated=False,
        driver="sdrplay",
        _sdr=object(),
    )

    class Host:
        _device = device
        _sdrplay_preflight_done = False
        _sdrplay_preflight_ok = False
        logs: list[str] = []

        def _log(self, msg: str) -> None:
            self.logs.append(msg)

        def _ensure_sdrplay_rx_preflight(self) -> bool:
            from core.session_log import log_breadcrumb

            if not self._device or self._device.is_simulated or self._device.driver != "sdrplay":
                return True
            if self._device._sdr is not None:
                log_breadcrumb("skip")
                self._sdrplay_preflight_done = True
                self._sdrplay_preflight_ok = True
                return True
            return False

    host = Host()
    assert host._ensure_sdrplay_rx_preflight() is True
    assert calls == []


def test_run_preflight_mock_subprocess(monkeypatch):
    def _fake_run(*_args, **_kwargs):
        class _Proc:
            returncode = 0
            stdout = "STEP:activateStream\nSTEP:readStream ret=4096\nOK\n"
            stderr = ""

        return _Proc()

    monkeypatch.setattr("core.sdrplay_preflight.subprocess.run", _fake_run)
    result = run_preflight("minimal", timeout=1.0)
    assert result.ok
    assert result.path == "minimal"


def test_resolve_preflight_timeout_env(monkeypatch):
    from core.sdrplay_preflight import (
        DEFAULT_PREFLIGHT_TIMEOUT,
        per_path_timeout,
        resolve_preflight_timeout,
    )

    monkeypatch.delenv("XYZ_SDR_PREFLIGHT_TIMEOUT", raising=False)
    assert resolve_preflight_timeout() == DEFAULT_PREFLIGHT_TIMEOUT
    assert per_path_timeout(60) == 30

    monkeypatch.setenv("XYZ_SDR_PREFLIGHT_TIMEOUT", "90")
    assert resolve_preflight_timeout() == 90.0


def test_preflight_user_message_timeout():
    from core.sdrplay_preflight import PreflightResult, preflight_user_message

    result = PreflightResult(
        ok=False,
        path="minimal",
        segfault=False,
        last_step="timeout",
        detail="timeout (stream may be slow but did not crash)",
    )
    msg = preflight_user_message(result)
    assert "timeout" in msg.lower()
    assert "crashea" not in msg.lower()


def test_run_preflight_best_prefers_minimal(monkeypatch):
    call_n = {"n": 0}

    def _fake_run(*_args, **_kwargs):
        call_n["n"] += 1
        if call_n["n"] > 1:
            raise AssertionError("run_preflight_best should stop after first OK")

        class _Proc:
            returncode = 0
            stdout = "STEP:readStream ret=4096\nOK\n"
            stderr = ""

        return _Proc()

    monkeypatch.setattr("core.sdrplay_preflight.subprocess.run", _fake_run)
    result = run_preflight_best(timeout=4.0)
    assert result.ok
    assert call_n["n"] == 1
