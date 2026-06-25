"""Tests estructurales para setup/install_actions.py.

La mayoría de las acciones en este módulo requieren instalación real
(download de installers, elevación UAC, modificación de PATH) y no son
testeables en CI sin mocks masivos. Estos tests verifican solo lo que es
seguro validar de forma aislada: dataclasses, helpers puros, contratos.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from setup.install_actions import InstallContext


def test_install_context_is_dataclass():
    """InstallContext debe ser un dataclass con campos esperados."""
    ctx = InstallContext(
        lang="es",
        say=MagicMock(),
        confirm=MagicMock(return_value=True),
        temp_dir="C:\\tmp",
    )
    assert ctx.lang == "es"
    assert callable(ctx.say)
    assert callable(ctx.confirm)
    assert ctx.temp_dir == "C:\\tmp"


def test_install_context_say_is_invokable():
    """ctx.say debe poder invocarse sin lanzar (es callable)."""
    ctx = InstallContext(
        lang="en",
        say=MagicMock(),
        confirm=MagicMock(return_value=False),
        temp_dir="/tmp",
    )
    # No debe lanzar
    ctx.say("hello")
    ctx.say("world", extra="kwarg-ok")
    assert ctx.say.call_count == 2


def test_install_actions_module_imports():
    """El módulo setup/install_actions debe importar sin errores."""
    import setup.install_actions  # noqa: F401


@pytest.mark.skip(
    reason=(
        "Las acciones de install_pothos, install_sdrplay, install_python_env "
        "requieren installers reales, elevación UAC y modificación de PATH. "
        "No son seguras de ejecutar en CI. "
        "Quedan para tests manuales o mocks de integración (Fase 3)."
    )
)
def test_install_pothos_idempotent():
    """Pendiente: instalar Pothos dos veces produce el mismo estado."""
    raise NotImplementedError


@pytest.mark.skip(
    reason=(
        "report_path_configuration modifica PATH del usuario vía Windows registry. "
        "Requiere mock de winreg + elevación. Queda para Fase 3."
    )
)
def test_report_path_configuration_force_vs_no_force():
    """Pendiente: force=True ejecuta aunque ya esté configurado; force=False skip."""
    raise NotImplementedError


@pytest.mark.skip(
    reason=(
        "install_soapy_sdrplay3 requiere compilación nativa (CMake + VS BuildTools). "
        "Queda para tests manuales en Windows con toolchain instalado."
    )
)
def test_install_soapy_sdrplay3_dry_run():
    """Pendiente: dry_run=True no debe dejar artefactos en disco."""
    raise NotImplementedError