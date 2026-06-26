"""Tests de core/stream_strategy.py.

Fase 1 pre-work: contrato de elección de estrategia Soapy SDRplay RX.
Cubre parse_strategy, read_sdrplay_strategy, strategy_to_format_and_mode
y convert_cs16_to_iq. Puro numpy, headless.
"""

from __future__ import annotations

import os
import numpy as np
import pytest

from core.stream_strategy import (
    ENV_VAR_NAME,
    STREAM_FORMAT_CF32,
    STREAM_FORMAT_CS16,
    STREAM_MODE_LEGACY,
    STREAM_MODE_MINIMAL,
    StreamStrategy,
    convert_cs16_to_iq,
    parse_strategy,
    read_sdrplay_strategy,
    strategy_to_format_and_mode,
)


# ─── parse_strategy ───────────────────────────────────────────────────────


def test_parse_strategy_none_returns_auto():
    assert parse_strategy(None) is StreamStrategy.AUTO


def test_parse_strategy_empty_returns_auto():
    assert parse_strategy("") is StreamStrategy.AUTO
    assert parse_strategy("   ") is StreamStrategy.AUTO


def test_parse_strategy_exact_match():
    assert parse_strategy("auto") is StreamStrategy.AUTO
    assert parse_strategy("cf32_minimal") is StreamStrategy.CF32_MINIMAL
    assert parse_strategy("cf32_legacy") is StreamStrategy.CF32_LEGACY
    assert parse_strategy("cs16_minimal") is StreamStrategy.CS16_MINIMAL
    assert parse_strategy("cs16_legacy") is StreamStrategy.CS16_LEGACY


def test_parse_strategy_case_insensitive():
    assert parse_strategy("AUTO") is StreamStrategy.AUTO
    assert parse_strategy("Auto") is StreamStrategy.AUTO
    assert parse_strategy("CF32_MINIMAL") is StreamStrategy.CF32_MINIMAL


def test_parse_strategy_with_whitespace():
    assert parse_strategy("  auto  ") is StreamStrategy.AUTO
    assert parse_strategy("\tcf32_legacy\n") is StreamStrategy.CF32_LEGACY


def test_parse_strategy_prefix_match_unique():
    """Prefijos únicos resuelven correctamente (no ambiguos)."""
    # "cf32_m" solo matchea cf32_minimal (cf32_legacy empieza con cf32_l)
    assert parse_strategy("cf32_m") is StreamStrategy.CF32_MINIMAL
    # "cf32_l" solo matchea cf32_legacy
    assert parse_strategy("cf32_l") is StreamStrategy.CF32_LEGACY
    # "cs16_m" solo matchea cs16_minimal
    assert parse_strategy("cs16_m") is StreamStrategy.CS16_MINIMAL
    # "cs16_l" solo matchea cs16_legacy
    assert parse_strategy("cs16_l") is StreamStrategy.CS16_LEGACY


def test_parse_strategy_prefix_ambiguous_returns_auto():
    """Prefijos ambiguos (múltiples matches) caen a AUTO."""
    # 'c' matchea cf32_minimal, cf32_legacy, cs16_minimal, cs16_legacy → ambigüedad
    assert parse_strategy("c") is StreamStrategy.AUTO


def test_parse_strategy_unknown_returns_auto():
    assert parse_strategy("xyz") is StreamStrategy.AUTO
    assert parse_strategy("garbage_value") is StreamStrategy.AUTO
    assert parse_strategy("cf99") is StreamStrategy.AUTO


# ─── read_sdrplay_strategy ────────────────────────────────────────────────


def test_read_sdrplay_strategy_uses_env(monkeypatch):
    monkeypatch.setenv(ENV_VAR_NAME, "cs16_legacy")
    assert read_sdrplay_strategy() is StreamStrategy.CS16_LEGACY


def test_read_sdrplay_strategy_unset_returns_auto(monkeypatch):
    monkeypatch.delenv(ENV_VAR_NAME, raising=False)
    assert read_sdrplay_strategy() is StreamStrategy.AUTO


def test_read_sdrplay_strategy_with_explicit_env(monkeypatch):
    monkeypatch.setenv(ENV_VAR_NAME, "garbage")
    assert read_sdrplay_strategy(env=None) is StreamStrategy.AUTO


def test_read_sdrplay_strategy_explicit_env_dict():
    """Verifica que se puede pasar un dict sin tocar os.environ."""
    env = {ENV_VAR_NAME: "cs16_minimal"}
    assert read_sdrplay_strategy(env=env) is StreamStrategy.CS16_MINIMAL


def test_read_sdrplay_strategy_explicit_env_missing_key():
    """Si la key no está en el dict explícito, devuelve AUTO."""
    assert read_sdrplay_strategy(env={}) is StreamStrategy.AUTO


def test_read_sdrplay_strategy_explicit_env_invalid_value():
    """Valor inválido en dict explícito también cae a AUTO."""
    assert read_sdrplay_strategy(env={ENV_VAR_NAME: "nonsense"}) is StreamStrategy.AUTO


def test_env_var_name_constant():
    """El nombre del env var es estable (cambio = romper config usuarios)."""
    assert ENV_VAR_NAME == "XYZ_SDR_SDRPLAY_STREAM_STRATEGY"


def test_format_constants():
    """Las constantes de formato Soapy no cambian."""
    assert STREAM_FORMAT_CF32 == "CF32"
    assert STREAM_FORMAT_CS16 == "CS16"


def test_mode_constants():
    assert STREAM_MODE_MINIMAL == "minimal"
    assert STREAM_MODE_LEGACY == "legacy"


# ─── strategy_to_format_and_mode ──────────────────────────────────────────


def test_strategy_to_format_and_mode_auto_defaults():
    """AUTO cae a CF32 + minimal (default histórico, pre-Fase 0 gate)."""
    fmt, mode = strategy_to_format_and_mode(StreamStrategy.AUTO)
    assert fmt == STREAM_FORMAT_CF32
    assert mode == STREAM_MODE_MINIMAL


def test_strategy_to_format_and_mode_cf32_minimal():
    fmt, mode = strategy_to_format_and_mode(StreamStrategy.CF32_MINIMAL)
    assert fmt == STREAM_FORMAT_CF32
    assert mode == STREAM_MODE_MINIMAL


def test_strategy_to_format_and_mode_cf32_legacy():
    fmt, mode = strategy_to_format_and_mode(StreamStrategy.CF32_LEGACY)
    assert fmt == STREAM_FORMAT_CF32
    assert mode == STREAM_MODE_LEGACY


def test_strategy_to_format_and_mode_cs16_minimal():
    fmt, mode = strategy_to_format_and_mode(StreamStrategy.CS16_MINIMAL)
    assert fmt == STREAM_FORMAT_CS16
    assert mode == STREAM_MODE_MINIMAL


def test_strategy_to_format_and_mode_cs16_legacy():
    fmt, mode = strategy_to_format_and_mode(StreamStrategy.CS16_LEGACY)
    assert fmt == STREAM_FORMAT_CS16
    assert mode == STREAM_MODE_LEGACY


def test_strategy_to_format_and_mode_all_strategies_resolve():
    """Todas las estrategias del enum deben tener un mapeo (no drift)."""
    for strategy in StreamStrategy:
        fmt, mode = strategy_to_format_and_mode(strategy)
        assert fmt in (STREAM_FORMAT_CF32, STREAM_FORMAT_CS16)
        assert mode in (STREAM_MODE_MINIMAL, STREAM_MODE_LEGACY)


# ─── convert_cs16_to_iq ───────────────────────────────────────────────────


def test_convert_cs16_to_iq_basic_pair():
    """Par IQ intercalado simple: [I, Q] → I + jQ normalizado."""
    raw = np.array([16384, -16384], dtype=np.int16)
    out = convert_cs16_to_iq(raw)
    assert out.dtype == np.complex64
    assert out.shape == (1,)
    # 16384 / 32768 = 0.5
    assert out[0].real == pytest.approx(0.5, abs=1e-4)
    assert out[0].imag == pytest.approx(-0.5, abs=1e-4)


def test_convert_cs16_to_iq_multiple_pairs():
    """N pares → N muestras complejas."""
    raw = np.array([32767, 0, -32768, 0, 16384, -16384], dtype=np.int16)
    out = convert_cs16_to_iq(raw)
    assert out.dtype == np.complex64
    assert out.shape == (3,)
    assert out[0].real == pytest.approx(32767 / 32768.0, abs=1e-4)
    assert out[0].imag == pytest.approx(0.0, abs=1e-4)
    assert out[1].real == pytest.approx(-1.0, abs=1e-4)
    assert out[2].real == pytest.approx(0.5, abs=1e-4)
    assert out[2].imag == pytest.approx(-0.5, abs=1e-4)


def test_convert_cs16_to_iq_zero():
    """Vector de ceros → vector complejo de ceros."""
    raw = np.zeros(10, dtype=np.int16)
    out = convert_cs16_to_iq(raw)
    assert out.shape == (5,)
    assert np.allclose(out.real, 0.0)
    assert np.allclose(out.imag, 0.0)


def test_convert_cs16_to_iq_empty():
    """Array vacío → array complejo vacío (sin raise)."""
    raw = np.zeros(0, dtype=np.int16)
    out = convert_cs16_to_iq(raw)
    assert out.shape == (0,)
    assert out.dtype == np.complex64


def test_convert_cs16_to_iq_odd_length_drops_last():
    """Longitud impar: se descarta el último sample (sin warning raise)."""
    raw = np.array([100, 200, 300], dtype=np.int16)
    out = convert_cs16_to_iq(raw)
    # Solo se procesa el par (100, 200); el 300 suelto se ignora.
    assert out.shape == (1,)
    assert out[0].real == pytest.approx(100 / 32768.0, abs=1e-4)
    assert out[0].imag == pytest.approx(200 / 32768.0, abs=1e-4)


def test_convert_cs16_to_iq_single_sample_returns_empty():
    """1 sample no forma par → array vacío."""
    raw = np.array([100], dtype=np.int16)
    out = convert_cs16_to_iq(raw)
    assert out.shape == (0,)


def test_convert_cs16_to_iq_uint16_accepted():
    """uint16 también es válido (algunos drivers lo entregan)."""
    raw = np.array([32767, 16384], dtype=np.uint16)
    out = convert_cs16_to_iq(raw)
    assert out.shape == (1,)
    assert out[0].real == pytest.approx(32767 / 32768.0, abs=1e-4)


def test_convert_cs16_to_iq_rejects_float():
    """dtype float no es CS16 → TypeError."""
    raw = np.array([0.5, -0.5], dtype=np.float32)
    with pytest.raises(TypeError, match="int16"):
        convert_cs16_to_iq(raw)


def test_convert_cs16_to_iq_rejects_int32():
    """int32 no es CS16 → TypeError (overflow prevention)."""
    raw = np.array([100, 200], dtype=np.int32)
    with pytest.raises(TypeError, match="int16"):
        convert_cs16_to_iq(raw)


def test_convert_cs16_to_iq_with_out_buffer():
    """El parámetro `out` reutiliza buffer (no allocation nueva)."""
    raw = np.array([16384, -16384, 32767, 0], dtype=np.int16)
    expected = convert_cs16_to_iq(raw).copy()
    out = np.zeros(2, dtype=np.complex64)
    result = convert_cs16_to_iq(raw, out=out)
    assert result is out  # devuelve el mismo buffer
    assert np.allclose(result, expected)


def test_convert_cs16_to_iq_normalization_range():
    """El output está normalizado al rango ±1.0."""
    raw = np.array([32767, -32768], dtype=np.int16)
    out = convert_cs16_to_iq(raw)
    assert -1.0 <= out[0].real <= 1.0
    assert -1.0 <= out[0].imag <= 1.0


def test_convert_cs16_to_iq_preserves_phase_relationship():
    """La fase del par IQ se preserva tras la normalización."""
    raw = np.array([23170, 23170], dtype=np.int16)  # 45° en plano unitario
    out = convert_cs16_to_iq(raw)
    # I = Q → fase = 45°
    assert out[0].real == pytest.approx(out[0].imag, abs=1e-4)
    assert out[0].real > 0


# ─── StreamStrategy enum properties ───────────────────────────────────────


def test_stream_strategy_inherits_str():
    """StreamStrategy hereda de str para JSON legible (json.dumps)."""
    assert isinstance(StreamStrategy.AUTO, str)
    assert StreamStrategy.AUTO == "auto"


def test_stream_strategy_json_serializable():
    """StreamStrategy es serializable a JSON como string."""
    import json

    payload = json.dumps({"strategy": StreamStrategy.CS16_LEGACY})
    assert payload == '"cs16_legacy"' or payload == '{"strategy": "cs16_legacy"}'


def test_stream_strategy_all_values_unique():
    """Cada estrategia tiene un value único."""
    values = [s.value for s in StreamStrategy]
    assert len(values) == len(set(values))


def test_stream_strategy_member_count():
    """El enum tiene exactamente 5 miembros (no drift silencioso)."""
    assert len(list(StreamStrategy)) == 5


# ─── Integration: env → strategy → format/mode ────────────────────────────


def test_full_pipeline_cf32_minimal(monkeypatch):
    monkeypatch.setenv(ENV_VAR_NAME, "cf32_minimal")
    strategy = read_sdrplay_strategy()
    fmt, mode = strategy_to_format_and_mode(strategy)
    assert (strategy, fmt, mode) == (
        StreamStrategy.CF32_MINIMAL,
        STREAM_FORMAT_CF32,
        STREAM_MODE_MINIMAL,
    )


def test_full_pipeline_cs16_legacy_with_conversion(monkeypatch):
    monkeypatch.setenv(ENV_VAR_NAME, "cs16_legacy")
    strategy = read_sdrplay_strategy()
    fmt, mode = strategy_to_format_and_mode(strategy)
    assert fmt == STREAM_FORMAT_CS16

    raw = np.array([16384, -16384, 0, 0], dtype=np.int16)
    iq = convert_cs16_to_iq(raw)
    assert iq.shape == (2,)


def test_full_pipeline_auto_default(monkeypatch):
    monkeypatch.delenv(ENV_VAR_NAME, raising=False)
    strategy = read_sdrplay_strategy()
    fmt, mode = strategy_to_format_and_mode(strategy)
    # AUTO cae al default CF32 + minimal
    assert fmt == STREAM_FORMAT_CF32
    assert mode == STREAM_MODE_MINIMAL


def test_full_pipeline_invalid_env_falls_back(monkeypatch):
    """Env var mal escrita nunca rompe el arranque (cae a AUTO)."""
    monkeypatch.setenv(ENV_VAR_NAME, "garbage_xyz")
    strategy = read_sdrplay_strategy()
    assert strategy is StreamStrategy.AUTO