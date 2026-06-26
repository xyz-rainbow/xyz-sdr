# Testing — xyz-sdr

Estructura de tests, convenciones, mapeo test → módulo, comandos útiles.

> **Tests:** ~52 archivos en `resources/test/`, ~280 funciones, marcadores `slow` + `integration`.
> **Cobertura:** instrumentada en CI (`--cov=core --cov=setup --cov=tui`), umbral `--cov-fail-under=50` (subida gradual 40 → 45 → 48 → 50; últimos填补: `core/device.py` resolución pura + `SimulatedSDR`, `setup/install_actions.py` orquestación, `core/sdr_io.py` timeout/shutdown, `core/dsp.py` demoduladores).

---

## Estructura de directorios

```
resources/test/
├── conftest.py              # Fixtures compartidas (synthetic_psd, center_hz, …)
├── test_<module>.py         # Tests unitarios (1 archivo por módulo)
├── test_<feature>.py        # Tests de feature (e.g. test_sdr_features.py)
├── test_<behavior>.py       # Tests de comportamiento (e.g. test_cache_guard.py)
└── conftest.py              # fixtures específicas si las necesitas
```

**Convención:** `test_<module>.py` con la misma estructura jerárquica que el código:

| Módulo | Test directo |
|--------|--------------|
| `core/dsp.py` | `test_dsp.py` + `test_dsp_unit.py` (legacy) |
| `core/audio_output.py` | `test_audio_output.py` |
| `core/recorder.py` | `test_recorder.py` |
| `core/bookmarks.py` | `test_bookmarks.py` |
| `core/band_buffer.py` | `test_band_buffer.py` |
| `core/config_store.py` | `test_config_store.py` |
| `core/runtime_paths.py` | `test_runtime_paths.py` |
| `core/python_runtime.py` | `test_python_runtime.py` |
| `core/uv_runtime.py` | `test_uv_runtime.py` |
| `core/auto_demod.py` | `test_auto_demod.py` |
| `core/stream_stats.py` | `test_stream_stats.py` |
| `core/display_levels.py` | `test_display_levels.py` |
| `core/spectrum_rle` | `test_spectrum_rle.py` |
| `core/audio_agc.py` | `test_audio_agc.py` |
| `core/bandwidth_presets.py` | `test_bandwidth_presets.py` |
| `core/band_profiles.py` | `test_band_profiles.py` |
| `core/passband.py` | `test_passband_selection.py` |
| `core/squelch.py` | `test_squelch.py` |
| `core/soapy_runtime.py` | `test_soapy_runtime.py` |
| `core/audio_effects.py` | (pendiente) |
| `core/repo_update.py` | `test_repo_update.py` |
| `core/resolve_device.py` | `test_resolve_device.py` |
| `core/device.py` | `test_device_stream.py` |
| `core/sdrplay_service.py` | `test_sdrplay_service.py` |
| `core/sdr_io.py` | `test_sdr_io.py` |
| `core/diagnose_sdrplay.py` | `test_diagnose_sdrplay.py` |
| `core/rx_warmup.py` | `test_rx_warmup.py` |
| `core/session_exit.py` | `test_session_exit.py` |
| `core/session_log.py` | `test_session_log.py` |
| `core/crash_ui.py` | `test_crash_ui.py` |
| `core/console_utf8.py` | `test_console_utf8.py` |
| `core/env_state.py` | `test_env_state.py` |
| `tui/app.py` | `test_tui_app_smoke.py` (estructural; ver § TUI) |
| `tui/rx_worker.py` | `test_rx_worker.py` |
| `tui/splash.py` | (cubierto por smoke test) |
| `tui/widgets/frequency_timeline.py` | (imports en `test_widgets.py`) |
| `tui/widgets/spectrum_graph.py` | (imports en `test_widgets.py`) |
| `tui/widgets/waterfall_timeline.py` | `test_waterfall_history.py` + `test_waterfall_stress.py` |
| `tui/widgets/settings_menu.py` | (imports en `test_widgets.py`) |
| `tui/widgets/passband_messages.py` | (imports en `test_widgets.py`) |
| `tui/widgets/display_palette.py` | (imports en `test_widgets.py`) |
| `setup/install_wizard.py` | `test_install_wizard.py` |
| `setup/install_actions.py` | `test_install_actions.py` (estructural) |
| `setup/install_guidance.py` | `test_install_guidance.py` |
| `setup/install_menu.py` | (cubierto por test_install_wizard) |
| `setup/install_drivers.py` | (cubierto por test_install_wizard) |
| `setup/check_env.py` | (manual; ver `docs/installer.md`) |
| `setup/install_log.py` | (cubierto por otros tests) |
| `setup/install_i18n.py` | (cubierto por test_install_wizard) |
| `setup/soapy_sdrplay3.py` | `test_soapy_sdrplay3.py` + `test_soapy_plugin_path.py` |
| `setup/bundled_installers.py` | `test_bundled_installers.py` |
| `setup/windows_installers.py` | (cubierto por test_install_wizard) |
| `setup/repo_update.py` | (cubierto por test_repo_update) |
| `main.py` | `test_main.py` + `test_startup_io.py` |
| (general) | `test_setup_imports.py`, `test_input_modifiers.py`, `test_cache_guard.py` |

---

## Marcadores

Definidos en `pyproject.toml [tool.pytest.ini_options].markers`:

```python
"slow: tests that take several seconds",
"integration: external services or timing-sensitive I/O",
```

### Uso

```python
import pytest

@pytest.mark.slow
def test_full_pipeline():
    """Tarda >5s, marcado como slow."""
    ...

@pytest.mark.integration
def test_sdrplay_real_hardware():
    """Requiere SDRplay físico. NO corre en CI por defecto."""
    ...
```

### Comandos

```powershell
# Suite sin slow (default para CI rápida)
pytest -m "not slow"

# Solo slow
pytest -m "slow"

# Solo integration (los marcados; corre manual)
pytest -m "integration"

# Combinar
pytest -m "not slow and not integration"
```

---

## Fixtures compartidas (`conftest.py`)

```python
@pytest.fixture
def center_hz() -> float:
    return 100_600_000.0

@pytest.fixture
def sample_rate() -> float:
    return 500_000.0

@pytest.fixture
def band_cols_count() -> int:
    return 512

@pytest.fixture
def synthetic_psd() -> np.ndarray:
    """PSD sintético con pico central para tests de detección."""
    rng = np.random.default_rng(42)
    psd = rng.normal(loc=-60.0, scale=5.0, size=4096)
    psd[2048] = -20.0
    return psd

@pytest.fixture
def flat_band_cols(band_cols_count: int) -> np.ndarray:
    """Columnas planas para tests de waterfall."""
    return np.linspace(-80.0, -20.0, band_cols_count, dtype=np.float32)
```

### Fixture `sdr_mock_host` (Fase 2)

Compartida por `test_rx_worker.py`, `test_sdr_features.py`, etc. Mockea el `XyzSDRApp` con todos los atributos que el RX worker necesita.

```python
@pytest.fixture
def sdr_mock_host() -> MagicMock:
    """Host mock para tests del RX worker — atributos necesarios."""
    host = MagicMock()
    host._bandwidth_changing = False
    host._rx_active = True
    host.sample_rate = 500_000.0
    host.tuned_frequency = 100e6
    host.visible_span = 500_000.0
    host._display_width = 80
    host.demod_mode = "wbfm"
    host.squelch_enabled = False
    host.squelch_threshold = 5.0
    host.passband_center_hz = 100e6
    host.passband_width_hz = 80_000.0
    host.fm_deemphasis_us = 50.0
    host.fm_agc_enabled = True
    host.debug_mode = False
    host.config = {"dsp": {"fft_size": 512, "fft_avg_windows": 2, "fft_overlap": 0.5, "band_cache_cols": 256, "audio_rate": 48000}}
    host._device.read_samples.return_value = np.random.randn(4096).astype(np.complex64)
    host._band_mailbox = BandFrameMailbox()
    host._recorder = None
    host._audio_output = None
    host._fm_demod_state = MagicMock()
    host._fm_agc = MagicMock()
    host._squelch_gate = MagicMock()
    host._squelch_gate.is_open.return_value = True
    host.consume_rx_warmup_samples.side_effect = lambda requested: requested
    return host
```

---

## Convenciones de tests

### Aislamiento

- **`tmp_path`** para todo archivo en disco (pytest lo limpia solo).
- **`monkeypatch`** para modificar globales (`os.environ`, módulos importados).
- **`MagicMock` + `patch.object`** para collaborators.
- **Sin estado global** entre tests.

### Parametrización

```python
import pytest

@pytest.mark.parametrize("mode,audio_rate", [
    ("wbfm", 48_000),
    ("nbfm", 48_000),
    ("am",   48_000),
    ("usb",  48_000),
    ("lsb",  48_000),
])
def test_demod_modes(mode, audio_rate):
    iq = np.random.randn(2048).astype(np.complex64)
    audio = demodulate(iq, mode=mode, sample_rate=250_000, audio_rate=audio_rate)
    assert len(audio) > 0
    assert np.isfinite(audio).all()
```

### Property-based testing (Fase 2)

`hypothesis` para invariantes round-trip:

```python
from hypothesis import given, strategies as st

@given(st.floats(min_value=1e6, max_value=1e10, allow_nan=False))
def test_passband_freq_col_roundtrip(freq_hz):
    """col ↔ freq ↔ col round-trip."""
    col_a = freq_to_col(freq_hz, ...)
    freq_back = col_to_freq(col_a, ...)
    col_b = freq_to_col(freq_back, ...)
    assert abs(col_a - col_b) <= 1
```

### Marcado de tests que requieren hardware/red

```python
@pytest.mark.integration
def test_real_sdr_device_open():
    """Requiere SDRplay físico + service. NO corre en CI."""
    ...
```

---

## Cobertura

### CI

`.github/workflows/test.yml` ejecuta:

```bash
python -m pytest resources/test -q -m "not slow" \
  --cov=core --cov=setup --cov=tui \
  --cov-report=xml \
  --cov-report=term-missing \
  --cov-fail-under=70
```

Umbral: **70%**. Subir gradualmente a 85%.

### Local

```powershell
# Cobertura local con HTML report
pytest --cov=core --cov=setup --cov=tui --cov-report=html --cov-report=term-missing

# Abrir reporte
start htmlcov/index.html
```

---

## Comandos rápidos

```powershell
# Todos los tests (sin slow)
.\scripts\test.ps1

# Solo smoke/imports (rápido)
pytest -q --co  # solo collection, sin ejecutar

# Un archivo específico
pytest resources/test/test_dsp.py -v

# Un test específico
pytest resources/test/test_dsp.py::test_round_fft_size_power_of_two -v

# Con duración (top 20)
pytest --durations=20

# Verbose con cobertura
pytest -v --cov=core --cov=setup --cov=tui --cov-report=term-missing
```

---

## Tests pendientes (gaps reconocidos)

Ver `.mavis/plans/deliverables/final_report.md` §5.4. Resumen:

1. `tui/app.py` (~2.900 LOC) — solo smoke estructural, falta pilot pattern.
2. `setup/install_actions.py` — la mayoría marcada SKIP (requieren installers reales).
3. `tui/widgets/{settings_menu,frequency_timeline,passband_messages}.py` — solo imports, falta pilot pattern.
4. `core/audio_effects.py` — pendiente test con mock de `sounddevice`.
5. `main()` end-to-end — parcial en `test_main.py`.
6. Sin `pytest-textual-snapshot` para regresiones visuales.
7. Sin property-based tests con `hypothesis` para `compact_band_cols`, `merge_configs`, `slice_band_to_viewport`, `passband.col↔freq`.

---

## Ver también

- [CONTRIBUTING.md §Tests](../CONTRIBUTING.md#tests)
- [`architecture.md`](architecture.md) § Concurrency model
- [`docs/README.md`](README.md)