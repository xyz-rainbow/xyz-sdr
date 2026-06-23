"""Tests de setup/env_state.py."""

from __future__ import annotations

from setup.env_state import (
    EnvironmentState,
    path_contains_pothos,
    probe_environment,
)


def test_path_contains_pothos():
    assert path_contains_pothos(r"C:\Program Files\PothosSDR\bin;C:\Windows")
    assert not path_contains_pothos(r"C:\Windows\System32")


def test_python_env_ready_requires_venv_and_libs():
    state = EnvironmentState(
        venv_path=__import__("pathlib").Path("dummy"),
        python_libs_missing=[],
        soapy_import_ok=True,
    )
    assert state.python_env_ready is False  # dummy path no es archivo real


def test_probe_environment_returns_state():
    state = probe_environment(bootstrap_soapy=False)
    assert isinstance(state, EnvironmentState)
    assert isinstance(state.blockers, list)


def test_probe_keeps_venv_soapy_when_bootstrap_runs_on_other_interpreter(monkeypatch):
    from pathlib import Path
    from unittest.mock import MagicMock

    venv_py = Path(__file__).resolve()
    monkeypatch.setattr(
        "core.python_runtime.project_venv_python",
        lambda _root=None: venv_py,
    )
    monkeypatch.setattr("setup.env_state.check_core_libs", lambda _exe: ([], []))
    monkeypatch.setattr("setup.env_state.check_soapy_import", lambda _exe: True)
    monkeypatch.setattr(
        "setup.env_state.probe_soapy_in_python",
        lambda _exe: (True, [{"driver": "sdrplay", "label": "test"}]),
    )
    monkeypatch.setattr("core.soapy_runtime.check_sdrplay_api", lambda: True)
    monkeypatch.setattr("core.soapy_runtime.find_pothos_install", lambda: r"C:\Program Files\PothosSDR")
    monkeypatch.setattr("core.soapy_runtime.check_sdrplay_plugin", lambda: True)
    monkeypatch.setattr("setup.env_state.read_path_from_registry", lambda: r"C:\Program Files\PothosSDR\bin")
    monkeypatch.setenv("PATH", r"C:\Program Files\PothosSDR\bin")

    failed_status = MagicMock(import_ok=False, has_devices=False, devices=[])
    monkeypatch.setattr("core.soapy_runtime.bootstrap_soapy", lambda **kwargs: failed_status)

    state = probe_environment(bootstrap_soapy=True)
    assert state.soapy_import_ok is True
    assert state.has_devices is True
    assert state.device_count == 1
    assert "soapysdr" not in state.blockers


def test_env_ready_vs_hardware_ready():
    state = EnvironmentState(
        sdrplay_ok=True,
        pothos_installed=True,
        path_in_process=True,
        venv_path=__import__("pathlib").Path(__file__),
        python_libs_missing=[],
        soapy_import_ok=True,
        has_devices=False,
    )
    assert state.env_ready is True
    assert state.ready_for_hardware is False
    assert state.hardware_ready is False
    assert state.readiness_level() == "env"
