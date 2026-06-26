"""Tests de core/soapy_runtime.py (checker sdrplay + helpers puros)."""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import pytest

from core.soapy_runtime import (
    SoapyStatus,
    _API_FAULT_MARKERS,
    _LEGACY_SDRPLAY_MODULE_CUTOFF,
    _allow_pothos_plugins,
    _copy_if_newer,
    _disable_stale_pothos_api_dll,
    _iter_sdrplay_module_paths,
    _parse_sdrplay_find_stdout,
    _prepend_path,
    _prepend_sys_path,
    _preferred_sdrplay_api_subdirs,
    _score_sdrplay_api_dir,
    _soapy_pip_supported,
    _soapy_util_executable,
    _SDRPLAY_SOAPY_MODULE_HINTS,
    assess_sdrplay_soapy_module,
    check_sdrplay_plugin,
    check_sdrplay_service_running,
    clear_soapy_bootstrap_cache,
    find_sdrplay_api_bin,
    find_sdrplay_soapy_module,
    is_python_64bit,
    is_sdrplay_soapy_module_ok,
    list_pothos_python_versions,
    message_indicates_sdrplay_api_fault,
    user_soapy_plugin_dir,
    user_xyz_sdr_bin_dir,
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


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_soapy_status_defaults_empty():
    status = SoapyStatus()
    assert status.import_ok is False
    assert status.devices == []
    assert status.has_devices is False
    assert status.sdrplay_plugin_status == "missing"
    assert status.sdrplay_plugin_module_ok is False


def test_soapy_status_has_devices_true_when_non_empty():
    status = SoapyStatus(devices=[{"driver": "sdrplay"}])
    assert status.has_devices is True


def test_soapy_status_plugin_module_ok_when_present():
    status = SoapyStatus(sdrplay_plugin_status="present")
    assert status.sdrplay_plugin_module_ok is True


def test_constants_exposed():
    assert isinstance(_API_FAULT_MARKERS, tuple)
    assert "servicenotresponding" in _API_FAULT_MARKERS
    assert "sdrplayapiopenfail" in _API_FAULT_MARKERS
    assert isinstance(_SDRPLAY_SOAPY_MODULE_HINTS, tuple)
    assert "sdrplay" in _SDRPLAY_SOAPY_MODULE_HINTS
    assert _LEGACY_SDRPLAY_MODULE_CUTOFF > 1_000_000_000


def test_preferred_sdrplay_api_subdirs_64bit():
    assert "x64" in _preferred_sdrplay_api_subdirs()


def test_preferred_sdrplay_api_subdirs_32bit(monkeypatch):
    monkeypatch.setattr("core.soapy_runtime.is_python_64bit", lambda: False)
    subs = _preferred_sdrplay_api_subdirs()
    assert "x86" in subs


def test_score_sdrplay_api_dir_arm64_negative():
    assert _score_sdrplay_api_dir(r"C:\Program Files\SDRplay\API\arm64") < 0
    assert _score_sdrplay_api_dir(r"C:\Program Files\SDRplay\API\aarch64") < 0


def test_score_sdrplay_api_dir_x64_higher_than_arm64():
    arm = _score_sdrplay_api_dir(r"C:\Program Files\SDRplay\API\arm64")
    x64 = _score_sdrplay_api_dir(r"C:\Program Files\SDRplay\API\x64")
    assert x64 > arm >= -100


def test_score_sdrplay_api_dir_unscored_returns_zero():
    assert _score_sdrplay_api_dir(r"C:\random\path\weird") == 0


def test_message_indicates_sdrplay_api_fault_match():
    assert message_indicates_sdrplay_api_fault("sdrplay_api_Open() Error: SDRplayAPIServiceNotResponding") is True


def test_message_indicates_sdrplay_api_fault_ignores_underscores_spaces():
    assert message_indicates_sdrplay_api_fault("sdrplay api open fail detected") is True
    assert message_indicates_sdrplay_api_fault("sdrplay_api_open_fail") is True


def test_message_indicates_sdrplay_api_fault_false_for_unrelated():
    assert message_indicates_sdrplay_api_fault("permission denied") is False
    assert message_indicates_sdrplay_api_fault("") is False
    assert message_indicates_sdrplay_api_fault("audio buffer underrun") is False


def test_soapy_pip_supported_known_value():
    """_soapy_pip_supported sólo depende de sys.version_info."""
    if sys.version_info < (3, 13):
        assert _soapy_pip_supported() is True
    else:
        assert _soapy_pip_supported() is False


def test_is_python_64bit_matches_struct():
    import struct

    expected = struct.calcsize("P") * 8 == 64
    assert is_python_64bit() is expected


def test_clear_soapy_bootstrap_cache_resets(monkeypatch):
    """clear_soapy_bootstrap_cache debe permitir re-bootstrap."""
    clear_soapy_bootstrap_cache()
    # Llamarlo de nuevo es idempotente.
    clear_soapy_bootstrap_cache()


def test_prepend_path_skips_empty(monkeypatch):
    saved = os.environ.get("PATH")
    try:
        _prepend_path("")
        _prepend_path("/definitely/not/a/real/dir/xyz_sdr_test")
        assert os.environ.get("PATH") == saved
    finally:
        if saved is not None:
            os.environ["PATH"] = saved


def test_prepend_path_prepends_new_dir(tmp_path, monkeypatch):
    target = tmp_path / "bin"
    target.mkdir()
    saved = os.environ.get("PATH")
    try:
        monkeypatch.setenv("PATH", "/usr/bin")
        _prepend_path(str(target))
        assert os.environ["PATH"].startswith(str(target))
    finally:
        if saved is not None:
            os.environ["PATH"] = saved


def test_prepend_path_dedupes(tmp_path, monkeypatch):
    target = tmp_path / "bin"
    target.mkdir()
    saved = os.environ.get("PATH")
    try:
        norm_target = os.path.normcase(str(target))
        monkeypatch.setenv("PATH", f"{norm_target}{os.pathsep}/usr/bin")
        _prepend_path(str(target))
        # El path sólo aparece una vez
        parts = [p for p in os.environ["PATH"].split(os.pathsep) if os.path.normcase(p) == norm_target]
        assert len(parts) == 1
    finally:
        if saved is not None:
            os.environ["PATH"] = saved


def test_prepend_sys_path_inserts_when_missing(tmp_path, monkeypatch):
    target = str(tmp_path / "site-packages")
    (tmp_path / "site-packages").mkdir()
    saved = list(sys.path)
    try:
        _prepend_sys_path(target)
        assert sys.path[0] == target
    finally:
        sys.path[:] = saved


def test_prepend_sys_path_skips_existing(tmp_path):
    target = str(tmp_path / "site-packages")
    (tmp_path / "site-packages").mkdir()
    saved = list(sys.path)
    try:
        _prepend_sys_path(target)
        _prepend_sys_path(target)
        assert sys.path.count(target) == 1
    finally:
        sys.path[:] = saved


def test_prepend_sys_path_skips_non_dir():
    saved = list(sys.path)
    try:
        _prepend_sys_path("/this/dir/does/not/exist/xyz_sdr_test")
        assert "/this/dir/does/not/exist/xyz_sdr_test" not in sys.path
    finally:
        sys.path[:] = saved


def test_allow_pothos_plugins_truthy_values(monkeypatch):
    for val in ("1", "true", "TRUE", "yes", "Yes"):
        monkeypatch.setenv("XYZ_SDR_ALLOW_POTHOS_PLUGINS", val)
        assert _allow_pothos_plugins() is True


def test_allow_pothos_plugins_falsy_values(monkeypatch):
    for val in ("", "0", "no", "false", "off", "random"):
        monkeypatch.setenv("XYZ_SDR_ALLOW_POTHOS_PLUGINS", val)
        assert _allow_pothos_plugins() is False


def test_allow_pothos_plugins_unset(monkeypatch):
    monkeypatch.delenv("XYZ_SDR_ALLOW_POTHOS_PLUGINS", raising=False)
    assert _allow_pothos_plugins() is False


def test_copy_if_newer_creates_dest(tmp_path):
    src = tmp_path / "src.txt"
    dest = tmp_path / "sub" / "dest.txt"
    src.write_bytes(b"hello")
    assert _copy_if_newer(str(src), str(dest)) is True
    assert dest.is_file()
    assert dest.read_bytes() == b"hello"


def test_copy_if_newer_skips_when_dest_newer(tmp_path):
    src = tmp_path / "src.txt"
    dest = tmp_path / "dest.txt"
    src.write_bytes(b"new")
    dest.write_bytes(b"old")
    # Hace dest más reciente que src (Windows limita timestamps).
    future = 2_000_000_000
    os.utime(dest, (future, future))
    os.utime(src, (1_000_000_000, 1_000_000_000))
    assert _copy_if_newer(str(src), str(dest)) is True
    # El contenido antiguo se preserva (no se sobreescribe)
    assert dest.read_bytes() == b"old"


def test_copy_if_newer_returns_false_on_missing_src(tmp_path):
    dest = tmp_path / "dest.txt"
    assert _copy_if_newer(str(tmp_path / "missing.txt"), str(dest)) is False


def test_disable_stale_pothos_api_dll_skips_when_sizes_match(tmp_path, monkeypatch):
    dest = tmp_path / "sdrplay_api.dll"
    dest.write_bytes(b"same-size")
    fake_src = tmp_path / "src.dll"
    fake_src.write_bytes(b"same-size")

    monkeypatch.setattr("core.soapy_runtime.find_sdrplay_api_dll", lambda: str(fake_src))
    _disable_stale_pothos_api_dll(str(dest))
    assert dest.is_file()  # no se renombró


def test_disable_stale_pothos_api_dll_renames_when_different_size(tmp_path, monkeypatch):
    dest = tmp_path / "sdrplay_api.dll"
    dest.write_bytes(b"old-content")
    fake_src = tmp_path / "src.dll"
    fake_src.write_bytes(b"new-larger-content")
    monkeypatch.setattr("core.soapy_runtime.find_sdrplay_api_dll", lambda: str(fake_src))
    _disable_stale_pothos_api_dll(str(dest))
    disabled = tmp_path / "sdrplay_api.dll.pothos-legacy"
    assert disabled.is_file()
    assert not dest.is_file()


def test_disable_stale_pothos_api_dll_skips_missing(tmp_path):
    _disable_stale_pothos_api_dll(str(tmp_path / "nope.dll"))
    assert not (tmp_path / "nope.dll.pothos-legacy").exists()


def test_iter_sdrplay_module_paths_filters(tmp_path):
    mod_dir = tmp_path / "modules"
    mod_dir.mkdir()
    (mod_dir / "SoapySDRPlay3.dll").write_bytes(b"")
    (mod_dir / "other.dll").write_bytes(b"")
    (mod_dir / "sdrplay_support.dll").write_bytes(b"")
    (mod_dir / "readme.txt").write_bytes(b"")
    paths = _iter_sdrplay_module_paths([str(mod_dir)])
    names = sorted(os.path.basename(p) for p in paths)
    assert names == ["SoapySDRPlay3.dll", "sdrplay_support.dll"]


def test_iter_sdrplay_module_paths_skips_missing_dirs(tmp_path):
    paths = _iter_sdrplay_module_paths([str(tmp_path / "missing")])
    assert paths == []


def test_user_dirs_use_localappdata(monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", r"C:\fake\localappdata")
    assert user_soapy_plugin_dir().endswith(os.path.join("xyz-sdr", "SoapySDR", "modules0.8"))
    assert user_xyz_sdr_bin_dir().endswith(os.path.join("xyz-sdr", "bin"))


def test_user_dirs_fallback_to_temp(monkeypatch):
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.setenv("TEMP", "/tmp/fake")
    assert user_xyz_sdr_bin_dir().endswith(os.path.join("xyz-sdr", "bin"))


def test_list_pothos_python_versions_empty_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("core.soapy_runtime.find_pothos_install", lambda: None)
    assert list_pothos_python_versions() == []


def test_list_pothos_python_versions_returns_sorted_desc(tmp_path):
    root = tmp_path / "PothosSDR"
    (root / "lib" / "python3.9" / "site-packages").mkdir(parents=True)
    (root / "lib" / "python3.11" / "site-packages").mkdir(parents=True)
    (root / "lib" / "python3.10" / "site-packages").mkdir(parents=True)
    versions = list_pothos_python_versions(str(root))
    assert versions == [(3, 11), (3, 10), (3, 9)]


def test_list_pothos_python_versions_skips_non_python_dirs(tmp_path):
    root = tmp_path / "PothosSDR"
    (root / "lib" / "python3.9" / "site-packages").mkdir(parents=True)
    (root / "lib" / "extra").mkdir()
    (root / "lib" / "pythonXYZ").mkdir()
    versions = list_pothos_python_versions(str(root))
    assert versions == [(3, 9)]


def test_list_pothos_python_versions_skips_dirs_without_site_packages(tmp_path):
    root = tmp_path / "PothosSDR"
    (root / "lib" / "python3.9").mkdir(parents=True)  # sin site-packages
    (root / "lib" / "python3.11" / "site-packages").mkdir(parents=True)
    versions = list_pothos_python_versions(str(root))
    assert versions == [(3, 11)]


def test_list_pothos_python_versions_skips_invalid_names(tmp_path):
    root = tmp_path / "PothosSDR"
    (root / "lib" / "python3.x" / "site-packages").mkdir(parents=True)
    (root / "lib" / "pythonabc" / "site-packages").mkdir(parents=True)
    (root / "lib" / "python3.9" / "site-packages").mkdir(parents=True)
    versions = list_pothos_python_versions(str(root))
    assert versions == [(3, 9)]


def test_assess_sdrplay_soapy_module_missing():
    assert assess_sdrplay_soapy_module(None) == "missing"
    assert assess_sdrplay_soapy_module("/non/existent/path.dll") == "missing"


def test_assess_sdrplay_soapy_module_legacy_short_name(tmp_path):
    """Ruta con nombre corto como 'sdrplay.dll' se considera legacy si es antigua."""
    legacy = tmp_path / "sdrplay.dll"
    legacy.write_bytes(b"x")
    os.utime(legacy, (1_000_000_000, 1_000_000_000))
    assert assess_sdrplay_soapy_module(str(legacy)) == "legacy"
