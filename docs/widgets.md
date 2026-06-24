# 🔌 Documentación de Widgets Personalizados — xyz-sdr

Este documento detalla el funcionamiento interno de los tres componentes visuales interactivos de la aplicación.

Index: [README.md](README.md) | PASS: [passband.md](passband.md) | Display: [display.md](display.md) | Viewport: [architecture.md](architecture.md)

---

## 1. `FrequencyTimeline` (Regla de Frecuencias)

Dibuja una regla horizontal interactiva alineada con el espectro y la cascada.

### Estructura de Renderizado
El método `render()` genera tres filas de texto enriquecido:
1. **Fila 1 (Cursores e Indicador Digital)**:
   * Coloca el cursor sintonizado principal `▼` (rojo) y el cursor de previsualización `▽` (celeste) en sus columnas respectivas.
   * Superpone una lectura digital en alta resolución (ej. `▽ 100.600000 MHz`) en los márgenes de la fila de forma adaptativa.
2. **Fila 2 (Marcas de Ticks)**:
   * Coloca líneas verticales `│` coloreadas en las frecuencias calculadas como "ticks" o en la posición del cursor de sintonía. El resto se completa con líneas de unión horizontales `─`.
3. **Fila 3 (Etiquetas Numéricas)**:
   * Renderiza el valor numérico en MHz (ej. `100.6M`) centrado bajo su marca correspondiente.

### Matemáticas de Ticks (`_nice_tick_spacing`)
Para evitar que las marcas numéricas se solapen o queden demasiado dispersas al variar el zoom (span), el widget calcula dinámicamente un paso de marcas legible utilizando múltiplos de 1, 2, 5 o 10:
$$\text{Spacing} = \text{nice\_step} \times 10^{\lfloor \log_{10}(\text{raw\_spacing}) \rfloor}$$
Donde `nice_step` se ajusta a `[1.0, 2.0, 5.0, 10.0]` según la escala visual óptima.

---

## 2. `SpectrumGraph` (Analizador Espectral FFT)

Muestra los picos de potencia de la señal en tiempo real mediante barras verticales de caracteres ASCII (`▁▂▃▄▅▆▇█`).

### Algoritmo de Agregación de Picos (Máxima Resolución)
Al renderizar spans muy anchos de frecuencia en una terminal con pocas columnas, múltiples bins de la FFT caen dentro del rango representado por un único carácter. El widget usa agregación **máximo** vía `slice_band_to_viewport` en `core/band_buffer.py`. Con zoom activo, el worker RX escala `fft_size` y `band_cache_cols` (`compute_effective_fft_size` / `compute_effective_band_cols`) para mantener detalle espectral.

Un contorno de pico (`·`) marca la curva de la señal encima del relleno de barras ASCII (`▁▂▃▄▅▆▇█`).

### Niveles por columna

El espectro no calcula sus propios min/max: recibe `floor[]` y `ceiling[]` desde `XyzSDRApp._flush_display_frames()` vía `set_column_levels()`. La normalización usa `normalize_per_column()` de `display_palette.py`.

Detalle del algoritmo y configuración: [display.md](display.md).

---

## 3. `WaterfallTimeline` (Espectrograma en Cascada)

Muestra la actividad del espectro a lo largo del tiempo. Las filas nuevas se añaden **arriba**; el historial baja cuando la pantalla está llena. Cada fila temporal ocupa exactamente una línea de terminal — el zoom horizontal solo afecta el eje de frecuencia, no la densidad temporal.

### Auto-level de paleta

Con `waterfall_auto_level = true` en `[display]` del TOML, el rango dB de la paleta se ajusta automáticamente. Hay dos modos (`display_level_mode`):

| Modo | Clave TOML | Comportamiento |
|------|------------|----------------|
| **Por columna** (recomendado) | `per_column` | Cada bin de frecuencia tiene su propio suelo/techo estimado con percentiles + EMA asimétrica sobre el frame actual y las últimas filas del waterfall (`column_history_rows`). Compensa pendientes de ruido izquierda→derecha. |
| **Global** | `global` | Un solo min/max para todo el viewport (percentiles P5–P99 sobre `cols`). |

Parámetros relevantes en `[display]`:
- `column_floor_pct` / `column_ceiling_pct` — percentiles por columna (por defecto 10 / 99).
- `column_ema_attack` / `column_ema_release` — suavizado temporal (suelo baja rápido, sube lento).
- `column_smooth_bins` — media móvil lateral para evitar rayas verticales entre columnas.
- `waterfall_min_range_db` — rango mínimo por columna; escala ligeramente con el zoom (`visible_span / sample_rate`).

Desactiva el modo auto desde **Ajustes → Waterfall auto** para usar un rango fijo (`-80` / `-20` dB). Los colores interpolan linealmente entre paradas del gradiente `THERMAL_GRADIENT` en `tui/widgets/display_palette.py` — **el mismo gradiente y los mismos niveles dB** se aplican al espectro y al waterfall para que pico y cascada coincidan en color y posición horizontal.

El ancho de columnas espectrales lo fija el espectro (`plot_content_width`); espectro y waterfall comparten el mismo ancho al 100%.

### Barra de velocidad

Entre el espectro y la cascada hay una fila horizontal (`#waterfall_speed_row`) con botones `1 2 3 5 10 25 50` (FPS de la cascada). Ya no se superpone con `dock: right` sobre el waterfall.

### Alineación Dinámica Histórica
A diferencia de los waterfalls clásicos que asumen una frecuencia fija, `WaterfallTimeline` admite que el usuario cambie el zoom y el centro del viewport en cualquier momento.
Cada línea guardada en la historia se encapsula en un objeto `_WaterfallRow` que contiene la frecuencia central de captura exacta (`center_hz`), la tasa de muestreo (`sample_rate`) y los datos de potencia (`psd`):
```python
row_left_hz = row.center_hz - row.sample_rate / 2
row_right_hz = row.center_hz + row.sample_rate / 2
```
Al renderizar cualquier columna `col` en la pantalla:
1. Calculamos su frecuencia física absoluta: $f = f_{start} + col \times f_{per\_col}$.
2. Si $f$ está dentro de `[row_left_hz, row_right_hz]`, mapeamos e interpolamos la señal de esa captura histórica mediante agregación de picos (`np.max`) en el segmento correspondiente.
3. Si $f$ está fuera del rango del hardware capturado en esa fila, pintamos el carácter de inactividad `░` con un fondo de color de inactividad `#08080f`.

Esto crea un efecto de **re-alineamiento físico dinámico**: si sintonizas a otra frecuencia o cambias el zoom, la historia visible de la cascada se deforma, escala y desplaza coherentemente en pantalla en lugar de borrarse o desplazarse de forma errática.

---

## 🖱️ Interactividad de Ratón — Banda audible (PASS)

`FrequencyTimeline` y `SpectrumGraph` comparten el mixin `PassbandDragMixin` (`tui/widgets/passband_messages.py`):

1. **`mouse_down`**: fija el **centro** de la banda audible en la columna clicada.
2. **`mouse_move`** (botón pulsado): calcula ancho simétrico  
   `width = 2 × |f_cursor − f_center|` y publica `PassbandPreview`.
3. **`mouse_up`**: publica `PassbandSelectRequest(center, width)`.
4. **Clic corto** (arrastre &lt; 5 px): ancho por defecto del modo (`wbfm` 200 kHz, etc.).

Overlay visual:
- Timeline: zona `▓` verde en la fila de ticks + lectura `▼ 100.600 MHz | 120 kHz`.
- Espectro: columnas dentro de PASS en color normal; fuera, atenuadas.
- Cascada: overlay pasivo (columnas fuera de PASS más oscuras).

La barra de estado muestra **PASS** (ancho audible) separado de **ZOOM** (span visible) y **BW** (sample rate IQ).

## 🖱️ Scroll y zoom

Timeline, espectro y cascada comparten:
* **`on_mouse_scroll_up` / `on_mouse_scroll_down`**:
  * Desplazamiento normal: `ScrollRequest` (cambia frecuencia sintonizada).
* **`Shift + Rueda`** en cascada: desplazar historial vertical (filas antiguas).

Documentación ampliada: [display.md](display.md).
