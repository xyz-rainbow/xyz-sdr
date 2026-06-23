"""Tests de rollback .venv tras fallo de instalación."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from core.python_runtime import PythonCandidate, ensure_project_venv_with_deps


def test_venv_rollback_on_install_fail(tmp_path: Path):
    root = tmp_path
    best = PythonCandidate(sys.executable, (3, 12, 0), "test")

    with patch("core.python_runtime.project_root", return_value=root):
        with patch("core.python_runtime.find_best_soapy_python", return_value=best):
            with patch("core.python_runtime.project_venv_python", return_value=None):
                with patch("core.python_runtime.create_project_venv") as create:
                    venv_py = root / ".venv" / "Scripts" / "python.exe"
                    venv_py.parent.mkdir(parents=True)
                    venv_py.write_text("", encoding="utf-8")
                    create.return_value = venv_py
                    with patch("core.python_runtime.install_requirements", side_effect=RuntimeError("uv fail")):
                        with pytest.raises(RuntimeError):
                            ensure_project_venv_with_deps(root)
                    assert not (root / ".venv").exists()
