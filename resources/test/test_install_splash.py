"""Tests de splash del instalador."""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock

from setup.env_state import EnvironmentState
from setup.install_splash import run_installer_closing_splash, run_installer_opening_splash


@contextmanager
def _nullctx(*_args, **_kwargs):
    yield


def test_opening_splash_probes_environment(monkeypatch):
    ready = EnvironmentState(sdrplay_ok=True, pothos_installed=True)
    splash = MagicMock(return_value=ready)
    monkeypatch.setattr("tui.splash.run_startup_splash", splash)
    monkeypatch.setattr("setup.install_splash.refresh_windows_environment", lambda: None)
    monkeypatch.setattr("setup.install_splash.probe_environment", lambda **k: ready)
    monkeypatch.setattr("core.startup_io.suppress_soapy_probe_output", _nullctx)
    monkeypatch.setattr("core.startup_io.suppress_startup_output", _nullctx)

    state = run_installer_opening_splash("es")
    assert state is ready
    splash.assert_called_once()
    assert splash.call_args.kwargs.get("status_lines") is not None


def test_closing_splash_delegates(monkeypatch):
    called = {"value": False}
    monkeypatch.setattr(
        "tui.splash.print_shutdown_splash",
        lambda: called.update(value=True),
    )
    run_installer_closing_splash()
    assert called["value"] is True
