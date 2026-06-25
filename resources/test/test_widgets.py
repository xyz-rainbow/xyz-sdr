"""Tests estructurales para widgets TUI en tui/widgets/.

Los widgets están acoplados al ciclo de vida de la app Textual (requieren
Screen, Mount, event loop). Para un test completo se necesita `app.run_test()`
(pilot pattern), pero eso requiere refactor previo del lifecycle.

Estos tests verifican solo lo testeable de forma aislada:
- Importabilidad.
- Existencia de clases públicas.
- Métodos puros sin estado de widget.
"""

from __future__ import annotations

import pytest


# ── Importability ────────────────────────────────────────────────────────────


def test_widgets_module_imports():
    """El paquete tui.widgets debe importar sin errores."""
    import tui.widgets  # noqa: F401


def test_settings_menu_imports():
    from tui.widgets import settings_menu  # noqa: F401


def test_frequency_timeline_imports():
    from tui.widgets import frequency_timeline  # noqa: F401


def test_spectrum_graph_imports():
    from tui.widgets import spectrum_graph  # noqa: F401


def test_waterfall_timeline_imports():
    from tui.widgets import waterfall_timeline  # noqa: F401


def test_passband_messages_imports():
    from tui.widgets import passband_messages  # noqa: F401


def test_display_palette_imports():
    from tui.widgets import display_palette  # noqa: F401


# ── Helpers puros (no requieren Mount) ───────────────────────────────────────


def test_frequency_format_helpers_present():
    """FrequencyTimeline debe exponer métodos de formato Hz/MHz en la clase."""
    from tui.widgets.frequency_timeline import FrequencyTimeline

    # Buscamos métodos de la clase (no módulo) relacionados con formato o freq
    members = dir(FrequencyTimeline)
    format_hints = [m for m in members if "format" in m.lower() or "freq" in m.lower()]
    assert format_hints, (
        f"FrequencyTimeline no expone helpers de formato Hz reconocibles. "
        f"Methods: {[m for m in members if not m.startswith('_')][:10]}..."
    )


def test_display_palette_has_color_helpers():
    """display_palette debe tener funciones puras de cálculo de color."""
    from tui.widgets import display_palette

    members = dir(display_palette)
    # Busca cualquier callable que no sea import
    callables = [
        m for m in members
        if callable(getattr(display_palette, m, None)) and not m.startswith("_")
    ]
    assert len(callables) > 0, "display_palette no expone helpers públicos"


# ── Tests pendientes (requieren pilot pattern) ───────────────────────────────


@pytest.mark.skip(
    reason=(
        "Render real requiere `app.run_test()` (Textual pilot). "
        "Fase 3: refactor de lifecycle para que los widgets sean instanciables "
        "sin app y testeables con `pilot.press(...)` y `pilot.pause()`."
    )
)
def test_settings_menu_validates_invalid_freq():
    """Pendiente: settings_menu rechaza freq fuera de rango."""
    raise NotImplementedError


@pytest.mark.skip(
    reason=(
        "Render real requiere pilot pattern. Ver test anterior."
    )
)
def test_frequency_timeline_renders_empty_data():
    """Pendiente: render con datos vacíos no crashea."""
    raise NotImplementedError


@pytest.mark.skip(
    reason=(
        "Format Hz/MM:SS es output-only; requiere pilot pattern."
    )
)
def test_frequency_timeline_format_consistency():
    """Pendiente: misma freq produce misma representación en Hz y MHz."""
    raise NotImplementedError