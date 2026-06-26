"""Tests de compatibilidad de Python con SoapySDR."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from core.python_runtime import (
    PIP_SOAPY_MAX,
    PIP_SOAPY_MIN,
    _requirements_without_soapy,
    is_version_soapy_compatible,
)


def test_pip_soapy_range_3_11():
    assert is_version_soapy_compatible((3, 11)) is True


def test_pip_soapy_range_3_12():
    assert is_version_soapy_compatible((3, 12)) is True


def test_python_3_14_not_compatible_without_pothos():
    with patch("core.python_runtime.find_pothos_install", return_value=None):
        assert is_version_soapy_compatible((3, 14)) is False


def test_python_3_9_compatible_when_pothos_bindings_exist():
    with patch("core.python_runtime.find_pothos_install", return_value=r"C:\Program Files\PothosSDR"):
        with patch(
            "core.python_runtime.get_pothos_site_packages_for_version",
            return_value=r"C:\Program Files\PothosSDR\lib\python3.9\site-packages",
        ):
            assert is_version_soapy_compatible((3, 9)) is True


def test_python_3_9_compatible_ignores_active_interpreter_version():
    """3.9 debe ser compatible aunque el instalador corra con Python 3.14."""
    with patch("core.python_runtime.find_pothos_install", return_value=r"C:\Program Files\PothosSDR"):
        with patch("core.python_runtime.get_pothos_site_packages_for_version") as mock_sp:
            mock_sp.return_value = r"C:\Program Files\PothosSDR\lib\python3.9\site-packages"
            assert is_version_soapy_compatible((3, 9)) is True
            mock_sp.assert_called_with(3, 9)


def test_pip_bounds_constants():
    assert PIP_SOAPY_MIN == (3, 10)
    assert PIP_SOAPY_MAX == (3, 12)


def test_requirements_without_soapy(tmp_path: Path):
    req = tmp_path / "requirements.txt"
    req.write_text(
        "numpy>=1.24\nSoapySDR\n# comment\nscipy>=1.10\n",
        encoding="utf-8",
    )
    filtered = _requirements_without_soapy(req)
    text = filtered.read_text(encoding="utf-8")
    assert "SoapySDR" not in text
    assert "numpy>=1.24" in text
    assert "scipy>=1.10" in text


def test_provision_returns_existing_candidate():
    from core.python_runtime import ProvisionResult, PythonCandidate, provision_compatible_python_verbose

    existing = PythonCandidate("C:\\Python312\\python.exe", (3, 12, 9), "test")
    with patch("core.python_runtime.find_best_soapy_python", return_value=existing):
        result = provision_compatible_python_verbose()
    assert isinstance(result, ProvisionResult)
    assert result.candidate == existing


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="Pothos binding discovery asume rutas y herramientas Windows; ver tests equivalentes para Linux cuando aplique.",
)
def test_find_best_prefers_pothos_python_version():
    from core.python_runtime import PythonCandidate, find_best_soapy_python

    candidates = [
        PythonCandidate("C:\\Python312\\python.exe", (3, 12, 0), "test"),
        PythonCandidate("C:\\Python39\\python.exe", (3, 9, 13), "test"),
    ]
    with patch("core.python_runtime.discover_python_candidates", return_value=candidates):
        with patch("core.python_runtime.list_pothos_python_versions", return_value=[(3, 9)]):
            with patch(
                "core.python_runtime.is_version_soapy_compatible",
                side_effect=lambda v: v in {(3, 9), (3, 12)},
            ):
                best = find_best_soapy_python()
    assert best is not None
    assert best.version_short == (3, 9)


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="Test de integración con Pothos (rutas Windows).",
)
def test_use_pothos_bindings_when_versions_match():
    from core.python_runtime import _use_pothos_soapy_bindings

    with patch("core.python_runtime.find_pothos_install", return_value=r"C:\Program Files\PothosSDR"):
        with patch("core.python_runtime._query_python_version", return_value=(3, 9, 13)):
            with patch(
                "core.python_runtime.get_pothos_site_packages_for_version",
                return_value=r"C:\Program Files\PothosSDR\lib\python3.9\site-packages",
            ):
                assert _use_pothos_soapy_bindings("C:\\Python39\\python.exe") is True


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="reexec con python.exe es path Windows-only (uso de C:\\\\fake\\\\python.exe).",
)
def test_reexec_with_python_includes_script_and_args(tmp_path):
    from core.python_runtime import reexec_with_python

    script = tmp_path / "main.py"
    script.write_text("print('ok')", encoding="utf-8")
    captured: dict = {}

    def fake_run(cmd, env=None):
        captured["cmd"] = cmd
        captured["env"] = env
        class R:
            returncode = 0
        return R()

    with patch("core.python_runtime.subprocess.run", side_effect=fake_run):
        with patch("core.python_runtime.sys.exit", side_effect=SystemExit) as mock_exit:
            with pytest.raises(SystemExit):
                reexec_with_python(
                    r"C:\fake\python.exe",
                    [str(script), "--debug"],
                )

    assert captured["cmd"] == [r"C:\fake\python.exe", str(script.resolve()), "--debug"]
    assert captured["env"]["XYZ_SDR_REEXEC_DONE"] == "1"


# ---------------------------------------------------------------------------
# Pure helpers (added in coverage-gradual pass) -- no subprocess, no fs.
# ---------------------------------------------------------------------------


def test_current_version_matches_sys_version_info() -> None:
    from core.python_runtime import current_version

    assert current_version() == sys.version_info[:3]


def test_is_python_64bit_matches_struct_calcsize() -> None:
    import struct

    from core.python_runtime import is_python_64bit

    assert is_python_64bit() is (struct.calcsize("P") * 8 == 64)


def test_version_in_range_branches() -> None:
    from core.python_runtime import _version_in_range

    assert _version_in_range((3, 11), (3, 10), (3, 12)) is True
    assert _version_in_range((3, 10), (3, 10), (3, 12)) is True
    assert _version_in_range((3, 12), (3, 10), (3, 12)) is True
    assert _version_in_range((3, 9), (3, 10), (3, 12)) is False
    assert _version_in_range((3, 13), (3, 10), (3, 12)) is False


def test_python_candidate_version_short_and_label() -> None:
    from core.python_runtime import PythonCandidate

    cand = PythonCandidate("/usr/bin/python3.12", (3, 12, 9), "system")
    assert cand.version_short == (3, 12)
    assert cand.label() == "Python 3.12.9 (system)"


@pytest.mark.parametrize(
    ("pothos_versions", "expected"),
    [
        ([(3, 9)], (3, 9)),
        ([(3, 11)], (3, 11)),
        ([], (3, 12)),
    ],
)
def test_provision_target_version_with_pothos(pothos_versions, expected) -> None:
    from core.python_runtime import provision_target_version

    with patch(
        "core.python_runtime.list_pothos_python_versions",
        return_value=pothos_versions,
    ):
        assert provision_target_version() == expected


@pytest.mark.parametrize(
    ("target", "expected_key"),
    [
        ((3, 9), "py_install_python39_prompt"),
        ((3, 12), "py_install_python_prompt"),
    ],
)
def test_provision_i18n_keys_follow_target_version(target, expected_key) -> None:
    from core.python_runtime import (
        provision_fail_i18n_key,
        provision_manual_i18n_key,
        provision_prompt_i18n_key,
        provision_running_i18n_key,
    )

    with patch("core.python_runtime.provision_target_version", return_value=target):
        assert provision_prompt_i18n_key() == expected_key
        assert provision_running_i18n_key() == expected_key.replace("prompt", "running")
        assert provision_fail_i18n_key() == expected_key.replace("prompt", "fail")
        assert provision_manual_i18n_key() == expected_key.replace("prompt", "manual")


def test_provision_i18n_key_suffix_mapping_for_3_12() -> None:
    from core.python_runtime import (
        provision_fail_i18n_key,
        provision_manual_i18n_key,
        provision_prompt_i18n_key,
        provision_running_i18n_key,
    )

    with patch("core.python_runtime.provision_target_version", return_value=(3, 12)):
        assert provision_prompt_i18n_key() == "py_install_python_prompt"
        assert provision_running_i18n_key() == "py_install_python_running"
        assert provision_fail_i18n_key() == "py_install_python_fail"
        assert provision_manual_i18n_key() == "py_install_python_manual"


def test_is_current_soapy_compatible_uses_current_version() -> None:
    from core.python_runtime import is_current_soapy_compatible

    with patch("core.python_runtime.current_version", return_value=(3, 12, 9)):
        # 3.12 is in PIP_SOAPY range and no pothos -> still compatible.
        with patch("core.python_runtime.find_pothos_install", return_value=None):
            assert is_current_soapy_compatible() is True

    with patch("core.python_runtime.current_version", return_value=(3, 14, 0)):
        with patch("core.python_runtime.find_pothos_install", return_value=None):
            assert is_current_soapy_compatible() is False


def test_project_venv_python_returns_none_when_missing(tmp_path: Path) -> None:
    from core.python_runtime import project_venv_python

    # tmp_path has no .venv -> None on every OS.
    assert project_venv_python(root=tmp_path) is None


def test_project_venv_python_returns_executable_when_present(tmp_path: Path) -> None:
    import sys as _sys

    from core.python_runtime import project_venv_python

    if _sys.platform == "win32":
        candidate = tmp_path / ".venv" / "Scripts" / "python.exe"
    else:
        candidate = tmp_path / ".venv" / "bin" / "python"
    candidate.parent.mkdir(parents=True, exist_ok=True)
    candidate.write_text("# fake", encoding="utf-8")
    assert project_venv_python(root=tmp_path) == candidate
