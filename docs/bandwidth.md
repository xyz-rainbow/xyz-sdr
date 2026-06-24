# 📡 Bandwidth IQ (Sample Rate) — xyz-sdr

En xyz-sdr, el **bandwidth de captura** es el `sample_rate` del SDR: define cuánto espectro IQ recibe el dispositivo alrededor de la frecuencia central.

Índice: [README.md](README.md) | DSP: [dsp.md](dsp.md) | Perfiles: [audio-presets-research.md](audio-presets-research.md) | Config: [configuration.md](configuration.md)

---

## Interfaz de usuario

- **Selector BANDWIDTH** en el panel izquierdo, debajo del campo de frecuencia (MHz).
- **Atajo `B`**: enfoca el desplegable de bandwidth.
- **Barra de estado**: métrica `BW` (bandwidth activo) junto a `ZOOM` (span visible en pantalla).

> **ZOOM ≠ BW**: el zoom controla cuánto espectro *ves* en pantalla; el bandwidth controla cuánto espectro *captura* el hardware. El zoom máximo está acotado al bandwidth actual.

---

## Presets disponibles

Definidos en `core/device.py` → `BANDWIDTH_PRESETS`:

| Preset | Uso típico |
|--------|------------|
| 250 kHz | NFM, señales estrechas |
| 500 kHz | AM, scanning fino |
| 1 MHz | FM local |
| 2.048 MHz | WBFM, **recomendado para audio FM** |
| 4 MHz | Exploración amplia (espectro; demod decima IQ internamente) |
| 8 MHz | Máximo captura (espectro; audio FM usa decimación IQ interna) |

> **Audio WBFM:** un bandwidth IQ alto mejora el espectro visible pero **no** hace falta para escuchar FM comercial (~200 kHz PASS). El demodulador reduce la tasa IQ antes de filtrar (`resample_iq_for_demod` en `core/dsp.py`). Para la mejor relación calidad/CPU en FM, usa **1–2 MHz**.

SoapySDR filtra los presets según el rango soportado por el hardware. En **modo simulado** están todos disponibles.

---

## Perfiles DSP por preset

Implementados en `core/dsp_profiles.py`. El worker RX selecciona perfil automáticamente.

| Preset | SR demod máx | SR demod mín | chunk_scale | Modos recomendados |
|--------|--------------|--------------|-------------|-------------------|
| 250 kHz | 160 kHz | 80 kHz | 0.25 | nbfm, am, usb, lsb |
| 500 kHz | 250 kHz | 100 kHz | 0.5 | am, nbfm |
| 1 MHz | 560 kHz | 250 kHz | 0.75 | **wbfm**, nbfm |
| 2.048 MHz | 560 kHz | 250 kHz | 1.0 | wbfm (referencia) |
| 4 MHz | 768 kHz | 250 kHz | 1.0 | wbfm, espectro |
| 8 MHz | 768 kHz | 250 kHz | 1.0 | wbfm, máximo span |

Documentación completa: [dsp.md](dsp.md), [audio-presets-research.md](audio-presets-research.md).

---

## Desacople espectro / audio

Un solo `read_samples(N)` alimenta ambas rutas:

| Ruta | Muestras IQ | Propósito |
|------|-------------|-----------|
| Espectro / cascada | Chunk completo `N` | FFT, SNR, máxima resolución |
| Audio demod | Cola `samples[-audio_iq_samples:]` | Menor latencia en presets bajos |

`compute_audio_chunk_samples()` limita la cola según preset (p. ej. 8k @ 250 kHz vs 65k @ 8 MHz).

---

## Secuencia al cambiar bandwidth

```mermaid
sequenceDiagram
    participant U as Usuario
    participant TUI as XyzSDRApp
    participant DEV as SDRDevice
    participant RX as RX Worker

    U->>TUI: Selecciona nuevo bandwidth
    TUI->>TUI: _bandwidth_changing = true
    alt RX activo
        TUI->>RX: _stop_rx() + espera _rx_stop_event
    end
    TUI->>DEV: set_sample_rate(rate)
    TUI->>TUI: _rebuild_zoom_levels()
    TUI->>TUI: _adapt_viewport_to_bandwidth()
    Note over TUI: tuned_frequency y viewport_center NO cambian
    TUI->>DEV: set_frequency(tuned_frequency)
    TUI->>TUI: _sync_viewport()
    TUI->>TUI: patch_device_section(TOML)
    alt RX estaba activo
        TUI->>RX: _start_rx()
    end
    TUI->>TUI: _bandwidth_changing = false
```

### Regla de adaptación de zoom

```
Si visible_span > sample_rate:
    visible_span = sample_rate   (zoom-out máximo)
    viewport_center → sin cambios
Si visible_span <= sample_rate:
    mantener visible_span (recalcular zoom_index)
```

---

## Configuración persistente

Archivo: `config/defaults.toml` → sección `[device]`:

```toml
[device]
driver       = "sdrplay"
sample_rate  = 2_048_000      # Bandwidth IQ en Hz
center_freq  = 100_600_000
gain         = 40.0
```

La persistencia la gestiona `core/config_store.py` (`patch_device_section`). Se actualiza al cambiar bandwidth o driver con éxito.

Al arrancar, si `sample_rate` del TOML difiere del default del dispositivo y es soportado, se aplica automáticamente.

---

## Cambio de driver (Esc → Hardware)

`change_device_driver()` en `tui/app.py`:

- Detiene RX, cierra el dispositivo, abre el nuevo driver.
- Si falla (p. ej. SDRplay sin SoapySDR): **rollback** al driver anterior, log de error, **sin crash**.
- Devuelve `bool`; el menú de ajustes re-sincroniza el Select.

---

## Archivos relevantes

| Archivo | Responsabilidad |
|---------|-----------------|
| `core/device.py` | `set_sample_rate()`, `get_supported_sample_rates()` |
| `core/dsp.py` | `compute_rx_chunk_samples()`, demod, `resample_iq_for_demod`, `resample_audio_to_rate` |
| `core/dsp_profiles.py` | Perfiles DSP por preset IQ |
| `core/config_store.py` | Persistencia TOML |
| `tui/app.py` | `change_bandwidth()`, zoom dinámico, worker RX |
| `tui/widgets/settings_menu.py` | Cambio de driver con rollback |

Ver también [audio-presets-research.md](audio-presets-research.md) para la matriz completa por preset y [configuration.md](configuration.md) para claves TOML.

---

## Worker RX y cambios en caliente

- El worker captura un **snapshot** de `sample_rate`, frecuencia y modo por iteración.
- `_rx_stop_event` sincroniza parada/arranque durante cambios de bandwidth o driver.
- Errores transitorios durante `_bandwidth_changing` se ignoran sin tumbar la TUI.
