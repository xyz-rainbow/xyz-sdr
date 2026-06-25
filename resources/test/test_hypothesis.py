"""Property-based tests con Hypothesis para invariantes geométricas/DSP.

Cubre:
- `compact_band_cols` (core.band_buffer): idempotente (compact(compact(x)) == compact(x)).
- `slice_band_to_viewport` (core.band_buffer): shape invariante.
- `passband.col_to_freq ↔ freq_to_col` (core.passband): round-trip preserva índice (±1).
- `merge_configs` (core.band_profiles): asociatividad limitada.

Refs:
- docs/roadmap.md §Fase 2 item 24
- .mavis/plans/deliverables/final_report.md §5.4
"""

from __future__ import annotations

import numpy as np
import pytest
from hypothesis import HealthCheck, assume, given, settings, strategies as st

from core.band_buffer import compact_band_cols, slice_band_to_viewport
from core.band_profiles import merge_configs
from core.passband import col_to_freq, freq_to_col


# ── compact_band_cols ────────────────────────────────────────────────────────


@given(
    st.lists(
        st.floats(min_value=-100.0, max_value=0.0, allow_nan=False, allow_infinity=False),
        min_size=1,
        max_size=200,
    ),
    st.integers(min_value=1, max_value=512),
)
def test_compact_band_cols_idempotent(values, target):
    """compact(compact(x)) debe dar el mismo resultado que compact(x)."""
    arr = np.array(values, dtype=np.float32)
    once = compact_band_cols(arr, target=target)
    twice = compact_band_cols(once, target=target)
    np.testing.assert_array_equal(once, twice)


@settings(suppress_health_check=[HealthCheck.large_base_example, HealthCheck.too_slow], max_examples=20)
@given(
    st.lists(
        st.floats(min_value=-100.0, max_value=0.0, allow_nan=False, allow_infinity=False),
        min_size=600,
        max_size=1000,
    ),
)
def test_compact_band_cols_output_length(values):
    """compact_band_cols debe producir exactamente `target` columnas cuando input > target."""
    arr = np.array(values, dtype=np.float32)
    out = compact_band_cols(arr)
    # Si input > 512 (target default), output debe ser exactamente target
    assert len(out) == 512


# ── slice_band_to_viewport shape ──────────────────────────────────────────────


@given(
    band_n=st.integers(min_value=64, max_value=2048),
    width=st.integers(min_value=20, max_value=200),
    sample_rate=st.floats(min_value=100_000.0, max_value=10_000_000.0, allow_nan=False),
    visible_span=st.floats(min_value=10_000.0, max_value=5_000_000.0, allow_nan=False),
)
def test_slice_band_to_viewport_shape_invariant(band_n, width, sample_rate, visible_span):
    """El viewport debe tener exactamente `terminal_width` columnas."""
    arr = np.random.default_rng(0).normal(-60, 10, band_n).astype(np.float32)
    sliced = slice_band_to_viewport(
        arr,
        center_hz=100e6,
        sample_rate=sample_rate,
        viewport_center_hz=100e6,
        visible_span_hz=visible_span,
        terminal_width=width,
    )
    assert sliced.shape == (width,)


# ── passband col↔freq round-trip ─────────────────────────────────────────────


@given(
    col=st.floats(min_value=0.0, max_value=1000.0, allow_nan=False),
    widget_width=st.integers(min_value=80, max_value=2000),
    viewport_center_hz=st.floats(min_value=80e6, max_value=500e6, allow_nan=False),
    visible_span_hz=st.floats(min_value=10_000.0, max_value=5_000_000.0, allow_nan=False),
)
def test_passband_col_freq_roundtrip(col, widget_width, viewport_center_hz, visible_span_hz):
    """col → freq → col debe preservar el índice (±1)."""
    freq = col_to_freq(
        col,
        widget_width=widget_width,
        viewport_center_hz=viewport_center_hz,
        visible_span_hz=visible_span_hz,
    )
    col_back = freq_to_col(
        freq,
        widget_width=widget_width,
        viewport_center_hz=viewport_center_hz,
        visible_span_hz=visible_span_hz,
    )
    # freq_to_col puede devolver -1 (fuera de rango) o widget_width (overflow); verificamos
    # solo cuando está dentro del rango
    if 0 <= col_back < widget_width:
        # Convertir col inicial a entero (truncado) y comparar
        expected_col = int(col)
        assert abs(expected_col - col_back) <= 1, (
            f"col={col}, expected_col={expected_col}, col_back={col_back}, "
            f"freq={freq}, viewport={viewport_center_hz}, span={visible_span_hz}"
        )


# ── merge_configs ────────────────────────────────────────────────────────────


@given(
    a=st.dictionaries(
        keys=st.sampled_from(["dsp", "device", "display", "app"]),
        values=st.dictionaries(
            keys=st.text(min_size=1, max_size=10),
            values=st.one_of(
                st.floats(allow_nan=False, allow_infinity=False),
                st.integers(),
                st.booleans(),
                st.text(max_size=20),
            ),
            max_size=5,
        ),
        max_size=4,
    ),
    b=st.dictionaries(
        keys=st.sampled_from(["dsp", "device", "display", "app"]),
        values=st.dictionaries(
            keys=st.text(min_size=1, max_size=10),
            values=st.one_of(
                st.floats(allow_nan=False, allow_infinity=False),
                st.integers(),
                st.booleans(),
                st.text(max_size=20),
            ),
            max_size=5,
        ),
        max_size=4,
    ),
)
@settings(
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
    max_examples=50,
)
def test_merge_configs_idempotent_with_b(a, b):
    """merge(merge(a, b), b) == merge(a, b) — la segunda llamada con b no cambia nada."""
    once = merge_configs(a, b)
    twice = merge_configs(once, b)
    assert once == twice, f"merge no idempotente: once={once}, twice={twice}"


# ── Smoke ────────────────────────────────────────────────────────────────────


def test_hypothesis_imports_ok():
    """hypothesis debe estar instalado para que estos tests corran."""
    import hypothesis  # noqa: F401