"""Tests for setup/check_env.py -- run_check output helpers + non-verbose branch."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from setup import check_env
from setup.check_env import fail, ok, run_check, step, warn


# ---------------------------------------------------------------------------
# Print helpers (smoke tests, no behavioral assertions on ANSI escapes)
# ---------------------------------------------------------------------------


def test_ok_prints(capsys: pytest.CaptureFixture) -> None:
    ok("mensaje")
    out = capsys.readouterr().out
    assert "mensaje" in out
    assert "[OK]" in out


def test_warn_prints(capsys: pytest.CaptureFixture) -> None:
    warn("cuidado")
    out = capsys.readouterr().out
    assert "cuidado" in out
    assert "[!!]" in out


def test_fail_prints(capsys: pytest.CaptureFixture) -> None:
    fail("roto")
    out = capsys.readouterr().out
    assert "roto" in out
    assert "[XX]" in out


def test_step_prints(capsys: pytest.CaptureFixture) -> None:
    step("Iniciando")
    out = capsys.readouterr().out
    assert "Iniciando" in out
    assert "[>>]" in out


# ---------------------------------------------------------------------------
# run_check non-verbose branch
# ---------------------------------------------------------------------------


def test_run_check_non_verbose_returns_zero_when_env_ready(monkeypatch, capsys) -> None:
    from setup.env_state import EnvironmentState
    import tempfile
    import pathlib

    with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as f:
        venv_path = pathlib.Path(f.name)

    state = EnvironmentState(
        sdrplay_ok=True,
        pothos_installed=True,
        path_in_process=True,
        sdrplay_module_ok=True,
        sdrplay_plugin_ok=True,
        venv_path=venv_path,
        python_libs_missing=[],
        soapy_import_ok=True,
        has_devices=False,
    )

    # run_check imports probe_environment from setup.env_state at call time.
    monkeypatch.setattr("setup.env_state.probe_environment", lambda **kw: state)
    # Avoid Windows-specific refresh that requires real hardware.
    monkeypatch.setattr(
        "setup.windows_installers.refresh_windows_environment", lambda: None,
    )
    rc = run_check(verbose=False, lang="es")
    assert rc == 0
    out = capsys.readouterr().out
    assert "resumen" in out.lower() or "status" in out.lower() or "resumen del estado" in out.lower()


def test_run_check_non_verbose_returns_one_when_blockers(monkeypatch, capsys) -> None:
    from setup.env_state import EnvironmentState

    state = EnvironmentState(blockers=["sdrplay_api", "venv"])

    monkeypatch.setattr("setup.env_state.probe_environment", lambda **kw: state)
    monkeypatch.setattr(
        "setup.windows_installers.refresh_windows_environment", lambda: None,
    )
    rc = run_check(verbose=False, lang="es")
    assert rc == 1
    out = capsys.readouterr().out
    # Blockers should be listed under "problema(s)".
    assert "sdrplay_api" in out
    assert "venv" in out


def test_run_check_non_verbose_warns_when_no_devices(monkeypatch, capsys) -> None:
    from setup.env_state import EnvironmentState
    import tempfile
    import pathlib

    with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as f:
        venv_path = pathlib.Path(f.name)

    state = EnvironmentState(
        sdrplay_ok=True,
        pothos_installed=True,
        path_in_process=True,
        sdrplay_module_ok=True,
        venv_path=venv_path,
        python_libs_missing=[],
        soapy_import_ok=True,
        has_devices=False,
    )
    monkeypatch.setattr("setup.env_state.probe_environment", lambda **kw: state)
    monkeypatch.setattr(
        "setup.windows_installers.refresh_windows_environment", lambda: None,
    )
    rc = run_check(verbose=False, lang="es")
    assert rc == 0
    out = capsys.readouterr().out
    assert "OK" in out or "[OK]" in out


def test_run_check_verbose_short_circuits_when_not_verbose(monkeypatch, capsys) -> None:
    from setup.env_state import EnvironmentState
    import tempfile
    import pathlib

    with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as f:
        venv_path = pathlib.Path(f.name)

    state = EnvironmentState(
        sdrplay_ok=True,
        pothos_installed=True,
        path_in_process=True,
        sdrplay_module_ok=True,
        venv_path=venv_path,
        python_libs_missing=[],
        soapy_import_ok=True,
        has_devices=True,
    )
    monkeypatch.setattr("setup.env_state.probe_environment", lambda **kw: state)
    monkeypatch.setattr(
        "setup.windows_installers.refresh_windows_environment", lambda: None,
    )
    rc = run_check(verbose=False, lang="es")
    assert rc == 0


# ---------------------------------------------------------------------------
# Module-level configuration smoke tests
# ---------------------------------------------------------------------------


def test_check_env_module_exposes_run_check() -> None:
    assert callable(check_env.run_check)
    assert callable(check_env.ok)
    assert callable(check_env.warn)
    assert callable(check_env.fail)
    assert callable(check_env.step)


def test_check_env_module_root_path_set() -> None:
    # Module loads ROOT for its sys.path bootstrap; should be a Path under workspace.
    assert check_env.ROOT.is_dir()
    # And it should be the project root (contains pyproject.toml or setup/).
    assert (check_env.ROOT / "pyproject.toml").is_file() or (
        check_env.ROOT / "setup"
    ).is_dir()