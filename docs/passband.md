# Banda audible (PASS) — xyz-sdr

La **banda audible** (`PASS`) es el ancho de espectro que el demodulador usa para generar audio. Es independiente del **ZOOM** (span visible) y del **BW** (sample rate IQ del hardware).

---

## Interfaz

| Control | Acción |
|---------|--------|
| Clic en timeline o espectro | Fija el **centro** de la banda |
| Clic + arrastre simétrico | Define el **ancho** (`width = 2 × |cursor − centro|`) |
| Clic corto (sin arrastre) | Centro + ancho por defecto del modo |
| `[` / `]` | Estrecha / ensancha la banda (paso según modo) |

Overlay visual:

- **Timeline**: zona verde `▓` y lectura `▼ 100.600 MHz | 120 kHz`
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

Definidos en `core/passband.py`. Persistencia en `[dsp]` de `config/defaults.toml`:

- `wbfm_bandwidth`, `nbfm_bandwidth`, `am_bandwidth`
- `fm_deemphasis_us` (50 µs EU por defecto, 75 µs US)
- `fm_agc_enabled` (AGC post-demod FM, default `true`)

---

## DSP

1. `shift_to_baseband()` — alinea el centro de PASS con DC si hace falta
2. Filtro paso bajo con ancho configurable en `demod_wbfm` / `demod_nbfm` / `demod_am`
3. De-emphasis FM tras demodulación (`fm_deemphasis_us`)

El worker RX en `tui/app.py` pasa `passband_width_hz` y `frequency_offset_hz` a `core/dsp.demodulate()`.

---

## Módulos

| Archivo | Rol |
|---------|-----|
| `core/passband.py` | Límites, clamp, col↔freq |
| `tui/widgets/passband_messages.py` | `PassbandDragMixin`, mensajes |
| `tui/widgets/frequency_timeline.py` | Regla + overlay |
| `tui/widgets/spectrum_graph.py` | Arrastre + overlay vertical |

Ver también [widgets.md](widgets.md) y [bandwidth.md](bandwidth.md).
