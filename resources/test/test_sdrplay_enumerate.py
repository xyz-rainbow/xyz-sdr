"""Tests de recuperación de enumeración SDRplay."""

from __future__ import annotations

from core.sdrplay_enumerate import has_sdrplay_in_devices, recover_sdrplay_enumeration


def test_has_sdrplay_in_devices():
    assert has_sdrplay_in_devices([{"driver": "audio"}, {"driver": "sdrplay"}])
    assert not has_sdrplay_in_devices([{"driver": "audio"}])


def test_recover_skips_restart_when_disabled(monkeypatch):
    class Status:
        devices = [{"driver": "audio"}]

    monkeypatch.setattr("core.sdrplay_enumerate.bootstrap_soapy", lambda **k: Status())
    monkeypatch.setattr("core.sdrplay_enumerate.check_sdrplay_plugin", lambda: False)
    monkeypatch.setattr(
        "core.sdrplay_service.restart_sdrplay_service",
        lambda **k: (_ for _ in ()).throw(AssertionError("should not restart")),
    )

    found, msg, _status = recover_sdrplay_enumeration(restart_if_missing=False)
    assert found is False
    assert "no visible" in msg.lower()


def test_recover_quick_retry_before_restart(monkeypatch):
    calls = {"restart": 0, "bootstrap": 0}

    class Status:
        devices = []

    def fake_bootstrap(**kwargs):
        calls["bootstrap"] += 1
        status = Status()
        if calls["bootstrap"] >= 3:
            status.devices = [{"driver": "sdrplay", "label": "RSP1"}]
        return status

    monkeypatch.setattr("core.sdrplay_enumerate.bootstrap_soapy", fake_bootstrap)
    monkeypatch.setattr("core.sdrplay_enumerate.check_sdrplay_plugin", lambda: False)
    monkeypatch.setattr("core.sdrplay_enumerate.time.sleep", lambda _s: None)

    def fail_restart(**kwargs):
        calls["restart"] += 1
        raise AssertionError("should not restart")

    monkeypatch.setattr("core.sdrplay_service.restart_sdrplay_service", fail_restart)

    found, msg, _status = recover_sdrplay_enumeration(restart_if_missing=True)
    assert found is True
    assert calls["restart"] == 0
    assert "reintento" in msg.lower()


def test_recover_restarts_service_when_api_ok(monkeypatch):
    calls = {"restart": 0, "bootstrap": 0}

    class Status:
        devices = []

    def fake_bootstrap(**kwargs):
        calls["bootstrap"] += 1
        status = Status()
        if calls["bootstrap"] >= 5:
            status.devices = [{"driver": "sdrplay", "label": "RSP1"}]
        else:
            status.devices = []
        return status

    monkeypatch.setattr("core.sdrplay_enumerate.bootstrap_soapy", fake_bootstrap)
    monkeypatch.setattr("core.sdrplay_enumerate.check_sdrplay_plugin", lambda: False)
    monkeypatch.setattr("core.sdrplay_enumerate.check_sdrplay_api", lambda: True)
    monkeypatch.setattr("core.sdrplay_service.check_sdrplay_service_running", lambda: True)

    def fake_restart(**kwargs):
        calls["restart"] += 1
        return True, "restarted"

    monkeypatch.setattr("core.sdrplay_service.restart_sdrplay_service", fake_restart)
    monkeypatch.setattr("core.sdrplay_service.ensure_sdrplay_service_running", lambda **k: (True, "ok"))
    monkeypatch.setattr("core.sdrplay_enumerate.time.sleep", lambda _s: None)

    found, msg, _status = recover_sdrplay_enumeration(restart_if_missing=True)
    assert found is True
    assert calls["restart"] == 1
    assert "visible" in msg.lower()
