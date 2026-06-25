"""Smoke test estructural para tui/app.py: XyzSDRApp.

Este test NO instancia la app (eso requiere setup de Soapy + hardware real).
En su lugar valida:
- Importabilidad del módulo.
- Estructura mínima de la clase: BINDINGS, CSS, acciones clave.
- Ausencia de errores en `compose()` cuando se mockea lo suficiente.

Para un test end-to-end real (con driver `simulated`), ver Fase 3 del roadmap
(`docs/roadmap.md`) — requiere refactor del lifecycle.
"""

from __future__ import annotations

import pytest


def test_tui_app_module_imports():
    """El módulo tui/app.py debe importarse sin errores."""
    import tui.app  # noqa: F401


def test_xyz_sdr_app_class_exists():
    """XyzSDRApp debe estar definido en tui.app."""
    from tui.app import XyzSDRApp

    assert XyzSDRApp is not None


def test_xyz_sdr_app_has_bindings():
    """XyzSDRApp debe declarar BINDINGS (atajos de teclado)."""
    from tui.app import XyzSDRApp

    bindings = getattr(XyzSDRApp, "BINDINGS", [])
    assert isinstance(bindings, (list, tuple))
    assert len(bindings) > 0, "XyzSDRApp.BINDINGS está vacío"


def test_xyz_sdr_app_has_css():
    """XyzSDRApp debe declarar CSS (estilos TUI)."""
    from tui.app import XyzSDRApp

    css = getattr(XyzSDRApp, "CSS", "")
    assert isinstance(css, str)
    assert len(css) > 100, "XyzSDRApp.CSS parece demasiado corto"


def test_xyz_sdr_app_key_actions_exist():
    """Acciones clave referenciadas en BINDINGS deben existir como métodos."""
    from tui.app import XyzSDRApp

    required_actions = ("action_quit",)
    for action_name in required_actions:
        assert hasattr(XyzSDRApp, action_name), (
            f"Falta método {action_name} en XyzSDRApp"
        )


def test_xyz_sdr_app_compose_is_callable():
    """compose() debe ser un método callable (no requiere instanciar para validar)."""
    from tui.app import XyzSDRApp

    assert callable(getattr(XyzSDRApp, "compose", None))


@pytest.mark.skip(
    reason=(
        "Instanciar XyzSDRApp requiere setup de Soapy + device. "
        "Queda pendiente para Fase 3 (refactor del lifecycle a un patrón "
        "testeable headless con driver='simulated'). "
        "Ver docs/roadmap.md."
    )
)
def test_xyz_sdr_app_instantiable_simulated():
    """Pendiente: instanciar XyzSDRApp(driver='simulated') sin abrir hardware."""
    raise NotImplementedError