"""Tests de compatibilidad de Python con SoapySDR."""

from __future__ import annotations

from unittest.mock import patch

from core.python_runtime import (
    PIP_SOAPY_MAX,
    PIP_SOAPY_MIN,
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
            "core.python_runtime.get_pothos_site_packages",
            return_value=r"C:\Program Files\PothosSDR\lib\python3.9\site-packages",
        ):
            assert is_version_soapy_compatible((3, 9)) is True


def test_pip_bounds_constants():
    assert PIP_SOAPY_MIN == (3, 10)
    assert PIP_SOAPY_MAX == (3, 12)
