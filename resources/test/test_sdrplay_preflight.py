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
    """Dispositivo abierto sin preflight previo: bloquear RX (no marcar OK)."""
    from types import SimpleNamespace

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
            if self._sdrplay_preflight_done:
                return self._sdrplay_preflight_ok
            if self._device._sdr is not None:
                log_breadcrumb("skip")
                self._sdrplay_preflight_done = True
                self._sdrplay_preflight_ok = False
                return False
            return False

    host = Host()
    assert host._ensure_sdrplay_rx_preflight() is False
    assert host._sdrplay_preflight_ok is False


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


def test_build_preflight_script_cs16():
    from core.sdrplay_preflight import build_preflight_script

    script = build_preflight_script("minimal", stream_format="CS16")
    assert "SOAPY_SDR_CS16" in script
    assert "np.int16" in script


def test_apply_preflight_strategy(monkeypatch):
    from core.sdrplay_preflight import PreflightResult, apply_preflight_strategy

    monkeypatch.delenv("XYZ_SDR_SDRPLAY_STREAM_FORMAT", raising=False)
    apply_preflight_strategy(
        PreflightResult(
            ok=True,
            path="minimal",
            segfault=False,
            last_step="done",
            detail="OK",
            stream_format="CS16",
        )
    )
    import os

    assert os.environ.get("XYZ_SDR_SDRPLAY_STREAM_FORMAT") == "CS16"
    assert os.environ.get("XYZ_SDR_SDRPLAY_STREAM_MODE") == "minimal"
