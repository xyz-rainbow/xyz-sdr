# Banda audible (PASS) — xyz-sdr

La **banda audible** (`PASS`) es el ancho de espectro que el demodulador usa para generar audio. Es independiente del **ZOOM** (span visible) y del **BW** (sample rate IQ del hardware).

Index: [README.md](README.md) | DSP: [dsp.md](dsp.md)

---

## Interfaz

| Control | Acción |
|---------|--------|
| Clic en timeline o espectro | Fija el **centro** de la banda |
| Clic + arrastre simétrico | Define el **ancho** (`width = 2 × \|cursor − centro\|`) |
| Clic corto (sin arrastre) | Centro + ancho por defecto del modo |
| `[` / `]` | Estrecha / ensancha la banda (paso según modo) |

Overlay visual:

- **Timeline**: zona verde `▓` y lectura `▼ 100.600 MHz \| 120 kHz`
- **Espectro**: columnas dentro de PASS a color; fuera, atenuadas
- **Cascada**: columnas fuera de PASS más oscuras

Barra de estado: métrica **PASS** junto a ZOOM y BW.

---

## Límites por modo

| Modo | Default | Mín | Máx |
|------|---------|-----|-----|
| wbfm | 200 kHz | 80 kHz | 250 kHz |
| nbfm | 12.5 kHz | 5 kHz | 25 kHz |
| am | 10 kHz | 3 kHz | 15 kHz |
| usb | 3 kHz | 1.5 kHz | 6 kHz |
| lsb | 3 kHz | 1.5 kHz | 6 kHz |

Definidos en `core/passband.py` → `PASSBAND_DEFAULTS`, `PASSBAND_LIMITS`.

---

## Persistencia (`config/defaults.toml` → `[dsp]`)

| Clave | Descripción |
|-------|-------------|
| `wbfm_bandwidth` | PASS default WBFM |
| `nbfm_bandwidth` | PASS default NBFM |
| `am_bandwidth` | PASS default AM |
| `fm_deemphasis_us` | 50 µs EU / 75 µs US |
| `fm_agc_enabled` | AGC post-demod FM |

USB/LSB usan default 3 kHz en código; PASS UI aplica clamp 1.5–6 kHz.

---

## Cadena DSP

1. **`shift_to_baseband(offset)`** — centra PASS en DC si `passband_center ≠ tuned_frequency`
2. **`resample_iq_for_demod(bw)`** — según preset IQ ([bandwidth.md](bandwidth.md))
3. **`low_pass_filter(bw/2)`** — FIR adaptativo
4. **Demod** — FM / AM / SSB según modo
5. **`resample_audio_to_rate(48000)`** — salida exacta
6. **De-emphasis** (FM) → normalize → AGC → squelch

El worker RX pasa a `demodulate()`:

- `passband_width_hz`
- `frequency_offset_hz = passband_center - tuned_frequency`
- `fm_state` (continuidad FM entre chunks)

---

## Interacción PASS × BANDWIDTH

| IQ preset | WBFM | NBFM/AM/SSB |
|-----------|------|-------------|
| 250 kHz | PASS max = Nyquist — **no ideal** | Recomendado |
| 500 kHz – 1 MHz | OK | OK |
| 2.048 MHz | Referencia diseño | OK |
| 4–8 MHz | Audio OK (IQ decimado internamente) | OK |

Al cambiar a 250 kHz en WBFM, la app avisa en el log.

---

## Módulos

| Archivo | Rol |
|---------|-----|
| `core/passband.py` | Límites, clamp, col↔freq |
| `tui/widgets/passband_messages.py` | `PassbandDragMixin`, mensajes |
| `tui/widgets/frequency_timeline.py` | Regla + overlay |
| `tui/widgets/spectrum_graph.py` | Arrastre + overlay vertical |
| `tui/widgets/waterfall_timeline.py` | Overlay pasivo |

Ver [widgets.md](widgets.md), [display.md](display.md) y [bandwidth.md](bandwidth.md).

---

## Tests

`resources/test/test_passband_selection.py` — mapping, clamp, drag simétrico.
