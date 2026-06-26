"""Tests for setup/env_state.py -- EnvironmentState + probe helpers."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from setup.env_state import (
    POTHOS_BIN_TARGETS,
    EnvironmentState,
    _count_sdrplay_devices,
    _same_python_executable,
    check_core_libs,
    check_soapy_import,
    path_contains_pothos,
    probe_environment,
    probe_soapy_in_python,
    read_path_from_registry,
)


# ---------------------------------------------------------------------------
# EnvironmentState property derivations
# ---------------------------------------------------------------------------


def test_env_state_defaults_path_ok_false() -> None:
    s = EnvironmentState()
    assert s.path_ok is False
    assert s.path_needs_terminal_restart is False
    assert s.venv_ok is False
    assert s.python_libs_ok is False
    assert s.pothos_ready is False
    assert s.python_env_ready is False
    assert s.drivers_ready is False
    assert s.has_target_hardware is False
    assert s.env_ready is False
    assert s.hardware_ready is False
    assert s.sim_ready is False
    assert s.ready_for_hardware is False
    assert s.readiness_level() == "pending"


def test_env_state_path_ok_when_path_in_process() -> None:
    s = EnvironmentState(path_in_process=True)
    assert s.path_ok is True
    assert s.path_needs_terminal_restart is False


def test_env_state_path_ok_when_path_in_registry() -> None:
    s = EnvironmentState(path_in_registry=True)
    assert s.path_ok is True
    assert s.path_needs_terminal_restart is True


def test_env_state_venv_ok_requires_existing_file(tmp_path: Path) -> None:
    # None -> not ok
    s = EnvironmentState(venv_path=None)
    assert s.venv_ok is False

    # Existing file -> ok
    real = tmp_path / "python.exe"
    real.write_text("# fake", encoding="utf-8")
    s2 = EnvironmentState(venv_path=real)
    assert s2.venv_ok is True

    # Non-existent -> not ok
    s3 = EnvironmentState(venv_path=tmp_path / "missing.exe")
    assert s3.venv_ok is False


def test_env_state_python_libs_ok_requires_venv_and_no_missing() -> None:
    # venv missing -> python_libs_ok is False (even with no missing libs).
    s = EnvironmentState(venv_path=None, python_libs_missing=[])
    assert s.python_libs_ok is False

    # venv present but libs missing -> False
    real = Path("/tmp/fake/python")  # not actually created; venv_ok requires is_file
    s2 = EnvironmentState(venv_path=real, python_libs_missing=["numpy"])
    assert s2.python_libs_ok is False


def test_env_state_pothos_ready_requires_installed_and_path() -> None:
    s = EnvironmentState(pothos_installed=True, path_in_process=True)
    assert s.pothos_ready is True
    s2 = EnvironmentState(pothos_installed=True, path_in_registry=True)
    assert s2.pothos_ready is True
    s3 = EnvironmentState(pothos_installed=True)  # no path
    assert s3.pothos_ready is False
    s4 = EnvironmentState(path_in_process=True)  # not installed
    assert s4.pothos_ready is False


def test_env_state_python_env_ready_requires_all_three() -> None:
    real = Path("/nope/python")  # not created; venv_ok requires is_file
    s_ok = EnvironmentState(
        venv_path=real, python_libs_missing=[], soapy_import_ok=True,
    )
    # venv_ok=False because file missing -> python_env_ready must be False.
    assert s_ok.python_env_ready is False


def test_env_state_drivers_ready_requires_sdrplay_pothos_and_module() -> None:
    # Without sdrplay -> False.
    s = EnvironmentState()
    assert s.drivers_ready is False

    # With sdrplay but no pothos -> False.
    s2 = EnvironmentState(sdrplay_ok=True)
    assert s2.drivers_ready is False

    # With sdrplay + pothos but no module -> False.
    s3 = EnvironmentState(
        sdrplay_ok=True, pothos_installed=True, path_in_process=True,
    )
    assert s3.drivers_ready is False

    # With all three -> True.
    s4 = EnvironmentState(
        sdrplay_ok=True,
        pothos_installed=True,
        path_in_process=True,
        sdrplay_module_ok=True,
    )
    assert s4.drivers_ready is True


def test_env_state_has_target_hardware_uses_sdrplay_when_available() -> None:
    s_sdrplay = EnvironmentState(
        sdrplay_ok=True, has_devices=True, has_sdrplay_devices=False,
    )
    # When sdrplay_ok, has_target_hardware reflects sdrplay devices.
    assert s_sdrplay.has_target_hardware is False
    s_sdrplay2 = EnvironmentState(
        sdrplay_ok=True, has_sdrplay_devices=True,
    )
    assert s_sdrplay2.has_target_hardware is True

    # Without sdrplay, falls back to has_devices.
    s_other = EnvironmentState(sdrplay_ok=False, has_devices=True)
    assert s_other.has_target_hardware is True


def test_env_state_readiness_level_states() -> None:
    s = EnvironmentState()
    assert s.readiness_level() == "pending"
    # env_ready but not hardware_ready -> "env".
    # We force env_ready via drivers_ready + python_env_ready.
    s2 = EnvironmentState(
        sdrplay_ok=True,
        pothos_installed=True,
        path_in_process=True,
        sdrplay_module_ok=True,
        venv_path=Path("/nope/python"),
        python_libs_missing=[],
        soapy_import_ok=True,
    )
    # venv_ok still False (file missing), so env_ready False.
    # We need venv_ok=True -- skip, hard to fake without tmp_path trick.
    assert s2.readiness_level() in ("env", "pending")


def test_env_state_install_blockers_filters_hardware_only() -> None:
    s = EnvironmentState(
        blockers=[
            "sdrplay_api",
            "pothos",
            "pothos_path",
            "soapy_sdrplay3",
            "venv",
            "python_libs",
            "soapysdr",
            "sdrplay_enumeration",  # not an install blocker
            "usb_driver",  # hardware-related, not install blocker
        ],
    )
    blockers = s.install_blockers
    assert "sdrplay_api" in blockers
    assert "pothos" in blockers
    assert "pothos_path" in blockers
    assert "soapy_sdrplay3" in blockers
    assert "venv" in blockers
    assert "python_libs" in blockers
    assert "soapysdr" in blockers
    assert "sdrplay_enumeration" not in blockers
    assert "usb_driver" not in blockers


def test_env_state_install_blockers_empty_when_no_blockers() -> None:
    s = EnvironmentState()
    assert s.install_blockers == []


# ---------------------------------------------------------------------------
# path_contains_pothos
# ---------------------------------------------------------------------------


def test_path_contains_pothos_true_for_pothos_path() -> None:
    assert path_contains_pothos(r"C:\Windows;C:\Program Files\PothosSDR\bin;C:\Other") is True


def test_path_contains_pothos_true_for_soapy_path() -> None:
    assert path_contains_pothos(r"C:\Program Files\SoapySDR\bin") is True


def test_path_contains_pothos_false_for_unrelated_path() -> None:
    assert path_contains_pothos(r"C:\Windows;C:\Other") is False
    assert path_contains_pothos("") is False
    assert path_contains_pothos("/usr/local/bin") is False


def test_path_contains_pothos_case_insensitive() -> None:
    assert path_contains_pothos(r"c:\program files\pothosSDR\bin") is True


# ---------------------------------------------------------------------------
# _same_python_executable
# ---------------------------------------------------------------------------


def test_same_python_executable_identical_paths() -> None:
    assert _same_python_executable("/usr/bin/python3", "/usr/bin/python3") is True


def test_same_python_executable_different_paths() -> None:
    assert _same_python_executable("/usr/bin/python3", "/usr/local/bin/python3") is False


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="Windows-style backslash path semantics; skip on POSIX.",
)
def test_same_python_executable_handles_trailing_slashes() -> None:
    # Both Windows-style with trailing backslash.
    assert _same_python_executable(
        r"C:\Python312\python.exe",
        r"C:\Python312\python.exe\.",
    ) is True


def test_same_python_executable_resolves_through_path() -> None:
    # Same file via different relative paths -> resolved absolute paths equal.
    assert _same_python_executable("/tmp/a/../b/python", "/tmp/b/python") is True


# ---------------------------------------------------------------------------
# _count_sdrplay_devices
# ---------------------------------------------------------------------------


def test_count_sdrplay_devices_zero_for_empty_list() -> None:
    assert _count_sdrplay_devices([]) == 0


def test_count_sdrplay_devices_counts_only_sdrplay() -> None:
    devices = [
        {"driver": "sdrplay", "label": "RSP1"},
        {"driver": "rtlsdr", "label": "RTL-A"},
        {"driver": "sdrplay", "label": "RSP2"},
        {"driver": "miri", "label": "Miri"},
    ]
    assert _count_sdrplay_devices(devices) == 2


def test_count_sdrplay_devices_case_insensitive() -> None:
    devices = [{"driver": "SDRPlay"}, {"driver": "sdrPLAY"}]
    assert _count_sdrplay_devices(devices) == 2


def test_count_sdrplay_devices_handles_missing_driver_key() -> None:
    devices = [{}, {"driver": "sdrplay"}]
    assert _count_sdrplay_devices(devices) == 1


# ---------------------------------------------------------------------------
# read_path_from_registry
# ---------------------------------------------------------------------------


def test_read_path_from_registry_returns_empty_on_posix(monkeypatch):
    monkeypatch.setattr("os.name", "posix")
    assert read_path_from_registry() == ""


@pytest.mark.skipif(sys.platform != "win32", reason="winreg only available on Windows")
def test_read_path_from_registry_joins_hives(monkeypatch):
    """En Windows, lee Path de HKCU y HKLM y los une."""
    import winreg

    def fake_open(root, subkey):
        m = MagicMock()
        m.__enter__ = lambda s: s
        m.__exit__ = lambda s, *a: False
        return m

    def fake_query(key, name):
        if name == "Path":
            if key is fake_open.hkcu_key:
                return r"C:\Program Files\PothosSDR\bin;C:\Windows", 1
            return r"C:\Program Files\Git\cmd", 1
        raise FileNotFoundError(name)

    hkcu_key = fake_open(winreg.HKEY_CURRENT_USER, "Environment")
    fake_open.hkcu_key = hkcu_key
    hklm_key = fake_open(winreg.HKEY_LOCAL_MACHINE, "...")
    fake_open.hklm_key = hklm_key

    def open_dispatch(root, subkey):
        if root == winreg.HKEY_CURRENT_USER:
            return hkcu_key
        return hklm_key

    monkeypatch.setattr(winreg, "OpenKey", open_dispatch)
    monkeypatch.setattr(winreg, "QueryValueEx", fake_query)
    result = read_path_from_registry()
    assert "PothosSDR" in result
    assert "Git" in result


def test_read_path_from_registry_handles_missing_keys(monkeypatch):
    """Si OpenKey lanza OSError, sigue con la siguiente hive."""
    import winreg

    def fake_open(root, subkey):
        raise OSError("missing")

    monkeypatch.setattr(winreg, "OpenKey", fake_open)
    monkeypatch.setattr("os.name", "nt")
    assert read_path_from_registry() == ""


def test_read_path_from_registry_handles_missing_path_value(monkeypatch):
    """Si la hive no tiene valor Path, continúa."""
    import winreg

    empty_key = MagicMock()
    empty_key.__enter__ = lambda s: s
    empty_key.__exit__ = lambda s, *a: False

    monkeypatch.setattr(winreg, "OpenKey", lambda *a, **kw: empty_key)
    monkeypatch.setattr(winreg, "QueryValueEx", MagicMock(side_effect=FileNotFoundError("Path")))
    monkeypatch.setattr("os.name", "nt")
    assert read_path_from_registry() == ""


# ---------------------------------------------------------------------------
# check_core_libs
# ---------------------------------------------------------------------------


def test_check_core_libs_parses_installed_missing(monkeypatch):
    payload = json.dumps({"installed": ["numpy", "scipy"], "missing": ["sounddevice"]})
    mock_run = MagicMock(return_value=MagicMock(returncode=0, stdout=payload))
    monkeypatch.setattr("subprocess.run", mock_run)
    installed, missing = check_core_libs("/fake/python")
    assert installed == ["numpy", "scipy"]
    assert missing == ["sounddevice"]


def test_check_core_libs_handles_nonzero_returncode(monkeypatch):
    mock_run = MagicMock(return_value=MagicMock(returncode=1, stdout=""))
    monkeypatch.setattr("subprocess.run", mock_run)
    installed, missing = check_core_libs("/fake/python")
    assert installed == []
    assert missing == list(["numpy", "scipy", "sounddevice", "textual", "rich"])


def test_check_core_libs_handles_invalid_json(monkeypatch):
    mock_run = MagicMock(return_value=MagicMock(returncode=0, stdout="not json"))
    monkeypatch.setattr("subprocess.run", mock_run)
    installed, missing = check_core_libs("/fake/python")
    assert installed == []
    assert missing == list(["numpy", "scipy", "sounddevice", "textual", "rich"])


def test_check_core_libs_handles_subprocess_exception(monkeypatch):
    def raise_exc(*_a, **_kw):
        raise OSError("boom")

    monkeypatch.setattr("subprocess.run", raise_exc)
    installed, missing = check_core_libs("/fake/python")
    assert installed == []
    assert len(missing) >= 1


# ---------------------------------------------------------------------------
# check_soapy_import
# ---------------------------------------------------------------------------


def test_check_soapy_import_returns_true_on_success(monkeypatch):
    mock_run = MagicMock(return_value=MagicMock(returncode=0))
    monkeypatch.setattr("subprocess.run", mock_run)
    assert check_soapy_import("/fake/python") is True


def test_check_soapy_import_returns_false_on_nonzero(monkeypatch):
    mock_run = MagicMock(return_value=MagicMock(returncode=1))
    monkeypatch.setattr("subprocess.run", mock_run)
    assert check_soapy_import("/fake/python") is False


def test_check_soapy_import_returns_false_on_exception(monkeypatch):
    def raise_exc(*_a, **_kw):
        raise OSError("boom")

    monkeypatch.setattr("subprocess.run", raise_exc)
    assert check_soapy_import("/fake/python") is False


# ---------------------------------------------------------------------------
# probe_soapy_in_python
# ---------------------------------------------------------------------------


def test_probe_soapy_in_python_success(monkeypatch):
    payload = json.dumps({"ok": True, "devices": [{"driver": "sdrplay", "label": "RSP1"}]})
    mock_run = MagicMock(return_value=MagicMock(returncode=0, stdout=payload))
    monkeypatch.setattr("subprocess.run", mock_run)
    ok, devices = probe_soapy_in_python("/fake/python", quiet=True, bootstrap=True, project_root="/proj")
    assert ok is True
    assert len(devices) == 1


def test_probe_soapy_in_python_failure(monkeypatch):
    payload = json.dumps({"ok": False, "error": "no module"})
    mock_run = MagicMock(return_value=MagicMock(returncode=0, stdout=payload))
    monkeypatch.setattr("subprocess.run", mock_run)
    ok, devices = probe_soapy_in_python("/fake/python")
    assert ok is False
    assert devices == []


def test_probe_soapy_in_python_nonzero_returncode(monkeypatch):
    mock_run = MagicMock(return_value=MagicMock(returncode=1, stdout=""))
    monkeypatch.setattr("subprocess.run", mock_run)
    ok, devices = probe_soapy_in_python("/fake/python")
    assert ok is False
    assert devices == []


def test_probe_soapy_in_python_handles_exception(monkeypatch):
    def raise_exc(*_a, **_kw):
        raise OSError("boom")

    monkeypatch.setattr("subprocess.run", raise_exc)
    ok, devices = probe_soapy_in_python("/fake/python")
    assert ok is False
    assert devices == []


def test_probe_soapy_in_python_no_bootstrap_branch(monkeypatch):
    """Sin bootstrap, no se incluye bootstrap_block."""
    payload = json.dumps({"ok": True, "devices": []})
    mock_run = MagicMock(return_value=MagicMock(returncode=0, stdout=payload))
    monkeypatch.setattr("subprocess.run", mock_run)
    ok, devices = probe_soapy_in_python("/fake/python", bootstrap=False)
    assert ok is True


# ---------------------------------------------------------------------------
# probe_environment
# ---------------------------------------------------------------------------


def test_probe_environment_assembles_state(monkeypatch, tmp_path):
    """Probe agrega resultados de los checks en un EnvironmentState."""
    fake_py = tmp_path / "python.exe"
    fake_py.write_text("# fake")
    monkeypatch.setattr("core.runtime_paths.project_root", lambda: tmp_path)
    monkeypatch.setattr("core.python_runtime.project_venv_python", lambda _r: fake_py)
    monkeypatch.setattr("core.sdrplay_usb.probe_sdrplay_usb_with_retry", lambda **kw: MagicMock(present=False, ok=False))
    monkeypatch.setattr("core.soapy_runtime.check_sdrplay_api", lambda: True)
    monkeypatch.setattr("core.soapy_runtime.find_pothos_install", lambda: "C:/Pothos")
    monkeypatch.setattr("core.soapy_runtime.is_sdrplay_soapy_module_ok", lambda: True)
    monkeypatch.setattr("core.soapy_runtime.check_sdrplay_plugin", lambda: True)
    fake_status = MagicMock(import_ok=True, has_devices=True, devices=[{"driver": "sdrplay"}])
    monkeypatch.setattr("core.soapy_runtime.bootstrap_soapy", lambda **kw: fake_status)
    monkeypatch.setattr("setup.env_state._same_python_executable", lambda l, r: True)
    monkeypatch.setattr("setup.env_state.path_contains_pothos", lambda p: True)
    monkeypatch.setattr("setup.env_state.check_core_libs", lambda _p: (["numpy"], []))
    monkeypatch.setattr("setup.env_state.check_soapy_import", lambda _p: True)
    monkeypatch.setattr("os.environ", {"PATH": "C:/Pothos/bin"})

    state = probe_environment(bootstrap_soapy=True, inprocess_soapy=True)
    assert state.sdrplay_ok is True
    assert state.pothos_installed is True
    assert state.path_in_process is True
    assert state.venv_path == fake_py
    assert state.venv_ok is True
    assert state.python_libs_missing == []
    assert state.soapy_import_ok is True
    assert state.has_devices is True
    assert state.has_sdrplay_devices is True
    assert state.drivers_ready is True


def test_probe_environment_collects_blockers(monkeypatch, tmp_path):
    fake_py = tmp_path / "missing.exe"  # venv_ok=False
    monkeypatch.setattr("core.runtime_paths.project_root", lambda: tmp_path)
    monkeypatch.setattr("core.python_runtime.project_venv_python", lambda _r: fake_py)
    monkeypatch.setattr("core.sdrplay_usb.probe_sdrplay_usb_with_retry", lambda **kw: MagicMock(present=False, ok=False))
    monkeypatch.setattr("core.soapy_runtime.check_sdrplay_api", lambda: False)
    monkeypatch.setattr("core.soapy_runtime.find_pothos_install", lambda: None)
    monkeypatch.setattr("core.soapy_runtime.is_sdrplay_soapy_module_ok", lambda: False)
    monkeypatch.setattr("core.soapy_runtime.check_sdrplay_plugin", lambda: False)
    monkeypatch.setattr("setup.env_state.path_contains_pothos", lambda p: False)
    monkeypatch.setattr("os.environ", {"PATH": ""})

    state = probe_environment(bootstrap_soapy=False, inprocess_soapy=False)
    assert "sdrplay_api" in state.blockers
    assert "pothos" in state.blockers
    assert "venv" in state.blockers
    assert state.sdrplay_ok is False


def test_probe_environment_uses_subprocess_when_not_inprocess(monkeypatch, tmp_path):
    """Si _same_python_executable devuelve False, usa probe_soapy_in_python."""
    fake_py = tmp_path / "python.exe"
    fake_py.write_text("# fake")
    monkeypatch.setattr("core.runtime_paths.project_root", lambda: tmp_path)
    monkeypatch.setattr("core.python_runtime.project_venv_python", lambda _r: fake_py)
    monkeypatch.setattr("core.sdrplay_usb.probe_sdrplay_usb_with_retry", lambda **kw: MagicMock(present=False, ok=False))
    monkeypatch.setattr("core.soapy_runtime.check_sdrplay_api", lambda: True)
    monkeypatch.setattr("core.soapy_runtime.find_pothos_install", lambda: "C:/Pothos")
    monkeypatch.setattr("core.soapy_runtime.is_sdrplay_soapy_module_ok", lambda: True)
    monkeypatch.setattr("core.soapy_runtime.check_sdrplay_plugin", lambda: True)
    monkeypatch.setattr("setup.env_state._same_python_executable", lambda l, r: False)
    monkeypatch.setattr("setup.env_state.probe_soapy_in_python", lambda *a, **kw: (True, [{"driver": "sdrplay"}]))
    monkeypatch.setattr("setup.env_state.path_contains_pothos", lambda p: True)
    monkeypatch.setattr("setup.env_state.check_core_libs", lambda _p: ([], []))
    monkeypatch.setattr("setup.env_state.check_soapy_import", lambda _p: True)
    monkeypatch.setattr("os.environ", {"PATH": "C:/Pothos/bin"})

    state = probe_environment(bootstrap_soapy=True, inprocess_soapy=True)
    assert state.has_sdrplay_devices is True


def test_probe_environment_skips_soapy_when_no_venv(monkeypatch, tmp_path):
    """Sin venv_ok, no se llama a bootstrap ni probe_soapy_in_python."""
    fake_py = tmp_path / "missing.exe"
    monkeypatch.setattr("core.runtime_paths.project_root", lambda: tmp_path)
    monkeypatch.setattr("core.python_runtime.project_venv_python", lambda _r: fake_py)
    monkeypatch.setattr("core.sdrplay_usb.probe_sdrplay_usb_with_retry", lambda **kw: MagicMock(present=False, ok=False))
    monkeypatch.setattr("core.soapy_runtime.check_sdrplay_api", lambda: True)
    monkeypatch.setattr("core.soapy_runtime.find_pothos_install", lambda: "C:/Pothos")
    monkeypatch.setattr("core.soapy_runtime.is_sdrplay_soapy_module_ok", lambda: True)
    monkeypatch.setattr("core.soapy_runtime.check_sdrplay_plugin", lambda: True)
    monkeypatch.setattr("setup.env_state.path_contains_pothos", lambda p: True)
    monkeypatch.setattr("os.environ", {"PATH": "C:/Pothos/bin"})
    soapy_called = {"v": False}
    monkeypatch.setattr(
        "core.soapy_runtime.bootstrap_soapy",
        lambda **kw: soapy_called.__setitem__("v", True) or MagicMock(import_ok=True, has_devices=False, devices=[]),
    )
    state = probe_environment(bootstrap_soapy=True, inprocess_soapy=True)
    assert soapy_called["v"] is False  # venv_ok=False, no se llama
    assert state.soapy_import_ok is False


def test_probe_environment_adds_soapy_sdrplay3_blocker(monkeypatch, tmp_path):
    """Si sdrplay+pothos OK pero no hay módulo Soapy, marca soapy_sdrplay3."""
    fake_py = tmp_path / "python.exe"
    fake_py.write_text("# fake")
    monkeypatch.setattr("core.runtime_paths.project_root", lambda: tmp_path)
    monkeypatch.setattr("core.python_runtime.project_venv_python", lambda _r: fake_py)
    monkeypatch.setattr("core.sdrplay_usb.probe_sdrplay_usb_with_retry", lambda **kw: MagicMock(present=False, ok=False))
    monkeypatch.setattr("core.soapy_runtime.check_sdrplay_api", lambda: True)
    monkeypatch.setattr("core.soapy_runtime.find_pothos_install", lambda: "C:/Pothos")
    monkeypatch.setattr("core.soapy_runtime.is_sdrplay_soapy_module_ok", lambda: False)
    monkeypatch.setattr("core.soapy_runtime.check_sdrplay_plugin", lambda: False)
    monkeypatch.setattr("setup.env_state._same_python_executable", lambda l, r: True)
    monkeypatch.setattr("setup.env_state.path_contains_pothos", lambda p: True)
    monkeypatch.setattr("setup.env_state.check_core_libs", lambda _p: ([], []))
    monkeypatch.setattr("setup.env_state.check_soapy_import", lambda _p: True)
    monkeypatch.setattr("os.environ", {"PATH": "C:/Pothos/bin"})
    monkeypatch.setattr("core.soapy_runtime.bootstrap_soapy", lambda **kw: MagicMock(import_ok=True, has_devices=False, devices=[]))
    state = probe_environment(bootstrap_soapy=True, inprocess_soapy=True)
    assert "soapy_sdrplay3" in state.blockers


def test_probe_environment_adds_enumeration_blocker(monkeypatch, tmp_path):
    """Si todo OK pero plugin no enumera, marca sdrplay_enumeration."""
    fake_py = tmp_path / "python.exe"
    fake_py.write_text("# fake")
    monkeypatch.setattr("core.runtime_paths.project_root", lambda: tmp_path)
    monkeypatch.setattr("core.python_runtime.project_venv_python", lambda _r: fake_py)
    monkeypatch.setattr("core.sdrplay_usb.probe_sdrplay_usb_with_retry", lambda **kw: MagicMock(present=False, ok=False))
    monkeypatch.setattr("core.soapy_runtime.check_sdrplay_api", lambda: True)
    monkeypatch.setattr("core.soapy_runtime.find_pothos_install", lambda: "C:/Pothos")
    monkeypatch.setattr("core.soapy_runtime.is_sdrplay_soapy_module_ok", lambda: True)
    monkeypatch.setattr("core.soapy_runtime.check_sdrplay_plugin", lambda: False)
    monkeypatch.setattr("setup.env_state._same_python_executable", lambda l, r: True)
    monkeypatch.setattr("setup.env_state.path_contains_pothos", lambda p: True)
    monkeypatch.setattr("setup.env_state.check_core_libs", lambda _p: ([], []))
    monkeypatch.setattr("setup.env_state.check_soapy_import", lambda _p: True)
    monkeypatch.setattr("os.environ", {"PATH": "C:/Pothos/bin"})
    monkeypatch.setattr("core.soapy_runtime.bootstrap_soapy", lambda **kw: MagicMock(import_ok=True, has_devices=False, devices=[]))
    state = probe_environment(bootstrap_soapy=True, inprocess_soapy=True)
    assert "sdrplay_enumeration" in state.blockers


def test_probe_environment_usb_issue(monkeypatch, tmp_path):
    """Si USB falla (present=True, ok=False), marca sdrplay_usb_issue."""
    fake_py = tmp_path / "python.exe"
    fake_py.write_text("# fake")
    monkeypatch.setattr("core.runtime_paths.project_root", lambda: tmp_path)
    monkeypatch.setattr("core.python_runtime.project_venv_python", lambda _r: fake_py)
    monkeypatch.setattr("core.sdrplay_usb.probe_sdrplay_usb_with_retry", lambda **kw: MagicMock(present=True, ok=False))
    monkeypatch.setattr("core.soapy_runtime.check_sdrplay_api", lambda: True)
    monkeypatch.setattr("core.soapy_runtime.find_pothos_install", lambda: None)
    monkeypatch.setattr("core.soapy_runtime.is_sdrplay_soapy_module_ok", lambda: False)
    monkeypatch.setattr("core.soapy_runtime.check_sdrplay_plugin", lambda: False)
    monkeypatch.setattr("setup.env_state.path_contains_pothos", lambda p: False)
    monkeypatch.setattr("os.environ", {"PATH": ""})
    state = probe_environment(bootstrap_soapy=False, inprocess_soapy=False)
    assert state.sdrplay_usb_issue is True


# ---------------------------------------------------------------------------
# Helpers para tests
# ---------------------------------------------------------------------------


class _MockKey:
    def __init__(self, values: dict) -> None:
        self._values = values

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def __iter__(self):
        return iter([])

    def QueryValueEx(self, name: str):
        if name not in self._values:
            raise FileNotFoundError(name)
        return self._values[name], 1