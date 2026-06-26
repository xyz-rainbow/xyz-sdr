"""Tests de setup/soapy_sdrplay3.py (sin compilar)."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

from setup.soapy_sdrplay3 import (
    BUNDLED_DIR,
    BUNDLED_DLL_NAME,
    BUNDLED_MANIFEST,
    CMAKE_GENERATORS,
    SOAPY_SDRPLAY3_REPO,
    _default_confirm,
    _disable_pothos_sdrplay_module,
    _git_head_commit,
    _has_msvc,
    _module_dir,
    _parse_args,
    _run,
    _say,
    _sha256_file,
    _winget_executable,
    build_env,
    bundled_dll_path,
    command_available,
    install_bundled_soapy_sdrplay3,
    install_soapy_sdrplay3_if_needed,
    main,
    needs_soapy_sdrplay3_build,
    publish_bundled_dll,
    winget_available,
)


def test_needs_build_when_plugin_missing():
    with patch("setup.soapy_sdrplay3.is_sdrplay_soapy_module_ok", return_value=False), patch(
        "setup.soapy_sdrplay3.check_sdrplay_plugin", return_value=False
    ), patch("setup.soapy_sdrplay3.bootstrap_soapy") as boot, patch(
        "setup.soapy_sdrplay3.assess_sdrplay_soapy_module", return_value="missing"
    ):
        boot.return_value = MagicMock(sdrplay_plugin_module=None)
        assert needs_soapy_sdrplay3_build() is True


def test_needs_build_false_when_plugin_ok():
    with patch("setup.soapy_sdrplay3.check_sdrplay_plugin", return_value=True):
        assert needs_soapy_sdrplay3_build() is False


def test_install_skips_when_not_needed():
    messages: list[str] = []

    with patch("setup.soapy_sdrplay3.needs_soapy_sdrplay3_build", return_value=False), patch(
        "setup.soapy_sdrplay3.check_sdrplay_plugin", return_value=True
    ):
        ok = install_soapy_sdrplay3_if_needed("/tmp", say=messages.append, force=False)
    assert ok is True
    assert any("operativo" in m for m in messages)


def test_install_restarts_service_when_plugin_on_disk_but_api_hung():
    messages: list[str] = []

    with patch("setup.soapy_sdrplay3.needs_soapy_sdrplay3_build", return_value=False), patch(
        "setup.soapy_sdrplay3.check_sdrplay_plugin", side_effect=[False, True]
    ), patch("setup.soapy_sdrplay3.is_sdrplay_soapy_module_ok", return_value=True), patch(
        "core.sdrplay_service.restart_sdrplay_service", return_value=(True, "restarted")
    ):
        ok = install_soapy_sdrplay3_if_needed("/tmp", say=messages.append, force=False)
    assert ok is True
    assert any("reiniciando servicio" in m.lower() for m in messages)


def test_install_uses_bundled_before_build(tmp_path):
    messages: list[str] = []
    with patch("setup.soapy_sdrplay3.install_bundled_soapy_sdrplay3", return_value=True) as bundled, patch(
        "setup.soapy_sdrplay3.build_and_install_soapy_sdrplay3"
    ) as build, patch("core.soapy_runtime.check_sdrplay_api", return_value=True), patch(
        "setup.soapy_sdrplay3.find_pothos_install", return_value="C:/Pothos"
    ):
        ok = install_soapy_sdrplay3_if_needed(str(tmp_path), say=messages.append, force=True)
    assert ok is True
    bundled.assert_called_once()
    build.assert_not_called()


def test_bundled_dll_path_with_manifest(tmp_path, monkeypatch):
    plugins = tmp_path / "plugins"
    plugins.mkdir()
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    monkeypatch.setattr("core.driver_runtime.bundled_plugins_dir", lambda root=None: plugins)
    monkeypatch.setattr(
        "core.driver_runtime.bundled_manifest_path", lambda root=None: tmp_path / "manifest.json"
    )
    monkeypatch.setattr("core.driver_runtime.legacy_bundled_plugins_dir", lambda root=None: legacy)
    dll = plugins / BUNDLED_DLL_NAME
    dll.write_bytes(b"x" * 40_000)
    manifest = {
        "size_bytes": 40_000,
        "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    # sha mismatch -> None
    assert bundled_dll_path() is None

    manifest["sha256"] = hashlib.sha256(dll.read_bytes()).hexdigest()
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    assert bundled_dll_path() == dll


def test_publish_bundled_dll(tmp_path, monkeypatch):
    plugins = tmp_path / "plugins"
    plugins.mkdir()
    monkeypatch.setattr("core.driver_runtime.bundled_plugins_dir", lambda root=None: plugins)
    monkeypatch.setattr(
        "core.driver_runtime.bundled_manifest_path", lambda root=None: tmp_path / "manifest.json"
    )
    monkeypatch.setattr(
        "core.driver_runtime.legacy_bundled_plugins_dir",
        lambda root=None: tmp_path / "legacy",
    )
    source = tmp_path / "built.dll"
    source.write_bytes(b"new-plugin-bytes-here" * 2000)
    messages: list[str] = []
    assert publish_bundled_dll(source, say=messages.append, source_commit="abc123") is True
    assert (plugins / BUNDLED_DLL_NAME).is_file()
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["source_commit"] == "abc123"
    assert manifest["size_bytes"] == (plugins / BUNDLED_DLL_NAME).stat().st_size


def test_command_available_git():
    assert command_available("python") is True
    assert command_available("xyz-sdr-nonexistent-tool-12345") is False


# ---------------------------------------------------------------------------
# Helpers puros
# ---------------------------------------------------------------------------


def test_say_calls_log_when_provided(capsys):
    log_calls: list[str] = []
    _say("hello", log=log_calls.append)
    assert log_calls == ["hello"]
    captured = capsys.readouterr()
    assert "hello" in captured.out


def test_say_without_log_only_prints(capsys):
    _say("plain")
    captured = capsys.readouterr()
    assert "plain" in captured.out


def test_sha256_file_matches_hashlib(tmp_path):
    target = tmp_path / "data.bin"
    data = b"some random content for sha256"
    target.write_bytes(data)
    expected = hashlib.sha256(data).hexdigest()
    assert _sha256_file(target) == expected


def test_sha256_file_handles_large_chunks(tmp_path):
    """Verifica que el digest funciona con archivos >1MB (chunk size del código)."""
    target = tmp_path / "big.bin"
    data = b"A" * (1024 * 1024 * 3)  # 3 MB
    target.write_bytes(data)
    expected = hashlib.sha256(data).hexdigest()
    assert _sha256_file(target) == expected


def test_winget_executable_from_path(monkeypatch):
    monkeypatch.setattr("setup.soapy_sdrplay3.shutil.which", lambda name, **_kw: "C:/winget.exe")
    monkeypatch.setattr("os.environ", {"LOCALAPPDATA": "/tmp"})
    assert _winget_executable({}) == "C:/winget.exe"


def test_winget_executable_fallback_to_localappdata(monkeypatch):
    monkeypatch.setattr("setup.soapy_sdrplay3.shutil.which", lambda name, **_kw: None)
    monkeypatch.setattr("os.environ", {"LOCALAPPDATA": "/tmp"})
    expected = os.path.join("/tmp", "Microsoft", "WindowsApps", "winget.exe")
    assert _winget_executable({}) == expected


def test_winget_available_via_path(monkeypatch):
    monkeypatch.setattr("setup.soapy_sdrplay3.command_available", lambda name, env=None: True)
    assert winget_available() is True


def test_winget_available_via_localappdata(monkeypatch, tmp_path):
    monkeypatch.setattr("setup.soapy_sdrplay3.command_available", lambda name, env=None: False)
    monkeypatch.setattr("os.environ", {"LOCALAPPDATA": str(tmp_path)})
    apps = tmp_path / "Microsoft" / "WindowsApps"
    apps.mkdir(parents=True)
    (apps / "winget.exe").write_bytes(b"")
    assert winget_available() is True


def test_winget_available_false_when_nothing(monkeypatch, tmp_path):
    monkeypatch.setattr("setup.soapy_sdrplay3.command_available", lambda name, env=None: False)
    monkeypatch.setattr("os.environ", {"LOCALAPPDATA": str(tmp_path)})
    assert winget_available() is False


def test_has_msvc_via_cl(monkeypatch):
    monkeypatch.setattr("setup.soapy_sdrplay3.command_available", lambda name, env=None: True)
    assert _has_msvc({}) is True


def test_has_msvc_via_buildtools_dir(monkeypatch, tmp_path):
    monkeypatch.setattr("setup.soapy_sdrplay3.command_available", lambda name, env=None: False)
    # Crea estructura simulada
    (tmp_path / "Microsoft Visual Studio" / "2022" / "BuildTools").mkdir(parents=True)
    monkeypatch.setattr(
        "setup.soapy_sdrplay3.os.path.isdir",
        lambda p: "BuildTools" in p or "Community" in p,
    )
    assert _has_msvc({}) is True


def test_has_msvc_false_when_nothing(monkeypatch):
    monkeypatch.setattr("setup.soapy_sdrplay3.command_available", lambda name, env=None: False)
    monkeypatch.setattr("setup.soapy_sdrplay3.os.path.isdir", lambda p: False)
    assert _has_msvc({}) is False


def test_module_dir_returns_default_when_lib_missing(tmp_path):
    """Si Pothos no tiene lib/SoapySDR, devuelve modules0.8 esperado."""
    pothos = tmp_path / "PothosSDR"
    pothos.mkdir()
    result = _module_dir(str(pothos))
    assert result == Path(str(pothos)) / "lib" / "SoapySDR" / "modules0.8"


def test_module_dir_picks_highest_version(tmp_path):
    lib = tmp_path / "lib" / "SoapySDR"
    (lib / "modules0.7").mkdir(parents=True)
    (lib / "modules0.8").mkdir(parents=True)
    (lib / "modules0.9-rc").mkdir(parents=True)
    result = _module_dir(str(tmp_path))
    # sorted reverse: modules0.9-rc, modules0.8, modules0.7 → primero = 0.9-rc
    assert result.name == "modules0.9-rc"


def test_module_dir_skips_non_modules_dirs(tmp_path):
    lib = tmp_path / "lib" / "SoapySDR"
    (lib / "extra").mkdir(parents=True)
    (lib / "modules0.8").mkdir(parents=True)
    result = _module_dir(str(tmp_path))
    assert result.name == "modules0.8"


def test_module_dir_fallback_when_no_modules(tmp_path):
    lib = tmp_path / "lib" / "SoapySDR"
    (lib / "extra").mkdir(parents=True)
    result = _module_dir(str(tmp_path))
    assert result.name == "modules0.8"


def test_git_head_commit_returns_none_without_git_dir(tmp_path):
    result = _git_head_commit(tmp_path, {})
    assert result is None


def test_git_head_commit_returns_commit_hash(tmp_path, monkeypatch):
    (tmp_path / ".git").mkdir()
    mock_run = MagicMock(return_value=MagicMock(returncode=0, stdout="abc1234\n"))
    monkeypatch.setattr("subprocess.run", mock_run)
    assert _git_head_commit(tmp_path, {}) == "abc1234"


def test_git_head_commit_returns_none_on_nonzero(tmp_path, monkeypatch):
    (tmp_path / ".git").mkdir()
    mock_run = MagicMock(return_value=MagicMock(returncode=128, stdout=""))
    monkeypatch.setattr("subprocess.run", mock_run)
    assert _git_head_commit(tmp_path, {}) is None


def test_git_head_commit_returns_none_on_empty_stdout(tmp_path, monkeypatch):
    (tmp_path / ".git").mkdir()
    mock_run = MagicMock(return_value=MagicMock(returncode=0, stdout=""))
    monkeypatch.setattr("subprocess.run", mock_run)
    assert _git_head_commit(tmp_path, {}) is None


def test_disable_pothos_sdrplay_module_noop_when_missing(tmp_path):
    pothos = str(tmp_path / "PothosSDR")
    (tmp_path / "lib" / "SoapySDR" / "modules0.8").mkdir(parents=True)
    messages: list[str] = []
    _disable_pothos_sdrplay_module(pothos, say=messages.append)
    assert messages == []


def test_disable_pothos_sdrplay_module_renames_dll(tmp_path):
    mod_dir = tmp_path / "lib" / "SoapySDR" / "modules0.8"
    mod_dir.mkdir(parents=True)
    dll = mod_dir / BUNDLED_DLL_NAME
    dll.write_bytes(b"old")
    pothos = str(tmp_path)
    messages: list[str] = []
    _disable_pothos_sdrplay_module(pothos, say=messages.append)
    assert dll.with_name(f"{BUNDLED_DLL_NAME}.pothos-disabled").is_file()
    assert any("desactivado" in m.lower() for m in messages)


def test_disable_pothos_sdrplay_module_avoids_overwrite(tmp_path):
    mod_dir = tmp_path / "lib" / "SoapySDR" / "modules0.8"
    mod_dir.mkdir(parents=True)
    dll = mod_dir / BUNDLED_DLL_NAME
    dll.write_bytes(b"new")
    # Crea ya el .pothos-disabled
    (mod_dir / f"{BUNDLED_DLL_NAME}.pothos-disabled").write_bytes(b"old")
    pothos = str(tmp_path)
    _disable_pothos_sdrplay_module(pothos, say=lambda m: None)
    assert dll.with_name(f"{BUNDLED_DLL_NAME}.pothos-disabled").is_file()
    # El archivo disabled original no se sobreescribe
    assert dll.with_name(f"{BUNDLED_DLL_NAME}.pothos-disabled").read_bytes() == b"old"
    # Se creó con sufijo numérico
    assert dll.with_name(f"{BUNDLED_DLL_NAME}.pothos-disabled-1").is_file()


def test_disable_pothos_sdrplay_module_swallows_oserror(tmp_path, monkeypatch):
    mod_dir = tmp_path / "lib" / "SoapySDR" / "modules0.8"
    mod_dir.mkdir(parents=True)
    dll = mod_dir / BUNDLED_DLL_NAME
    dll.write_bytes(b"x")
    messages: list[str] = []
    monkeypatch.setattr("pathlib.Path.rename", MagicMock(side_effect=OSError("locked")))
    _disable_pothos_sdrplay_module(str(tmp_path), say=messages.append)
    assert any("permisos" in m.lower() or "no se pudo" in m.lower() for m in messages)


def test_run_returns_exit_code(monkeypatch):
    mock_run = MagicMock(return_value=MagicMock(returncode=0))
    monkeypatch.setattr("setup.soapy_sdrplay3.subprocess.run", mock_run)
    assert _run(["echo", "hi"], env={}) == 0


def test_run_propagates_nonzero(monkeypatch):
    mock_run = MagicMock(return_value=MagicMock(returncode=42))
    monkeypatch.setattr("setup.soapy_sdrplay3.subprocess.run", mock_run)
    assert _run(["false"], env={}) == 42


def test_build_env_prepends_pothos_bin(monkeypatch):
    monkeypatch.setattr("setup.soapy_sdrplay3.refresh_windows_environment", lambda: True)
    monkeypatch.setattr(
        "setup.soapy_sdrplay3.find_pothos_install", lambda: "/fake/PothosSDR"
    )
    monkeypatch.setattr("os.path.isdir", lambda p: p.endswith("bin") or "lib/SoapySDR" in p)
    fake_listdir = MagicMock(return_value=["modules0.8"])
    monkeypatch.setattr("os.listdir", fake_listdir)
    env = build_env()
    assert env["PATH"].startswith(os.path.join("/fake/PothosSDR", "bin") + os.pathsep)


def test_build_env_no_pothos_uses_extras(monkeypatch):
    monkeypatch.setattr("setup.soapy_sdrplay3.refresh_windows_environment", lambda: True)
    monkeypatch.setattr("setup.soapy_sdrplay3.find_pothos_install", lambda: None)
    monkeypatch.setattr("os.path.isdir", lambda p: "CMake" in p or "Git" in p)
    env = build_env()
    # PATH se compone de extras + actual PATH
    assert "PATH" in env


def test_default_confirm_says_yes(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda prompt: "s")
    assert _default_confirm("OK?") is True


def test_default_confirm_y_yes(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda prompt: "y")
    assert _default_confirm("OK?") is True


def test_default_confirm_si_with_accent(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda prompt: "sí")
    assert _default_confirm("OK?") is True


def test_default_confirm_rejects_no(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda prompt: "n")
    assert _default_confirm("OK?") is False


def test_default_confirm_empty_defaults_no(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda prompt: "")
    assert _default_confirm("OK?") is False


def test_default_confirm_eof_returns_false(monkeypatch):
    def raise_eof(_):
        raise EOFError

    monkeypatch.setattr("builtins.input", raise_eof)
    assert _default_confirm("OK?") is False


def test_parse_args_defaults():
    args = _parse_args([])
    assert args.build is False
    assert args.publish_bundled is False
    assert args.publish_only is None
    assert args.yes is False


def test_parse_args_build_flag():
    args = _parse_args(["--build"])
    assert args.build is True


def test_parse_args_publish_bundled():
    args = _parse_args(["--publish-bundled"])
    assert args.publish_bundled is True


def test_parse_args_publish_only():
    args = _parse_args(["--publish-only", "C:/built.dll"])
    assert args.publish_only == "C:/built.dll"


def test_parse_args_yes_short():
    args = _parse_args(["-y"])
    assert args.yes is True


def test_parse_args_yes_long():
    args = _parse_args(["--yes"])
    assert args.yes is True


def test_parse_args_none_uses_sys_argv(monkeypatch):
    monkeypatch.setattr("sys.argv", ["soapy_sdrplay3.py", "--build"])
    args = _parse_args(None)
    assert args.build is True


# ---------------------------------------------------------------------------
# main / install_bundled_soapy_sdrplay3
# ---------------------------------------------------------------------------


def test_main_publish_only_success(tmp_path, monkeypatch):
    dll = tmp_path / "built.dll"
    dll.write_bytes(b"x")
    monkeypatch.setattr("setup.soapy_sdrplay3.publish_bundled_dll", lambda path, say: True)
    rc = main(["--publish-only", str(dll)])
    assert rc == 0


def test_main_publish_only_failure(tmp_path, monkeypatch):
    dll = tmp_path / "missing.dll"
    monkeypatch.setattr("setup.soapy_sdrplay3.publish_bundled_dll", lambda path, say: False)
    rc = main(["--publish-only", str(dll)])
    assert rc == 1


def test_main_install_ok(monkeypatch):
    monkeypatch.setattr(
        "setup.soapy_sdrplay3.install_soapy_sdrplay3_if_needed", lambda *a, **kw: True
    )
    rc = main(["--yes"])
    assert rc == 0


def test_main_install_fails(monkeypatch):
    monkeypatch.setattr(
        "setup.soapy_sdrplay3.install_soapy_sdrplay3_if_needed", lambda *a, **kw: False
    )
    rc = main([])
    assert rc == 1


def test_main_passes_publish_bundled(monkeypatch):
    captured: dict = {}

    def fake_install(*args, **kwargs):
        captured.update(kwargs)
        captured["force"] = kwargs.get("force")
        captured["prefer_build"] = kwargs.get("prefer_build")
        captured["publish_bundled"] = kwargs.get("publish_bundled")
        return True

    monkeypatch.setattr("setup.soapy_sdrplay3.install_soapy_sdrplay3_if_needed", fake_install)
    main(["--publish-bundled"])
    assert captured["publish_bundled"] is True
    assert captured["prefer_build"] is True


def test_install_bundled_no_source(monkeypatch):
    monkeypatch.setattr("setup.soapy_sdrplay3.bundled_dll_path", lambda: None)
    messages: list[str] = []
    assert install_bundled_soapy_sdrplay3(say=messages.append) is False
    assert any("no disponible" in m.lower() for m in messages)


def test_install_bundled_no_pothos(monkeypatch, tmp_path):
    source = tmp_path / "x.dll"
    source.write_bytes(b"x")
    monkeypatch.setattr("setup.soapy_sdrplay3.bundled_dll_path", lambda: source)
    monkeypatch.setattr("setup.soapy_sdrplay3.find_pothos_install", lambda: None)
    messages: list[str] = []
    assert install_bundled_soapy_sdrplay3(say=messages.append) is False
    assert any("pothossdr" in m.lower() for m in messages)


def test_install_bundled_success(monkeypatch, tmp_path):
    source = tmp_path / "x.dll"
    source.write_bytes(b"x")
    monkeypatch.setattr("setup.soapy_sdrplay3.bundled_dll_path", lambda: source)
    monkeypatch.setattr("setup.soapy_sdrplay3.find_pothos_install", lambda: "C:/Pothos")
    monkeypatch.setattr("setup.soapy_sdrplay3.install_plugin_dll", lambda *a, **kw: source)
    monkeypatch.setattr("setup.soapy_sdrplay3.finalize_plugin_install", lambda say: True)
    assert install_bundled_soapy_sdrplay3(say=lambda m: None) is True


def test_constants_exposed():
    assert "pothosware/SoapySDRPlay3" in SOAPY_SDRPLAY3_REPO
    assert len(CMAKE_GENERATORS) >= 2
    assert BUNDLED_DIR  # alias legacy
    assert BUNDLED_MANIFEST  # alias legacy
    assert BUNDLED_DLL_NAME
