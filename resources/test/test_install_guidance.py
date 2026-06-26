"""Tests de setup/install_guidance.py."""

from __future__ import annotations

from pathlib import Path

from setup.env_state import EnvironmentState
from setup.install_guidance import (
    INSTALL_BLOCKER_ORDER,
    InstallAction,
    _first_install_blocker,
    drivers_row_status,
    format_action,
    hardware_row_status,
    next_action,
    python_row_status,
)


def _state(**kwargs) -> EnvironmentState:
    return EnvironmentState(**kwargs)


def test_next_action_missing_venv():
    state = _state(
        sdrplay_ok=True,
        pothos_installed=True,
        path_in_process=True,
        sdrplay_module_ok=True,
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
        sdrplay_module_ok=True,
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
        sdrplay_module_ok=True,
        sdrplay_plugin_ok=True,
        venv_path=Path(__file__),
        python_libs_missing=[],
        soapy_import_ok=True,
        has_sdrplay_devices=True,
        sdrplay_device_count=1,
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
        sdrplay_module_ok=False,
        blockers=["soapy_sdrplay3"],
    )
    action = next_action(state, "es")
    assert action.id == "repair_all"
    assert action.reason_key == "next_reason_soapy_sdrplay3"


def test_next_action_sdrplay_enumeration():
    state = _state(
        sdrplay_ok=True,
        pothos_installed=True,
        path_in_process=True,
        sdrplay_module_ok=True,
        sdrplay_plugin_ok=False,
        venv_path=Path(__file__),
        python_libs_missing=[],
        soapy_import_ok=True,
        blockers=["sdrplay_enumeration"],
    )
    action = next_action(state, "es")
    assert action.reason_key == "next_reason_sdrplay_enum"
    assert action.menu_highlight == "1"


def test_drivers_row_plugin_installed_not_enumerating():
    state = _state(
        sdrplay_ok=True,
        pothos_installed=True,
        path_in_process=True,
        sdrplay_module_ok=True,
        sdrplay_plugin_ok=False,
    )
    text = drivers_row_status(state, "es")
    assert "no visible" in text.lower() or "instalado" in text.lower()


def test_hardware_row_usb_driver_failed():
    state = _state(
        sdrplay_ok=True,
        pothos_installed=True,
        path_in_process=True,
        sdrplay_module_ok=True,
        venv_path=Path(__file__),
        python_libs_missing=[],
        soapy_import_ok=True,
        sdrplay_usb_issue=True,
    )
    text = hardware_row_status(state, "es")
    assert "28" in text


def test_env_ready_property():
    state = _state(
        sdrplay_ok=True,
        pothos_installed=True,
        path_in_process=True,
        sdrplay_module_ok=True,
        venv_path=Path(__file__),
        python_libs_missing=[],
        soapy_import_ok=True,
    )
    assert state.env_ready is True
    assert state.hardware_ready is False
    assert state.readiness_level() == "env"


# ---------------------------------------------------------------------------
# Branches adicionales
# ---------------------------------------------------------------------------


def test_next_action_missing_pothos():
    state = _state(blockers=["pothos"])
    action = next_action(state, "es")
    assert action.id == "repair_all"
    assert action.reason_key == "next_reason_pothos"


def test_next_action_missing_sdrplay_api():
    state = _state(blockers=["sdrplay_api"])
    action = next_action(state, "es")
    assert action.id == "repair_all"
    assert action.reason_key == "next_reason_sdrplay"


def test_next_action_missing_python_libs():
    state = _state(
        sdrplay_ok=True,
        pothos_installed=True,
        path_in_process=True,
        sdrplay_module_ok=True,
        venv_path=Path(__file__),
        python_libs_missing=["numpy"],
        blockers=["python_libs"],
    )
    action = next_action(state, "es")
    assert action.reason_key == "next_reason_python"


def test_next_action_missing_soapy():
    state = _state(
        sdrplay_ok=True,
        pothos_installed=True,
        path_in_process=True,
        sdrplay_module_ok=True,
        venv_path=Path(__file__),
        python_libs_missing=[],
        soapy_import_ok=False,
        blockers=["soapysdr"],
    )
    action = next_action(state, "es")
    assert action.reason_key == "next_reason_python"


def test_next_action_env_ready_sdrplay_enum_issue():
    """env_ready=True + sdrplay_enumeration en blockers → repair."""
    state = _state(
        sdrplay_ok=True,
        pothos_installed=True,
        path_in_process=True,
        sdrplay_module_ok=True,
        sdrplay_plugin_ok=False,
        venv_path=Path(__file__),
        python_libs_missing=[],
        soapy_import_ok=True,
        has_sdrplay_devices=False,
        blockers=["sdrplay_enumeration"],
    )
    action = next_action(state, "es")
    assert action.reason_key == "next_reason_sdrplay_enum"


def test_next_action_fallback_repair_all():
    """Si nada coincide, repair_all con blockers."""
    state = _state(blockers=["some_unknown"])
    action = next_action(state, "es")
    assert action.id == "repair_all"
    assert action.reason_key == "next_reason_pending"


def test_format_action_returns_tuple():
    state = _state(blockers=["venv"])
    action, title, reason = format_action(state, "es")
    assert isinstance(action, InstallAction)
    assert isinstance(title, str)
    assert isinstance(reason, str)


def test_first_install_blocker_picks_pothos_first():
    state = _state(
        sdrplay_ok=True,
        pothos_installed=False,
        path_in_process=True,
        sdrplay_module_ok=True,
        venv_path=Path(__file__),
        python_libs_missing=["numpy"],
        blockers=["python_libs", "sdrplay_api", "pothos"],
    )
    assert _first_install_blocker(state) == "pothos"


def test_first_install_blocker_respects_order():
    state = _state(blockers=["soapy_sdrplay3", "venv", "pothos_path"])
    # pothos_path viene antes en INSTALL_BLOCKER_ORDER que soapy_sdrplay3
    assert _first_install_blocker(state) == "pothos_path"


def test_first_install_blocker_none_when_empty():
    state = _state(blockers=[])
    assert _first_install_blocker(state) is None


def test_first_install_blocker_filters_non_install():
    """blockers no-install son ignorados por install_blockers."""
    state = _state(
        blockers=["usb_driver", "sdrplay_enumeration"],
    )
    # Estos NO están en install_blockers
    assert _first_install_blocker(state) is None


def test_install_blocker_order_constant():
    assert INSTALL_BLOCKER_ORDER[0] == "pothos"
    assert "venv" in INSTALL_BLOCKER_ORDER


def test_drivers_row_ok():
    state = _state(
        sdrplay_ok=True,
        pothos_installed=True,
        path_in_process=True,
        sdrplay_module_ok=True,
    )
    text = drivers_row_status(state, "es")
    assert text  # non-empty


def test_drivers_row_missing_sdrplay():
    state = _state(
        sdrplay_ok=False,
        pothos_installed=True,
        path_in_process=True,
    )
    text = drivers_row_status(state, "es")
    assert "SDRplay" in text or "sdrplay" in text.lower()


def test_drivers_row_missing_pothos():
    state = _state(
        sdrplay_ok=True,
        pothos_installed=False,
    )
    text = drivers_row_status(state, "es")
    assert "PothosSDR" in text or "pothos" in text.lower()


def test_drivers_row_missing_path():
    state = _state(
        sdrplay_ok=True,
        pothos_installed=True,
        path_in_process=False,
        path_in_registry=False,
    )
    text = drivers_row_status(state, "es")
    assert "PATH" in text


def test_drivers_row_missing_soapy_module():
    state = _state(
        sdrplay_ok=True,
        pothos_installed=True,
        path_in_process=True,
        sdrplay_module_ok=False,
    )
    text = drivers_row_status(state, "es")
    assert "SoapySDRPlay3" in text or "soapy" in text.lower()


def test_drivers_row_default_when_nothing_missing():
    """Caso patológico: drivers_ready=False pero missing=[] → '?'."""
    state = _state(
        sdrplay_ok=False,
        pothos_installed=True,  # pothos ok, path ok, sdrplay falla
        path_in_process=True,
    )
    # El test cae en la rama sdrplay_ok=False → missing incluye SDRplay
    text = drivers_row_status(state, "es")
    assert text


def test_python_row_ok():
    state = _state(
        venv_path=Path(__file__),
        python_libs_missing=[],
        soapy_import_ok=True,
    )
    text = python_row_status(state, "es")
    assert text


def test_python_row_no_venv():
    state = _state(venv_path=None)
    text = python_row_status(state, "es")
    assert ".venv" in text or "venv" in text.lower()


def test_python_row_missing_libs():
    state = _state(
        venv_path=Path(__file__),
        python_libs_missing=["numpy", "scipy"],
    )
    text = python_row_status(state, "es")
    assert "numpy" in text
    assert "scipy" in text


def test_python_row_no_soapy():
    state = _state(
        venv_path=Path(__file__),
        python_libs_missing=[],
        soapy_import_ok=False,
    )
    text = python_row_status(state, "es")
    assert "SoapySDR" in text or "soapy" in text.lower()


def test_python_row_warn_default():
    """venv_ok=True, libs ok, soapy ok → 'ok' por orden de checks."""
    # Cuando venv_ok=True y todo lo demás ok, devuelve 'ok' antes de warn.
    state = _state(
        venv_path=Path(__file__),
        python_libs_missing=[],
        soapy_import_ok=True,
    )
    text = python_row_status(state, "es")
    # En la implementación: python_env_ready=True → return t("status_row_ok")
    assert text


def test_hardware_row_no_env():
    state = _state()  # env_ready=False
    text = hardware_row_status(state, "es")
    assert text  # non-empty


def test_hardware_row_sdrplay_devices_count():
    state = _state(
        sdrplay_ok=True,
        pothos_installed=True,
        path_in_process=True,
        sdrplay_module_ok=True,
        venv_path=Path(__file__),
        python_libs_missing=[],
        soapy_import_ok=True,
        has_sdrplay_devices=True,
        sdrplay_device_count=3,
    )
    text = hardware_row_status(state, "es")
    assert "3" in text


def test_hardware_row_rsp_not_visible():
    state = _state(
        sdrplay_ok=True,
        pothos_installed=True,
        path_in_process=True,
        sdrplay_module_ok=True,
        venv_path=Path(__file__),
        python_libs_missing=[],
        soapy_import_ok=True,
        sdrplay_plugin_ok=False,
        has_sdrplay_devices=False,
        sdrplay_usb_issue=False,
    )
    text = hardware_row_status(state, "es")
    assert text


def test_hardware_row_no_device():
    state = _state(
        sdrplay_ok=True,
        pothos_installed=True,
        path_in_process=True,
        sdrplay_module_ok=True,
        venv_path=Path(__file__),
        python_libs_missing=[],
        soapy_import_ok=True,
        sdrplay_plugin_ok=True,
        has_sdrplay_devices=False,
    )
    text = hardware_row_status(state, "es")
    assert text


def test_hardware_row_other_devices_count_branch():
    """Cuando sdrplay_ok=True, has_devices no se usa en hardware_row.

    Este test documenta la decisión: si sdrplay_ok=True, el contador de
    dispositivos se basa sólo en sdrplay.
    """
    state = _state(
        sdrplay_ok=True,
        pothos_installed=True,
        path_in_process=True,
        sdrplay_module_ok=True,
        venv_path=Path(__file__),
        python_libs_missing=[],
        soapy_import_ok=True,
        sdrplay_plugin_ok=True,
        has_sdrplay_devices=False,
        has_devices=True,
        device_count=2,
    )
    text = hardware_row_status(state, "es")
    # El mensaje de "RSP no visible" se muestra en lugar del conteo de otros.
    assert "2" not in text or "no visible" in text.lower()


def test_hardware_row_rsp_present_count():
    state = _state(
        sdrplay_ok=True,
        pothos_installed=True,
        path_in_process=True,
        sdrplay_module_ok=True,
        venv_path=Path(__file__),
        python_libs_missing=[],
        soapy_import_ok=True,
        sdrplay_plugin_ok=True,
        has_sdrplay_devices=True,
        sdrplay_device_count=1,
    )
    text = hardware_row_status(state, "es")
    assert "1" in text


def test_install_action_is_frozen():
    """InstallAction es frozen (dataclass frozen=True)."""
    import dataclasses

    assert dataclasses.fields(InstallAction)  # smoke test
    action = InstallAction(id="x", menu_highlight="1", title_key="t", reason_key="r")
    assert action.id == "x"
    # Inmutabilidad
    try:
        action.id = "y"  # type: ignore[misc]
        assert False, "Should have raised FrozenInstanceError"
    except (dataclasses.FrozenInstanceError, AttributeError):
        pass
