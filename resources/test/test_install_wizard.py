"""Wizard idempotente — segunda ejecución omite pasos completos."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from setup.env_state import EnvironmentState
from setup.install_actions import InstallContext
from setup.install_wizard import run_repair_wizard


def test_wizard_skips_ready_python(monkeypatch):
    calls: list[str] = []

    def fake_install_python(ctx, **kwargs):
        calls.append("install")
        return True

    ready = EnvironmentState(
        sdrplay_ok=True,
        pothos_installed=True,
        path_in_process=True,
        sdrplay_module_ok=True,
        sdrplay_plugin_ok=True,
        venv_path=Path(__file__),
        python_libs_missing=[],
        soapy_import_ok=True,
        has_devices=True,
        has_sdrplay_devices=True,
        blockers=[],
    )

    monkeypatch.setattr("setup.install_wizard.probe_environment", lambda **k: ready)
    monkeypatch.setattr("setup.install_wizard.ensure_repo_updated_for_wizard", lambda *a, **k: None)
    def fake_repair(*a, **k):
        calls.append("repair")
        return True, "ok"

    monkeypatch.setattr(
        "setup.install_wizard.repair_sdrplay_driver_stack",
        fake_repair,
    )
    monkeypatch.setattr("setup.install_wizard.install_pothos", lambda ctx: calls.append("pothos"))
    monkeypatch.setattr("setup.install_wizard.install_soapy_sdrplay3", lambda ctx, **k: calls.append("soapy3"))
    monkeypatch.setattr("setup.install_wizard.install_python_env", fake_install_python)
    monkeypatch.setattr("setup.check_env.run_check", lambda **k: 0)

    ctx = InstallContext(lang="es", say=lambda m: None, confirm=lambda p: True, temp_dir="/tmp")
    code = run_repair_wizard(ctx, quiet=True)
    assert code == 0
    assert "install" not in calls
    assert "repair" in calls
