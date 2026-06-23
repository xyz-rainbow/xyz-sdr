# 🔌 Documentación de Widgets Personalizados — xyz-sdr

Este documento detalla el funcionamiento interno de los tres componentes visuales interactivos de la aplicación.

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

---

## 3. `WaterfallTimeline` (Espectrograma en Cascada)

Muestra la actividad del espectro a lo largo del tiempo. Las filas nuevas se añaden **abajo**; el historial sube cuando la pantalla está llena (estilo SDR clásico). Cada fila temporal ocupa exactamente una línea de terminal — el zoom horizontal solo afecta el eje de frecuencia, no la densidad temporal.

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
  * `Ctrl + Rueda`: `ZoomRequest` (span visible).
