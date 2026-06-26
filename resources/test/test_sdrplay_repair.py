"""Tests de setup/sdrplay_repair.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from core.sdrplay_usb import CM_PROB_FAILED_INSTALL, SdrplayUsbStatus
from setup.env_state import EnvironmentState
from setup.sdrplay_repair import repair_sdrplay_driver_stack


def _ctx(say_log: list[str] | None = None):
    messages = say_log if say_log is not None else []

    class Ctx:
        lang = "es"
        say = staticmethod(messages.append)

    return Ctx()


def _patch_service_stack(monkeypatch) -> None:
    monkeypatch.setattr("setup.sdrplay_repair.rescan_sdrplay_usb_devices", lambda **k: True)
    monkeypatch.setattr("core.sdrplay_service.stop_sdrplay_service", lambda **k: (True, "stopped"))
    monkeypatch.setattr(
        "core.sdrplay_service.restart_sdrplay_service",
        lambda **k: (True, "restarted"),
    )


def test_repair_runs_api_installer_on_usb_driver_error(monkeypatch):
    messages: list[str] = []
    ctx = _ctx(messages)
    api_ran = {"value": False}

    monkeypatch.setattr(
        "setup.sdrplay_repair.probe_sdrplay_usb_with_retry",
        lambda **k: SdrplayUsbStatus(
            present=True,
            ok=False,
            problem_code=CM_PROB_FAILED_INSTALL,
        ),
    )
    monkeypatch.setattr(
        "setup.sdrplay_repair.probe_environment",
        lambda **k: EnvironmentState(sdrplay_ok=True, pothos_installed=True),
    )
    monkeypatch.setattr("setup.sdrplay_repair.is_sdrplay_api_fault", lambda **k: False)
    monkeypatch.setattr("setup.sdrplay_repair.is_sdrplay_soapy_module_ok", lambda: True)
    _patch_service_stack(monkeypatch)
    monkeypatch.setattr("setup.sdrplay_repair.sync_sdrplay_api_dll_to_pothos", lambda *a, **k: True)
    monkeypatch.setattr("setup.sdrplay_repair.bootstrap_soapy", lambda **k: MagicMock())
    monkeypatch.setattr(
        "setup.sdrplay_repair.recover_sdrplay_enumeration",
        lambda **k: (True, "SDRplay enumerado", MagicMock()),
    )

    def run_api():
        api_ran["value"] = True
        return True

    found, _msg = repair_sdrplay_driver_stack(
        ctx,
        run_api_installer=run_api,
        install_soapy_plugin=lambda: True,
    )
    assert api_ran["value"] is True
    assert found is True
    assert any("28" in m or "USB" in m for m in messages)


def test_repair_installs_api_when_api_fault(monkeypatch):
    messages: list[str] = []
    ctx = _ctx(messages)
    api_ran = {"value": False}

    monkeypatch.setattr(
        "setup.sdrplay_repair.probe_sdrplay_usb_with_retry",
        lambda **k: SdrplayUsbStatus(),
    )
    monkeypatch.setattr(
        "setup.sdrplay_repair.probe_environment",
        lambda **k: EnvironmentState(sdrplay_ok=True, pothos_installed=True),
    )
    monkeypatch.setattr("setup.sdrplay_repair.is_sdrplay_api_fault", lambda **k: True)
    monkeypatch.setattr("setup.sdrplay_repair.is_sdrplay_soapy_module_ok", lambda: True)
    _patch_service_stack(monkeypatch)
    monkeypatch.setattr("setup.sdrplay_repair.sync_sdrplay_api_dll_to_pothos", lambda *a, **k: True)
    monkeypatch.setattr("setup.sdrplay_repair.bootstrap_soapy", lambda **k: MagicMock())
    monkeypatch.setattr(
        "setup.sdrplay_repair.recover_sdrplay_enumeration",
        lambda **k: (True, "SDRplay enumerado", MagicMock()),
    )

    def run_api():
        api_ran["value"] = True
        return True

    found, _msg = repair_sdrplay_driver_stack(
        ctx,
        run_api_installer=run_api,
        install_soapy_plugin=lambda: True,
    )
    assert api_ran["value"] is True
    assert found is True
    assert any("no responde" in m for m in messages)


def test_repair_installs_api_when_missing(monkeypatch):
    ctx = _ctx()
    monkeypatch.setattr("setup.sdrplay_repair.probe_sdrplay_usb_with_retry", lambda **k: SdrplayUsbStatus())
    monkeypatch.setattr(
        "setup.sdrplay_repair.probe_environment",
        lambda **k: EnvironmentState(sdrplay_ok=False),
    )
    monkeypatch.setattr("setup.sdrplay_repair.is_sdrplay_api_fault", lambda **k: False)
    monkeypatch.setattr("setup.sdrplay_repair.is_sdrplay_soapy_module_ok", lambda: False)
    _patch_service_stack(monkeypatch)
    monkeypatch.setattr("setup.sdrplay_repair.sync_sdrplay_api_dll_to_pothos", lambda *a, **k: False)
    monkeypatch.setattr("setup.sdrplay_repair.bootstrap_soapy", lambda **k: MagicMock())
    monkeypatch.setattr(
        "setup.sdrplay_repair.recover_sdrplay_enumeration",
        lambda **k: (True, "ok", MagicMock()),
    )

    calls = {"api": 0}

    def run_api():
        calls["api"] += 1
        monkeypatch.setattr(
            "setup.sdrplay_repair.probe_environment",
            lambda **k: EnvironmentState(sdrplay_ok=True),
        )
        return True

    found, _msg = repair_sdrplay_driver_stack(
        ctx,
        run_api_installer=run_api,
        install_soapy_plugin=lambda: True,
    )
    assert calls["api"] == 1
    assert found is True
