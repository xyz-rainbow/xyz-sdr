"""Tests de setup/install_sdrplay_api.py (atajo CLI)."""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def reload_install_sdrplay_api():
    """Importa (o reimporta) el módulo y restaura cwd después."""
    saved_cwd = os.getcwd()
    # Quitar módulo de caché para forzar reimport fresco en cada test.
    sys.modules.pop("setup.install_sdrplay_api", None)
    import setup.install_sdrplay_api as mod  # noqa: WPS433

    yield mod

    os.chdir(saved_cwd)


def test_say_prints_and_logs(reload_install_sdrplay_api, monkeypatch, capsys):
    mod = reload_install_sdrplay_api
    monkeypatch.setattr("setup.install_sdrplay_api.log_line", lambda msg: None)
    mod._say("hola")
    captured = capsys.readouterr()
    assert "hola" in captured.out


def test_say_flushes(reload_install_sdrplay_api, monkeypatch, capsys):
    """print con flush=True debe escribir al stream."""
    mod = reload_install_sdrplay_api
    monkeypatch.setattr("setup.install_sdrplay_api.log_line", lambda msg: None)
    mod._say("flush-me")
    captured = capsys.readouterr()
    assert "flush-me" in captured.out


def test_say_calls_log_line(reload_install_sdrplay_api):
    mod = reload_install_sdrplay_api
    log_calls: list[str] = []
    with patch("setup.install_sdrplay_api.log_line", side_effect=log_calls.append):
        mod._say("msg-to-log")
    assert log_calls == ["msg-to-log"]


def test_main_returns_zero_on_success(reload_install_sdrplay_api, monkeypatch):
    mod = reload_install_sdrplay_api
    monkeypatch.setattr("setup.install_sdrplay_api.get_install_logger", lambda: None)
    monkeypatch.setattr("setup.install_sdrplay_api.refresh_windows_environment", lambda: True)
    monkeypatch.setattr("setup.install_sdrplay_api.detect_system_language", lambda: "es")
    monkeypatch.setattr("setup.install_sdrplay_api.run_sdrplay_api_installer", lambda ctx, isolated: True)
    monkeypatch.setattr("setup.install_sdrplay_api.log_line", lambda msg: None)
    monkeypatch.setattr("sys.argv", ["install_sdrplay_api.py"])

    rc = mod.main()
    assert rc == 0


def test_main_returns_one_on_failure(reload_install_sdrplay_api, monkeypatch):
    mod = reload_install_sdrplay_api
    monkeypatch.setattr("setup.install_sdrplay_api.get_install_logger", lambda: None)
    monkeypatch.setattr("setup.install_sdrplay_api.refresh_windows_environment", lambda: True)
    monkeypatch.setattr("setup.install_sdrplay_api.detect_system_language", lambda: "es")
    monkeypatch.setattr("setup.install_sdrplay_api.run_sdrplay_api_installer", lambda ctx, isolated: False)
    monkeypatch.setattr("setup.install_sdrplay_api.log_line", lambda msg: None)
    monkeypatch.setattr("sys.argv", ["install_sdrplay_api.py"])

    rc = mod.main()
    assert rc == 1


def test_main_passes_isolated_flag(reload_install_sdrplay_api, monkeypatch):
    mod = reload_install_sdrplay_api
    monkeypatch.setattr("setup.install_sdrplay_api.get_install_logger", lambda: None)
    monkeypatch.setattr("setup.install_sdrplay_api.refresh_windows_environment", lambda: True)
    monkeypatch.setattr("setup.install_sdrplay_api.detect_system_language", lambda: "es")
    captured = {}

    def fake_run(ctx, *, isolated):
        captured["isolated"] = isolated
        return True

    monkeypatch.setattr("setup.install_sdrplay_api.run_sdrplay_api_installer", fake_run)
    monkeypatch.setattr("setup.install_sdrplay_api.log_line", lambda msg: None)
    monkeypatch.setattr("sys.argv", ["install_sdrplay_api.py", "--isolated"])

    assert mod.main() == 0
    assert captured["isolated"] is True


def test_main_uses_temp_env(monkeypatch, reload_install_sdrplay_api):
    mod = reload_install_sdrplay_api
    monkeypatch.setattr("setup.install_sdrplay_api.get_install_logger", lambda: None)
    monkeypatch.setattr("setup.install_sdrplay_api.refresh_windows_environment", lambda: True)
    monkeypatch.setattr("setup.install_sdrplay_api.detect_system_language", lambda: "es")
    monkeypatch.setenv("TEMP", "/tmp/fake-temp")
    monkeypatch.delenv("TMP", raising=False)
    captured: dict = {}

    def fake_run(ctx, *, isolated):
        captured["temp_dir"] = ctx.temp_dir
        return True

    monkeypatch.setattr("setup.install_sdrplay_api.run_sdrplay_api_installer", fake_run)
    monkeypatch.setattr("setup.install_sdrplay_api.log_line", lambda msg: None)
    monkeypatch.setattr("sys.argv", ["install_sdrplay_api.py"])

    mod.main()
    assert captured["temp_dir"] == "/tmp/fake-temp"


def test_main_falls_back_to_tmp_when_temp_unset(monkeypatch, reload_install_sdrplay_api):
    mod = reload_install_sdrplay_api
    monkeypatch.setattr("setup.install_sdrplay_api.get_install_logger", lambda: None)
    monkeypatch.setattr("setup.install_sdrplay_api.refresh_windows_environment", lambda: True)
    monkeypatch.setattr("setup.install_sdrplay_api.detect_system_language", lambda: "es")
    monkeypatch.delenv("TEMP", raising=False)
    monkeypatch.setenv("TMP", "/tmp/fallback-tmp")
    captured: dict = {}

    def fake_run(ctx, *, isolated):
        captured["temp_dir"] = ctx.temp_dir
        return True

    monkeypatch.setattr("setup.install_sdrplay_api.run_sdrplay_api_installer", fake_run)
    monkeypatch.setattr("setup.install_sdrplay_api.log_line", lambda msg: None)
    monkeypatch.setattr("sys.argv", ["install_sdrplay_api.py"])

    mod.main()
    assert captured["temp_dir"] == "/tmp/fallback-tmp"


def test_main_prints_banner(reload_install_sdrplay_api, monkeypatch, capsys):
    mod = reload_install_sdrplay_api
    monkeypatch.setattr("setup.install_sdrplay_api.get_install_logger", lambda: None)
    monkeypatch.setattr("setup.install_sdrplay_api.refresh_windows_environment", lambda: True)
    monkeypatch.setattr("setup.install_sdrplay_api.detect_system_language", lambda: "es")
    monkeypatch.setattr("setup.install_sdrplay_api.run_sdrplay_api_installer", lambda ctx, isolated: True)
    monkeypatch.setattr("setup.install_sdrplay_api.log_line", lambda msg: None)
    monkeypatch.setattr("sys.argv", ["install_sdrplay_api.py"])

    mod.main()
    captured = capsys.readouterr()
    # El banner usa el i18n key 'menu_opt_sdrplay' pero se imprime siempre.
    assert "===" in captured.out