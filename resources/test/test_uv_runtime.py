"""Tests de uv_runtime (instalación y resolución de comando)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from core import uv_runtime


def test_uv_available_true_when_on_path():
    with patch.object(uv_runtime, "_uv_on_path", return_value=r"C:\Tools\uv.exe"):
        assert uv_runtime.uv_available() is True


def test_resolve_uv_command_prefers_path():
    with patch.object(uv_runtime, "_uv_on_path", return_value=r"C:\Tools\uv.exe"):
        assert uv_runtime.resolve_uv_command() == [r"C:\Tools\uv.exe"]


def test_ensure_uv_installs_when_missing():
    pip_called = False

    def fake_run(cmd, **kwargs):
        nonlocal pip_called
        if len(cmd) >= 4 and cmd[1:4] == ["-m", "pip", "install"] and cmd[-1] == "uv":
            pip_called = True
            return None
        raise AssertionError(f"unexpected cmd: {cmd}")

    with patch.object(uv_runtime, "uv_available", side_effect=[False, True]):
        with patch.object(uv_runtime, "resolve_uv_command", return_value=["uv"]):
            with patch.object(uv_runtime.subprocess, "run", side_effect=fake_run):
                cmd = uv_runtime.ensure_uv("python")
    assert pip_called is True
    assert cmd == ["uv"]


def test_ensure_uv_raises_when_still_missing():
    with patch.object(uv_runtime, "uv_available", return_value=False):
        with patch.object(uv_runtime.subprocess, "run"):
            with patch.object(uv_runtime, "resolve_uv_command", side_effect=FileNotFoundError("uv")):
                with pytest.raises(FileNotFoundError):
                    uv_runtime.ensure_uv("python")
