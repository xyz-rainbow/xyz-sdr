"""Tests de setup/install_guidance.py."""

from __future__ import annotations

from pathlib import Path

from setup.env_state import EnvironmentState
from setup.install_guidance import next_action


def _state(**kwargs) -> EnvironmentState:
    return EnvironmentState(**kwargs)


def test_next_action_missing_venv():
    state = _state(
        sdrplay_ok=True,
        pothos_installed=True,
        path_in_process=True,
        venv_path=None,
        blockers=["venv"],
    )
    action = next_action(state, "es")
    assert action.id == "repair_all"
    assert action.menu_highlight == "1"


def test_next_action_env_ready_no_device():
    state = _state(
        sdrplay_ok=True,
        pothos_installed=True,
        path_in_process=True,
        sdrplay_plugin_ok=True,
        venv_path=Path(__file__),
        python_libs_missing=[],
        soapy_import_ok=True,
        has_devices=False,
        blockers=[],
    )
    action = next_action(state, "en")
    assert action.id == "run_sim"
    assert action.menu_highlight == "2"


def test_next_action_all_ready():
    state = _state(
        sdrplay_ok=True,
        pothos_installed=True,
        path_in_process=True,
        sdrplay_plugin_ok=True,
        venv_path=Path(__file__),
        python_libs_missing=[],
        soapy_import_ok=True,
        has_devices=True,
        device_count=1,
        blockers=[],
    )
    action = next_action(state, "es")
    assert action.id == "run_app"


def test_next_action_pothos_path():
    state = _state(
        pothos_installed=True,
        path_in_registry=True,
        path_in_process=False,
        blockers=["pothos_path"],
    )
    action = next_action(state, "es")
    assert action.id == "repair_all"
    assert "pothos_path" in action.blockers


def test_next_action_soapy_sdrplay3():
    state = _state(
        sdrplay_ok=True,
        pothos_installed=True,
        path_in_process=True,
        sdrplay_plugin_ok=False,
        blockers=["soapy_sdrplay3"],
    )
    action = next_action(state, "es")
    assert action.id == "repair_all"
    assert action.reason_key == "next_reason_soapy_sdrplay3"


def test_env_ready_property():
    state = _state(
        sdrplay_ok=True,
        pothos_installed=True,
        path_in_process=True,
        sdrplay_plugin_ok=True,
        venv_path=Path(__file__),
        python_libs_missing=[],
        soapy_import_ok=True,
    )
    assert state.env_ready is True
    assert state.hardware_ready is False
    assert state.readiness_level() == "env"
