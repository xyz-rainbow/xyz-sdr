"""Tests de core/soapy_runtime.py (checker sdrplay)."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest

from core.soapy_runtime import (
    _parse_sdrplay_find_stdout,
    _soapy_util_executable,
    assess_sdrplay_soapy_module,
    check_sdrplay_plugin,
    check_sdrplay_service_running,
    find_sdrplay_api_bin,
    find_sdrplay_soapy_module,
    is_sdrplay_soapy_module_ok,
)

SUCCESS_STDOUT = """
Found device 0
  driver = sdrplay
  label = SDRplay Dev0 RSP1 0000000001
  serial = 0000000001
"""

FAIL_STDOUT = "No devices found! driver=sdrplay\n"

ERROR_STDERR = """
[ERROR] sdrplay_api_Open() Error: sdrplay_api_Fail
[ERROR] SoapySDR::Device::enumerate(sdrplay) sdrplay_api_Open() failed
"""


def test_parse_sdrplay_find_stdout_accepts_found_device():
    assert _parse_sdrplay_find_stdout(SUCCESS_STDOUT) is True


def test_parse_sdrplay_find_stdout_rejects_no_devices():
    assert _parse_sdrplay_find_stdout(FAIL_STDOUT) is False


def test_parse_sdrplay_find_stdout_rejects_empty():
    assert _parse_sdrplay_find_stdout("") is False


def test_check_sdrplay_plugin_ignores_stderr_errors(monkeypatch):
    mock_run = MagicMock(
        return_value=MagicMock(
            stdout="",
            stderr=ERROR_STDERR,
            returncode=-1073741819,
        )
    )
    monkeypatch.setattr("core.soapy_runtime.subprocess.run", mock_run)
    assert check_sdrplay_plugin() is False


def test_check_sdrplay_plugin_accepts_stdout_match(monkeypatch):
    mock_run = MagicMock(
        return_value=MagicMock(
            stdout=SUCCESS_STDOUT,
            stderr="[WARNING] SoapyVOLKConverters: no VOLK config file found.\n",
            returncode=0,
        )
    )
    monkeypatch.setattr("core.soapy_runtime.subprocess.run", mock_run)
    assert check_sdrplay_plugin() is True


def test_check_sdrplay_service_running_detects_running(monkeypatch):
    mock_run = MagicMock(
        return_value=MagicMock(
            returncode=0,
            stdout="STATE              : 4  RUNNING\n",
        )
    )
    monkeypatch.setattr("core.soapy_runtime.subprocess.run", mock_run)
    assert check_sdrplay_service_running() is True


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="check_sdrplay_service_running usa 'sc query SDRplayAPIService', Windows-only.",
)
def test_check_sdrplay_service_running_detects_stopped(monkeypatch):
    mock_run = MagicMock(
        return_value=MagicMock(
            returncode=0,
            stdout="STATE              : 1  STOPPED\n",
        )
    )
    monkeypatch.setattr("core.soapy_runtime.subprocess.run", mock_run)
    assert check_sdrplay_service_running() is False


def test_find_sdrplay_soapy_module_detects_dll(tmp_path, monkeypatch):
    pothos = tmp_path / "PothosSDR"
    mod_dir = pothos / "lib" / "SoapySDR" / "modules0.8"
    mod_dir.mkdir(parents=True)
    module = mod_dir / "SoapySDRPlay3.dll"
    module.write_bytes(b"")
    monkeypatch.setattr("core.soapy_runtime.find_pothos_install", lambda: str(pothos))
    found = find_sdrplay_soapy_module(str(pothos))
    assert found == str(module)


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="Pothos installer y naming SoapySDRUtil.exe es Windows-only.",
)
def test_soapy_util_prefers_pothos_binary(tmp_path, monkeypatch):
    pothos = tmp_path / "PothosSDR"
    bin_dir = pothos / "bin"
    bin_dir.mkdir(parents=True)
    util = bin_dir / "SoapySDRUtil.exe"
    util.write_bytes(b"")
    monkeypatch.setattr("core.soapy_runtime.find_pothos_install", lambda: str(pothos))
    # bundled_soapy_util debe devolver None para que la rama pothos sea la candidata.
    # Sin este mock el bundled real (drivers/win-x64/soapy/SoapySDRUtil.exe) gana.
    # NOTA: la función hace `from core.driver_runtime import bundled_soapy_util` dentro,
    # así que el patch debe ir al módulo de origen.
    monkeypatch.setattr("core.driver_runtime.bundled_soapy_util", lambda: None)
    assert _soapy_util_executable() == str(util)


def test_find_sdrplay_api_bin_prefers_x64_on_amd64(tmp_path, monkeypatch):
    api_root = tmp_path / "SDRplay" / "API"
    (api_root / "arm64").mkdir(parents=True)
    (api_root / "x64").mkdir(parents=True)
    (api_root / "arm64" / "sdrplay_api.dll").write_bytes(b"arm")
    (api_root / "x64" / "sdrplay_api.dll").write_bytes(b"x64")

    def fake_isdir(path: str) -> bool:
        norm = path.replace("\\", "/")
        if norm.endswith("SDRplay") or norm.endswith("SDRplay/API"):
            return True
        return False

    def fake_walk(root: str):
        if root.endswith("SDRplay"):
            yield str(api_root), ["arm64", "x64"], []
            for sub in ("arm64", "x64"):
                yield str(api_root / sub), [], ["sdrplay_api.dll"]

    monkeypatch.setattr("core.soapy_runtime.os.path.isdir", fake_isdir)
    monkeypatch.setattr("core.soapy_runtime.os.walk", lambda r: fake_walk(r))
    monkeypatch.setattr("core.soapy_runtime.is_python_64bit", lambda: True)
    assert find_sdrplay_api_bin().replace("\\", "/").endswith("SDRplay/API/x64")


def test_assess_sdrplay_soapy_module_legacy_by_mtime(tmp_path):
    module = tmp_path / "sdrPlaySupport.dll"
    module.write_bytes(b"old")
    import os

    os.utime(module, (1_000_000_000, 1_000_000_000))
    assert assess_sdrplay_soapy_module(str(module)) == "legacy"


def test_assess_sdrplay_soapy_module_present_when_recent(tmp_path):
    module = tmp_path / "sdrPlaySupport.dll"
    module.write_bytes(b"new-plugin")
    assert assess_sdrplay_soapy_module(str(module)) == "present"


def test_find_sdrplay_module_prefers_non_legacy(tmp_path, monkeypatch):
    legacy_dir = tmp_path / "legacy"
    user_dir = tmp_path / "user"
    legacy_dir.mkdir()
    user_dir.mkdir()
    legacy = legacy_dir / "sdrPlaySupport.dll"
    current = user_dir / "sdrPlaySupport.dll"
    legacy.write_bytes(b"old")
    current.write_bytes(b"new")
    import os

    os.utime(legacy, (1_000_000_000, 1_000_000_000))

    monkeypatch.setattr("core.soapy_runtime.user_soapy_plugin_dir", lambda: str(user_dir))
    monkeypatch.setattr(
        "core.soapy_runtime.soapy_plugin_search_dirs",
        lambda _root=None: [str(user_dir), str(legacy_dir)],
    )
    chosen = find_sdrplay_soapy_module()
    assert chosen == str(current)


def test_is_sdrplay_soapy_module_ok_with_recent_dll(tmp_path, monkeypatch):
    user_dir = tmp_path / "user"
    user_dir.mkdir()
    module = user_dir / "sdrPlaySupport.dll"
    module.write_bytes(b"new-plugin")
    monkeypatch.setattr("core.soapy_runtime.user_soapy_plugin_dir", lambda: str(user_dir))
    monkeypatch.setattr(
        "core.soapy_runtime.soapy_plugin_search_dirs",
        lambda _root=None: [str(user_dir)],
    )
    assert is_sdrplay_soapy_module_ok() is True
