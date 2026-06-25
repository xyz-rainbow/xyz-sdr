"""Tests del módulo ai/ — API segura opt-in (Fase 4-5 pendiente)."""

from __future__ import annotations

import pytest


def test_is_available_returns_bool():
    from ai import is_available

    # Mientras ai/ sea placeholder, debe devolver False aunque las deps estén.
    result = is_available()
    assert isinstance(result, bool)
    assert result is False


def test_get_status_defaults_when_no_config():
    from ai import get_status

    s = get_status(None)
    assert s["engine_ready"] is False
    assert s["whisper_enabled"] is False
    assert s["classifier_enabled"] is False
    assert s["whisper_model"] == "base"
    assert s["whisper_language"] == "es"
    assert isinstance(s["deps"], dict)


def test_get_status_reads_config_section():
    from ai import get_status

    cfg = {
        "ai": {
            "whisper_enabled": True,
            "whisper_model": "small",
            "whisper_language": "en",
            "classifier_enabled": True,
        }
    }
    s = get_status(cfg)
    assert s["whisper_enabled"] is True
    assert s["whisper_model"] == "small"
    assert s["whisper_language"] == "en"
    assert s["classifier_enabled"] is True


def test_is_enabled_force_true_respects_availability():
    """Forzar --ai sin motor disponible debe devolver False (no-op seguro)."""
    from ai import is_available, is_enabled

    assert is_enabled(force=True, config={}) is is_available()


def test_is_enabled_no_force_no_config():
    from ai import is_enabled

    # Sin force y sin config → siempre False.
    assert is_enabled(force=False, config=None) is False
    assert is_enabled(force=False, config={}) is False


def test_is_enabled_off_config_sections():
    from ai import is_enabled

    cfg = {"ai": {"whisper_enabled": False, "classifier_enabled": False}}
    assert is_enabled(force=False, config=cfg) is False


def test_whisper_models_constant_is_closed_set():
    from ai import WHISPER_MODELS

    assert isinstance(WHISPER_MODELS, (list, tuple))
    assert "tiny" in WHISPER_MODELS
    assert "base" in WHISPER_MODELS
    assert "large-v2" in WHISPER_MODELS


def test_deps_dict_has_expected_keys():
    from ai import get_status

    deps = get_status(None).get("deps", {})
    assert "faster_whisper" in deps
    assert "sklearn" in deps
    assert "joblib" in deps
    for v in deps.values():
        assert isinstance(v, bool)


def test_default_language_is_spanish():
    from ai import DEFAULT_LANGUAGE

    assert DEFAULT_LANGUAGE == "es"


@pytest.mark.parametrize(
    "cfg",
    [
        None,
        {},
        {"ai": None},
        {"ai": "not-a-dict"},
    ],
)
def test_get_status_is_robust_to_bad_config(cfg):
    """Config corrupto no debe tirar excepción (settings_menu llama desde compose)."""
    from ai import get_status

    s = get_status(cfg)
    assert isinstance(s, dict)
    assert "engine_ready" in s