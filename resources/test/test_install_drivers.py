"""Tests de setup/install_drivers.py (entrypoint del instalador)."""

from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest


@pytest.fixture
def reload_install_drivers():
    """Importa el módulo y restaura cwd."""
    saved_cwd = os.getcwd()
    sys.modules.pop("setup.install_drivers", None)
    import setup.install_drivers as mod  # noqa: WPS433

    yield mod

    os.chdir(saved_cwd)


def test_lang_returns_current(reload_install_drivers):
    mod = reload_install_drivers
    initial = mod._lang()
    assert initial in ("es", "en")  # detect_system_language
    mod._set_lang("en")
    assert mod._lang() == "en"
    mod._set_lang("es")
    assert mod._lang() == "es"


def test_say_prints_and_logs(reload_install_drivers, monkeypatch, capsys):
    mod = reload_install_drivers
    monkeypatch.setattr("setup.install_drivers.log_line", lambda msg: None)
    mod._say("hello installer")
    captured = capsys.readouterr()
    assert "hello installer" in captured.out


def test_say_calls_log_line(reload_install_drivers):
    mod = reload_install_drivers
    log_calls: list[str] = []
    with patch("setup.install_drivers.log_line", side_effect=log_calls.append):
        mod._say("logged-msg")
    assert log_calls == ["logged-msg"]


def test_confirm_yes(monkeypatch, reload_install_drivers):
    mod = reload_install_drivers
    monkeypatch.setattr("builtins.input", lambda prompt: "s")
    assert mod._confirm("OK?") is True


def test_confirm_si(monkeypatch, reload_install_drivers):
    mod = reload_install_drivers
    monkeypatch.setattr("builtins.input", lambda prompt: "si")
    assert mod._confirm("OK?") is True


def test_confirm_y(monkeypatch, reload_install_drivers):
    mod = reload_install_drivers
    monkeypatch.setattr("builtins.input", lambda prompt: "y")
    assert mod._confirm("OK?") is True


def test_confirm_yes_english(monkeypatch, reload_install_drivers):
    mod = reload_install_drivers
    monkeypatch.setattr("builtins.input", lambda prompt: "yes")
    assert mod._confirm("OK?") is True


def test_confirm_rejects_no(monkeypatch, reload_install_drivers):
    mod = reload_install_drivers
    monkeypatch.setattr("builtins.input", lambda prompt: "n")
    assert mod._confirm("OK?") is False


def test_confirm_rejects_empty(monkeypatch, reload_install_drivers):
    mod = reload_install_drivers
    monkeypatch.setattr("builtins.input", lambda prompt: "")
    assert mod._confirm("OK?") is False


def test_ctx_uses_current_lang(reload_install_drivers, monkeypatch):
    mod = reload_install_drivers
    monkeypatch.setattr("setup.install_drivers.log_line", lambda msg: None)
    mod._set_lang("en")
    ctx = mod._ctx("/tmp/fake")
    assert ctx.lang == "en"
    assert ctx.temp_dir == "/tmp/fake"
    # say y confirm son callables
    assert callable(ctx.say)
    assert callable(ctx.confirm)


def test_ctx_propagates_lang_change(reload_install_drivers, monkeypatch):
    mod = reload_install_drivers
    monkeypatch.setattr("setup.install_drivers.log_line", lambda msg: None)
    mod._set_lang("es")
    ctx1 = mod._ctx("/tmp/fake")
    mod._set_lang("en")
    ctx2 = mod._ctx("/tmp/fake")
    assert ctx1.lang == "es"
    assert ctx2.lang == "en"


def test_build_parser_creates_all_flags(reload_install_drivers):
    mod = reload_install_drivers
    parser = mod._build_parser()
    # No lanza al parsear flags conocidos
    ns = parser.parse_args(["--menu", "--check", "--quiet", "--no-splash"])
    assert ns.menu is True
    assert ns.check is True
    assert ns.quiet is True
    assert ns.no_splash is True


def test_build_parser_require_hardware(reload_install_drivers):
    mod = reload_install_drivers
    parser = mod._build_parser()
    ns = parser.parse_args(["--require-hardware"])
    assert ns.require_hardware is True


def test_build_parser_defaults_false(reload_install_drivers):
    mod = reload_install_drivers
    parser = mod._build_parser()
    ns = parser.parse_args([])
    assert ns.menu is False
    assert ns.repair is False
    assert ns.check is False
    assert ns.quiet is False
    assert ns.verbose is False
    assert ns.require_hardware is False
    assert ns.no_splash is False


def test_exit_code_for_state_env_ready(reload_install_drivers, monkeypatch):
    mod = reload_install_drivers
    monkeypatch.setattr("setup.install_drivers.refresh_windows_environment", lambda: True)
    fake_state = MagicMock_ready(env_ready=True, has_target_hardware=True)
    monkeypatch.setattr("setup.install_drivers.probe_environment", lambda **kw: fake_state)
    assert mod._exit_code_for_state() == 0


def test_exit_code_for_state_env_not_ready(reload_install_drivers, monkeypatch):
    mod = reload_install_drivers
    monkeypatch.setattr("setup.install_drivers.refresh_windows_environment", lambda: True)
    fake_state = MagicMock_ready(env_ready=False, has_target_hardware=False)
    monkeypatch.setattr("setup.install_drivers.probe_environment", lambda **kw: fake_state)
    assert mod._exit_code_for_state() == 1


def test_exit_code_for_state_require_hardware_without_device(reload_install_drivers, monkeypatch):
    mod = reload_install_drivers
    monkeypatch.setattr("setup.install_drivers.refresh_windows_environment", lambda: True)
    fake_state = MagicMock_ready(env_ready=True, has_target_hardware=False)
    monkeypatch.setattr("setup.install_drivers.probe_environment", lambda **kw: fake_state)
    assert mod._exit_code_for_state(require_hardware=True) == 2


def test_make_exit_installer_uses_splash(reload_install_drivers, monkeypatch):
    mod = reload_install_drivers
    fake_splash_calls: list[str] = []
    # El import es lazy dentro de la closure: parchear el módulo de origen.
    monkeypatch.setattr(
        "setup.install_splash.run_installer_closing_splash",
        lambda: fake_splash_calls.append("splash"),
    )
    monkeypatch.setattr("setup.install_drivers.restore_terminal_after_tui", lambda: None)
    monkeypatch.setattr("sys.exit", lambda code: fake_splash_calls.append(f"exit:{code}"))
    exit_fn = mod._make_exit_installer(use_splash=True)
    exit_fn()
    assert "splash" in fake_splash_calls
    assert any(s.startswith("exit:") for s in fake_splash_calls)


def test_make_exit_installer_no_splash(reload_install_drivers, monkeypatch, capsys):
    mod = reload_install_drivers
    monkeypatch.setattr("setup.install_drivers.restore_terminal_after_tui", lambda: None)
    exit_codes: list[int] = []
    monkeypatch.setattr("sys.exit", lambda code: exit_codes.append(code))
    exit_fn = mod._make_exit_installer(use_splash=False)
    exit_fn()
    captured = capsys.readouterr()
    assert "Saliendo" in captured.out
    assert exit_codes == [0]


def test_main_runs_check(reload_install_drivers, monkeypatch):
    mod = reload_install_drivers
    monkeypatch.setattr("setup.install_drivers.get_install_logger", lambda: None)
    monkeypatch.setattr("setup.install_drivers.refresh_windows_environment", lambda: True)
    monkeypatch.setattr("setup.install_drivers.detect_system_language", lambda: "es")
    monkeypatch.setattr("setup.check_env.run_check", lambda verbose, lang: 0)
    monkeypatch.setattr("sys.argv", ["install_drivers.py", "--check"])
    assert mod.main() == 0


def test_main_runs_repair(reload_install_drivers, monkeypatch):
    mod = reload_install_drivers
    monkeypatch.setattr("setup.install_drivers.get_install_logger", lambda: None)
    monkeypatch.setattr("setup.install_drivers.refresh_windows_environment", lambda: True)
    monkeypatch.setattr("setup.install_drivers.detect_system_language", lambda: "es")
    monkeypatch.setattr("setup.install_drivers.log_line", lambda msg: None)
    monkeypatch.setattr("setup.install_drivers.run_repair_wizard", lambda ctx, quiet=False: 0)
    fake_state = MagicMock_ready(env_ready=True, has_target_hardware=True)
    monkeypatch.setattr("setup.install_drivers.probe_environment", lambda **kw: fake_state)
    monkeypatch.setattr("sys.argv", ["install_drivers.py", "--repair"])
    assert mod.main() == 0


def test_main_repair_propagates_code(reload_install_drivers, monkeypatch):
    mod = reload_install_drivers
    monkeypatch.setattr("setup.install_drivers.get_install_logger", lambda: None)
    monkeypatch.setattr("setup.install_drivers.refresh_windows_environment", lambda: True)
    monkeypatch.setattr("setup.install_drivers.detect_system_language", lambda: "es")
    monkeypatch.setattr("setup.install_drivers.log_line", lambda msg: None)
    monkeypatch.setattr("setup.install_drivers.run_repair_wizard", lambda ctx, quiet=False: 7)
    monkeypatch.setattr("sys.argv", ["install_drivers.py", "--repair"])
    assert mod.main() == 7


def test_main_repair_quiet(reload_install_drivers, monkeypatch):
    mod = reload_install_drivers
    monkeypatch.setattr("setup.install_drivers.get_install_logger", lambda: None)
    monkeypatch.setattr("setup.install_drivers.refresh_windows_environment", lambda: True)
    monkeypatch.setattr("setup.install_drivers.detect_system_language", lambda: "es")
    monkeypatch.setattr("setup.install_drivers.log_line", lambda msg: None)
    captured_ctx = {}

    def fake_wizard(ctx, *, quiet=False):
        captured_ctx["quiet"] = quiet
        captured_ctx["auto_confirm"] = ctx.confirm("anything")
        return 0

    monkeypatch.setattr("setup.install_drivers.run_repair_wizard", fake_wizard)
    fake_state = MagicMock_ready(env_ready=True, has_target_hardware=True)
    monkeypatch.setattr("setup.install_drivers.probe_environment", lambda **kw: fake_state)
    monkeypatch.setattr("sys.argv", ["install_drivers.py", "--repair", "--quiet"])
    assert mod.main() == 0
    assert captured_ctx["quiet"] is True
    assert captured_ctx["auto_confirm"] is True


def test_main_resume_repair(reload_install_drivers, monkeypatch):
    mod = reload_install_drivers
    monkeypatch.setattr("setup.install_drivers.get_install_logger", lambda: None)
    monkeypatch.setattr("setup.install_drivers.refresh_windows_environment", lambda: True)
    monkeypatch.setattr("setup.install_drivers.detect_system_language", lambda: "es")
    monkeypatch.setattr("setup.install_drivers.log_line", lambda msg: None)
    monkeypatch.setenv("XYZ_SDR_INSTALL_RESUME", "repair")
    try:
        called = {"yes": False}
        monkeypatch.setattr(
            "setup.install_drivers.run_resumed_repair",
            lambda lang, ctx: called.__setitem__("yes", True),
        )
        monkeypatch.setattr("sys.argv", ["install_drivers.py"])
        assert mod.main() == 0
        assert called["yes"] is True
    finally:
        monkeypatch.delenv("XYZ_SDR_INSTALL_RESUME", raising=False)


def test_main_resume_wizard(reload_install_drivers, monkeypatch):
    mod = reload_install_drivers
    monkeypatch.setattr("setup.install_drivers.get_install_logger", lambda: None)
    monkeypatch.setattr("setup.install_drivers.refresh_windows_environment", lambda: True)
    monkeypatch.setattr("setup.install_drivers.detect_system_language", lambda: "es")
    monkeypatch.setattr("setup.install_drivers.log_line", lambda msg: None)
    monkeypatch.setenv("XYZ_SDR_INSTALL_RESUME", "wizard")
    try:
        called = {"yes": False}
        monkeypatch.setattr(
            "setup.install_drivers.run_resumed_repair",
            lambda lang, ctx: called.__setitem__("yes", True),
        )
        monkeypatch.setattr("sys.argv", ["install_drivers.py"])
        assert mod.main() == 0
        assert called["yes"] is True
    finally:
        monkeypatch.delenv("XYZ_SDR_INSTALL_RESUME", raising=False)


def test_main_uses_temp_env(reload_install_drivers, monkeypatch):
    mod = reload_install_drivers
    monkeypatch.setattr("setup.install_drivers.get_install_logger", lambda: None)
    monkeypatch.setattr("setup.install_drivers.refresh_windows_environment", lambda: True)
    monkeypatch.setattr("setup.install_drivers.detect_system_language", lambda: "es")
    monkeypatch.setattr("setup.install_drivers.log_line", lambda msg: None)
    monkeypatch.setenv("TEMP", "/tmp/fake-temp")
    monkeypatch.delenv("TMP", raising=False)
    monkeypatch.setattr("setup.install_drivers.run_resumed_repair", lambda lang, ctx: None)
    monkeypatch.setenv("XYZ_SDR_INSTALL_RESUME", "repair")
    try:
        captured: dict = {}
        monkeypatch.setattr(
            "setup.install_drivers.run_resumed_repair",
            lambda lang, ctx: captured.__setitem__("temp", ctx.temp_dir),
        )
        monkeypatch.setattr("sys.argv", ["install_drivers.py"])
        mod.main()
        assert captured["temp"] == "/tmp/fake-temp"
    finally:
        monkeypatch.delenv("XYZ_SDR_INSTALL_RESUME", raising=False)


def test_main_falls_back_to_tmp(reload_install_drivers, monkeypatch):
    mod = reload_install_drivers
    monkeypatch.setattr("setup.install_drivers.get_install_logger", lambda: None)
    monkeypatch.setattr("setup.install_drivers.refresh_windows_environment", lambda: True)
    monkeypatch.setattr("setup.install_drivers.detect_system_language", lambda: "es")
    monkeypatch.setattr("setup.install_drivers.log_line", lambda msg: None)
    monkeypatch.delenv("TEMP", raising=False)
    monkeypatch.setenv("TMP", "/tmp/fallback")
    monkeypatch.setenv("XYZ_SDR_INSTALL_RESUME", "repair")
    try:
        captured: dict = {}
        monkeypatch.setattr(
            "setup.install_drivers.run_resumed_repair",
            lambda lang, ctx: captured.__setitem__("temp", ctx.temp_dir),
        )
        monkeypatch.setattr("sys.argv", ["install_drivers.py"])
        mod.main()
        assert captured["temp"] == "/tmp/fallback"
    finally:
        monkeypatch.delenv("XYZ_SDR_INSTALL_RESUME", raising=False)


def test_main_express_menu_skips_splash(reload_install_drivers, monkeypatch):
    mod = reload_install_drivers
    monkeypatch.setattr("setup.install_drivers.get_install_logger", lambda: None)
    monkeypatch.setattr("setup.install_drivers.refresh_windows_environment", lambda: True)
    monkeypatch.setattr("setup.install_drivers.detect_system_language", lambda: "es")
    monkeypatch.setattr("setup.install_drivers.log_line", lambda msg: None)
    monkeypatch.delenv("XYZ_SDR_INSTALL_RESUME", raising=False)
    captured: dict = {}

    def fake_menu(lang, ctx, *, set_lang, temp_dir, exit_fn, initial_state):
        captured["splash_called"] = initial_state is not None
        captured["exit_fn"] = exit_fn

    monkeypatch.setattr("setup.install_drivers.run_express_menu", fake_menu)
    monkeypatch.setattr("sys.argv", ["install_drivers.py", "--no-splash"])
    assert mod.main() == 0
    assert captured["splash_called"] is False


# ---------------------------------------------------------------------------
# Helper para construir EnvironmentState mock
# ---------------------------------------------------------------------------


def MagicMock_ready(*, env_ready: bool, has_target_hardware: bool):
    """Crea un mock con atributos específicos."""
    from unittest.mock import MagicMock

    state = MagicMock()
    state.env_ready = env_ready
    state.has_target_hardware = has_target_hardware
    state.sdrplay_ok = env_ready
    state.drivers_ready = env_ready
    state.python_env_ready = env_ready
    state.path_in_process = env_ready
    state.pothos_installed = env_ready
    state.sdrplay_usb_issue = False
    state.blockers = []
    return state