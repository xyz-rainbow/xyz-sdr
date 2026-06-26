"""Tests del InstallContext dataclass en setup/install_actions.py.

Verifica que el dataclass sea instanciable, los callbacks sean invocables,
y se pueda usar como parámetro en funciones del instalador.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from setup.install_actions import InstallContext


def test_install_context_default_construction():
    """InstallContext debe instanciarse con los 4 campos requeridos."""
    ctx = InstallContext(
        lang="es",
        say=lambda msg: None,
        confirm=lambda prompt: True,
        temp_dir="C:\\temp",
    )
    assert ctx.lang == "es"
    assert ctx.temp_dir == "C:\\temp"
    assert callable(ctx.say)
    assert callable(ctx.confirm)


def test_install_context_callbacks_invokable():
    """Los callbacks say/confirm deben ser invocables y registrar llamadas."""
    messages: list[str] = []
    answers: list[str] = []

    def my_say(msg: str) -> None:
        messages.append(msg)

    def my_confirm(prompt: str) -> bool:
        answers.append(prompt)
        return True

    ctx = InstallContext(
        lang="en",
        say=my_say,
        confirm=my_confirm,
        temp_dir="/tmp",
    )

    ctx.say("hello")
    ctx.say("world")
    assert messages == ["hello", "world"]

    assert ctx.confirm("continue?") is True
    assert answers == ["continue?"]


def test_install_context_with_mock_callbacks():
    """InstallContext debe aceptar MagicMock para tests."""
    mock_say = MagicMock()
    mock_confirm = MagicMock(return_value=False)
    ctx = InstallContext(
        lang="es",
        say=mock_say,
        confirm=mock_confirm,
        temp_dir="/tmp",
    )

    ctx.say("test message")
    mock_say.assert_called_once_with("test message")
    assert ctx.confirm("prompt?") is False


def test_install_context_dataclass_field_order():
    """Los campos deben estar en orden: lang, say, confirm, temp_dir."""
    import dataclasses
    fields = dataclasses.fields(InstallContext)
    names = [f.name for f in fields]
    assert names == ["lang", "say", "confirm", "temp_dir"]


def test_install_actions_module_uses_context():
    """Las funciones públicas de install_actions deben aceptar InstallContext."""
    import inspect
    from setup import install_actions

    functions_to_check = [
        "report_path_configuration",
        "run_sdrplay_api_installer",
        "install_pothos",
        "install_python_env",
        "install_soapy_sdrplay3",
    ]
    for fname in functions_to_check:
        if hasattr(install_actions, fname):
            func = getattr(install_actions, fname)
            sig = inspect.signature(func)
            params = list(sig.parameters.keys())
            # El primer parámetro debe ser ctx o context
            assert any("ctx" in p.lower() or "context" in p.lower() for p in params), (
                f"{fname}() no acepta InstallContext como parámetro. Params: {params}"
            )


@pytest.mark.parametrize("lang,temp_dir", [
    ("es", "/tmp"),
    ("en", "C:\\Users\\test\\AppData\\Local\\Temp"),
    ("es", ""),  # temp_dir vacío (debería ser OK al instanciar)
])
def test_install_context_various_values(lang, temp_dir):
    """InstallContext debe aceptar varios valores de idioma y temp_dir."""
    ctx = InstallContext(
        lang=lang,
        say=lambda m: None,
        confirm=lambda p: True,
        temp_dir=temp_dir,
    )
    assert ctx.lang == lang
    assert ctx.temp_dir == temp_dir