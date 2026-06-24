# Configuración — `config/defaults.toml`

Referencia de todas las claves del archivo TOML por defecto. La app carga el archivo al arrancar (`main.py --config`); la UI persiste cambios parciales vía `core/config_store.py`.

**Relacionado:** [customization.md](customization.md) (cómo modificar), [bandwidth.md](bandwidth.md), [audio.md](audio.md), [display.md](display.md).

---

## Ubicación y CLI

| Opción | Descripción |
|--------|-------------|
| Ruta por defecto | `config/defaults.toml` |
| `--config PATH` | Archivo alternativo |
| `--driver`, `--freq`, `--gain`, `--mode` | Sobrescriben valores de `[device]` / `[dsp]` al lanzar |

Los flags CLI tienen prioridad sobre el TOML en el arranque; los ajustes hechos en la TUI se escriben de vuelta al archivo.

---

## Persistencia desde la UI

`config_store.py` actualiza claves concretas **sin reescribir** el archivo entero (conserva comentarios inline):

| Función | Sección | Claves |
|---------|---------|--------|
| `patch_device_section` | `[device]` | `driver`, `sample_rate`, `center_freq`, `gain` |
| `patch_dsp_section` | `[dsp]` | squelch, volumen, anchos PASS, de-emphasis, AGC FM |
| `patch_display_section` | `[display]` | `waterfall_auto_level` |

Otras claves solo se editan a mano en el TOML.

---

## `[device]` — hardware SDR

| Clave | Tipo | Default | Descripción |
|-------|------|---------|-------------|
| `driver` | string | `"sdrplay"` | `"auto"`, `sdrplay`, `rtlsdr`, `hackrf`, `airspy`, … |
| `sample_rate` | int (Hz) | `500_000` | Bandwidth IQ / tasa de muestreo. Presets: 250k–8M — ver [bandwidth.md](bandwidth.md) |
| `center_freq` | int (Hz) | `97_780_487` | Frecuencia central del SDR al conectar |
| `gain` | float (dB) | `40.0` | Ganancia RF |
| `auto_gain` | bool | `false` | AGC hardware si el driver lo soporta |
| `ppm_correction` | int | `0` | Corrección PPM del oscilador |

---

## `[dsp]` — procesado y audio

| Clave | Tipo | Default | Descripción |
|-------|------|---------|-------------|
| `fft_size` | int | `2048` | Tamaño FFT base; escala con zoom — [architecture.md](architecture.md) |
| `fft_overlap` | float | `0.5` | Solapamiento entre ventanas FFT (0–1) |
| `fft_avg_windows` | int | `4` | Ventanas promediadas por iteración RX |
| `band_cache_cols` | int | `1024` | Columnas de rejilla espectral base |
| `display_fps` | int | `20` | Tope FPS espectro/cascada |
| `demod_mode` | string | `"wbfm"` | `wbfm`, `nbfm`, `am`, `usb`, `lsb` |
| `audio_rate` | int | `48_000` | Hz de salida de audio — [dsp.md](dsp.md) |
| `wbfm_bandwidth` | int | `80_000` | Ancho PASS WBFM (Hz) |
| `nbfm_bandwidth` | int | `12_500` | Ancho PASS NBFM |
| `am_bandwidth` | int | `15_000` | Ancho PASS AM |
| `fm_deemphasis_us` | int | `50` | De-emphasis FM: `50` (EU) o `75` (US) µs |
| `fm_agc_enabled` | bool | `true` | AGC post-demod FM |
| `volume` | float | `75.0` | Volumen 0–100 % |
| `squelch_db` | float | `-70.0` | Umbral squelch dBFS (legacy) |
| `squelch_enabled` | bool | `false` | Activa squelch |
| `squelch_threshold` | float | `5` | Umbral UI en dB (5–40) |
| `squelch_hang_ms` | int | `500` | Retardo antes de mutear (ms) |

Perfiles automáticos por preset IQ: `core/dsp_profiles.py` — [audio-presets-research.md](audio-presets-research.md).

---

## `[display]` — visualización

| Clave | Tipo | Default | Descripción |
|-------|------|---------|-------------|
| `waterfall_history` | int | `100` | Filas máximas en memoria |
| `waterfall_history_buffer_ratio` | float | `0.667` | Buffer extra sobre lo visible |
| `waterfall_auto_level` | bool | `true` | Auto-ajuste rango dB de la paleta |
| `waterfall_level_low_pct` | float | `5` | Percentil inferior (modo auto global) |
| `waterfall_level_high_pct` | float | `99` | Percentil superior |
| `waterfall_min_range_db` | float | `6.0` | Rango mínimo dB |
| `display_level_mode` | string | `"per_column"` | `"global"` \| `"per_column"` |
| `column_floor_pct` | float | `10` | Percentil suelo por columna |
| `column_ceiling_pct` | float | `99` | Percentil techo por columna |
| `column_ema_attack` | float | `0.35` | EMA rápida |
| `column_ema_release` | float | `0.08` | EMA lenta |
| `column_smooth_bins` | int | `3` | Suavizado lateral 1D |
| `column_history_rows` | int | `32` | Filas waterfall para estimar suelo |
| `freq_span_mhz` | float | `0.5` | Span inicial mostrado (MHz); suele coincidir con `sample_rate`/1e6 |
| `color_theme` | string | `"cyberpunk"` | Tema de color TUI |

Detalle del pipeline visual: [display.md](display.md).

---

## `[recorder]` — grabación (Fase 3, parcial)

| Clave | Tipo | Default | Descripción |
|-------|------|---------|-------------|
| `output_dir` | string | `""` | Vacío → `~/Music/xyz-sdr` |
| `record_iq` | bool | `true` | SigMF IQ |
| `record_audio` | bool | `true` | WAV demodulado |
| `iq_format` | string | `"sigmf"` | `sigmf`, `raw`, `wav` |
| `audio_format` | string | `"wav"` | Formato audio |
| `auto_record` | bool | `false` | Grabación automática |
| `trigger_db` | float | `-50.0` | Umbral de activación (dB) |

---

## `[ai]` — transcripción y clasificación (planificado)

| Clave | Tipo | Default | Descripción |
|-------|------|---------|-------------|
| `whisper_enabled` | bool | `false` | Transcripción Whisper |
| `whisper_model` | string | `"base"` | `tiny` … `large` |
| `whisper_language` | string | `"es"` | Idioma ISO |
| `classifier_enabled` | bool | `false` | Clasificador de modulación |
| `classifier_model` | string | `"./ai/models/..."` | Ruta modelo sklearn |

Ver [roadmap.md](roadmap.md) fases 4–5.

---

## `[scanner]` — escáner espectral (planificado)

| Clave | Tipo | Default | Descripción |
|-------|------|---------|-------------|
| `enabled` | bool | `false` | Activa escáner |
| `freq_start` | int | `88_000_000` | Inicio barrido (Hz) |
| `freq_end` | int | `108_000_000` | Fin barrido |
| `freq_step` | int | `200_000` | Paso (Hz) |
| `dwell_ms` | int | `500` | Tiempo por frecuencia |
| `min_snr_db` | float | `10.0` | SNR mínima para detener |

---

## Ejemplo mínimo FM broadcast

```toml
[device]
driver       = "sdrplay"
sample_rate  = 1_000_000
center_freq  = 100_600_000
gain         = 40.0

[dsp]
demod_mode       = "wbfm"
fm_deemphasis_us = 50
fm_agc_enabled   = true
wbfm_bandwidth   = 200_000
volume           = 75.0
```

---

## Depuración

Con `--debug`, la TUI muestra métricas DSP (SR captura/demod, chunk audio, underruns). Ver [audio.md](audio.md) y [hardware.md](hardware.md).
