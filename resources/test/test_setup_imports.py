"""Todos los módulos setup/* deben importar sin NameError."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SETUP_MODULES = (
    "setup.env_state",
    "setup.install_guidance",
    "setup.install_actions",
    "setup.install_wizard",
    "setup.install_menu",
    "setup.install_i18n",
    "setup.install_log",
    "setup.repo_update",
    "setup.windows_installers",
    "setup.check_env",
    "setup.install_drivers",
    "setup.capture_ui",
    "core.runtime_paths",
)


def test_setup_modules_import():
    for name in SETUP_MODULES:
        mod = importlib.import_module(name)
        assert mod is not None
